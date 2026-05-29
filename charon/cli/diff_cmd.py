"""CLI command: diff — compare src and dst at table or partition level."""

from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table

from charon.client import CHClient, RetryConfig
from charon.config import CopyProfile
from charon.diff import diff_partitions, diff_tables

console = Console()


def _status_cell(status: str) -> str:
    icons = {
        "ok": "[green]✓ ok[/green]",
        "mismatch": "[yellow]~ mismatch[/yellow]",
        "missing": "[red]✗ missing[/red]",
    }
    return icons.get(status, status)


def run_diff(
    profile: CopyProfile,
    table_name: str | None = None,
    output_json: bool = False,
) -> None:
    """Show diff between src and dst."""
    retry = RetryConfig(
        retry_count=profile.retry_count,
        retry_sleep=profile.retry_sleep,
        retry_max_sleep=profile.retry_max_sleep,
    )
    src = CHClient(profile.src, retry=retry)
    dst = CHClient(profile.dst, retry=retry)

    if table_name:
        _partition_diff(src, dst, profile, table_name, output_json)
    else:
        _table_diff(src, dst, profile, output_json)


def _table_diff(
    src: CHClient,
    dst: CHClient,
    profile: CopyProfile,
    output_json: bool,
) -> None:
    src_tables = src.get_tables(profile.src.database)
    dst_tables = dst.get_tables(profile.dst.database)

    diffs = diff_tables(src_tables, dst_tables)

    if output_json:
        data = [
            {
                "name": d.name,
                "engine": d.engine,
                "src_rows": d.src_rows,
                "dst_rows": d.dst_rows,
                "status": d.status,
            }
            for d in diffs
        ]
        console.print(json.dumps(data, indent=2))
        return

    table = Table(title="Table-level diff", show_header=True, header_style="bold")
    table.add_column("Table", style="cyan")
    table.add_column("Engine", style="dim")
    table.add_column("Src rows", justify="right")
    table.add_column("Dst rows", justify="right")
    table.add_column("Diff", justify="right")
    table.add_column("Status")

    for d in diffs:
        diff_val = ""
        if d.dst_rows is not None:
            delta = d.src_rows - d.dst_rows
            if delta > 0:
                diff_val = f"[yellow]+{delta}[/yellow]"
            elif delta < 0:
                diff_val = f"[red]{delta}[/red]"
            else:
                diff_val = "[green]0[/green]"

        table.add_row(
            d.name,
            d.engine,
            str(d.src_rows),
            str(d.dst_rows) if d.dst_rows is not None else "[red]—[/red]",
            diff_val,
            _status_cell(d.status),
        )

    console.print(table)

    ok = sum(1 for d in diffs if d.status == "ok")
    mismatch = sum(1 for d in diffs if d.status == "mismatch")
    missing = sum(1 for d in diffs if d.status == "missing")
    console.print(
        f"[dim]Total: {len(diffs)}  "
        f"[green]ok: {ok}[/green]  "
        f"[yellow]mismatch: {mismatch}[/yellow]  "
        f"[red]missing: {missing}[/red][/dim]"
    )


def _partition_diff(
    src: CHClient,
    dst: CHClient,
    profile: CopyProfile,
    table_name: str,
    output_json: bool,
) -> None:
    src_parts = src.get_partitions(profile.src.database, table_name)
    dst_parts = dst.get_partitions(profile.dst.database, table_name)

    diffs = diff_partitions(src_parts, dst_parts)

    if output_json:
        data = [
            {
                "partition_id": d.partition_id,
                "src_rows": d.src_rows,
                "dst_rows": d.dst_rows,
                "status": d.status,
            }
            for d in diffs
        ]
        console.print(json.dumps(data, indent=2))
        return

    table = Table(
        title=f"Partition-level diff: {table_name}",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Partition", style="cyan")
    table.add_column("Src rows", justify="right")
    table.add_column("Dst rows", justify="right")
    table.add_column("Diff", justify="right")
    table.add_column("Status")

    for d in diffs:
        diff_val = ""
        if d.dst_rows is not None:
            delta = d.src_rows - d.dst_rows
            if delta > 0:
                diff_val = f"[yellow]+{delta}[/yellow]"
            elif delta < 0:
                diff_val = f"[red]{delta}[/red]"
            else:
                diff_val = "[green]0[/green]"

        table.add_row(
            d.partition_id,
            str(d.src_rows),
            str(d.dst_rows) if d.dst_rows is not None else "[red]—[/red]",
            diff_val,
            _status_cell(d.status),
        )

    console.print(table)
