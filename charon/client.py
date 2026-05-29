"""ClickHouse HTTP client with retry and exponential backoff."""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from typing import Any

import requests

from .config import InstanceConfig


class ClickHouseError(RuntimeError):
    """Raised when ClickHouse returns an error response or all retries are exhausted."""


@dataclass
class RetryConfig:
    retry_count: int = 3
    retry_sleep: float = 2.0
    retry_max_sleep: float = 30.0


class CHClient:
    """Thin HTTP wrapper around the ClickHouse HTTP interface."""

    def __init__(self, cfg: InstanceConfig, retry: RetryConfig | None = None) -> None:
        self.host = cfg.host
        self.auth = (cfg.user, cfg.password)
        self.default_db = cfg.database
        self.timeout = cfg.timeout
        self._session = requests.Session()
        self._retry = retry or RetryConfig()

    # ------------------------------------------------------------------
    # Low-level
    # ------------------------------------------------------------------

    def query(
        self,
        sql: str,
        *,
        database: str | None = None,
        settings: dict[str, Any] | None = None,
        skip_database: bool = False,
    ) -> str:
        """Execute *sql* and return the raw response text."""
        params: dict[str, Any] = dict(settings or {})
        if not skip_database:
            params["database"] = database or self.default_db

        last_exc: Exception = RuntimeError("No attempts made")
        for attempt in range(self._retry.retry_count):
            try:
                r = self._session.post(
                    f"{self.host}/",
                    params=params,
                    data=sql.encode("utf-8"),
                    auth=self.auth,
                    timeout=self.timeout,
                )
                if r.status_code != 200:
                    raise ClickHouseError(f"HTTP {r.status_code}: {r.text[:500]}")
                return r.text
            except ClickHouseError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < self._retry.retry_count - 1:
                    sleep_time = min(
                        self._retry.retry_sleep * (2**attempt),
                        self._retry.retry_max_sleep,
                    )
                    jitter = sleep_time * 0.1 * (2 * random.random() - 1)
                    time.sleep(max(0.0, sleep_time + jitter))
        raise ClickHouseError(f"All {self._retry.retry_count} attempts failed") from last_exc

    def query_rows(
        self,
        sql: str,
        *,
        database: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute *sql* and return parsed JSONEachRow results."""
        fmt_sql = sql.rstrip().rstrip(";") + " FORMAT JSONEachRow"
        txt = self.query(fmt_sql, database=database, settings=settings)
        return [json.loads(line) for line in txt.splitlines() if line.strip()]

    def ping(self) -> bool:
        """Return True if the server is reachable."""
        try:
            self.query("SELECT 1", skip_database=True)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_tables(self, database: str) -> list[dict[str, Any]]:
        """Return metadata for all tables in *database*."""
        sql = f"""
            SELECT
                name,
                engine,
                is_temporary,
                create_table_query,
                total_rows,
                total_bytes,
                if(engine IN ('View', 'MaterializedView', 'Dictionary'), 9, 1) AS priority
            FROM system.tables
            WHERE database = '{database}'
            ORDER BY priority, name
        """
        return self.query_rows(sql)

    def get_partitions(self, database: str, table: str) -> list[dict[str, Any]]:
        """Return partition-level row counts for *database.table*."""
        sql = f"""
            SELECT
                partition_id,
                sum(rows) AS rows
            FROM system.parts
            WHERE active = 1
              AND database = '{database}'
              AND table = '{table}'
            GROUP BY partition_id
            ORDER BY partition_id
        """
        return self.query_rows(sql)

    def get_multi_part(self, database: str, table: str) -> list[dict[str, Any]]:
        """Return partitions that have more than one active part (need OPTIMIZE)."""
        sql = f"""
            SELECT
                partition_id,
                count() AS count_
            FROM system.parts
            WHERE active = 1
              AND database = '{database}'
              AND table = '{table}'
            GROUP BY partition_id
            HAVING count_ > 1
            ORDER BY partition_id
        """
        return self.query_rows(sql)

    def db_stats(self, database: str) -> dict[str, Any]:
        """Return aggregate stats (tables, total_rows, total_bytes) for *database*."""
        sql = f"""
            SELECT
                count()          AS tables,
                sum(total_rows)  AS total_rows,
                sum(total_bytes) AS total_bytes
            FROM system.tables
            WHERE database = '{database}'
        """
        rows = self.query_rows(sql)
        return rows[0] if rows else {"tables": 0, "total_rows": 0, "total_bytes": 0}
