#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from graph_store.schema import OptimizationHistoryRecord, OptimizedPartitionRecord


def _normalize_member_symbols(partition: Dict[str, Any]) -> List[Dict[str, str]]:
    member_symbols = partition.get("member_symbols") or []
    normalized = [
        {
            "symbol_id": str(item.get("symbol_id") or "").strip(),
            "qualified_name": str(item.get("qualified_name") or "").strip(),
        }
        for item in member_symbols
        if isinstance(item, dict)
    ]
    normalized = [item for item in normalized if item["symbol_id"] or item["qualified_name"]]
    if normalized:
        return sorted(normalized, key=lambda item: (item["symbol_id"], item["qualified_name"]))

    methods = [str(item).strip() for item in (partition.get("methods") or []) if str(item).strip()]
    qualified_methods = [str(item).strip() for item in (partition.get("qualified_methods") or []) if str(item).strip()]
    pairs = list(zip(methods, qualified_methods)) if qualified_methods and len(qualified_methods) == len(methods) else []
    if pairs:
        return [
            {"symbol_id": symbol_id, "qualified_name": qualified_name}
            for symbol_id, qualified_name in sorted(pairs, key=lambda item: (item[0], item[1]))
        ]
    return [
        {"symbol_id": method, "qualified_name": method}
        for method in sorted(methods)
    ]


def extract_optimized_partition_records(
    partitions: List[Dict[str, Any]],
    *,
    optimization_run_id: str,
    source_project_path: Optional[str],
    trigger_mode: str,
    threshold: float,
    was_optimized: bool,
) -> List[OptimizedPartitionRecord]:
    records: List[OptimizedPartitionRecord] = []
    for partition in partitions or []:
        methods = sorted(str(item).strip() for item in (partition.get("methods") or []) if str(item).strip())
        qualified_methods = sorted(
            str(item).strip() for item in (partition.get("qualified_methods") or []) if str(item).strip()
        )
        member_symbols = _normalize_member_symbols(partition)
        records.append(
            OptimizedPartitionRecord(
                optimization_run_id=optimization_run_id,
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
                size=int(partition.get("size") or len(methods) or len(qualified_methods)),
                method_count=max(len(methods), len(qualified_methods), len(member_symbols)),
                methods_json=json.dumps(methods, ensure_ascii=False, sort_keys=True),
                qualified_methods_json=json.dumps(qualified_methods, ensure_ascii=False, sort_keys=True),
                member_symbols_json=json.dumps(member_symbols, ensure_ascii=False, sort_keys=True),
                source_project_path=source_project_path,
                trigger_mode=trigger_mode,
                threshold=float(threshold),
                was_optimized=bool(was_optimized),
            )
        )
    return sorted(records, key=lambda item: item.partition_id)


def extract_optimization_history_records(
    history_entries: List[Dict[str, Any]],
    *,
    optimization_run_id: str,
    source_project_path: Optional[str],
    trigger_mode: str,
    threshold: float,
) -> List[OptimizationHistoryRecord]:
    records: List[OptimizationHistoryRecord] = []
    for index, entry in enumerate(history_entries or []):
        records.append(
            OptimizationHistoryRecord(
                optimization_run_id=optimization_run_id,
                history_index=index,
                iteration=int(entry.get("iteration") or 0),
                action=str(entry.get("action") or "unknown"),
                partitions_before_json=json.dumps(entry.get("partitions_before") or [], ensure_ascii=False, sort_keys=True),
                partitions_after_json=json.dumps(entry.get("partitions_after") or [], ensure_ascii=False, sort_keys=True),
                modularity_before=float(entry.get("modularity_before") or 0.0),
                modularity_after=float(entry.get("modularity_after") or 0.0),
                modularity_improvement=float(entry.get("modularity_improvement") or 0.0),
                llm_reasoning=str(entry.get("llm_reasoning") or ""),
                details_json=json.dumps(entry.get("details") or {}, ensure_ascii=False, sort_keys=True),
                source_project_path=source_project_path,
                trigger_mode=str(entry.get("trigger_mode") or trigger_mode),
                threshold=float(entry.get("threshold") or threshold),
                status=str(entry.get("status") or "completed"),
                skip_reason=(
                    str(entry.get("skip_reason"))
                    if entry.get("skip_reason") not in {None, ""}
                    else None
                ),
            )
        )
    return records
