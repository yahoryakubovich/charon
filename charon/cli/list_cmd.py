"""CLI command: list — show tables on src or dst."""

from __future__ import annotations

import re
from typing import Any

from rich.console import Console
from rich.table import Table

from charon.client import CHClient, RetryConfig
from charon.config import CopyProfile

console = Console()


def _human_bytes(value: int | None) -> str:
    if not value:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}"
        value = int(value / 1024)
    return f"{value:.1f} PB"


def run_list(
    profile: CopyProfile,
    use_dst: bool = False,
    filter_re: str | None = None,
) -> None:
    """List tables from src (or dst) with optional regex filter."""
    retry = RetryConfig(
        retry_count=profile.retry_count,
        retry_sleep=profile.retry_sleep,
        retry_max_sleep=profile.retry_max_sleep,
    )
    cfg = profile.dst if use_dst else profile.src
    client = CHClient(cfg, retry=retry)
    side_label = "DST" if use_dst else "SRC"

    rows: list[dict[str, Any]] = client.get_tables(cfg.database)

    if filter_re:
        pattern = re.compile(filter_re, re.IGNORECASE)
        rows = [r for r in rows if pattern.search(str(r["name"]))]

    table = Table(
        title=f"Tables on {side_label} — {cfg.host}/{cfg.database}",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Engine", style="dim")
    table.add_column("Rows", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("DDL (truncated)", overflow="fold", max_width=60)

    for row in rows:
        ddl = str(row.get("create_table_query", ""))
        if len(ddl) > 80:
            ddl = ddl[:77] + "..."
        table.add_row(
            str(row["name"]),
            str(row.get("engine", "")),
            str(row.get("total_rows") or 0),
            _human_bytes(int(row.get("total_bytes") or 0)),
            ddl,
        )

    console.print(table)
    console.print(f"[dim]{len(rows)} table(s)[/dim]")
