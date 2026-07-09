#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from .basic import list_relations
from .common import connect_readonly, parse_json, select_all, table_counts


def _method_edges(db_path: str) -> Tuple[Set[str], Dict[str, Set[str]], Dict[str, Set[str]], Dict[str, int]]:
    nodes: Set[str] = set()
    outgoing: Dict[str, Set[str]] = defaultdict(set)
    incoming: Dict[str, Set[str]] = defaultdict(set)
    link_counts: Dict[str, int] = defaultdict(int)
    with connect_readonly(db_path) as connection:
        rows = select_all(connection, "SELECT caller, callee FROM path_links ORDER BY caller, callee")
    for row in rows:
        caller = str(row.get("caller") or "")
        callee = str(row.get("callee") or "")
        if not caller or not callee:
            continue
        nodes.update([caller, callee])
        outgoing[caller].add(callee)
        incoming[callee].add(caller)
        link_counts[caller] += 1
        link_counts[callee] += 1
    return nodes, outgoing, incoming, link_counts


def _pagerank(nodes: Set[str], outgoing: Dict[str, Set[str]], iterations: int = 30, damping: float = 0.85) -> Dict[str, float]:
    if not nodes:
        return {}
    count = len(nodes)
    scores = {node: 1.0 / count for node in nodes}
    base = (1.0 - damping) / count
    for _ in range(iterations):
        next_scores = {node: base for node in nodes}
        sink_score = sum(scores[node] for node in nodes if not outgoing.get(node))
        sink_share = damping * sink_score / count
        for node in nodes:
            next_scores[node] += sink_share
        for source, targets in outgoing.items():
            if not targets:
                continue
            share = damping * scores.get(source, 0.0) / len(targets)
            for target in targets:
                next_scores[target] = next_scores.get(target, base) + share
        scores = next_scores
    return scores


def find_hubs(db_path: str, top_k: int = 10) -> List[Dict[str, Any]]:
    top_k = max(0, int(top_k or 0))
    nodes, outgoing, incoming, link_counts = _method_edges(db_path)
    relations = list_relations(db_path)
    relation_by_method: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for relation in relations:
        method_qn = str(relation.get("method_qn") or "")
        if method_qn:
            relation_by_method[method_qn].append(relation)
            nodes.add(method_qn)
    scores = _pagerank(nodes, outgoing)
    hubs: List[Dict[str, Any]] = []
    for node in nodes:
        node_relations = relation_by_method.get(node, [])
        hubs.append(
            {
                "method_qn": node,
                "pagerank": round(float(scores.get(node, 0.0)), 10),
                "indegree": len(incoming.get(node, set())),
                "outdegree": len(outgoing.get(node, set())),
                "path_link_count": int(link_counts.get(node, 0)),
                "path_count": int(sum(item.get("path_count") or 0 for item in node_relations)),
                "partition_ids": sorted({str(item.get("partition_id")) for item in node_relations if item.get("partition_id")}),
                "community_labels": sorted({str(item.get("community_label")) for item in node_relations if item.get("community_label")}),
            }
        )
    return sorted(
        hubs,
        key=lambda item: (
            -float(item.get("pagerank") or 0.0),
            -int(item.get("indegree") or 0),
            -int(item.get("path_link_count") or 0),
            str(item.get("method_qn") or ""),
        ),
    )[:top_k]


def get_partition_topology(db_path: str) -> List[Dict[str, Any]]:
    with connect_readonly(db_path) as connection:
        rows = select_all(
            connection,
            "SELECT * FROM partition_topology ORDER BY source_partition, target_partition",
        )
    for row in rows:
        row["call_examples"] = parse_json(row.pop("call_examples_json", None), []) or []
    return rows


def get_architecture(db_path: str, top_k: int = 5) -> Dict[str, Any]:
    with connect_readonly(db_path) as connection:
        counts = table_counts(
            connection,
            ["partitions", "paths", "graph_relations", "community_summaries", "partition_topology"],
        )
        community_rows = select_all(
            connection,
            "SELECT partition_id, semantic_label, name, status FROM community_summaries ORDER BY partition_id",
        )
    labels = [row.get("semantic_label") or row.get("name") for row in community_rows if row.get("semantic_label") or row.get("name")]
    return {
        "partition_count": int(counts.get("partitions", 0)),
        "path_count": int(counts.get("paths", 0)),
        "relation_count": int(counts.get("graph_relations", 0)),
        "community_summary_count": int(counts.get("community_summaries", 0)),
        "partition_topology_count": int(counts.get("partition_topology", 0)),
        "community_labels": sorted(str(label) for label in labels),
        "top_hubs": find_hubs(db_path, top_k=top_k),
    }
