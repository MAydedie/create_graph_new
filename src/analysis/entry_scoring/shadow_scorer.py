from __future__ import annotations

import copy
import os
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_test_file(file_path: str, method_name: str) -> bool:
    normalized = _normalize_text(file_path).replace("\\", "/").lower()
    method_lower = method_name.lower()
    if "/tests/" in normalized or normalized.endswith("_test.py") or normalized.endswith("test.py"):
        return True
    if "/test/" in normalized or normalized.startswith("tests/"):
        return True
    if method_lower.startswith("test_"):
        return True
    return False


def _extract_method_metadata(analyzer_report: Any) -> Dict[str, Dict[str, Any]]:
    metadata: Dict[str, Dict[str, Any]] = {}
    if analyzer_report is None:
        return metadata

    for class_name, class_info in getattr(analyzer_report, "classes", {}).items():
        class_file = ""
        if getattr(class_info, "source_location", None):
            class_file = _normalize_text(getattr(class_info.source_location, "file_path", ""))
        for method_name, method_info in getattr(class_info, "methods", {}).items():
            method_sig = f"{class_name}.{method_name}"
            method_file = class_file
            if getattr(method_info, "source_location", None):
                method_file = _normalize_text(getattr(method_info.source_location, "file_path", "")) or class_file
            metadata[method_sig] = {
                "file_path": method_file,
                "source_code": _normalize_text(getattr(method_info, "source_code", "")),
                "is_public": not method_name.startswith("_"),
                "method_name": method_name,
                "is_top_level": False,
            }

    for func_info in getattr(analyzer_report, "functions", []) or []:
        method_sig = _normalize_text(getattr(func_info, "name", ""))
        if not method_sig:
            continue
        file_path = ""
        if getattr(func_info, "source_location", None):
            file_path = _normalize_text(getattr(func_info.source_location, "file_path", ""))
        metadata[method_sig] = {
            "file_path": file_path,
            "source_code": _normalize_text(getattr(func_info, "source_code", "")),
            "is_public": not method_sig.split(".")[-1].startswith("_"),
            "method_name": method_sig.split(".")[-1],
            "is_top_level": True,
        }

    return metadata


def _build_reverse_call_graph(call_graph: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    reverse_call_graph: Dict[str, Set[str]] = {}
    for caller, callees in (call_graph or {}).items():
        for callee in callees:
            reverse_call_graph.setdefault(callee, set()).add(caller)
    return reverse_call_graph


def _collect_other_partition_methods(partitions: Iterable[Dict[str, Any]], current_partition_id: str) -> Set[str]:
    other_methods: Set[str] = set()
    for partition in partitions or []:
        if _normalize_text(partition.get("partition_id")) == current_partition_id:
            continue
        other_methods.update(partition.get("methods", []) or [])
    return other_methods


def _check_framework_hints(file_path: str, source_code: str, method_name: str) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    normalized_path = file_path.replace("\\", "/").lower()
    source_lower = source_code.lower()
    method_lower = method_name.lower()

    score = 0.0
    if any(token in normalized_path for token in ["/api", "/route", "/routes", "/controller", "/handler", "/cli"]):
        score = max(score, 0.7)
        reasons.append("文件路径带有接口/路由提示")
    if any(token in source_lower for token in ["@app.route", "@bp.route", "@router.", "@api", "@click.command", "@app.get", "@app.post"]):
        score = max(score, 1.0)
        reasons.append("源码含框架装饰器提示")
    if any(token in method_lower for token in ["handle", "handler", "route", "endpoint", "command"]):
        score = max(score, 0.5)
        reasons.append("方法名具有框架入口语义")

    return score, reasons


def _score_candidate(
    method_sig: str,
    call_graph: Dict[str, Set[str]],
    reverse_call_graph: Dict[str, Set[str]],
    partition_methods: Set[str],
    other_partition_methods: Set[str],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    method_name = _normalize_text(metadata.get("method_name") or method_sig.split(".")[-1])
    file_path = _normalize_text(metadata.get("file_path"))
    source_code = _normalize_text(metadata.get("source_code"))

    if _is_test_file(file_path, method_name):
        return {
            "method_signature": method_sig,
            "file_path": file_path,
            "score": 0.0,
            "reasons": ["测试文件或测试方法，稳定排除"],
            "components": {
                "call_ratio": 0.0,
                "naming_pattern": 0.0,
                "public_export": 0.0,
                "framework_hint": 0.0,
                "external_call": 0.0,
            },
            "excluded": True,
            "excluded_reason": "test-filter",
        }

    out_degree = len([callee for callee in call_graph.get(method_sig, set()) if callee in partition_methods])
    in_degree = len([caller for caller in reverse_call_graph.get(method_sig, set()) if caller in partition_methods])
    external_callers = [caller for caller in reverse_call_graph.get(method_sig, set()) if caller in other_partition_methods]

    total_degree = out_degree + in_degree
    call_ratio_score = out_degree / total_degree if total_degree > 0 else (1.0 if out_degree > 0 else 0.2)
    if out_degree > 0 and in_degree == 0:
        call_ratio_score = 1.0

    naming_score = 0.1
    naming_reasons: List[str] = []
    method_lower = method_name.lower()
    if method_lower in {"main", "run", "start", "execute", "entry", "entry_point"}:
        naming_score = 1.0
        naming_reasons.append("方法名是强入口模式")
    elif any(token in method_lower for token in ["api", "handle", "handler", "route", "command", "service"]):
        naming_score = 0.7
        naming_reasons.append("方法名带入口模式线索")
    elif not method_lower.startswith("_"):
        naming_score = 0.4
        naming_reasons.append("方法名公开可见")

    public_export_score = 0.2
    public_reasons: List[str] = []
    if metadata.get("is_top_level"):
        public_export_score = 1.0
        public_reasons.append("顶层函数，天然更像外部入口")
    elif metadata.get("is_public"):
        public_export_score = 0.7
        public_reasons.append("公开方法，暴露概率更高")

    framework_score, framework_reasons = _check_framework_hints(file_path, source_code, method_name)

    external_score = min(1.0, len(external_callers) / 3.0) if external_callers else 0.0
    external_reasons = [f"被其他分区调用 {len(external_callers)} 次"] if external_callers else []

    score = (
        call_ratio_score * 0.30
        + naming_score * 0.20
        + public_export_score * 0.20
        + framework_score * 0.20
        + external_score * 0.10
    )

    reasons: List[str] = []
    if call_ratio_score >= 0.7:
        reasons.append(f"调用比偏向起点（出度 {out_degree} / 入度 {in_degree}）")
    reasons.extend(naming_reasons)
    reasons.extend(public_reasons)
    reasons.extend(framework_reasons)
    reasons.extend(external_reasons)

    if not reasons:
        reasons.append("满足基础入口特征")

    return {
        "method_signature": method_sig,
        "file_path": file_path,
        "score": round(min(score, 1.0), 4),
        "reasons": reasons,
        "components": {
            "call_ratio": round(call_ratio_score, 4),
            "naming_pattern": round(naming_score, 4),
            "public_export": round(public_export_score, 4),
            "framework_hint": round(framework_score, 4),
            "external_call": round(external_score, 4),
        },
        "excluded": False,
        "excluded_reason": None,
    }


def _summarize_partition(candidates: List[Dict[str, Any]], threshold: float) -> Dict[str, Any]:
    effective_count = len([item for item in candidates if (not item.get("excluded")) and item.get("score", 0.0) >= threshold])
    excluded_test_count = len([item for item in candidates if item.get("excluded_reason") == "test-filter"])
    return {
        "candidate_count": len(candidates),
        "effective_count": effective_count,
        "excluded_test_count": excluded_test_count,
        "threshold": threshold,
    }


def build_entry_points_shadow(
    partitions: Iterable[Dict[str, Any]],
    call_graph: Dict[str, Set[str]],
    analyzer_report: Any,
    threshold: float = 0.45,
) -> Dict[str, Any]:
    metadata_map = _extract_method_metadata(analyzer_report)
    reverse_call_graph = _build_reverse_call_graph(call_graph)
    shadow_partitions: Dict[str, Dict[str, Any]] = {}
    total_effective = 0
    total_excluded_test = 0

    partitions_list = list(partitions or [])
    for partition in partitions_list:
        partition_id = _normalize_text(partition.get("partition_id") or "unknown")
        partition_methods = set(partition.get("methods", []) or [])
        other_partition_methods = _collect_other_partition_methods(partitions_list, partition_id)

        candidates: List[Dict[str, Any]] = []
        for method_sig in sorted(partition_methods):
            metadata = metadata_map.get(method_sig, {
                "file_path": "",
                "source_code": "",
                "is_public": not method_sig.split(".")[-1].startswith("_"),
                "method_name": method_sig.split(".")[-1],
                "is_top_level": "." not in method_sig,
            })
            candidates.append(
                _score_candidate(
                    method_sig=method_sig,
                    call_graph=call_graph,
                    reverse_call_graph=reverse_call_graph,
                    partition_methods=partition_methods,
                    other_partition_methods=other_partition_methods,
                    metadata=metadata,
                )
            )

        candidates.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        effective_entries = [
            item for item in candidates
            if (not item.get("excluded")) and item.get("score", 0.0) >= threshold
        ]
        summary = _summarize_partition(candidates, threshold)
        total_effective += summary["effective_count"]
        total_excluded_test += summary["excluded_test_count"]
        shadow_partitions[partition_id] = {
            "all_candidates": candidates,
            "effective_entries": effective_entries,
            "summary": summary,
        }

    return {
        "version": "phase4-shadow-v1",
        "config": {
            "threshold": threshold,
            "weights": {
                "call_ratio": 0.30,
                "naming_pattern": 0.20,
                "public_export": 0.20,
                "framework_hint": 0.20,
                "external_call": 0.10,
            },
            "test_filter_mode": "strict",
        },
        "partitions": shadow_partitions,
        "summary": {
            "partition_count": len(shadow_partitions),
            "effective_entry_count": total_effective,
            "excluded_test_count": total_excluded_test,
        },
    }


def filter_entry_points_shadow(shadow_payload: Dict[str, Any], threshold_override: Optional[float]) -> Dict[str, Any]:
    if threshold_override is None:
        return shadow_payload

    filtered = copy.deepcopy(shadow_payload)
    filtered.setdefault("config", {})["threshold"] = threshold_override
    total_effective = 0
    total_excluded_test = 0

    for partition_id, partition_payload in (filtered.get("partitions") or {}).items():
        candidates = partition_payload.get("all_candidates", []) or []
        effective_entries = [
            item for item in candidates
            if (not item.get("excluded")) and item.get("score", 0.0) >= threshold_override
        ]
        summary = _summarize_partition(candidates, threshold_override)
        partition_payload["effective_entries"] = effective_entries
        partition_payload["summary"] = summary
        total_effective += summary["effective_count"]
        total_excluded_test += summary["excluded_test_count"]

    filtered["summary"] = {
        "partition_count": len(filtered.get("partitions") or {}),
        "effective_entry_count": total_effective,
        "excluded_test_count": total_excluded_test,
    }
    return filtered
