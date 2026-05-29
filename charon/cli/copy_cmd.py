"""CLI command: copy — copy tables from src to dst with rich progress."""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn
from rich.table import Table

from charon.client import CHClient, RetryConfig
from charon.config import CopyProfile
from charon.copy import copy_database, should_copy_table

console = Console()


@dataclass
class CopySummary:
    tables_copied: int = 0
    tables_skipped: int = 0
    tables_errored: int = 0
    partitions_copied: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


class RichCopyCallback:
    """Implements CopyCallback using Rich progress bars."""

    def __init__(self, progress: Progress, summary: CopySummary, dry_run: bool = False) -> None:
        self._progress = progress
        self._summary = summary
        self._dry_run = dry_run
        self._overall_task: TaskID | None = None
        self._partition_task: TaskID | None = None

    def set_overall_task(self, task_id: TaskID, total: int) -> None:
        self._overall_task = task_id
        self._progress.update(task_id, total=total)

    def on_table_start(self, table: str, engine: str, partitions: int) -> None:
        prefix = "[DRY RUN] " if self._dry_run else ""
        if self._partition_task is not None:
            self._progress.remove_task(self._partition_task)
        self._partition_task = self._progress.add_task(
            f"{prefix}[cyan]{table}[/cyan] ({engine})",
            total=max(partitions, 1),
        )

    def on_partition_start(self, table: str, partition_id: str, rows: int) -> None:
        if self._partition_task is not None:
            self._progress.update(
                self._partition_task,
                description=f"  partition [yellow]{partition_id}[/yellow] ({rows:,} rows)",
            )

    def on_partition_done(self, table: str, partition_id: str) -> None:
        self._summary.partitions_copied += 1
        if self._partition_task is not None:
            self._progress.advance(self._partition_task)

    def on_table_done(self, table: str) -> None:
        self._summary.tables_copied += 1
        if self._overall_task is not None:
            self._progress.advance(self._overall_task)
        if self._partition_task is not None:
            self._progress.update(self._partition_task, visible=False)

    def on_table_skip(self, table: str, reason: str) -> None:
        self._summary.tables_skipped += 1
        console.print(f"  [dim]SKIP[/dim] {table}  [dim]{reason}[/dim]")
        if self._overall_task is not None:
            self._progress.advance(self._overall_task)

    def on_error(self, table: str, error: Exception) -> None:
        self._summary.tables_errored += 1
        self._summary.errors.append((table, str(error)))
        console.print(f"  [red]ERROR[/red] {table}: {error}")
        if self._overall_task is not None:
            self._progress.advance(self._overall_task)


def run_copy(
    profile: CopyProfile,
    table_name: str | None = None,
    tables: list[str] | None = None,
    dry_run: bool = False,
    no_partitions: bool = False,
) -> None:
    """Orchestrate the copy operation with live progress display."""
    retry = RetryConfig(
        retry_count=profile.retry_count,
        retry_sleep=profile.retry_sleep,
        retry_max_sleep=profile.retry_max_sleep,
    )
    src = CHClient(profile.src, retry=retry)
    dst = CHClient(profile.dst, retry=retry)

    # Resolve which tables to copy
    if table_name:
        table_filter: list[str] | None = [table_name]
    elif tables:
        table_filter = tables
    else:
        table_filter = None

    # Fetch full table list to determine total work
    src_tables = src.get_tables(profile.src.database)
    if table_filter:
        src_tables = [t for t in src_tables if str(t["name"]) in table_filter]

    eligible = [
        t
        for t in src_tables
        if str(t["name"]) not in profile.skip_tables
        and should_copy_table(str(t.get("engine", "")), profile)[0]
    ]

    if dry_run:
        console.print("[bold yellow]DRY RUN — no data will be copied[/bold yellow]\n")
        tbl = Table(show_header=True, header_style="bold")
        tbl.add_column("Table", style="cyan")
        tbl.add_column("Engine")
        tbl.add_column("Src rows", justify="right")
        for t in eligible:
            tbl.add_row(str(t["name"]), str(t.get("engine", "")), str(t.get("total_rows") or 0))
        console.print(tbl)
        console.print(f"\n[dim]{len(eligible)} table(s) would be copied.[/dim]")
        return

    summary = CopySummary()

    eff_profile = profile
    if no_partitions:
        eff_profile = profile.model_copy(update={"copy_by_partitions": False})

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        cb = RichCopyCallback(progress, summary, dry_run=dry_run)
        overall = progress.add_task("[bold]Overall progress[/bold]", total=len(eligible))
        cb.set_overall_task(overall, len(eligible))

        copy_database(
            src=src,
            dst=dst,
            profile=eff_profile,
            callback=cb,
            table_filter=table_filter,
        )

    # Summary table
    console.print("\n[bold]Copy summary[/bold]")
    result_table = Table(show_header=False)
    result_table.add_column("Label", style="dim")
    result_table.add_column("Value", style="bold")
    result_table.add_row("Tables copied", f"[green]{summary.tables_copied}[/green]")
    result_table.add_row("Tables skipped", str(summary.tables_skipped))
    errored_val = f"[red]{summary.tables_errored}[/red]" if summary.tables_errored else "0"
    result_table.add_row("Tables errored", errored_val)
    result_table.add_row("Partitions copied", str(summary.partitions_copied))
    console.print(result_table)

    if summary.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for tbl_name, err in summary.errors:
            console.print(f"  [red]{tbl_name}[/red]: {err}")
