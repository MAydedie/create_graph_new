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


RUNTIME_DIR = BASE_DIR / "runtime"
STEP6_FUSED_CONTEXT_FILE = RUNTIME_DIR / "step6_fused_context.json"
STEP7_DECOMPOSED_REQUIREMENTS_FILE = RUNTIME_DIR / "step7_decomposed_requirements.json"

IMPLEMENTATION_ROUTE_MARKERS = {
    "modify_existing",
    "create_new",
    "implement",
    "implementation",
    "build",
    "fix",
}
IMPLEMENTATION_TEXT_MARKERS = (
    "实现",
    "脚本",
    "模块",
    "代码",
    "测试",
    "build",
    "script",
    "module",
    "test",
)


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_as_str(item) for item in value if _as_str(item)]
    normalized = _as_str(value)
    return [normalized] if normalized else []


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _as_str(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _read_required_payload(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(payload).__name__}.")
    return payload


def _normalize_task_summary(payload: dict[str, Any]) -> dict[str, Any]:
    raw_task_summary = payload.get("task_summary") or {}
    next_stage_inputs = payload.get("next_stage_inputs") or {}
    next_stage_task_summary = next_stage_inputs.get("task_summary") or {}

    if not isinstance(raw_task_summary, dict):
        raw_task_summary = {}
    if not isinstance(next_stage_task_summary, dict):
        next_stage_task_summary = {}

    constraints = _dedupe_keep_order(
        _as_str_list(raw_task_summary.get("constraints"))
        + _as_str_list(next_stage_task_summary.get("constraints"))
    )

    return {
        "source_file": _as_str(raw_task_summary.get("source_file")),
        "raw_task": _as_str(raw_task_summary.get("raw_task")),
        "route": _as_str(raw_task_summary.get("route") or payload.get("route")),
        "task_mode": _as_str(raw_task_summary.get("task_mode") or payload.get("task_mode")),
        "goal": _as_str(raw_task_summary.get("goal") or next_stage_task_summary.get("goal")),
        "target": _as_str(raw_task_summary.get("target") or next_stage_task_summary.get("target")),
        "expected_output": _as_str(
            raw_task_summary.get("expected_output") or next_stage_task_summary.get("expected_output")
        ),
        "constraints": constraints,
    }


def _normalize_skill_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        skill_id = _as_str(item)
        if not skill_id:
            return None
        return {
            "skill_id": skill_id,
            "name": skill_id,
            "summary": "",
            "reasons": [],
            "source_count": 0,
            "max_score": 0.0,
        }

    if not isinstance(item, dict):
        return None

    skill_id = _as_str(item.get("skill_id") or item.get("id"))
    name = _as_str(item.get("name") or item.get("title") or skill_id)
    if not skill_id and not name:
        return None

    source_count_value = item.get("source_count")
    max_score_value = item.get("max_score")
    try:
        source_count = int(source_count_value or 0)
    except (TypeError, ValueError):
        source_count = 0
    try:
        max_score = float(max_score_value or 0.0)
    except (TypeError, ValueError):
        max_score = 0.0

    reasons = _as_str_list(item.get("reasons"))
    single_reason = _as_str(item.get("reason"))
    if single_reason:
        reasons = _dedupe_keep_order(reasons + [single_reason])

    return {
        "skill_id": skill_id,
        "name": name,
        "summary": _as_str(item.get("summary") or item.get("description")),
        "reasons": reasons,
        "source_count": source_count,
        "max_score": max_score,
    }


def _normalize_recommended_skills(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in payload.get("recommended_skills") or []:
        normalized = _normalize_skill_item(item)
        if normalized is not None:
            result.append(normalized)

    result.sort(
        key=lambda item: (
            -int(item.get("source_count") or 0),
            -float(item.get("max_score") or 0.0),
            item.get("skill_id") or "",
            item.get("name") or "",
        )
    )
    return result


def _collect_input_files(payload: dict[str, Any]) -> list[str]:
    collected: list[str] = [str(STEP6_FUSED_CONTEXT_FILE)]

    def append_value(value: Any) -> None:
        if isinstance(value, str):
            normalized = _as_str(value)
            if normalized:
                collected.append(normalized)
            return
        if isinstance(value, list):
            for item in value:
                append_value(item)
            return
        if isinstance(value, dict):
            for item in value.values():
                append_value(item)

    task_summary = payload.get("task_summary") or {}
    if isinstance(task_summary, dict):
        append_value(task_summary.get("source_file"))

    for context_key in ("path_context", "semantic_context", "code_context"):
        context_payload = payload.get(context_key) or {}
        if not isinstance(context_payload, dict):
            continue
        append_value(context_payload.get("source_file"))
        append_value((context_payload.get("context") or {}).get("input_files"))

    return _dedupe_keep_order(collected)


def _build_common_constraints(task_summary: dict[str, Any]) -> list[str]:
    return _dedupe_keep_order(
        _as_str_list(task_summary.get("constraints"))
        + [
            "保持确定性，禁止调用 LLM 或引入随机决策。",
            "仅使用本地文件输入与 JSON 落盘输出。",
            "只拆解当前任务，不预设未来阶段的额外前置依赖。",
            "不修改 skill_callchain_v2 之外的旧模块。",
        ]
    )


def _skill_stage_score(skill: dict[str, Any], keywords: tuple[str, ...]) -> tuple[int, int, float]:
    haystack = "\n".join(
        [
            _as_str(skill.get("skill_id")),
            _as_str(skill.get("name")),
            _as_str(skill.get("summary")),
            *(_as_str_list(skill.get("reasons"))),
        ]
    ).lower()
    score = 0
    for keyword in keywords:
        normalized = keyword.lower().strip()
        if normalized and normalized in haystack:
            score += 1
    return (
        score,
        int(skill.get("source_count") or 0),
        float(skill.get("max_score") or 0.0),
    )


def _select_skill_refs(
    skills: list[dict[str, Any]],
    keywords: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    ranked = sorted(
        skills,
        key=lambda skill: (
            -_skill_stage_score(skill, keywords)[0],
            -_skill_stage_score(skill, keywords)[1],
            -_skill_stage_score(skill, keywords)[2],
            skill.get("skill_id") or "",
            skill.get("name") or "",
        ),
    )
    selected = ranked[: max(1, min(limit, len(ranked)))] if ranked else []
    return [
        {
            "skill_id": _as_str(skill.get("skill_id")),
            "name": _as_str(skill.get("name")),
            "summary": _as_str(skill.get("summary")),
            "reason": _as_str((skill.get("reasons") or [""])[0]),
        }
        for skill in selected
    ]


def _needs_implementation_chain(task_summary: dict[str, Any]) -> bool:
    route_markers = {
        _as_str(task_summary.get("route")).lower(),
        _as_str(task_summary.get("task_mode")).lower(),
    }
    if route_markers.intersection(IMPLEMENTATION_ROUTE_MARKERS):
        return True

    combined_text = "\n".join(
        [
            _as_str(task_summary.get("goal")),
            _as_str(task_summary.get("target")),
            _as_str(task_summary.get("expected_output")),
            *(_as_str_list(task_summary.get("constraints"))),
        ]
    ).lower()
    return any(marker in combined_text for marker in IMPLEMENTATION_TEXT_MARKERS)


def _build_sub_requirements(
    task_summary: dict[str, Any],
    recommended_skills: list[dict[str, Any]],
    next_stage_inputs: dict[str, Any],
    input_files: list[str],
) -> list[dict[str, Any]]:
    common_constraints = _build_common_constraints(task_summary)
    next_stage_fields = [
        "task_summary",
        "recommended_skill_ids",
        "shared_skill_ids",
        "path_summary",
        "semantic_summary",
        "code_summary",
    ]

    sub_requirements: list[dict[str, Any]] = [
        {
            "id": "subreq_context_preparation",
            "title": "准备稳定输入上下文",
            "goal": "把任务摘要、约束和输入文件清单整理成后续文档链可直接消费的统一入口。",
            "input": {
                "files": input_files,
                "fused_context_fields": ["task_summary", "next_stage_inputs.task_summary"],
                "task_focus": {
                    "goal": _as_str(task_summary.get("goal")),
                    "target": _as_str(task_summary.get("target")),
                    "expected_output": _as_str(task_summary.get("expected_output")),
                },
            },
            "output": {
                "artifacts": [
                    "context_brief",
                    "constraint_profile",
                    "input_inventory",
                ],
                "handoff": "供后续 analysis/spec/design 脚本直接读取。",
            },
            "constraints": common_constraints,
            "dependencies": [],
            "skill_refs": _select_skill_refs(
                recommended_skills,
                ("澄清", "clarification", "context", "上下文", "task", "任务"),
                limit=2,
            ),
        },
        {
            "id": "subreq_skill_selection_context",
            "title": "整理技能选择与上下文锚点",
            "goal": "基于推荐技能和 next_stage_inputs 提炼稳定的 skill shortlist、上下文锚点与使用边界。",
            "input": {
                "files": input_files,
                "fused_context_fields": ["recommended_skills", "next_stage_inputs"],
                "next_stage_fields": [field for field in next_stage_fields if field in next_stage_inputs],
                "recommended_skill_ids": _dedupe_keep_order(
                    [
                        _as_str(skill.get("skill_id"))
                        for skill in recommended_skills
                        if _as_str(skill.get("skill_id"))
                    ]
                ),
            },
            "output": {
                "artifacts": [
                    "skill_shortlist",
                    "skill_context_packet",
                    "skill_usage_boundaries",
                ],
                "handoff": "供后续分析脚本和设计脚本复用，不重新推导 skill。",
            },
            "constraints": common_constraints
            + ["只使用 fused context 已给出的 recommended_skills，不额外发散新技能。"],
            "dependencies": ["subreq_context_preparation"],
            "skill_refs": _select_skill_refs(
                recommended_skills,
                ("skill", "技能", "path", "semantic", "code", "流程"),
                limit=3,
            ),
        },
        {
            "id": "subreq_design_document_chain",
            "title": "生成文档链需求",
            "goal": "把当前任务拆成 analysis/spec/design 三类文档脚本可执行的结构化关注点与产出边界。",
            "input": {
                "files": input_files,
                "fused_context_fields": ["task_summary", "recommended_skills", "next_stage_inputs"],
                "next_stage_fields": [field for field in next_stage_fields if field in next_stage_inputs],
                "task_focus": {
                    "goal": _as_str(task_summary.get("goal")),
                    "expected_output": _as_str(task_summary.get("expected_output")),
                    "constraints": _as_str_list(task_summary.get("constraints")),
                },
            },
            "output": {
                "artifacts": [
                    "analysis_topics",
                    "spec_outline",
                    "design_decision_scope",
                ],
                "handoff": "作为后续 analysis/spec/design 脚本的直接输入骨架。",
            },
            "constraints": common_constraints
            + ["文档链只描述当前任务范围，不把实现细节提前绑定为既定方案。"],
            "dependencies": [
                "subreq_context_preparation",
                "subreq_skill_selection_context",
            ],
            "skill_refs": _select_skill_refs(
                recommended_skills,
                ("流程", "summary", "context", "文档", "分析", "设计", "step"),
                limit=3,
            ),
        },
    ]

    if _needs_implementation_chain(task_summary):
        sub_requirements.append(
            {
                "id": "subreq_implementation_testing_chain",
                "title": "提炼实现与测试关注点",
                "goal": "基于当前任务目标与预期结果，提前整理后续实现/测试阶段需要持续追踪的交付约束与验证要点。",
                "input": {
                    "files": input_files,
                    "fused_context_fields": ["task_summary", "recommended_skills", "next_stage_inputs"],
                    "task_focus": {
                        "route": _as_str(task_summary.get("route")),
                        "task_mode": _as_str(task_summary.get("task_mode")),
                        "expected_output": _as_str(task_summary.get("expected_output")),
                        "constraints": _as_str_list(task_summary.get("constraints")),
                    },
                },
                "output": {
                    "artifacts": [
                        "implementation_focus",
                        "test_focus",
                        "completion_gates",
                    ],
                    "handoff": "仅生成实现/测试关注点，不直接依赖未来实现阶段产物。",
                },
                "constraints": common_constraints
                + ["实现与测试链只提炼关注点，不提前假设未来阶段已经产出设计文档或代码结果。"],
                "dependencies": [
                    "subreq_context_preparation",
                    "subreq_skill_selection_context",
                ],
                "skill_refs": _select_skill_refs(
                    recommended_skills,
                    ("code", "实现", "测试", "runtime", "step", "核心"),
                    limit=2,
                ),
            }
        )

    return sub_requirements


def build_payload(fused_context: dict[str, Any]) -> dict[str, Any]:
    task_summary = _normalize_task_summary(fused_context)
    recommended_skills = _normalize_recommended_skills(fused_context)
    next_stage_inputs = fused_context.get("next_stage_inputs") or {}
    if not isinstance(next_stage_inputs, dict):
        next_stage_inputs = {}
    input_files = _collect_input_files(fused_context)
    sub_requirements = _build_sub_requirements(
        task_summary=task_summary,
        recommended_skills=recommended_skills,
        next_stage_inputs=next_stage_inputs,
        input_files=input_files,
    )

    return {
        "version": "v2.work_order_d",
        "step": "decompose_requirement",
        "generated_at": utc_now(),
        "input_files": input_files,
        "decomposition_strategy": {
            "name": "deterministic_stage_split_v1",
            "summary": "按稳定输入准备、技能上下文、文档链需求、实现测试关注点四段拆解。",
            "uses_fields": ["task_summary", "recommended_skills", "next_stage_inputs"],
            "ordering_principles": [
                "先固定任务上下文，再固定 skill/context，再展开文档链。",
                "仅依据 fused context 当前字段生成子需求，不引入未来阶段依赖。",
                "当任务包含实现信号时，附带实现与测试关注点子需求。",
            ],
            "implementation_testing_included": any(
                item.get("id") == "subreq_implementation_testing_chain" for item in sub_requirements
            ),
            "sub_requirement_count": len(sub_requirements),
        },
        "sub_requirements": sub_requirements,
    }


def main() -> None:
    ensure_runtime()
    fused_context = _read_required_payload(STEP6_FUSED_CONTEXT_FILE)
    payload = build_payload(fused_context)
    write_json(STEP7_DECOMPOSED_REQUIREMENTS_FILE, payload)
    print_output("step7 完成", STEP7_DECOMPOSED_REQUIREMENTS_FILE)


if __name__ == "__main__":
    main()
