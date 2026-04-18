from __future__ import annotations

from typing import Any, Dict, Optional

from app.services import analysis_service
from data.data_accessor import get_data_accessor


def _normalize_partition_summary(summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = summary if isinstance(summary, dict) else {}
    return {
        "partition_id": str(payload.get("partition_id") or "").strip(),
        "name": str(payload.get("name") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "methods": [
            str(item).strip()
            for item in (payload.get("methods") or [])
            if str(item).strip()
        ],
        "path_count": int(payload.get("path_count") or 0),
        "rich_path_count": int(payload.get("rich_path_count") or 0),
        "available_path_count": int(payload.get("available_path_count") or 0),
        "deferred_path_count": int(payload.get("deferred_path_count") or 0),
        "selection_policy": str(payload.get("selection_policy") or "").strip(),
        "analysis_status": str(payload.get("analysis_status") or "").strip(),
        "entry_point_count": int(payload.get("entry_point_count") or 0),
        "shadow_entry_point_count": int(payload.get("shadow_entry_point_count") or 0),
        "process_count": int(payload.get("process_count") or 0),
        "community_count": int(payload.get("community_count") or 0),
        "has_cfg": bool(payload.get("has_cfg")),
        "has_dfg": bool(payload.get("has_dfg")),
        "has_io": bool(payload.get("has_io")),
        "supports_process_shadow": bool(payload.get("supports_process_shadow")),
        "supports_community_shadow": bool(payload.get("supports_community_shadow")),
    }


def slim_phase6_contract(
    contract_payload: Optional[Dict[str, Any]],
    *,
    include_shadow_results: bool = False,
    include_raw_hierarchy: bool = False,
) -> Optional[Dict[str, Any]]:
    if not isinstance(contract_payload, dict) or not contract_payload:
        return None

    lightweight = {
        "contract_version": str(contract_payload.get("contract_version") or "").strip(),
        "project_path": str(contract_payload.get("project_path") or "").strip(),
        "capabilities": dict(contract_payload.get("capabilities") or {}),
        "sources": dict(contract_payload.get("sources") or {}),
        "adapters": {
            "partition_summaries": [
                _normalize_partition_summary(item)
                for item in ((contract_payload.get("adapters") or {}).get("partition_summaries") or [])
                if isinstance(item, dict)
            ],
        },
    }

    if include_shadow_results:
        lightweight["shadow_results"] = dict(contract_payload.get("shadow_results") or {})

    if include_raw_hierarchy:
        lightweight["raw"] = {
            "hierarchy_result": contract_payload.get("hierarchy_result"),
        }

    return lightweight


def build_phase6_contract(
    project_path: str,
    hierarchy_cached: Optional[Dict[str, Any]],
    *,
    include_shadow_results: bool = False,
    include_raw_hierarchy: bool = False,
) -> Optional[Dict[str, Any]]:
    contract_payload = analysis_service._build_phase6_read_contract(project_path, hierarchy_cached)
    return slim_phase6_contract(
        contract_payload,
        include_shadow_results=include_shadow_results,
        include_raw_hierarchy=include_raw_hierarchy,
    )


def load_phase6_contract(
    project_path: str,
    *,
    include_shadow_results: bool = False,
    include_raw_hierarchy: bool = False,
) -> Optional[Dict[str, Any]]:
    normalized_project_path = str(project_path or "").strip()
    hierarchy_cached = analysis_service._resolve_function_hierarchy_cached(normalized_project_path)
    hierarchy_cached = analysis_service._select_best_phase6_hierarchy_payload(normalized_project_path, hierarchy_cached)
    if not hierarchy_cached:
        hierarchy_cached = get_data_accessor().get_function_hierarchy(normalized_project_path)
    if not hierarchy_cached:
        return None

    return build_phase6_contract(
        normalized_project_path,
        hierarchy_cached,
        include_shadow_results=include_shadow_results,
        include_raw_hierarchy=include_raw_hierarchy,
    )
