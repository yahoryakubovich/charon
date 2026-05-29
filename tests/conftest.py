"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from charon.config import CopyProfile, InstanceConfig


@pytest.fixture
def sample_profile() -> CopyProfile:
    """A CopyProfile with fake src and dst for testing."""
    return CopyProfile(
        src=InstanceConfig(
            host="http://src-host:8123",
            user="src_user",
            password="src_secret",
            database="src_db",
        ),
        dst=InstanceConfig(
            host="http://dst-host:8123",
            user="dst_user",
            password="dst_secret",
            database="dst_db",
            tcp_hostport="dst-host:9000",
        ),
        retry_count=1,
        retry_sleep=0.0,
        retry_max_sleep=0.0,
    )


@pytest.fixture
def tmp_config_path(tmp_path: Path) -> Path:
    """A temporary config file path."""
    return tmp_path / "config.yaml"


@pytest.fixture
def mock_ch_response():
    """
    Context manager that patches requests.Session.post to return a fake response.

    Usage::

        with mock_ch_response("line1\\nline2\\n", status_code=200) as mock_post:
            ...
    """

    @contextmanager
    def _mock(text: str = "", status_code: int = 200) -> Generator[MagicMock, None, None]:
        fake_response = MagicMock(spec=requests.Response)
        fake_response.status_code = status_code
        fake_response.text = text
        with patch("requests.Session.post", return_value=fake_response) as mock_post:
            yield mock_post

    return _mock
