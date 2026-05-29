"""Main typer application — registers all sub-commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console

from charon import __version__
from charon.config import AppConfig, CopyProfile, config_path_from_option, load_config

from .config_cmd import config_app

app = typer.Typer(
    name="charon",
    help="ClickHouse database copier — copy tables between instances.",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")

console = Console()


# ---------------------------------------------------------------------------
# State object passed via typer Context
# ---------------------------------------------------------------------------


@dataclass
class State:
    config_path: Path
    profile_name: str | None
    cfg: AppConfig
    profile: CopyProfile | None = None


def _get_state(ctx: typer.Context) -> State:
    state: State = ctx.ensure_object(State)
    return state


# ---------------------------------------------------------------------------
# Global callback (sets up state before any sub-command)
# ---------------------------------------------------------------------------


@app.callback()
def main(
    ctx: typer.Context,
    config: str | None = typer.Option(
        None, "--config", "-c", envvar="CHCOPY_CONFIG", help="Config file path"
    ),
    profile: str | None = typer.Option(
        None, "--profile", "-p", envvar="CHCOPY_PROFILE", help="Profile name"
    ),
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit", is_eager=True
    ),
) -> None:
    if version:
        console.print(f"charon {__version__}")
        raise typer.Exit()

    config_path = config_path_from_option(config)
    cfg = load_config(config_path)

    # Try to resolve the profile (may be None if config is empty)
    copy_profile: CopyProfile | None = None
    if cfg.profiles:
        try:
            copy_profile = cfg.get_profile(profile)
        except KeyError:
            pass

    ctx.obj = State(
        config_path=config_path,
        profile_name=profile,
        cfg=cfg,
        profile=copy_profile,
    )
    ctx.ensure_object(State)


def _require_profile(ctx: typer.Context) -> CopyProfile:
    state = _get_state(ctx)
    if state.profile is None:
        console.print("[red]No profile configured. Run `charon config init` to create one.[/red]")
        raise typer.Exit(1)
    return state.profile


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@app.command()
def status(ctx: typer.Context) -> None:
    """Ping src and dst; show table count, rows, and bytes."""
    from .status_cmd import run_status

    profile = _require_profile(ctx)
    run_status(profile)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@app.command("list")
def list_tables(
    ctx: typer.Context,
    dst: bool = typer.Option(False, "--dst", help="List destination tables instead of source"),
    filter_re: str | None = typer.Option(None, "--filter", "-f", help="Regex filter on table name"),
) -> None:
    """List tables on src (or dst with --dst)."""
    from .list_cmd import run_list

    profile = _require_profile(ctx)
    run_list(profile, use_dst=dst, filter_re=filter_re)


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


@app.command()
def diff(
    ctx: typer.Context,
    table: str | None = typer.Option(
        None, "--table", "-t", help="Focus on single table (partition-level)"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show row-count diff between src and dst."""
    from .diff_cmd import run_diff

    profile = _require_profile(ctx)
    run_diff(profile, table_name=table, output_json=output_json)


# ---------------------------------------------------------------------------
# copy
# ---------------------------------------------------------------------------


@app.command()
def copy(
    ctx: typer.Context,
    table: str | None = typer.Option(None, "--table", "-t", help="Copy a single table"),
    tables: str | None = typer.Option(
        None, "--tables", help="Comma-separated list of tables to copy"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be copied without executing"
    ),
    no_partitions: bool = typer.Option(
        False, "--no-partitions", help="Copy whole tables without partition awareness"
    ),
) -> None:
    """Copy tables from src to dst."""
    from .copy_cmd import run_copy

    profile = _require_profile(ctx)
    table_list = [t.strip() for t in tables.split(",")] if tables else None
    run_copy(
        profile=profile,
        table_name=table,
        tables=table_list,
        dry_run=dry_run,
        no_partitions=no_partitions,
    )


# ---------------------------------------------------------------------------
# web
# ---------------------------------------------------------------------------


@app.command()
def web(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(8765, "--port", help="Port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (dev mode)"),
) -> None:
    """Start the web dashboard."""
    import uvicorn

    from charon.web.app import create_app

    state = _get_state(ctx)

    fastapi_app = create_app(config_path=state.config_path, profile_name=state.profile_name)

    console.print(f"[bold green]CHaron[/bold green] → [link]http://{host}:{port}[/link]")

    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        reload=reload,
    )
