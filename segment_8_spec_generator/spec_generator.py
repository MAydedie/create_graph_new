#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from app.services import experience_library_service as exp_service
from graph_query.common import normalize_path, parse_json

from .audit import append_audit_row, build_audit_row
from .graph_collector import collect_graph_context, graph_claim_methods, load_segment6_payload, persisted_path_ids
from .llm_renderer import maybe_enrich_sections
from .template_loader import SECTION_TITLES, load_template, render_template


def _stable_run_id(
    graph_db_path: str,
    segment6_json_path: str,
    project_path: str,
    user_intent: str,
    skip_llm: bool,
    top_k: int,
    max_paths: int,
    template_path: str | None,
    batch_path: str | None,
) -> str:
    token = json.dumps(
        {
            "graph_db_path": normalize_path(graph_db_path),
            "segment6_json_path": normalize_path(segment6_json_path),
            "project_path": normalize_path(project_path) if project_path else "",
            "user_intent": user_intent,
            "skip_llm": bool(skip_llm),
            "top_k": int(top_k),
            "max_paths": int(max_paths),
            "template_path": normalize_path(template_path) if template_path else "",
            "batch_path": normalize_path(batch_path) if batch_path else "",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return "stage8_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _stable_timestamp(run_id: str) -> str:
    return f"2026-01-01T00:00:00Z#{run_id}"


def _json_write(path: str | Path, payload: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _list_lines(items: Iterable[str], empty: str) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return f"- {empty}"
    return "\n".join(f"- {item}" for item in values)


def _load_architecture_digest(project_path: str) -> Dict[str, Any]:
    try:
        return exp_service.generate_architecture_digest(project_path)
    except Exception:
        return {}


def _project_name(segment6_payload: Dict[str, Any], project_path: str) -> str:
    project = segment6_payload.get("project") if isinstance(segment6_payload, dict) else {}
    name = str((project or {}).get("name") or "").strip()
    if name:
        return name
    return Path(project_path).name if project_path else "unknown_project"


def _community_status(segment6_payload: Dict[str, Any]) -> str:
    summaries = segment6_payload.get("community_summaries") if isinstance(segment6_payload, dict) else []
    if summaries and all(str(item.get("status") or item.get("summary_status") or "skipped") == "skipped" for item in summaries if isinstance(item, dict)):
        return "skipped_placeholder"
    semantics = segment6_payload.get("community_semantics") if isinstance(segment6_payload, dict) else {}
    if (semantics or {}).get("effective_summary_source") == "placeholder":
        return "skipped_placeholder"
    return "available" if summaries else "missing"


def _experience_stats(segment6_payload: Dict[str, Any], architecture_digest: Dict[str, Any]) -> Dict[str, Any]:
    raw_summary = segment6_payload.get("summary") if isinstance(segment6_payload, dict) else {}
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    stats = dict(architecture_digest.get("experience_library_stats") or {})
    stats.update(
        {
            "partitions": int(summary.get("partition_count") or len(segment6_payload.get("partition_analyses") or {})),
            "paths": int(summary.get("path_count") or len(segment6_payload.get("path_analyses") or [])),
            "relations": int(summary.get("graph_relation_count") or len(segment6_payload.get("graph_relations") or [])),
            "community_summaries": f"{len(segment6_payload.get('community_summaries') or [])}_{_community_status(segment6_payload).replace('_placeholder', '')}",
            "community_summary_status": _community_status(segment6_payload),
        }
    )
    return stats


def _format_core_paths(core_paths: List[Dict[str, Any]]) -> str:
    if not core_paths:
        return "- skipped_query: 未获得可验证的 persisted path，当前说明书保留占位。"
    lines: List[str] = []
    for index, path in enumerate(core_paths, 1):
        chain = path.get("function_chain") or path.get("matched_subchain") or []
        lines.append(f"- 链路 {index}: `{path.get('path_id')}`")
        lines.append(f"  - 分区: {path.get('partition_id') or 'unknown'}")
        lines.append(f"  - 调用链: {' -> '.join(str(item) for item in chain) if chain else 'unknown'}")
        if path.get("path_name"):
            lines.append(f"  - 路径名: {path.get('path_name')}")
    return "\n".join(lines)


def _format_modules(architecture_digest: Dict[str, Any], raw_results: Dict[str, Any]) -> str:
    modules = architecture_digest.get("modules") or []
    lines: List[str] = []
    for module in modules[:12]:
        lines.append(f"- `{module.get('path') or module.get('name')}`: {module.get('file_count', 0)} 个代码文件")
    node_queries = [item for item in raw_results.get("queries", []) if item.get("query_name") == "get_node_info" and item.get("status") == "completed"]
    for item in node_queries[:5]:
        result = item.get("result") or {}
        lines.append(f"- graph node `{result.get('method_qn')}`: partitions={result.get('partitions', [])}, paths={result.get('path_ids', [])}")
    return "\n".join(lines) if lines else "- 未扫描到模块目录；已保留 graph_query 节点信息占位。"


def _format_api_routes(architecture_digest: Dict[str, Any], raw_results: Dict[str, Any]) -> str:
    routes = architecture_digest.get("api_catalog") or []
    lines: List[str] = []
    for group in routes:
        lines.append(f"- `{group.get('source_file')}`: {', '.join(group.get('routes') or [])}")
    impact = [item for item in raw_results.get("queries", []) if item.get("query_name") == "impact_analysis" and item.get("status") == "completed"]
    if impact:
        lines.append("- graph_query impact_analysis 已用于补充入口影响面：")
        for item in impact[:3]:
            result = item.get("result") or {}
            summary = result.get("summary") or {}
            lines.append(f"  - `{result.get('method_qn')}`: affected_paths={summary.get('affected_path_count', 0)}, callers={summary.get('caller_chain_count', 0)}")
    return "\n".join(lines) if lines else "- 未检测到 Flask API 路由；本段保留 graph_query impact_analysis 作为接口影响面证据。"


def _build_sections(
    *,
    project_name: str,
    user_intent: str,
    segment6_payload: Dict[str, Any],
    architecture_digest: Dict[str, Any],
    graph_context: Dict[str, Any],
) -> Dict[str, Any]:
    raw_results = graph_context.get("raw_results") or {}
    architecture = next((item.get("result") for item in raw_results.get("queries", []) if item.get("query_name") == "get_architecture"), {}) or {}
    topology = next((item.get("result") for item in raw_results.get("queries", []) if item.get("query_name") == "get_partition_topology"), []) or []
    hubs = next((item.get("result") for item in raw_results.get("queries", []) if item.get("query_name") == "find_hubs"), []) or []
    stats = _experience_stats(segment6_payload, architecture_digest)
    overview = "\n".join(
        [
            f"- 用户意图: {user_intent}",
            f"- 项目: {project_name}",
            f"- 技术栈: {', '.join(architecture_digest.get('overview', {}).get('tech_stack') or architecture_digest.get('overview', {}).get('frameworks') or []) or '未检测到'}",
            f"- 图谱规模: partitions={architecture.get('partition_count', 0)}, paths={architecture.get('path_count', 0)}, relations={architecture.get('relation_count', 0)}, community_summaries={architecture.get('community_summary_count', 0)}",
            f"- 社区摘要状态: {_community_status(segment6_payload)}",
        ]
    )
    partition_lines = [f"- partition_topology edges: {len(topology)}"]
    for edge in topology[:12]:
        partition_lines.append(f"- {edge.get('source_partition')} -> {edge.get('target_partition')}: edge_count={edge.get('edge_count')}")
    if hubs:
        partition_lines.append("- 关键 hub:")
        for hub in hubs[:5]:
            partition_lines.append(f"  - `{hub.get('method_qn')}` pagerank={hub.get('pagerank')} indegree={hub.get('indegree')} outdegree={hub.get('outdegree')}")
    patterns = architecture_digest.get("design_patterns") or []
    readme = architecture_digest.get("readme_summary") or "README 未提供或读取失败。"
    return {
        "overview": overview,
        "partition_architecture": "\n".join(partition_lines),
        "core_call_chains": _format_core_paths(graph_context.get("core_paths") or []),
        "module_list": _format_modules(architecture_digest, raw_results),
        "design_patterns": _list_lines([f"{item.get('name')}: {item.get('description')} (证据: {item.get('evidence')})" for item in patterns], "未检测到明确设计模式；保留规则式占位。"),
        "api_routes": _format_api_routes(architecture_digest, raw_results),
        "readme_summary": readme,
        "experience_stats": "\n".join(f"- {key}: {value}" for key, value in sorted(stats.items())),
    }


def _assert_non_hallucination(graph_db_path: str, core_paths: List[Dict[str, Any]], sections: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    real_paths = persisted_path_ids(graph_db_path)
    for path in core_paths:
        path_id = str(path.get("path_id") or "")
        if path_id not in real_paths:
            errors.append(f"unverified path_id: {path_id}")
    known_methods = graph_claim_methods(graph_db_path)
    method_pattern = re.compile(r"`([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+)`")
    for section_name, value in sections.items():
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        for method in method_pattern.findall(text):
            if method in SECTION_TITLES.values():
                continue
            if method not in known_methods and "/" not in method:
                errors.append(f"unverified method_qn in {section_name}: {method}")
    return sorted(set(errors))


def generate_spec(
    *,
    graph_db_path: str,
    segment6_json_path: str,
    project_path: str,
    user_intent: str = "项目说明书",
    template_path: str | None = None,
    top_k: int = 5,
    max_paths: int = 3,
    skip_llm: bool = False,
    batch_path: str | None = None,
) -> Tuple[Dict[str, Any], str, Dict[str, Any], str, str | None]:
    segment6_payload, segment6_errors = load_segment6_payload(segment6_json_path)
    project_name = _project_name(segment6_payload, project_path)
    graph_context = collect_graph_context(graph_db_path, top_k=top_k, max_paths=max_paths, batch_path=batch_path)
    architecture_digest = _load_architecture_digest(project_path) if project_path else {}
    sections = _build_sections(
        project_name=project_name,
        user_intent=user_intent,
        segment6_payload=segment6_payload,
        architecture_digest=architecture_digest,
        graph_context=graph_context,
    )
    sections, llm_status, llm_error = maybe_enrich_sections(sections, graph_context, skip_llm=skip_llm)
    template, template_used = load_template(template_path)
    markdown = render_template(template, project_name, {key: str(value) for key, value in sections.items()})
    unverified_claims = _assert_non_hallucination(graph_db_path, graph_context.get("core_paths") or [], sections)
    errors = list(segment6_errors) + list((graph_context.get("raw_results") or {}).get("errors") or [])
    if unverified_claims:
        errors.extend(unverified_claims)
    status = "completed"
    if errors or not Path(graph_db_path).exists() or not segment6_payload:
        status = "partial"
    run_id = _stable_run_id(graph_db_path, segment6_json_path, project_path, user_intent, skip_llm, top_k, max_paths, template_path, batch_path)
    spec = {
        "version": "2.0",
        "schema_version": "2.0",
        "project_name": project_name,
        "generated_at": _stable_timestamp(run_id),
        "graph_queries_used": graph_context.get("graph_queries_used") or [],
        "graph_section_map": graph_context.get("graph_section_map") or {},
        "user_intent": user_intent,
        "status": status,
        "llm_status": llm_status,
        "template_used": template_used,
        "sections": sections,
        "raw_graph_query_results": graph_context.get("raw_results") or {},
        "core_call_chain_evidence": graph_context.get("core_paths") or [],
        "unverified_claims": unverified_claims,
        "errors": errors,
    }
    return spec, markdown, graph_context.get("raw_results") or {}, template_used, llm_error


def run_stage8(
    *,
    graph_db_path: str,
    segment6_json_path: str,
    project_path: str,
    output_path: str,
    spec_json_path: str | None = None,
    raw_results_path: str | None = None,
    audit_log_path: str | None = None,
    template_path: str | None = None,
    user_intent: str = "项目说明书",
    top_k: int = 5,
    max_paths: int = 3,
    skip_llm: bool = False,
    batch_path: str | None = None,
    verbose: bool = False,
) -> Path:
    started_at = time.perf_counter()
    output_file = Path(output_path)
    spec_json_file = Path(spec_json_path) if spec_json_path else output_file.with_suffix(".json")
    raw_file = Path(raw_results_path) if raw_results_path else output_file.parent / "raw_graph_query_results.json"
    audit_file = Path(audit_log_path) if audit_log_path else output_file.parent / "logs" / "spec_generator_audit.jsonl"
    run_id = _stable_run_id(graph_db_path, segment6_json_path, project_path, user_intent, skip_llm, top_k, max_paths, template_path, batch_path)
    spec, markdown, raw_results, template_used, llm_error = generate_spec(
        graph_db_path=graph_db_path,
        segment6_json_path=segment6_json_path,
        project_path=project_path,
        user_intent=user_intent,
        template_path=template_path,
        top_k=top_k,
        max_paths=max_paths,
        skip_llm=skip_llm,
        batch_path=batch_path,
    )
    duration_ms = 0 if skip_llm else int((time.perf_counter() - started_at) * 1000)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(markdown, encoding="utf-8")
    _json_write(spec_json_file, spec)
    raw_payload = {
        **raw_results,
        "graph_queries_used": spec.get("graph_queries_used", []),
        "graph_section_map": spec.get("graph_section_map", {}),
    }
    _json_write(raw_file, raw_payload)
    audit_row = build_audit_row(
        ts=datetime.now(timezone.utc).isoformat(),
        run_id=run_id,
        graph_db_path=normalize_path(graph_db_path),
        segment6_json_path=normalize_path(segment6_json_path),
        project_path=normalize_path(project_path) if project_path else "",
        user_intent=user_intent,
        template_used=template_used,
        skip_llm=skip_llm,
        status=str(spec.get("status") or "partial"),
        llm_status=str(spec.get("llm_status") or "unknown"),
        sections_filled=sum(1 for value in (spec.get("sections") or {}).values() if value),
        queries_used=len(spec.get("graph_queries_used") or []),
        output_path=normalize_path(output_file),
        spec_json_path=normalize_path(spec_json_file),
        raw_results_path=normalize_path(raw_file),
        duration_ms=duration_ms,
        error="; ".join(spec.get("errors") or []) or llm_error,
    )
    append_audit_row(audit_file, audit_row)
    if verbose:
        print("[segment_8_spec_generator] output:", output_file)
        print("[segment_8_spec_generator] spec_json:", spec_json_file)
        print("[segment_8_spec_generator] raw_results:", raw_file)
        print("[segment_8_spec_generator] audit:", audit_file)
        print("[segment_8_spec_generator] status:", spec.get("status"))
    return output_file
