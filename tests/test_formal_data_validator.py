from __future__ import annotations

import json
import sys
from pathlib import Path

import formal_data.validate_server_data as validator
from pytest import MonkeyPatch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from formal_data.loaders.core import MissingDataError
from formal_data.validate_server_data import (
    _compare_file_inventory,
    _crosscodeeval_expected_rows,
    _run_loader_plan,
    build_loader_plan,
    dataset_index,
    parse_checksum_ledger,
    validate_server_data,
)


def test_parse_checksum_ledger_reads_expected_mapping(tmp_path: Path) -> None:
    ledger_path = tmp_path / "checksums.sha256"
    ledger_path.write_text(
        "abc123  /opt/forge_flow/database/a.txt\n"
        "def456  /opt/forge_flow/database/b.txt\n",
        encoding="utf-8",
    )

    parsed = parse_checksum_ledger(ledger_path)

    assert parsed == {
        "/opt/forge_flow/database/a.txt": "abc123",
        "/opt/forge_flow/database/b.txt": "def456",
    }


def test_build_loader_plan_selects_only_applicable_real_assets() -> None:
    manifest = json.loads((PROJECT_ROOT / "formal_data" / "dataset_manifest.json").read_text(encoding="utf-8"))

    plan = build_loader_plan(manifest)

    assert len(plan) == 53
    plan_paths = [item["path"] for item in plan]
    assert "/opt/forge_flow/database/repoqa-2024-06-23.json.gz" in plan_paths
    assert "/opt/forge_flow/database/repoqa_data/repoqa-2024-06-23.json" not in plan_paths
    assert "/opt/forge_flow/database/RepoEval/datasets.zip" in plan_paths
    assert "/opt/forge_flow/database/RepoEval/line_and_api_level.zip" not in plan_paths
    assert "/opt/forge_flow/database/RepoEval/function_level.zip" not in plan_paths
    assert "/opt/forge_flow/database/SWE-bench_Verified/eval.yaml" not in plan_paths


def test_dataset_index_exposes_expected_manifest_keys() -> None:
    manifest = json.loads((PROJECT_ROOT / "formal_data" / "dataset_manifest.json").read_text(encoding="utf-8"))

    indexed = dataset_index(manifest)

    assert indexed["repoqa"]["readiness"] == "PROTOCOL_READY"
    assert indexed["codesearchnet"]["counts"]["test_total"] == 100529
    assert indexed["swe_bench_verified"]["counts"]["verified_parquet_rows"] == 500


def test_crosscodeeval_expected_rows_accepts_windows_paths() -> None:
    manifest = json.loads((PROJECT_ROOT / "formal_data" / "dataset_manifest.json").read_text(encoding="utf-8"))
    dataset = dataset_index(manifest)["crosscodeeval"]

    assert _crosscodeeval_expected_rows(dataset, r"C:\data\crosscodeeval\python\line_completion.jsonl") == 2665
    assert _crosscodeeval_expected_rows(dataset, r"C:\data\crosscodeeval\typescript\line_completion.jsonl") == 3356


def test_loader_plan_records_structured_exceptions() -> None:
    def fail_loader(path: str) -> dict[str, object]:
        raise MissingDataError(f"missing: {path}")

    failures: list[dict[str, object]] = []
    plan = [{"dataset": "repoqa", "path": "/missing.json", "inspector": fail_loader, "kwargs": {}}]

    results = _run_loader_plan(plan, {"datasets": []}, failures)

    assert results[0]["status"] == "missing"
    assert failures[0]["scope"] == "loader_exception"
    actual = failures[0]["actual"]
    assert isinstance(actual, dict)
    assert actual["code"] == "missing"


def test_loader_plan_records_structured_non_ok_results() -> None:
    def missing_loader(path: str) -> dict[str, object]:
        return {"status": "missing", "path": path, "counts": {}, "readiness": {}}

    failures: list[dict[str, object]] = []
    plan = [{"dataset": "repoqa", "path": "/missing.json", "inspector": missing_loader, "kwargs": {}}]

    results = _run_loader_plan(plan, {"datasets": []}, failures)

    assert results[0]["status"] == "missing"
    assert failures == [
        {"scope": "loader_status", "id": "/missing.json", "expected": "ok", "actual": "missing"}
    ]


def test_inventory_counts_only_fully_verified_files(tmp_path: Path) -> None:
    path = tmp_path / "asset.txt"
    path.write_text("actual", encoding="utf-8")
    manifest = {
        "datasets": [
            {
                "id": "fixture",
                "files": [
                    {
                        "path": str(path),
                        "byte_size": path.stat().st_size,
                        "sha256": "0" * 64,
                    }
                ],
            }
        ]
    }

    failures, verified = _compare_file_inventory(manifest, {str(path): "1" * 64})

    assert verified == []
    assert {failure["scope"] for failure in failures} == {"manifest_sha256", "ledger_sha256"}


def test_inventory_failure_stops_before_loader_deserialization(monkeypatch: MonkeyPatch) -> None:
    manifest = {
        "raw_root": "/data",
        "evidence_timestamp": "2026-07-10T00:00:00+08:00",
        "overall_stage1_status": "READY_FOR_STAGE2",
        "datasets": [],
    }

    monkeypatch.setattr(validator, "load_manifest", lambda: manifest)
    monkeypatch.setattr(validator, "parse_checksum_ledger", lambda: {})
    monkeypatch.setattr(validator, "_compare_file_inventory", lambda _manifest, _ledger: ([{"scope": "manifest_sha256"}], []))

    def fail_if_called(_manifest: object) -> list[dict[str, object]]:
        raise AssertionError("loader plan must not be built after an inventory failure")

    monkeypatch.setattr(validator, "build_loader_plan", fail_if_called)

    summary = validate_server_data()

    assert summary["ok"] is False
    assert summary["loader_run_count"] == 0
