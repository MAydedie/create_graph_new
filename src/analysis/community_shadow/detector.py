from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from analysis.community_detector import CommunityDetector


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _copy_call_graph_subset(call_graph: Dict[str, Set[str]], allowed_nodes: Set[str]) -> Dict[str, Set[str]]:
    subset: Dict[str, Set[str]] = {}
    for caller, callees in (call_graph or {}).items():
        if caller not in allowed_nodes:
            continue
        subset[caller] = {callee for callee in (callees or set()) if callee in allowed_nodes}
    return subset


def _sample_call_graph(call_graph: Dict[str, Set[str]], max_nodes: int) -> Tuple[Dict[str, Set[str]], bool]:
    nodes = sorted({*call_graph.keys(), *{callee for callees in call_graph.values() for callee in callees}})
    if len(nodes) <= max_nodes:
        return call_graph, False

    scored_nodes: List[Tuple[int, str]] = []
    for node in nodes:
        out_degree = len(call_graph.get(node, set()))
        in_degree = sum(1 for callees in call_graph.values() if node in callees)
        scored_nodes.append((out_degree + in_degree, node))
    scored_nodes.sort(key=lambda item: item[0], reverse=True)
    sampled_nodes = {node for _, node in scored_nodes[:max_nodes]}
    return _copy_call_graph_subset(call_graph, sampled_nodes), True


def _run_detector(call_graph: Dict[str, Set[str]], algorithm: str, weight_threshold: float) -> List[Dict[str, Any]]:
    detector = CommunityDetector()
    return detector.detect_communities(call_graph, algorithm=algorithm, weight_threshold=weight_threshold)


def _run_with_timeout(
    call_graph: Dict[str, Set[str]],
    algorithm: str,
    weight_threshold: float,
    timeout_seconds: float,
) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_detector, call_graph, algorithm, weight_threshold)
        try:
            return future.result(timeout=timeout_seconds), False, None
        except TimeoutError:
            return [], True, "timeout"
        except Exception as error:
            return [], False, str(error)


def _build_method_node_map(graph_data: Optional[Dict[str, Any]]) -> Dict[str, str]:
    method_node_map: Dict[str, str] = {}
    if not isinstance(graph_data, dict):
        return method_node_map
    for node in graph_data.get("nodes", []) or []:
        if not isinstance(node, dict):
            continue
        node_data = node.get("data", {}) if isinstance(node.get("data"), dict) else node
        node_id = _normalize_text(node_data.get("id") or node.get("id"))
        if not node_id:
            continue
        candidates = [
            node_data.get("full_name"),
            node_data.get("qualified_name"),
            node_data.get("method_signature"),
            node_data.get("label"),
            node_data.get("name"),
        ]
        for candidate in candidates:
            method_sig = _normalize_text(candidate)
            if method_sig and method_sig not in method_node_map:
                method_node_map[method_sig] = node_id
    return method_node_map


def _calculate_cohesion(community: Dict[str, Any]) -> float:
    internal_calls = float(community.get("internal_calls", 0))
    external_calls = float(community.get("external_calls", 0))
    total = internal_calls + external_calls
    return internal_calls / total if total > 0 else 0.0


def _assemble_member_of(
    communities: Iterable[Dict[str, Any]],
    graph_data: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    method_node_map = _build_method_node_map(graph_data)
    community_nodes: List[Dict[str, Any]] = []
    member_of_edges: List[Dict[str, Any]] = []
    missing_method_count = 0

    for index, community in enumerate(communities or []):
        partition_id = _normalize_text(community.get("partition_id") or f"partition_{index}")
        community_id = f"community_shadow_{partition_id}"
        methods = community.get("methods", []) or []
        cohesion = community.get("cohesion")
        community_nodes.append(
            {
                "id": community_id,
                "label": community.get("label") or f"Community Shadow {index + 1}",
                "type": "Community",
                "symbol_count": len(methods),
                "modularity": community.get("modularity", 0.0),
                "cohesion": cohesion,
            }
        )

        for method_sig in methods:
            node_id = method_node_map.get(method_sig)
            if not node_id:
                missing_method_count += 1
                continue
            member_of_edges.append(
                {
                    "source": node_id,
                    "target": community_id,
                    "type": "MEMBER_OF",
                    "relation": "MEMBER_OF",
                }
            )

    relation_report = {
        "community_node_count": len(community_nodes),
        "member_of_edge_count": len(member_of_edges),
        "missing_method_count": missing_method_count,
        "consistent": len(community_nodes) > 0 and missing_method_count == 0,
    }
    return community_nodes, member_of_edges, relation_report


def build_community_shadow(
    call_graph: Dict[str, Set[str]],
    graph_data: Optional[Dict[str, Any]] = None,
    algorithm: str = "leiden",
    fallback_algorithm: str = "louvain",
    weight_threshold: float = 0.0,
    timeout_seconds: float = 5.0,
    max_nodes: int = 2000,
) -> Dict[str, Any]:
    effective_call_graph, sampled = _sample_call_graph(call_graph, max_nodes=max_nodes)
    communities, timed_out, execution_error = _run_with_timeout(
        effective_call_graph,
        algorithm=algorithm,
        weight_threshold=weight_threshold,
        timeout_seconds=timeout_seconds,
    )

    fallback_used = False
    fallback_reason = execution_error or ("timeout" if timed_out else None)
    if timed_out or execution_error or not communities:
        communities = _run_detector(effective_call_graph, fallback_algorithm, weight_threshold)
        fallback_used = True

    enriched_communities: List[Dict[str, Any]] = []
    for index, community in enumerate(communities or []):
        enriched = dict(community)
        enriched["label"] = f"Community Shadow {index + 1}"
        enriched["cohesion"] = round(_calculate_cohesion(enriched), 4)
        enriched_communities.append(enriched)

    community_nodes, member_of_edges, relation_report = _assemble_member_of(enriched_communities, graph_data)
    singleton_count = sum(1 for community in enriched_communities if len(community.get("methods", []) or []) == 1)
    total_methods = sum(len(community.get("methods", []) or []) for community in enriched_communities)
    avg_cohesion = sum((community.get("cohesion") or 0.0) for community in enriched_communities) / len(enriched_communities) if enriched_communities else 0.0

    return {
        "version": "phase5-shadow-v1",
        "config": {
            "algorithm": algorithm,
            "fallback_algorithm": fallback_algorithm,
            "weight_threshold": weight_threshold,
            "timeout_seconds": timeout_seconds,
            "max_nodes": max_nodes,
        },
        "execution": {
            "sampled": sampled,
            "timed_out": timed_out,
            "fallback_used": fallback_used,
            "effective_algorithm": fallback_algorithm if fallback_used else algorithm,
            "fallback_reason": fallback_reason,
        },
        "communities": enriched_communities,
        "community_nodes": community_nodes,
        "member_of_edges": member_of_edges,
        "quality_report": {
            "community_count": len(enriched_communities),
            "total_methods": total_methods,
            "avg_cohesion": round(avg_cohesion, 4),
            "singleton_ratio": round(singleton_count / len(enriched_communities), 4) if enriched_communities else 0.0,
            "timeout_fallback_rate": 1.0 if fallback_used else 0.0,
        },
        "relation_report": relation_report,
    }
