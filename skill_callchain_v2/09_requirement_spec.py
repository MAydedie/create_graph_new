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
read_text: Callable[[Path], str] = _load_attr("common", "read_text")
write_text: Callable[[Path, str], None] = _load_attr("common", "write_text")
RUNTIME_DIR: Path = _load_attr("config", "RUNTIME_DIR")


STEP6_FUSED_CONTEXT_FILE = RUNTIME_DIR / "step6_fused_context.json"
STEP7_DECOMPOSED_REQUIREMENTS_FILE = RUNTIME_DIR / "step7_decomposed_requirements.json"
STEP8_REQUIREMENT_ANALYSIS_FILE = RUNTIME_DIR / "step8_requirement_analysis.md"
STEP9_REQUIREMENT_SPEC_FILE = RUNTIME_DIR / "step9_requirement_spec.md"

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
        normalized_items.append(
            {
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
        )

    normalized_items.sort(key=lambda item: (_stringify(item.get("item_id")), _stringify(item.get("title"))))
    return normalized_items


def _parse_markdown_sections(markdown_text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_section = ""
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            current_section = line[3:].strip()
            sections.setdefault(current_section, [])
            continue
        if current_section and line.startswith("- "):
            sections[current_section].append(line[2:].strip())
    return sections


def _task_constraints(fused_payload: dict[str, Any]) -> list[str]:
    task_summary = fused_payload.get("task_summary") or {}
    return _string_list(task_summary.get("constraints"))


def _recommended_skills(fused_payload: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in fused_payload.get("recommended_skills") or []:
        if isinstance(item, dict):
            results.append(item)
    return results


def _format_bullet_lines(values: list[str], fallback: str) -> list[str]:
    normalized = _dedupe_strings(values)
    return [f"- {item}" for item in normalized] if normalized else [f"- {fallback}"]


def _build_scope_lines(requirement_items: list[dict[str, Any]], fused_payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    task_summary = fused_payload.get("task_summary") or {}
    target = _stringify(task_summary.get("target"))
    if target:
        lines.append(f"- Target area: {target}")
    for item in requirement_items:
        lines.append(f"- `{_stringify(item.get('item_id'))}` {_stringify(item.get('title'))}: {_stringify(item.get('summary'))}")
    return lines or ["- 当前输入未显式给出可展开的范围条目。"]


def _build_input_lines(requirement_items: list[dict[str, Any]], analysis_sections: dict[str, list[str]]) -> list[str]:
    inputs = [
        "`runtime/step6_fused_context.json`: fused task summary, recommended skills, X/Y/Z context evidence.",
        "`runtime/step7_decomposed_requirements.json`: decomposed requirement items and per-item contracts.",
        "`runtime/step8_requirement_analysis.md`: analysis baseline used for traceability and spec carry-over.",
    ]
    for item in requirement_items:
        for input_item in _string_list(item.get("inputs")):
            inputs.append(f"`{_stringify(item.get('item_id'))}` input: {input_item}")
    if analysis_sections:
        inputs.append(f"analysis sections imported: {', '.join(sorted(analysis_sections))}")
    return _format_bullet_lines(inputs, "无额外输入。")


def _build_output_lines(fused_payload: dict[str, Any], requirement_items: list[dict[str, Any]]) -> list[str]:
    task_summary = fused_payload.get("task_summary") or {}
    outputs = [
        "`runtime/step8_requirement_analysis.md`: concise requirement analysis markdown.",
        "`runtime/step9_requirement_spec.md`: formal requirement specification markdown.",
    ]
    expected_output = _stringify(task_summary.get("expected_output"))
    if expected_output:
        outputs.append(f"task expected output: {expected_output}")
    for item in requirement_items:
        for output_item in _string_list(item.get("outputs")):
            outputs.append(f"`{_stringify(item.get('item_id'))}` output: {output_item}")
    return _format_bullet_lines(outputs, "无额外交付物。")


def _build_constraint_lines(fused_payload: dict[str, Any], requirement_items: list[dict[str, Any]]) -> list[str]:
    constraints = _task_constraints(fused_payload)
    constraints.extend(
        [
            "只使用本地 runtime 输入与已生成分析文档。",
            "输出保持确定性、简洁、以 Markdown 标题和 bullet 为主。",
            "不进入系统设计或详细设计。",
        ]
    )
    for item in requirement_items:
        constraints.extend(_string_list(item.get("constraints")))
    return _format_bullet_lines(constraints, "当前输入未显式给出额外约束。")


def _build_acceptance_lines(
    requirement_items: list[dict[str, Any]],
    analysis_sections: dict[str, list[str]],
    fused_payload: dict[str, Any],
) -> list[str]:
    acceptance: list[str] = [
        "`08_requirement_analysis.py` 可读取 `step6_fused_context.json` 与 `step7_decomposed_requirements.json` 并写出 `runtime/step8_requirement_analysis.md`。",
        "`09_requirement_spec.py` 可读取 `step6_fused_context.json`、`step7_decomposed_requirements.json` 与 `step8_requirement_analysis.md` 并写出 `runtime/step9_requirement_spec.md`。",
        "文档内容对齐 fused task summary、decomposition 条目与推荐技能，不依赖外部 LLM 调用。",
    ]

    task_summary = fused_payload.get("task_summary") or {}
    goal = _stringify(task_summary.get("goal"))
    if goal:
        acceptance.append(f"规格文档明确保留任务目标：{goal}")

    for item in requirement_items:
        title = _stringify(item.get("title") or item.get("item_id"))
        criteria = _string_list(item.get("acceptance_criteria"))
        if criteria:
            for criterion in criteria:
                acceptance.append(f"`{title}`: {criterion}")
        else:
            acceptance.append(f"`{title}`: 至少在规格中保留该条目的目标、输入/输出与约束摘要。")

    risk_lines = analysis_sections.get("Risks") or []
    if risk_lines:
        acceptance.append(f"规格文档保留 {len(risk_lines)} 条分析风险的可追踪信息。")
    skill_fit_lines = analysis_sections.get("Why Selected Skills Fit") or []
    if skill_fit_lines:
        acceptance.append(f"规格文档保留 {len(skill_fit_lines)} 条技能适配依据。")
    return _format_bullet_lines(acceptance, "无额外验收条件。")


def _build_traceability_lines(analysis_sections: dict[str, list[str]]) -> list[str]:
    trace_lines: list[str] = []
    for section_name in ("Constraints", "Risks", "Why Selected Skills Fit"):
        entries = analysis_sections.get(section_name) or []
        if entries:
            trace_lines.append(f"{section_name}: imported {len(entries)} bullet(s) from `runtime/step8_requirement_analysis.md`.")
            trace_lines.extend(entries[:2])
    return _format_bullet_lines(trace_lines, "分析文档未提供可追踪条目。")


def _build_non_goal_lines(requirement_items: list[dict[str, Any]]) -> list[str]:
    non_goals: list[str] = []
    for item in requirement_items:
        non_goals.extend(_string_list(item.get("non_goals")))
    non_goals.extend(
        [
            "不展开系统设计。",
            "不展开详细设计、类图、模块图或实现步骤分配。",
            "不引入 fused/decomposed runtime 输入之外的新需求。",
        ]
    )
    return _format_bullet_lines(non_goals, "无额外非目标。")


def build_markdown(fused_payload: dict[str, Any], step7_payload: dict[str, Any], analysis_markdown: str) -> str:
    task_summary = fused_payload.get("task_summary") or {}
    requirement_items = _normalize_requirement_items(step7_payload)
    analysis_sections = _parse_markdown_sections(analysis_markdown)
    skill_names = [
        _stringify(item.get("name") or item.get("skill_id"))
        for item in _recommended_skills(fused_payload)
        if _stringify(item.get("name") or item.get("skill_id"))
    ]

    lines = [
        "# Requirement Specification",
        "",
        "- Source inputs: `runtime/step6_fused_context.json`, `runtime/step7_decomposed_requirements.json`, `runtime/step8_requirement_analysis.md`",
        "- Generation mode: deterministic local runtime inputs only.",
        "",
        "## Goal",
        f"- Primary goal: {_stringify(task_summary.get('goal')) or '未显式给出'}",
        f"- Supporting skills: {('、'.join(_dedupe_strings(skill_names)) if skill_names else '未显式给出')}",
        "",
        "## Scope",
        *_build_scope_lines(requirement_items, fused_payload),
        "",
        "## Inputs",
        *_build_input_lines(requirement_items, analysis_sections),
        "",
        "## Outputs",
        *_build_output_lines(fused_payload, requirement_items),
        "",
        "## Constraints",
        *_build_constraint_lines(fused_payload, requirement_items),
        "",
        "## Acceptance Criteria",
        *_build_acceptance_lines(requirement_items, analysis_sections, fused_payload),
        "",
        "## Analysis Traceability",
        *_build_traceability_lines(analysis_sections),
        "",
        "## Non-Goals",
        *_build_non_goal_lines(requirement_items),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ensure_runtime()
    fused_payload = _read_required_payload(STEP6_FUSED_CONTEXT_FILE)
    step7_payload = _read_required_payload(STEP7_DECOMPOSED_REQUIREMENTS_FILE)
    analysis_markdown = read_text(STEP8_REQUIREMENT_ANALYSIS_FILE)
    markdown = build_markdown(fused_payload, step7_payload, analysis_markdown)
    write_text(STEP9_REQUIREMENT_SPEC_FILE, markdown)
    print_output("step9 完成", STEP9_REQUIREMENT_SPEC_FILE)


if __name__ == "__main__":
    main()
