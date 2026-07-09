#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from graph_store.schema import CommunitySummaryHistoryRecord, CommunitySummaryRecord


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
    return [{"symbol_id": method, "qualified_name": method} for method in sorted(methods)]


def extract_community_summary_records(
    summaries: List[Dict[str, Any]],
    *,
    community_run_id: str,
    source_project_path: Optional[str],
    trigger_mode: str,
    threshold: float,
) -> List[CommunitySummaryRecord]:
    records: List[CommunitySummaryRecord] = []
    for summary in summaries or []:
        methods = sorted(str(item).strip() for item in (summary.get("methods") or []) if str(item).strip())
        qualified_methods = sorted(
            str(item).strip() for item in (summary.get("qualified_methods") or []) if str(item).strip()
        )
        member_symbols = _normalize_member_symbols(summary)
        records.append(
            CommunitySummaryRecord(
                community_run_id=community_run_id,
                partition_id=str(summary.get("partition_id") or "unknown"),
                name=str(summary.get("name") or summary.get("partition_id") or "unknown"),
                original_name=(
                    str(summary.get("original_name"))
                    if summary.get("original_name") not in {None, ""}
                    else None
                ),
                modularity=float(summary.get("modularity") or 0.0),
                cohesion_score=float(summary.get("cohesion_score") or summary.get("cohesion") or 0.0),
                internal_calls=int(summary.get("internal_calls") or 0),
                external_calls=int(summary.get("external_calls") or 0),
                size=int(summary.get("size") or len(methods) or len(qualified_methods)),
                method_count=max(len(methods), len(qualified_methods), len(member_symbols)),
                methods_json=json.dumps(methods, ensure_ascii=False, sort_keys=True),
                qualified_methods_json=json.dumps(qualified_methods, ensure_ascii=False, sort_keys=True),
                member_symbols_json=json.dumps(member_symbols, ensure_ascii=False, sort_keys=True),
                semantic_label=str(summary.get("label") or summary.get("semantic_label") or "").strip(),
                description=str(summary.get("description") or "").strip(),
                functional_domain=str(summary.get("functional_domain") or "").strip(),
                key_concepts_json=json.dumps(summary.get("key_concepts") or [], ensure_ascii=False, sort_keys=True),
                top_files_json=json.dumps(summary.get("top_files") or [], ensure_ascii=False, sort_keys=True),
                top_dependencies_json=json.dumps(summary.get("top_dependencies") or [], ensure_ascii=False, sort_keys=True),
                source_project_path=source_project_path,
                trigger_mode=trigger_mode,
                threshold=float(threshold),
                status=str(summary.get("summary_status") or summary.get("status") or "completed"),
                skip_reason=(
                    str(summary.get("skip_reason"))
                    if summary.get("skip_reason") not in {None, ""}
                    else None
                ),
                model=(str(summary.get("model")) if summary.get("model") not in {None, ""} else None),
                duration_ms=int(summary.get("duration_ms") or 0),
            )
        )
    return sorted(records, key=lambda item: item.partition_id)


def extract_community_summary_history_records(
    history_entries: List[Dict[str, Any]],
    *,
    community_run_id: str,
    source_project_path: Optional[str],
    trigger_mode: str,
    threshold: float,
) -> List[CommunitySummaryHistoryRecord]:
    records: List[CommunitySummaryHistoryRecord] = []
    for index, entry in enumerate(history_entries or []):
        records.append(
            CommunitySummaryHistoryRecord(
                community_run_id=community_run_id,
                history_index=index,
                partition_id=str(entry.get("partition_id") or "unknown"),
                action=str(entry.get("action") or "summary"),
                status=str(entry.get("status") or "completed"),
                llm_reasoning=str(entry.get("llm_reasoning") or "").strip(),
                details_json=json.dumps(entry.get("details") or {}, ensure_ascii=False, sort_keys=True),
                source_project_path=source_project_path,
                trigger_mode=str(entry.get("trigger_mode") or trigger_mode),
                threshold=float(entry.get("threshold") or threshold),
                skip_reason=(
                    str(entry.get("skip_reason"))
                    if entry.get("skip_reason") not in {None, ""}
                    else None
                ),
                model=(str(entry.get("model")) if entry.get("model") not in {None, ""} else None),
                duration_ms=int(entry.get("duration_ms") or 0),
            )
        )
    return records
