from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from formal_data.loaders.core import collect_row_fields, load_trusted_gzip_pickle, ok_inspection, require_fields, sha256_stream, validate_inspector


DATASET = "repobench_r"
REQUIRED_ROW_FIELDS = {"repo_name", "file_path", "context", "import_statement", "code", "next_line"}
LEVELS = ("easy", "hard")
SPLITS = ("train", "test")


def inspect_repobench_r(path: str | Path) -> dict[str, Any]:
    path_obj = Path(path)
    payload = load_trusted_gzip_pickle(path_obj)
    if not isinstance(payload, Mapping):
        from formal_data.loaders.core import MalformedDataError

        raise MalformedDataError("RepoBench-R pickle must contain a mapping")

    counts: dict[str, int] = {}
    observed_fields: set[str] = set()
    normalized_gold = 0
    rows_total = 0
    # Trusted RepoBench-R pickle is loaded fully because pickle is not stream-safe.
    for split in SPLITS:
        split_payload = payload.get(split)
        if not isinstance(split_payload, Mapping):
            from formal_data.loaders.core import PartialDataError

            raise PartialDataError(f"RepoBench-R missing split mapping: {split}")
        for level in LEVELS:
            rows = split_payload.get(level)
            if not isinstance(rows, list):
                from formal_data.loaders.core import PartialDataError

                raise PartialDataError(f"RepoBench-R missing level list: {split}.{level}")
            counts[f"{split}_{level}_rows"] = len(rows)
            rows_total += len(rows)
            for index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    from formal_data.loaders.core import MalformedDataError

                    raise MalformedDataError(f"RepoBench-R row must be an object: {split}.{level}[{index}]")
                require_fields(row, REQUIRED_ROW_FIELDS, f"{split}.{level}[{index}]")
                observed_fields.update(collect_row_fields(row))
                if "gold_snippet_index" in row or "golden_snippet_index" in row:
                    normalized_gold += 1

    counts["rows"] = rows_total
    return ok_inspection(
        DATASET,
        path_obj,
        counts=counts,
        fields={"required": REQUIRED_ROW_FIELDS | {"gold_snippet_index"}, "observed": observed_fields},
        gold={"gold_snippet_index_rows": normalized_gold, "accepts_source_typo": True, "has_gold": normalized_gold == rows_total and rows_total > 0},
        readiness={"sha256": sha256_stream(path_obj), "trusted_local_pickle": True, "model_free": True},
    )


def validate_repobench_r(path: str | Path) -> dict[str, Any]:
    return validate_inspector(DATASET, path, lambda path_obj: inspect_repobench_r(path_obj))
