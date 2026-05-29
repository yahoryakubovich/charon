"""FastAPI application factory for the CHaron web dashboard."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from charon import __version__
from charon.client import CHClient, RetryConfig
from charon.config import (
    DEFAULT_CONFIG_PATH,
    CopyProfile,
    InstanceConfig,
    load_config,
    save_config,
)
from charon.copy import copy_database
from charon.diff import diff_tables

from .jobs import JobManager
from .models import (
    ConfigUpdateRequest,
    CopyRequest,
    InstanceStatus,
    JobStatus,
    JobSummary,
    TableRow,
)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app(
    config_path: Path = DEFAULT_CONFIG_PATH,
    profile_name: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI app."""
    app = FastAPI(title="charon", version=__version__)
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    job_manager = JobManager()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_profile() -> CopyProfile | None:
        cfg = load_config(config_path)
        try:
            return cfg.get_profile(profile_name)
        except KeyError:
            return None

    def _require_profile() -> CopyProfile:
        profile = _load_profile()
        if profile is None:
            raise HTTPException(
                status_code=503,
                detail="No profile configured. Open Settings to add a connection.",
            )
        return profile

    def _make_client(cfg_instance: InstanceConfig, profile: CopyProfile) -> CHClient:
        retry = RetryConfig(
            retry_count=profile.retry_count,
            retry_sleep=profile.retry_sleep,
            retry_max_sleep=profile.retry_max_sleep,
        )
        return CHClient(cfg_instance, retry=retry)

    # ------------------------------------------------------------------
    # Dashboard page
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"version": __version__},
        )

    # ------------------------------------------------------------------
    # Status API
    # ------------------------------------------------------------------

    @app.get("/api/configured")
    async def api_configured() -> dict[str, bool]:
        return {"configured": _load_profile() is not None}

    @app.get("/api/status", response_model=list[InstanceStatus])
    async def api_status() -> list[InstanceStatus]:
        profile = _require_profile()
        results: list[InstanceStatus] = []
        for side, cfg_inst in [("src", profile.src), ("dst", profile.dst)]:
            client = _make_client(cfg_inst, profile)
            reachable = client.ping()
            stats: dict[str, Any] = {}
            if reachable:
                try:
                    stats = client.db_stats(cfg_inst.database)
                except Exception:
                    pass
            results.append(
                InstanceStatus(
                    host=cfg_inst.host,
                    database=cfg_inst.database,
                    reachable=reachable,
                    tables=int(stats.get("tables") or 0),
                    total_rows=int(stats.get("total_rows") or 0),
                    total_bytes=int(stats.get("total_bytes") or 0),
                )
            )
        return results

    # ------------------------------------------------------------------
    # Tables diff API
    # ------------------------------------------------------------------

    @app.get("/api/tables", response_model=list[TableRow])
    async def api_tables() -> list[TableRow]:
        profile = _require_profile()
        src = _make_client(profile.src, profile)
        dst = _make_client(profile.dst, profile)

        src_tables = src.get_tables(profile.src.database)
        dst_tables = dst.get_tables(profile.dst.database)

        diffs = diff_tables(src_tables, dst_tables)

        rows: list[TableRow] = []
        for d in diffs:
            diff_rows = d.src_rows - (d.dst_rows or 0)
            rows.append(
                TableRow(
                    name=d.name,
                    engine=d.engine,
                    src_rows=d.src_rows,
                    dst_rows=d.dst_rows,
                    status=d.status,
                    diff_rows=diff_rows,
                )
            )
        return rows

    # ------------------------------------------------------------------
    # Copy API
    # ------------------------------------------------------------------

    @app.post("/api/copy")
    async def api_copy(req: CopyRequest) -> dict[str, str]:
        profile = _require_profile()
        cfg = load_config(config_path)
        actual_profile_name = req.profile or profile_name or cfg.default_profile

        job_id = job_manager.create_job(actual_profile_name, req.table)

        def _run(log: Any) -> None:
            retry = RetryConfig(
                retry_count=profile.retry_count,
                retry_sleep=profile.retry_sleep,
                retry_max_sleep=profile.retry_max_sleep,
            )
            src = CHClient(profile.src, retry=retry)
            dst = CHClient(profile.dst, retry=retry)

            from charon.copy import NullCallback

            class LogCallback(NullCallback):
                def on_table_start(self, table: str, engine: str, partitions: int) -> None:
                    log(f"START {table} ({engine}) — {partitions} partition(s) to copy")

                def on_partition_done(self, table: str, partition_id: str) -> None:
                    log(f"  partition {partition_id} done")

                def on_table_done(self, table: str) -> None:
                    log(f"DONE {table}")

                def on_table_skip(self, table: str, reason: str) -> None:
                    log(f"SKIP {table}: {reason}")

                def on_error(self, table: str, error: Exception) -> None:
                    log(f"ERROR {table}: {error}")

            copy_database(
                src=src,
                dst=dst,
                profile=profile,
                callback=LogCallback(),
                table_filter=[req.table] if req.table else None,
            )

        job_manager.start_job(job_id, _run)
        return {"job_id": job_id}

    # ------------------------------------------------------------------
    # Jobs API
    # ------------------------------------------------------------------

    @app.get("/api/jobs", response_model=list[JobSummary])
    async def api_list_jobs() -> list[JobSummary]:
        return job_manager.list_jobs()

    @app.get("/api/jobs/{job_id}", response_model=JobStatus)
    async def api_get_job(job_id: str) -> JobStatus:
        job = job_manager.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.get("/api/jobs/{job_id}/stream")
    async def api_stream_job(job_id: str) -> StreamingResponse:
        """Server-Sent Events stream of log lines for a job."""

        async def _event_generator() -> AsyncGenerator[str, None]:
            loop = asyncio.get_event_loop()
            gen = job_manager.iter_log(job_id)
            try:
                while True:
                    line = await loop.run_in_executor(None, lambda: next(gen, None))
                    if line is None:
                        yield "event: done\ndata: {}\n\n"
                        break
                    yield f"data: {line}\n\n"
            except asyncio.CancelledError:
                pass

        return StreamingResponse(
            _event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ------------------------------------------------------------------
    # Config API
    # ------------------------------------------------------------------

    @app.get("/api/config")
    async def api_get_config() -> dict[str, Any]:
        profile = _load_profile()
        if profile is None:
            empty = {"host": "", "user": "", "password": "", "database": "", "timeout": 3600}
            return {
                "src": empty,
                "dst": {**empty, "tcp_hostport": None},
                "copy_by_partitions": True,
                "retry_count": 3,
                "retry_sleep": 2.0,
            }
        return {
            "src": {
                "host": profile.src.host,
                "user": profile.src.user,
                "password": "***",
                "database": profile.src.database,
                "timeout": profile.src.timeout,
            },
            "dst": {
                "host": profile.dst.host,
                "user": profile.dst.user,
                "password": "***",
                "database": profile.dst.database,
                "timeout": profile.dst.timeout,
                "tcp_hostport": profile.dst.tcp_hostport,
            },
            "copy_by_partitions": profile.copy_by_partitions,
            "retry_count": profile.retry_count,
            "retry_sleep": profile.retry_sleep,
        }

    @app.put("/api/config")
    async def api_update_config(req: ConfigUpdateRequest) -> dict[str, str]:
        cfg = load_config(config_path)
        profile = _load_profile()

        src_data = profile.src.model_dump() if profile else {
            "host": "http://localhost:8123", "user": "default",
            "password": "", "database": "default", "timeout": 3600,
        }
        dst_data = profile.dst.model_dump() if profile else {
            "host": "http://localhost:8123", "user": "default",
            "password": "", "database": "default", "timeout": 3600, "tcp_hostport": None,
        }

        if req.src_host is not None:
            src_data["host"] = req.src_host
        if req.src_user is not None:
            src_data["user"] = req.src_user
        if req.src_password is not None:
            src_data["password"] = req.src_password
        if req.src_database is not None:
            src_data["database"] = req.src_database
        if req.dst_host is not None:
            dst_data["host"] = req.dst_host
        if req.dst_user is not None:
            dst_data["user"] = req.dst_user
        if req.dst_password is not None:
            dst_data["password"] = req.dst_password
        if req.dst_database is not None:
            dst_data["database"] = req.dst_database
        if req.dst_tcp_hostport is not None:
            dst_data["tcp_hostport"] = req.dst_tcp_hostport

        try:
            new_src = InstanceConfig(**src_data)
            new_dst = InstanceConfig(**dst_data)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        actual_name = profile_name or cfg.default_profile or "default"
        base = profile or CopyProfile(src=new_src, dst=new_dst)
        updated = base.model_copy(update={"src": new_src, "dst": new_dst})
        cfg.profiles[actual_name] = updated
        if not cfg.default_profile:
            cfg.default_profile = actual_name
        save_config(cfg, config_path)

        return {"status": "saved"}

    return app
