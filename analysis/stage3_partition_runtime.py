#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import copy
import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from analysis.multi_source_info_collector import MultiSourceInfoCollector


def clone_partition(partition: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(partition if isinstance(partition, dict) else {})


def compute_cohesion_score(partition: Dict[str, Any]) -> float:
    total_calls = int(partition.get("internal_calls") or 0) + int(partition.get("external_calls") or 0)
    return (int(partition.get("internal_calls") or 0) / total_calls) if total_calls > 0 else 1.0


def sort_partitions(partitions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        partitions,
        key=lambda item: (
            -int(item.get("size") or len(item.get("methods") or []) or len(item.get("qualified_methods") or [])),
            tuple(str(method) for method in (item.get("methods") or [])),
            str(item.get("partition_id") or ""),
        ),
    )


def prepare_partitions_for_optimizer(partitions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for partition in partitions or []:
        partition_copy = clone_partition(partition)
        partition_copy["methods"] = list(partition_copy.get("qualified_methods") or partition_copy.get("methods") or [])
        partition_copy["qualified_methods"] = list(partition_copy.get("qualified_methods") or partition_copy.get("methods") or [])
        partition_copy.setdefault("size", len(partition_copy.get("methods") or []))
        partition_copy.setdefault("name", partition_copy.get("partition_id") or "unknown")
        partition_copy["cohesion_score"] = float(partition_copy.get("cohesion_score") or compute_cohesion_score(partition_copy))
        prepared.append(partition_copy)
    return sort_partitions(prepared)


def restore_optimized_partitions(
    optimized_partitions: List[Dict[str, Any]],
    original_partitions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    qn_to_member: Dict[str, Dict[str, str]] = {}
    symbol_id_to_member: Dict[str, Dict[str, str]] = {}
    original_by_partition_id: Dict[str, Dict[str, Any]] = {}

    for partition in original_partitions or []:
        partition_id = str(partition.get("partition_id") or "")
        if partition_id:
            original_by_partition_id[partition_id] = clone_partition(partition)
        member_symbols = partition.get("member_symbols") or []
        if isinstance(member_symbols, list):
            for item in member_symbols:
                if not isinstance(item, dict):
                    continue
                symbol_id = str(item.get("symbol_id") or "").strip()
                qualified_name = str(item.get("qualified_name") or "").strip()
                normalized = {
                    "symbol_id": symbol_id or qualified_name,
                    "qualified_name": qualified_name or symbol_id,
                }
                if normalized["qualified_name"]:
                    qn_to_member[normalized["qualified_name"]] = normalized
                if normalized["symbol_id"]:
                    symbol_id_to_member[normalized["symbol_id"]] = normalized

    restored: List[Dict[str, Any]] = []
    for index, partition in enumerate(optimized_partitions or []):
        partition_copy = clone_partition(partition)
        base_partition = original_by_partition_id.get(str(partition_copy.get("partition_id") or ""), {})
        raw_methods = [str(item).strip() for item in (partition_copy.get("methods") or []) if str(item).strip()]
        member_symbols: List[Dict[str, str]] = []
        for item in raw_methods:
            normalized = qn_to_member.get(item) or symbol_id_to_member.get(item) or {
                "symbol_id": item,
                "qualified_name": item,
            }
            member_symbols.append(normalized)
        unique_members = sorted(
            {
                (entry["symbol_id"], entry["qualified_name"])
                for entry in member_symbols
                if entry.get("symbol_id") or entry.get("qualified_name")
            }
        )
        normalized_members = [
            {"symbol_id": symbol_id, "qualified_name": qualified_name}
            for symbol_id, qualified_name in unique_members
        ]
        restored_partition = clone_partition(base_partition if base_partition else {})
        restored_partition.update(partition_copy)
        restored_partition["partition_id"] = str(restored_partition.get("partition_id") or f"partition_{index}")
        restored_partition["member_symbols"] = normalized_members
        restored_partition["methods"] = [item["symbol_id"] for item in normalized_members]
        restored_partition["qualified_methods"] = [item["qualified_name"] for item in normalized_members]
        restored_partition["size"] = len(normalized_members)
        restored_partition["name"] = str(restored_partition.get("name") or restored_partition["partition_id"])
        restored_partition["cohesion_score"] = float(restored_partition.get("cohesion_score") or compute_cohesion_score(restored_partition))
        restored.append(restored_partition)
    return sort_partitions(restored)


def build_skip_history(plan: Dict[str, Any], status: str = "skipped") -> List[Dict[str, Any]]:
    return [
        {
            "iteration": 0,
            "action": status,
            "partitions_before": [],
            "partitions_after": [],
            "modularity_before": float(plan.get("avg_modularity") or 0.0),
            "modularity_after": float(plan.get("avg_modularity") or 0.0),
            "modularity_improvement": 0.0,
            "llm_reasoning": str(plan.get("reason") or ""),
            "details": {"trigger_mode": plan.get("trigger_mode"), "status": status},
            "trigger_mode": str(plan.get("trigger_mode") or "skip"),
            "threshold": float(plan.get("threshold") or 0.4),
            "status": status,
            "skip_reason": str(plan.get("reason") or ""),
        }
    ]


def build_error_history(plan: Dict[str, Any], error: Exception) -> List[Dict[str, Any]]:
    history = build_skip_history(plan, status="error")
    history[0]["llm_reasoning"] = str(error)
    history[0]["details"] = {"trigger_mode": plan.get("trigger_mode"), "error": str(error)}
    history[0]["skip_reason"] = str(error)
    return history


def _read_readme_keywords(project_path: str) -> List[str]:
    if not project_path:
        return []
    for candidate in ("README.md", "readme.md", "README.txt", "README.rst"):
        path = os.path.join(project_path, candidate)
        if not os.path.isfile(path):
            continue
        try:
            text = open(path, "r", encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        keywords: List[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                keywords.append(stripped.lstrip("#").strip())
        keywords.extend(re.findall(r"[-*]\s+(.+)", text))
        normalized = [item.strip() for item in keywords if str(item).strip()]
        return list(dict.fromkeys(normalized))[:10]
    return []


def build_multi_source_info(project_path: Optional[str], report: Any = None) -> Dict[str, Any]:
    normalized_project_path = str(project_path or "").strip()
    if normalized_project_path and report is not None:
        try:
            return MultiSourceInfoCollector(normalized_project_path, report).collect_all()
        except Exception:
            pass
    return {
        "readme": {
            "content": "",
            "keywords": _read_readme_keywords(normalized_project_path),
        }
    }


def build_stage3_run_id(source: str = "stage3", stable_token: str = "") -> str:
    normalized_source = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(source or "stage3"))
    if stable_token:
        digest = hashlib.md5(str(stable_token).encode("utf-8")).hexdigest()[:16]
        return f"{normalized_source[:48]}_{digest}"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{normalized_source[:48]}_{timestamp}"
