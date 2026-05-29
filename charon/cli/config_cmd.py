"""CLI sub-app: manage connection profiles."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from charon.config import (
    CopyProfile,
    InstanceConfig,
    config_path_from_option,
    load_config,
    save_config,
)

config_app = typer.Typer(name="config", help="Manage connection profiles.")
console = Console()


@config_app.command("init")
def init(
    profile: str = typer.Option(
        "default", "--profile", "-p", help="Profile name to create or update"
    ),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """Interactively create or update a named profile."""
    config_path = config_path_from_option(config)
    cfg = load_config(config_path)

    console.print(f"[bold]Creating/updating profile:[/bold] [cyan]{profile}[/cyan]")
    console.print("(Press Enter to accept the default shown in brackets)\n")

    existing = cfg.profiles.get(profile)

    # Source
    console.print("[bold yellow]Source ClickHouse[/bold yellow]")
    src_host = typer.prompt(
        "  Host", default=existing.src.host if existing else "http://localhost:8123"
    )
    src_user = typer.prompt("  User", default=existing.src.user if existing else "default")
    src_password = typer.prompt(
        "  Password",
        default=existing.src.password if existing else "",
        hide_input=True,
    )
    src_database = typer.prompt(
        "  Database", default=existing.src.database if existing else "default"
    )

    # Destination
    console.print("\n[bold yellow]Destination ClickHouse[/bold yellow]")
    dst_host = typer.prompt(
        "  Host", default=existing.dst.host if existing else "http://localhost:8123"
    )
    dst_user = typer.prompt("  User", default=existing.dst.user if existing else "default")
    dst_password = typer.prompt(
        "  Password",
        default=existing.dst.password if existing else "",
        hide_input=True,
    )
    dst_database = typer.prompt(
        "  Database", default=existing.dst.database if existing else "default"
    )
    dst_tcp = typer.prompt(
        "  TCP hostport (host:port, used for remote() INSERT)",
        default=existing.dst.tcp_hostport if existing and existing.dst.tcp_hostport else "",
    )

    copy_profile = CopyProfile(
        src=InstanceConfig(
            host=src_host, user=src_user, password=src_password, database=src_database
        ),
        dst=InstanceConfig(
            host=dst_host,
            user=dst_user,
            password=dst_password,
            database=dst_database,
            tcp_hostport=dst_tcp or None,
        ),
    )

    cfg.profiles[profile] = copy_profile
    if not cfg.default_profile or profile == "default":
        cfg.default_profile = profile

    save_config(cfg, config_path)
    console.print(f"\n[green]Profile '{profile}' saved to {config_path}[/green]")


@config_app.command("show")
def show(
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile name"),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """Print the current profile (password masked)."""
    config_path = config_path_from_option(config)
    cfg = load_config(config_path)

    try:
        prof = cfg.get_profile(profile)
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    name = profile or cfg.default_profile

    table = Table(title=f"Profile: {name}", show_header=True)
    table.add_column("Field", style="bold")
    table.add_column("Source")
    table.add_column("Destination")

    table.add_row("Host", prof.src.host, prof.dst.host)
    table.add_row("User", prof.src.user, prof.dst.user)
    table.add_row("Password", "***", "***")
    table.add_row("Database", prof.src.database, prof.dst.database)
    table.add_row("Timeout", str(prof.src.timeout), str(prof.dst.timeout))
    table.add_row("TCP hostport", "-", prof.dst.tcp_hostport or "-")

    console.print(table)

    console.print(f"\n[dim]copy_by_partitions:[/dim] {prof.copy_by_partitions}")
    console.print(f"[dim]convert_replicated_to_merge:[/dim] {prof.convert_replicated_to_merge}")
    console.print(f"[dim]retry_count:[/dim] {prof.retry_count}")
    console.print(f"[dim]retry_sleep:[/dim] {prof.retry_sleep}s  max {prof.retry_max_sleep}s")


@config_app.command("list")
def list_profiles(
    config: str | None = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """List all available profiles."""
    config_path = config_path_from_option(config)
    cfg = load_config(config_path)

    if not cfg.profiles:
        console.print(
            "[yellow]No profiles configured. Run `charon config init` to create one.[/yellow]"
        )
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Profile")
    table.add_column("Src host")
    table.add_column("Src DB")
    table.add_column("Dst host")
    table.add_column("Dst DB")
    table.add_column("Default")

    for name, prof in cfg.profiles.items():
        is_default = "[green]✓[/green]" if name == cfg.default_profile else ""
        table.add_row(
            name, prof.src.host, prof.src.database, prof.dst.host, prof.dst.database, is_default
        )

    console.print(table)


@config_app.command("delete")
def delete(
    profile_name: str = typer.Argument(..., help="Profile name to delete"),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file path"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Remove a profile."""
    config_path = config_path_from_option(config)
    cfg = load_config(config_path)

    if profile_name not in cfg.profiles:
        console.print(f"[red]Profile '{profile_name}' not found.[/red]")
        raise typer.Exit(1)

    if not yes:
        confirmed = typer.confirm(f"Delete profile '{profile_name}'?")
        if not confirmed:
            raise typer.Abort()

    del cfg.profiles[profile_name]
    if cfg.default_profile == profile_name:
        cfg.default_profile = next(iter(cfg.profiles), "default")

    save_config(cfg, config_path)
    console.print(f"[green]Profile '{profile_name}' deleted.[/green]")
