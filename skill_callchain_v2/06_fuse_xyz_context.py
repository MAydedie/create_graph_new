from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable


BASE_DIR = Path(__file__).resolve().parent
if __package__ in {None, ""}:
    sys.path.insert(0, str(BASE_DIR.parent))
    _MODULE_PREFIX = "skill_callchain_v2"
else:
    _MODULE_PREFIX = __package__


def _load_attr(module_suffix: str, attr_name: str) -> Any:
    module = importlib.import_module(f"{_MODULE_PREFIX}.{module_suffix}")
    return getattr(module, attr_name)


ensure_runtime: Callable[[], Path] = _load_attr("common", "ensure_runtime")
print_output: Callable[[str, Path], None] = _load_attr("common", "print_output")
read_json: Callable[[Path], Any] = _load_attr("common", "read_json")
utc_now: Callable[[], str] = _load_attr("common", "utc_now")
write_json: Callable[[Path, Any], None] = _load_attr("common", "write_json")
STEP1_CLARIFIED_TASK_FILE: Path = _load_attr("config", "STEP1_CLARIFIED_TASK_FILE")


RUNTIME_DIR = BASE_DIR / "runtime"
STEP3_X_PATH_CONTEXT_FILE = RUNTIME_DIR / "step3_x_path_context.json"
STEP4_Y_SEMANTIC_CONTEXT_FILE = RUNTIME_DIR / "step4_y_semantic_context.json"
STEP5_Z_CODE_CONTEXT_FILE = RUNTIME_DIR / "step5_z_code_context.json"
STEP6_FUSED_CONTEXT_FILE = RUNTIME_DIR / "step6_fused_context.json"

SKILL_OBJECT_KEYS = (
    "recommended_skills",
    "selected_skills",
    "top_skills",
    "candidate_skills",
    "skill_candidates",
    "matched_skills",
    "skills",
)
SKILL_ID_KEYS = (
    "recommended_skill_ids",
    "selected_skill_ids",
    "top_skill_ids",
    "skill_ids",
)
SUMMARY_KEYS = (
    "summary",
    "context_summary",
    "analysis_summary",
    "path_summary",
    "semantic_summary",
    "code_summary",
    "overall_summary",
    "reason",
    "description",
)
CONTEXT_EXCLUDED_KEYS = {
    "version",
    "step",
    "generated_at",
    "created_at",
    "recommended_skills",
    "selected_skills",
    "top_skills",
    "candidate_skills",
    "skill_candidates",
    "matched_skills",
    "skills",
    "recommended_skill_ids",
    "selected_skill_ids",
    "top_skill_ids",
    "skill_ids",
    "shared_skill_ids",
    "next_stage_inputs",
}


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = _as_str(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return _dedupe_keep_order([_as_str(item) for item in value])
    if isinstance(value, tuple):
        return _dedupe_keep_order([_as_str(item) for item in value])
    normalized = _as_str(value)
    return [normalized] if normalized else []


def _read_required_payload(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(payload).__name__}.")
    return payload


def _extract_summary(payload: dict[str, Any]) -> str:
    for key in SUMMARY_KEYS:
        summary = _as_str(payload.get(key))
        if summary:
            return summary
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        for key in SUMMARY_KEYS:
            summary = _as_str(metadata.get(key))
            if summary:
                return summary
    return ""


def _normalize_skill_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        skill_id = _as_str(item)
        if not skill_id:
            return None
        return {
            "skill_id": skill_id,
            "name": skill_id,
            "summary": "",
            "score": 0.0,
            "reasons": [],
        }

    if not isinstance(item, dict):
        return None

    skill_id = _as_str(item.get("skill_id") or item.get("id") or item.get("skillId"))
    name = _as_str(item.get("name") or item.get("skill_name") or item.get("title") or skill_id)
    summary = _as_str(item.get("summary") or item.get("reason") or item.get("description"))
    reasons = _as_str_list(item.get("reasons"))
    single_reason = _as_str(item.get("reason"))
    if single_reason:
        reasons = _dedupe_keep_order(reasons + [single_reason])

    if not skill_id and not name:
        return None

    return {
        "skill_id": skill_id,
        "name": name,
        "summary": summary,
        "score": _as_float(
            item.get("score")
            or item.get("relevance")
            or item.get("confidence")
            or item.get("weight")
            or item.get("rank_score")
        ),
        "reasons": reasons,
    }


def _extract_recommended_skills(payload: dict[str, Any]) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []

    for key in SKILL_OBJECT_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                normalized = _normalize_skill_item(item)
                if normalized is not None:
                    skills.append(normalized)

    for key in SKILL_ID_KEYS:
        for skill_id in _as_str_list(payload.get(key)):
            skills.append(
                {
                    "skill_id": skill_id,
                    "name": skill_id,
                    "summary": "",
                    "score": 0.0,
                    "reasons": [],
                }
            )

    return skills


def _skill_merge_key(skill: dict[str, Any]) -> str:
    skill_id = _as_str(skill.get("skill_id"))
    if skill_id:
        return f"id:{skill_id.lower()}"
    name = _as_str(skill.get("name"))
    if name:
        return f"name:{name.lower()}"
    return ""


def _merge_recommended_skills(stage_skill_map: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for source_name in ("path", "semantic", "code"):
        for skill in stage_skill_map.get(source_name) or []:
            merge_key = _skill_merge_key(skill)
            if not merge_key:
                continue

            current = merged.get(merge_key)
            if current is None:
                current = {
                    "skill_id": _as_str(skill.get("skill_id")),
                    "name": _as_str(skill.get("name")),
                    "summary": _as_str(skill.get("summary")),
                    "selected_by": [],
                    "source_count": 0,
                    "max_score": 0.0,
                    "reasons": [],
                }
                merged[merge_key] = current

            if source_name not in current["selected_by"]:
                current["selected_by"].append(source_name)
                current["source_count"] = len(current["selected_by"])

            if not current["skill_id"]:
                current["skill_id"] = _as_str(skill.get("skill_id"))
            if not current["name"]:
                current["name"] = _as_str(skill.get("name"))
            if not current["summary"]:
                current["summary"] = _as_str(skill.get("summary"))

            current["max_score"] = max(current["max_score"], _as_float(skill.get("score")))
            current["reasons"] = _dedupe_keep_order(current["reasons"] + _as_str_list(skill.get("reasons")))

    merged_skills = list(merged.values())
    merged_skills.sort(
        key=lambda item: (
            -int(item.get("source_count") or 0),
            -float(item.get("max_score") or 0.0),
            _as_str(item.get("skill_id") or item.get("name")).lower(),
        )
    )
    return merged_skills


def _filter_context_payload(payload: dict[str, Any]) -> dict[str, Any]:
    filtered: dict[str, Any] = {}
    for key, value in payload.items():
        if key in CONTEXT_EXCLUDED_KEYS:
            continue
        if not _is_non_empty(value):
            continue
        filtered[key] = value
    return filtered


def _normalize_task_summary(payload: dict[str, Any]) -> dict[str, Any]:
    structured_requirement = payload.get("structured_requirement")
    structured_requirement = structured_requirement if isinstance(structured_requirement, dict) else {}
    domain_constraints = _as_str_list(structured_requirement.get("domain_constraints") or structured_requirement.get("constraints"))
    pipeline_constraints = _as_str_list(structured_requirement.get("pipeline_constraints"))
    return {
        "source_file": str(STEP1_CLARIFIED_TASK_FILE),
        "raw_task": _as_str(payload.get("raw_task")),
        "route": _as_str(payload.get("route")),
        "task_mode": _as_str(payload.get("task_mode")),
        "goal": _as_str(structured_requirement.get("goal")),
        "target": _as_str(structured_requirement.get("target")),
        "expected_output": _as_str(structured_requirement.get("expected_output")),
        "constraints": domain_constraints,
        "pipeline_constraints": pipeline_constraints,
        "ready_for_next_step": bool(payload.get("ready_for_next_step")),
    }


def _normalize_stage_context(
    stage_name: str,
    source_file: Path,
    payload: dict[str, Any],
    recommended_skills: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "source_file": str(source_file),
        "step": _as_str(payload.get("step")) or stage_name,
        "generated_at": _as_str(payload.get("generated_at") or payload.get("created_at")),
        "summary": _extract_summary(payload),
        "recommended_skill_ids": _dedupe_keep_order([_as_str(item.get("skill_id")) for item in recommended_skills]),
        "context": _filter_context_payload(payload),
    }


def build_fused_payload(
    clarified_task: dict[str, Any],
    path_payload: dict[str, Any],
    semantic_payload: dict[str, Any],
    code_payload: dict[str, Any],
) -> dict[str, Any]:
    task_summary = _normalize_task_summary(clarified_task)

    stage_skill_map = {
        "path": _extract_recommended_skills(path_payload),
        "semantic": _extract_recommended_skills(semantic_payload),
        "code": _extract_recommended_skills(code_payload),
    }
    recommended_skills = _merge_recommended_skills(stage_skill_map)

    path_context = _normalize_stage_context("x_path_context", STEP3_X_PATH_CONTEXT_FILE, path_payload, stage_skill_map["path"])
    semantic_context = _normalize_stage_context(
        "y_semantic_context",
        STEP4_Y_SEMANTIC_CONTEXT_FILE,
        semantic_payload,
        stage_skill_map["semantic"],
    )
    code_context = _normalize_stage_context("z_code_context", STEP5_Z_CODE_CONTEXT_FILE, code_payload, stage_skill_map["code"])

    shared_skill_ids = sorted(
        {
            _as_str(item.get("skill_id"))
            for item in recommended_skills
            if int(item.get("source_count") or 0) >= 2 and _as_str(item.get("skill_id"))
        }
    )
    recommended_skill_ids = [
        _as_str(item.get("skill_id"))
        for item in recommended_skills
        if _as_str(item.get("skill_id"))
    ]

    return {
        "version": "v2.work_order_c",
        "step": "fuse_xyz_context",
        "generated_at": utc_now(),
        "task_summary": task_summary,
        "recommended_skills": recommended_skills,
        "path_context": path_context,
        "semantic_context": semantic_context,
        "code_context": code_context,
        "shared_skill_ids": shared_skill_ids,
        "next_stage_inputs": {
            "task_summary": {
                "goal": task_summary.get("goal") or "",
                "target": task_summary.get("target") or "",
                "expected_output": task_summary.get("expected_output") or "",
                "constraints": task_summary.get("constraints") or [],
            },
            "recommended_skill_ids": recommended_skill_ids,
            "shared_skill_ids": shared_skill_ids,
            "path_summary": path_context.get("summary") or "",
            "semantic_summary": semantic_context.get("summary") or "",
            "code_summary": code_context.get("summary") or "",
        },
    }


def main() -> None:
    ensure_runtime()
    clarified_task = _read_required_payload(STEP1_CLARIFIED_TASK_FILE)
    path_payload = _read_required_payload(STEP3_X_PATH_CONTEXT_FILE)
    semantic_payload = _read_required_payload(STEP4_Y_SEMANTIC_CONTEXT_FILE)
    code_payload = _read_required_payload(STEP5_Z_CODE_CONTEXT_FILE)

    fused_payload = build_fused_payload(clarified_task, path_payload, semantic_payload, code_payload)
    write_json(STEP6_FUSED_CONTEXT_FILE, fused_payload)
    print_output("step6 完成", STEP6_FUSED_CONTEXT_FILE)


if __name__ == "__main__":
    main()
