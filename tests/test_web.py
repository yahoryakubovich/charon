"""Tests for the FastAPI web app."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from charon.config import AppConfig, CopyProfile, InstanceConfig, save_config
from charon.web.app import create_app


@pytest.fixture
def config_with_profile(tmp_path: Path) -> Path:
    """Write a minimal config file and return its path."""
    config_path = tmp_path / "config.yaml"
    profile = CopyProfile(
        src=InstanceConfig(host="http://src:8123", user="u", password="p", database="srcdb"),
        dst=InstanceConfig(
            host="http://dst:8123",
            user="u2",
            password="p2",
            database="dstdb",
            tcp_hostport="dst:9000",
        ),
        retry_count=1,
        retry_sleep=0.0,
        retry_max_sleep=0.0,
    )
    cfg = AppConfig(profiles={"default": profile}, default_profile="default")
    save_config(cfg, config_path)
    return config_path


@pytest.fixture
def client(config_with_profile: Path) -> TestClient:
    app = create_app(config_path=config_with_profile)
    return TestClient(app, raise_server_exceptions=True)


class TestDashboard:
    def test_get_root_returns_200(self, client: TestClient) -> None:
        r = client.get("/")
        assert r.status_code == 200
        assert "CHaron" in r.text

    def test_root_contains_html(self, client: TestClient) -> None:
        r = client.get("/")
        assert "<!DOCTYPE html>" in r.text or "<html" in r.text


class TestStatusAPI:
    def test_status_returns_two_entries(
        self, client: TestClient, config_with_profile: Path
    ) -> None:
        with patch("charon.web.app.CHClient") as MockClient:
            instance = MockClient.return_value
            instance.ping.return_value = True
            instance.db_stats.return_value = {"tables": 5, "total_rows": 1000, "total_bytes": 1024}
            r = client.get("/api/status")

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert data[0]["reachable"] is True or data[0]["reachable"] is False  # field present

    def test_status_schema(self, client: TestClient) -> None:
        with patch("charon.web.app.CHClient") as MockClient:
            instance = MockClient.return_value
            instance.ping.return_value = False
            instance.db_stats.return_value = {}
            r = client.get("/api/status")

        assert r.status_code == 200
        entry = r.json()[0]
        for field in ("host", "database", "reachable", "tables", "total_rows", "total_bytes"):
            assert field in entry


class TestCopyAPI:
    def test_post_copy_creates_job(self, client: TestClient) -> None:
        with (
            patch("charon.web.app.CHClient"),
            patch("charon.web.app.copy_database"),
        ):
            r = client.post("/api/copy", json={})

        assert r.status_code == 200
        data = r.json()
        assert "job_id" in data
        assert len(data["job_id"]) > 0

    def test_post_copy_with_table(self, client: TestClient) -> None:
        with (
            patch("charon.web.app.CHClient"),
            patch("charon.web.app.copy_database"),
        ):
            r = client.post("/api/copy", json={"table": "my_table"})

        assert r.status_code == 200
        job_id = r.json()["job_id"]

        # The job should appear in the job list
        r2 = client.get("/api/jobs")
        assert r2.status_code == 200
        job_ids = [j["id"] for j in r2.json()]
        assert job_id in job_ids


class TestJobsAPI:
    def test_list_jobs_empty(self, client: TestClient) -> None:
        r = client.get("/api/jobs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_nonexistent_job_404(self, client: TestClient) -> None:
        r = client.get("/api/jobs/nonexistent-job-id")
        assert r.status_code == 404


class TestConfigAPI:
    def test_get_config_masks_password(self, client: TestClient) -> None:
        r = client.get("/api/config")
        assert r.status_code == 200
        data = r.json()
        assert data["src"]["password"] == "***"
        assert data["dst"]["password"] == "***"

    def test_get_config_has_expected_fields(self, client: TestClient) -> None:
        r = client.get("/api/config")
        data = r.json()
        assert "src" in data
        assert "dst" in data
        assert data["src"]["host"] == "http://src:8123"
        assert data["src"]["database"] == "srcdb"

    def test_put_config_updates_host(self, client: TestClient, config_with_profile: Path) -> None:
        r = client.put("/api/config", json={"src_host": "http://new-src:8123"})
        assert r.status_code == 200

        r2 = client.get("/api/config")
        assert r2.json()["src"]["host"] == "http://new-src:8123"
