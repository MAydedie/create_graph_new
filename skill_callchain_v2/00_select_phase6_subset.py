from __future__ import annotations

import copy
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


ensure_runtime: Callable[[], Path] = _load_attr("common", "ensure_runtime")
print_output: Callable[[str, Path], None] = _load_attr("common", "print_output")
read_json: Callable[[Path], Any] = _load_attr("common", "read_json")
utc_now: Callable[[], str] = _load_attr("common", "utc_now")
write_json: Callable[[Path, Any], None] = _load_attr("common", "write_json")
DEFAULT_SUBSET_SKILL_COUNT: int = int(_load_attr("config", "DEFAULT_SUBSET_SKILL_COUNT") or 12)
PHASE6_CONTRACT_FILE: Path = _load_attr("config", "PHASE6_CONTRACT_FILE")
PHASE6_CONTRACT_REAL_FILE: Path = _load_attr("config", "PHASE6_CONTRACT_REAL_FILE")
PHASE6_CONTRACT_SUBSET_FILE: Path = _load_attr("config", "PHASE6_CONTRACT_SUBSET_FILE")
RUNTIME_DIR: Path = _load_attr("config", "RUNTIME_DIR")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _load_contract() -> dict[str, Any]:
    source = PHASE6_CONTRACT_REAL_FILE if PHASE6_CONTRACT_REAL_FILE.exists() else PHASE6_CONTRACT_FILE
    payload = read_json(source)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid contract payload at {source}")
    return payload


def _score_partition(summary: dict[str, Any]) -> int:
    score = 0
    score += _safe_int(summary.get("rich_path_count")) * 8
    score += _safe_int(summary.get("path_count")) * 6
    score += _safe_int(summary.get("entry_point_count")) * 2
    score += _safe_int(summary.get("process_count"))
    score += _safe_int(summary.get("community_count"))
    score += 1 if summary.get("has_cfg") else 0
    score += 1 if summary.get("has_dfg") else 0
    score += 1 if summary.get("has_io") else 0
    return score


def _resolve_keep_count(total: int) -> int:
    argv_count = 0
    if len(sys.argv) > 1:
        try:
            argv_count = int(sys.argv[1])
        except ValueError:
            argv_count = 0
    env_count = 0
    raw_env = os.getenv("SKILL_SUBSET_COUNT", "").strip()
    if raw_env:
        try:
            env_count = int(raw_env)
        except ValueError:
            env_count = 0

    requested = argv_count or env_count or DEFAULT_SUBSET_SKILL_COUNT
    requested = max(requested, 1)

    if total >= 8:
        requested = max(requested, 8)
    return min(requested, total)


def _select_partition_ids(contract_payload: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], int]:
    summaries = ((contract_payload.get("adapters") or {}).get("partition_summaries") or [])
    normalized = [item for item in summaries if isinstance(item, dict) and _stringify(item.get("partition_id"))]
    ranked = sorted(
        normalized,
        key=lambda item: (-_score_partition(item), _stringify(item.get("partition_id"))),
    )
    keep_count = _resolve_keep_count(len(ranked))
    selected_summaries = ranked[:keep_count]
    selected_ids = [_stringify(item.get("partition_id")) for item in selected_summaries]
    return selected_ids, selected_summaries, keep_count


def _filter_hierarchy_result(hierarchy_result: dict[str, Any], selected_ids: set[str]) -> dict[str, Any]:
    filtered = copy.deepcopy(hierarchy_result)

    partition_analyses = filtered.get("partition_analyses")
    if isinstance(partition_analyses, dict):
        filtered["partition_analyses"] = {
            key: value for key, value in partition_analyses.items() if _stringify(key) in selected_ids
        }

    hierarchy = filtered.get("hierarchy")
    if isinstance(hierarchy, dict):
        for key in ("layer1_functions", "layer1"):
            layer_items = hierarchy.get(key)
            if isinstance(layer_items, list):
                hierarchy[key] = [
                    item
                    for item in layer_items
                    if isinstance(item, dict) and _stringify(item.get("partition_id")) in selected_ids
                ]
    return filtered


def _build_subset_contract(contract_payload: dict[str, Any]) -> dict[str, Any]:
    selected_ids, selected_summaries, keep_count = _select_partition_ids(contract_payload)
    selected_id_set = set(selected_ids)

    subset_payload = copy.deepcopy(contract_payload)
    subset_payload.setdefault("adapters", {})
    subset_payload["adapters"]["partition_summaries"] = selected_summaries

    hierarchy_result = subset_payload.get("hierarchy_result")
    if isinstance(hierarchy_result, dict):
        subset_payload["hierarchy_result"] = _filter_hierarchy_result(hierarchy_result, selected_id_set)

    subset_payload.setdefault("runtime_meta", {})
    subset_payload["runtime_meta"].update(
        {
            "subset_enabled": True,
            "subset_partition_count": keep_count,
            "subset_selected_partition_ids": selected_ids,
            "subset_generated_at": utc_now(),
            "subset_generated_by": "00_select_phase6_subset.py",
        }
    )
    return subset_payload


def main() -> None:
    ensure_runtime()
    contract_payload = _load_contract()
    subset_payload = _build_subset_contract(contract_payload)

    write_json(PHASE6_CONTRACT_SUBSET_FILE, subset_payload)
    write_json(PHASE6_CONTRACT_FILE, subset_payload)

    selection_report = {
        "generated_at": utc_now(),
        "total_partition_count": len(((contract_payload.get("adapters") or {}).get("partition_summaries") or [])),
        "selected_partition_count": len((((subset_payload.get("runtime_meta") or {}).get("subset_selected_partition_ids")) or [])),
        "selected_partition_ids": ((subset_payload.get("runtime_meta") or {}).get("subset_selected_partition_ids")) or [],
    }
    write_json(RUNTIME_DIR / "phase6_subset_selection_report.json", selection_report)

    print_output("phase6 subset contract 完成", PHASE6_CONTRACT_SUBSET_FILE)
    print_output("active phase6 contract(子集) 完成", PHASE6_CONTRACT_FILE)


if __name__ == "__main__":
    main()
