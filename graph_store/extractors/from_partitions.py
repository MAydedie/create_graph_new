#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict, List, Optional

from graph_store.schema import PartitionMemberRecord, PartitionRecord


def extract_partition_records(
    partitions: List[Dict[str, Any]],
    source_project_path: Optional[str] = None,
) -> List[PartitionRecord]:
    records: List[PartitionRecord] = []
    for partition in partitions or []:
        methods = sorted(str(method) for method in (partition.get("methods") or []) if str(method).strip())
        records.append(
            PartitionRecord(
                partition_id=str(partition.get("partition_id") or "unknown"),
                name=str(partition.get("name") or partition.get("partition_id") or "unknown"),
                original_name=(
                    str(partition.get("original_name"))
                    if partition.get("original_name") not in {None, ""}
                    else None
                ),
                modularity=float(partition.get("modularity") or 0.0),
                cohesion_score=float(partition.get("cohesion_score") or 0.0),
                internal_calls=int(partition.get("internal_calls") or 0),
                external_calls=int(partition.get("external_calls") or 0),
                size=int(partition.get("size") or len(methods)),
                method_count=len(methods),
                source_project_path=source_project_path,
            )
        )
    return sorted(records, key=lambda item: item.partition_id)


def extract_partition_members(partitions: List[Dict[str, Any]]) -> List[PartitionMemberRecord]:
    members: List[PartitionMemberRecord] = []
    for partition in partitions or []:
        partition_id = str(partition.get("partition_id") or "unknown")
        member_symbols = partition.get("member_symbols") or []
        if member_symbols:
            normalized_symbols = sorted(
                [item for item in member_symbols if isinstance(item, dict) and str(item.get("symbol_id") or "").strip()],
                key=lambda item: (
                    str(item.get("symbol_id") or ""),
                    str(item.get("qualified_name") or ""),
                ),
            )
        else:
            normalized_symbols = [
                {
                    "symbol_id": str(symbol_id),
                    "qualified_name": str(symbol_id),
                }
                for symbol_id in sorted(str(method) for method in (partition.get("methods") or []) if str(method).strip())
            ]

        for index, symbol_payload in enumerate(normalized_symbols):
            members.append(
                PartitionMemberRecord(
                    partition_id=partition_id,
                    member_order=index,
                    symbol_id=str(symbol_payload.get("symbol_id") or "").strip(),
                    symbol_qualified_name=str(symbol_payload.get("qualified_name") or "").strip(),
                )
            )
    return sorted(members, key=lambda item: (item.partition_id, item.member_order, item.symbol_id, item.symbol_qualified_name))
