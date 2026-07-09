#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict, List


def build_partition_topology(
    partitions: List[Dict[str, Any]],
    partition_call_graphs: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    method_to_partition: Dict[str, str] = {}
    method_to_symbol_id: Dict[str, str] = {}
    partition_ids: List[str] = []
    for partition in partitions or []:
        partition_id = str(partition.get("partition_id") or "unknown")
        partition_ids.append(partition_id)
        member_symbols = partition.get("member_symbols") or []
        if member_symbols:
            for member_symbol in member_symbols:
                if not isinstance(member_symbol, dict):
                    continue
                qualified_name = str(member_symbol.get("qualified_name") or "").strip()
                symbol_id = str(member_symbol.get("symbol_id") or "").strip()
                if not qualified_name:
                    continue
                method_to_partition[qualified_name] = partition_id
                if symbol_id:
                    method_to_symbol_id[qualified_name] = symbol_id
        else:
            for method in sorted(str(item) for item in (partition.get("qualified_methods") or partition.get("methods") or []) if str(item).strip()):
                method_to_partition[method] = partition_id

    matrix: Dict[tuple[str, str], Dict[str, Any]] = {}
    for source_partition in sorted(partition_ids):
        for target_partition in sorted(partition_ids):
            if source_partition == target_partition:
                continue
            matrix[(source_partition, target_partition)] = {
                "source_partition": source_partition,
                "target_partition": target_partition,
                "edge_count": 0,
                "weight": 0.0,
                "call_examples": [],
            }

    for source_partition in sorted(partition_ids):
        call_graph_payload = partition_call_graphs.get(source_partition) or {}
        for edge in call_graph_payload.get("external_edges", []) or []:
            source_method = str(edge.get("source") or "").strip()
            target_method = str(edge.get("target") or "").strip()
            if not source_method or not target_method:
                continue
            target_partition = method_to_partition.get(target_method)
            if not target_partition or target_partition == source_partition:
                continue
            item = matrix[(source_partition, target_partition)]
            item["edge_count"] += 1
            item["weight"] += 1.0
            if len(item["call_examples"]) < 10:
                item["call_examples"].append(
                    {
                        "source_symbol_id": method_to_symbol_id.get(source_method),
                        "source_qualified_name": source_method,
                        "target_symbol_id": method_to_symbol_id.get(target_method),
                        "target_qualified_name": target_method,
                    }
                )

    result = list(matrix.values())
    for item in result:
        item["call_examples"] = sorted(
            item.get("call_examples", []),
            key=lambda pair: (
                str(pair.get("source_symbol_id") or ""),
                str(pair.get("source_qualified_name") or ""),
                str(pair.get("target_symbol_id") or ""),
                str(pair.get("target_qualified_name") or ""),
            ),
        )
    result.sort(key=lambda item: (item["source_partition"], item["target_partition"]))
    return result
