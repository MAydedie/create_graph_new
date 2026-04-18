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
write_json: Callable[[Path, Any], None] = _load_attr("common", "write_json")
STEP1_CLARIFIED_TASK_FILE: Path = _load_attr("config", "STEP1_CLARIFIED_TASK_FILE")
STEP9_REQUIREMENT_SPEC_FILE: Path = _load_attr("config", "STEP9_REQUIREMENT_SPEC_FILE")
STEP13_TEST_REPORT_FILE: Path = _load_attr("config", "STEP13_TEST_REPORT_FILE")
STEP14_ERROR_REPORT_FILE: Path = _load_attr("config", "STEP14_ERROR_REPORT_FILE")
STEP15_DEMAND_REPORT_FILE: Path = _load_attr("config", "STEP15_DEMAND_REPORT_FILE")


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text)]


def _contains(spec_text: str, value: str) -> bool:
    value = str(value).strip()
    return bool(value) and value in spec_text


def build_report(step1_payload: dict[str, Any], spec_text: str, test_report: dict[str, Any], error_report: dict[str, Any]) -> dict[str, Any]:
    structured = step1_payload.get("structured_requirement") or {}
    blocking_errors = error_report.get("blocking_errors") or []
    test_summary = test_report.get("summary") or {}
    blocking_test_failures = int(test_summary.get("blocking_failures") or 0)

    checks = {
        "goal": _contains(spec_text, structured.get("goal") or ""),
        "target": _contains(spec_text, structured.get("target") or ""),
        "expected_output": _contains(spec_text, structured.get("expected_output") or ""),
    }
    constraint_checks = []
    for item in structured.get("constraints") or []:
        normalized = str(item).strip()
        if not normalized:
            continue
        constraint_checks.append({"text": normalized, "matched": _contains(spec_text, normalized)})

    satisfied_requirements = [key for key, matched in checks.items() if matched]
    missing_requirements = [key for key, matched in checks.items() if not matched]
    partially_satisfied = [item["text"] for item in constraint_checks if not item["matched"]]
    is_requirement_satisfied = (not blocking_errors) and (blocking_test_failures == 0) and (len(missing_requirements) == 0) and (len(partially_satisfied) == 0)

    why = []
    if blocking_errors:
        why.append("存在 blocking errors，需求不能判定为满足。")
    if blocking_test_failures > 0:
        why.append("step13 存在 blocking 级别测试失败。")
    if missing_requirements:
        why.append(f"规格说明书中缺少关键字段覆盖：{', '.join(missing_requirements)}。")
    if partially_satisfied:
        why.append(f"仍有约束未被规格说明书覆盖：{', '.join(partially_satisfied)}。")
    if not why:
        why.append("核心目标、目标位置、预期输出与约束均已被规格说明书覆盖，且无 blocking errors。")

    return {
        "step": "step15_demand_gate",
        "generated_at": utc_now(),
        "input_files": [
            str(STEP1_CLARIFIED_TASK_FILE),
            str(STEP9_REQUIREMENT_SPEC_FILE),
            str(STEP13_TEST_REPORT_FILE),
            str(STEP14_ERROR_REPORT_FILE),
        ],
        "is_requirement_satisfied": is_requirement_satisfied,
        "satisfied_requirements": satisfied_requirements,
        "missing_requirements": missing_requirements,
        "partially_satisfied_requirements": partially_satisfied,
        "constraint_checks": constraint_checks,
        "why": why,
    }


def main() -> None:
    ensure_runtime()
    report = build_report(
        read_json(STEP1_CLARIFIED_TASK_FILE),
        read_text(STEP9_REQUIREMENT_SPEC_FILE),
        read_json(STEP13_TEST_REPORT_FILE),
        read_json(STEP14_ERROR_REPORT_FILE),
    )
    write_json(STEP15_DEMAND_REPORT_FILE, report)
    print_output("step15 完成", STEP15_DEMAND_REPORT_FILE)


if __name__ == "__main__":
    main()
