from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


def _build_entry_point_map(partition_analyses: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    entry_map: Dict[str, List[str]] = {}
    for partition_id, analysis in (partition_analyses or {}).items():
        entries: List[str] = []
        shadow_payload = analysis.get("entry_points_shadow") if isinstance(analysis, dict) else None
        if isinstance(shadow_payload, dict):
            for entry in shadow_payload.get("effective_entries", []) or []:
                method_sig = _normalize_text(entry.get("method_signature") or entry.get("method_sig"))
                if method_sig:
                    entries.append(method_sig)
        if entries:
            entry_map[partition_id] = entries
            continue
        for entry in analysis.get("entry_points", []) or []:
            if isinstance(entry, dict):
                method_sig = _normalize_text(entry.get("method_signature") or entry.get("method_sig"))
            else:
                method_sig = _normalize_text(getattr(entry, "method_sig", None))
            if method_sig:
                entries.append(method_sig)
        if entries:
            entry_map[partition_id] = entries
    return entry_map


def _build_entry_point_detail_map(partition_analyses: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    detail_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for partition_id, analysis in (partition_analyses or {}).items():
        partition_detail: Dict[str, Dict[str, Any]] = {}
        shadow_payload = analysis.get("entry_points_shadow") if isinstance(analysis, dict) else None
        if isinstance(shadow_payload, dict):
            for entry in shadow_payload.get("effective_entries", []) or []:
                method_sig = _normalize_text(entry.get("method_signature") or entry.get("method_sig"))
                if method_sig:
                    partition_detail[method_sig] = entry
        else:
            for entry in analysis.get("entry_points", []) or []:
                if isinstance(entry, dict):
                    method_sig = _normalize_text(entry.get("method_signature") or entry.get("method_sig"))
                    if method_sig:
                        partition_detail[method_sig] = entry
        if partition_detail:
            detail_map[partition_id] = partition_detail
    return detail_map


def _detect_terminal_nodes(order: List[str], partition_methods: Set[str], call_graph: Dict[str, Set[str]]) -> List[str]:
    terminal_nodes: List[str] = []
    for method_sig in order:
        internal_callees = [callee for callee in call_graph.get(method_sig, set()) if callee in partition_methods]
        if not internal_callees:
            terminal_nodes.append(method_sig)
    return terminal_nodes


def _build_process_from_entry(
    partition_id: str,
    entry_sig: str,
    partition_methods: Set[str],
    call_graph: Dict[str, Set[str]],
    method_node_map: Dict[str, str],
    entry_detail: Optional[Dict[str, Any]],
    index: int,
    max_steps: int,
) -> Optional[Dict[str, Any]]:
    queue: deque[str] = deque([entry_sig])
    visited: Set[str] = set()
    order: List[str] = []

    while queue and len(order) < max_steps:
        current_sig = queue.popleft()
        if current_sig in visited or current_sig not in partition_methods:
            continue
        visited.add(current_sig)
        order.append(current_sig)

        for callee_sig in sorted(call_graph.get(current_sig, set())):
            if callee_sig in partition_methods and callee_sig not in visited:
                queue.append(callee_sig)

    if not order:
        return None

    process_id = f"process_shadow_{partition_id}_{index + 1}"
    terminal_nodes = _detect_terminal_nodes(order, partition_methods, call_graph)
    step_edges: List[Dict[str, Any]] = []

    for step, method_sig in enumerate(order, start=1):
        step_edges.append(
            {
                "source_method": method_sig,
                "source_node_id": method_node_map.get(method_sig),
                "target_process_id": process_id,
                "type": "STEP_IN_PROCESS",
                "step": step,
            }
        )

    return {
        "process_id": process_id,
        "partition_id": partition_id,
        "entry": entry_sig,
        "entry_node_id": method_node_map.get(entry_sig),
        "entry_score": entry_detail.get("score") if entry_detail else None,
        "entry_reasons": entry_detail.get("reasons") if entry_detail else [],
        "terminal_nodes": terminal_nodes,
        "stepCount": len(order),
        "steps": [
            {
                "step": index_step + 1,
                "method_signature": method_sig,
                "node_id": method_node_map.get(method_sig),
            }
            for index_step, method_sig in enumerate(order)
        ],
        "step_edges": step_edges,
    }


def build_process_shadow(
    partitions: Iterable[Dict[str, Any]],
    partition_analyses: Dict[str, Dict[str, Any]],
    call_graph: Dict[str, Set[str]],
    graph_data: Optional[Dict[str, Any]] = None,
    max_processes_per_partition: int = 5,
    max_steps_per_process: int = 60,
) -> Dict[str, Any]:
    method_node_map = _build_method_node_map(graph_data)
    entry_point_map = _build_entry_point_map(partition_analyses)
    entry_point_detail_map = _build_entry_point_detail_map(partition_analyses)

    processes: List[Dict[str, Any]] = []
    process_edges: List[Dict[str, Any]] = []
    continuity_checks: List[Dict[str, Any]] = []

    for partition in partitions or []:
        partition_id = _normalize_text(partition.get("partition_id") or "unknown")
        partition_methods = set(partition.get("methods", []) or [])
        candidate_entries = entry_point_map.get(partition_id, [])

        dedupe_signatures: Set[Tuple[str, ...]] = set()
        built_for_partition = 0
        for entry_index, entry_sig in enumerate(candidate_entries):
            if built_for_partition >= max_processes_per_partition:
                break
            process = _build_process_from_entry(
                partition_id=partition_id,
                entry_sig=entry_sig,
                partition_methods=partition_methods,
                call_graph=call_graph,
                method_node_map=method_node_map,
                entry_detail=(entry_point_detail_map.get(partition_id) or {}).get(entry_sig),
                index=entry_index,
                max_steps=max_steps_per_process,
            )
            if not process:
                continue

            signature = tuple(step["method_signature"] for step in process.get("steps", []))
            if signature in dedupe_signatures:
                continue
            dedupe_signatures.add(signature)
            processes.append(process)
            process_edges.extend(process.get("step_edges", []))
            built_for_partition += 1

            step_values = [step_edge.get("step") for step_edge in process.get("step_edges", [])]
            continuity_checks.append(
                {
                    "process_id": process["process_id"],
                    "is_continuous": step_values == list(range(1, len(step_values) + 1)),
                    "step_values": step_values,
                }
            )

    return {
        "version": "phase3-shadow-v1",
        "processes": processes,
        "step_edges": process_edges,
        "summary": {
            "process_count": len(processes),
            "step_edge_count": len(process_edges),
            "continuous_process_count": sum(1 for item in continuity_checks if item.get("is_continuous")),
        },
        "continuity_checks": continuity_checks,
    }
