"""Tests for charon.config."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from charon.config import AppConfig, CopyProfile, InstanceConfig, load_config, save_config


def _make_profile(
    src_host: str = "http://src:8123", dst_host: str = "http://dst:8123"
) -> CopyProfile:
    return CopyProfile(
        src=InstanceConfig(host=src_host, user="u", password="secret", database="mydb"),
        dst=InstanceConfig(host=dst_host, user="u2", password="secret2", database="mydb2"),
    )


class TestLoadConfig:
    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.profiles == {}

    def test_save_and_reload(self, tmp_config_path: Path) -> None:
        profile = _make_profile()
        cfg = AppConfig(profiles={"prod": profile}, default_profile="prod")
        save_config(cfg, tmp_config_path)

        loaded = load_config(tmp_config_path)
        assert "prod" in loaded.profiles
        assert loaded.profiles["prod"].src.database == "mydb"

    def test_host_normalization_on_load(self, tmp_config_path: Path) -> None:
        """Hosts without scheme should get http:// prepended."""
        profile = _make_profile(src_host="src-host:8123")
        cfg = AppConfig(profiles={"x": profile})
        save_config(cfg, tmp_config_path)

        loaded = load_config(tmp_config_path)
        assert loaded.profiles["x"].src.host.startswith("http://")

    def test_missing_profile_raises_key_error(self, tmp_config_path: Path) -> None:
        cfg = AppConfig(profiles={"dev": _make_profile()}, default_profile="dev")
        save_config(cfg, tmp_config_path)

        loaded = load_config(tmp_config_path)
        with pytest.raises(KeyError, match="prod"):
            loaded.get_profile("prod")

    def test_get_profile_default(self, tmp_config_path: Path) -> None:
        cfg = AppConfig(profiles={"default": _make_profile()}, default_profile="default")
        save_config(cfg, tmp_config_path)

        loaded = load_config(tmp_config_path)
        p = loaded.get_profile()  # no name → uses default_profile
        assert p.src.database == "mydb"


class TestSaveConfig:
    def test_file_permissions_0o600(self, tmp_config_path: Path) -> None:
        cfg = AppConfig(profiles={"p": _make_profile()})
        save_config(cfg, tmp_config_path)

        mode = stat.S_IMODE(tmp_config_path.stat().st_mode)
        assert mode == 0o600

    def test_password_not_in_repr(self) -> None:
        ic = InstanceConfig(host="http://h:8123", password="topsecret", database="db")
        assert "topsecret" not in repr(ic)
        assert "***" in repr(ic)
