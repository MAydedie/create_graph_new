#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graph_store.partition_topology import build_partition_topology
from graph_store import sqlite_store
from graph_store.sqlite_store import persist_stage2_snapshot
from segment_2_partition.cli import run_stage2


def _write_stage1_fixture(path: Path) -> dict:
    payload = {
        "schema_version": "stage1.v1",
        "project": {
            "name": "fixture_project",
            "path": "D:/fixture/project",
            "total_files": 2,
            "total_lines_of_code": 42,
        },
        "symbols": [
            {"id": "sym:A.a1", "qualified_name": "A.a1", "kind": "method"},
            {"id": "sym:B.b1", "qualified_name": "B.b1", "kind": "method"},
            {"id": "sym:C.c1", "qualified_name": "C.c1", "kind": "method"},
            {"id": "sym:Other.a1", "qualified_name": "Other.a1", "kind": "method"},
        ],
        "call_graph": {
            "adjacency": {
                "A.a1": ["B.b1"],
                "B.b1": [],
                "C.c1": [],
            },
            "unresolved_targets": [],
        },
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_stage2_writes_json_and_graph_db(tmp_path: Path) -> None:
    stage1_path = tmp_path / "segment1.json"
    stage2_path = tmp_path / "segment2.json"
    graph_db_path = tmp_path / "graph.db"
    _write_stage1_fixture(stage1_path)

    run_stage2(
        input_path=str(stage1_path),
        output_path=str(stage2_path),
        graph_db_path=str(graph_db_path),
    )

    assert stage2_path.exists()
    assert graph_db_path.exists()

    payload = json.loads(stage2_path.read_text(encoding="utf-8"))
    assert payload["summary"]["partition_count"] >= 1
    assert payload["artifacts"]["graph_db_path"].endswith("graph.db")
    assert all(str(method_id).startswith("sym:") for partition in payload["partitions"] for method_id in (partition.get("methods") or []))

    with sqlite3.connect(str(graph_db_path)) as connection:
        partition_count = connection.execute("SELECT COUNT(*) FROM partitions").fetchone()[0]
        member_count = connection.execute("SELECT COUNT(*) FROM partition_assignments").fetchone()[0]
        topology_count = connection.execute("SELECT COUNT(*) FROM partition_topology").fetchone()[0]
        stored_symbol_ids = {
            row[0]
            for row in connection.execute("SELECT symbol_id FROM partition_assignments")
        }

    assert partition_count == payload["summary"]["partition_count"]
    assert member_count == payload["summary"]["total_partitioned_methods"]
    assert topology_count == payload["summary"]["partition_count"] * max(payload["summary"]["partition_count"] - 1, 0)
    assert stored_symbol_ids
    assert all(symbol_id.startswith("sym:") for symbol_id in stored_symbol_ids)


def test_partition_topology_includes_zero_edge_pairs(tmp_path: Path) -> None:
    graph_db_path = tmp_path / "graph.db"
    partitions = [
        {"partition_id": "partition_0", "name": "p0", "methods": ["sym:A.a1"], "qualified_methods": ["A.a1"], "member_symbols": [{"symbol_id": "sym:A.a1", "qualified_name": "A.a1"}], "internal_calls": 1, "external_calls": 1, "cohesion_score": 0.5},
        {"partition_id": "partition_1", "name": "p1", "methods": ["sym:B.b1"], "qualified_methods": ["B.b1"], "member_symbols": [{"symbol_id": "sym:B.b1", "qualified_name": "B.b1"}], "internal_calls": 1, "external_calls": 0, "cohesion_score": 1.0},
        {"partition_id": "partition_2", "name": "p2", "methods": ["sym:C.c1"], "qualified_methods": ["C.c1"], "member_symbols": [{"symbol_id": "sym:C.c1", "qualified_name": "C.c1"}], "internal_calls": 0, "external_calls": 0, "cohesion_score": 1.0},
    ]
    partition_call_graphs = {
        "partition_0": {"external_edges": [{"source": "A.a1", "target": "B.b1", "type": "calls"}]},
        "partition_1": {"external_edges": []},
        "partition_2": {"external_edges": []},
    }

    topology = build_partition_topology(partitions, partition_call_graphs)
    assert topology
    assert any(int(item["edge_count"]) == 0 for item in topology)
    non_zero_edge = next(item for item in topology if int(item["edge_count"]) > 0)
    assert non_zero_edge["call_examples"][0]["source_symbol_id"] == "sym:A.a1"
    assert non_zero_edge["call_examples"][0]["target_symbol_id"] == "sym:B.b1"

    persist_stage2_snapshot(str(graph_db_path), partitions=partitions, partition_topology=topology)

    with sqlite3.connect(str(graph_db_path)) as connection:
        zero_edge_rows = connection.execute(
            "SELECT COUNT(*) FROM partition_topology WHERE edge_count = 0"
        ).fetchone()[0]
        symbol_id_rows = connection.execute(
            "SELECT COUNT(*) FROM partition_assignments WHERE symbol_id LIKE 'sym:%'"
        ).fetchone()[0]
    assert zero_edge_rows >= 1
    assert symbol_id_rows == 3


def test_stage2_json_output_is_deterministic_for_same_input(tmp_path: Path) -> None:
    stage1_path = tmp_path / "segment1.json"
    stage2_path = tmp_path / "segment2.json"
    graph_db_path = tmp_path / "graph.db"
    _write_stage1_fixture(stage1_path)

    run_stage2(str(stage1_path), str(stage2_path), graph_db_path=str(graph_db_path))
    first_hash = _sha256(stage2_path)

    run_stage2(str(stage1_path), str(stage2_path), graph_db_path=str(graph_db_path))
    second_hash = _sha256(stage2_path)

    assert first_hash == second_hash


def test_run_stage2_filters_unresolved_and_ambiguous_members(tmp_path: Path) -> None:
    stage1_path = tmp_path / "segment1_collision.json"
    stage2_path = tmp_path / "segment2_collision.json"
    graph_db_path = tmp_path / "collision.db"
    payload = _write_stage1_fixture(stage1_path)
    payload["call_graph"]["adjacency"] = {
        "A.a1": ["B.b1", "self.a1", "missing.call"],
        "B.b1": [],
        "C.c1": [],
    }
    stage1_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    run_stage2(str(stage1_path), str(stage2_path), graph_db_path=str(graph_db_path))
    stage2_payload = json.loads(stage2_path.read_text(encoding="utf-8"))
    all_method_ids = [method_id for partition in stage2_payload["partitions"] for method_id in (partition.get("methods") or [])]
    assert "sym:Other.a1" not in all_method_ids
    assert all(method_id in {"sym:A.a1", "sym:B.b1", "sym:C.c1"} for method_id in all_method_ids)


def test_persist_stage2_snapshot_rolls_back_on_failure(tmp_path: Path, monkeypatch) -> None:
    graph_db_path = tmp_path / "rollback.db"
    initial_partitions = [
        {"partition_id": "partition_0", "name": "p0", "methods": ["sym:A.a1"], "member_symbols": [{"symbol_id": "sym:A.a1", "qualified_name": "A.a1"}], "internal_calls": 1, "external_calls": 0, "cohesion_score": 1.0},
    ]
    persist_stage2_snapshot(str(graph_db_path), initial_partitions, [])

    original_connect = sqlite_store.sqlite3.connect

    class FaultyConnection:
        def __init__(self, connection):
            self._connection = connection
            self._executemany_calls = 0

        def __getattr__(self, item):
            return getattr(self._connection, item)

        def __enter__(self):
            self._connection.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self._connection.__exit__(exc_type, exc_val, exc_tb)

        def executemany(self, sql, seq_of_parameters):
            self._executemany_calls += 1
            if self._executemany_calls == 2:
                raise RuntimeError("forced insert failure")
            return self._connection.executemany(sql, seq_of_parameters)

    monkeypatch.setattr(
        sqlite_store.sqlite3,
        "connect",
        lambda *args, **kwargs: FaultyConnection(original_connect(*args, **kwargs)),
    )

    with pytest.raises(RuntimeError, match="forced insert failure"):
        persist_stage2_snapshot(
            str(graph_db_path),
            partitions=[
                {"partition_id": "partition_new", "name": "new", "methods": ["sym:B.b1"], "member_symbols": [{"symbol_id": "sym:B.b1", "qualified_name": "B.b1"}], "internal_calls": 0, "external_calls": 0, "cohesion_score": 1.0},
            ],
            partition_topology=[],
        )

    with sqlite3.connect(str(graph_db_path)) as connection:
        persisted_partitions = [row[0] for row in connection.execute("SELECT partition_id FROM partitions ORDER BY partition_id")]
        persisted_symbols = [row[0] for row in connection.execute("SELECT symbol_id FROM partition_assignments ORDER BY symbol_id")]

    assert persisted_partitions == ["partition_0"]
    assert persisted_symbols == ["sym:A.a1"]


def test_python_m_segment_2_partition_succeeds(tmp_path: Path) -> None:
    stage1_path = tmp_path / "segment1.json"
    stage2_path = tmp_path / "segment2.json"
    graph_db_path = tmp_path / "graph.db"
    _write_stage1_fixture(stage1_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "segment_2_partition",
            "--input",
            str(stage1_path),
            "--output",
            str(stage2_path),
            "--graph-db",
            str(graph_db_path),
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert stage2_path.exists()
    assert graph_db_path.exists()
