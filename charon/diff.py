"""Diff helpers: compare src vs. dst at table and partition level."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class PartitionDiff:
    partition_id: str
    src_rows: int
    dst_rows: int | None  # None means partition is absent on dst
    status: Literal["missing", "mismatch", "ok"]


@dataclass
class TableDiff:
    name: str
    engine: str
    src_rows: int
    dst_rows: int | None  # None means table is absent on dst
    status: Literal["missing", "mismatch", "ok"]


def diff_partitions(
    src_parts: list[dict[str, int | str]],
    dst_parts: list[dict[str, int | str]],
) -> list[PartitionDiff]:
    """
    Compare partition lists from src and dst.

    Returns ALL partitions from src tagged with their status.
    Partitions that exist only on dst are ignored (we copy src → dst).
    """
    dst_map: dict[str, int] = {str(p["partition_id"]): int(p["rows"]) for p in dst_parts}

    result: list[PartitionDiff] = []
    for part in src_parts:
        pid = str(part["partition_id"])
        src_rows = int(part["rows"])
        dst_rows = dst_map.get(pid)

        if dst_rows is None:
            status: Literal["missing", "mismatch", "ok"] = "missing"
        elif dst_rows != src_rows:
            status = "mismatch"
        else:
            status = "ok"

        result.append(
            PartitionDiff(
                partition_id=pid,
                src_rows=src_rows,
                dst_rows=dst_rows,
                status=status,
            )
        )

    return result


def changed_partition_ids(diffs: list[PartitionDiff]) -> list[str]:
    """Return partition IDs that are missing or mismatched."""
    return [d.partition_id for d in diffs if d.status in ("missing", "mismatch")]


def diff_tables(
    src_tables: list[dict[str, str | int]],
    dst_tables: list[dict[str, str | int]],
) -> list[TableDiff]:
    """
    Compare table lists at the row-count level.

    *src_tables* and *dst_tables* are lists of dicts with keys:
    ``name``, ``engine``, ``total_rows``.
    """
    dst_map: dict[str, int] = {str(t["name"]): int(t.get("total_rows") or 0) for t in dst_tables}

    result: list[TableDiff] = []
    for tbl in src_tables:
        name = str(tbl["name"])
        engine = str(tbl.get("engine", ""))
        src_rows = int(tbl.get("total_rows") or 0)
        dst_rows: int | None = dst_map.get(name)

        if dst_rows is None:
            status: Literal["missing", "mismatch", "ok"] = "missing"
        elif dst_rows != src_rows:
            status = "mismatch"
        else:
            status = "ok"

        result.append(
            TableDiff(
                name=name,
                engine=engine,
                src_rows=src_rows,
                dst_rows=dst_rows,
                status=status,
            )
        )

    return result
