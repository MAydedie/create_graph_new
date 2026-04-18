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
STEP14_ERROR_REPORT_FILE: Path = _load_attr("config", "STEP14_ERROR_REPORT_FILE")
STEP15_DEMAND_REPORT_FILE: Path = _load_attr("config", "STEP15_DEMAND_REPORT_FILE")
STEP16_FEEDBACK_ACTION_FILE: Path = _load_attr("config", "STEP16_FEEDBACK_ACTION_FILE")


def build_report(error_report: dict[str, Any], demand_report: dict[str, Any]) -> dict[str, Any]:
    blocking_errors = error_report.get("blocking_errors") or []
    syntax_errors = error_report.get("syntax_errors") or []
    is_requirement_satisfied = bool(demand_report.get("is_requirement_satisfied"))

    if syntax_errors:
        next_action = "rollback_and_fix"
        rollback_target = "step11_detailed_design"
        decision_reason = "存在 syntax/type 级别阻塞错误，优先回退到详细设计与后续编码计划。"
    elif blocking_errors:
        next_action = "rollback_and_replan"
        rollback_target = "step10_system_design"
        decision_reason = "存在运行或结构性 blocking error，应回退到系统设计层重新校正。"
    elif not is_requirement_satisfied:
        next_action = "revisit_requirement_chain"
        rollback_target = "step9_requirement_spec"
        decision_reason = "没有 blocking errors，但需求对齐未通过，应回退到规格说明书与需求分析。"
    else:
        next_action = "proceed_to_finalize"
        rollback_target = ""
        decision_reason = "Error Gate 与 Demand Gate 均通过，可以进入最终汇总。"

    return {
        "step": "step16_feedback_router",
        "generated_at": utc_now(),
        "input_files": [str(STEP14_ERROR_REPORT_FILE), str(STEP15_DEMAND_REPORT_FILE)],
        "next_action": next_action,
        "rollback_target": rollback_target,
        "decision_reason": decision_reason,
    }


def main() -> None:
    ensure_runtime()
    report = build_report(read_json(STEP14_ERROR_REPORT_FILE), read_json(STEP15_DEMAND_REPORT_FILE))
    write_json(STEP16_FEEDBACK_ACTION_FILE, report)
    print_output("step16 完成", STEP16_FEEDBACK_ACTION_FILE)


if __name__ == "__main__":
    main()
