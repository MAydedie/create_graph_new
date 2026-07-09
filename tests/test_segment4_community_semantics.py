#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graph_store.partition_topology import build_partition_topology
from graph_store.sqlite_store import load_stage4_community_summaries, persist_stage2_snapshot
from app.services import analysis_service
from data.project_library_storage import ProjectLibraryStorage
from segment_3_function_partition import cli as stage3_cli
from segment_4_community_semantics import cli as stage4_cli


def _write_stage1_fixture(path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "stage1.v1",
        "project": {
            "name": "fixture_project",
            "path": "D:/fixture/project",
        },
        "symbols": [
            {"id": "sym:A.a1", "qualified_name": "A.a1", "kind": "method", "file_path": "src/a.py", "signature": "A.a1()"},
            {"id": "sym:B.b1", "qualified_name": "B.b1", "kind": "method", "file_path": "src/b.py", "signature": "B.b1()"},
            {"id": "sym:C.c1", "qualified_name": "C.c1", "kind": "method", "file_path": "src/c.py", "signature": "C.c1()"},
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
    base_dir.mkdir(parents=True, exist_ok=True)
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


def _write_stage3_fixture(base_dir: Path, *, avg_modularity: float) -> tuple[Path, Path]:
    stage3_dir = base_dir / "stage3_outputs"
    stage3_dir.mkdir(parents=True, exist_ok=True)
    _, stage2_path, _ = _write_stage2_fixture(base_dir / "stage2_fixture", avg_modularity=avg_modularity)
    stage3_path = stage3_dir / "segment3.json"
    stage3_cli.run_stage3(str(stage2_path), str(stage3_path), skip_llm=True)
    payload = json.loads(stage3_path.read_text(encoding="utf-8"))
    return stage3_path, Path(payload["artifacts"]["stage3_graph_db_copy"])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_stage4_skips_high_modularity_and_persists_placeholders(tmp_path: Path) -> None:
    stage3_path, _ = _write_stage3_fixture(tmp_path, avg_modularity=0.95)
    stage4_dir = tmp_path / "stage4_outputs"
    stage4_path = stage4_dir / "segment4.json"

    stage4_cli.run_stage4(str(stage3_path), str(stage4_path))

    payload = json.loads(stage4_path.read_text(encoding="utf-8"))
    assert payload["summary"]["community_llm_triggered"] is False
    assert payload["summary"]["community_llm_applied"] is False
    assert payload["summary"]["skipped_count"] == 2
    assert all(item["summary_status"] == "skipped" for item in payload["community_summaries"])

    stage4_db = stage4_dir / "graph.db"
    assert stage4_db.exists()
    with sqlite3.connect(str(stage4_db)) as connection:
        summary_count = connection.execute("SELECT COUNT(*) FROM community_summaries").fetchone()[0]
        history_statuses = connection.execute("SELECT DISTINCT status FROM community_summary_history ORDER BY status").fetchall()
        existing_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('partitions','optimization_history','community_summaries','community_summary_history')"
            )
        }
    assert summary_count == 2
    assert history_statuses == [("skipped",)]
    assert existing_tables == {"partitions", "optimization_history", "community_summaries", "community_summary_history"}


def test_run_stage4_force_env_invokes_llm_and_persists_rows(tmp_path: Path, monkeypatch) -> None:
    stage3_path, stage3_graph_db_copy = _write_stage3_fixture(tmp_path, avg_modularity=0.95)
    stage4_path = tmp_path / "segment4_force.json"

    class DummyHelper:
        class config:
            model = "fake-model"

    monkeypatch.setenv("FH_FORCE_COMMUNITY_LLM", "1")
    monkeypatch.setattr(stage4_cli, "has_deepseek_config", lambda: True)
    monkeypatch.setattr(stage4_cli, "get_deepseek_settings", lambda: {"api_key": "fake", "base_url": "https://example.com", "model": "fake-model"})
    monkeypatch.setattr(stage4_cli, "build_llm_helper", lambda settings: DummyHelper())
    monkeypatch.setattr(
        stage4_cli,
        "summarize_partition_with_llm",
        lambda helper, community_context: {
            "label": f"Summary for {community_context['partition_id']}",
            "description": "This community coordinates fixture methods and downstream dependencies.",
            "functional_domain": "fixture-domain",
            "key_concepts": ["fixture", "summary"],
            "top_files": community_context["top_files"],
            "top_dependencies": community_context["top_dependencies"],
            "duration_ms": 12,
        },
    )

    stage4_cli.run_stage4(str(stage3_path), str(stage4_path), force=None, graph_db_path=str(stage3_graph_db_copy))

    payload = json.loads(stage4_path.read_text(encoding="utf-8"))
    assert payload["summary"]["community_llm_triggered"] is True
    assert payload["summary"]["community_llm_applied"] is True
    assert payload["summary"]["completed_count"] == 2
    assert all(item["summary_status"] == "completed" for item in payload["community_summaries"])

    with sqlite3.connect(str(stage3_graph_db_copy)) as connection:
        summary_rows = connection.execute("SELECT COUNT(*) FROM community_summaries WHERE status='completed'").fetchone()[0]
        history_rows = connection.execute("SELECT COUNT(*) FROM community_summary_history WHERE status='completed'").fetchone()[0]
    assert summary_rows == 2
    assert history_rows == 2


def test_run_stage4_skip_llm_overrides_force(tmp_path: Path, monkeypatch) -> None:
    stage3_path, _ = _write_stage3_fixture(tmp_path, avg_modularity=0.1)
    stage4_path = tmp_path / "segment4_skip.json"

    def _fail(*args, **kwargs):
        raise AssertionError("LLM should not run when --skip-llm is set")

    monkeypatch.setattr(stage4_cli, "summarize_partition_with_llm", _fail)
    stage4_cli.run_stage4(str(stage3_path), str(stage4_path), force=True, skip_llm=True)

    payload = json.loads(stage4_path.read_text(encoding="utf-8"))
    assert payload["summary"]["community_llm_triggered"] is False
    assert payload["summary"]["skipped_count"] == 2


def test_run_stage4_missing_config_marks_error_rows(tmp_path: Path, monkeypatch) -> None:
    stage3_path, _ = _write_stage3_fixture(tmp_path, avg_modularity=0.1)
    stage4_path = tmp_path / "segment4_missing_config.json"

    monkeypatch.setattr(stage4_cli, "has_deepseek_config", lambda: False)
    monkeypatch.setattr(stage4_cli, "get_deepseek_settings", lambda: {"api_key": "", "base_url": "", "model": ""})

    stage4_cli.run_stage4(str(stage3_path), str(stage4_path), force=True)

    payload = json.loads(stage4_path.read_text(encoding="utf-8"))
    assert payload["summary"]["error_count"] == 2
    assert all(item["summary_status"] == "error" for item in payload["community_summaries"])


def test_run_stage4_skip_llm_output_is_deterministic(tmp_path: Path) -> None:
    stage3_path, stage3_graph_db_copy = _write_stage3_fixture(tmp_path, avg_modularity=0.95)
    stage4_path = tmp_path / "segment4_deterministic.json"

    stage4_cli.run_stage4(str(stage3_path), str(stage4_path), skip_llm=True, graph_db_path=str(stage3_graph_db_copy))
    first_hash = _sha256(stage4_path)

    stage4_cli.run_stage4(str(stage3_path), str(stage4_path), skip_llm=True, graph_db_path=str(stage3_graph_db_copy))
    second_hash = _sha256(stage4_path)

    assert first_hash == second_hash


def test_run_stage4_loads_stage1_from_sibling_output_root(tmp_path: Path) -> None:
    stage3_path, stage3_graph_db_copy = _write_stage3_fixture(tmp_path, avg_modularity=0.95)
    stage4_path = tmp_path / "segment4_sibling_stage1.json"

    stage4_cli.run_stage4(str(stage3_path), str(stage4_path), skip_llm=True, graph_db_path=str(stage3_graph_db_copy))

    payload = json.loads(stage4_path.read_text(encoding="utf-8"))
    assert any(item.get("top_files") for item in payload["community_summaries"])


def test_run_stage4_falls_back_to_project_library_graph_db_when_stage3_copy_missing(tmp_path: Path) -> None:
    stage3_path, stage3_graph_db_copy = _write_stage3_fixture(tmp_path, avg_modularity=0.95)
    stage3_payload = json.loads(stage3_path.read_text(encoding="utf-8"))
    stage2_graph_db = Path(stage3_payload["artifacts"]["graph_db_path"])
    project_graph_db = ProjectLibraryStorage().graph_db_path("D:/fixture/project")
    project_graph_db.parent.mkdir(parents=True, exist_ok=True)
    project_graph_db.write_bytes(stage3_graph_db_copy.read_bytes())
    stage3_graph_db_copy.unlink()
    if stage2_graph_db.exists():
        stage2_graph_db.unlink()

    stage4_path = tmp_path / "segment4_fallback.json"
    stage4_cli.run_stage4(str(stage3_path), str(stage4_path), skip_llm=True)

    stage4_payload = json.loads(stage4_path.read_text(encoding="utf-8"))
    assert stage4_payload["artifacts"]["source_graph_db_path"].replace("\\", "/") == str(project_graph_db).replace("\\", "/")


def test_load_stage4_community_summaries_reads_rows(tmp_path: Path) -> None:
    stage3_path, stage3_graph_db_copy = _write_stage3_fixture(tmp_path, avg_modularity=0.95)
    stage4_path = tmp_path / "segment4_read_rows.json"

    stage4_cli.run_stage4(str(stage3_path), str(stage4_path), skip_llm=True, graph_db_path=str(stage3_graph_db_copy))
    rows = load_stage4_community_summaries(str(stage3_graph_db_copy), source_project_path="D:/fixture/project")

    assert len(rows) == 2
    assert rows[0]["summary_status"] == "skipped"


def test_build_phase6_read_contract_exposes_stage4_semantics(tmp_path: Path) -> None:
    stage3_path, stage3_graph_db_copy = _write_stage3_fixture(tmp_path, avg_modularity=0.95)
    stage4_path = tmp_path / "segment4_contract.json"

    stage4_cli.run_stage4(str(stage3_path), str(stage4_path), skip_llm=True, graph_db_path=str(stage3_graph_db_copy))

    hierarchy_cached = {
        "hierarchy": {
            "layer1_functions": [
                {
                    "partition_id": "partition_0",
                    "name": "p0",
                    "methods": ["A.a1", "B.b1"],
                }
            ]
        },
        "partition_analyses": {
            "partition_0": {
                "entry_points": [],
                "entry_points_shadow": {"effective_entries": []},
                "path_analyses": [],
            }
        },
        "community_shadow": {
            "communities": [
                {
                    "partition_id": "partition_0",
                    "methods": ["A.a1", "B.b1"],
                    "label": "Community Shadow 1",
                }
            ]
        },
        "process_shadow": {"processes": []},
    }

    contract = analysis_service._build_phase6_read_contract("D:/fixture/project", hierarchy_cached)
    assert contract is not None

    partition_summary = contract["adapters"]["partition_summaries"][0]
    assert partition_summary["description"] == "skip_llm flag enabled"
    assert partition_summary["community_summary_status"] == "skipped"
    enriched_community = contract["shadow_results"]["community"]["communities"][0]
    assert enriched_community["community_semantics"]["summary_status"] == "skipped"


def test_project_library_storage_default_root_is_cwd_independent(tmp_path: Path, monkeypatch) -> None:
    original_cwd = Path.cwd()
    try:
        monkeypatch.chdir(tmp_path)
        from data.project_library_storage import ProjectLibraryStorage as FreshProjectLibraryStorage

        storage = FreshProjectLibraryStorage()
        expected_root = (PROJECT_ROOT / "output_analysis" / "project_library").resolve()

        assert storage.storage_dir == expected_root
        assert storage.graph_db_path("D:/fixture/project") == expected_root / "project_151004ae6ad8" / "graph.db"
    finally:
        os.chdir(original_cwd)


def test_python_m_segment_4_community_semantics_succeeds(tmp_path: Path) -> None:
    stage3_path, stage3_graph_db_copy = _write_stage3_fixture(tmp_path, avg_modularity=0.95)
    stage4_path = tmp_path / "segment4_cli.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "segment_4_community_semantics",
            "--input",
            str(stage3_path),
            "--output",
            str(stage4_path),
            "--graph-db",
            str(stage3_graph_db_copy),
            "--skip-llm",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert stage4_path.exists()
