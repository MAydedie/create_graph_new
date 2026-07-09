#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from segment_5_path_semantics import cli as stage5_cli
from segment_6_persistence import cli as stage6_cli
from tests.test_segment5_path_semantics import _write_stage4_fixture


def _write_stage5_fixture(base_dir: Path) -> Path:
    _, stage4_path, _ = _write_stage4_fixture(base_dir)
    stage5_path = base_dir / "stage5_outputs" / "segment5_output.json"
    stage5_cli.run_stage5(str(stage4_path), str(stage5_path), skip_llm_explain=True)
    return stage5_path


def _relation_pair_count_from_stage5(stage5_path: Path) -> int:
    payload = json.loads(stage5_path.read_text(encoding="utf-8"))
    pairs = set()
    for partition_id, partition_payload in (payload.get("partition_analyses") or {}).items():
        for path_item in partition_payload.get("path_analyses") or []:
            for method_qn in path_item.get("function_chain") or []:
                if method_qn:
                    pairs.add((partition_id, method_qn))
    return len(pairs)


def _rewrite_stage5_graph_db_artifact(stage5_path: Path, graph_db_path: Path) -> Path:
    payload = json.loads(stage5_path.read_text(encoding="utf-8"))
    artifacts = dict(payload.get("artifacts") or {})
    artifacts["stage5_graph_db_copy"] = str(graph_db_path).replace("\\", "/")
    artifacts["graph_db_path"] = str(graph_db_path).replace("\\", "/")
    payload["artifacts"] = artifacts
    rewritten = stage5_path.parent / f"{graph_db_path.stem}_segment5.json"
    rewritten.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return rewritten


def test_merge_graph_relations_is_idempotent_for_repeated_stage6_runs(tmp_path: Path) -> None:
    stage5_path = _write_stage5_fixture(tmp_path)
    stage6_path = tmp_path / "stage6_outputs" / "segment6_output.json"

    stage6_cli.run_stage6(str(stage5_path), str(stage6_path))
    first_payload = json.loads(stage6_path.read_text(encoding="utf-8"))
    first_relations = first_payload["graph_relations"]
    stage6_cli.run_stage6(str(stage5_path), str(stage6_path))
    second_payload = json.loads(stage6_path.read_text(encoding="utf-8"))

    assert second_payload["graph_relations"] == first_relations
    with sqlite3.connect(str(tmp_path / "stage6_outputs" / "graph.db")) as connection:
        relation_count = connection.execute("SELECT COUNT(*) FROM graph_relations").fetchone()[0]
        summary_count = connection.execute("SELECT COUNT(*) FROM graph_summary").fetchone()[0]
    assert relation_count == _relation_pair_count_from_stage5(stage5_path)
    assert summary_count >= 3


def test_skip_validation_still_merges_graph_tables(tmp_path: Path) -> None:
    stage5_path = _write_stage5_fixture(tmp_path)
    stage6_path = tmp_path / "stage6_outputs" / "segment6_skip_validation.json"

    stage6_cli.run_stage6(str(stage5_path), str(stage6_path), skip_validation=True)

    payload = json.loads(stage6_path.read_text(encoding="utf-8"))
    assert payload["summary"]["validation_status"] == "skipped"
    with sqlite3.connect(str(tmp_path / "stage6_outputs" / "graph.db")) as connection:
        assert connection.execute("SELECT COUNT(*) FROM graph_relations").fetchone()[0] > 0
        assert connection.execute("SELECT COUNT(*) FROM graph_summary").fetchone()[0] > 0


def test_empty_partition_analyses_is_partial_and_non_crashing(tmp_path: Path) -> None:
    stage5_path = _write_stage5_fixture(tmp_path)
    payload = json.loads(stage5_path.read_text(encoding="utf-8"))
    payload["partition_analyses"] = {}
    payload["path_analyses"] = []
    partial_stage5_path = tmp_path / "stage5_outputs" / "segment5_empty.json"
    partial_stage5_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    stage6_path = tmp_path / "stage6_outputs" / "segment6_partial.json"

    stage6_cli.run_stage6(str(partial_stage5_path), str(stage6_path))

    result = json.loads(stage6_path.read_text(encoding="utf-8"))
    assert result["summary"]["status"] == "partial"
    assert result["graph_relations"] == []
    with sqlite3.connect(str(tmp_path / "stage6_outputs" / "graph.db")) as connection:
        audit_status = connection.execute(
            "SELECT status FROM graph_summary WHERE summary_type='partition_audit'"
        ).fetchone()[0]
    assert audit_status == "partial"


def test_graph_relations_support_partition_lookup(tmp_path: Path) -> None:
    stage5_path = _write_stage5_fixture(tmp_path)
    stage6_path = tmp_path / "stage6_outputs" / "segment6_lookup.json"

    stage6_cli.run_stage6(str(stage5_path), str(stage6_path))

    with sqlite3.connect(str(tmp_path / "stage6_outputs" / "graph.db")) as connection:
        rows = connection.execute(
            "SELECT method_qn FROM graph_relations WHERE partition_id = ? ORDER BY method_qn",
            ("partition_0",),
        ).fetchall()
    assert [row[0] for row in rows] == ["A.a1", "B.b1", "C.c1"]


def test_python_m_segment_6_persistence_succeeds(tmp_path: Path) -> None:
    stage5_path = _write_stage5_fixture(tmp_path)
    stage6_path = tmp_path / "stage6_outputs" / "segment6_cli.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "segment_6_persistence",
            "--input",
            str(stage5_path),
            "--output",
            str(stage6_path),
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert stage6_path.exists()


def test_validation_warns_instead_of_crashing_when_stage_tables_are_missing(tmp_path: Path) -> None:
    stage5_path = _write_stage5_fixture(tmp_path)
    unrelated_db = tmp_path / "stage5_outputs" / "unrelated.db"
    with sqlite3.connect(str(unrelated_db)) as connection:
        connection.execute("CREATE TABLE unrelated_table (id INTEGER PRIMARY KEY)")
    rewritten_stage5_path = _rewrite_stage5_graph_db_artifact(stage5_path, unrelated_db)
    stage6_path = tmp_path / "stage6_outputs" / "segment6_missing_tables.json"

    stage6_cli.run_stage6(str(rewritten_stage5_path), str(stage6_path))

    result = json.loads(stage6_path.read_text(encoding="utf-8"))
    validation = result["persistence"]["validation"]
    assert result["summary"]["validation_status"] == "warning"
    assert "partitions" in validation["missing_stage1_to_stage5_tables"]
    assert "partition_topology" in validation["missing_stage1_to_stage5_tables"]
    assert validation["missing_relation_partitions_in_db"] == ["partition_0"]


def test_validation_warns_when_stage_tables_exist_but_have_no_partition_rows(tmp_path: Path) -> None:
    stage5_path = _write_stage5_fixture(tmp_path)
    empty_schema_db = tmp_path / "stage5_outputs" / "empty_schema.db"
    with sqlite3.connect(str(empty_schema_db)) as connection:
        connection.execute(
            "CREATE TABLE partitions (partition_id TEXT PRIMARY KEY)"
        )
        connection.execute(
            "CREATE TABLE partition_topology (source_partition TEXT, target_partition TEXT)"
        )
    rewritten_stage5_path = _rewrite_stage5_graph_db_artifact(stage5_path, empty_schema_db)
    stage6_path = tmp_path / "stage6_outputs" / "segment6_empty_schema.json"

    stage6_cli.run_stage6(str(rewritten_stage5_path), str(stage6_path))

    result = json.loads(stage6_path.read_text(encoding="utf-8"))
    validation = result["persistence"]["validation"]
    assert validation["status"] == "warning"
    assert validation["db_partition_count"] == 0
    assert validation["missing_json_partitions_in_db"] == ["partition_0"]
    assert validation["missing_relation_partitions_in_db"] == ["partition_0"]


def test_max_relations_zero_persists_no_relation_rows(tmp_path: Path) -> None:
    stage5_path = _write_stage5_fixture(tmp_path)
    stage6_path = tmp_path / "stage6_outputs" / "segment6_zero_relations.json"

    stage6_cli.run_stage6(str(stage5_path), str(stage6_path), max_relations=0)

    result = json.loads(stage6_path.read_text(encoding="utf-8"))
    assert result["graph_relations"] == []
    with sqlite3.connect(str(tmp_path / "stage6_outputs" / "graph.db")) as connection:
        relation_count = connection.execute("SELECT COUNT(*) FROM graph_relations").fetchone()[0]
    assert relation_count == 0


def test_artifact_paths_outside_stage_run_root_are_not_trusted(tmp_path: Path) -> None:
    stage5_path = _write_stage5_fixture(tmp_path)
    original_payload = json.loads(stage5_path.read_text(encoding="utf-8"))
    outside_dir = tmp_path.parent / f"{tmp_path.name}_outside"
    outside_dir.mkdir()
    outside_db = outside_dir / "untrusted.db"
    with sqlite3.connect(str(outside_db)) as connection:
        connection.execute("CREATE TABLE unrelated_table (id INTEGER PRIMARY KEY)")
    outside_stage1 = outside_dir / "segment1_output.json"
    outside_stage1.write_text(
        json.dumps({"symbols": [{"id": "sym:bad", "qualified_name": "bad.method"}]}, sort_keys=True),
        encoding="utf-8",
    )
    payload = dict(original_payload)
    payload["artifacts"] = {
        **dict(original_payload.get("artifacts") or {}),
        "stage5_graph_db_copy": str(outside_db).replace("\\", "/"),
        "graph_db_path": str(outside_db).replace("\\", "/"),
    }
    payload["input"] = {
        **dict(original_payload.get("input") or {}),
        "stage1_output_path": str(outside_stage1).replace("\\", "/"),
    }
    untrusted_stage5_path = tmp_path / "stage5_outputs" / "segment5_untrusted_paths.json"
    untrusted_stage5_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    stage6_path = tmp_path / "stage6_outputs" / "segment6_trust_root.json"

    stage6_cli.run_stage6(str(untrusted_stage5_path), str(stage6_path))

    result = json.loads(stage6_path.read_text(encoding="utf-8"))
    assert result["summary"]["status"] == "completed"
    assert result["persistence"]["validation"]["symbol_validation_mode"] == "skipped_no_stage1_symbols"
    assert result["artifacts"]["source_graph_db_path"].endswith("stage5_outputs/graph.db")
    with sqlite3.connect(str(tmp_path / "stage6_outputs" / "graph.db")) as connection:
        assert connection.execute("SELECT COUNT(*) FROM partitions").fetchone()[0] == 1
