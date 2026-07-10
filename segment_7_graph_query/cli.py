#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from graph_query.basic import find_callees, find_callers, get_node_info, list_relations  # noqa: E402
from graph_query.common import normalize_path, validate_graph_db  # noqa: E402
from graph_query.hub_query import find_hubs, get_architecture, get_partition_topology  # noqa: E402
from graph_query.impact import detect_unused_functions, impact_analysis  # noqa: E402
from graph_query.path_query import find_paths_between, get_path_detail, is_on_same_path  # noqa: E402


QUERY_NAMES = {
    "detect_unused_functions",
    "find_callees",
    "find_callers",
    "find_hubs",
    "find_paths_between",
    "get_architecture",
    "get_node_info",
    "get_partition_topology",
    "get_path_detail",
    "impact_analysis",
    "is_on_same_path",
    "list_relations",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 7 graph query: read-only graph.db -> segment7_query_result.json")
    parser.add_argument("--graph-db", "--input", dest="graph_db", required=True, help="Path to stage6 graph.db")
    parser.add_argument("--query", choices=sorted(QUERY_NAMES), default=None, help="Single query name")
    parser.add_argument("--batch", default=None, help="JSON file containing a list of query objects or {'queries': [...]}.")
    parser.add_argument("--output", required=True, help="Path to segment7_query_result.json")
    parser.add_argument("--audit-log", default=None, help="Path to logs/graph_query_audit.jsonl")
    parser.add_argument("--method", default=None, help="Method qualified name")
    parser.add_argument("--src", default=None, help="Source method qualified name")
    parser.add_argument("--dst", default=None, help="Destination method qualified name")
    parser.add_argument("--path-id", default=None, help="Path id for get_path_detail")
    parser.add_argument("--depth", type=int, default=1, help="Traversal depth")
    parser.add_argument("--top-k", type=int, default=10, help="Hub count")
    parser.add_argument("--max-depth", type=int, default=8, help="Maximum path depth")
    parser.add_argument("--verbose", action="store_true", help="Print extra progress logs")
    return parser


def _load_batch(batch_path: str) -> List[Dict[str, Any]]:
    payload = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("queries"), list):
        return [dict(item) for item in payload["queries"] if isinstance(item, dict)]
    raise ValueError("batch JSON must be a list or an object with queries[]")


def _single_query_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "query": args.query,
        "method": args.method,
        "src": args.src,
        "dst": args.dst,
        "path_id": args.path_id,
        "depth": args.depth,
        "top_k": args.top_k,
        "max_depth": args.max_depth,
    }


def _auto_pair(graph_db_path: str) -> Dict[str, str]:
    from graph_query.common import connect_readonly, parse_json, select_all

    try:
        with connect_readonly(graph_db_path) as connection:
            rows = select_all(connection, "SELECT path_id, function_chain_json FROM paths ORDER BY path_id")
    except Exception:
        return {"src": "", "dst": "", "path_id": ""}
    for row in rows:
        chain = [str(item) for item in (parse_json(row.get("function_chain_json"), []) or [])]
        if len(chain) >= 2:
            return {"src": chain[0], "dst": chain[-1], "path_id": str(row.get("path_id") or "")}
    return {"src": "", "dst": "", "path_id": ""}


def _default_queries(graph_db_path: str) -> List[Dict[str, Any]]:
    pair = _auto_pair(graph_db_path)
    method = pair.get("src") or ""
    dst = pair.get("dst") or ""
    return [
        {"query": "list_relations"},
        {"query": "get_partition_topology"},
        {"query": "get_architecture", "top_k": 5},
        {"query": "find_hubs", "top_k": 5},
        {"query": "find_paths_between", "src": method, "dst": dst, "max_depth": 8},
        {"query": "find_callers", "method": dst, "depth": 2},
        {"query": "find_callees", "method": method, "depth": 2},
        {"query": "impact_analysis", "method": dst, "max_depth": 3},
    ]


def _query_input(query: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in sorted(query.items()) if key != "query" and value is not None}


def _dispatch(graph_db_path: str, query: Dict[str, Any]) -> Any:
    name = str(query.get("query") or "")
    if name == "list_relations":
        return list_relations(graph_db_path)
    if name == "find_callers":
        return find_callers(graph_db_path, str(query.get("method") or ""), int(query.get("depth") or 1))
    if name == "find_callees":
        return find_callees(graph_db_path, str(query.get("method") or ""), int(query.get("depth") or 1))
    if name == "get_node_info":
        return get_node_info(graph_db_path, str(query.get("method") or ""))
    if name == "find_paths_between":
        return find_paths_between(
            graph_db_path,
            str(query.get("src") or ""),
            str(query.get("dst") or ""),
            int(query.get("max_depth") or 8),
        )
    if name == "is_on_same_path":
        return is_on_same_path(graph_db_path, str(query.get("src") or ""), str(query.get("dst") or ""))
    if name == "get_path_detail":
        return get_path_detail(graph_db_path, str(query.get("path_id") or ""))
    if name == "find_hubs":
        return find_hubs(graph_db_path, int(query.get("top_k") or 10))
    if name == "get_partition_topology":
        return get_partition_topology(graph_db_path)
    if name == "get_architecture":
        return get_architecture(graph_db_path, top_k=int(query.get("top_k") or 5))
    if name == "impact_analysis":
        return impact_analysis(
            graph_db_path,
            str(query.get("method") or ""),
            int(query.get("max_depth") or query.get("depth") or 3),
        )
    if name == "detect_unused_functions":
        return detect_unused_functions(graph_db_path)
    raise ValueError(f"unknown query: {name}")


def _result_summary(result: Any) -> Dict[str, Any]:
    if isinstance(result, list):
        return {"type": "list", "count": len(result)}
    if isinstance(result, dict):
        summary = {"type": "dict", "keys": sorted(result.keys())[:12]}
        for key in ("partition_count", "path_count", "relation_count", "community_summary_count"):
            if key in result:
                summary[key] = result[key]
        if "summary" in result and isinstance(result["summary"], dict):
            summary["nested_summary"] = result["summary"]
        return summary
    return {"type": type(result).__name__}


def _query_tables(query_name: str) -> List[str]:
    mapping = {
        "list_relations": ["graph_relations"],
        "find_callers": ["path_links", "path_reverse_index"],
        "find_callees": ["path_links"],
        "get_node_info": ["graph_relations", "partition_assignments", "path_reverse_index"],
        "find_paths_between": ["paths", "path_links", "path_cfg", "path_dfg"],
        "is_on_same_path": ["paths", "path_links", "path_cfg", "path_dfg"],
        "get_path_detail": ["paths", "path_links", "path_cfg", "path_dfg"],
        "find_hubs": ["paths", "path_links", "graph_relations", "partition_topology"],
        "get_partition_topology": ["partition_topology"],
        "get_architecture": ["partitions", "paths", "graph_relations", "community_summaries"],
        "impact_analysis": ["path_reverse_index", "path_links", "paths", "graph_relations", "partition_topology"],
        "detect_unused_functions": ["graph_relations", "path_reverse_index", "path_links"],
    }
    return mapping.get(query_name, [])


def _missing_query_tables(query_name: str, validation: Dict[str, Any]) -> List[str]:
    missing = set(str(item) for item in validation.get("missing_tables", []) or [])
    return sorted(table for table in _query_tables(query_name) if table in missing)


def _stable_run_id(graph_db_path: str, queries: List[Dict[str, Any]]) -> str:
    token = json.dumps({"graph_db_path": normalize_path(graph_db_path), "queries": queries}, ensure_ascii=False, sort_keys=True)
    return "stage7_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _append_audit(audit_log_path: Path, row: Dict[str, Any]) -> None:
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _execute_one(
    graph_db_path: str,
    query: Dict[str, Any],
    validation: Dict[str, Any],
    audit_log_path: Path,
    run_id: str,
) -> Dict[str, Any]:
    name = str(query.get("query") or "")
    started_at = time.perf_counter()
    result: Any = None
    status = "completed"
    error: Optional[str] = None
    missing_query_tables = _missing_query_tables(name, validation)
    if validation.get("table_counts") == {} and validation.get("status") == "partial":
        status = "partial"
        result = {"errors": validation.get("errors", []), "missing_tables": validation.get("missing_tables", [])}
    elif missing_query_tables:
        status = "partial"
        result = {"errors": [f"missing table: {table}" for table in missing_query_tables], "missing_tables": missing_query_tables}
    else:
        try:
            result = _dispatch(graph_db_path, query)
        except Exception as exc:
            status = "partial"
            error = str(exc)
            result = {"errors": [str(exc)]}
    measured_ms = int((time.perf_counter() - started_at) * 1000)
    summary = _result_summary(result)
    audit_row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "query": name,
        "input": _query_input(query),
        "result": result,
        "result_summary": summary,
        "duration_ms": measured_ms,
        "run_id": run_id,
        "status": status,
        "error": error,
    }
    _append_audit(audit_log_path, audit_row)
    return {
        "query_name": name,
        "input": _query_input(query),
        "result": result,
        "duration_ms": 0,
        "status": status,
        "error": error,
        "sql_plan": {
            "read_only": True,
            "tables_checked": sorted(validation.get("table_counts", {}).keys()),
            "missing_tables": missing_query_tables,
            "query_tables": _query_tables(name),
        },
    }


def _relation_count_from_query_results(queries: List[Dict[str, Any]]) -> int:
    for query in queries:
        if query.get("query_name") == "list_relations" and isinstance(query.get("result"), list):
            return len(query["result"])
    for query in queries:
        result = query.get("result")
        if query.get("query_name") == "get_architecture" and isinstance(result, dict):
            return int(result.get("relation_count") or 0)
    return 0


def run_stage7(
    graph_db_path: str,
    output_path: str,
    *,
    query: Optional[Dict[str, Any]] = None,
    batch_path: Optional[str] = None,
    audit_log_path: Optional[str] = None,
    verbose: bool = False,
) -> Path:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    audit_file = Path(audit_log_path) if audit_log_path else output_file.parent / "logs" / "graph_query_audit.jsonl"
    if batch_path:
        queries = _load_batch(batch_path)
    elif query and query.get("query"):
        queries = [query]
    else:
        queries = _default_queries(graph_db_path)
    validation = validate_graph_db(graph_db_path)
    run_id = _stable_run_id(graph_db_path, queries)
    query_results = [_execute_one(graph_db_path, item, validation, audit_file, run_id) for item in queries]
    passed = [item for item in query_results if item.get("status") == "completed"]
    durations = [(item.get("query_name"), int(item.get("duration_ms") or 0)) for item in query_results]
    slowest = max(durations, key=lambda item: (item[1], item[0])) if durations else [None, 0]
    fastest = min(durations, key=lambda item: (item[1], item[0])) if durations else [None, 0]
    payload = {
        "schema_version": "stage7.v1",
        "input": {"graph_db_path": normalize_path(graph_db_path)},
        "queries": query_results,
        "audit_log_path": normalize_path(audit_file),
        "graph_relations_used": _relation_count_from_query_results(query_results),
        "summary": {
            "queries_total": len(query_results),
            "queries_passed": len(passed),
            "status": "completed" if len(passed) == len(query_results) else "partial",
            "total_duration_ms": 0,
            "slowest_query": {"query_name": slowest[0], "duration_ms": slowest[1]},
            "fastest_query": {"query_name": fastest[0], "duration_ms": fastest[1]},
            "llm_status": "skipped_no_llm_required",
            "validation_status": validation.get("status"),
            "errors": validation.get("errors", []),
        },
    }
    output_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    if verbose:
        print("[segment_7_graph_query] output:", output_file)
        print("[segment_7_graph_query] audit:", audit_file)
        print("[segment_7_graph_query] status:", payload["summary"]["status"])
    return output_file


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        run_stage7(
            graph_db_path=args.graph_db,
            output_path=args.output,
            query=_single_query_from_args(args),
            batch_path=args.batch,
            audit_log_path=args.audit_log,
            verbose=bool(args.verbose),
        )
        return 0
    except Exception as exc:
        print(f"[segment_7_graph_query] ERROR: {exc}", file=sys.stderr)
        return 1
