from __future__ import annotations

import importlib
import os
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


analysis_service = importlib.import_module("app.services.analysis_service")
ensure_runtime: Callable[[], Path] = _load_attr("common", "ensure_runtime")
print_output: Callable[[str, Path], None] = _load_attr("common", "print_output")
read_json: Callable[[Path], Any] = _load_attr("common", "read_json")
utc_now: Callable[[], str] = _load_attr("common", "utc_now")
write_json: Callable[[Path, Any], None] = _load_attr("common", "write_json")
DEFAULT_SOURCE_PROJECT_PATH: Path = _load_attr("config", "DEFAULT_SOURCE_PROJECT_PATH")
PHASE6_CONTRACT_FILE: Path = _load_attr("config", "PHASE6_CONTRACT_FILE")
PHASE6_CONTRACT_REAL_FILE: Path = _load_attr("config", "PHASE6_CONTRACT_REAL_FILE")
RUNTIME_DIR: Path = _load_attr("config", "RUNTIME_DIR")


def _resolve_source_project_path() -> str:
    argv_path = sys.argv[1] if len(sys.argv) > 1 else ""
    env_path = os.getenv("SKILL_SOURCE_PROJECT", "").strip()
    candidate = argv_path.strip() or env_path or str(DEFAULT_SOURCE_PROJECT_PATH)
    normalized = os.path.normpath(candidate)
    if not Path(normalized).exists():
        raise FileNotFoundError(f"Source project path not found: {normalized}")
    return normalized


def _build_contract_payload(source_project_path: str) -> dict[str, Any]:
    analysis_service.analyze_function_hierarchy(source_project_path)
    hierarchy_cached = analysis_service._resolve_function_hierarchy_cached(source_project_path)
    hierarchy_cached = analysis_service._select_best_phase6_hierarchy_payload(source_project_path, hierarchy_cached)
    contract_payload = analysis_service._build_phase6_read_contract(source_project_path, hierarchy_cached)
    if not isinstance(contract_payload, dict):
        raise RuntimeError("Failed to build phase6 contract from real hierarchy output.")
    contract_payload.setdefault("runtime_meta", {})
    contract_payload["runtime_meta"].update(
        {
            "generated_at": utc_now(),
            "source_project_path": source_project_path,
            "generated_by": "00_build_real_phase6_contract.py",
        }
    )
    return contract_payload


def main() -> None:
    ensure_runtime()
    source_project_path = _resolve_source_project_path()
    contract_payload = _build_contract_payload(source_project_path)
    write_json(PHASE6_CONTRACT_REAL_FILE, contract_payload)
    write_json(PHASE6_CONTRACT_FILE, contract_payload)

    source_meta = {
        "source_project_path": source_project_path,
        "partition_count": len(((contract_payload.get("adapters") or {}).get("partition_summaries") or [])),
        "contract_version": str(contract_payload.get("contract_version") or ""),
    }
    write_json(RUNTIME_DIR / "phase6_real_source_meta.json", source_meta)

    print_output("real phase6 contract 完成", PHASE6_CONTRACT_REAL_FILE)
    print_output("active phase6 contract 完成", PHASE6_CONTRACT_FILE)


if __name__ == "__main__":
    main()
