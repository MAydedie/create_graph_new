from __future__ import annotations

from pathlib import Path
from typing import Any

from formal_data.loaders.core import collect_row_fields, iter_jsonl, iter_parquet_rows, ok_inspection, parquet_metadata, require_fields, sha256_stream, validate_inspector


DATASET = "fea_bench"
BASE_FIELDS = {"instance_id", "repo", "base_commit", "FAIL_TO_PASS", "PASS_TO_PASS", "environment_setup_commit"}
PATCH_FIELDS = {"patch", "test_patch"}


def inspect_fea_bench(path: str | Path) -> dict[str, Any]:
    path_obj = Path(path)
    suffixes = path_obj.suffixes
    rows = 0
    observed_fields: set[str] = set()
    readiness_counts = {"patch_rows": 0, "test_patch_rows": 0, "environment_setup_commit_rows": 0}
    if suffixes[-1:] == [".parquet"]:
        fields, row_count, row_groups = parquet_metadata(path_obj)
        missing = sorted(BASE_FIELDS - set(fields))
        if missing:
            from formal_data.loaders.core import PartialDataError

            raise PartialDataError("FEA-Bench parquet missing required metadata fields", evidence={"missing": missing})
        rows = row_count
        observed_fields.update(fields)
        dataset_shape = "public_essential_parquet" if rows == 1401 else "parquet"
        row_groups_count = row_groups
    else:
        dataset_shape = "enriched_jsonl"
        row_groups_count = 0
        for line_number, row in iter_jsonl(path_obj):
            require_fields(row, BASE_FIELDS, f"line {line_number}")
            observed_fields.update(collect_row_fields(row))
            if row.get("patch"):
                readiness_counts["patch_rows"] += 1
            if row.get("test_patch"):
                readiness_counts["test_patch_rows"] += 1
            if row.get("environment_setup_commit"):
                readiness_counts["environment_setup_commit_rows"] += 1
            rows += 1
    if suffixes[-1:] == [".parquet"] and "environment_setup_commit" in observed_fields:
        columns = sorted((BASE_FIELDS | PATCH_FIELDS) & observed_fields)
        for row in iter_parquet_rows(path_obj, columns=columns):
            if row.get("patch"):
                readiness_counts["patch_rows"] += 1
            if row.get("test_patch"):
                readiness_counts["test_patch_rows"] += 1
            if row.get("environment_setup_commit"):
                readiness_counts["environment_setup_commit_rows"] += 1
    return ok_inspection(
        DATASET,
        path_obj,
        counts={"rows": rows, "row_groups": row_groups_count, **readiness_counts},
        fields={"required": BASE_FIELDS, "patch_readiness": PATCH_FIELDS, "observed": observed_fields},
        gold={"FAIL_TO_PASS": "present", "PASS_TO_PASS": "present", "has_gold": rows > 0},
        readiness={
            "sha256": sha256_stream(path_obj),
            "dataset_shape": dataset_shape,
            "metadata_ready": readiness_counts["environment_setup_commit_rows"] == rows and rows > 0,
            "patch_ready": readiness_counts["patch_rows"] == rows and rows > 0,
            "test_patch_ready": readiness_counts["test_patch_rows"] == rows and rows > 0,
            "repository_checkout_ready": False,
            "test_environment_ready": False,
            "model_free": True,
        },
    )


def validate_fea_bench(path: str | Path) -> dict[str, Any]:
    return validate_inspector(DATASET, path, lambda path_obj: inspect_fea_bench(path_obj))
