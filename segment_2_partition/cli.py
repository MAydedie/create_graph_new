#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Set


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from analysis.community_detector import CommunityDetector
from analysis.function_call_graph_generator import FunctionCallGraphGenerator
from data.project_library_storage import ProjectLibraryStorage
from graph_store.partition_topology import build_partition_topology
from graph_store.sqlite_store import persist_stage2_snapshot


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage 2 partition analysis: stage1_output.json -> segment2_output.json",
    )
    parser.add_argument("--input", required=True, help="Path to segment1_output.json")
    parser.add_argument("--output", required=True, help="Path to segment2_output.json")
    parser.add_argument("--graph-db", default=None, help="Optional output path for graph.db")
    parser.add_argument(
        "--algorithm",
        default="louvain",
        choices=["louvain", "leiden", "greedy_modularity", "label_propagation"],
        help="Community detection algorithm",
    )
    parser.add_argument(
        "--weight-threshold",
        "--threshold",
        dest="weight_threshold",
        type=float,
        default=0.0,
        help="Ignore edges below threshold",
    )
    parser.add_argument("--random-state", type=int, default=42, help="Deterministic seed")
    parser.add_argument("--verbose", action="store_true", help="Print extra progress logs")
    return parser


def _load_json(path: str) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("输入 JSON 顶层必须是对象")
    return payload


def _normalize_symbol_kind(symbol: Dict[str, Any]) -> str:
    return str(symbol.get("kind") or "").strip().lower()


def _build_symbol_indexes(stage1_payload: Dict[str, Any]) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    qn_to_symbol: Dict[str, Dict[str, Any]] = {}
    simple_name_to_qn: Dict[str, str] = {}
    collisions: Set[str] = set()

    for symbol in stage1_payload.get("symbols", []) or []:
        if not isinstance(symbol, dict):
            continue
        if _normalize_symbol_kind(symbol) not in {"method", "function"}:
            continue
        qn = str(symbol.get("qualified_name") or "").strip()
        symbol_id = str(symbol.get("id") or "").strip()
        if not qn or not symbol_id:
            continue
        qn_to_symbol[qn] = symbol
        simple_name = qn.split(".")[-1]
        if simple_name in simple_name_to_qn and simple_name_to_qn[simple_name] != qn:
            collisions.add(simple_name)
        else:
            simple_name_to_qn[simple_name] = qn

    for collision in collisions:
        simple_name_to_qn.pop(collision, None)

    return qn_to_symbol, simple_name_to_qn


def _resolve_symbol(name: str, qn_to_symbol: Dict[str, Dict[str, Any]], simple_name_to_qn: Dict[str, str]) -> Dict[str, Any] | None:
    normalized = str(name or "").strip()
    if not normalized:
        return None

    direct = qn_to_symbol.get(normalized)
    if direct:
        return direct

    simple_name = normalized.split(".")[-1]
    resolved_qn = simple_name_to_qn.get(simple_name)
    if not resolved_qn:
        return None
    return qn_to_symbol.get(resolved_qn)


def _normalize_call_graph(
    payload: Dict[str, Any],
    qn_to_symbol: Dict[str, Dict[str, Any]],
    simple_name_to_qn: Dict[str, str],
) -> Dict[str, Set[str]]:
    adjacency = (((payload.get("call_graph") or {}).get("adjacency")) or {})
    call_graph: Dict[str, Set[str]] = {}
    for caller, callees in sorted(adjacency.items(), key=lambda item: str(item[0])):
        caller_symbol = _resolve_symbol(str(caller), qn_to_symbol, simple_name_to_qn)
        if not caller_symbol:
            continue
        caller_qn = str(caller_symbol.get("qualified_name") or "").strip()
        normalized_callees = {
            str(resolved_symbol.get("qualified_name") or "").strip()
            for item in (callees or [])
            for resolved_symbol in [_resolve_symbol(str(item), qn_to_symbol, simple_name_to_qn)]
            if resolved_symbol and str(resolved_symbol.get("qualified_name") or "").strip()
        }
        call_graph[caller_qn] = set(sorted(normalized_callees))
    return call_graph


def _resolve_partition_methods(
    partitions: List[Dict[str, Any]],
    qn_to_symbol: Dict[str, Dict[str, Any]],
    simple_name_to_qn: Dict[str, str],
) -> List[Dict[str, Any]]:
    resolved: List[Dict[str, Any]] = []
    for idx, partition in enumerate(partitions):
        methods = partition.get("methods", []) or []
        resolved_symbols: List[Dict[str, str]] = []
        seen_symbol_ids: Set[str] = set()

        for method in methods:
            resolved_symbol = _resolve_symbol(str(method), qn_to_symbol, simple_name_to_qn)
            if not resolved_symbol:
                continue
            symbol_id = str(resolved_symbol.get("id") or "").strip()
            qualified_name = str(resolved_symbol.get("qualified_name") or "").strip()
            if not symbol_id or not qualified_name or symbol_id in seen_symbol_ids:
                continue
            seen_symbol_ids.add(symbol_id)
            resolved_symbols.append(
                {
                    "symbol_id": symbol_id,
                    "qualified_name": qualified_name,
                }
            )

        resolved_symbols.sort(key=lambda item: (item["symbol_id"], item["qualified_name"]))
        resolved_method_ids = [item["symbol_id"] for item in resolved_symbols]
        resolved_qualified_methods = [item["qualified_name"] for item in resolved_symbols]

        partition_copy = copy.deepcopy(partition)
        partition_copy["partition_id"] = str(partition_copy.get("partition_id") or f"partition_{idx}")
        partition_copy["methods"] = resolved_method_ids
        partition_copy["qualified_methods"] = resolved_qualified_methods
        partition_copy["member_symbols"] = resolved_symbols
        partition_copy["size"] = len(resolved_method_ids)
        partition_copy["name"] = partition_copy.get("name") or partition_copy["partition_id"]
        internal_calls = int(partition_copy.get("internal_calls") or 0)
        external_calls = int(partition_copy.get("external_calls") or 0)
        total_calls = internal_calls + external_calls
        partition_copy["cohesion_score"] = (internal_calls / total_calls) if total_calls > 0 else 1.0
        resolved.append(partition_copy)
    return resolved


def _deduplicate_and_resolve_name_conflicts(partitions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not partitions:
        return []

    seen_method_sets: Dict[frozenset[str], Dict[str, Any]] = {}
    unique_partitions: List[Dict[str, Any]] = []
    for partition in partitions:
        method_set = frozenset(partition.get("methods", []) or [])
        if method_set in seen_method_sets:
            existing = seen_method_sets[method_set]
            if partition.get("modularity", 0) > existing.get("modularity", 0):
                existing["modularity"] = partition.get("modularity", 0)
        else:
            seen_method_sets[method_set] = partition
            unique_partitions.append(partition)

    name_to_partitions: Dict[str, List[Dict[str, Any]]] = {}
    for partition in unique_partitions:
        name = str(partition.get("name") or "未知分区")
        name_to_partitions.setdefault(name, []).append(partition)

    for name, same_name_partitions in sorted(name_to_partitions.items(), key=lambda item: item[0]):
        if len(same_name_partitions) > 1:
            for idx, partition in enumerate(same_name_partitions[1:], start=1):
                original_name = partition.get("name", "未知分区")
                partition["name"] = f"{original_name}-{idx}"
                partition["original_name"] = original_name

    final_partitions = sorted(
        unique_partitions,
        key=lambda part: (
            -(part.get("size") or 0),
            tuple(part.get("methods", []) or []),
            str(part.get("name") or ""),
        ),
    )
    for idx, partition in enumerate(final_partitions):
        partition["partition_id"] = f"partition_{idx}"
    return final_partitions


def _normalize_partition_call_graph(payload: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(payload or {})
    result["nodes"] = sorted(
        result.get("nodes", []) or [],
        key=lambda node: (
            str(node.get("is_internal", False)),
            str(node.get("id") or ""),
            str(node.get("label") or ""),
        ),
    )
    result["internal_edges"] = sorted(
        result.get("internal_edges", []) or [],
        key=lambda edge: (str(edge.get("source") or ""), str(edge.get("target") or ""), str(edge.get("type") or "")),
    )
    result["external_edges"] = sorted(
        result.get("external_edges", []) or [],
        key=lambda edge: (str(edge.get("source") or ""), str(edge.get("target") or ""), str(edge.get("type") or "")),
    )
    return result


def _resolve_graph_db_path(stage1_payload: Dict[str, Any], output_path: str, graph_db_path: str | None) -> Path:
    if graph_db_path:
        return Path(graph_db_path)
    project_path = str((((stage1_payload.get("project") or {}).get("path")) or "")).strip()
    if project_path:
        return ProjectLibraryStorage().graph_db_path(project_path)
    return Path(output_path).resolve().parent / "graph.db"


def run_stage2(
    input_path: str,
    output_path: str,
    algorithm: str = "louvain",
    weight_threshold: float = 0.0,
    random_state: int = 42,
    verbose: bool = False,
    graph_db_path: str | None = None,
) -> Path:
    stage1_payload = _load_json(input_path)
    qn_to_symbol, simple_name_to_qn = _build_symbol_indexes(stage1_payload)
    call_graph = _normalize_call_graph(stage1_payload, qn_to_symbol, simple_name_to_qn)
    if not call_graph:
        raise ValueError("输入文件中未找到可解析到 stage1 Symbol.id 的有效调用图")

    detector = CommunityDetector()
    raw_partitions = detector.detect_communities(
        call_graph,
        algorithm=algorithm,
        weight_threshold=weight_threshold,
        random_state=random_state,
    )
    resolved_partitions = _resolve_partition_methods(raw_partitions, qn_to_symbol, simple_name_to_qn)
    partitions = _deduplicate_and_resolve_name_conflicts(resolved_partitions)

    generator = FunctionCallGraphGenerator(call_graph)
    partition_call_graphs: Dict[str, Dict[str, Any]] = {}
    for partition in partitions:
        partition_id = partition.get("partition_id", "unknown")
        graph_partition = dict(partition)
        graph_partition["methods"] = list(partition.get("qualified_methods") or [])
        partition_call_graphs[partition_id] = _normalize_partition_call_graph(
            generator.generate_partition_call_graph(graph_partition)
        )

    topology = build_partition_topology(partitions, partition_call_graphs)
    stats = detector.get_statistics()
    resolved_graph_db_path = _resolve_graph_db_path(stage1_payload, output_path, graph_db_path)
    project_path = str((((stage1_payload.get("project") or {}).get("path")) or "")).strip() or None
    persist_stage2_snapshot(
        db_path=str(resolved_graph_db_path),
        partitions=partitions,
        partition_topology=topology,
        source_project_path=project_path,
    )
    output_payload = {
        "schema_version": "stage2.v1",
        "input": {
            "stage1_output_path": os.path.normpath(input_path).replace("\\", "/"),
            "algorithm": algorithm,
            "weight_threshold": weight_threshold,
            "random_state": random_state,
        },
        "project": copy.deepcopy(stage1_payload.get("project") or {}),
        "artifacts": {
            "graph_db_path": str(resolved_graph_db_path).replace("\\", "/"),
        },
        "summary": {
            "partition_count": len(partitions),
            "total_partitioned_methods": sum(len(partition.get("methods", []) or []) for partition in partitions),
            "avg_modularity": stats.get("avg_modularity", 0.0),
            "max_modularity": stats.get("max_modularity", 0.0),
            "min_modularity": stats.get("min_modularity", 0.0),
            "cross_partition_edge_count": sum(item.get("edge_count", 0) for item in topology),
        },
        "partitions": partitions,
        "partition_statistics": stats,
        "partition_topology": topology,
        "partition_call_graphs": {
            key: partition_call_graphs[key]
            for key in sorted(partition_call_graphs.keys())
        },
    }

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(output_payload, handle, indent=2, ensure_ascii=False, sort_keys=True)

    if verbose:
        print("[segment_2_partition] 输出完成")
        print(f"  output: {output_file}")
        print(f"  partitions: {output_payload['summary']['partition_count']}")
        print(f"  avg_modularity: {output_payload['summary']['avg_modularity']}")
        print(f"  cross_partition_edges: {output_payload['summary']['cross_partition_edge_count']}")

    return output_file


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        run_stage2(
            input_path=args.input,
            output_path=args.output,
            algorithm=args.algorithm,
            weight_threshold=float(args.weight_threshold),
            random_state=int(args.random_state),
            verbose=bool(args.verbose),
            graph_db_path=args.graph_db,
        )
        return 0
    except Exception as exc:
        print(f"[segment_2_partition] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
