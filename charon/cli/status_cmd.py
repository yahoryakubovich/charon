"""CLI command: status — ping and show aggregate stats for src and dst."""

from __future__ import annotations

from typing import Any

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from charon.client import CHClient, RetryConfig
from charon.config import CopyProfile

console = Console()


def _human_bytes(value: int | None) -> str:
    if value is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}"
        value = int(value / 1024)
    return f"{value:.1f} PB"


def _human_rows(value: int | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _make_panel(label: str, profile_side: Any, reachable: bool, stats: dict[str, Any]) -> Panel:
    color = "green" if reachable else "red"
    ping_icon = "[green]●[/green]" if reachable else "[red]●[/red]"

    tables = stats.get("tables") or 0
    total_rows = int(stats.get("total_rows") or 0)
    total_bytes = int(stats.get("total_bytes") or 0)

    body = Text()
    body.append("Host:    ", style="dim")
    body.append(f"{profile_side.host}\n")
    body.append("DB:      ", style="dim")
    body.append(f"{profile_side.database}\n")
    body.append("Tables:  ", style="dim")
    body.append(f"{tables}\n")
    body.append("Rows:    ", style="dim")
    body.append(f"{_human_rows(total_rows)}\n")
    body.append("Size:    ", style="dim")
    body.append(f"{_human_bytes(total_bytes)}\n")
    body.append("Ping:    ", style="dim")
    body.append(f"{ping_icon} {'OK' if reachable else 'UNREACHABLE'}")

    return Panel(body, title=f"[bold {color}]{label}[/bold {color}]", expand=True)


def run_status(profile: CopyProfile) -> None:
    """Execute the status check and print the two side-by-side panels."""
    retry = RetryConfig(
        retry_count=profile.retry_count,
        retry_sleep=profile.retry_sleep,
        retry_max_sleep=profile.retry_max_sleep,
    )
    src_client = CHClient(profile.src, retry=retry)
    dst_client = CHClient(profile.dst, retry=retry)

    src_reachable = src_client.ping()
    dst_reachable = dst_client.ping()

    src_stats: dict[str, Any] = {}
    dst_stats: dict[str, Any] = {}

    if src_reachable:
        try:
            src_stats = src_client.db_stats(profile.src.database)
        except Exception:
            pass

    if dst_reachable:
        try:
            dst_stats = dst_client.db_stats(profile.dst.database)
        except Exception:
            pass

    src_panel = _make_panel("SRC", profile.src, src_reachable, src_stats)
    dst_panel = _make_panel("DST", profile.dst, dst_reachable, dst_stats)

    console.print(Columns([src_panel, dst_panel], equal=True))
