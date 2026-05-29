"""DDL helpers: normalize CREATE statements and replay them on the destination."""

from __future__ import annotations

import re

from .client import CHClient

# Engines that accept FINAL for optimize
_FINAL_ENGINES = frozenset(
    {
        "ReplacingMergeTree",
        "CollapsingMergeTree",
        "VersionedCollapsingMergeTree",
    }
)

# Engines that accept FINAL DEDUPLICATE
_DEDUP_ENGINES = frozenset({"ReplacingMergeTree"})

# Replicated engine prefix → plain equivalent
_REPLICATED_MAP: dict[str, str] = {
    "ReplicatedMergeTree": "MergeTree",
    "ReplicatedReplacingMergeTree": "ReplacingMergeTree",
    "ReplicatedAggregatingMergeTree": "AggregatingMergeTree",
    "ReplicatedCollapsingMergeTree": "CollapsingMergeTree",
    "ReplicatedVersionedCollapsingMergeTree": "VersionedCollapsingMergeTree",
    "ReplicatedSummingMergeTree": "SummingMergeTree",
    "ReplicatedGraphiteMergeTree": "GraphiteMergeTree",
}


def normalize_create_ddl(sql: str, *, convert_replicated: bool = False) -> str:
    """
    Clean up a CREATE TABLE statement fetched from system.tables:

    - Remove ``ON CLUSTER <cluster>`` clause.
    - Optionally convert Replicated* engines to their plain equivalents.
    """
    # Strip ON CLUSTER <identifier|'string'>
    sql = re.sub(
        r"\bON\s+CLUSTER\s+(?:'[^']*'|\S+)",
        "",
        sql,
        flags=re.IGNORECASE,
    )
    # Collapse extra whitespace introduced by the removal
    sql = re.sub(r"[ \t]{2,}", " ", sql)

    if convert_replicated:
        for replicated, plain in _REPLICATED_MAP.items():
            # Replace engine name; also strip the ZooKeeper path + replica arguments
            # that are mandatory for Replicated* but meaningless for plain engines.
            pattern = rf"\b{re.escape(replicated)}\s*\([^)]*\)"
            replacement = f"{plain}()"
            sql = re.sub(pattern, replacement, sql, flags=re.IGNORECASE)

    return sql.strip()


def create_database(client: CHClient, database: str) -> None:
    """Create the database if it does not exist."""
    client.query(
        f"CREATE DATABASE IF NOT EXISTS `{database}`",
        skip_database=True,
    )


def create_table(client: CHClient, create_sql: str, target_db: str) -> None:
    """
    Replay a CREATE TABLE statement on *client* targeting *target_db*.

    Rewrites the database qualifier and adds ``IF NOT EXISTS``.
    """
    sql = _rewrite_db_in_ddl(create_sql, target_db)
    sql = _ensure_if_not_exists(sql, "TABLE")
    client.query(sql, skip_database=True)


def create_view(client: CHClient, create_sql: str, target_db: str) -> None:
    """Replay a CREATE VIEW statement on *client* targeting *target_db*."""
    sql = _rewrite_db_in_ddl(create_sql, target_db)
    sql = _ensure_if_not_exists(sql, "VIEW")
    client.query(sql, skip_database=True)


def create_materialized_view(client: CHClient, create_sql: str, target_db: str) -> None:
    """Replay a CREATE MATERIALIZED VIEW statement on *client*."""
    sql = _rewrite_db_in_ddl(create_sql, target_db)
    sql = _ensure_if_not_exists(sql, "MATERIALIZED VIEW")
    client.query(sql, skip_database=True)


def optimize_partition(
    client: CHClient,
    database: str,
    table: str,
    partition_id: str,
    engine: str,
) -> None:
    """
    Run OPTIMIZE TABLE on a specific partition.

    - Plain MergeTree: ``OPTIMIZE TABLE ... PARTITION '...'``
    - Replacing/Collapsing: adds ``FINAL``
    - ReplacingMergeTree: adds ``FINAL DEDUPLICATE``
    """
    base = f"OPTIMIZE TABLE `{database}`.`{table}` PARTITION '{partition_id}'"
    if engine in _DEDUP_ENGINES:
        sql = f"{base} FINAL DEDUPLICATE"
    elif engine in _FINAL_ENGINES:
        sql = f"{base} FINAL"
    else:
        sql = base
    client.query(sql, skip_database=True)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _rewrite_db_in_ddl(sql: str, target_db: str) -> str:
    """Replace the database qualifier in a CREATE statement with *target_db*."""
    # Handles both: CREATE TABLE db.name and CREATE TABLE `db`.`name`
    sql = re.sub(
        r"(CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMPORARY\s+)?(?:TABLE|VIEW|MATERIALIZED\s+VIEW)"
        r"\s+(?:IF\s+NOT\s+EXISTS\s+)?)`?[^`\s.(]+`?\.",
        rf"\1`{target_db}`.",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )
    return sql


def _ensure_if_not_exists(sql: str, object_type: str) -> str:
    """Insert ``IF NOT EXISTS`` if not already present."""
    not_exists = r"(?!IF\s+NOT\s+EXISTS)"
    pattern = (
        rf"(CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMPORARY\s+)?{re.escape(object_type)}\s+){not_exists}"
    )
    replacement = r"\1IF NOT EXISTS "
    return re.sub(pattern, replacement, sql, count=1, flags=re.IGNORECASE)
