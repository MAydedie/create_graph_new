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
STEP4_Y_SEMANTIC_CONTEXT_FILE: Path = _load_optional_config_path(
    "STEP4_Y_SEMANTIC_CONTEXT_FILE",
    "step4_y_semantic_context.json",
)
XYZ_TOP_N = _load_optional_config_int("XYZ_TOP_N", 5)


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
    "比对",
    "需求比对",
    "落盘",
    "中间文件",
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
    return _dedupe_strings(
        [
            skill.get("skill_id"),
            skill.get("partition_id"),
            skill.get("partition_name"),
            skill.get("name"),
            skill.get("summary"),
            skill.get("what"),
            skill.get("when_to_use"),
            skill.get("description"),
            *(_string_list(skill.get("tags"))),
            *(_string_list(skill.get("methods"))),
            *(_string_list(skill.get("inputs"))),
            *(_string_list(skill.get("outputs"))),
            *(_string_list(skill.get("caution"))),
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
        "overlap_tokens": overlap_tokens,
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


def _functional_description(skill: dict[str, Any]) -> str:
    call_chain = _string_list(skill.get("method_call_chain"))
    if len(call_chain) >= 2:
        preview = " -> ".join(call_chain[:4])
        return f"调用链主线：{preview}。用于把任务输入逐步映射到可执行代码落点。"
    chain_explanation = _string_list(skill.get("chain_explanation"))
    if chain_explanation:
        return chain_explanation[0]
    methods = _string_list(skill.get("methods"))
    if methods:
        return f"围绕以下方法族提供能力：{', '.join(methods[:4])}。"
    return "该技能用于承接当前任务相关分区的功能理解与后续实现判断。"


def _use_conditions(skill: dict[str, Any]) -> list[str]:
    partition_summary = skill.get("partition_summary") or {}
    methods = _string_list(skill.get("methods"))
    results = _dedupe_strings([
        skill.get("when_to_use"),
        f"相关方法：{', '.join(methods[:4])}" if methods else "",
        f"已有 {int(partition_summary.get('path_count') or 0)} 条路径证据可供后续验证。"
        if int(partition_summary.get("path_count") or 0) > 0
        else "",
        f"分析状态：{_stringify(partition_summary.get('analysis_status'))}。"
        if _stringify(partition_summary.get("analysis_status"))
        else "",
    ])
    return results or ["当任务与该技能分区功能相近、且需要轻量上下文时使用。"]


def _caution_items(skill: dict[str, Any]) -> list[str]:
    partition_summary = skill.get("partition_summary") or {}
    evidence_summary = skill.get("evidence_summary") or {}
    results = _dedupe_strings(_string_list(skill.get("caution")))
    analysis_status = _stringify(partition_summary.get("analysis_status"))
    if analysis_status and analysis_status != "complete":
        results.append(f"当前分析状态为 {analysis_status}，不要把轻量证据当作完整实现证明。")
    if int(evidence_summary.get("code_ref_count") or 0) == 0:
        results.append("当前缺少稳定源码证据，编码前应再次核实实际落点。")
    return results or ["保持轻量语义摘要，不要在本阶段做融合或大段源码搬运。"]


def _build_semantic_entries(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in selected:
        skill = item.get("skill") or {}
        entries.append(
            {
                "skill_id": item.get("skill_id"),
                "partition_id": item.get("partition_id"),
                "name": item.get("name"),
                "reasoning": item.get("reason"),
                "functional_description": _functional_description(skill),
                "chain_explanation": _string_list(skill.get("chain_explanation"))[:4],
                "method_call_chain": _string_list(skill.get("method_call_chain"))[:6],
                "use_conditions": _use_conditions(skill),
                "caution_items": _caution_items(skill),
                "input_contract": _string_list(skill.get("inputs")),
                "output_contract": _string_list(skill.get("outputs")),
            }
        )
    return entries


def build_report(task_payload: dict[str, Any], skills_payload: dict[str, Any]) -> dict[str, Any]:
    skills = skills_payload.get("skills") or []
    selected = _select_skills(task_payload, skills, XYZ_TOP_N)
    structured_requirement = task_payload.get("structured_requirement") or {}
    domain_constraints = _string_list(structured_requirement.get("domain_constraints") or structured_requirement.get("constraints"))
    pipeline_constraints = _string_list(structured_requirement.get("pipeline_constraints"))

    return {
        "version": "v2.work_order_c",
        "step": "build_y_semantic_context",
        "generated_at": utc_now(),
        "input_files": [
            str(STEP1_CLARIFIED_TASK_FILE),
            str(GENERATED_SKILLS_FILE),
        ],
        "selection_policy": "deterministic_keyword_overlap_plus_evidence",
        "reasoning": "按澄清任务关键词重叠、直接命中与轻量证据量排序，稳定选出语义上下文候选。",
        "task_digest": {
            "goal": _stringify(structured_requirement.get("goal")),
            "target": _stringify(structured_requirement.get("target")),
            "expected_output": _stringify(structured_requirement.get("expected_output")),
            "constraints": domain_constraints,
            "pipeline_constraints": pipeline_constraints,
        },
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
        "semantic_context": _build_semantic_entries(selected),
    }


def main() -> None:
    ensure_runtime()
    task_payload = read_json(STEP1_CLARIFIED_TASK_FILE)
    skills_payload = read_json(GENERATED_SKILLS_FILE)
    report = build_report(task_payload, skills_payload)
    write_json(STEP4_Y_SEMANTIC_CONTEXT_FILE, report)
    print_output("step4_y 完成", STEP4_Y_SEMANTIC_CONTEXT_FILE)


if __name__ == "__main__":
    main()
