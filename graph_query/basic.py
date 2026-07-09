#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Set, Tuple

from .common import connect_readonly, relation_payload, select_all, sorted_unique


def list_relations(db_path: str) -> List[Dict[str, Any]]:
    with connect_readonly(db_path) as connection:
        rows = select_all(
            connection,
            "SELECT * FROM graph_relations ORDER BY partition_id, method_qn",
        )
    return [relation_payload(row) for row in rows]


def get_node_info(db_path: str, method_qn: str) -> Dict[str, Any]:
    with connect_readonly(db_path) as connection:
        relation_rows = select_all(
            connection,
            "SELECT * FROM graph_relations WHERE method_qn = ? ORDER BY partition_id, method_qn",
            (method_qn,),
        )
        assignment_rows = select_all(
            connection,
            "SELECT * FROM partition_assignments WHERE symbol_qualified_name = ? ORDER BY partition_id, symbol_id",
            (method_qn,),
        )
        reverse_rows = select_all(
            connection,
            "SELECT path_id FROM path_reverse_index WHERE method_qn = ? ORDER BY path_id",
            (method_qn,),
        )
    relations = [relation_payload(row) for row in relation_rows]
    first = relations[0] if relations else {}
    partitions = sorted_unique(
        [item.get("partition_id") for item in relations] + [item.get("partition_id") for item in assignment_rows]
    )
    return {
        "found": bool(relations or assignment_rows or reverse_rows),
        "method_qn": method_qn,
        "symbol_id": first.get("symbol_id") or (assignment_rows[0].get("symbol_id") if assignment_rows else None),
        "file_path": first.get("file_path"),
        "line_start": first.get("line_start"),
        "line_end": first.get("line_end"),
        "community_label": first.get("community_label"),
        "partitions": partitions,
        "path_ids": sorted_unique([path_id for item in relations for path_id in item.get("path_ids", [])] + [row.get("path_id") for row in reverse_rows]),
        "relations": relations,
    }


def _load_edges(db_path: str) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], Dict[Tuple[str, str], Set[str]]]:
    forward: Dict[str, Set[str]] = defaultdict(set)
    reverse: Dict[str, Set[str]] = defaultdict(set)
    edge_paths: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    with connect_readonly(db_path) as connection:
        rows = select_all(connection, "SELECT caller, callee, path_id FROM path_links ORDER BY caller, callee, path_id")
    for row in rows:
        caller = str(row.get("caller") or "")
        callee = str(row.get("callee") or "")
        if not caller or not callee:
            continue
        forward[caller].add(callee)
        reverse[callee].add(caller)
        edge_paths[(caller, callee)].add(str(row.get("path_id") or ""))
    return forward, reverse, edge_paths


def _chains_from_edges(db_path: str, method_qn: str, depth: int, reverse_mode: bool) -> List[Dict[str, Any]]:
    depth = max(1, int(depth or 1))
    forward, reverse, edge_paths = _load_edges(db_path)
    graph = reverse if reverse_mode else forward
    queue = deque([(method_qn, [method_qn])])
    results: List[Dict[str, Any]] = []
    while queue:
        node, chain = queue.popleft()
        if len(chain) - 1 >= depth:
            continue
        for nxt in sorted(graph.get(node, set())):
            if nxt in chain:
                continue
            raw_chain = chain + [nxt]
            display_chain = list(reversed(raw_chain)) if reverse_mode else raw_chain
            edge_pairs = list(zip(display_chain, display_chain[1:]))
            path_ids = sorted_unique(path_id for pair in edge_pairs for path_id in edge_paths.get(pair, set()))
            results.append(
                {
                    "method_qn": method_qn,
                    "chain": display_chain,
                    "depth": len(display_chain) - 1,
                    "path_ids": path_ids,
                    "direction": "reverse" if reverse_mode else "forward",
                }
            )
            queue.append((nxt, raw_chain))
    return sorted(results, key=lambda item: (int(item.get("depth") or 0), item.get("chain", [])))


def find_callers(db_path: str, method_qn: str, depth: int = 1) -> List[Dict[str, Any]]:
    return _chains_from_edges(db_path, method_qn, depth, reverse_mode=True)


def find_callees(db_path: str, method_qn: str, depth: int = 1) -> List[Dict[str, Any]]:
    return _chains_from_edges(db_path, method_qn, depth, reverse_mode=False)
