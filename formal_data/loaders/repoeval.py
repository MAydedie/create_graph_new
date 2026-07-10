from __future__ import annotations

from pathlib import Path
from typing import Any

from formal_data.loaders.core import collect_row_fields, iter_zip_jsonl_rows, ok_inspection, require_fields, sha256_stream, validate_inspector


DATASET = "repoeval"
BASE_REQUIRED = {"prompt", "metadata.task_id", "metadata.ground_truth", "metadata.fpath_tuple", "metadata.context_start_lineno"}


def _kind_from_name(name: str) -> str:
    lower = name.lower()
    if "api" in lower:
        return "api"
    if "function" in lower:
        return "function"
    return "line"


def _require_kind_fields(row: dict[str, Any], kind: str, location: str) -> None:
    if kind == "function":
        require_fields(row, {"metadata.lineno", "metadata.function_name"}, location)
    elif kind == "line":
        require_fields(row, {"metadata.line_no"}, location)


def inspect_repoeval(path: str | Path) -> dict[str, Any]:
    path_obj = Path(path)
    counts = {"members": 0, "rows": 0, "line_rows": 0, "api_rows": 0, "function_rows": 0}
    member_counts: dict[str, int] = {}
    observed_fields: set[str] = set()
    for name, line_number, row in iter_zip_jsonl_rows(path_obj, suffixes=(".jsonl",)):
        kind = _kind_from_name(name)
        require_fields(row, BASE_REQUIRED, f"{name}:{line_number}")
        _require_kind_fields(row, kind, f"{name}:{line_number}")
        observed_fields.update(collect_row_fields(row))
        counts[f"{kind}_rows"] += 1
        counts["rows"] += 1
        member_counts[name] = member_counts.get(name, 0) + 1
    counts["members"] = len(member_counts)
    if counts["members"] == 0:
        from formal_data.loaders.core import MissingDataError

        raise MissingDataError("RepoEval datasets.zip has no JSONL members")
    return ok_inspection(
        DATASET,
        path_obj,
        counts=counts,
        fields={"required": BASE_REQUIRED | {"metadata.line_no|metadata.lineno|metadata.function_name"}, "observed": observed_fields},
        gold={"metadata.ground_truth": "present", "has_gold": counts["rows"] > 0},
        readiness={"sha256": sha256_stream(path_obj), "member_counts": member_counts, "extracted": False, "model_free": True},
    )


def validate_repoeval(path: str | Path) -> dict[str, Any]:
    return validate_inspector(DATASET, path, lambda path_obj: inspect_repoeval(path_obj))
