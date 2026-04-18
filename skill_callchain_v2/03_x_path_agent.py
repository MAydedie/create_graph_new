from __future__ import annotations

import importlib
import re
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


def _load_optional_attr(module_suffix: str, attr_name: str, default: Any) -> Any:
    try:
        module = importlib.import_module(f"{_MODULE_PREFIX}.{module_suffix}")
    except Exception:
        return default
    return getattr(module, attr_name, default)


ensure_runtime: Callable[[], Path] = _load_attr("common", "ensure_runtime")
print_output: Callable[[str, Path], None] = _load_attr("common", "print_output")
read_json: Callable[[Path], Any] = _load_attr("common", "read_json")
utc_now: Callable[[], str] = _load_attr("common", "utc_now")
write_json: Callable[[Path, Any], None] = _load_attr("common", "write_json")
GENERATED_SKILLS_FILE: Path = _load_attr("config", "GENERATED_SKILLS_FILE")
RUNTIME_DIR: Path = _load_attr("config", "RUNTIME_DIR")
STEP1_CLARIFIED_TASK_FILE: Path = _load_attr("config", "STEP1_CLARIFIED_TASK_FILE")
XYZ_TOP_N: int = int(_load_optional_attr("config", "XYZ_TOP_N", 5) or 5)
STEP3_X_PATH_CONTEXT_FILE = RUNTIME_DIR / "step3_x_path_context.json"

REQUIREMENT_FIELD_WEIGHTS = {
    "goal": 3.0,
    "target": 2.0,
    "expected_output": 3.0,
    "constraints": 1.5,
}

SKILL_FIELD_WEIGHTS = {
    "name": 2.5,
    "tags": 2.0,
    "what": 2.5,
    "summary": 2.0,
    "how": 1.5,
    "path_summaries": 2.0,
}

EN_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "that",
    "this",
    "when",
    "then",
    "step",
    "path",
    "skill",
    "runtime",
    "json",
    "file",
    "files",
    "error",
    "gate",
    "demand",
    "finalize",
}

CN_STOPWORDS = {
    "包含",
    "需求比对",
    "双检测",
    "中间文件",
    "落盘",
    "导出",
    "目录",
    "约束",
    "指标",
}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            normalized = _stringify(item)
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result
    return []


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _tokenize_text(text: str) -> list[str]:
    normalized = _stringify(text).lower()
    if not normalized:
        return []

    seen: set[str] = set()
    result: list[str] = []

    for token in re.findall(r"[a-z0-9_]{2,}", normalized):
        if token in EN_STOPWORDS:
            continue
        if token not in seen:
            seen.add(token)
            result.append(token)

    for segment in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
        if segment in CN_STOPWORDS:
            continue
        if segment not in seen:
            seen.add(segment)
            result.append(segment)
        if len(segment) > 2:
            for index in range(len(segment) - 1):
                bigram = segment[index : index + 2]
                if bigram in CN_STOPWORDS:
                    continue
                if bigram not in seen:
                    seen.add(bigram)
                    result.append(bigram)
    return result


def _extract_requirement_fields(step1_payload: dict[str, Any]) -> dict[str, list[str]]:
    structured_requirement = step1_payload.get("structured_requirement") or {}
    goal = _stringify(structured_requirement.get("goal") or step1_payload.get("inferred_intent") or step1_payload.get("raw_task"))
    target = _stringify(structured_requirement.get("target"))
    expected_output = _stringify(structured_requirement.get("expected_output"))
    constraints = _string_list(structured_requirement.get("domain_constraints") or structured_requirement.get("constraints"))

    return {
        "goal": [goal] if goal else [],
        "target": [target] if target else [],
        "expected_output": [expected_output] if expected_output else [],
        "constraints": constraints,
    }


def _path_evidence_list(skill_payload: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in skill_payload.get("path_evidence") or []:
        if isinstance(item, dict):
            result.append(item)
    result.sort(
        key=lambda item: (
            -_safe_float(item.get("worthiness_score")),
            _stringify(item.get("path_id")),
            _stringify(item.get("path_name")),
        )
    )
    return result


def _skill_text_fields(skill_payload: dict[str, Any]) -> dict[str, str]:
    path_summaries: list[str] = []
    for item in _path_evidence_list(skill_payload):
        parts = [
            _stringify(item.get("path_name")),
            _stringify(item.get("summary") or item.get("path_description")),
            " ".join(_string_list(item.get("function_chain"))),
            _stringify(item.get("leaf_node")),
        ]
        text = " ".join(part for part in parts if part)
        if text:
            path_summaries.append(text)

    method_call_chain = _string_list(skill_payload.get("method_call_chain"))
    retrieval_hints = skill_payload.get("retrieval_hints") or {}
    preferred_symbols = _string_list(retrieval_hints.get("preferred_symbols"))
    preferred_paths = _string_list(retrieval_hints.get("preferred_paths"))

    return {
        "name": " ".join(
            part
            for part in [
                _stringify(skill_payload.get("name")),
                _stringify(skill_payload.get("partition_name")),
            ]
            if part
        ),
        "tags": " ".join(_string_list(skill_payload.get("tags"))),
        "what": " ".join(method_call_chain[:5]),
        "summary": " ".join(preferred_symbols[:5] + preferred_paths[:3]),
        "how": _stringify(skill_payload.get("how")),
        "path_summaries": " ".join(path_summaries),
    }


def _best_overlap(requirement_text: str, skill_text_fields: dict[str, str]) -> dict[str, Any]:
    requirement_tokens = set(_tokenize_text(requirement_text))
    best = {
        "skill_field": "",
        "score": 0.0,
        "matched_terms": [],
        "coverage": 0.0,
    }
    if not requirement_tokens:
        return best

    for skill_field_name, skill_text in skill_text_fields.items():
        skill_tokens = set(_tokenize_text(skill_text))
        matched_terms = sorted(requirement_tokens & skill_tokens)
        if not matched_terms:
            continue
        coverage = len(matched_terms) / len(requirement_tokens)
        raw_score = (len(matched_terms) + coverage) * SKILL_FIELD_WEIGHTS[skill_field_name]
        if raw_score > best["score"]:
            best = {
                "skill_field": skill_field_name,
                "score": raw_score,
                "matched_terms": matched_terms,
                "coverage": coverage,
            }
    return best


def _score_skill(skill_payload: dict[str, Any], requirement_fields: dict[str, list[str]]) -> dict[str, Any]:
    skill_text_fields = _skill_text_fields(skill_payload)
    per_field_matches: list[dict[str, Any]] = []
    matched_requirement_fields: list[str] = []
    matched_terms: list[str] = []
    total_score = 0.0

    for field_name, texts in requirement_fields.items():
        field_weight = REQUIREMENT_FIELD_WEIGHTS[field_name]
        for text in texts:
            overlap = _best_overlap(text, skill_text_fields)
            if overlap["score"] <= 0:
                continue
            weighted_score = overlap["score"] * field_weight
            total_score += weighted_score
            matched_requirement_fields.append(field_name)
            matched_terms.extend(overlap["matched_terms"])
            per_field_matches.append(
                {
                    "requirement_field": field_name,
                    "requirement_text": text,
                    "matched_skill_field": overlap["skill_field"],
                    "matched_terms": overlap["matched_terms"],
                    "coverage": round(overlap["coverage"], 4),
                    "weighted_score": round(weighted_score, 4),
                }
            )

    deduped_requirement_fields = []
    seen_fields: set[str] = set()
    for item in matched_requirement_fields:
        if item not in seen_fields:
            seen_fields.add(item)
            deduped_requirement_fields.append(item)

    deduped_terms = []
    seen_terms: set[str] = set()
    for item in matched_terms:
        if item not in seen_terms:
            seen_terms.add(item)
            deduped_terms.append(item)

    path_items = _path_evidence_list(skill_payload)
    return {
        "score": round(total_score, 4),
        "matched_requirement_fields": deduped_requirement_fields,
        "matched_terms": deduped_terms,
        "per_field_matches": per_field_matches,
        "path_count": len(path_items),
        "best_path_score": round(max((_safe_float(item.get("worthiness_score")) for item in path_items), default=0.0), 4),
    }


def _select_paths(skill_payload: dict[str, Any], max_paths: int = 2) -> list[dict[str, Any]]:
    selected_paths: list[dict[str, Any]] = []
    for item in _path_evidence_list(skill_payload)[:max_paths]:
        selected_paths.append(
            {
                "path_id": _stringify(item.get("path_id")),
                "path_name": _stringify(item.get("path_name")),
                "summary": _stringify(item.get("summary") or item.get("path_description")),
                "function_chain": _string_list(item.get("function_chain")),
                "leaf_node": _stringify(item.get("leaf_node")),
                "worthiness_score": round(_safe_float(item.get("worthiness_score")), 4),
                "selection_policy": _stringify(item.get("selection_policy") or item.get("path_type")),
                "deep_analysis_status": _stringify(item.get("deep_analysis_status") or item.get("path_type")),
                "source": _stringify(item.get("source")),
            }
        )
    return selected_paths


def _select_skills(skills_report: dict[str, Any], requirement_fields: dict[str, list[str]], top_n: int) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    all_skills = [item for item in (skills_report.get("skills") or []) if isinstance(item, dict)]
    candidate_skills = [item for item in all_skills if bool(item.get("usable_for_matching", True))]
    if not candidate_skills:
        candidate_skills = all_skills

    for skill in candidate_skills:
        if not isinstance(skill, dict):
            continue
        score_info = _score_skill(skill, requirement_fields)
        ranked.append(
            {
                "skill": skill,
                "score_info": score_info,
            }
        )

    ranked.sort(
        key=lambda item: (
            -item["score_info"]["score"],
            -item["score_info"]["path_count"],
            -item["score_info"]["best_path_score"],
            _stringify(item["skill"].get("partition_id")),
            _stringify(item["skill"].get("name")),
        )
    )

    selected: list[dict[str, Any]] = []
    for rank, item in enumerate(ranked[: max(top_n, 1)], start=1):
        skill = item["skill"]
        score_info = item["score_info"]
        selected.append(
            {
                "rank": rank,
                "skill_id": _stringify(skill.get("skill_id")),
                "name": _stringify(skill.get("name")),
                "partition_id": _stringify(skill.get("partition_id")),
                "partition_name": _stringify(skill.get("partition_name") or skill.get("name")),
                "summary": _stringify(skill.get("summary") or skill.get("what")),
                "what": " -> ".join(_string_list(skill.get("method_call_chain"))[:4]),
                "how": _stringify(skill.get("how")),
                "tags": _string_list(skill.get("tags")),
                "methods": _string_list(skill.get("methods")),
                "score": score_info["score"],
                "matched_requirement_fields": score_info["matched_requirement_fields"],
                "matched_terms": score_info["matched_terms"],
                "overlap_details": score_info["per_field_matches"],
                "path_count": score_info["path_count"],
                "best_path_score": score_info["best_path_score"],
                "selected_paths": _select_paths(skill),
            }
        )
    return selected


def _build_function_chain_groups(selected_skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for skill in selected_skills:
        chains = []
        for path in skill.get("selected_paths") or []:
            function_chain = _string_list(path.get("function_chain"))
            if not function_chain:
                continue
            chains.append(
                {
                    "path_id": _stringify(path.get("path_id")),
                    "path_name": _stringify(path.get("path_name")),
                    "summary": _stringify(path.get("summary")),
                    "function_chain": function_chain,
                    "leaf_node": _stringify(path.get("leaf_node")) or function_chain[-1],
                    "worthiness_score": _safe_float(path.get("worthiness_score")),
                    "selection_policy": _stringify(path.get("selection_policy")),
                    "source": _stringify(path.get("source")),
                }
            )

        groups.append(
            {
                "group_id": f"partition::{_stringify(skill.get('partition_id')) or _stringify(skill.get('skill_id'))}",
                "skill_id": _stringify(skill.get("skill_id")),
                "skill_name": _stringify(skill.get("name")),
                "partition_id": _stringify(skill.get("partition_id")),
                "partition_name": _stringify(skill.get("partition_name")),
                "matched_requirement_fields": _string_list(skill.get("matched_requirement_fields")),
                "chain_count": len(chains),
                "chains": chains,
            }
        )
    return groups


def _build_path_steps(selected_skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    step_index = 1
    for skill in selected_skills:
        for path in skill.get("selected_paths") or []:
            function_chain = _string_list(path.get("function_chain"))
            if not function_chain:
                continue
            for function_index, function_name in enumerate(function_chain, start=1):
                steps.append(
                    {
                        "step_index": step_index,
                        "skill_id": _stringify(skill.get("skill_id")),
                        "skill_name": _stringify(skill.get("name")),
                        "partition_id": _stringify(skill.get("partition_id")),
                        "path_id": _stringify(path.get("path_id")),
                        "path_name": _stringify(path.get("path_name")),
                        "function_index": function_index,
                        "function_name": function_name,
                        "is_entry": function_index == 1,
                        "is_leaf": function_index == len(function_chain),
                        "path_summary": _stringify(path.get("summary")),
                        "selection_policy": _stringify(path.get("selection_policy")),
                        "source": _stringify(path.get("source")),
                        "worthiness_score": _safe_float(path.get("worthiness_score")),
                    }
                )
                step_index += 1
    return steps


def _build_selection_reasoning(
    requirement_fields: dict[str, list[str]],
    selected_skills: list[dict[str, Any]],
    skills_report: dict[str, Any],
    top_n: int,
) -> dict[str, Any]:
    return {
        "top_n": top_n,
        "total_candidate_skills": len(skills_report.get("skills") or []),
        "requirement_focus": requirement_fields,
        "heuristics": {
            "requirement_field_weights": REQUIREMENT_FIELD_WEIGHTS,
            "skill_field_weights": SKILL_FIELD_WEIGHTS,
            "tie_breakers": [
                "path_count",
                "best_path_score",
                "partition_id",
                "name",
            ],
            "notes": [
                "只使用本地 runtime 输入文件。",
                "按 goal/target/expected_output/constraints 与 skill name/tags/what/how/path summaries 的词项重叠打分。",
                "输出路径步骤时优先使用每个入选 skill 的高分 path_evidence。",
            ],
        },
        "selected_skill_reasons": [
            {
                "rank": skill.get("rank"),
                "skill_id": skill.get("skill_id"),
                "name": skill.get("name"),
                "score": skill.get("score"),
                "matched_requirement_fields": skill.get("matched_requirement_fields"),
                "matched_terms": skill.get("matched_terms"),
                "path_count": skill.get("path_count"),
                "best_path_score": skill.get("best_path_score"),
            }
            for skill in selected_skills
        ],
    }


def build_payload(step1_payload: dict[str, Any], skills_report: dict[str, Any]) -> dict[str, Any]:
    requirement_fields = _extract_requirement_fields(step1_payload)
    top_n = XYZ_TOP_N if XYZ_TOP_N > 0 else 5
    selected_skills = _select_skills(skills_report, requirement_fields, top_n)
    function_chain_groups = _build_function_chain_groups(selected_skills)
    path_steps = _build_path_steps(selected_skills)

    return {
        "version": "v2.work_order_c",
        "step": "build_x_path_context",
        "generated_at": utc_now(),
        "input_files": {
            "step1_clarified_task": str(STEP1_CLARIFIED_TASK_FILE),
            "generated_skills": str(GENERATED_SKILLS_FILE),
        },
        "selected_skills": selected_skills,
        "path_steps": path_steps,
        "function_chain_groups": function_chain_groups,
        "selection_reasoning": _build_selection_reasoning(requirement_fields, selected_skills, skills_report, top_n),
    }


def main() -> None:
    ensure_runtime()
    step1_payload = read_json(STEP1_CLARIFIED_TASK_FILE)
    skills_report = read_json(GENERATED_SKILLS_FILE)
    payload = build_payload(step1_payload, skills_report)
    write_json(STEP3_X_PATH_CONTEXT_FILE, payload)
    print_output("step3 X 完成", STEP3_X_PATH_CONTEXT_FILE)


if __name__ == "__main__":
    main()
