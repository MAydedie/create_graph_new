from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from formal_data.validate_server_data import build_loader_plan, dataset_index, parse_checksum_ledger


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
