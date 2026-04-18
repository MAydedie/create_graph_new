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
write_text: Callable[[Path, str], None] = _load_attr("common", "write_text")
RUNTIME_DIR: Path = _load_attr("config", "RUNTIME_DIR")


STEP6_FUSED_CONTEXT_FILE = RUNTIME_DIR / "step6_fused_context.json"
STEP7_DECOMPOSED_REQUIREMENTS_FILE = RUNTIME_DIR / "step7_decomposed_requirements.json"
STEP8_REQUIREMENT_ANALYSIS_FILE = RUNTIME_DIR / "step8_requirement_analysis.md"

DECOMPOSITION_LIST_KEYS = (
    "decomposed_requirements",
    "requirements",
    "requirement_items",
    "items",
    "decomposition",
    "sub_requirements",
    "capability_requirements",
)
TITLE_KEYS = (
    "title",
    "name",
    "requirement",
    "summary",
    "description",
    "goal",
    "capability",
)
SUMMARY_KEYS = (
    "summary",
    "description",
    "requirement",
    "goal",
    "purpose",
    "reason",
)
INPUT_KEYS = ("inputs", "input_contract", "depends_on", "dependencies", "source_inputs")
OUTPUT_KEYS = ("outputs", "output_contract", "deliverables", "artifacts")
CONSTRAINT_KEYS = ("constraints", "caution_items", "cautions", "risks")
ACCEPTANCE_KEYS = ("acceptance_criteria", "done_when", "checks", "verification_points")
SKILL_KEYS = ("related_skills", "skill_ids", "recommended_skill_ids", "skills")
NON_GOAL_KEYS = ("non_goals", "out_of_scope", "excluded_scope")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _dedupe_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _stringify(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = _pick_first_string(item, TITLE_KEYS + SUMMARY_KEYS)
                if text:
                    result.append(text)
            else:
                result.append(_stringify(item))
        return _dedupe_strings(result)
    if isinstance(value, tuple):
        return _dedupe_strings(list(value))
    if isinstance(value, str):
        return [_stringify(value)] if _stringify(value) else []
    return []


def _pick_first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _stringify(payload.get(key))
        if value:
            return value
    return ""


def _read_required_payload(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(payload).__name__}.")
    return payload


def _find_first_list(payload: dict[str, Any], keys: tuple[str, ...]) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _find_first_list(value, keys)
            if nested:
                return nested
    return []


def _normalize_skill_refs(value: Any) -> list[str]:
    results: list[str] = []
    for item in _string_list(value):
        results.append(item)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                results.append(
                    _pick_first_string(item, ("skill_id", "id", "name", "skill_name", "title"))
                )
    return _dedupe_strings(results)


def _normalize_requirement_items(step7_payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = _find_first_list(step7_payload, DECOMPOSITION_LIST_KEYS)
    if not raw_items and any(key in step7_payload for key in TITLE_KEYS + SUMMARY_KEYS):
        raw_items = [step7_payload]

    normalized_items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if isinstance(item, str):
            title = _stringify(item)
            if not title:
                continue
            normalized_items.append(
                {
                    "item_id": f"R{index}",
                    "title": title,
                    "summary": title,
                    "inputs": [],
                    "outputs": [],
                    "constraints": [],
                    "acceptance_criteria": [],
                    "related_skills": [],
                    "non_goals": [],
                }
            )
            continue

        if not isinstance(item, dict):
            continue

        title = _pick_first_string(item, TITLE_KEYS)
        summary = _pick_first_string(item, SUMMARY_KEYS) or title
        item_id = _stringify(item.get("item_id") or item.get("requirement_id") or item.get("id") or f"R{index}")
        normalized = {
            "item_id": item_id,
            "title": title or summary or item_id,
            "summary": summary or title or item_id,
            "inputs": _dedupe_strings([text for key in INPUT_KEYS for text in _string_list(item.get(key))]),
            "outputs": _dedupe_strings([text for key in OUTPUT_KEYS for text in _string_list(item.get(key))]),
            "constraints": _dedupe_strings([text for key in CONSTRAINT_KEYS for text in _string_list(item.get(key))]),
            "acceptance_criteria": _dedupe_strings(
                [text for key in ACCEPTANCE_KEYS for text in _string_list(item.get(key))]
            ),
            "related_skills": _dedupe_strings(
                [text for key in SKILL_KEYS for text in _normalize_skill_refs(item.get(key))]
            ),
            "non_goals": _dedupe_strings([text for key in NON_GOAL_KEYS for text in _string_list(item.get(key))]),
        }
        normalized_items.append(normalized)

    normalized_items.sort(key=lambda item: (_stringify(item.get("item_id")), _stringify(item.get("title"))))
    return normalized_items


def _format_inline_list(values: list[str], fallback: str) -> str:
    normalized = _dedupe_strings(values)
    return "、".join(normalized) if normalized else fallback


def _task_constraints(fused_payload: dict[str, Any]) -> list[str]:
    task_summary = fused_payload.get("task_summary") or {}
    return _string_list(task_summary.get("constraints"))


def _recommended_skills(fused_payload: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in fused_payload.get("recommended_skills") or []:
        if isinstance(item, dict):
            results.append(item)
    return results


def _semantic_entries(fused_payload: dict[str, Any]) -> list[dict[str, Any]]:
    semantic_context = ((fused_payload.get("semantic_context") or {}).get("context") or {}).get("semantic_context") or []
    return [item for item in semantic_context if isinstance(item, dict)]


def _code_entries(fused_payload: dict[str, Any]) -> list[dict[str, Any]]:
    code_context = ((fused_payload.get("code_context") or {}).get("context") or {}).get("code_context") or []
    return [item for item in code_context if isinstance(item, dict)]


def _path_groups(fused_payload: dict[str, Any]) -> list[dict[str, Any]]:
    path_context = ((fused_payload.get("path_context") or {}).get("context") or {}).get("function_chain_groups") or []
    return [item for item in path_context if isinstance(item, dict)]


def _match_requirement_titles(skill: dict[str, Any], requirement_items: list[dict[str, Any]]) -> list[str]:
    skill_id = _stringify(skill.get("skill_id"))
    skill_name = _stringify(skill.get("name"))
    matched: list[str] = []
    for item in requirement_items:
        related_skills = _string_list(item.get("related_skills"))
        if skill_id and skill_id in related_skills:
            matched.append(_stringify(item.get("title")))
            continue
        if skill_name and skill_name in related_skills:
            matched.append(_stringify(item.get("title")))
    return _dedupe_strings(matched)


def _build_decomposition_lines(requirement_items: list[dict[str, Any]]) -> list[str]:
    if not requirement_items:
        return ["- 未从 `runtime/step7_decomposed_requirements.json` 解析出明确分解条目。"]

    lines: list[str] = []
    for item in requirement_items:
        fragments = [
            f"摘要：{_stringify(item.get('summary'))}",
            f"输入：{_format_inline_list(_string_list(item.get('inputs')), '未显式给出')}",
            f"输出：{_format_inline_list(_string_list(item.get('outputs')), '未显式给出')}",
        ]
        if _string_list(item.get("constraints")):
            fragments.append(f"约束：{_format_inline_list(_string_list(item.get('constraints')), '无')}")
        if _string_list(item.get("acceptance_criteria")):
            fragments.append(f"验收：{_format_inline_list(_string_list(item.get('acceptance_criteria')), '无')}")
        lines.append(f"- `{_stringify(item.get('item_id'))}` {_stringify(item.get('title'))}；" + "；".join(fragments))
    return lines


def _build_capability_lines(fused_payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    path_groups = _path_groups(fused_payload)
    semantic_entries = _semantic_entries(fused_payload)
    code_entries = _code_entries(fused_payload)

    if path_groups:
        for group in path_groups:
            chains = group.get("chains") or []
            first_chain = chains[0] if chains and isinstance(chains[0], dict) else {}
            chain_text = " -> ".join(_string_list(first_chain.get("function_chain"))) or "未显式给出函数链"
            lines.append(
                f"- 路径证据 `{_stringify(group.get('skill_id') or group.get('skill_name'))}`：{_stringify(first_chain.get('path_name') or group.get('partition_name'))}；函数链：{chain_text}"
            )

    if semantic_entries:
        for entry in semantic_entries:
            lines.append(
                f"- 语义证据 `{_stringify(entry.get('skill_id') or entry.get('name'))}`：{_stringify(entry.get('functional_description') or entry.get('reasoning') or '未显式给出') }"
            )

    if code_entries:
        for entry in code_entries:
            evidence = entry.get("source_evidence") or []
            file_refs = _dedupe_strings(
                [_stringify(item.get("file_ref") or item.get("file_path")) for item in evidence if isinstance(item, dict)]
            )
            lines.append(
                f"- 源码证据 `{_stringify(entry.get('skill_id') or entry.get('name'))}`：{_format_inline_list(file_refs[:3], '未显式给出文件引用')}"
            )

    return lines or ["- `step6_fused_context.json` 中未提供可用的 X/Y/Z 能力证据。"]


def _build_constraint_lines(fused_payload: dict[str, Any], requirement_items: list[dict[str, Any]]) -> list[str]:
    constraints = _task_constraints(fused_payload)
    for item in requirement_items:
        constraints.extend(_string_list(item.get("constraints")))
    deduped = _dedupe_strings(constraints)
    return [f"- {item}" for item in deduped] or ["- 当前输入未显式给出额外约束。"]


def _build_risk_lines(fused_payload: dict[str, Any], requirement_items: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []

    if not requirement_items:
        risks.append("`step7_decomposed_requirements.json` 缺少可解析条目，后续规格容易退化为任务复述。")

    for item in requirement_items:
        title = _stringify(item.get("title") or item.get("item_id"))
        if not _string_list(item.get("outputs")):
            risks.append(f"分解条目“{title}”未显式给出输出，交付边界可能不稳定。")
        if not _string_list(item.get("acceptance_criteria")):
            risks.append(f"分解条目“{title}”未显式给出验收标准，老师阅读时可能缺少完成判据。")

    recommended_skills = _recommended_skills(fused_payload)
    if not recommended_skills:
        risks.append("融合上下文未产出推荐技能，需求分析缺少能力承接依据。")

    for skill in recommended_skills:
        source_count = int(skill.get("source_count") or 0)
        skill_label = _stringify(skill.get("skill_id") or skill.get("name"))
        if source_count < 2:
            risks.append(f"技能“{skill_label}”仅由 {source_count} 个上下文来源支持，适配性证据偏弱。")

    for entry in _code_entries(fused_payload):
        evidence_summary = entry.get("evidence_summary") or {}
        if int(evidence_summary.get("selected_count") or 0) <= 0:
            risks.append(f"技能“{_stringify(entry.get('skill_id') or entry.get('name'))}”缺少稳定源码引用。")

    if not _path_groups(fused_payload):
        risks.append("路径侧未给出函数链证据，需求与实际调用链的对应关系偏弱。")

    return [f"- {item}" for item in _dedupe_strings(risks)] or ["- 当前输入下未发现新增高风险项，主要风险已由约束与验收条目覆盖。"]


def _build_skill_fit_lines(fused_payload: dict[str, Any], requirement_items: list[dict[str, Any]]) -> list[str]:
    semantic_entries = {
        _stringify(item.get("skill_id") or item.get("name")): item for item in _semantic_entries(fused_payload)
    }
    code_entries = {
        _stringify(item.get("skill_id") or item.get("name")): item for item in _code_entries(fused_payload)
    }

    lines: list[str] = []
    for skill in _recommended_skills(fused_payload):
        skill_key = _stringify(skill.get("skill_id") or skill.get("name"))
        matched_titles = _match_requirement_titles(skill, requirement_items)
        semantic_entry = semantic_entries.get(skill_key) or {}
        code_entry = code_entries.get(skill_key) or {}
        evidence = code_entry.get("source_evidence") or []
        refs = _dedupe_strings(
            [_stringify(item.get("file_ref") or item.get("file_path")) for item in evidence if isinstance(item, dict)]
        )
        lines.append(
            "- "
            + f"`{skill_key}` 适配原因：{_stringify(skill.get('summary') or semantic_entry.get('functional_description') or '未显式给出')}；"
            + f"来源：{_format_inline_list(_string_list(skill.get('selected_by')), '未显式给出')}；"
            + f"关联分解：{_format_inline_list(matched_titles, 'step7 未显式绑定技能')}；"
            + f"源码落点：{_format_inline_list(refs[:2], '未显式给出')}"
        )
    return lines or ["- 当前输入未给出可解释的推荐技能列表。"]


def build_markdown(fused_payload: dict[str, Any], step7_payload: dict[str, Any]) -> str:
    task_summary = fused_payload.get("task_summary") or {}
    requirement_items = _normalize_requirement_items(step7_payload)

    lines = [
        "# Requirement Analysis",
        "",
        "- Source inputs: `runtime/step6_fused_context.json`, `runtime/step7_decomposed_requirements.json`",
        "- Generation mode: deterministic local runtime JSON only.",
        "",
        "## Problem Statement",
        f"- Goal: {_stringify(task_summary.get('goal')) or '未显式给出'}",
        f"- Target: {_stringify(task_summary.get('target')) or '未显式给出'}",
        f"- Expected output: {_stringify(task_summary.get('expected_output')) or '未显式给出'}",
        f"- Decomposed requirement count: {len(requirement_items)}",
        "",
        "## Requirement Decomposition",
        *_build_decomposition_lines(requirement_items),
        "",
        "## Capability Sources",
        *_build_capability_lines(fused_payload),
        "",
        "## Constraints",
        *_build_constraint_lines(fused_payload, requirement_items),
        "",
        "## Risks",
        *_build_risk_lines(fused_payload, requirement_items),
        "",
        "## Why Selected Skills Fit",
        *_build_skill_fit_lines(fused_payload, requirement_items),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ensure_runtime()
    fused_payload = _read_required_payload(STEP6_FUSED_CONTEXT_FILE)
    step7_payload = _read_required_payload(STEP7_DECOMPOSED_REQUIREMENTS_FILE)
    markdown = build_markdown(fused_payload, step7_payload)
    write_text(STEP8_REQUIREMENT_ANALYSIS_FILE, markdown)
    print_output("step8 完成", STEP8_REQUIREMENT_ANALYSIS_FILE)


if __name__ == "__main__":
    main()
