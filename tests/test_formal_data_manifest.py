from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


FORMAL_DATA = PROJECT_ROOT / "formal_data"
MANIFEST_PATH = FORMAL_DATA / "dataset_manifest.json"
CHECKSUMS_PATH = FORMAL_DATA / "checksums.sha256"
SCHEMA_DIR = FORMAL_DATA / "schema"


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest() -> dict[str, object]:
    payload = _load_json(MANIFEST_PATH)
    assert isinstance(payload, dict)
    return payload


def _datasets() -> list[dict[str, object]]:
    datasets = _manifest()["datasets"]
    assert isinstance(datasets, list)
    return cast(list[dict[str, object]], datasets)


def _dataset_index() -> dict[str, dict[str, Any]]:
    return {str(dataset["id"]): cast(dict[str, Any], dataset) for dataset in _datasets()}


def _checksum_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in CHECKSUMS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, path = line.split("  ", 1)
        result[path] = digest
    return result


def test_manifest_has_all_expected_datasets_and_order() -> None:
    manifest = _manifest()
    assert manifest["model_network_benchmark_use"] == "NONE"
    assert manifest["overall_stage1_status"] == "READY_FOR_STAGE2"
    assert manifest["generated_by"] == "model_free_stage1_inventory"
    assert manifest["raw_root"] == "/opt/forge_flow/database"
    assert manifest["readiness_order"] == ["NOT_PROVIDED", "PRESENT", "FORMAT_VERIFIED", "LOADER_READY", "GOLD_READY", "PROTOCOL_READY"]
    dataset_ids = [dataset["id"] for dataset in _datasets()]
    assert dataset_ids == [
        "repoqa",
        "codesearchnet",
        "repobench_r",
        "repobench_v11",
        "crosscodeeval",
        "repoeval",
        "fea_bench",
        "swe_bench_verified",
    ]


def test_manifest_files_match_checksum_ledger_and_are_unique() -> None:
    checksum_map = _checksum_map()
    paths: set[str] = set()
    hashes: set[str] = set()
    for dataset in _datasets():
        files = dataset["files"]
        assert isinstance(files, list)
        for file_record in files:
            assert isinstance(file_record, dict)
            path = file_record["path"]
            sha256 = file_record["sha256"]
            assert path in checksum_map
            assert checksum_map[path] == sha256
            assert path not in paths
            assert sha256 not in hashes
            paths.add(path)
            hashes.add(sha256)


def test_manifest_schema_and_split_files_exist_and_are_consistent() -> None:
    for dataset in _datasets():
        schema_path = FORMAL_DATA / str(dataset["row_schema"])
        split_path = FORMAL_DATA / str(dataset["split_file"])
        assert schema_path.is_file(), schema_path
        assert split_path.is_file(), split_path
        split_payload = _load_json(split_path)
        assert isinstance(split_payload, dict)
        assert split_payload["dataset"] == dataset["id"]


def test_all_schemas_parse_and_declare_expected_required_fields() -> None:
    expected_required = {
        "manifest.schema.json": {"overall_stage1_status", "raw_root", "readiness_order", "datasets"},
        "repoqa_row.schema.json": {"repo", "commit_sha", "content", "functions", "needles"},
        "codesearchnet_row.schema.json": {"code", "docstring", "func_name", "language", "repo", "sha", "path", "url"},
        "repobench_r_row.schema.json": {"repo_name", "file_path", "context", "import_statement", "code", "next_line"},
        "repobench_v11_row.schema.json": {"repo_name", "file_path", "context", "token_num", "gold_snippet_index", "level"},
        "crosscodeeval_row.schema.json": {"prompt", "groundtruth", "metadata"},
        "repoeval_row.schema.json": {"prompt", "metadata"},
        "fea_bench_row.schema.json": {"instance_id", "repo", "base_commit", "FAIL_TO_PASS", "PASS_TO_PASS", "environment_setup_commit"},
        "swe_bench_verified_row.schema.json": {"repo", "instance_id", "base_commit", "patch", "test_patch"},
        "holdout.schema.json": {"status", "optional", "repositories", "activation_requirements"},
        "annotation_record.schema.json": {"record_id", "dataset", "repository", "commit_sha", "annotator_id", "human_reviewed", "template_not_gold"},
        "annotation_queue.schema.json": {"status", "template_not_gold", "qa_template", "c2_template"},
    }
    found = {path.name for path in SCHEMA_DIR.glob("*.json")}
    assert found == set(expected_required)
    for name, required_fields in expected_required.items():
        payload = _load_json(SCHEMA_DIR / name)
        assert isinstance(payload, dict)
        required = set(payload.get("required", []))
        assert required_fields <= required, name


def test_manifest_exact_required_counts_and_readiness() -> None:
    indexed = _dataset_index()
    assert indexed["repoqa"]["counts"]["official_subset_repos"] == 50
    assert indexed["repoqa"]["counts"]["official_subset_needles"] == 500
    assert indexed["repoqa"]["readiness"] == "PROTOCOL_READY"
    assert indexed["codesearchnet"]["counts"]["test_total"] == 100529
    assert indexed["codesearchnet"]["readiness"] == "LOADER_READY"
    assert indexed["repobench_r"]["counts"]["total_rows"] == 192000
    assert indexed["repobench_r"]["readiness"] == "PROTOCOL_READY"
    assert indexed["repobench_v11"]["counts"]["total_rows"] == 49684
    assert indexed["repobench_v11"]["readiness"] == "PROTOCOL_READY"
    assert indexed["crosscodeeval"]["counts"]["python_each_variant"] == 2665
    assert indexed["crosscodeeval"]["readiness"] == "PROTOCOL_READY"
    assert indexed["repoeval"]["counts"]["total_rows"] == 13710
    assert indexed["repoeval"]["readiness"] == "PROTOCOL_READY"
    assert indexed["fea_bench"]["counts"]["public_parquet_metadata_rows"] == 1401
    assert indexed["fea_bench"]["readiness"] == "LOADER_READY"
    assert indexed["swe_bench_verified"]["counts"]["verified_parquet_rows"] == 500
    assert indexed["swe_bench_verified"]["readiness"] == "GOLD_READY"
    assert indexed["repoqa"]["task_notes"].startswith("Search Needle Function")
    assert "Apache-2.0" in indexed["repoqa"]["license_notes"]
    assert "threshold 0.8" in indexed["repoqa"]["split_gold_metric_or_harness"]
    assert "MIT-licensed" in indexed["codesearchnet"]["license_notes"]
    assert "NDCG" in indexed["codesearchnet"]["split_gold_metric_or_harness"]


def test_repoeval_split_members_use_exact_dataset_member_names() -> None:
    split = _load_json(FORMAL_DATA / "splits/repoeval_splits.json")
    assert isinstance(split, dict)
    units = {unit["id"]: unit for unit in split["formal_units"]}
    assert units["line"]["members"] == [
        "line_level_completion_1k_context_codegen.test.jsonl",
        "line_level_completion_2k_context_codegen.test.jsonl",
        "line_level_completion_2k_context_codex.test.jsonl",
        "line_level_completion_4k_context_codex.test.jsonl",
    ]
    assert units["api"]["members"] == [
        "api_level_completion_1k_context_codegen.test.jsonl",
        "api_level_completion_2k_context_codegen.test.jsonl",
        "api_level_completion_2k_context_codex.test.jsonl",
        "api_level_completion_4k_context_codex.test.jsonl",
    ]
    assert units["function"]["members"] == [
        "function_level_completion_2k_context_codex.test.jsonl",
        "function_level_completion_4k_context_codex.test.jsonl",
    ]


def test_excluded_variants_are_not_formal() -> None:
    indexed = _dataset_index()
    cce_exclusions = indexed["crosscodeeval"]["exclusions"]
    assert {item["id"] for item in cce_exclusions} == {
        "crosscodeeval_csharp_oracle_openai_cosine_sim_short",
        "crosscodeeval_csharp_rg1_openai_cosine_sim_short",
    }
    assert all(item["formal"] is False for item in cce_exclusions)
    csn_exclusions = indexed["codesearchnet"]["exclusions"]
    assert csn_exclusions[0]["formal"] is False
