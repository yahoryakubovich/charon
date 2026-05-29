"""Pydantic models for API request/response payloads."""

from __future__ import annotations

from pydantic import BaseModel


class InstanceStatus(BaseModel):
    host: str
    database: str
    reachable: bool
    tables: int
    total_rows: int
    total_bytes: int


class TableRow(BaseModel):
    name: str
    engine: str
    src_rows: int
    dst_rows: int | None
    status: str
    diff_rows: int


class JobStatus(BaseModel):
    id: str
    profile: str
    table: str | None
    status: str  # queued / running / done / error
    started_at: str | None
    finished_at: str | None
    log_lines: list[str]


class JobSummary(BaseModel):
    id: str
    profile: str
    table: str | None
    status: str
    started_at: str | None
    finished_at: str | None


class CopyRequest(BaseModel):
    profile: str | None = None
    table: str | None = None


class ConfigUpdateRequest(BaseModel):
    """Partial update payload for the active profile."""

    src_host: str | None = None
    src_user: str | None = None
    src_password: str | None = None
    src_database: str | None = None
    dst_host: str | None = None
    dst_user: str | None = None
    dst_password: str | None = None
    dst_database: str | None = None
    dst_tcp_hostport: str | None = None
