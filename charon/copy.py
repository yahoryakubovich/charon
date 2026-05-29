"""Core copy logic: table DDL + data transfer with partition awareness."""

from __future__ import annotations

from typing import Protocol

from .client import CHClient, ClickHouseError
from .config import CopyProfile
from .ddl import (
    create_database,
    create_materialized_view,
    create_table,
    create_view,
    normalize_create_ddl,
)
from .diff import changed_partition_ids, diff_partitions

# ---------------------------------------------------------------------------
# Callback protocol
# ---------------------------------------------------------------------------


class CopyCallback(Protocol):
    """Observer interface for copy progress events."""

    def on_table_start(self, table: str, engine: str, partitions: int) -> None: ...
    def on_partition_start(self, table: str, partition_id: str, rows: int) -> None: ...
    def on_partition_done(self, table: str, partition_id: str) -> None: ...
    def on_table_done(self, table: str) -> None: ...
    def on_table_skip(self, table: str, reason: str) -> None: ...
    def on_error(self, table: str, error: Exception) -> None: ...


class NullCallback:
    """No-op implementation of CopyCallback — the default."""

    def on_table_start(self, table: str, engine: str, partitions: int) -> None:
        pass

    def on_partition_start(self, table: str, partition_id: str, rows: int) -> None:
        pass

    def on_partition_done(self, table: str, partition_id: str) -> None:
        pass

    def on_table_done(self, table: str) -> None:
        pass

    def on_table_skip(self, table: str, reason: str) -> None:
        pass

    def on_error(self, table: str, error: Exception) -> None:
        pass


# ---------------------------------------------------------------------------
# Engine classification
# ---------------------------------------------------------------------------

_KAFKA_ENGINES = frozenset({"Kafka", "RabbitMQ", "NATS"})
_DICT_ENGINES = frozenset({"Dictionary"})
_VIEW_ENGINES = frozenset({"View", "MaterializedView"})
_SKIP_ALWAYS = frozenset({"Buffer", "Null", "Memory"})


def should_copy_table(engine: str, profile: CopyProfile) -> tuple[bool, str]:
    """
    Decide whether to copy a table with the given *engine*.

    Returns ``(should_copy, reason)`` — reason is non-empty when skipping.
    """
    if engine in _SKIP_ALWAYS:
        return False, f"engine {engine} is always skipped"
    if engine in _KAFKA_ENGINES and not profile.copy_kafka_tables:
        return False, "Kafka/queue table (set copy_kafka_tables=true to include)"
    if engine in _DICT_ENGINES and not profile.copy_dictionaries:
        return False, "Dictionary table (set copy_dictionaries=true to include)"
    if engine in _VIEW_ENGINES and not profile.copy_views:
        return False, "View table (set copy_views=true to include)"
    return True, ""


# ---------------------------------------------------------------------------
# Single-table copy
# ---------------------------------------------------------------------------


def copy_table(
    src: CHClient,
    dst: CHClient,
    profile: CopyProfile,
    src_db: str,
    dst_db: str,
    table_name: str,
    engine: str,
    callback: CopyCallback | None = None,
) -> None:
    """
    Copy one table from *src_db.table_name* to *dst_db.table_name*.

    Uses partition-aware INSERT INTO FUNCTION remote() when:
    - ``profile.copy_by_partitions`` is True
    - the destination has ``tcp_hostport`` configured
    - the table has MergeTree-family engine
    """
    cb: CopyCallback = callback or NullCallback()

    # Get partitions that need copying
    src_parts = src.get_partitions(src_db, table_name)
    dst_parts = dst.get_partitions(dst_db, table_name)
    diffs = diff_partitions(src_parts, dst_parts)
    to_copy = changed_partition_ids(diffs)

    cb.on_table_start(table_name, engine, len(to_copy))

    if not to_copy:
        cb.on_table_done(table_name)
        return

    use_partitions = (
        profile.copy_by_partitions
        and profile.dst.tcp_hostport is not None
        and _is_merge_tree(engine)
    )

    insert_settings = profile.insert_settings.to_dict()

    if use_partitions:
        _copy_by_partitions(
            src=src,
            dst_hostport=profile.dst.tcp_hostport,  # type: ignore[arg-type]
            dst_user=profile.dst.user,
            dst_password=profile.dst.password,
            src_db=src_db,
            dst_db=dst_db,
            table=table_name,
            partition_ids=to_copy,
            settings=insert_settings,
            callback=cb,
        )
    else:
        _copy_full_table(
            src=src,
            dst=dst,
            src_db=src_db,
            dst_db=dst_db,
            table=table_name,
            settings=insert_settings,
            callback=cb,
            partition_ids=to_copy if profile.copy_by_partitions else None,
        )

    cb.on_table_done(table_name)


def _is_merge_tree(engine: str) -> bool:
    return "MergeTree" in engine


def _copy_by_partitions(
    src: CHClient,
    dst_hostport: str,
    dst_user: str,
    dst_password: str,
    src_db: str,
    dst_db: str,
    table: str,
    partition_ids: list[str],
    settings: dict[str, object],
    callback: CopyCallback,
) -> None:
    """Push each partition from src to dst via INSERT INTO FUNCTION remote()."""
    settings_str = _format_settings(settings)
    password_escaped = dst_password.replace("'", "\\'")

    for pid in partition_ids:
        src_rows_list = src.get_partitions(src_db, table)
        rows_for_pid = next((int(p["rows"]) for p in src_rows_list if p["partition_id"] == pid), 0)
        callback.on_partition_start(table, pid, rows_for_pid)

        sql = (
            f"INSERT INTO FUNCTION remote('{dst_hostport}', '{dst_db}.{table}', "
            f"'{dst_user}', '{password_escaped}')"
            f" {settings_str}"
            f" SELECT * FROM `{src_db}`.`{table}` WHERE _partition_id = '{pid}'"
        )
        src.query(sql, skip_database=True)
        callback.on_partition_done(table, pid)


def _copy_full_table(
    src: CHClient,
    dst: CHClient,
    src_db: str,
    dst_db: str,
    table: str,
    settings: dict[str, object],
    callback: CopyCallback,
    partition_ids: list[str] | None,
) -> None:
    """Fallback: pull data with SELECT and push with INSERT via the dst client."""
    settings_str = _format_settings(settings)

    if partition_ids:
        pid_list = ", ".join(f"'{p}'" for p in partition_ids)
        where = f"WHERE _partition_id IN ({pid_list})"
    else:
        where = ""

    # We do a pseudo-progress: one "partition" = the whole table
    callback.on_partition_start(table, "__all__", 0)

    data = src.query(
        f"SELECT * FROM `{src_db}`.`{table}` {where} FORMAT Native",
        skip_database=True,
    )
    # data is raw Native-format bytes encoded as string — won't work for large tables
    # but serves as a fallback path. A real production impl would stream.
    dst.query(
        f"INSERT INTO `{dst_db}`.`{table}` {settings_str} FORMAT Native\n{data}",
        skip_database=True,
    )
    callback.on_partition_done(table, "__all__")


def _format_settings(settings: dict[str, object]) -> str:
    if not settings:
        return ""
    parts = [f"{k}={v}" for k, v in settings.items()]
    return "SETTINGS " + ", ".join(parts)


# ---------------------------------------------------------------------------
# Database-level orchestration
# ---------------------------------------------------------------------------


def copy_database(
    src: CHClient,
    dst: CHClient,
    profile: CopyProfile,
    callback: CopyCallback | None = None,
    table_filter: list[str] | None = None,
) -> None:
    """
    Copy all eligible tables from src.database to dst.database.

    1. Creates the destination database.
    2. Iterates src tables in engine-priority order (data tables before views).
    3. Creates DDL on dst.
    4. Copies data partition-by-partition.
    """
    cb: CopyCallback = callback or NullCallback()
    src_db = profile.src.database
    dst_db = profile.dst.database

    create_database(dst, dst_db)

    tables = src.get_tables(src_db)

    for tbl in tables:
        name = str(tbl["name"])
        engine = str(tbl.get("engine", ""))
        create_sql = str(tbl.get("create_table_query", ""))

        if name in profile.skip_tables:
            cb.on_table_skip(name, "in skip_tables list")
            continue

        if table_filter and name not in table_filter:
            continue

        ok, reason = should_copy_table(engine, profile)
        if not ok:
            cb.on_table_skip(name, reason)
            continue

        # Create schema on dst
        ddl = normalize_create_ddl(
            create_sql, convert_replicated=profile.convert_replicated_to_merge
        )
        try:
            if engine == "MaterializedView":
                create_materialized_view(dst, ddl, dst_db)
            elif engine == "View":
                create_view(dst, ddl, dst_db)
            else:
                create_table(dst, ddl, dst_db)
        except ClickHouseError as exc:
            cb.on_error(name, exc)
            continue

        # Skip data copy for views / dictionaries
        if engine in _VIEW_ENGINES or engine in _DICT_ENGINES:
            cb.on_table_done(name)
            continue

        try:
            copy_table(
                src=src,
                dst=dst,
                profile=profile,
                src_db=src_db,
                dst_db=dst_db,
                table_name=name,
                engine=engine,
                callback=cb,
            )
        except ClickHouseError as exc:
            cb.on_error(name, exc)
