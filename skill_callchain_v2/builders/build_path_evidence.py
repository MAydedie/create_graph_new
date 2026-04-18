from __future__ import annotations

import importlib
from typing import Any


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_stringify(item) for item in value if _stringify(item)]
    return []


def _maybe_path_model(payload: dict[str, Any]) -> Any:
    try:
        module = importlib.import_module("skill_callchain_v2.models")
        model_cls = getattr(module, "PathEvidence", None)
    except Exception:
        model_cls = None
    if model_cls is None:
        return payload
    try:
        return model_cls(**payload)
    except Exception:
        return payload


def _iter_partition_analyses(contract_payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    hierarchy_result = contract_payload.get("hierarchy_result") or contract_payload
    partition_analyses = hierarchy_result.get("partition_analyses") or {}
    items: list[tuple[str, dict[str, Any]]] = []
    for partition_id, payload in partition_analyses.items():
        if isinstance(payload, dict):
            items.append((_stringify(partition_id), payload))
    items.sort(key=lambda item: item[0])
    return items


def _build_path_payload(
    partition_id: str,
    source: str,
    path_index: int,
    path_payload: dict[str, Any],
    *,
    default_path_type: str,
) -> dict[str, Any] | None:
    function_chain = _string_list(path_payload.get("function_chain") or path_payload.get("path"))
    if not function_chain:
        return None

    path_id = _stringify(path_payload.get("path_id")) or f"{partition_id}:path:{path_index}"
    highlight_config = path_payload.get("highlight_config") or {}

    return {
        "partition_id": partition_id,
        "path_id": path_id,
        "path_name": _stringify(path_payload.get("path_name")) or f"Path {path_index + 1}",
        "path_type": _stringify(path_payload.get("deep_analysis_status"))
        or _stringify(path_payload.get("selection_policy"))
        or default_path_type,
        "function_chain": function_chain,
        "leaf_node": _stringify(path_payload.get("leaf_node")) or function_chain[-1],
        "summary": _stringify(path_payload.get("path_description"))
        or _stringify(highlight_config.get("explanation")),
        "worthiness_score": float(path_payload.get("worthiness_score") or 0.0),
        "has_cfg": bool(path_payload.get("cfg")),
        "has_dfg": bool(path_payload.get("dfg")),
        "has_io": bool(path_payload.get("io_graph")),
        "source": source,
    }


def _extract_from_deep_paths(partition_id: str, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, path_payload in enumerate(analysis.get("path_analyses") or []):
        if not isinstance(path_payload, dict):
            continue
        normalized = _build_path_payload(
            partition_id,
            "path_analyses",
            index,
            path_payload,
            default_path_type="deep_analysis",
        )
        if normalized is not None:
            result.append(normalized)
    return result


def _extract_from_paths_map(partition_id: str, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    paths_map = analysis.get("paths_map") or {}
    if not isinstance(paths_map, dict):
        return []

    result: list[dict[str, Any]] = []
    for leaf_node in sorted(paths_map):
        paths = paths_map.get(leaf_node) or []
        for path_index, path in enumerate(paths):
            normalized = _build_path_payload(
                partition_id,
                "paths_map",
                len(result),
                {
                    "path_id": f"structural:{partition_id}:{path_index}",
                    "leaf_node": leaf_node,
                    "path": path,
                    "path_name": f"Structural Path {len(result) + 1}",
                    "path_description": "Recovered from partition structural paths cache.",
                    "selection_policy": "structural_paths_map",
                },
                default_path_type="structural_paths_map",
            )
            if normalized is not None:
                result.append(normalized)
    return result


def _node_value(node: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _stringify(node.get(key))
        if value:
            return value
    data = node.get("data")
    if isinstance(data, dict):
        for key in keys:
            value = _stringify(data.get(key))
            if value:
                return value
    return ""


def _extract_from_call_graph(partition_id: str, analysis: dict[str, Any], *, max_paths: int = 4) -> list[dict[str, Any]]:
    call_graph = analysis.get("call_graph") or {}
    edges = call_graph.get("edges") or []
    nodes = call_graph.get("nodes") or []

    methods = {
        _node_value(node, "method_signature", "signature", "full_name", "label", "id")
        for node in nodes
        if isinstance(node, dict)
    }
    methods = {item for item in methods if item}

    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        edge_data = edge.get("data") if isinstance(edge.get("data"), dict) else edge
        if not isinstance(edge_data, dict):
            continue
        source = _stringify(edge_data.get("source") or edge_data.get("sourceId") or edge_data.get("caller"))
        target = _stringify(edge_data.get("target") or edge_data.get("targetId") or edge_data.get("callee"))
        if not source or not target:
            continue
        adjacency.setdefault(source, []).append(target)
        methods.add(source)
        methods.add(target)

    entry_points = analysis.get("entry_points") or []
    start_methods = [
        _stringify(item.get("method_signature") or item.get("signature"))
        for item in entry_points
        if isinstance(item, dict)
    ]
    start_methods = [item for item in start_methods if item] or sorted(methods)[:max_paths]

    results: list[dict[str, Any]] = []
    seen_paths: set[tuple[str, ...]] = set()
    for start_method in start_methods:
        if len(results) >= max_paths:
            break
        path = [start_method]
        direct_targets = sorted(set(adjacency.get(start_method) or []))
        if direct_targets:
            path.append(direct_targets[0])
            second_targets = sorted(set(adjacency.get(direct_targets[0]) or []))
            if second_targets:
                path.append(second_targets[0])
        normalized_path = tuple(item for item in path if item)
        if len(normalized_path) < 1 or normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)
        payload = _build_path_payload(
            partition_id,
            "call_graph_fallback",
            len(results),
            {
                "path_id": f"lightweight:{partition_id}:{len(results)}",
                "path": list(normalized_path),
                "leaf_node": normalized_path[-1],
                "path_name": f"Lightweight Path {len(results) + 1}",
                "path_description": "Inferred from entry points and partition call graph.",
                "selection_policy": "lightweight_fallback",
            },
            default_path_type="lightweight_fallback",
        )
        if payload is not None:
            results.append(payload)
    return results


def build_path_evidence(contract_payload: dict[str, Any]) -> list[Any]:
    results: list[Any] = []
    for partition_id, analysis in _iter_partition_analyses(contract_payload):
        evidences = _extract_from_deep_paths(partition_id, analysis)
        if not evidences:
            evidences = _extract_from_paths_map(partition_id, analysis)
        if not evidences:
            evidences = _extract_from_call_graph(partition_id, analysis)
        for evidence in evidences:
            results.append(_maybe_path_model(evidence))
    return results
