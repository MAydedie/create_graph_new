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


def _load_optional_config_path(attr_name: str, filename: str) -> Path:
    try:
        return _load_attr("config", attr_name)
    except AttributeError:
        return BASE_DIR / "runtime" / filename


def _load_optional_config_int(attr_name: str, default: int) -> int:
    try:
        return int(_load_attr("config", attr_name))
    except Exception:
        return default


ensure_runtime: Callable[[], Path] = _load_attr("common", "ensure_runtime")
print_output: Callable[[str, Path], None] = _load_attr("common", "print_output")
read_json: Callable[[Path], Any] = _load_attr("common", "read_json")
utc_now: Callable[[], str] = _load_attr("common", "utc_now")
write_json: Callable[[Path, Any], None] = _load_attr("common", "write_json")
GENERATED_SKILLS_FILE: Path = _load_attr("config", "GENERATED_SKILLS_FILE")
STEP1_CLARIFIED_TASK_FILE: Path = _load_attr("config", "STEP1_CLARIFIED_TASK_FILE")
STEP5_Z_CODE_CONTEXT_FILE: Path = _load_optional_config_path(
    "STEP5_Z_CODE_CONTEXT_FILE",
    "step5_z_code_context.json",
)
XYZ_TOP_N = _load_optional_config_int("XYZ_TOP_N", 5)
MAX_CODE_SNIPPETS_PER_SKILL = _load_optional_config_int("MAX_CODE_SNIPPETS_PER_SKILL", 3)


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")
STOP_TOKENS = {
    "task",
    "goal",
    "target",
    "output",
    "inputs",
    "outputs",
    "runtime",
    "step",
    "skill",
    "skills",
    "json",
    "python",
    "生成",
    "输出",
    "输入",
    "相关",
    "结果",
    "任务",
    "功能",
    "代码",
    "上下文",
    "文件",
    "脚本",
    "error",
    "gate",
    "demand",
    "finalize",
    "包含",
    "需求比对",
}
KIND_PRIORITY = {
    "entry_point": 8,
    "method_ref": 5,
    "method": 5,
    "function": 5,
    "graph_node": 3,
    "class": 2,
}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _stringify(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _dedupe_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _stringify(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if token and token.lower() not in STOP_TOKENS
    ]


def _task_text_fragments(task_payload: dict[str, Any]) -> list[str]:
    structured_requirement = task_payload.get("structured_requirement") or {}
    domain_constraints = _string_list(structured_requirement.get("domain_constraints") or structured_requirement.get("constraints"))
    return _dedupe_strings(
        [
            task_payload.get("raw_task"),
            task_payload.get("inferred_intent"),
            structured_requirement.get("goal"),
            structured_requirement.get("target"),
            structured_requirement.get("expected_output"),
            *(domain_constraints),
        ]
    )


def _skill_text_fragments(skill: dict[str, Any]) -> list[str]:
    retrieval_hints = skill.get("retrieval_hints") or {}
    return _dedupe_strings(
        [
            skill.get("skill_id"),
            skill.get("partition_id"),
            skill.get("partition_name"),
            skill.get("name"),
            skill.get("when_to_use"),
            *(_string_list(skill.get("tags"))),
            *(_string_list(skill.get("methods"))),
            *(_string_list(skill.get("method_call_chain"))),
            *(_string_list(skill.get("chain_explanation"))),
            *(_string_list(skill.get("inputs"))),
            *(_string_list(skill.get("outputs"))),
            *(_string_list(skill.get("caution"))),
            *(_string_list(retrieval_hints.get("preferred_symbols"))),
            *(_string_list(retrieval_hints.get("preferred_paths"))),
        ]
    )


def _skill_evidence_counts(skill: dict[str, Any]) -> tuple[int, int, int]:
    evidence_summary = skill.get("evidence_summary") or {}
    return (
        int(evidence_summary.get("path_count") or 0),
        int(evidence_summary.get("code_ref_count") or 0),
        int(evidence_summary.get("file_count") or 0),
    )


def _score_skill(task_payload: dict[str, Any], skill: dict[str, Any]) -> dict[str, Any]:
    task_fragments = _task_text_fragments(task_payload)
    task_text = "\n".join(task_fragments).lower()
    task_tokens = set(_tokenize("\n".join(task_fragments)))
    skill_fragments = _skill_text_fragments(skill)
    skill_tokens = set(_tokenize("\n".join(skill_fragments)))
    overlap_tokens = sorted(task_tokens.intersection(skill_tokens))

    direct_hits: list[str] = []
    direct_bonus = 0
    for candidate, bonus in (
        (_stringify(skill.get("name")), 24),
        (_stringify(skill.get("partition_name")), 18),
        (_stringify(skill.get("partition_id")), 12),
    ):
        normalized = candidate.lower()
        if normalized and len(normalized) >= 2 and normalized in task_text and candidate not in direct_hits:
            direct_hits.append(candidate)
            direct_bonus += bonus

    method_hits: list[str] = []
    for method in _string_list(skill.get("methods"))[:6]:
        normalized = method.lower()
        if normalized and len(normalized) >= 2 and normalized in task_text:
            method_hits.append(method)
            direct_bonus += 4

    path_count, code_ref_count, file_count = _skill_evidence_counts(skill)
    score = len(overlap_tokens) * 10 + direct_bonus + min(path_count, 3) * 2 + min(code_ref_count, 4) + min(file_count, 2)

    reasons: list[str] = []
    if overlap_tokens:
        reasons.append(f"关键词重叠: {', '.join(overlap_tokens[:6])}")
    if direct_hits:
        reasons.append(f"直接命中: {', '.join(direct_hits[:3])}")
    if method_hits:
        reasons.append(f"方法命中: {', '.join(method_hits[:3])}")
    if path_count or code_ref_count or file_count:
        reasons.append(f"证据量 path={path_count}, code={code_ref_count}, file={file_count}")
    if not reasons:
        reasons.append("缺少显式关键词重叠，按稳定顺序与证据量兜底。")

    return {
        "skill": skill,
        "skill_id": _stringify(skill.get("skill_id")),
        "partition_id": _stringify(skill.get("partition_id")),
        "name": _stringify(skill.get("name") or skill.get("partition_name")),
        "score": score,
        "overlap_count": len(overlap_tokens),
        "path_count": path_count,
        "code_ref_count": code_ref_count,
        "file_count": file_count,
        "reason": "；".join(reasons),
    }


def _select_skills(task_payload: dict[str, Any], skills: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    all_skills = [item for item in skills if isinstance(item, dict)]
    candidate_skills = [item for item in all_skills if bool(item.get("usable_for_matching", True))]
    if not candidate_skills:
        candidate_skills = all_skills
    ranked = [_score_skill(task_payload, skill) for skill in candidate_skills]
    ranked.sort(
        key=lambda item: (
            -int(item.get("score") or 0),
            -int(item.get("overlap_count") or 0),
            -int(item.get("path_count") or 0),
            -int(item.get("code_ref_count") or 0),
            -int(item.get("file_count") or 0),
            item.get("skill_id") or "",
        )
    )
    return ranked[: max(1, min(top_n, len(ranked)))] if ranked else []


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _short_preview(value: Any, fallback: str = "") -> str:
    text = _stringify(value) or fallback
    text = re.sub(r"\s+", " ", text)
    if len(text) <= 160:
        return text
    return f"{text[:157]}..."


def _fallback_code_evidence(skill: dict[str, Any]) -> list[dict[str, Any]]:
    fallbacks: list[dict[str, Any]] = []
    for symbol in _string_list(skill.get("code_refs")) or _string_list(skill.get("methods")):
        fallbacks.append(
            {
                "file_path": "",
                "class_name": "",
                "method_signature": symbol,
                "symbol": symbol,
                "snippet_preview": symbol,
                "kind": "method_ref",
                "source": "skill_refs_fallback",
            }
        )
    return fallbacks


def _source_location_evidence(skill: dict[str, Any]) -> list[dict[str, Any]]:
    locations = skill.get("source_locations") or []
    results: list[dict[str, Any]] = []
    for item in locations:
        if not isinstance(item, dict):
            continue
        symbol = _stringify(item.get("symbol"))
        file_path = _stringify(item.get("file_path"))
        line = _int_or_none(item.get("line"))
        if not symbol and not file_path:
            continue
        results.append(
            {
                "file_path": file_path,
                "class_name": "",
                "method_signature": symbol,
                "symbol": symbol,
                "snippet_preview": symbol,
                "kind": "source_location",
                "line": line,
                "source": "source_locations",
            }
        )
    return results


def _normalize_code_evidence(skill: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = skill.get("code_evidence") or []
    raw_items = list(_source_location_evidence(skill)) + list(raw_items)
    if not raw_items:
        raw_items = _fallback_code_evidence(skill)

    normalized_items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        raw_metadata = item.get("metadata")
        metadata: dict[str, Any]
        if isinstance(raw_metadata, dict):
            metadata = raw_metadata
        else:
            metadata = {}
        file_path = _stringify(item.get("file_path") or metadata.get("file_path"))
        method_signature = _stringify(item.get("method_signature") or item.get("symbol") or metadata.get("method_signature"))
        class_name = _stringify(item.get("class_name") or metadata.get("class_name"))
        symbol_kind = _stringify(item.get("symbol_kind") or item.get("kind") or metadata.get("symbol_kind"))
        line = _int_or_none(item.get("line") or item.get("line_start") or metadata.get("line"))
        snippet_preview = _short_preview(
            item.get("snippet_preview") or metadata.get("snippet_preview"),
            fallback=method_signature or _stringify(item.get("symbol")),
        )
        key = (file_path, method_signature, str(line or ""), symbol_kind)
        if key in seen:
            continue
        seen.add(key)
        normalized_items.append(
            {
                "file_path": file_path,
                "file_ref": f"{file_path}:{line}" if file_path and line is not None else file_path,
                "class_name": class_name,
                "method_signature": method_signature,
                "symbol_kind": symbol_kind or "code_ref",
                "line": line,
                "snippet_preview": snippet_preview,
                "source": _stringify(item.get("source") or metadata.get("source")),
            }
        )
    return normalized_items


def _score_code_entry(item: dict[str, Any]) -> tuple[int, str, int, str]:
    score = 0
    if _stringify(item.get("file_path")):
        score += 50
    if _stringify(item.get("method_signature")):
        score += 25
    if _stringify(item.get("class_name")):
        score += 10
    if _stringify(item.get("snippet_preview")):
        score += 10
    if item.get("line") is not None:
        score += 5
    score += KIND_PRIORITY.get(_stringify(item.get("symbol_kind")), 1)
    return (
        -score,
        _stringify(item.get("file_path")),
        int(item.get("line") or 0),
        _stringify(item.get("method_signature")),
    )


def _build_code_entries(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in selected:
        skill = item.get("skill") or {}
        code_items = _normalize_code_evidence(skill)
        code_items.sort(key=_score_code_entry)
        chosen = code_items[:MAX_CODE_SNIPPETS_PER_SKILL]
        file_count = len({_stringify(entry.get("file_path")) for entry in code_items if _stringify(entry.get("file_path"))})
        entries.append(
            {
                "skill_id": item.get("skill_id"),
                "partition_id": item.get("partition_id"),
                "name": item.get("name"),
                "reasoning": item.get("reason"),
                "evidence_summary": {
                    "total_candidates": len(code_items),
                    "selected_count": len(chosen),
                    "file_count": file_count,
                },
                "source_evidence": chosen,
            }
        )
    return entries


def build_report(task_payload: dict[str, Any], skills_payload: dict[str, Any]) -> dict[str, Any]:
    skills = skills_payload.get("skills") or []
    selected = _select_skills(task_payload, skills, XYZ_TOP_N)

    return {
        "version": "v2.work_order_c",
        "step": "build_z_code_context",
        "generated_at": utc_now(),
        "input_files": [
            str(STEP1_CLARIFIED_TASK_FILE),
            str(GENERATED_SKILLS_FILE),
        ],
        "selection_policy": "deterministic_keyword_overlap_plus_evidence",
        "reasoning": "与 Y 侧复用同一 skill 选择逻辑，再从本地 generated_skills 中提取轻量源码证据。",
        "selected_skills": [
            {
                "skill_id": item.get("skill_id"),
                "partition_id": item.get("partition_id"),
                "name": item.get("name"),
                "score": item.get("score"),
                "reason": item.get("reason"),
            }
            for item in selected
        ],
        "code_context": _build_code_entries(selected),
    }


def main() -> None:
    ensure_runtime()
    task_payload = read_json(STEP1_CLARIFIED_TASK_FILE)
    skills_payload = read_json(GENERATED_SKILLS_FILE)
    report = build_report(task_payload, skills_payload)
    write_json(STEP5_Z_CODE_CONTEXT_FILE, report)
    print_output("step5_z 完成", STEP5_Z_CODE_CONTEXT_FILE)


if __name__ == "__main__":
    main()
