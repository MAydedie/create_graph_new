from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services import analysis_service
from data.data_accessor import get_data_accessor

from ..models import PathEvidence
from .phase6_contract_adapter import load_phase6_contract


def _load_hierarchy_cached(project_path: str) -> Optional[Dict[str, Any]]:
    return get_data_accessor().get_function_hierarchy(project_path)


def _normalize_entry_points(entry_points: Any, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in entry_points or []:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "method_signature": str(item.get("method_signature") or "").strip(),
                "score": float(item.get("score") or 0.0),
                "reasons": [
                    str(reason).strip()
                    for reason in (item.get("reasons") or [])
                    if str(reason).strip()
                ],
            }
        )
        if limit is not None and len(normalized) >= max(limit, 0):
            break
    return [item for item in normalized if item["method_signature"]]


def _normalize_path_info(path_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = path_info if isinstance(path_info, dict) else {}
    return {
        "selection_policy": str(payload.get("selection_policy") or "").strip(),
        "completion_status": str(payload.get("completion_status") or "").strip(),
        "selected_count": int(payload.get("selected_count") or 0),
        "deferred_count": int(payload.get("deferred_count") or 0),
        "total_candidates": int(payload.get("total_candidates") or 0),
        "timed_out": bool(payload.get("timed_out")),
        "user_message": str(payload.get("user_message") or "").strip(),
        "representative_path_summaries": [
            _normalize_path_summary(item)
            for item in (payload.get("representative_path_summaries") or [])
            if isinstance(item, dict)
        ],
        "deferred_path_summaries": [
            _normalize_path_summary(item)
            for item in (payload.get("deferred_path_summaries") or [])
            if isinstance(item, dict)
        ],
    }


def _normalize_path_summary(path_summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "leaf_node": str(path_summary.get("leaf_node") or "").strip(),
        "path_index": int(path_summary.get("path_index") or 0),
        "path": [str(item).strip() for item in (path_summary.get("path") or []) if str(item).strip()],
        "worthiness_score": float(path_summary.get("worthiness_score") or 0.0),
        "worthiness_reasons": [
            str(item).strip()
            for item in (path_summary.get("worthiness_reasons") or [])
            if str(item).strip()
        ],
        "deep_analysis_status": str(path_summary.get("deep_analysis_status") or "").strip(),
        "deferred_reason": str(path_summary.get("deferred_reason") or "").strip(),
    }


def build_path_evidence(
    partition_id: str,
    partition_name: str,
    path_analyses: Any,
    *,
    selection_policy: str = "",
    max_paths: Optional[int] = 4,
) -> List[PathEvidence]:
    items: List[PathEvidence] = []
    for path_analysis in path_analyses or []:
        if not isinstance(path_analysis, dict):
            continue
        function_chain = [
            str(item).strip()
            for item in (path_analysis.get("function_chain") or path_analysis.get("path") or [])
            if str(item).strip()
        ]
        summary = str(
            ((path_analysis.get("semantics") or {}).get("description"))
            or path_analysis.get("path_description")
            or ((path_analysis.get("highlight_config") or {}).get("explanation"))
            or ""
        ).strip()
        items.append(
            PathEvidence(
                partition_id=partition_id,
                partition_name=partition_name,
                path_id=str(path_analysis.get("path_id") or "").strip(),
                path_name=str(path_analysis.get("path_name") or "").strip(),
                path_description=str(path_analysis.get("path_description") or "").strip(),
                function_chain=function_chain,
                leaf_node=str(path_analysis.get("leaf_node") or "").strip(),
                worthiness_score=float(path_analysis.get("worthiness_score") or 0.0),
                worthiness_reasons=[
                    str(item).strip()
                    for item in (path_analysis.get("worthiness_reasons") or [])
                    if str(item).strip()
                ],
                deep_analysis_status=str(path_analysis.get("deep_analysis_status") or "").strip(),
                selection_policy=selection_policy,
                summary=summary,
                metadata={
                    "path_index": path_analysis.get("path_index"),
                    "source": "phase6_partition_analysis",
                },
            )
        )
        if max_paths is not None and len(items) >= max(max_paths, 0):
            break
    return items


def get_partition_summaries(contract_payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summaries = ((contract_payload or {}).get("adapters") or {}).get("partition_summaries") or []
    return [dict(item) for item in summaries if isinstance(item, dict)]


def load_partition_summaries(project_path: str) -> List[Dict[str, Any]]:
    return get_partition_summaries(load_phase6_contract(project_path))


def get_partition_summary(contract_payload: Optional[Dict[str, Any]], partition_id: str) -> Optional[Dict[str, Any]]:
    target = str(partition_id or "").strip()
    if not target:
        return None
    for summary in get_partition_summaries(contract_payload):
        if str(summary.get("partition_id") or "").strip() == target:
            return summary
    return None


def load_partition_analysis(
    project_path: str,
    partition_id: str,
    *,
    max_paths: int = 4,
    entry_point_limit: int = 6,
    include_raw: bool = False,
) -> Optional[Dict[str, Any]]:
    target = str(partition_id or "").strip()
    if not target:
        return None

    hierarchy_cached = _load_hierarchy_cached(project_path)
    if not hierarchy_cached:
        return None

    contract_payload = load_phase6_contract(project_path)
    summary = get_partition_summary(contract_payload, target) or {"partition_id": target}
    analysis = ((hierarchy_cached.get("partition_analyses") or {}).get(target)) or {}
    if not isinstance(analysis, dict) or not analysis:
        return None

    path_analyses, path_info = analysis_service._get_partition_path_payload(
        analysis,
        partition_methods=summary.get("methods") or [],
    )
    path_evidence = build_path_evidence(
        target,
        str(summary.get("name") or target).strip(),
        path_analyses,
        selection_policy=str(path_info.get("selection_policy") or "").strip(),
        max_paths=max_paths,
    )

    payload: Dict[str, Any] = {
        "partition_id": target,
        "summary": summary,
        "methods": [
            str(item).strip()
            for item in (summary.get("methods") or [])
            if str(item).strip()
        ],
        "entry_points": _normalize_entry_points(analysis.get("entry_points"), limit=entry_point_limit),
        "path_analysis_info": _normalize_path_info(path_info),
        "path_evidence": [item.to_dict() for item in path_evidence],
    }

    if include_raw:
        payload["raw_analysis"] = analysis

    return payload


def load_partition_analyses(
    project_path: str,
    *,
    max_partitions: Optional[int] = None,
    max_paths: int = 4,
    entry_point_limit: int = 6,
    include_raw: bool = False,
) -> List[Dict[str, Any]]:
    analyses: List[Dict[str, Any]] = []
    for summary in load_partition_summaries(project_path):
        partition_id = str(summary.get("partition_id") or "").strip()
        if not partition_id:
            continue
        payload = load_partition_analysis(
            project_path,
            partition_id,
            max_paths=max_paths,
            entry_point_limit=entry_point_limit,
            include_raw=include_raw,
        )
        if payload:
            analyses.append(payload)
        if max_partitions is not None and len(analyses) >= max(max_partitions, 0):
            break
    return analyses
