from __future__ import annotations

from pathlib import Path
from typing import Any

from formal_data.loaders.core import iter_parquet_rows, ok_inspection, parquet_metadata, sha256_stream, validate_inspector


DATASET = "swe_bench_verified"
REQUIRED_FIELDS = {
    "repo", "instance_id", "base_commit", "patch", "test_patch", "problem_statement", "version",
    "FAIL_TO_PASS", "PASS_TO_PASS", "environment_setup_commit", "difficulty",
}


def inspect_swe_bench_verified(path: str | Path, expected_count: int = 500) -> dict[str, Any]:
    path_obj = Path(path)
    fields, rows, row_groups = parquet_metadata(path_obj)
    missing = sorted(REQUIRED_FIELDS - set(fields))
    errors: dict[str, Any] = {}
    if missing:
        errors["missing"] = missing
    if rows != expected_count:
        errors["expected_count"] = expected_count
        errors["actual_count"] = rows
    if errors:
        from formal_data.loaders.core import PartialDataError

        raise PartialDataError("SWE-bench Verified parquet does not match required metadata", evidence=errors)
    serialization_types = _sample_fail_pass_types(path_obj)
    return ok_inspection(
        DATASET,
        path_obj,
        counts={"rows": rows, "row_groups": row_groups, "expected_rows": expected_count},
        fields={"required": REQUIRED_FIELDS, "observed": fields},
        gold={
            "FAIL_TO_PASS": "present",
            "PASS_TO_PASS": "present",
            "serialization_types": serialization_types,
            "has_gold": True,
        },
        readiness={
            "sha256": sha256_stream(path_obj),
            "metadata_ready": True,
            "docker_ready": False,
            "harness_ready": False,
            "model_free": True,
        },
    )


def validate_swe_bench_verified(path: str | Path, expected_count: int = 500) -> dict[str, Any]:
    return validate_inspector(DATASET, path, lambda path_obj: inspect_swe_bench_verified(path_obj, expected_count=expected_count))


def _sample_fail_pass_types(path: Path) -> dict[str, list[str]]:
    observed = {"FAIL_TO_PASS": set[str](), "PASS_TO_PASS": set[str]()}
    for index, row in enumerate(iter_parquet_rows(path, columns=("FAIL_TO_PASS", "PASS_TO_PASS"), batch_size=16)):
        for field in observed:
            observed[field].add(type(row.get(field)).__name__)
        if index >= 15:
            break
    return {field: sorted(types) for field, types in observed.items()}
