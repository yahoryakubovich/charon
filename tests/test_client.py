"""Tests for charon.client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from charon.client import CHClient, ClickHouseError, RetryConfig
from charon.config import InstanceConfig


def _make_client(retry_count: int = 1, retry_sleep: float = 0.0) -> CHClient:
    cfg = InstanceConfig(host="http://ch:8123", user="default", password="", database="testdb")
    retry = RetryConfig(retry_count=retry_count, retry_sleep=retry_sleep, retry_max_sleep=1.0)
    return CHClient(cfg, retry=retry)


def _fake_response(text: str = "1\n", status: int = 200) -> MagicMock:
    r = MagicMock(spec=requests.Response)
    r.status_code = status
    r.text = text
    return r


class TestPing:
    def test_returns_true_on_200(self) -> None:
        client = _make_client()
        with patch.object(client._session, "post", return_value=_fake_response("1\n")) as mock_post:
            assert client.ping() is True
            mock_post.assert_called_once()

    def test_returns_false_on_connection_error(self) -> None:
        client = _make_client()
        with patch.object(client._session, "post", side_effect=requests.ConnectionError("refused")):
            assert client.ping() is False

    def test_returns_false_on_http_500(self) -> None:
        client = _make_client()
        with patch.object(client._session, "post", return_value=_fake_response("err", 500)):
            assert client.ping() is False


class TestQueryRows:
    def test_parses_json_each_row(self) -> None:
        rows = [{"name": "t1", "rows": 10}, {"name": "t2", "rows": 20}]
        text = "\n".join(json.dumps(r) for r in rows) + "\n"
        client = _make_client()
        with patch.object(client._session, "post", return_value=_fake_response(text)):
            result = client.query_rows("SELECT 1")
        assert result == rows

    def test_appends_format_json_each_row(self) -> None:
        client = _make_client()
        with patch.object(client._session, "post", return_value=_fake_response("")) as mock_post:
            client.query_rows("SELECT 1")
        sent_sql: bytes = mock_post.call_args.kwargs["data"]
        assert b"FORMAT JSONEachRow" in sent_sql

    def test_empty_response_returns_empty_list(self) -> None:
        client = _make_client()
        with patch.object(client._session, "post", return_value=_fake_response("")):
            assert client.query_rows("SELECT 1") == []


class TestRetry:
    def test_retries_on_network_error_then_succeeds(self) -> None:
        client = _make_client(retry_count=3, retry_sleep=0.0)
        responses = [
            requests.ConnectionError("fail 1"),
            requests.ConnectionError("fail 2"),
            _fake_response("1\n"),
        ]

        def side_effect(*args: object, **kwargs: object) -> object:
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with patch.object(client._session, "post", side_effect=side_effect) as mock_post:
            with patch("time.sleep"):
                result = client.query("SELECT 1", skip_database=True)
        assert result == "1\n"
        assert mock_post.call_count == 3

    def test_raises_clickhouse_error_after_all_retries(self) -> None:
        client = _make_client(retry_count=2, retry_sleep=0.0)
        with patch.object(
            client._session, "post", side_effect=requests.ConnectionError("always fails")
        ):
            with patch("time.sleep"):
                with pytest.raises(ClickHouseError):
                    client.query("SELECT 1", skip_database=True)

    def test_exponential_backoff_sleep_called(self) -> None:
        client = _make_client(retry_count=3, retry_sleep=2.0)
        client._retry.retry_max_sleep = 100.0
        with patch.object(client._session, "post", side_effect=requests.ConnectionError("fail")):
            with patch("time.sleep") as mock_sleep:
                with pytest.raises(ClickHouseError):
                    client.query("SELECT 1", skip_database=True)
        # Should have slept at least twice (attempts 0 and 1)
        assert mock_sleep.call_count == 2
        # First sleep should be ~2.0s (base), second ~4.0s (2^1 * base)
        first_sleep = mock_sleep.call_args_list[0][0][0]
        second_sleep = mock_sleep.call_args_list[1][0][0]
        assert first_sleep < second_sleep  # exponential: second > first

    def test_clickhouse_error_not_retried(self) -> None:
        """HTTP 500 from ClickHouse should NOT be retried — it's a CH error, not transient."""
        client = _make_client(retry_count=3, retry_sleep=0.0)
        with patch.object(
            client._session, "post", return_value=_fake_response("Code: 60. DB not found", 500)
        ) as mock_post:
            with pytest.raises(ClickHouseError):
                client.query("SELECT 1", skip_database=True)
        # Should only call once (no retry for ClickHouseError)
        assert mock_post.call_count == 1
