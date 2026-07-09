#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graph_query.hub_query import find_hubs, get_partition_topology
from graph_query.llm_interface import as_llm_tool_schemas
from graph_query.path_query import find_paths_between
from segment_6_persistence import cli as stage6_cli
from segment_7_graph_query import cli as stage7_cli
from tests.test_segment6_persistence import _write_stage5_fixture


REAL_STAGE6_DIR = PROJECT_ROOT.parent / "实验对比项目" / "JUnitGenie-main" / "segment_runs" / "stage6_outputs"


def _write_stage6_fixture(base_dir: Path) -> tuple[Path, Path]:
    stage5_path = _write_stage5_fixture(base_dir)
    stage6_path = base_dir / "stage6_outputs" / "segment6_output.json"
    stage6_cli.run_stage6(str(stage5_path), str(stage6_path))
    return stage6_path, base_dir / "stage6_outputs" / "graph.db"


def _real_stage6_paths() -> tuple[Path, Path]:
    segment6_path = REAL_STAGE6_DIR / "segment6_output.json"
    graph_db_path = REAL_STAGE6_DIR / "graph.db"
    if not segment6_path.exists() or not graph_db_path.exists():
        pytest.skip("real JUnitGenie stage6 artifacts are not available")
    return segment6_path, graph_db_path


def test_list_relations_matches_segment6_output_graph_relations(tmp_path: Path) -> None:
    segment6_path, graph_db_path = _write_stage6_fixture(tmp_path)
    output_path = tmp_path / "stage7_outputs" / "segment7_query_result.json"

    stage7_cli.run_stage7(
        str(graph_db_path),
        str(output_path),
        query={"query": "list_relations"},
    )

    segment6_payload = json.loads(segment6_path.read_text(encoding="utf-8"))
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["summary"]["status"] == "completed"
    assert result["graph_relations_used"] == len(segment6_payload["graph_relations"])
    assert len(result["queries"][0]["result"]) == len(segment6_payload["graph_relations"])


def test_get_partition_topology_count_matches_stage6_db() -> None:
    _, graph_db_path = _real_stage6_paths()

    rows = get_partition_topology(str(graph_db_path))
    with sqlite3.connect(str(graph_db_path)) as connection:
        expected = connection.execute("SELECT COUNT(*) FROM partition_topology").fetchone()[0]

    assert len(rows) == expected == 132


def test_find_hubs_top5_are_backed_by_path_links() -> None:
    _, graph_db_path = _real_stage6_paths()

    hubs = find_hubs(str(graph_db_path), top_k=5)
    with sqlite3.connect(str(graph_db_path)) as connection:
        for hub in hubs:
            count = connection.execute(
                "SELECT COUNT(*) FROM path_links WHERE caller = ? OR callee = ?",
                (hub["method_qn"], hub["method_qn"]),
            ).fetchone()[0]
            assert count > 0

    assert len(hubs) == 5


def test_find_paths_between_returns_path_on_two_partition_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "two_partition.db"
    with sqlite3.connect(str(db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE paths (
                path_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                partition_id TEXT NOT NULL,
                leaf_node TEXT NOT NULL,
                function_chain_json TEXT NOT NULL,
                path_name TEXT NOT NULL,
                path_description TEXT NOT NULL,
                semantic_label TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                functional_domain TEXT NOT NULL,
                worthiness_score REAL NOT NULL,
                deep_analysis_status TEXT NOT NULL,
                cfg_dfg_explain_md TEXT NOT NULL,
                model TEXT,
                duration_ms INTEGER NOT NULL,
                source_project_path TEXT,
                skip_reason TEXT,
                trigger_mode TEXT NOT NULL,
                llm_reasoning TEXT NOT NULL
            );
            CREATE TABLE path_links (
                link_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                path_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                caller TEXT NOT NULL,
                callee TEXT NOT NULL,
                is_direct_call INTEGER,
                caller_file_path TEXT NOT NULL,
                callee_file_path TEXT NOT NULL
            );
            CREATE TABLE path_cfg (
                cfg_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                path_id TEXT NOT NULL,
                method_sig TEXT NOT NULL,
                node_id TEXT NOT NULL,
                line_number INTEGER NOT NULL,
                node_type TEXT NOT NULL,
                code_excerpt TEXT NOT NULL
            );
            CREATE TABLE path_dfg (
                dfg_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                path_id TEXT NOT NULL,
                method_sig TEXT NOT NULL,
                variable_name TEXT NOT NULL,
                node_id TEXT NOT NULL,
                line_number INTEGER NOT NULL,
                node_type TEXT NOT NULL,
                method_node_id TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO paths VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "partition_0_0",
                "run_fixture",
                "partition_0",
                "A.a",
                json.dumps(["A.a", "B.b", "C.c"]),
                "path 1",
                "fixture path",
                "fixture",
                "[]",
                "general",
                3.0,
                "completed",
                "",
                None,
                0,
                "D:/fixture/project",
                None,
                "fixture",
                "",
            ),
        )
        connection.execute(
            "INSERT INTO paths VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "partition_1_0",
                "run_fixture",
                "partition_1",
                "D.d",
                json.dumps(["D.d"]),
                "path 2",
                "second partition placeholder",
                "fixture",
                "[]",
                "general",
                1.0,
                "completed",
                "",
                None,
                0,
                "D:/fixture/project",
                None,
                "fixture",
                "",
            ),
        )
        connection.executemany(
            "INSERT INTO path_links VALUES (?,?,?,?,?,?,?,?,?)",
            [
                ("l0", "run_fixture", "partition_0_0", 0, "A.a", "B.b", 1, "a.py", "b.py"),
                ("l1", "run_fixture", "partition_0_0", 1, "B.b", "C.c", 1, "b.py", "c.py"),
            ],
        )

    result = find_paths_between(str(db_path), "A.a", "C.c", max_depth=3)

    assert len(result) >= 1
    assert result[0]["matched_subchain"] == ["A.a", "B.b", "C.c"]


def test_missing_graph_db_cli_is_partial_and_audited(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing.db"
    output_path = tmp_path / "stage7_outputs" / "segment7_query_result.json"
    audit_path = tmp_path / "stage7_outputs" / "logs" / "graph_query_audit.jsonl"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "segment_7_graph_query",
            "--graph-db",
            str(missing_db),
            "--query",
            "list_relations",
            "--output",
            str(output_path),
            "--audit-log",
            str(audit_path),
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(output_path.read_text(encoding="utf-8"))
    audit_rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert result["summary"]["status"] == "partial"
    assert result["queries"][0]["status"] == "partial"
    assert audit_rows[-1]["status"] == "partial"
    assert audit_rows[-1]["result_summary"]["type"] == "dict"
    assert "result" in audit_rows[-1]


def test_query_runs_when_unrelated_stage_tables_are_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "partial_stage6.db"
    with sqlite3.connect(str(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE graph_relations (
                partition_id TEXT NOT NULL,
                method_qn TEXT NOT NULL,
                symbol_id TEXT,
                relation_type TEXT NOT NULL,
                path_ids_json TEXT NOT NULL,
                path_count INTEGER NOT NULL,
                first_path_id TEXT,
                community_label TEXT,
                summary_status TEXT NOT NULL,
                source_project_path TEXT,
                run_id TEXT NOT NULL,
                relation_payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (partition_id, method_qn)
            )
            """
        )
        connection.execute(
            "INSERT INTO graph_relations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "partition_0",
                "A.a",
                "sym:A.a",
                "path_membership",
                json.dumps(["path_0"]),
                1,
                "path_0",
                "partition_0",
                "skipped",
                "D:/fixture/project",
                "stage6_fixture",
                json.dumps({"line_start": 1, "line_end": 2}),
                "stage6-deterministic",
            ),
        )
    output_path = tmp_path / "stage7_partial" / "segment7_query_result.json"

    stage7_cli.run_stage7(str(db_path), str(output_path), query={"query": "list_relations"})

    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["summary"]["status"] == "completed"
    assert result["summary"]["validation_status"] == "partial"
    assert result["queries"][0]["status"] == "completed"
    assert result["graph_relations_used"] == 1


def test_llm_tool_schemas_have_explicit_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("graph_query.llm_interface.has_deepseek_config", lambda: False)

    schemas = as_llm_tool_schemas()
    by_name = {item["function"]["name"]: item for item in schemas}
    callers_params = by_name["find_callers"]["function"]["parameters"]
    topology_params = by_name["get_partition_topology"]["function"]["parameters"]

    assert by_name["find_callers"]["llm_enabled"] is False
    assert callers_params["required"] == ["method"]
    assert callers_params["properties"]["method"]["type"] == "string"
    assert callers_params["additionalProperties"] is False
    assert topology_params["properties"] == {}
    assert topology_params["additionalProperties"] is False
