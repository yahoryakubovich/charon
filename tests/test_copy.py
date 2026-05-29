"""Tests for charon.copy."""

from __future__ import annotations

from unittest.mock import MagicMock

from charon.client import CHClient
from charon.config import CopyProfile, InstanceConfig
from charon.copy import CopyCallback, NullCallback, copy_table, should_copy_table


def _make_profile(**kwargs: object) -> CopyProfile:
    defaults = dict(
        src=InstanceConfig(host="http://src:8123", user="u", password="p", database="srcdb"),
        dst=InstanceConfig(
            host="http://dst:8123",
            user="u2",
            password="p2",
            database="dstdb",
            tcp_hostport="dst:9000",
        ),
        retry_count=1,
        retry_sleep=0.0,
        retry_max_sleep=0.0,
    )
    defaults.update(kwargs)
    return CopyProfile(**defaults)  # type: ignore[arg-type]


class TestShouldCopyTable:
    def test_merge_tree_always_copied(self) -> None:
        ok, _ = should_copy_table("MergeTree", _make_profile())
        assert ok is True

    def test_kafka_skipped_by_default(self) -> None:
        ok, reason = should_copy_table("Kafka", _make_profile(copy_kafka_tables=False))
        assert ok is False
        assert "Kafka" in reason or "queue" in reason.lower()

    def test_kafka_copied_when_flag_set(self) -> None:
        ok, _ = should_copy_table("Kafka", _make_profile(copy_kafka_tables=True))
        assert ok is True

    def test_dictionary_skipped_by_default(self) -> None:
        ok, _ = should_copy_table("Dictionary", _make_profile(copy_dictionaries=False))
        assert ok is False

    def test_dictionary_copied_when_flag_set(self) -> None:
        ok, _ = should_copy_table("Dictionary", _make_profile(copy_dictionaries=True))
        assert ok is True

    def test_view_skipped_by_default(self) -> None:
        ok, _ = should_copy_table("View", _make_profile(copy_views=False))
        assert ok is False

    def test_view_copied_when_flag_set(self) -> None:
        ok, _ = should_copy_table("View", _make_profile(copy_views=True))
        assert ok is True

    def test_buffer_always_skipped(self) -> None:
        ok, _ = should_copy_table("Buffer", _make_profile())
        assert ok is False


class TestCopyTableCallbacks:
    def _make_src(self, partitions: list[dict[str, object]]) -> MagicMock:
        src = MagicMock(spec=CHClient)
        src.get_partitions.return_value = partitions
        src.query.return_value = ""
        return src

    def _make_dst(self, partitions: list[dict[str, object]] | None = None) -> MagicMock:
        dst = MagicMock(spec=CHClient)
        dst.get_partitions.return_value = partitions or []
        return dst

    def test_on_table_start_called(self) -> None:
        profile = _make_profile()
        src_parts = [{"partition_id": "2024-01", "rows": 100}]
        src = self._make_src(src_parts)
        dst = self._make_dst([])
        cb = MagicMock(spec=CopyCallback)

        copy_table(src, dst, profile, "srcdb", "dstdb", "my_table", "MergeTree", callback=cb)

        cb.on_table_start.assert_called_once_with("my_table", "MergeTree", 1)

    def test_on_table_done_called(self) -> None:
        profile = _make_profile()
        src = self._make_src([{"partition_id": "p1", "rows": 10}])
        dst = self._make_dst([])
        cb = MagicMock(spec=CopyCallback)

        copy_table(src, dst, profile, "srcdb", "dstdb", "my_table", "MergeTree", callback=cb)

        cb.on_table_done.assert_called_once_with("my_table")

    def test_on_partition_start_and_done_called(self) -> None:
        profile = _make_profile()
        src = self._make_src([{"partition_id": "2024-01", "rows": 50}])
        dst = self._make_dst([])
        cb = MagicMock(spec=CopyCallback)

        copy_table(src, dst, profile, "srcdb", "dstdb", "my_table", "MergeTree", callback=cb)

        cb.on_partition_start.assert_called_once()
        cb.on_partition_done.assert_called_once()

    def test_no_copy_when_all_partitions_ok(self) -> None:
        """When src and dst have identical partitions, no INSERT should be issued."""
        profile = _make_profile()
        parts = [{"partition_id": "2024-01", "rows": 100}]
        src = self._make_src(parts)
        dst = self._make_dst(parts)
        cb = MagicMock(spec=CopyCallback)

        copy_table(src, dst, profile, "srcdb", "dstdb", "t", "MergeTree", callback=cb)

        cb.on_table_start.assert_called_once_with("t", "MergeTree", 0)
        cb.on_table_done.assert_called_once_with("t")
        # No partition callbacks (nothing to copy)
        cb.on_partition_start.assert_not_called()

    def test_null_callback_does_not_raise(self) -> None:
        """NullCallback should silently handle all events."""
        profile = _make_profile()
        src = self._make_src([{"partition_id": "p1", "rows": 5}])
        dst = self._make_dst([])
        null_cb = NullCallback()

        # Should not raise
        copy_table(src, dst, profile, "srcdb", "dstdb", "t", "MergeTree", callback=null_cb)
