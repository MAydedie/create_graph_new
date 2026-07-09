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

from graph_store.partition_topology import build_partition_topology
from graph_store.sqlite_store import persist_stage2_snapshot
from segment_3_function_partition import cli as stage3_cli
from segment_4_community_semantics import cli as stage4_cli
from segment_5_path_semantics import cli as stage5_cli


def _write_stage1_fixture(path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    source_a = path.parent / "service_a.py"
    source_b = path.parent / "service_b.py"
    source_c = path.parent / "service_c.py"
    source_a.write_text(
        "def a1(data):\n"
        "    prepared = b1(data)\n"
        "    return prepared\n",
        encoding="utf-8",
    )
    source_b.write_text(
        "def b1(data):\n"
        "    normalized = c1(data)\n"
        "    return normalized\n",
        encoding="utf-8",
    )
    source_c.write_text(
        "def c1(data):\n"
        "    result = data.strip()\n"
        "    return result\n",
        encoding="utf-8",
    )
    payload = {
        "schema_version": "stage1.v1",
        "project": {"name": "fixture_project", "path": "D:/fixture/project"},
        "symbols": [
            {
                "id": "sym:A.a1",
                "qualified_name": "A.a1",
                "name": "a1",
                "kind": "function",
                "file_path": str(source_a).replace("\\", "/"),
                "line_start": 1,
                "line_end": 3,
                "signature": "A.a1(data)",
                "return_type": "str",
                "parameters": [{"name": "data", "type": "str", "position": 0}],
                "source_code": source_a.read_text(encoding="utf-8"),
            },
            {
                "id": "sym:B.b1",
                "qualified_name": "B.b1",
                "name": "b1",
                "kind": "function",
                "file_path": str(source_b).replace("\\", "/"),
                "line_start": 1,
                "line_end": 3,
                "signature": "B.b1(data)",
                "return_type": "str",
                "parameters": [{"name": "data", "type": "str", "position": 0}],
                "source_code": source_b.read_text(encoding="utf-8"),
            },
            {
                "id": "sym:C.c1",
                "qualified_name": "C.c1",
                "name": "c1",
                "kind": "function",
                "file_path": str(source_c).replace("\\", "/"),
                "line_start": 1,
                "line_end": 3,
                "signature": "C.c1(data)",
                "return_type": "str",
                "parameters": [{"name": "data", "type": "str", "position": 0}],
                "source_code": source_c.read_text(encoding="utf-8"),
            },
        ],
        "call_graph": {
            "adjacency": {"A.a1": ["B.b1"], "B.b1": ["C.c1"], "C.c1": []},
            "unresolved_targets": [],
        },
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return payload


def _write_stage2_fixture(base_dir: Path) -> tuple[Path, Path, Path]:
    stage1_path = base_dir / "segment1.json"
    stage2_path = base_dir / "segment2.json"
    graph_db_path = base_dir / "graph.db"
    _write_stage1_fixture(stage1_path)

    partitions = [
        {
            "partition_id": "partition_0",
            "name": "p0",
            "methods": ["sym:A.a1", "sym:B.b1", "sym:C.c1"],
            "qualified_methods": ["A.a1", "B.b1", "C.c1"],
            "member_symbols": [
                {"symbol_id": "sym:A.a1", "qualified_name": "A.a1"},
                {"symbol_id": "sym:B.b1", "qualified_name": "B.b1"},
                {"symbol_id": "sym:C.c1", "qualified_name": "C.c1"},
            ],
            "internal_calls": 2,
            "external_calls": 0,
            "cohesion_score": 1.0,
            "size": 3,
            "modularity": 0.95,
        }
    ]
    partition_call_graphs = {
        "partition_0": {
            "internal_edges": [
                {"source": "A.a1", "target": "B.b1", "type": "calls"},
                {"source": "B.b1", "target": "C.c1", "type": "calls"},
            ],
            "external_edges": [],
            "nodes": [],
            "statistics": {"total_edges": 2},
        }
    }
    topology = build_partition_topology(partitions, partition_call_graphs)
    persist_stage2_snapshot(str(graph_db_path), partitions, topology, source_project_path="D:/fixture/project")

    payload = {
        "schema_version": "stage2.v1",
        "input": {"stage1_output_path": str(stage1_path).replace("\\", "/")},
        "project": {"name": "fixture_project", "path": "D:/fixture/project"},
        "artifacts": {"graph_db_path": str(graph_db_path).replace("\\", "/")},
        "summary": {"partition_count": 1, "avg_modularity": 0.95},
        "partition_statistics": {"avg_modularity": 0.95},
        "partition_topology": topology,
        "partition_call_graphs": partition_call_graphs,
        "partitions": partitions,
    }
    stage2_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return stage1_path, stage2_path, graph_db_path


def _write_stage4_fixture(base_dir: Path) -> tuple[Path, Path, Path]:
    stage1_path, stage2_path, _ = _write_stage2_fixture(base_dir / "stage2_fixture")
    stage3_path = base_dir / "stage3_outputs" / "segment3.json"
    stage3_cli.run_stage3(str(stage2_path), str(stage3_path), skip_llm=True)
    stage4_path = base_dir / "stage4_outputs" / "segment4.json"
    stage4_cli.run_stage4(str(stage3_path), str(stage4_path), skip_llm=True)
    stage4_payload = json.loads(stage4_path.read_text(encoding="utf-8"))
    return stage1_path, stage4_path, Path(stage4_payload["artifacts"]["stage4_graph_db_copy"])


def test_run_stage5_max_paths_and_skip_cfg_dfg_still_persists_paths_and_links(tmp_path: Path) -> None:
    _, stage4_path, _ = _write_stage4_fixture(tmp_path)
    stage5_path = tmp_path / "stage5_outputs" / "segment5.json"

    stage5_cli.run_stage5(str(stage4_path), str(stage5_path), max_paths=1, skip_cfg_dfg=True)

    payload = json.loads(stage5_path.read_text(encoding="utf-8"))
    assert payload["summary"]["path_count"] == 1
    assert payload["path_analyses"][0]["deep_analysis_status"] == "skipped_cfg_dfg"
    assert payload["path_links"]

    with sqlite3.connect(str(tmp_path / "stage5_outputs" / "graph.db")) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('partitions','partition_assignments','partition_topology','partitions_optimized','optimization_history','community_summaries','community_summary_history','paths','path_links','path_cfg','path_dfg','path_reverse_index')"
            )
        }
        path_rows = connection.execute("SELECT COUNT(*) FROM paths").fetchone()[0]
        link_rows = connection.execute("SELECT COUNT(*) FROM path_links").fetchone()[0]
        history_rows = connection.execute("SELECT COUNT(*) FROM path_history").fetchone()[0]
    assert len(tables) == 12
    assert path_rows == 1
    assert link_rows == 2
    assert history_rows == 1


def test_run_stage5_skip_llm_explain_leaves_explain_empty_and_marks_status(tmp_path: Path) -> None:
    _, stage4_path, _ = _write_stage4_fixture(tmp_path)
    stage5_path = tmp_path / "stage5_skip_explain.json"

    stage5_cli.run_stage5(str(stage4_path), str(stage5_path), skip_llm_explain=True)

    payload = json.loads(stage5_path.read_text(encoding="utf-8"))
    assert payload["path_analyses"]
    assert all(item["cfg_dfg_explain_md"] == "" for item in payload["path_analyses"])
    assert all(item["deep_analysis_status"] == "skipped_explain" for item in payload["path_analyses"])
    assert all(item["status"] == "skipped_explain" for item in payload["path_history"])


def test_run_stage5_empty_partitions_is_partial_and_non_crashing(tmp_path: Path) -> None:
    stage1_path, stage4_path, _ = _write_stage4_fixture(tmp_path)
    payload = json.loads(stage4_path.read_text(encoding="utf-8"))
    payload["partitions"] = []
    payload["partition_call_graphs"] = {}
    stage4_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    stage5_path = tmp_path / "stage5_partial.json"

    stage5_cli.run_stage5(str(stage4_path), str(stage5_path), stage1_path=str(stage1_path))

    result = json.loads(stage5_path.read_text(encoding="utf-8"))
    assert result["summary"]["status"] == "partial"
    assert result["summary"]["path_count"] == 0
    assert result["path_history"][0]["status"] == "partial"


def test_run_stage5_does_not_write_default_stage5_snapshot_into_canonical_db(tmp_path: Path) -> None:
    _, stage4_path, _ = _write_stage4_fixture(tmp_path)
    stage5_path = tmp_path / "stage5_no_canonical_write.json"

    stage5_cli.run_stage5(str(stage4_path), str(stage5_path), skip_llm_explain=True)

    payload = json.loads(stage5_path.read_text(encoding="utf-8"))
    canonical_graph_db_path = payload["artifacts"]["canonical_graph_db_path"]
    assert canonical_graph_db_path
    with sqlite3.connect(canonical_graph_db_path) as connection:
        path_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('paths','path_links','path_cfg','path_dfg','path_reverse_index','path_history')"
            )
        }
        path_row_count = connection.execute("SELECT COUNT(*) FROM paths").fetchone()[0] if "paths" in path_tables else 0
    assert path_row_count == 0


def test_run_stage5_path_reverse_index_supports_sql_lookup(tmp_path: Path) -> None:
    _, stage4_path, _ = _write_stage4_fixture(tmp_path)
    stage5_path = tmp_path / "stage5_reverse_index.json"

    stage5_cli.run_stage5(str(stage4_path), str(stage5_path))

    db_path = tmp_path / "graph.db"
    if not db_path.exists():
        db_path = tmp_path / "stage5_outputs" / "graph.db"
    with sqlite3.connect(str(db_path)) as connection:
        rows = connection.execute(
            "SELECT path_id FROM path_reverse_index WHERE method_qn = ? ORDER BY path_id",
            ("A.a1",),
        ).fetchall()
    assert rows


def test_python_m_segment_5_path_semantics_succeeds(tmp_path: Path) -> None:
    _, stage4_path, _ = _write_stage4_fixture(tmp_path)
    stage5_path = tmp_path / "segment5_cli.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "segment_5_path_semantics",
            "--input",
            str(stage4_path),
            "--output",
            str(stage5_path),
            "--skip-llm-explain",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert stage5_path.exists()
