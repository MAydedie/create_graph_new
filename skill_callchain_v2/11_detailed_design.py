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


ensure_runtime: Callable[[], Path] = _load_attr("common", "ensure_runtime")
print_output: Callable[[str, Path], None] = _load_attr("common", "print_output")
read_json: Callable[[Path], Any] = _load_attr("common", "read_json")
read_text: Callable[[Path], str] = _load_attr("common", "read_text")
utc_now: Callable[[], str] = _load_attr("common", "utc_now")
write_text: Callable[[Path, str], None] = _load_attr("common", "write_text")
RUNTIME_DIR: Path = _load_attr("config", "RUNTIME_DIR")


STEP10_SYSTEM_DESIGN_FILE = RUNTIME_DIR / "step10_system_design.md"
STEP11_DETAILED_DESIGN_FILE = RUNTIME_DIR / "step11_detailed_design.md"
DECOMPOSITION_CANDIDATE_FILES = (
    RUNTIME_DIR / "step9_task_decomposition.json",
    RUNTIME_DIR / "step9_decomposition.json",
    RUNTIME_DIR / "step8_module_decomposition.json",
    RUNTIME_DIR / "step8_decomposition.json",
    RUNTIME_DIR / "step7_requirement_decomposition.json",
    RUNTIME_DIR / "step7_decomposition.json",
    RUNTIME_DIR / "step3_x_path_context.json",
)

SYSTEM_FILE_PRIORITY = (
    "config.py",
    "common.py",
    "06_fuse_xyz_context.py",
    "adapters/hierarchy_adapter.py",
    "adapters/code_reference_adapter.py",
    "builders/build_path_evidence.py",
    "builders/build_code_evidence.py",
)

FUTURE_FILE_GUIDANCE = (
    (
        "validators/runtime_contract_validator.py",
        "在 Work Order E 前统一校验 `step1`、分解结果、`step10`、`step11` 是否存在且 schema/章节齐全。",
        (
            "validate_required_runtime_files()：校验必需 runtime 文件是否存在。",
            "validate_json_payload()：校验 decomposition / codegen 输入是否为稳定 JSON 对象。",
            "validate_markdown_sections()：校验 system design / detailed design 是否包含关键标题。",
        ),
    ),
    (
        "adapters/codegen_context_adapter.py",
        "把详细设计、系统设计、hierarchy 证据与 code references 组装成统一 codegen context。",
        (
            "load_design_inputs()：读取 `step10_system_design.md`、`step11_detailed_design.md` 与 decomposition payload。",
            "collect_partition_context()：复用 `adapters/hierarchy_adapter.py` 收集 partition/path context。",
            "build_codegen_context()：输出稳定字段，避免下游直接解析 Markdown。",
        ),
    ),
    (
        "builders/build_codegen_work_items.py",
        "把 file-level / function-level 设计说明拆成稳定 work items，供后续代码生成或补丁生成复用。",
        (
            "extract_file_targets()：从 detailed design 中提取目标文件与职责。",
            "extract_function_targets()：从 decomposition anchors 中提取函数级任务。",
            "build_work_items()：合并文件任务、函数任务、约束与参考证据。",
        ),
    ),
    (
        "12_codegen_input.py",
        "生成 Work Order E 的 machine-readable 输入文件。",
        (
            "build_payload()：聚合 validator/adapters/builders 的输出。",
            "main()：写出 `runtime/step12_codegen_input.json`。",
        ),
    ),
    (
        "13_codegen_plan.py",
        "生成人类可审阅的代码生成执行计划，明确编辑顺序与回退边界。",
        (
            "build_markdown()：把 work items 转为简洁 Markdown 计划。",
            "main()：写出 `runtime/step13_codegen_plan.md`。",
        ),
    ),
)

FILE_REF_PATTERN = re.compile(r"`([^`\n]+(?:\.py|\.json|\.md))`")


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


def _read_required_markdown(path: Path) -> str:
    text = read_text(path)
    if not text.strip():
        raise ValueError(f"Expected non-empty markdown in {path}.")
    return text


def _read_required_payload(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(payload).__name__}.")
    return payload


def _pick_decomposition_source() -> tuple[Path, dict[str, Any]]:
    for candidate in DECOMPOSITION_CANDIDATE_FILES:
        if candidate.exists():
            return candidate, _read_required_payload(candidate)
    filenames = ", ".join(path.name for path in DECOMPOSITION_CANDIDATE_FILES)
    raise FileNotFoundError(f"No decomposition payload found under runtime. Checked: {filenames}")


def _collect_file_refs(markdown: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for match in FILE_REF_PATTERN.findall(markdown):
        normalized = _as_str(match)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _prioritized_existing_files(system_design_refs: list[str]) -> list[str]:
    combined = list(SYSTEM_FILE_PRIORITY) + system_design_refs
    result: list[str] = []
    seen: set[str] = set()
    for relative_path in combined:
        normalized = _as_str(relative_path)
        if not normalized or normalized in seen:
            continue
        if (BASE_DIR / normalized).exists():
            seen.add(normalized)
            result.append(normalized)
    return result


def _extract_function_anchors(payload: dict[str, Any]) -> list[str]:
    anchors: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        normalized = _as_str(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            anchors.append(normalized)

    for group in payload.get("function_chain_groups") or []:
        if not isinstance(group, dict):
            continue
        for chain in group.get("chains") or []:
            if not isinstance(chain, dict):
                continue
            for function_name in chain.get("function_chain") or []:
                add(function_name)

    for step in payload.get("path_steps") or []:
        if isinstance(step, dict):
            add(step.get("function_name"))

    for key in ("tasks", "work_items", "function_tasks", "items"):
        for item in payload.get(key) or []:
            if not isinstance(item, dict):
                continue
            add(item.get("function_name"))
            add(item.get("method_signature"))
            add(item.get("symbol"))

    return anchors


def _extract_target_files(payload: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        normalized = _as_str(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            targets.append(normalized)

    for key in ("target_files", "files", "file_targets"):
        for item in payload.get(key) or []:
            if isinstance(item, str):
                add(item)
            elif isinstance(item, dict):
                add(item.get("file_path") or item.get("target_file") or item.get("path"))

    return targets


def build_markdown(system_design_markdown: str, decomposition_path: Path, decomposition_payload: dict[str, Any]) -> str:
    system_design_refs = _collect_file_refs(system_design_markdown)
    existing_files = _prioritized_existing_files(system_design_refs)
    decomposition_targets = _extract_target_files(decomposition_payload)
    anchors = _extract_function_anchors(decomposition_payload)

    lines = [
        "# Work Order D Detailed Design",
        "",
        "## Input Baseline",
        f"- Generated at：`{utc_now()}`",
        f"- System design source：`runtime/{STEP10_SYSTEM_DESIGN_FILE.name}`",
        f"- Decomposition source：`runtime/{decomposition_path.name}`",
        "- Goal：把系统设计收敛为可直接编码的文件级与函数级说明，供 Work Order E 复用。",
        "- Guardrails：不实现 codegen、不引入 LLM、不修改旧系统文件，仅围绕 `skill_callchain_v2` 规划后续落点。",
        "",
        "## File-Level Guidance",
    ]

    for relative_path in existing_files:
        responsibility = {
            "config.py": "继续作为 runtime 路径与参数中心，后续 step12/step13 常量应优先放在这里。",
            "common.py": "继续复用 `ensure_runtime`、`read_json`、`write_json`、`write_text`，避免重复 I/O 封装。",
            "06_fuse_xyz_context.py": "保留为上游统一输入边界，Work Order E 不应绕过 fused context 重新拼装需求。",
            "adapters/hierarchy_adapter.py": "继续提供 partition/path evidence 与 entry points，支撑 file/function 任务拆解。",
            "adapters/code_reference_adapter.py": "继续提供 method -> file/snippet 锚点，支撑后续精确改动定位。",
            "builders/build_path_evidence.py": "继续提供稳定 path evidence 归一化，避免 Work Order E 直接读原始 hierarchy。",
            "builders/build_code_evidence.py": "继续提供稳定 code evidence 归一化，避免 Work Order E 直接读杂散源码证据。",
        }.get(relative_path, "作为现有实现基座复用，不再新增平行职责。")
        lines.append(f"- `{relative_path}`：{responsibility}")

    if decomposition_targets:
        lines.append(f"- 分解结果显式目标文件：{', '.join(f'`{item}`' for item in decomposition_targets[:8])}")

    lines.extend(["", "## Function-Level Guidance"])
    for relative_path, purpose, function_guidance in FUTURE_FILE_GUIDANCE:
        function_text = "；".join(function_guidance)
        lines.append(f"- `{relative_path}`：{purpose}；建议函数：{function_text}")

    lines.extend(["", "## Existing Function Anchors"])
    if anchors:
        for item in anchors[:12]:
            lines.append(f"- `{item}`：保持为既有语义锚点，后续 codegen 只能围绕其输入/输出契约延展。")
    else:
        lines.append("- 无现成 function anchors，Work Order E 需要先补充分解结果再进入代码生成。")

    lines.extend(
        [
            "",
            "## Work Order E Sequence",
            "- 先执行 `validators/runtime_contract_validator.py`，确保 `step10`、`step11` 与 decomposition 输入齐备。",
            "- 再执行 `adapters/codegen_context_adapter.py`，统一文档与 evidence 输入。",
            "- 然后执行 `builders/build_codegen_work_items.py`，产出稳定 file/function work items。",
            "- 最后由 `12_codegen_input.py` 与 `13_codegen_plan.py` 落盘，作为代码生成前的最终桥接层。",
            "",
            "## Coding Notes",
            "- 所有新文件仍放在 `skill_callchain_v2` 目录树内，避免回写旧系统路径。",
            "- 需要 adapters/builders/validators 时，优先复用已有目录风格、导入模式与 `main()` 入口结构。",
            "- Markdown 计划保持短标题 + 简洁 bullet；JSON 输入保持 deterministic key layout。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    ensure_runtime()
    system_design_markdown = _read_required_markdown(STEP10_SYSTEM_DESIGN_FILE)
    decomposition_path, decomposition_payload = _pick_decomposition_source()
    markdown = build_markdown(system_design_markdown, decomposition_path, decomposition_payload)
    write_text(STEP11_DETAILED_DESIGN_FILE, markdown)
    print_output("step11 完成", STEP11_DETAILED_DESIGN_FILE)


if __name__ == "__main__":
    main()
