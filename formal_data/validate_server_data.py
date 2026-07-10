from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from formal_data.loaders.core import FormalDataError
from formal_data.loaders.codesearchnet import inspect_codesearchnet
from formal_data.loaders.crosscodeeval import inspect_crosscodeeval
from formal_data.loaders.fea_bench import inspect_fea_bench
from formal_data.loaders.repobench_r import inspect_repobench_r
from formal_data.loaders.repobench_v11 import inspect_repobench_v11
from formal_data.loaders.repoeval import inspect_repoeval
from formal_data.loaders.repoqa import inspect_repoqa
from formal_data.loaders.swe_bench_verified import inspect_swe_bench_verified


PACKAGE_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = PACKAGE_ROOT / "dataset_manifest.json"
CHECKSUM_PATH = PACKAGE_ROOT / "checksums.sha256"

READINESS_INDEX = {
    "NOT_PROVIDED": 0,
    "PRESENT": 1,
    "FORMAT_VERIFIED": 2,
    "LOADER_READY": 3,
    "GOLD_READY": 4,
    "PROTOCOL_READY": 5,
}


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a JSON object")
    return payload


def parse_checksum_ledger(path: Path = CHECKSUM_PATH) -> dict[str, str]:
    ledger: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, asset_path = line.split("  ", 1)
        ledger[asset_path] = digest
    return ledger


def dataset_index(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list):
        raise ValueError("manifest datasets must be a list")
    return {str(dataset["id"]): dataset for dataset in datasets if isinstance(dataset, dict)}


def build_loader_plan(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    indexed = dataset_index(manifest)
    plan: list[dict[str, Any]] = []

    def dataset_files(dataset_id: str) -> list[dict[str, Any]]:
        return list(indexed[dataset_id]["files"])

    repoqa_gz = next(file_record for file_record in dataset_files("repoqa") if str(file_record["path"]).endswith(".json.gz"))
    plan.append({"dataset": "repoqa", "path": repoqa_gz["path"], "inspector": inspect_repoqa, "kwargs": {}})

    for file_record in dataset_files("codesearchnet"):
        plan.append({"dataset": "codesearchnet", "path": file_record["path"], "inspector": inspect_codesearchnet, "kwargs": {}})

    for file_record in dataset_files("repobench_r"):
        plan.append({"dataset": "repobench_r", "path": file_record["path"], "inspector": inspect_repobench_r, "kwargs": {}})

    for file_record in dataset_files("repobench_v11"):
        plan.append({"dataset": "repobench_v11", "path": file_record["path"], "inspector": inspect_repobench_v11, "kwargs": {}})

    for file_record in dataset_files("crosscodeeval"):
        plan.append({"dataset": "crosscodeeval", "path": file_record["path"], "inspector": inspect_crosscodeeval, "kwargs": {}})

    repoeval_zip = next(file_record for file_record in dataset_files("repoeval") if str(file_record["path"]).endswith("datasets.zip"))
    plan.append({"dataset": "repoeval", "path": repoeval_zip["path"], "inspector": inspect_repoeval, "kwargs": {}})

    for file_record in dataset_files("fea_bench"):
        plan.append({"dataset": "fea_bench", "path": file_record["path"], "inspector": inspect_fea_bench, "kwargs": {}})

    swe_parquet = next(file_record for file_record in dataset_files("swe_bench_verified") if str(file_record["path"]).endswith(".parquet"))
    plan.append({"dataset": "swe_bench_verified", "path": swe_parquet["path"], "inspector": inspect_swe_bench_verified, "kwargs": {"expected_count": 500}})

    return plan


def _record_failure(failures: list[dict[str, Any]], scope: str, identifier: str, expected: Any, actual: Any) -> None:
    failures.append({"scope": scope, "id": identifier, "expected": expected, "actual": actual})


def _compare_file_inventory(manifest: dict[str, Any], ledger: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    for dataset in manifest["datasets"]:
        for file_record in dataset["files"]:
            path = Path(str(file_record["path"]))
            file_ok = True
            if not path.is_file():
                _record_failure(failures, "file_exists", str(path), True, False)
                continue
            actual_size = path.stat().st_size
            if actual_size != int(file_record["byte_size"]):
                _record_failure(failures, "byte_size", str(path), int(file_record["byte_size"]), actual_size)
                file_ok = False
            actual_hash = _sha256_stream(path)
            if actual_hash != str(file_record["sha256"]):
                _record_failure(failures, "manifest_sha256", str(path), str(file_record["sha256"]), actual_hash)
                file_ok = False
            if ledger.get(str(path)) != str(file_record["sha256"]):
                _record_failure(failures, "ledger_sha256", str(path), str(file_record["sha256"]), ledger.get(str(path)))
                file_ok = False
            if file_ok:
                verified.append({"dataset": dataset["id"], "path": str(path), "byte_size": actual_size, "sha256": actual_hash})
    return failures, verified


def _sha256_stream(path: Path, chunk_size: int = 1024 * 1024) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_split(dataset_id: str) -> dict[str, Any]:
    path = PACKAGE_ROOT / "splits" / f"{dataset_id}_splits.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"split file for {dataset_id} must be a JSON object")
    return payload


def _validate_loader_result(plan_item: dict[str, Any], inspection: dict[str, Any], manifest: dict[str, Any], failures: list[dict[str, Any]]) -> dict[str, Any]:
    dataset_id = str(plan_item["dataset"])
    path = str(plan_item["path"])
    if inspection["status"] != "ok":
        _record_failure(failures, "loader_status", path, "ok", inspection["status"])
        return {
            "dataset": dataset_id,
            "path": path,
            "status": inspection["status"],
            "counts": inspection.get("counts", {}),
            "readiness": inspection.get("readiness", {}),
        }
    indexed = dataset_index(manifest)
    dataset = indexed[dataset_id]
    expected_readiness = str(dataset["readiness"])
    split_payload = _load_split(dataset_id)
    if dataset_id == "repoqa":
        _compare_simple(failures, path, inspection["counts"]["languages"], dataset["counts"]["local_languages"], "repoqa_languages")
        _compare_simple(failures, path, inspection["counts"]["repos"], dataset["counts"]["local_repos_total"], "repoqa_repos")
        _compare_simple(failures, path, inspection["counts"]["needles"], dataset["counts"]["local_needles_total"], "repoqa_needles")
        _compare_simple(failures, path, inspection["counts"]["samples"], dataset["counts"]["local_repos_total"], "repoqa_samples")
    elif dataset_id == "codesearchnet":
        language = Path(path).stem.lower()
        key = f"{language}_test"
        _compare_simple(failures, path, inspection["counts"]["test_rows"], dataset["counts"][key], key)
    elif dataset_id == "repobench_r":
        name = Path(path).stem.replace(".pkl", "")
        if name.endswith("_cff"):
            expected_rows = 64000
            easy_train = 24000
            hard_train = 24000
            easy_test = 8000
            hard_test = 8000
        else:
            expected_rows = 32000
            easy_train = 12000
            hard_train = 12000
            easy_test = 4000
            hard_test = 4000
        _compare_simple(failures, path, inspection["counts"]["rows"], expected_rows, "repobench_r_rows")
        _compare_simple(failures, path, inspection["counts"]["train_easy_rows"], easy_train, "repobench_r_train_easy")
        _compare_simple(failures, path, inspection["counts"]["train_hard_rows"], hard_train, "repobench_r_train_hard")
        _compare_simple(failures, path, inspection["counts"]["test_easy_rows"], easy_test, "repobench_r_test_easy")
        _compare_simple(failures, path, inspection["counts"]["test_hard_rows"], hard_test, "repobench_r_test_hard")
    elif dataset_id == "repobench_v11":
        expected = _repobench_v11_expected_rows(dataset, path)
        _compare_simple(failures, path, inspection["counts"]["rows"], expected, "repobench_v11_rows")
    elif dataset_id == "crosscodeeval":
        expected = _crosscodeeval_expected_rows(dataset, path)
        _compare_simple(failures, path, inspection["counts"]["rows"], expected, "crosscodeeval_rows")
    elif dataset_id == "repoeval":
        _compare_simple(failures, path, inspection["counts"]["line_rows"], dataset["counts"]["line_rows_total"], "repoeval_line_rows")
        _compare_simple(failures, path, inspection["counts"]["api_rows"], dataset["counts"]["api_rows_total"], "repoeval_api_rows")
        _compare_simple(failures, path, inspection["counts"]["function_rows"], dataset["counts"]["function_rows_total"], "repoeval_function_rows")
        expected_members = [member for unit in split_payload["formal_units"] for member in unit["members"]]
        actual_members = sorted(inspection["readiness"]["member_counts"])
        if actual_members != sorted(expected_members):
            _record_failure(failures, "repoeval_members", path, sorted(expected_members), actual_members)
        for unit in split_payload["formal_units"]:
            for member in unit["members"]:
                actual = inspection["readiness"]["member_counts"].get(member)
                expected_rows = unit["rows_per_member"]
                _compare_simple(failures, f"{path}:{member}", actual, expected_rows, "repoeval_member_rows")
    elif dataset_id == "fea_bench":
        suffix = Path(path).suffix.lower()
        if suffix == ".parquet":
            _compare_simple(failures, path, inspection["counts"]["rows"], dataset["counts"]["public_parquet_metadata_rows"], "fea_public_rows")
        else:
            _compare_simple(failures, path, inspection["counts"]["rows"], dataset["counts"]["medium_jsonl_enriched_rows"], "fea_enriched_rows")
    elif dataset_id == "swe_bench_verified":
        _compare_simple(failures, path, inspection["counts"]["rows"], dataset["counts"]["verified_parquet_rows"], "swe_rows")
    if READINESS_INDEX[expected_readiness] < READINESS_INDEX["LOADER_READY"]:
        _record_failure(failures, "dataset_readiness", dataset_id, ">= LOADER_READY", expected_readiness)
    return {"dataset": dataset_id, "path": path, "status": inspection["status"], "counts": inspection["counts"], "readiness": inspection["readiness"]}


def _compare_simple(failures: list[dict[str, Any]], identifier: str, actual: Any, expected: Any, scope: str) -> None:
    if actual != expected:
        _record_failure(failures, scope, identifier, expected, actual)


def _repobench_v11_expected_rows(dataset: dict[str, Any], path: str) -> int:
    lower = path.lower()
    counts = dataset["counts"]
    if "repobench_python_v1.1" in lower and "cross_file_first" in lower:
        return counts["python_cff_shards"][0] if "00000-of-00002" in lower else counts["python_cff_shards"][1]
    if "repobench_python_v1.1" in lower and "cross_file_random" in lower:
        return counts["python_cfr"]
    if "repobench_python_v1.1" in lower and "in_file" in lower:
        return counts["python_in_file"]
    if "repobench_java_v1.1" in lower and "cross_file_first" in lower:
        return counts["java_cff_shards"][0] if "00000-of-00002" in lower else counts["java_cff_shards"][1]
    if "repobench_java_v1.1" in lower and "cross_file_random" in lower:
        return counts["java_cfr_shards"][0] if "00000-of-00002" in lower else counts["java_cfr_shards"][1]
    if "repobench_java_v1.1" in lower and "in_file" in lower:
        return counts["java_in_file_shards"][0] if "00000-of-00002" in lower else counts["java_in_file_shards"][1]
    raise ValueError(f"unexpected RepoBench v1.1 shard path: {path}")


def _crosscodeeval_expected_rows(dataset: dict[str, Any], path: str) -> int:
    lower = path.replace("\\", "/").lower()
    counts = dataset["counts"]
    if "/typescript/" in lower:
        return counts["typescript_each_variant"]
    if "/java/" in lower:
        return counts["java_each_variant"]
    if "/python/" in lower:
        return counts["python_each_variant"]
    if lower.endswith("oracle_openai_cosine_sim.jsonl") or lower.endswith("rg1_openai_cosine_sim.jsonl"):
        return counts["csharp_rows"][Path(path).stem.removeprefix("line_completion_")]
    return counts["csharp_rows"]["default"]


def _validate_policy_artifacts(
    manifest: dict[str, Any], failures: list[dict[str, Any]], package_root: Path = PACKAGE_ROOT
) -> int:
    verified = 0
    for dataset in manifest["datasets"]:
        split_path = package_root / str(dataset["split_file"])
        try:
            split_payload = json.loads(split_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _record_failure(failures, "split_parse", str(split_path), "valid JSON", str(exc))
            continue
        if split_payload.get("dataset") != dataset["id"]:
            _record_failure(failures, "split_dataset", str(split_path), dataset["id"], split_payload.get("dataset"))
            continue
        units = split_payload.get("formal_units")
        if not isinstance(units, list):
            _record_failure(failures, "split_units", str(split_path), "list", type(units).__name__)
            continue
        unit_ids = [str(unit.get("id")) for unit in units if isinstance(unit, dict)]
        if len(unit_ids) != len(units) or len(unit_ids) != len(set(unit_ids)):
            _record_failure(failures, "split_unit_ids", str(split_path), "unique object IDs", unit_ids)
            continue
        excluded_ids = {
            str(unit["id"])
            for unit in units
            if isinstance(unit, dict) and unit.get("formal") is False
        }
        declared_excluded_ids = {
            str(unit_id)
            for exclusion in dataset["exclusions"]
            for unit_id in exclusion.get("split_unit_ids", [])
        }
        if excluded_ids != declared_excluded_ids:
            _record_failure(
                failures,
                "split_exclusions",
                str(split_path),
                sorted(declared_excluded_ids),
                sorted(excluded_ids),
            )
        for exclusion in dataset["exclusions"]:
            if exclusion.get("formal") is not False:
                _record_failure(failures, "manifest_exclusion", str(exclusion.get("id")), False, exclusion.get("formal"))
        dataset_readiness = str(dataset["readiness"])
        for unit in units:
            if not isinstance(unit, dict):
                continue
            unit_readiness = str(unit.get("readiness"))
            if unit_readiness not in READINESS_INDEX:
                _record_failure(failures, "split_readiness", str(unit.get("id")), "known readiness", unit_readiness)
                continue
            if READINESS_INDEX[unit_readiness] > READINESS_INDEX[dataset_readiness]:
                _record_failure(failures, "split_readiness", str(unit.get("id")), f"<= {dataset_readiness}", unit_readiness)
            if unit.get("formal") is True and READINESS_INDEX[unit_readiness] < READINESS_INDEX["GOLD_READY"]:
                _record_failure(failures, "formal_unit_readiness", str(unit.get("id")), ">= GOLD_READY", unit_readiness)
        verified += 1

    holdout_path = package_root / "holdout_repositories.json"
    queue_path = package_root / "annotation_queue_template.json"
    audit_path = package_root / "annotation_audit.jsonl"
    qa_path = package_root / "custom_qa.jsonl"
    c2_path = package_root / "custom_c2.jsonl"
    try:
        holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        audit_rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        qa_text = qa_path.read_text(encoding="utf-8")
        c2_text = c2_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        _record_failure(failures, "optional_artifacts", str(package_root), "parseable files", str(exc))
        return verified
    optional_checks = {
        "holdout_status": ("NOT_PROVIDED", holdout.get("status")),
        "holdout_optional": (True, holdout.get("optional")),
        "holdout_repositories": ([], holdout.get("repositories")),
        "custom_qa_empty": ("", qa_text),
        "custom_c2_empty": ("", c2_text),
        "annotation_audit_rows": (1, len(audit_rows)),
        "queue_status": ("TEMPLATE_ONLY", queue.get("status")),
        "queue_not_gold": (True, queue.get("template_not_gold")),
    }
    for check_id, (expected, actual) in optional_checks.items():
        if actual != expected:
            _record_failure(failures, "optional_artifacts", check_id, expected, actual)
    if len(audit_rows) == 1:
        audit = audit_rows[0]
        audit_checks = {
            "audit_status": ("NOT_PROVIDED", audit.get("status")),
            "audit_optional": (True, audit.get("optional")),
            "audit_human_reviewed": (False, audit.get("human_reviewed")),
            "audit_human_gold": (False, audit.get("human_gold")),
            "audit_qa_records": (0, audit.get("qa_records")),
            "audit_c2_records": (0, audit.get("c2_records")),
        }
        for check_id, (expected, actual) in audit_checks.items():
            if actual != expected:
                _record_failure(failures, "optional_artifacts", check_id, expected, actual)
    return verified + 5


def _run_loader_plan(
    plan: list[dict[str, Any]], manifest: dict[str, Any], failures: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for plan_item in plan:
        try:
            inspection = plan_item["inspector"](plan_item["path"], **plan_item["kwargs"])
        except FormalDataError as exc:
            _record_failure(failures, "loader_exception", str(plan_item["path"]), "ok", exc.as_error())
            results.append(
                {
                    "dataset": str(plan_item["dataset"]),
                    "path": str(plan_item["path"]),
                    "status": exc.code,
                    "counts": {},
                    "readiness": {},
                }
            )
            continue
        except Exception as exc:
            actual = {"type": type(exc).__name__, "message": str(exc)}
            _record_failure(failures, "loader_exception", str(plan_item["path"]), "ok", actual)
            results.append(
                {
                    "dataset": str(plan_item["dataset"]),
                    "path": str(plan_item["path"]),
                    "status": "unexpected_error",
                    "counts": {},
                    "readiness": {},
                }
            )
            continue
        results.append(_validate_loader_result(plan_item, inspection, manifest, failures))
    return results


def validate_server_data() -> dict[str, Any]:
    manifest = load_manifest()
    ledger = parse_checksum_ledger()
    failures: list[dict[str, Any]] = []
    policy_artifact_count = _validate_policy_artifacts(manifest, failures)
    inventory_failures, verified_files = _compare_file_inventory(manifest, ledger)
    failures.extend(inventory_failures)
    loader_results = [] if failures else _run_loader_plan(build_loader_plan(manifest), manifest, failures)
    summary = {
        "manifest_path": str(MANIFEST_PATH),
        "checksum_path": str(CHECKSUM_PATH),
        "raw_root": manifest["raw_root"],
        "evidence_timestamp": manifest["evidence_timestamp"],
        "overall_stage1_status": manifest["overall_stage1_status"],
        "verified_file_count": len(verified_files),
        "loader_run_count": len(loader_results),
        "policy_artifact_count": policy_artifact_count,
        "failures": failures,
        "ok": not failures,
    }
    return summary


def main() -> int:
    summary = validate_server_data()
    sys.stdout.write(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
