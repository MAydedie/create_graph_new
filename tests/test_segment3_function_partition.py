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

from analysis.llm_partition_optimizer import OptimizationHistory, OptimizationResult, plan_partition_optimization
from analysis.stage3_partition_runtime import restore_optimized_partitions
from graph_store.partition_topology import build_partition_topology
from graph_store.sqlite_store import persist_stage2_snapshot
from segment_3_function_partition import cli as stage3_cli


def _write_stage1_fixture(path: Path) -> dict:
    payload = {
        "schema_version": "stage1.v1",
        "project": {
            "name": "fixture_project",
            "path": "D:/fixture/project",
        },
        "symbols": [
            {"id": "sym:A.a1", "qualified_name": "A.a1", "kind": "method"},
            {"id": "sym:B.b1", "qualified_name": "B.b1", "kind": "method"},
            {"id": "sym:C.c1", "qualified_name": "C.c1", "kind": "method"},
        ],
        "call_graph": {
            "adjacency": {
                "A.a1": ["B.b1"],
                "B.b1": ["C.c1"],
                "C.c1": [],
            },
            "unresolved_targets": [],
        },
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return payload


def _write_stage2_fixture(base_dir: Path, *, avg_modularity: float) -> tuple[Path, Path, Path]:
    stage1_path = base_dir / "segment1.json"
    stage2_path = base_dir / "segment2.json"
    graph_db_path = base_dir / "graph.db"
    _write_stage1_fixture(stage1_path)

    partitions = [
        {
            "partition_id": "partition_0",
            "name": "p0",
            "methods": ["sym:A.a1", "sym:B.b1"],
            "qualified_methods": ["A.a1", "B.b1"],
            "member_symbols": [
                {"symbol_id": "sym:A.a1", "qualified_name": "A.a1"},
                {"symbol_id": "sym:B.b1", "qualified_name": "B.b1"},
            ],
            "internal_calls": 1,
            "external_calls": 1,
            "cohesion_score": 0.5,
            "size": 2,
            "modularity": avg_modularity,
        },
        {
            "partition_id": "partition_1",
            "name": "p1",
            "methods": ["sym:C.c1"],
            "qualified_methods": ["C.c1"],
            "member_symbols": [{"symbol_id": "sym:C.c1", "qualified_name": "C.c1"}],
            "internal_calls": 0,
            "external_calls": 0,
            "cohesion_score": 1.0,
            "size": 1,
            "modularity": avg_modularity,
        },
    ]
    partition_call_graphs = {
        "partition_0": {
            "internal_edges": [{"source": "A.a1", "target": "B.b1", "type": "calls"}],
            "external_edges": [{"source": "B.b1", "target": "C.c1", "type": "calls"}],
            "nodes": [],
            "statistics": {"total_edges": 2},
        },
        "partition_1": {
            "internal_edges": [],
            "external_edges": [],
            "nodes": [],
            "statistics": {"total_edges": 0},
        },
    }
    topology = build_partition_topology(partitions, partition_call_graphs)
    persist_stage2_snapshot(str(graph_db_path), partitions, topology, source_project_path="D:/fixture/project")

    payload = {
        "schema_version": "stage2.v1",
        "input": {
            "stage1_output_path": str(stage1_path).replace("\\", "/"),
            "algorithm": "louvain",
            "random_state": 42,
            "weight_threshold": 0.0,
        },
        "project": {
            "name": "fixture_project",
            "path": "D:/fixture/project",
        },
        "artifacts": {
            "graph_db_path": str(graph_db_path).replace("\\", "/"),
        },
        "summary": {
            "partition_count": len(partitions),
            "total_partitioned_methods": 3,
            "avg_modularity": avg_modularity,
        },
        "partition_statistics": {"avg_modularity": avg_modularity},
        "partition_topology": topology,
        "partition_call_graphs": partition_call_graphs,
        "partitions": partitions,
    }
    stage2_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return stage1_path, stage2_path, graph_db_path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_plan_partition_optimization_threshold_and_force() -> None:
    partitions = [{"modularity": 0.95}, {"modularity": 0.95}]
    skipped = plan_partition_optimization(partitions, threshold=0.4, force=False, skip_llm=False)
    forced = plan_partition_optimization(partitions, threshold=0.4, force=True, skip_llm=False)

    assert skipped["should_run"] is False
    assert forced["should_run"] is True
    assert forced["trigger_mode"] == "force"


def test_run_stage3_skips_high_modularity_and_persists_empty_tables(tmp_path: Path) -> None:
    _, stage2_path, graph_db_path = _write_stage2_fixture(tmp_path, avg_modularity=0.95)
    stage3_path = tmp_path / "segment3.json"

    stage3_cli.run_stage3(str(stage2_path), str(stage3_path))

    payload = json.loads(stage3_path.read_text(encoding="utf-8"))
    assert payload["summary"]["optimization_triggered"] is False
    assert payload["summary"]["optimization_applied"] is False
    assert payload["partitions_optimized"] == []

    with sqlite3.connect(str(graph_db_path)) as connection:
        optimized_count = connection.execute("SELECT COUNT(*) FROM partitions_optimized").fetchone()[0]
        history_rows = connection.execute("SELECT action, status FROM optimization_history").fetchall()

    assert optimized_count == 0
    assert history_rows == [("skipped", "skipped")]


def test_run_stage3_force_invokes_optimizer_and_persists_rows(tmp_path: Path, monkeypatch) -> None:
    _, stage2_path, graph_db_path = _write_stage2_fixture(tmp_path, avg_modularity=0.95)
    stage3_path = tmp_path / "segment3_force.json"

    def fake_optimize(self, initial_partitions, call_graph, multi_source_info=None, max_iterations=3, modularity_improvement_threshold=0.1):
        optimized = [dict(initial_partitions[0], partition_id="optimized_partition", methods=["A.a1", "B.b1", "C.c1"], qualified_methods=["A.a1", "B.b1", "C.c1"], size=3, modularity=0.97)]
        return OptimizationResult(
            partitions=optimized,
            optimization_history=[OptimizationHistory(
                iteration=1,
                action="merge",
                partitions_before=initial_partitions,
                partitions_after=optimized,
                modularity_before=0.95,
                modularity_after=0.97,
                modularity_improvement=0.02,
                llm_reasoning="merge related partitions",
                details={"merge": ["partition_0", "partition_1"]},
            )],
            statistics={"final_modularity": 0.97},
        )

    monkeypatch.setattr(stage3_cli, "has_deepseek_config", lambda: True)
    monkeypatch.setattr(stage3_cli, "get_deepseek_settings", lambda: {"api_key": "fake", "base_url": "https://example.com"})
    monkeypatch.setattr(stage3_cli.LLMPartitionOptimizer, "optimize_partitions", fake_optimize)

    stage3_cli.run_stage3(str(stage2_path), str(stage3_path), force=True)

    payload = json.loads(stage3_path.read_text(encoding="utf-8"))
    assert payload["summary"]["optimization_triggered"] is True
    assert payload["summary"]["optimization_applied"] is True
    assert payload["summary"]["optimized_partition_count"] == 1

    with sqlite3.connect(str(graph_db_path)) as connection:
        optimized_count = connection.execute("SELECT COUNT(*) FROM partitions_optimized").fetchone()[0]
        history_count = connection.execute("SELECT COUNT(*) FROM optimization_history").fetchone()[0]

    assert optimized_count == 1
    assert history_count == 1


def test_run_stage3_skip_llm_overrides_force(tmp_path: Path, monkeypatch) -> None:
    _, stage2_path, graph_db_path = _write_stage2_fixture(tmp_path, avg_modularity=0.1)
    stage3_path = tmp_path / "segment3_skip.json"

    def _fail(*args, **kwargs):
        raise AssertionError("optimizer should not run when --skip-llm is set")

    monkeypatch.setattr(stage3_cli.LLMPartitionOptimizer, "optimize_partitions", _fail)

    stage3_cli.run_stage3(str(stage2_path), str(stage3_path), force=True, skip_llm=True)

    payload = json.loads(stage3_path.read_text(encoding="utf-8"))
    assert payload["summary"]["optimization_triggered"] is False
    with sqlite3.connect(str(graph_db_path)) as connection:
        optimized_count = connection.execute("SELECT COUNT(*) FROM partitions_optimized").fetchone()[0]
    assert optimized_count == 0


def test_run_stage3_honors_force_env_override(tmp_path: Path, monkeypatch) -> None:
    _, stage2_path, graph_db_path = _write_stage2_fixture(tmp_path, avg_modularity=0.95)
    stage3_path = tmp_path / "segment3_env_force.json"

    def fake_optimize(self, initial_partitions, call_graph, multi_source_info=None, max_iterations=3, modularity_improvement_threshold=0.1):
        optimized = [dict(initial_partitions[0], partition_id="partition_0", methods=["A.a1", "B.b1", "C.c1"], qualified_methods=["A.a1", "B.b1", "C.c1"], size=3, modularity=0.97)]
        return OptimizationResult(
            partitions=optimized,
            optimization_history=[OptimizationHistory(
                iteration=1,
                action="merge",
                partitions_before=initial_partitions,
                partitions_after=optimized,
                modularity_before=0.95,
                modularity_after=0.97,
                modularity_improvement=0.02,
                llm_reasoning="forced by env",
                details={"merge": ["partition_0", "partition_1"]},
            )],
            statistics={"final_modularity": 0.97},
        )

    monkeypatch.setenv("FH_FORCE_LLM_PARTITION", "1")
    monkeypatch.setattr(stage3_cli, "has_deepseek_config", lambda: True)
    monkeypatch.setattr(stage3_cli, "get_deepseek_settings", lambda: {"api_key": "fake", "base_url": "https://example.com"})
    monkeypatch.setattr(stage3_cli.LLMPartitionOptimizer, "optimize_partitions", fake_optimize)

    stage3_cli.run_stage3(str(stage2_path), str(stage3_path), force=None)

    payload = json.loads(stage3_path.read_text(encoding="utf-8"))
    assert payload["summary"]["optimization_triggered"] is True
    assert payload["optimization"]["trigger"]["trigger_mode"] == "force"


def test_restore_optimized_partitions_preserves_stage2_shape() -> None:
    original = [
        {
            "partition_id": "partition_0",
            "name": "p0",
            "methods": ["sym:A.a1"],
            "qualified_methods": ["A.a1"],
            "member_symbols": [{"symbol_id": "sym:A.a1", "qualified_name": "A.a1"}],
            "internal_calls": 1,
            "external_calls": 0,
            "cohesion_score": 1.0,
            "size": 1,
            "modularity": 1.0,
        }
    ]
    optimized = [
        {
            "partition_id": "partition_0",
            "methods": ["A.a1"],
            "modularity": 0.9,
            "internal_calls": 1,
            "external_calls": 0,
        }
    ]

    restored = restore_optimized_partitions(optimized, original)
    assert restored[0]["methods"] == ["sym:A.a1"]
    assert restored[0]["qualified_methods"] == ["A.a1"]
    assert restored[0]["member_symbols"] == [{"symbol_id": "sym:A.a1", "qualified_name": "A.a1"}]


def test_run_stage3_skip_llm_output_is_deterministic(tmp_path: Path) -> None:
    _, stage2_path, graph_db_path = _write_stage2_fixture(tmp_path, avg_modularity=0.95)
    stage3_path = tmp_path / "segment3_deterministic.json"

    stage3_cli.run_stage3(str(stage2_path), str(stage3_path), graph_db_path=str(graph_db_path), skip_llm=True)
    first_hash = _sha256(stage3_path)

    stage3_cli.run_stage3(str(stage2_path), str(stage3_path), graph_db_path=str(graph_db_path), skip_llm=True)
    second_hash = _sha256(stage3_path)

    assert first_hash == second_hash


def test_run_stage3_writes_stage3_graph_db_copy_next_to_output(tmp_path: Path) -> None:
    stage3_dir = tmp_path / "stage3_out"
    stage3_dir.mkdir(parents=True, exist_ok=True)
    stage3_path = stage3_dir / "segment3_copy.json"
    stage3_db_copy = stage3_dir / "graph.db"
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    _, stage2_path, _ = _write_stage2_fixture(fixture_dir, avg_modularity=0.95)

    stage3_cli.run_stage3(str(stage2_path), str(stage3_path), skip_llm=True)

    assert stage3_db_copy.exists(), "stage3 graph.db copy should be placed next to stage3_output.json"

    payload = json.loads(stage3_path.read_text(encoding="utf-8"))
    stage3_graph_db_copy = payload["artifacts"]["stage3_graph_db_copy"]
    assert stage3_graph_db_copy is not None
    assert stage3_graph_db_copy.endswith("graph.db")

    with sqlite3.connect(str(stage3_db_copy)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('partitions_optimized','optimization_history')"
            )
        }
    assert {"partitions_optimized", "optimization_history"}.issubset(tables)


def test_python_m_segment_3_function_partition_succeeds(tmp_path: Path) -> None:
    _, stage2_path, graph_db_path = _write_stage2_fixture(tmp_path, avg_modularity=0.95)
    stage3_path = tmp_path / "segment3_cli.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "segment_3_function_partition",
            "--input",
            str(stage2_path),
            "--output",
            str(stage3_path),
            "--graph-db",
            str(graph_db_path),
            "--skip-llm",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert stage3_path.exists()


def test_optimization_history_records_per_action_rows(tmp_path: Path) -> None:
    _, stage2_path, graph_db_path = _write_stage2_fixture(tmp_path, avg_modularity=0.95)
    stage3_path = tmp_path / "segment3_history_actions.json"

    def fake_optimize(self, initial_partitions, call_graph, multi_source_info=None, max_iterations=3, modularity_improvement_threshold=0.1):
        optimized = [dict(initial_partitions[0], partition_id="partition_0", methods=["A.a1", "B.b1", "C.c1"], qualified_methods=["A.a1", "B.b1", "C.c1"], size=3, modularity=0.97)]
        history_rows = []
        actions = ("merge", "split", "adjust", "summary")
        for index, action in enumerate(actions):
            history_rows.append(
                OptimizationHistory(
                    iteration=1,
                    action=action,
                    partitions_before=initial_partitions,
                    partitions_after=optimized,
                    modularity_before=0.95,
                    modularity_after=0.97,
                    modularity_improvement=0.02,
                    llm_reasoning=f"{action} action",
                    details={"decisions": [{"affected_ids": ["partition_0", "partition_1"]}]},
                )
            )
        return OptimizationResult(
            partitions=optimized,
            optimization_history=history_rows,
            statistics={"final_modularity": 0.97},
        )

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(stage3_cli, "has_deepseek_config", lambda: True)
        monkeypatch.setattr(stage3_cli, "get_deepseek_settings", lambda: {"api_key": "fake", "base_url": "https://example.com"})
        monkeypatch.setattr(stage3_cli.LLMPartitionOptimizer, "optimize_partitions", fake_optimize)

        stage3_cli.run_stage3(str(stage2_path), str(stage3_path), force=True)
    finally:
        monkeypatch.undo()

    with sqlite3.connect(str(graph_db_path)) as connection:
        action_counts = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT action, COUNT(1) FROM optimization_history GROUP BY action ORDER BY action"
            )
        }

    assert action_counts == {"adjust": 1, "merge": 1, "split": 1, "summary": 1}
