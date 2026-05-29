"""Configuration models and persistence helpers for CHaron."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator

DEFAULT_CONFIG_PATH = Path.home() / ".charon" / "config.yaml"


class InstanceConfig(BaseModel):
    host: str
    user: str = "default"
    password: str = ""
    database: str
    timeout: int = 3600
    tcp_hostport: str | None = None  # required on dst for remote() INSERT

    @field_validator("host")
    @classmethod
    def normalize_host(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            v = f"http://{v}"
        return v

    def __repr__(self) -> str:
        return (
            f"InstanceConfig(host={self.host!r}, user={self.user!r}, "
            f"password='***', database={self.database!r})"
        )


class InsertSettings(BaseModel):
    max_partitions_per_insert_block: int = 1000
    max_insert_block_size: int = 1_048_576
    max_threads: int = 8
    send_logs_level: str = "warning"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class CopyProfile(BaseModel):
    src: InstanceConfig
    dst: InstanceConfig
    copy_by_partitions: bool = True
    copy_views: bool = False
    copy_kafka_tables: bool = False
    copy_dictionaries: bool = False
    convert_replicated_to_merge: bool = False
    skip_tables: list[str] = []
    retry_count: int = 3
    retry_sleep: float = 2.0
    retry_max_sleep: float = 30.0
    insert_settings: InsertSettings = InsertSettings()


class AppConfig(BaseModel):
    profiles: dict[str, CopyProfile] = {}
    default_profile: str = "default"

    def get_profile(self, name: str | None = None) -> CopyProfile:
        key = name or self.default_profile
        if key not in self.profiles:
            raise KeyError(f"Profile '{key}' not found. Available: {list(self.profiles)}")
        return self.profiles[key]


# ---------------------------------------------------------------------------
# Load / save helpers
# ---------------------------------------------------------------------------


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load config from YAML file. Returns empty AppConfig if file does not exist."""
    if not path.exists():
        return AppConfig()
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    return AppConfig.model_validate(data)


def save_config(config: AppConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Save config to YAML and restrict permissions to owner-only (0o600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(config.model_dump(), f, allow_unicode=True, sort_keys=False)
    os.chmod(path, 0o600)


def config_path_from_option(path_str: str | None) -> Path:
    """Resolve config path from CLI option or use default."""
    return Path(path_str) if path_str else DEFAULT_CONFIG_PATH
