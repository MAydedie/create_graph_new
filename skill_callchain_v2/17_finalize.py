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
write_json: Callable[[Path, Any], None] = _load_attr("common", "write_json")
write_text: Callable[[Path, str], None] = _load_attr("common", "write_text")
utc_now: Callable[[], str] = _load_attr("common", "utc_now")
RUNTIME_DIR: Path = _load_attr("config", "RUNTIME_DIR")
STEP12_CODEGEN_RESULT_FILE: Path = _load_attr("config", "STEP12_CODEGEN_RESULT_FILE")
STEP13_TEST_REPORT_FILE: Path = _load_attr("config", "STEP13_TEST_REPORT_FILE")
STEP14_ERROR_REPORT_FILE: Path = _load_attr("config", "STEP14_ERROR_REPORT_FILE")
STEP15_DEMAND_REPORT_FILE: Path = _load_attr("config", "STEP15_DEMAND_REPORT_FILE")
STEP16_FEEDBACK_ACTION_FILE: Path = _load_attr("config", "STEP16_FEEDBACK_ACTION_FILE")
FINAL_RESULT_JSON_FILE: Path = _load_attr("config", "FINAL_RESULT_JSON_FILE")
FINAL_RESULT_MD_FILE: Path = _load_attr("config", "FINAL_RESULT_MD_FILE")


def build_result(codegen: dict[str, Any], test_report: dict[str, Any], error_report: dict[str, Any], demand_report: dict[str, Any], feedback: dict[str, Any]) -> dict[str, Any]:
    artifact_names = sorted([path.name for path in RUNTIME_DIR.iterdir() if path.is_file()])
    return {
        "step": "finalize",
        "generated_at": utc_now(),
        "final_status": "passed" if feedback.get("next_action") == "proceed_to_finalize" else "needs_followup",
        "artifacts": artifact_names,
        "codegen_summary": {
            "target_file_count": len(codegen.get("target_files") or []),
            "work_item_count": len(codegen.get("work_items") or []),
        },
        "test_summary": test_report.get("summary") or {},
        "error_summary": error_report.get("summary") or {},
        "demand_summary": {
            "is_requirement_satisfied": demand_report.get("is_requirement_satisfied"),
            "missing_requirements": demand_report.get("missing_requirements") or [],
            "partially_satisfied_requirements": demand_report.get("partially_satisfied_requirements") or [],
        },
        "feedback_action": feedback,
    }


def build_markdown(final_payload: dict[str, Any]) -> str:
    lines = [
        "# Final Result",
        "",
        f"- Generated at: `{final_payload['generated_at']}`",
        f"- Final status: `{final_payload['final_status']}`",
        f"- Target file count: `{final_payload['codegen_summary']['target_file_count']}`",
        f"- Work item count: `{final_payload['codegen_summary']['work_item_count']}`",
        "",
        "## Demand Summary",
        f"- Requirement satisfied: `{final_payload['demand_summary']['is_requirement_satisfied']}`",
        f"- Missing requirements: `{', '.join(final_payload['demand_summary']['missing_requirements']) or 'none'}`",
        f"- Partial requirements: `{', '.join(final_payload['demand_summary']['partially_satisfied_requirements']) or 'none'}`",
        "",
        "## Feedback Action",
        f"- Next action: `{final_payload['feedback_action'].get('next_action', '')}`",
        f"- Rollback target: `{final_payload['feedback_action'].get('rollback_target', '') or 'none'}`",
        f"- Reason: {final_payload['feedback_action'].get('decision_reason', '')}",
        "",
        "## Artifacts",
    ]
    lines.extend([f"- `{item}`" for item in final_payload["artifacts"]])
    return "\n".join(lines)


def main() -> None:
    ensure_runtime()
    final_payload = build_result(
        read_json(STEP12_CODEGEN_RESULT_FILE),
        read_json(STEP13_TEST_REPORT_FILE),
        read_json(STEP14_ERROR_REPORT_FILE),
        read_json(STEP15_DEMAND_REPORT_FILE),
        read_json(STEP16_FEEDBACK_ACTION_FILE),
    )
    write_json(FINAL_RESULT_JSON_FILE, final_payload)
    write_text(FINAL_RESULT_MD_FILE, build_markdown(final_payload))
    print_output("final 完成", FINAL_RESULT_JSON_FILE)
    print_output("final markdown 完成", FINAL_RESULT_MD_FILE)


if __name__ == "__main__":
    main()
