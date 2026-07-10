from __future__ import annotations

from pathlib import Path
from typing import Any

from formal_data.loaders.core import collect_row_fields, iter_jsonl, ok_inspection, require_fields, sha256_stream, validate_inspector


DATASET = "crosscodeeval"
REQUIRED_FIELDS = {"prompt", "groundtruth", "metadata.task_id"}
VARIANTS = (
    "raw",
    "oracle_bm25",
    "oracle_openai_cosine_sim",
    "oracle_unixcoder_cosine_sim",
    "rg1_bm25",
    "rg1_openai_cosine_sim",
    "rg1_unixcoder_cosine_sim",
)


def variant_from_filename(path: Path) -> str:
    stem = path.name.lower()
    for variant in VARIANTS:
        if variant in stem:
            return variant
    return "raw"


def inspect_crosscodeeval(path: str | Path) -> dict[str, Any]:
    path_obj = Path(path)
    variant = variant_from_filename(path_obj)
    rows = 0
    context_list_rows = 0
    context_text_rows = 0
    context_dict_rows = 0
    observed_fields: set[str] = set()
    for line_number, row in iter_jsonl(path_obj):
        require_fields(row, REQUIRED_FIELDS, f"line {line_number}")
        observed_fields.update(collect_row_fields(row))
        context = row.get("crossfile_context")
        if isinstance(context, dict):
            context_dict_rows += 1
            if variant != "raw":
                require_fields(context, {"list", "text"}, f"line {line_number}.crossfile_context")
            if isinstance(context.get("list"), list):
                context_list_rows += 1
            if isinstance(context.get("text"), str):
                context_text_rows += 1
        elif context is not None and variant != "raw":
            from formal_data.loaders.core import PartialDataError

            raise PartialDataError(
                "CrossCodeEval context variants require crossfile_context object with list and text keys",
                evidence={"line": line_number, "variant": variant},
            )
        elif isinstance(context, list):
            context_list_rows += 1
        elif isinstance(context, str):
            context_text_rows += 1
        rows += 1
    if rows == 0:
        from formal_data.loaders.core import PartialDataError

        raise PartialDataError("CrossCodeEval JSONL contains no rows")
    return ok_inspection(
        DATASET,
        path_obj,
        counts={
            "rows": rows,
            "context_dict_rows": context_dict_rows,
            "context_list_rows": context_list_rows,
            "context_text_rows": context_text_rows,
        },
        fields={"required": REQUIRED_FIELDS, "observed": observed_fields},
        gold={"groundtruth": "present", "has_gold": True},
        readiness={"sha256": sha256_stream(path_obj), "variant": variant, "model_free": True},
    )


def validate_crosscodeeval(path: str | Path) -> dict[str, Any]:
    return validate_inspector(DATASET, path, lambda path_obj: inspect_crosscodeeval(path_obj))
