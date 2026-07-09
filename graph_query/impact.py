#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict, List

from .basic import find_callers, get_node_info
from .common import connect_readonly, relation_payload, select_all, sorted_unique
from .path_query import get_path_detail


def impact_analysis(db_path: str, method_qn: str, max_depth: int = 3) -> Dict[str, Any]:
    node = get_node_info(db_path, method_qn)
    callers = find_callers(db_path, method_qn, depth=max_depth)
    with connect_readonly(db_path) as connection:
        reverse_rows = select_all(
            connection,
            "SELECT path_id FROM path_reverse_index WHERE method_qn = ? ORDER BY path_id",
            (method_qn,),
        )
        relation_rows = select_all(
            connection,
            "SELECT * FROM graph_relations WHERE method_qn = ? ORDER BY partition_id",
            (method_qn,),
        )
        partitions = sorted_unique(row.get("partition_id") for row in relation_rows)
        topology_rows: List[Dict[str, Any]] = []
        for partition_id in partitions:
            topology_rows.extend(
                select_all(
                    connection,
                    """
                    SELECT * FROM partition_topology
                    WHERE (source_partition = ? OR target_partition = ?) AND edge_count > 0
                    ORDER BY source_partition, target_partition
                    """,
                    (partition_id, partition_id),
                )
            )
    path_ids = sorted_unique(row.get("path_id") for row in reverse_rows)
    affected_paths = [get_path_detail(db_path, path_id) for path_id in path_ids]
    relation_details = [relation_payload(row) for row in relation_rows]
    return {
        "method_qn": method_qn,
        "node": node,
        "callers": callers,
        "affected_path_ids": path_ids,
        "affected_paths": affected_paths,
        "relations": relation_details,
        "cross_partition_edges": topology_rows,
        "summary": {
            "caller_chain_count": len(callers),
            "affected_path_count": len(path_ids),
            "cross_partition_edge_count": len(topology_rows),
            "max_depth": max_depth,
        },
    }


def detect_unused_functions(db_path: str) -> List[Dict[str, Any]]:
    with connect_readonly(db_path) as connection:
        relation_rows = select_all(connection, "SELECT * FROM graph_relations ORDER BY partition_id, method_qn")
        reverse_methods = {
            str(row.get("method_qn"))
            for row in select_all(connection, "SELECT DISTINCT method_qn FROM path_reverse_index ORDER BY method_qn")
        }
        linked_methods = set()
        for row in select_all(connection, "SELECT caller, callee FROM path_links ORDER BY caller, callee"):
            linked_methods.add(str(row.get("caller")))
            linked_methods.add(str(row.get("callee")))
    unused: List[Dict[str, Any]] = []
    for row in relation_rows:
        method_qn = str(row.get("method_qn") or "")
        if method_qn and method_qn not in reverse_methods and method_qn not in linked_methods:
            detail = relation_payload(row)
            detail["reason"] = "method appears in graph_relations but not in path_reverse_index or path_links"
            unused.append(detail)
    return unused
