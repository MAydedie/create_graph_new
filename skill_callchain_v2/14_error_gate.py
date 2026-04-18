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
RUNTIME_DIR: Path = _load_attr("config", "RUNTIME_DIR")
STEP13_TEST_REPORT_FILE: Path = _load_attr("config", "STEP13_TEST_REPORT_FILE")
STEP14_ERROR_REPORT_FILE: Path = _load_attr("config", "STEP14_ERROR_REPORT_FILE")


RETURN_CODE_SEMANTICS = {
    "0": "No blocking errors or warnings detected.",
    "1": "No blocking errors detected, but non-blocking warnings exist.",
    "2": "Blocking errors detected; the gate fails.",
}


def _relative_to_runtime(path: Path) -> str:
    try:
        return f"runtime/{path.relative_to(RUNTIME_DIR).as_posix()}"
    except ValueError:
        return path.as_posix()


def _sanitize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": item.get("item_id"),
        "category": item.get("category"),
        "name": item.get("name"),
        "path": item.get("path"),
        "blocking": bool(item.get("blocking")),
        "status": item.get("status"),
        "return_code": item.get("return_code"),
        "message": item.get("message"),
        "details": item.get("details") or {},
    }


def _build_report_from_failure(message: str) -> dict[str, Any]:
    failure_item = {
        "item_id": "error_gate:missing_step13_report",
        "category": "runtime_artifact_checks",
        "name": "Load step13 test report",
        "path": _relative_to_runtime(STEP13_TEST_REPORT_FILE),
        "blocking": True,
        "status": "failed",
        "return_code": 1,
        "message": message,
        "details": {},
    }
    return {
        "step": "step14_error_gate",
        "generated_at": utc_now(),
        "source_report": _relative_to_runtime(STEP13_TEST_REPORT_FILE),
        "report_file": _relative_to_runtime(STEP14_ERROR_REPORT_FILE),
        "overall_status": "failed",
        "return_code": 2,
        "return_code_semantics": RETURN_CODE_SEMANTICS,
        "syntax_errors": [],
        "runtime_errors": [failure_item],
        "blocking_errors": [failure_item],
        "non_blocking_warnings": [],
        "summary": {
            "syntax_error_count": 0,
            "runtime_error_count": 1,
            "blocking_error_count": 1,
            "warning_count": 0,
        },
    }


def build_report(test_report: dict[str, Any]) -> dict[str, Any]:
    raw_items = test_report.get("items") or []
    failed_items = [_sanitize_item(item) for item in raw_items if isinstance(item, dict) and item.get("status") == "failed"]

    syntax_errors = [item for item in failed_items if item.get("category") == "syntax_checks"]
    runtime_errors = [item for item in failed_items if item.get("category") != "syntax_checks"]
    blocking_errors = [item for item in failed_items if item.get("blocking")]
    non_blocking_warnings = [item for item in failed_items if not item.get("blocking")]

    if blocking_errors:
        overall_status = "failed"
        return_code = 2
    elif non_blocking_warnings:
        overall_status = "warning"
        return_code = 1
    else:
        overall_status = "clean"
        return_code = 0

    return {
        "step": "step14_error_gate",
        "generated_at": utc_now(),
        "source_report": _relative_to_runtime(STEP13_TEST_REPORT_FILE),
        "report_file": _relative_to_runtime(STEP14_ERROR_REPORT_FILE),
        "upstream_test_status": test_report.get("overall_status"),
        "upstream_test_return_code": test_report.get("return_code"),
        "overall_status": overall_status,
        "return_code": return_code,
        "return_code_semantics": RETURN_CODE_SEMANTICS,
        "syntax_errors": syntax_errors,
        "runtime_errors": runtime_errors,
        "blocking_errors": blocking_errors,
        "non_blocking_warnings": non_blocking_warnings,
        "summary": {
            "syntax_error_count": len(syntax_errors),
            "runtime_error_count": len(runtime_errors),
            "blocking_error_count": len(blocking_errors),
            "warning_count": len(non_blocking_warnings),
        },
        "message": "No syntax or runtime issues detected." if not failed_items else "Detected issues were categorized for the demand-comparison gate.",
    }


def main() -> None:
    ensure_runtime()
    try:
        test_report = read_json(STEP13_TEST_REPORT_FILE)
        if not isinstance(test_report, dict):
            raise ValueError(f"Expected JSON object in {STEP13_TEST_REPORT_FILE}, got {type(test_report).__name__}.")
        report = build_report(test_report)
    except Exception as exc:
        report = _build_report_from_failure(f"Unable to consume step13 test report: {exc.__class__.__name__}: {exc}")
    write_json(STEP14_ERROR_REPORT_FILE, report)
    print_output("step14 完成", STEP14_ERROR_REPORT_FILE)


if __name__ == "__main__":
    main()
