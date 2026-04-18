from __future__ import annotations

import importlib
import py_compile
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
RUNTIME_DIR: Path = _load_attr("config", "RUNTIME_DIR")
STEP13_TEST_REPORT_FILE: Path = _load_attr("config", "STEP13_TEST_REPORT_FILE")


RETURN_CODE_SEMANTICS = {
    "0": "All blocking and non-blocking checks passed.",
    "1": "At least one test item failed; inspect blocking and non-blocking failures.",
}

RUNTIME_ARTIFACT_SPECS = (
    {
        "path": RUNTIME_DIR / "step1_clarified_task.json",
        "kind": "json",
        "blocking": True,
        "expected_types": (dict,),
        "description": "Clarified task payload.",
    },
    {
        "path": RUNTIME_DIR / "phase6_read_contract.json",
        "kind": "json",
        "blocking": False,
        "expected_types": (dict,),
        "description": "Optional cached phase6 contract export.",
    },
    {
        "path": RUNTIME_DIR / "generated_skills.json",
        "kind": "json",
        "blocking": True,
        "expected_types": (dict, list),
        "description": "Generated skill library payload.",
    },
    {
        "path": RUNTIME_DIR / "step3_x_path_context.json",
        "kind": "json",
        "blocking": True,
        "expected_types": (dict,),
        "description": "Path-side context artifact.",
    },
    {
        "path": RUNTIME_DIR / "step4_y_semantic_context.json",
        "kind": "json",
        "blocking": True,
        "expected_types": (dict,),
        "description": "Semantic-side context artifact.",
    },
    {
        "path": RUNTIME_DIR / "step5_z_code_context.json",
        "kind": "json",
        "blocking": True,
        "expected_types": (dict,),
        "description": "Code-side context artifact.",
    },
    {
        "path": RUNTIME_DIR / "step6_fused_context.json",
        "kind": "json",
        "blocking": True,
        "expected_types": (dict,),
        "description": "Fused X/Y/Z context artifact.",
    },
    {
        "path": RUNTIME_DIR / "step7_decomposed_requirements.json",
        "kind": "json",
        "blocking": True,
        "expected_types": (dict, list),
        "description": "Requirement decomposition artifact.",
    },
    {
        "path": RUNTIME_DIR / "step8_requirement_analysis.md",
        "kind": "text",
        "blocking": True,
        "description": "Requirement analysis markdown.",
    },
    {
        "path": RUNTIME_DIR / "step9_requirement_spec.md",
        "kind": "text",
        "blocking": True,
        "description": "Requirement specification markdown.",
    },
    {
        "path": RUNTIME_DIR / "step10_system_design.md",
        "kind": "text",
        "blocking": True,
        "description": "System design markdown.",
    },
    {
        "path": RUNTIME_DIR / "step11_detailed_design.md",
        "kind": "text",
        "blocking": True,
        "description": "Detailed design markdown.",
    },
    {
        "path": RUNTIME_DIR / "step12_codegen_result.json",
        "kind": "json",
        "blocking": True,
        "expected_types": (dict,),
        "description": "Machine-readable codegen planning result.",
    },
)


def _relative_to_base(path: Path) -> str:
    try:
        return path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def _relative_to_runtime(path: Path) -> str:
    try:
        return f"runtime/{path.relative_to(RUNTIME_DIR).as_posix()}"
    except ValueError:
        return _relative_to_base(path)


def _status_counts(items: list[dict[str, Any]], category: str) -> dict[str, int]:
    scoped_items = [item for item in items if item.get("category") == category]
    passed = sum(1 for item in scoped_items if item.get("status") == "passed")
    failed = sum(1 for item in scoped_items if item.get("status") == "failed")
    return {
        "total": len(scoped_items),
        "passed": passed,
        "failed": failed,
    }


def _build_item(
    *,
    item_id: str,
    category: str,
    name: str,
    path: str,
    blocking: bool,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "category": category,
        "name": name,
        "path": path,
        "blocking": blocking,
        "status": status,
        "return_code": 0 if status == "passed" else 1,
        "message": message,
        "details": details or {},
    }


def _validate_text_artifact(path: Path, blocking: bool, description: str) -> dict[str, Any]:
    relative_path = _relative_to_runtime(path)
    if not path.exists():
        return _build_item(
            item_id=f"artifact:{path.name}",
            category="runtime_artifact_checks",
            name=f"Validate {relative_path}",
            path=relative_path,
            blocking=blocking,
            status="failed",
            message=f"Missing expected runtime artifact: {description}",
        )

    try:
        content = read_text(path)
    except Exception as exc:
        return _build_item(
            item_id=f"artifact:{path.name}",
            category="runtime_artifact_checks",
            name=f"Validate {relative_path}",
            path=relative_path,
            blocking=blocking,
            status="failed",
            message=f"Unable to read text artifact: {exc.__class__.__name__}: {exc}",
        )

    if not content.strip():
        return _build_item(
            item_id=f"artifact:{path.name}",
            category="runtime_artifact_checks",
            name=f"Validate {relative_path}",
            path=relative_path,
            blocking=blocking,
            status="failed",
            message="Text artifact is empty.",
            details={"bytes": path.stat().st_size},
        )

    return _build_item(
        item_id=f"artifact:{path.name}",
        category="runtime_artifact_checks",
        name=f"Validate {relative_path}",
        path=relative_path,
        blocking=blocking,
        status="passed",
        message="Text artifact exists and is readable.",
        details={"bytes": path.stat().st_size},
    )


def _validate_json_artifact(
    path: Path,
    blocking: bool,
    description: str,
    expected_types: tuple[type[Any], ...],
) -> dict[str, Any]:
    relative_path = _relative_to_runtime(path)
    if not path.exists():
        return _build_item(
            item_id=f"artifact:{path.name}",
            category="runtime_artifact_checks",
            name=f"Validate {relative_path}",
            path=relative_path,
            blocking=blocking,
            status="failed",
            message=f"Missing expected runtime artifact: {description}",
        )

    try:
        payload = read_json(path)
    except Exception as exc:
        return _build_item(
            item_id=f"artifact:{path.name}",
            category="runtime_artifact_checks",
            name=f"Validate {relative_path}",
            path=relative_path,
            blocking=blocking,
            status="failed",
            message=f"Unable to read JSON artifact: {exc.__class__.__name__}: {exc}",
        )

    if not isinstance(payload, expected_types):
        expected_names = ", ".join(sorted(expected_type.__name__ for expected_type in expected_types))
        return _build_item(
            item_id=f"artifact:{path.name}",
            category="runtime_artifact_checks",
            name=f"Validate {relative_path}",
            path=relative_path,
            blocking=blocking,
            status="failed",
            message=f"JSON root type mismatch; expected one of: {expected_names}.",
            details={"actual_type": type(payload).__name__},
        )

    return _build_item(
        item_id=f"artifact:{path.name}",
        category="runtime_artifact_checks",
        name=f"Validate {relative_path}",
        path=relative_path,
        blocking=blocking,
        status="passed",
        message="JSON artifact exists and is readable.",
        details={
            "bytes": path.stat().st_size,
            "json_root_type": type(payload).__name__,
        },
    )


def _runtime_artifact_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for spec in RUNTIME_ARTIFACT_SPECS:
        if spec["kind"] == "json":
            items.append(
                _validate_json_artifact(
                    path=spec["path"],
                    blocking=bool(spec["blocking"]),
                    description=str(spec["description"]),
                    expected_types=spec["expected_types"],
                )
            )
            continue
        items.append(
            _validate_text_artifact(
                path=spec["path"],
                blocking=bool(spec["blocking"]),
                description=str(spec["description"]),
            )
        )
    return items


def _syntax_target_paths() -> list[Path]:
    paths = [path for path in BASE_DIR.rglob("*.py") if "__pycache__" not in path.parts]
    return sorted(paths, key=lambda item: _relative_to_base(item))


def _syntax_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in _syntax_target_paths():
        relative_path = _relative_to_base(path)
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            message = exc.msg.strip() if isinstance(exc.msg, str) else str(exc)
            items.append(
                _build_item(
                    item_id=f"syntax:{relative_path}",
                    category="syntax_checks",
                    name=f"Compile {relative_path}",
                    path=relative_path,
                    blocking=True,
                    status="failed",
                    message=message,
                )
            )
            continue
        except Exception as exc:
            items.append(
                _build_item(
                    item_id=f"syntax:{relative_path}",
                    category="syntax_checks",
                    name=f"Compile {relative_path}",
                    path=relative_path,
                    blocking=True,
                    status="failed",
                    message=f"Compilation failed: {exc.__class__.__name__}: {exc}",
                )
            )
            continue

        items.append(
            _build_item(
                item_id=f"syntax:{relative_path}",
                category="syntax_checks",
                name=f"Compile {relative_path}",
                path=relative_path,
                blocking=True,
                status="passed",
                message="Python syntax compilation succeeded.",
            )
        )
    return items


def build_report() -> dict[str, Any]:
    artifact_items = _runtime_artifact_items()
    syntax_items = _syntax_items()
    items = artifact_items + syntax_items

    failed_items = [item for item in items if item.get("status") == "failed"]
    blocking_failures = [item for item in failed_items if item.get("blocking")]
    non_blocking_failures = [item for item in failed_items if not item.get("blocking")]

    return {
        "step": "step13_run_tests",
        "generated_at": utc_now(),
        "report_file": _relative_to_runtime(STEP13_TEST_REPORT_FILE),
        "overall_status": "passed" if not failed_items else "failed",
        "return_code": 0 if not failed_items else 1,
        "return_code_semantics": RETURN_CODE_SEMANTICS,
        "test_categories": {
            "runtime_artifact_checks": {
                "description": "Validate required local runtime artifacts for readability and expected shape.",
                **_status_counts(items, "runtime_artifact_checks"),
            },
            "syntax_checks": {
                "description": "Compile Python files under skill_callchain_v2 using the standard library only.",
                **_status_counts(items, "syntax_checks"),
            },
        },
        "summary": {
            "total": len(items),
            "passed": len(items) - len(failed_items),
            "failed": len(failed_items),
            "blocking_failures": len(blocking_failures),
            "non_blocking_failures": len(non_blocking_failures),
        },
        "items": items,
    }


def build_unexpected_failure_report(exc: Exception) -> dict[str, Any]:
    return {
        "step": "step13_run_tests",
        "generated_at": utc_now(),
        "report_file": _relative_to_runtime(STEP13_TEST_REPORT_FILE),
        "overall_status": "failed",
        "return_code": 1,
        "return_code_semantics": RETURN_CODE_SEMANTICS,
        "test_categories": {
            "runtime_artifact_checks": {
                "description": "Validate required local runtime artifacts for readability and expected shape.",
                "total": 0,
                "passed": 0,
                "failed": 0,
            },
            "syntax_checks": {
                "description": "Compile Python files under skill_callchain_v2 using the standard library only.",
                "total": 0,
                "passed": 0,
                "failed": 0,
            },
        },
        "summary": {
            "total": 1,
            "passed": 0,
            "failed": 1,
            "blocking_failures": 1,
            "non_blocking_failures": 0,
        },
        "items": [
            _build_item(
                item_id="framework:step13",
                category="runtime_artifact_checks",
                name="Run step13 test harness",
                path=_relative_to_base(Path(__file__)),
                blocking=True,
                status="failed",
                message=f"Unexpected test harness failure: {exc.__class__.__name__}: {exc}",
            )
        ],
    }


def main() -> None:
    ensure_runtime()
    try:
        report = build_report()
    except Exception as exc:
        report = build_unexpected_failure_report(exc)
    write_json(STEP13_TEST_REPORT_FILE, report)
    print_output("step13 完成", STEP13_TEST_REPORT_FILE)


if __name__ == "__main__":
    main()
