from __future__ import annotations

import importlib
import sys
from dataclasses import asdict, is_dataclass
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


build_code_evidence: Callable[[dict[str, Any]], list[Any]] = _load_attr("builders.build_code_evidence", "build_code_evidence")
build_path_evidence: Callable[[dict[str, Any]], list[Any]] = _load_attr("builders.build_path_evidence", "build_path_evidence")
build_skills_from_partitions: Callable[[dict[str, Any]], list[Any]] = _load_attr(
    "builders.build_skills_from_partitions",
    "build_skills_from_partitions",
)
merge_skill_cards: Callable[[list[Any], list[Any], list[Any]], list[dict[str, Any]]] = _load_attr(
    "builders.merge_skill_cards",
    "merge_skill_cards",
)
ensure_runtime: Callable[[], Path] = _load_attr("common", "ensure_runtime")
print_output: Callable[[str, Path], None] = _load_attr("common", "print_output")
read_json: Callable[[Path], Any] = _load_attr("common", "read_json")
utc_now: Callable[[], str] = _load_attr("common", "utc_now")
write_json: Callable[[Path, Any], None] = _load_attr("common", "write_json")
GENERATED_SKILLS_FILE: Path = _load_attr("config", "GENERATED_SKILLS_FILE")
PROJECT_PATH: Path = _load_attr("config", "PROJECT_PATH")
RUNTIME_DIR: Path = _load_attr("config", "RUNTIME_DIR")


CONTRACT_CANDIDATE_FILENAMES = (
    "phase6_read_contract_subset.json",
    "phase6_read_contract_real.json",
    "phase6_read_contract.json",
    "step2_phase6_read_contract.json",
    "read_contract.json",
    "hierarchy_read_contract.json",
    "function_hierarchy_result.json",
    "hierarchy_result.json",
)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_plain_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain_data(item) for item in value]
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _to_plain_data(value.model_dump())
    if hasattr(value, "dict") and callable(value.dict):
        return _to_plain_data(value.dict())
    if is_dataclass(value) and not isinstance(value, type):
        try:
            return _to_plain_data(asdict(value))
        except TypeError:
            pass
    if hasattr(value, "__dict__") and not isinstance(value, (str, bytes, Path)):
        return _to_plain_data(
            {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        )
    return value


def _try_call_loader(loader: Callable[..., Any]) -> dict[str, Any] | None:
    attempts = (
        {},
        {"runtime_dir": RUNTIME_DIR},
        {"base_dir": BASE_DIR},
        {"project_path": str(PROJECT_PATH)},
    )
    for kwargs in attempts:
        try:
            result = loader(**kwargs)
        except TypeError:
            continue
        except Exception:
            return None
        if isinstance(result, dict):
            return result
    try:
        result = loader()
    except Exception:
        return None
    return result if isinstance(result, dict) else None


def _load_contract_from_adapters() -> tuple[dict[str, Any] | None, str]:
    module_candidates = {
        "adapters.phase6_contract_adapter": (
            "load_phase6_contract",
            "load_contract",
            "read_phase6_contract",
            "build_phase6_read_contract",
        ),
        "adapters.hierarchy_adapter": (
            "load_hierarchy_contract",
            "load_contract",
            "read_hierarchy_contract",
            "build_contract",
        ),
    }
    for module_suffix, attr_names in module_candidates.items():
        try:
            module = importlib.import_module(f"{_MODULE_PREFIX}.{module_suffix}")
        except Exception:
            continue
        for attr_name in attr_names:
            loader = getattr(module, attr_name, None)
            if not callable(loader):
                continue
            payload = _try_call_loader(loader)
            if isinstance(payload, dict):
                return payload, f"adapter:{module_suffix}.{attr_name}"
    return None, ""


def _load_contract_from_runtime() -> tuple[dict[str, Any] | None, str]:
    for filename in CONTRACT_CANDIDATE_FILENAMES:
        candidate = RUNTIME_DIR / filename
        if candidate.exists():
            payload = read_json(candidate)
            if isinstance(payload, dict):
                return payload, str(candidate)

    for pattern in ("*contract*.json", "*hierarchy*.json"):
        for candidate in sorted(RUNTIME_DIR.glob(pattern)):
            if candidate == GENERATED_SKILLS_FILE or not candidate.is_file():
                continue
            payload = read_json(candidate)
            if isinstance(payload, dict):
                return payload, str(candidate)
    return None, ""


def _partition_methods_map(hierarchy_payload: dict[str, Any]) -> dict[str, list[str]]:
    hierarchy = hierarchy_payload.get("hierarchy") or {}
    layer1_functions = hierarchy.get("layer1_functions") or hierarchy.get("layer1") or []
    result: dict[str, list[str]] = {}
    for item in layer1_functions:
        if not isinstance(item, dict):
            continue
        partition_id = _stringify(item.get("partition_id"))
        if not partition_id:
            continue
        methods = []
        seen: set[str] = set()
        for method in item.get("methods") or []:
            normalized = _stringify(method)
            if normalized and normalized not in seen:
                seen.add(normalized)
                methods.append(normalized)
        result[partition_id] = methods
    return result


def _partition_meta_map(hierarchy_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    hierarchy = hierarchy_payload.get("hierarchy") or {}
    layer1_functions = hierarchy.get("layer1_functions") or hierarchy.get("layer1") or []
    result: dict[str, dict[str, Any]] = {}
    for item in layer1_functions:
        if not isinstance(item, dict):
            continue
        partition_id = _stringify(item.get("partition_id"))
        if partition_id:
            result[partition_id] = item
    return result


def _coerce_shadow_payload(hierarchy_payload: dict[str, Any], key: str) -> dict[str, Any]:
    direct = hierarchy_payload.get(key)
    if isinstance(direct, dict):
        return direct
    shadow_results = hierarchy_payload.get("shadow_results") or {}
    nested_key = key.replace("_shadow", "")
    nested = shadow_results.get(nested_key)
    return nested if isinstance(nested, dict) else {}


def _build_partition_summaries_from_hierarchy(hierarchy_payload: dict[str, Any]) -> list[dict[str, Any]]:
    partition_analyses = hierarchy_payload.get("partition_analyses") or {}
    partition_meta_map = _partition_meta_map(hierarchy_payload)
    partition_methods = _partition_methods_map(hierarchy_payload)
    process_shadow = _coerce_shadow_payload(hierarchy_payload, "process_shadow")
    community_shadow = _coerce_shadow_payload(hierarchy_payload, "community_shadow")

    partition_ids = sorted(set(partition_analyses) | set(partition_meta_map))
    summaries: list[dict[str, Any]] = []
    for partition_id in partition_ids:
        analysis = partition_analyses.get(partition_id) or {}
        meta = partition_meta_map.get(partition_id) or {}
        path_analyses = analysis.get("path_analyses") or []
        paths_map = analysis.get("paths_map") or {}
        path_info = analysis.get("path_analysis_info") or {}
        path_count = len(path_analyses)
        available_path_count = path_count
        if not path_count and isinstance(paths_map, dict):
            available_path_count = sum(len(item or []) for item in paths_map.values())
        available_path_count = max(
            available_path_count,
            int(path_info.get("selected_count") or 0),
            int(path_info.get("total_candidates") or 0),
        )
        rich_path_count = sum(
            1
            for item in path_analyses
            if isinstance(item, dict)
            and any(
                [
                    item.get("cfg"),
                    item.get("dfg"),
                    item.get("io_graph"),
                    item.get("cfg_dfg_explain_md"),
                    bool((item.get("semantics") or {}).get("description")),
                ]
            )
        )
        methods = partition_methods.get(partition_id) or [
            _stringify(item) for item in (analysis.get("methods") or []) if _stringify(item)
        ]
        summaries.append(
            {
                "partition_id": partition_id,
                "name": _stringify(meta.get("name") or analysis.get("name") or partition_id),
                "description": _stringify(meta.get("description") or analysis.get("description")),
                "methods": methods,
                "path_count": path_count,
                "rich_path_count": rich_path_count,
                "available_path_count": available_path_count,
                "deferred_path_count": int(path_info.get("deferred_count") or 0),
                "selection_policy": _stringify(path_info.get("selection_policy")),
                "analysis_status": _stringify(path_info.get("completion_status")) or (
                    "complete" if path_analyses else "fallback"
                ),
                "entry_point_count": len(analysis.get("entry_points") or []),
                "shadow_entry_point_count": len(((analysis.get("entry_points_shadow") or {}).get("effective_entries") or [])),
                "process_count": len(
                    [
                        process
                        for process in (process_shadow.get("processes") or [])
                        if isinstance(process, dict) and _stringify(process.get("partition_id")) == partition_id
                    ]
                ),
                "community_count": len(
                    [
                        community
                        for community in (community_shadow.get("communities") or [])
                        if isinstance(community, dict)
                        and set(_stringify(item) for item in (community.get("methods") or []) if _stringify(item)).intersection(set(methods))
                    ]
                ),
                "has_cfg": any(bool(item.get("cfg")) for item in path_analyses if isinstance(item, dict)),
                "has_dfg": any(bool(item.get("dfg")) for item in path_analyses if isinstance(item, dict)),
                "has_io": any(bool(item.get("io_graph")) for item in path_analyses if isinstance(item, dict)),
            }
        )
    return summaries


def _collect_skill_quality(skills: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(skills)
    usable = 0
    degraded = 0
    low_signal = 0
    for skill in skills:
        quality = skill.get("quality") or {}
        if bool(skill.get("usable_for_matching", True)):
            usable += 1
        if bool(quality.get("is_degraded")):
            degraded += 1
        if bool(quality.get("is_low_signal")):
            low_signal += 1
    return {
        "total_skills": total,
        "usable_skills": usable,
        "degraded_skills": degraded,
        "low_signal_skills": low_signal,
    }


def _normalize_contract_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if (payload.get("adapters") or {}).get("partition_summaries"):
        return payload
    if payload.get("partition_analyses") or payload.get("hierarchy"):
        return {
            "contract_version": _stringify(payload.get("contract_version")) or "phase6-stage1-v1-fallback",
            "project_path": _stringify(payload.get("project_path")) or str(PROJECT_PATH),
            "adapters": {
                "partition_summaries": _build_partition_summaries_from_hierarchy(payload),
            },
            "hierarchy_result": payload,
            "shadow_results": payload.get("shadow_results") or {
                "entry_points": payload.get("entry_points_shadow"),
                "process": payload.get("process_shadow"),
                "community": payload.get("community_shadow"),
            },
        }
    raise ValueError("No phase6/hierarchy contract payload found for skill generation.")


def _load_contract_payload() -> tuple[dict[str, Any], str]:
    adapter_payload, adapter_source = _load_contract_from_adapters()
    if isinstance(adapter_payload, dict):
        return _normalize_contract_payload(adapter_payload), adapter_source

    runtime_payload, runtime_source = _load_contract_from_runtime()
    if isinstance(runtime_payload, dict):
        return _normalize_contract_payload(runtime_payload), runtime_source

    searched_names = ", ".join(CONTRACT_CANDIDATE_FILENAMES)
    raise FileNotFoundError(f"No contract file found under {RUNTIME_DIR} ({searched_names}).")


def build_report(contract_payload: dict[str, Any], contract_source: str) -> dict[str, Any]:
    base_skills = build_skills_from_partitions(contract_payload)
    path_evidence = build_path_evidence(contract_payload)
    code_evidence = build_code_evidence(contract_payload)
    merged_skills = merge_skill_cards(base_skills, path_evidence, code_evidence)
    plain_skills = _to_plain_data(merged_skills)
    plain_partition_summaries = _to_plain_data(((contract_payload.get("adapters") or {}).get("partition_summaries") or []))
    quality_summary = _collect_skill_quality(plain_skills)

    if int(quality_summary.get("usable_skills") or 0) == 0:
        raise ValueError("No usable skills available for matching. Please rerun hierarchy analysis without degraded/fallback-only outputs.")

    return {
        "version": "v2.work_order_b",
        "step": "generate_skill_library",
        "generated_at": utc_now(),
        "skill_count": len(plain_skills),
        "metadata": {
            "generated_at": utc_now(),
            "skill_count": len(plain_skills),
            "contract_version": _stringify(contract_payload.get("contract_version")),
            "project_path": _stringify(contract_payload.get("project_path")) or str(PROJECT_PATH),
            "contract_source": contract_source,
            "partition_count": len(plain_partition_summaries),
            "path_evidence_count": len(_to_plain_data(path_evidence)),
            "code_evidence_count": len(_to_plain_data(code_evidence)),
            "quality_summary": quality_summary,
        },
        "partition_summaries": plain_partition_summaries,
        "skills": plain_skills,
    }


def main() -> None:
    ensure_runtime()
    contract_payload, contract_source = _load_contract_payload()
    report = build_report(contract_payload, contract_source)
    write_json(GENERATED_SKILLS_FILE, report)
    print_output("step2 完成", GENERATED_SKILLS_FILE)


if __name__ == "__main__":
    main()
