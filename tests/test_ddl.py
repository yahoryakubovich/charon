"""Tests for charon.ddl."""

from __future__ import annotations

from unittest.mock import MagicMock

from charon.client import CHClient
from charon.ddl import (
    create_table,
    normalize_create_ddl,
)


class TestNormalizeCreateDDL:
    def test_removes_on_cluster_unquoted(self) -> None:
        sql = "CREATE TABLE mydb.t ON CLUSTER my_cluster (id UInt32) ENGINE = MergeTree()"
        result = normalize_create_ddl(sql)
        assert "ON CLUSTER" not in result
        assert "my_cluster" not in result

    def test_removes_on_cluster_quoted(self) -> None:
        sql = "CREATE TABLE mydb.t ON CLUSTER 'prod-cluster' (id UInt32) ENGINE = MergeTree()"
        result = normalize_create_ddl(sql)
        assert "ON CLUSTER" not in result
        assert "prod-cluster" not in result

    def test_preserves_structure_after_removal(self) -> None:
        sql = "CREATE TABLE mydb.t ON CLUSTER c1 (id UInt32) ENGINE = MergeTree() ORDER BY id"
        result = normalize_create_ddl(sql)
        assert "MergeTree" in result
        assert "ORDER BY id" in result

    def test_replicated_to_merge_conversion(self) -> None:
        sql = (
            "CREATE TABLE mydb.t (id UInt32) ENGINE = "
            "ReplicatedMergeTree('/clickhouse/tables/t', '{replica}')"
        )
        result = normalize_create_ddl(sql, convert_replicated=True)
        assert "MergeTree" in result
        assert "Replicated" not in result
        assert "/clickhouse/tables" not in result

    def test_no_conversion_when_flag_false(self) -> None:
        sql = "CREATE TABLE mydb.t (id UInt32) ENGINE = ReplicatedMergeTree('/zk/t', 'r1')"
        result = normalize_create_ddl(sql, convert_replicated=False)
        assert "ReplicatedMergeTree" in result

    def test_replicated_replacing_conversion(self) -> None:
        sql = "CREATE TABLE mydb.t (id UInt32) ENGINE = ReplicatedReplacingMergeTree('/zk/t', 'r1')"
        result = normalize_create_ddl(sql, convert_replicated=True)
        assert "ReplacingMergeTree" in result
        assert "Replicated" not in result


class TestCreateTable:
    def test_rewrites_database_name(self) -> None:
        client = MagicMock(spec=CHClient)
        sql = "CREATE TABLE `source_db`.`my_table` (id UInt32) ENGINE = MergeTree() ORDER BY id"
        create_table(client, sql, "target_db")

        called_sql: str = client.query.call_args[0][0]
        assert "`target_db`" in called_sql
        assert "source_db" not in called_sql

    def test_adds_if_not_exists(self) -> None:
        client = MagicMock(spec=CHClient)
        sql = "CREATE TABLE `src`.`t` (id UInt32) ENGINE = MergeTree() ORDER BY id"
        create_table(client, sql, "dst")

        called_sql: str = client.query.call_args[0][0]
        assert "IF NOT EXISTS" in called_sql

    def test_skip_database_true(self) -> None:
        """create_table should use skip_database=True so it doesn't append a database param."""
        client = MagicMock(spec=CHClient)
        sql = "CREATE TABLE `src`.`t` (id UInt32) ENGINE = MergeTree() ORDER BY id"
        create_table(client, sql, "dst")

        kwargs = client.query.call_args.kwargs
        assert kwargs.get("skip_database") is True
