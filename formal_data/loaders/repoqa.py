from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from formal_data.loaders.core import collect_row_fields, load_json_object, ok_inspection, require_fields, sha256_stream, validate_inspector


DATASET = "repoqa"
REQUIRED_ROW_FIELDS = {"repo", "commit_sha", "content", "functions", "needles"}


def inspect_repoqa(path: str | Path) -> dict[str, Any]:
    path_obj = Path(path)
    payload = load_json_object(path_obj)
    language_counts: dict[str, int] = {}
    repos: set[str] = set()
    sample_count = 0
    needle_count = 0
    gold_rows = 0
    observed_fields: set[str] = set()

    # RepoQA is a top-level language mapping, so full JSON load is required before row traversal.
    for language, rows in sorted(payload.items()):
        if not isinstance(rows, list):
            from formal_data.loaders.core import MalformedDataError

            raise MalformedDataError(f"RepoQA language bucket must be a list: {language}")
        language_counts[str(language)] = len(rows)
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                from formal_data.loaders.core import MalformedDataError

                raise MalformedDataError(f"RepoQA row must be an object: {language}[{index}]")
            require_fields(row, REQUIRED_ROW_FIELDS, f"{language}[{index}]")
            observed_fields.update(collect_row_fields(row))
            repos.add(str(row["repo"]))
            sample_count += 1
            needles = row["needles"]
            if isinstance(needles, list):
                needle_count += len(needles)
                if needles:
                    gold_rows += 1

    return ok_inspection(
        DATASET,
        path_obj,
        counts={"languages": len(language_counts), "repos": len(repos), "samples": sample_count, "needles": needle_count},
        fields={"required": REQUIRED_ROW_FIELDS, "observed": observed_fields},
        gold={"needle_gold_rows": gold_rows, "has_needle_gold": gold_rows == sample_count and sample_count > 0},
        readiness={"sha256": sha256_stream(path_obj), "language_counts": language_counts, "model_free": True},
    )


def validate_repoqa(path: str | Path) -> dict[str, Any]:
    return validate_inspector(DATASET, path, lambda path_obj: inspect_repoqa(path_obj))
