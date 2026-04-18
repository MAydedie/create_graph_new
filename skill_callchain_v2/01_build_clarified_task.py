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


assess_clarification: Callable[..., dict] = _load_attr("adapters.clarification_adapter", "assess_clarification")
ensure_runtime: Callable[[], Path] = _load_attr("common", "ensure_runtime")
print_output: Callable[[str, Path], None] = _load_attr("common", "print_output")
read_text: Callable[[Path], str] = _load_attr("common", "read_text")
write_json: Callable[[Path, Any], None] = _load_attr("common", "write_json")
utc_now: Callable[[], str] = _load_attr("common", "utc_now")
STEP1_CLARIFIED_TASK_FILE: Path = _load_attr("config", "STEP1_CLARIFIED_TASK_FILE")
TASK_INPUT_FILE: Path = _load_attr("config", "TASK_INPUT_FILE")


PIPELINE_CONSTRAINT_KEYWORDS = (
    "error gate",
    "demand gate",
    "feedback",
    "finalize",
    "需求比对",
    "双检测",
    "落盘",
    "中间文件",
    ".skill",
    "导出",
)


def build_payload(raw_task: str) -> dict:
    normalized_task = raw_task.strip()
    result = assess_clarification(normalized_task, clarification_context=None, has_context=False)
    structured_requirement = dict(result.get("structured_requirement") or {})
    labeled_fields = _extract_labeled_fields(normalized_task)
    missing_slots = list(result.get("missing_slots") or [])

    if labeled_fields.get("goal"):
        structured_requirement["goal"] = labeled_fields["goal"]
    elif not structured_requirement.get("goal"):
        structured_requirement["goal"] = result.get("inferred_intent") or normalized_task

    if labeled_fields.get("target"):
        structured_requirement["target"] = labeled_fields["target"]
    elif not structured_requirement.get("target"):
        structured_requirement["target"] = ""

    if labeled_fields.get("expected_output"):
        structured_requirement["expected_output"] = labeled_fields["expected_output"]
    elif not structured_requirement.get("expected_output"):
        structured_requirement["expected_output"] = ""

    constraints = labeled_fields.get("constraints") or structured_requirement.get("constraints") or []
    if not isinstance(constraints, list):
        constraints = [str(constraints)] if str(constraints).strip() else []
    cleaned_constraints = [str(item).strip() for item in constraints if str(item).strip()]
    domain_constraints, pipeline_constraints = _split_constraints(cleaned_constraints)
    structured_requirement["constraints"] = cleaned_constraints
    structured_requirement["domain_constraints"] = domain_constraints
    structured_requirement["pipeline_constraints"] = pipeline_constraints

    return {
        "version": "v2.phase_a",
        "step": "build_clarified_task",
        "created_at": utc_now(),
        "input_file": str(TASK_INPUT_FILE),
        "raw_task": normalized_task,
        "route": result.get("route") or "clarify",
        "task_mode": result.get("task_mode") or "modify_existing",
        "confidence": result.get("confidence") or 0.0,
        "reason": result.get("reason") or "",
        "inferred_intent": result.get("inferred_intent") or normalized_task,
        "missing_slots": missing_slots,
        "structured_requirement": structured_requirement,
        "ready_for_next_step": len(missing_slots) == 0,
        "original_clarification_payload": result.get("original_clarification_payload") or {},
    }


def _split_constraints(constraints: list[str]) -> tuple[list[str], list[str]]:
    domain_constraints: list[str] = []
    pipeline_constraints: list[str] = []
    for raw_item in constraints:
        item = raw_item.strip()
        if not item:
            continue
        if _is_pipeline_constraint(item):
            pipeline_constraints.append(item)
        else:
            domain_constraints.append(item)
    return domain_constraints, pipeline_constraints


def _is_pipeline_constraint(constraint: str) -> bool:
    normalized = constraint.lower().strip()
    return any(keyword in normalized for keyword in PIPELINE_CONSTRAINT_KEYWORDS)


def _extract_labeled_fields(raw_task: str) -> dict[str, Any]:
    field_map = {
        "goal": ["目标", "goal"],
        "target": ["位置", "目标位置", "target"],
        "expected_output": ["预期结果", "期望结果", "expected_output"],
        "constraints": ["约束/指标", "约束", "constraints"],
    }
    extracted: dict[str, Any] = {}
    for logical_name, labels in field_map.items():
        value = _extract_first_label_value(raw_task, labels)
        if not value:
            continue
        if logical_name == "constraints":
            extracted[logical_name] = [item.strip() for item in re.split(r"[；;\n]+", value) if item.strip()]
        else:
            extracted[logical_name] = value
    return extracted


def _extract_first_label_value(raw_task: str, labels: list[str]) -> str:
    for raw_line in raw_task.splitlines():
        line = raw_line.strip()
        for label in labels:
            prefix = f"{label}："
            alt_prefix = f"{label}:"
            if line.startswith(prefix):
                return line[len(prefix):].strip()
            if line.startswith(alt_prefix):
                return line[len(alt_prefix):].strip()
    return ""


def main() -> None:
    ensure_runtime()
    raw_task = read_text(TASK_INPUT_FILE)
    payload = build_payload(raw_task)
    write_json(STEP1_CLARIFIED_TASK_FILE, payload)
    print_output("step1 完成", STEP1_CLARIFIED_TASK_FILE)


if __name__ == "__main__":
    main()
