from __future__ import annotations

from pathlib import Path
from typing import Any

from formal_data.loaders.core import ok_inspection, parquet_metadata, sha256_stream, validate_inspector


DATASET = "repobench_v11"
REQUIRED_FIELDS = {
    "repo_name", "file_path", "context", "import_statement", "token_num", "cropped_code",
    "all_code", "next_line", "gold_snippet_index", "created_at", "level",
}


def inspect_repobench_v11(path: str | Path) -> dict[str, Any]:
    path_obj = Path(path)
    fields, rows, row_groups = parquet_metadata(path_obj)
    missing = sorted(REQUIRED_FIELDS - set(fields))
    if missing:
        from formal_data.loaders.core import PartialDataError

        raise PartialDataError("RepoBench v1.1 parquet missing required fields", evidence={"missing": missing})
    return ok_inspection(
        DATASET,
        path_obj,
        counts={"rows": rows, "row_groups": row_groups, "shards": 1},
        fields={"required": REQUIRED_FIELDS, "observed": fields},
        gold={"gold_snippet_index": "present", "has_gold": rows > 0},
        readiness={"sha256": sha256_stream(path_obj), "metadata_only": True, "model_free": True},
    )


def validate_repobench_v11(path: str | Path) -> dict[str, Any]:
    return validate_inspector(DATASET, path, lambda path_obj: inspect_repobench_v11(path_obj))
