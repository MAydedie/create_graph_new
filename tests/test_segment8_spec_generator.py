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

from segment_8_spec_generator import spec_generator as stage8_spec
from tests.test_segment7_graph_query import _write_stage6_fixture


SECTION_KEYS = {
    "overview",
    "partition_architecture",
    "core_call_chains",
    "module_list",
    "design_patterns",
    "api_routes",
    "readme_summary",
    "experience_stats",
}


def _run_fixture_stage8(tmp_path: Path, *, skip_llm: bool = True, template_path: Path | None = None) -> tuple[Path, Path, Path, Path]:
    segment6_path, graph_db_path = _write_stage6_fixture(tmp_path)
    output_path = tmp_path / "stage8_outputs" / "spec_fixture.md"
    spec_json_path = tmp_path / "stage8_outputs" / "spec_fixture.json"
    raw_path = tmp_path / "stage8_outputs" / "raw_graph_query_results.json"
    stage8_spec.run_stage8(
        graph_db_path=str(graph_db_path),
        segment6_json_path=str(segment6_path),
        project_path=str(tmp_path),
        output_path=str(output_path),
        spec_json_path=str(spec_json_path),
        raw_results_path=str(raw_path),
        template_path=str(template_path) if template_path else None,
        skip_llm=skip_llm,
        max_paths=3,
    )
    return output_path, spec_json_path, raw_path, graph_db_path


def test_skip_llm_spec_has_all_8_sections_on_fixture(tmp_path: Path) -> None:
    output_path, spec_json_path, raw_path, _ = _run_fixture_stage8(tmp_path, skip_llm=True)

    spec = json.loads(spec_json_path.read_text(encoding="utf-8"))
    markdown = output_path.read_text(encoding="utf-8")

    assert output_path.exists() and output_path.stat().st_size > 0
    assert raw_path.exists() and raw_path.stat().st_size > 0
    assert spec["version"] == "2.0"
    assert set(spec["sections"].keys()) == SECTION_KEYS
    assert all(spec["sections"][key] for key in SECTION_KEYS)
    for title in ["项目概览", "功能架构", "核心调用链", "模块清单", "设计模式", "API 路由", "README 摘要", "经验库统计"]:
        assert title in markdown


def test_core_call_chain_path_ids_exist_in_graph_db(tmp_path: Path) -> None:
    _, spec_json_path, _, graph_db_path = _run_fixture_stage8(tmp_path, skip_llm=True)
    spec = json.loads(spec_json_path.read_text(encoding="utf-8"))

    with sqlite3.connect(str(graph_db_path)) as connection:
        real_path_ids = {row[0] for row in connection.execute("SELECT path_id FROM paths")}

    for path in spec["core_call_chain_evidence"]:
        assert path["path_id"] in real_path_ids
    assert spec["unverified_claims"] == []


def test_core_call_chain_requires_exact_candidate_path_id(tmp_path: Path, monkeypatch) -> None:
    segment6_path, graph_db_path = _write_stage6_fixture(tmp_path)
    output_path = tmp_path / "stage8_exact_path" / "spec.md"
    spec_json_path = tmp_path / "stage8_exact_path" / "spec.json"

    def wrong_persisted_path(_graph_db_path: str, src_qn: str, dst_qn: str, max_depth: int = 8):
        return [
            {
                "found": True,
                "path_id": "partition_0_1",
                "partition_id": "partition_0",
                "function_chain": [src_qn, dst_qn],
            }
        ]

    monkeypatch.setattr("segment_8_spec_generator.graph_collector.find_paths_between", wrong_persisted_path)
    stage8_spec.run_stage8(
        graph_db_path=str(graph_db_path),
        segment6_json_path=str(segment6_path),
        project_path=str(tmp_path),
        output_path=str(output_path),
        spec_json_path=str(spec_json_path),
        skip_llm=True,
        max_paths=1,
    )

    spec = json.loads(spec_json_path.read_text(encoding="utf-8"))
    requirement = spec["raw_graph_query_results"]["core_path_requirement"]
    assert spec["status"] == "partial"
    assert requirement["requested"] == 1
    assert requirement["collected"] == 0
    assert any("core_call_chains collected 0 of 1" in error for error in spec["errors"])


def test_graph_query_coverage_maps_at_least_5_sections(tmp_path: Path) -> None:
    _, spec_json_path, raw_path, _ = _run_fixture_stage8(tmp_path, skip_llm=True)
    spec = json.loads(spec_json_path.read_text(encoding="utf-8"))
    raw = json.loads(raw_path.read_text(encoding="utf-8"))

    covered = [section for section, queries in spec["graph_section_map"].items() if queries]
    raw_query_names = {item["query_name"] for item in raw["queries"]}

    assert len(covered) >= 5
    assert set(raw["graph_queries_used"]) == raw_query_names
    assert set(spec["graph_queries_used"]).issubset(raw_query_names)


def test_query_failure_marks_spec_partial(tmp_path: Path, monkeypatch) -> None:
    segment6_path, graph_db_path = _write_stage6_fixture(tmp_path)
    output_path = tmp_path / "stage8_partial" / "spec.md"
    spec_json_path = tmp_path / "stage8_partial" / "spec.json"

    def failing_architecture(_graph_db_path: str, top_k: int = 5):
        raise RuntimeError("forced architecture failure")

    monkeypatch.setattr("segment_8_spec_generator.graph_collector.get_architecture", failing_architecture)
    stage8_spec.run_stage8(
        graph_db_path=str(graph_db_path),
        segment6_json_path=str(segment6_path),
        project_path=str(tmp_path),
        output_path=str(output_path),
        spec_json_path=str(spec_json_path),
        skip_llm=True,
    )

    spec = json.loads(spec_json_path.read_text(encoding="utf-8"))
    assert spec["status"] == "partial"
    assert any("forced architecture failure" in error for error in spec["errors"])


def test_run_id_includes_result_shaping_inputs(tmp_path: Path) -> None:
    segment6_path, graph_db_path = _write_stage6_fixture(tmp_path)
    first = stage8_spec.generate_spec(
        graph_db_path=str(graph_db_path),
        segment6_json_path=str(segment6_path),
        project_path=str(tmp_path),
        skip_llm=True,
        top_k=5,
        max_paths=3,
    )[0]
    second = stage8_spec.generate_spec(
        graph_db_path=str(graph_db_path),
        segment6_json_path=str(segment6_path),
        project_path=str(tmp_path),
        skip_llm=True,
        top_k=1,
        max_paths=1,
    )[0]

    assert first["generated_at"] != second["generated_at"]


def test_llm_unavailable_and_failure_do_not_crash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("segment_8_spec_generator.llm_renderer.has_deepseek_config", lambda: False)
    _, spec_json_path, _, _ = _run_fixture_stage8(tmp_path / "no_llm", skip_llm=False)
    no_llm_spec = json.loads(spec_json_path.read_text(encoding="utf-8"))
    assert no_llm_spec["llm_status"] == "skipped_no_llm_configured"
    assert no_llm_spec["status"] == "completed"

    def failing_renderer(sections, graph_context, *, skip_llm):
        return sections, "partial_llm_failed", "forced llm failure"

    monkeypatch.setattr(stage8_spec, "maybe_enrich_sections", failing_renderer)
    output_path, spec_json_path, _, _ = _run_fixture_stage8(tmp_path / "llm_fail", skip_llm=False)
    failed_spec = json.loads(spec_json_path.read_text(encoding="utf-8"))
    audit_path = output_path.parent / "logs" / "spec_generator_audit.jsonl"
    audit_rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert failed_spec["llm_status"] == "partial_llm_failed"
    assert failed_spec["status"] == "completed"
    assert "forced llm failure" in str(audit_rows[-1]["error"])


def test_missing_template_and_missing_graph_db_fallbacks(tmp_path: Path) -> None:
    missing_template = tmp_path / "missing_template.md"
    _, spec_json_path, _, _ = _run_fixture_stage8(tmp_path / "template", skip_llm=True, template_path=missing_template)
    spec = json.loads(spec_json_path.read_text(encoding="utf-8"))
    assert spec["template_used"] == "built_in_fallback"

    missing_output = tmp_path / "missing_db" / "spec.md"
    missing_spec = tmp_path / "missing_db" / "spec.json"
    missing_raw = tmp_path / "missing_db" / "raw_graph_query_results.json"
    stage8_spec.run_stage8(
        graph_db_path=str(tmp_path / "missing.db"),
        segment6_json_path=str(tmp_path / "missing_segment6.json"),
        project_path=str(tmp_path),
        output_path=str(missing_output),
        spec_json_path=str(missing_spec),
        raw_results_path=str(missing_raw),
        skip_llm=True,
    )
    partial = json.loads(missing_spec.read_text(encoding="utf-8"))
    assert partial["status"] == "partial"
    assert partial["errors"]
    assert missing_output.exists()


def test_python_m_segment_8_spec_generator_succeeds(tmp_path: Path) -> None:
    segment6_path, graph_db_path = _write_stage6_fixture(tmp_path)
    output_path = tmp_path / "stage8_cli" / "spec_cli.md"
    spec_json_path = tmp_path / "stage8_cli" / "spec_cli.json"
    raw_path = tmp_path / "stage8_cli" / "raw_graph_query_results.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "segment_8_spec_generator",
            "--graph-db",
            str(graph_db_path),
            "--segment6-json",
            str(segment6_path),
            "--project",
            str(tmp_path),
            "--output",
            str(output_path),
            "--spec-json",
            str(spec_json_path),
            "--raw-results",
            str(raw_path),
            "--skip-llm",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert output_path.exists()
    assert json.loads(spec_json_path.read_text(encoding="utf-8"))["version"] == "2.0"
