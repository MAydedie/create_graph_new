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
read_text: Callable[[Path], str] = _load_attr("common", "read_text")
utc_now: Callable[[], str] = _load_attr("common", "utc_now")
write_json: Callable[[Path, Any], None] = _load_attr("common", "write_json")
STEP10_SYSTEM_DESIGN_FILE: Path = _load_attr("config", "STEP10_SYSTEM_DESIGN_FILE")
STEP11_DETAILED_DESIGN_FILE: Path = _load_attr("config", "STEP11_DETAILED_DESIGN_FILE")
STEP12_CODEGEN_RESULT_FILE: Path = _load_attr("config", "STEP12_CODEGEN_RESULT_FILE")


FILE_REF_PATTERN = re.compile(r"`([^`\n]+(?:\.py|\.json|\.md))`")
FUNC_PATTERN = re.compile(r"([A-Za-z0-9_./]+\.[A-Za-z_][A-Za-z0-9_]*)")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _extract_file_refs(*texts: str) -> list[str]:
    refs: list[str] = []
    for text in texts:
        refs.extend(FILE_REF_PATTERN.findall(text))
    return _dedupe(refs)


def _extract_function_targets(*texts: str) -> list[str]:
    targets: list[str] = []
    for text in texts:
        targets.extend(FUNC_PATTERN.findall(text))
    return _dedupe(targets)


def _build_work_items(file_refs: list[str], function_targets: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, file_ref in enumerate(file_refs, start=1):
        related_functions = [item for item in function_targets if file_ref.replace("/", ".").replace(".py", "") in item]
        items.append(
            {
                "item_id": f"work_item_{index:02d}",
                "target_file": file_ref,
                "purpose": "将详细设计中的文件职责转成后续代码生成的稳定输入。",
                "related_functions": related_functions,
                "status": "planned",
            }
        )
    return items


def build_payload(system_design_markdown: str, detailed_design_markdown: str) -> dict[str, Any]:
    file_refs = _extract_file_refs(system_design_markdown, detailed_design_markdown)
    function_targets = _extract_function_targets(detailed_design_markdown)
    return {
        "step": "step12_codegen",
        "generated_at": utc_now(),
        "input_files": [
            str(STEP10_SYSTEM_DESIGN_FILE),
            str(STEP11_DETAILED_DESIGN_FILE),
        ],
        "implementation_scope": {
            "mode": "planned_only",
            "note": "本阶段只生成 machine-readable codegen 结果，不真正改代码。",
        },
        "target_files": file_refs,
        "function_targets": function_targets,
        "guardrails": [
            "不调用 LLM",
            "不真正编辑代码",
            "只把详细设计转成稳定 work items",
            "保持结果可供后续测试与需求对齐使用",
        ],
        "work_items": _build_work_items(file_refs, function_targets),
    }


def main() -> None:
    ensure_runtime()
    payload = build_payload(read_text(STEP10_SYSTEM_DESIGN_FILE), read_text(STEP11_DETAILED_DESIGN_FILE))
    write_json(STEP12_CODEGEN_RESULT_FILE, payload)
    print_output("step12 完成", STEP12_CODEGEN_RESULT_FILE)


if __name__ == "__main__":
    main()
