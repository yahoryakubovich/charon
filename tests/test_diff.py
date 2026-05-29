"""Tests for charon.diff."""

from __future__ import annotations

from charon.diff import PartitionDiff, changed_partition_ids, diff_partitions


def _part(partition_id: str, rows: int) -> dict[str, object]:
    return {"partition_id": partition_id, "rows": rows}


class TestDiffPartitions:
    def test_all_ok_when_equal(self) -> None:
        src = [_part("2024-01", 100), _part("2024-02", 200)]
        dst = [_part("2024-01", 100), _part("2024-02", 200)]
        diffs = diff_partitions(src, dst)
        assert all(d.status == "ok" for d in diffs)

    def test_missing_partition_on_dst(self) -> None:
        src = [_part("2024-01", 100), _part("2024-02", 200)]
        dst = [_part("2024-01", 100)]
        diffs = diff_partitions(src, dst)
        statuses = {d.partition_id: d.status for d in diffs}
        assert statuses["2024-01"] == "ok"
        assert statuses["2024-02"] == "missing"

    def test_mismatch_when_row_counts_differ(self) -> None:
        src = [_part("2024-01", 100)]
        dst = [_part("2024-01", 90)]
        diffs = diff_partitions(src, dst)
        assert diffs[0].status == "mismatch"
        assert diffs[0].src_rows == 100
        assert diffs[0].dst_rows == 90

    def test_missing_partition_has_none_dst_rows(self) -> None:
        src = [_part("p1", 50)]
        dst: list[dict[str, object]] = []
        diffs = diff_partitions(src, dst)
        assert diffs[0].dst_rows is None

    def test_only_src_partitions_returned(self) -> None:
        """Partitions only on dst are ignored."""
        src = [_part("2024-01", 100)]
        dst = [_part("2024-01", 100), _part("2024-03", 999)]
        diffs = diff_partitions(src, dst)
        assert len(diffs) == 1
        assert diffs[0].partition_id == "2024-01"

    def test_empty_src_returns_empty(self) -> None:
        assert diff_partitions([], [_part("p", 10)]) == []


class TestChangedPartitionIds:
    def test_returns_missing_and_mismatch(self) -> None:
        diffs = [
            PartitionDiff("p1", 100, 100, "ok"),
            PartitionDiff("p2", 100, None, "missing"),
            PartitionDiff("p3", 100, 90, "mismatch"),
        ]
        changed = changed_partition_ids(diffs)
        assert set(changed) == {"p2", "p3"}

    def test_empty_when_all_ok(self) -> None:
        diffs = [
            PartitionDiff("p1", 10, 10, "ok"),
            PartitionDiff("p2", 20, 20, "ok"),
        ]
        assert changed_partition_ids(diffs) == []
