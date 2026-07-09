#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Set, Tuple

from .common import connect_readonly, parse_json, select_all, sorted_unique


def _path_row_to_detail(db_path: str, path_id: str) -> Dict[str, Any]:
    with connect_readonly(db_path) as connection:
        path_rows = select_all(connection, "SELECT * FROM paths WHERE path_id = ?", (path_id,))
        if not path_rows:
            return {"path_id": path_id, "found": False}
        row = path_rows[0]
        links = select_all(
            connection,
            "SELECT * FROM path_links WHERE path_id = ? ORDER BY step_index, link_id",
            (path_id,),
        )
        cfg_nodes = select_all(
            connection,
            "SELECT * FROM path_cfg WHERE path_id = ? ORDER BY method_sig, line_number, node_id",
            (path_id,),
        )
        dfg_nodes = select_all(
            connection,
            "SELECT * FROM path_dfg WHERE path_id = ? ORDER BY method_sig, line_number, node_id, variable_name",
            (path_id,),
        )
    return {
        "found": True,
        "path_id": row.get("path_id"),
        "partition_id": row.get("partition_id"),
        "leaf_node": row.get("leaf_node"),
        "function_chain": parse_json(row.get("function_chain_json"), []) or [],
        "path_name": row.get("path_name"),
        "path_description": row.get("path_description"),
        "semantic_label": row.get("semantic_label"),
        "keywords": parse_json(row.get("keywords_json"), []) or [],
        "functional_domain": row.get("functional_domain"),
        "worthiness_score": row.get("worthiness_score"),
        "deep_analysis_status": row.get("deep_analysis_status"),
        "cfg_dfg_explain_md": row.get("cfg_dfg_explain_md"),
        "skip_reason": row.get("skip_reason"),
        "links": links,
        "cfg_nodes": cfg_nodes,
        "dfg_nodes": dfg_nodes,
    }


def get_path_detail(db_path: str, path_id: str) -> Dict[str, Any]:
    return _path_row_to_detail(db_path, path_id)


def _paths_containing_pair(db_path: str, src_qn: str, dst_qn: str, max_depth: int) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    with connect_readonly(db_path) as connection:
        rows = select_all(connection, "SELECT path_id, function_chain_json FROM paths ORDER BY path_id")
    for row in rows:
        chain = [str(item) for item in (parse_json(row.get("function_chain_json"), []) or [])]
        try:
            src_index = chain.index(src_qn)
            dst_index = chain.index(dst_qn, src_index + 1)
        except ValueError:
            continue
        if dst_index - src_index <= max_depth:
            detail = _path_row_to_detail(db_path, str(row.get("path_id")))
            detail["matched_subchain"] = chain[src_index : dst_index + 1]
            matches.append(detail)
    return matches


def _edge_graph(db_path: str) -> Tuple[Dict[str, List[str]], Dict[Tuple[str, str], List[str]]]:
    adjacency: Dict[str, Set[str]] = defaultdict(set)
    edge_paths: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    with connect_readonly(db_path) as connection:
        rows = select_all(connection, "SELECT caller, callee, path_id FROM path_links ORDER BY caller, callee, path_id")
    for row in rows:
        caller = str(row.get("caller") or "")
        callee = str(row.get("callee") or "")
        if not caller or not callee:
            continue
        adjacency[caller].add(callee)
        edge_paths[(caller, callee)].add(str(row.get("path_id") or ""))
    return {node: sorted(targets) for node, targets in adjacency.items()}, {key: sorted_unique(paths) for key, paths in edge_paths.items()}


def _bfs_paths(db_path: str, src_qn: str, dst_qn: str, max_depth: int) -> List[Dict[str, Any]]:
    adjacency, edge_paths = _edge_graph(db_path)
    queue = deque([(src_qn, [src_qn])])
    found: List[Dict[str, Any]] = []
    while queue:
        node, chain = queue.popleft()
        if len(chain) - 1 >= max_depth:
            continue
        for nxt in adjacency.get(node, []):
            if nxt in chain:
                continue
            next_chain = chain + [nxt]
            if nxt == dst_qn:
                linked_path_ids = sorted_unique(
                    path_id
                    for index in range(len(next_chain) - 1)
                    for path_id in edge_paths.get((next_chain[index], next_chain[index + 1]), [])
                )
                found.append(
                    {
                        "found": True,
                        "path_id": "synthetic:" + " -> ".join(next_chain),
                        "function_chain": next_chain,
                        "matched_subchain": next_chain,
                        "source": "path_links_bfs",
                        "linked_path_ids": linked_path_ids,
                    }
                )
            else:
                queue.append((nxt, next_chain))
    return found


def find_paths_between(db_path: str, src_qn: str, dst_qn: str, max_depth: int = 8) -> List[Dict[str, Any]]:
    max_depth = max(1, int(max_depth or 1))
    persisted = _paths_containing_pair(db_path, src_qn, dst_qn, max_depth)
    seen = {str(item.get("path_id")) for item in persisted}
    bfs = [item for item in _bfs_paths(db_path, src_qn, dst_qn, max_depth) if str(item.get("path_id")) not in seen]
    return sorted(persisted + bfs, key=lambda item: str(item.get("path_id") or ""))


def is_on_same_path(db_path: str, a_qn: str, b_qn: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    with connect_readonly(db_path) as connection:
        rows = select_all(connection, "SELECT path_id, function_chain_json FROM paths ORDER BY path_id")
    for row in rows:
        chain = [str(item) for item in (parse_json(row.get("function_chain_json"), []) or [])]
        if a_qn in chain and b_qn in chain:
            detail = _path_row_to_detail(db_path, str(row.get("path_id")))
            detail["matched_methods"] = [a_qn, b_qn]
            matches.append(detail)
    return matches
