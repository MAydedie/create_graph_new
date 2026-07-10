from __future__ import annotations

from pathlib import Path
from typing import Any

from formal_data.loaders.core import collect_row_fields, iter_zip_gzip_jsonl_rows, ok_inspection, require_fields, sha256_stream, validate_inspector


DATASET = "codesearchnet"
REQUIRED_ROW_FIELDS = {"code", "docstring", "func_name", "language", "repo", "sha", "path", "url"}


def inspect_codesearchnet(path: str | Path) -> dict[str, Any]:
    path_obj = Path(path)
    member_counts: dict[str, int] = {}
    languages: set[str] = set()
    repos: set[str] = set()
    observed_fields: set[str] = set()
    total = 0

    for name, line_number, row in iter_zip_gzip_jsonl_rows(path_obj, suffixes=(".jsonl.gz",)):
        normalized = name.replace("\\", "/")
        if "/final/jsonl/test/" not in f"/{normalized}":
            continue
        require_fields(row, REQUIRED_ROW_FIELDS, f"{name}:{line_number}")
        observed_fields.update(collect_row_fields(row))
        languages.add(str(row["language"]))
        repos.add(str(row["repo"]))
        member_counts[name] = member_counts.get(name, 0) + 1
        total += 1

    if not member_counts:
        from formal_data.loaders.core import MissingDataError

        raise MissingDataError("CodeSearchNet ZIP has no nested final/jsonl/test/*.jsonl.gz members")

    return ok_inspection(
        DATASET,
        path_obj,
        counts={"test_rows": total, "members": len(member_counts), "languages": len(languages), "repos": len(repos)},
        fields={"required": REQUIRED_ROW_FIELDS, "observed": observed_fields},
        gold={
            "pair_target": "docstring",
            "pair_target_rows": total,
            "official_relevance_gold": False,
            "has_official_gold": False,
        },
        readiness={"sha256": sha256_stream(path_obj), "split": "test", "member_counts": member_counts, "model_free": True},
    )


def validate_codesearchnet(path: str | Path) -> dict[str, Any]:
    return validate_inspector(DATASET, path, lambda path_obj: inspect_codesearchnet(path_obj))
