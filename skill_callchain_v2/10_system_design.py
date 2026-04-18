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
write_text: Callable[[Path, str], None] = _load_attr("common", "write_text")
RUNTIME_DIR: Path = _load_attr("config", "RUNTIME_DIR")
STEP1_CLARIFIED_TASK_FILE: Path = _load_attr("config", "STEP1_CLARIFIED_TASK_FILE")


STEP6_FUSED_CONTEXT_FILE = RUNTIME_DIR / "step6_fused_context.json"
STEP10_SYSTEM_DESIGN_FILE = RUNTIME_DIR / "step10_system_design.md"

MODULE_GROUPS = (
    (
        "现有编排脚本",
        (
            ("01_build_clarified_task.py", "读取任务文本并生成结构化 requirement。"),
            ("02_prepare_phase6_contract.py", "导出可复用的 phase6 轻量 contract。"),
            ("02_generate_skill_library.py", "聚合 partition/path/code 证据并生成 skill 库。"),
            ("03_x_path_agent.py", "输出路径级 function chain 与分解线索。"),
            ("04_y_semantic_agent.py", "输出语义级 skill 上下文。"),
            ("05_z_code_agent.py", "输出代码证据与文件锚点。"),
            ("06_fuse_xyz_context.py", "融合 X/Y/Z 三侧上下文形成统一输入。"),
            ("config.py", "集中管理 runtime 路径与稳定参数。"),
            ("common.py", "提供 runtime 目录、JSON/Text 读写与时间戳能力。"),
            ("models.py", "定义 SkillCardV2、PathEvidence、CodeEvidence 数据结构。"),
        ),
    ),
    (
        "复用 adapters",
        (
            ("adapters/clarification_adapter.py", "承接前门澄清结果，不重新发明澄清逻辑。"),
            ("adapters/phase6_contract_adapter.py", "读取并裁剪 phase6 contract。"),
            ("adapters/hierarchy_adapter.py", "提取 partition/path evidence 与 entry points。"),
            ("adapters/code_reference_adapter.py", "把 method signature 解析为文件与代码片段锚点。"),
        ),
    ),
    (
        "复用 builders",
        (
            ("builders/build_skills_from_partitions.py", "基于 partition summaries 构建技能卡。"),
            ("builders/build_path_evidence.py", "归一化 path evidence。"),
            ("builders/build_code_evidence.py", "归一化 code evidence。"),
            ("builders/merge_skill_cards.py", "合并 skill/path/code 三类证据。"),
        ),
    ),
)

NEW_MODULES = (
    ("10_system_design.py", "读取 requirement spec 与 fused context，产出系统设计文档。"),
    ("11_detailed_design.py", "读取系统设计与分解结果，产出可直接编码的详细设计文档。"),
)

FUTURE_WORK_ORDER_E_FILES = (
    ("validators/runtime_contract_validator.py", "校验 step1、step6、step10、step11 与后续 codegen 输入是否齐备。"),
    ("adapters/codegen_context_adapter.py", "整合 design 文档、hierarchy 证据与代码引用，形成 codegen 上下文。"),
    ("builders/build_codegen_work_items.py", "把 detailed design 拆成 file-level / function-level work items。"),
    ("12_codegen_input.py", "落盘 runtime/step12_codegen_input.json，作为 Work Order E 的稳定输入。"),
    ("13_codegen_plan.py", "落盘 runtime/step13_codegen_plan.md，明确后续生成顺序与编辑边界。"),
)


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _as_str(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _read_required_payload(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(payload).__name__}.")
    return payload


def _existing_module_lines() -> list[str]:
    lines: list[str] = []
    for title, items in MODULE_GROUPS:
        lines.append(f"## {title}")
        for relative_path, responsibility in items:
            full_path = BASE_DIR / relative_path
            if full_path.exists():
                lines.append(f"- `{relative_path}`：{responsibility}")
        lines.append("")
    return lines


def _recommended_skill_lines(fused_payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in fused_payload.get("recommended_skills") or []:
        if not isinstance(item, dict):
            continue
        skill_name = _as_str(item.get("name") or item.get("skill_id"))
        reason_parts = _as_str_list(item.get("reasons"))
        source_count = int(item.get("source_count") or 0)
        max_score = float(item.get("max_score") or 0.0)
        if not skill_name:
            continue
        summary = _as_str(item.get("summary"))
        reason = reason_parts[0] if reason_parts else ""
        detail_parts = [part for part in [summary, reason] if part]
        detail = "；".join(detail_parts)
        lines.append(
            f"- `{skill_name}`：跨 {source_count} 个上下文源复用，max_score={max_score:.4f}；{detail}".rstrip("；")
        )
    return lines or ["- 无推荐 skill，系统设计应按本地目录结构兜底。"]


def _function_chain_lines(fused_payload: dict[str, Any]) -> list[str]:
    path_context = fused_payload.get("path_context") or {}
    context = path_context.get("context") or {}
    lines: list[str] = []
    for group in context.get("function_chain_groups") or []:
        if not isinstance(group, dict):
            continue
        skill_name = _as_str(group.get("skill_name") or group.get("partition_name") or group.get("skill_id"))
        for chain in group.get("chains") or []:
            if not isinstance(chain, dict):
                continue
            function_chain = _as_str_list(chain.get("function_chain"))
            if not function_chain:
                continue
            chain_text = " -> ".join(function_chain)
            lines.append(f"- `{skill_name}`：`{chain_text}`")
    return lines or ["- 无 function chain，可在后续分解阶段补全。"]


def _code_anchor_lines(fused_payload: dict[str, Any]) -> list[str]:
    code_context = fused_payload.get("code_context") or {}
    context = code_context.get("context") or {}
    lines: list[str] = []
    for item in context.get("code_context") or []:
        if not isinstance(item, dict):
            continue
        skill_name = _as_str(item.get("name") or item.get("skill_id"))
        for evidence in item.get("source_evidence") or []:
            if not isinstance(evidence, dict):
                continue
            file_path = _as_str(evidence.get("file_path"))
            method_signature = _as_str(evidence.get("method_signature"))
            if file_path or method_signature:
                lines.append(f"- `{skill_name}`：`{file_path}` / `{method_signature}`")
    return lines or ["- 无源码锚点，后续实现需优先补充 code references。"]


def build_markdown(step1_payload: dict[str, Any], fused_payload: dict[str, Any]) -> str:
    structured_requirement = step1_payload.get("structured_requirement") or {}
    next_stage_inputs = fused_payload.get("next_stage_inputs") or {}
    task_summary = fused_payload.get("task_summary") or {}

    lines = [
        "# Work Order D System Design",
        "",
        "## Design Basis",
        f"- Generated at：`{utc_now()}`",
        f"- Requirement source：`runtime/{STEP1_CLARIFIED_TASK_FILE.name}`",
        f"- Fused context source：`runtime/{STEP6_FUSED_CONTEXT_FILE.name}`",
        f"- Goal：{_as_str(structured_requirement.get('goal') or task_summary.get('goal'))}",
        f"- Target：{_as_str(structured_requirement.get('target') or task_summary.get('target'))}",
        f"- Expected output：{_as_str(structured_requirement.get('expected_output') or task_summary.get('expected_output'))}",
    ]

    constraints = _as_str_list(structured_requirement.get("constraints") or task_summary.get("constraints"))
    if constraints:
        lines.append("- Constraints：")
        lines.extend([f"  - {item}" for item in constraints])
    else:
        lines.append("- Constraints：无额外约束。")

    lines.extend(
        [
            "",
            "## System Boundary",
            "- In scope：基于 `step1_clarified_task.json` 与 `step6_fused_context.json` 产出可执行的系统设计与详细设计文档。",
            "- Out of scope：不实现 codegen、不调用 LLM、不修改旧主链文件、不做测试编排。",
            "- Runtime contract：所有中间结果继续落盘到 `skill_callchain_v2/runtime`。",
            "",
            "## Recommended Skills",
            *(_recommended_skill_lines(fused_payload)),
            "",
            "## Data Flow",
            "- `task_input.txt` -> `01_build_clarified_task.py` -> `runtime/step1_clarified_task.json`，提供 goal/target/expected_output/constraints。",
            "- `02_prepare_phase6_contract.py` + `02_generate_skill_library.py` -> `runtime/generated_skills.json`，提供 skill、partition、path/code evidence。",
            "- `03_x_path_agent.py` / `04_y_semantic_agent.py` / `05_z_code_agent.py` -> `runtime/step3_x_path_context.json`、`runtime/step4_y_semantic_context.json`、`runtime/step5_z_code_context.json`。",
            "- `06_fuse_xyz_context.py` -> `runtime/step6_fused_context.json`，统一 task summary、recommended skills、path/semantic/code context。",
            "- `10_system_design.py` 消费 requirement spec + fused context -> `runtime/step10_system_design.md`。",
            "- `11_detailed_design.py` 消费 system design + decomposition output -> `runtime/step11_detailed_design.md`，供 Work Order E 直接执行。",
            "",
            "## Function Chains",
            *(_function_chain_lines(fused_payload)),
            "",
            "## Code Anchors",
            *(_code_anchor_lines(fused_payload)),
            "",
        ]
    )

    lines.extend(_existing_module_lines())

    lines.extend(
        [
            "## 新增模块（本工单）",
            *[f"- `{path}`：{responsibility}" for path, responsibility in NEW_MODULES],
            "",
            "## Future Work Order E Files",
            *[f"- `{path}`：{responsibility}" for path, responsibility in FUTURE_WORK_ORDER_E_FILES],
            "",
            "## Output Contracts",
            "- `runtime/step10_system_design.md`：模块边界、数据流、复用点、新增点与 Work Order E 交接范围。",
            "- `runtime/step11_detailed_design.md`：面向编码执行的文件级/函数级实施说明。",
            "- `runtime/step12_codegen_input.json`：建议作为 Work Order E 的稳定 machine-readable 输入。",
            "- `runtime/step13_codegen_plan.md`：建议作为 Work Order E 的人工审阅与执行顺序说明。",
            "",
            "## Handoff Notes",
            f"- Shared skill ids：{', '.join(_as_str_list(fused_payload.get('shared_skill_ids')))}",
            f"- Next-stage summaries：path=`{_as_str(next_stage_inputs.get('path_summary'))}`；semantic=`{_as_str(next_stage_inputs.get('semantic_summary'))}`；code=`{_as_str(next_stage_inputs.get('code_summary'))}`。",
            "- Work Order E 应优先复用现有 adapters/builders/common/config，不新增平行实现。",
            "- Work Order E 如需 validators，应只校验 v2 runtime 与文档产物，不扩散到旧系统。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    ensure_runtime()
    step1_payload = _read_required_payload(STEP1_CLARIFIED_TASK_FILE)
    fused_payload = _read_required_payload(STEP6_FUSED_CONTEXT_FILE)
    markdown = build_markdown(step1_payload, fused_payload)
    write_text(STEP10_SYSTEM_DESIGN_FILE, markdown)
    print_output("step10 完成", STEP10_SYSTEM_DESIGN_FILE)


if __name__ == "__main__":
    main()
