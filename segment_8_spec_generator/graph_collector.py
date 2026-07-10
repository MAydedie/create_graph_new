#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from graph_query.basic import get_node_info, list_relations
from graph_query.common import connect_readonly, normalize_path, parse_json, select_all, validate_graph_db
from graph_query.hub_query import find_hubs, get_architecture, get_partition_topology
from graph_query.impact import impact_analysis
from graph_query.path_query import find_paths_between, get_path_detail


GRAPH_SECTION_MAP: Dict[str, List[str]] = {
    "overview": ["get_architecture", "find_hubs"],
    "partition_architecture": ["get_partition_topology", "get_architecture"],
    "core_call_chains": ["find_paths_between", "get_path_detail"],
    "module_list": ["get_node_info", "find_hubs", "list_relations"],
    "api_routes": ["impact_analysis", "get_node_info"],
}


def load_segment6_payload(segment6_json_path: str) -> Tuple[Dict[str, Any], List[str]]:
    path = Path(segment6_json_path)
    if not path.exists():
        return {}, [f"segment6_output.json does not exist: {path}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, [f"cannot read segment6_output.json: {exc}"]
    if not isinstance(payload, dict):
        return {}, ["segment6_output.json top-level value must be an object"]
    return payload, []


def _execute_query(graph_db_path: str, query_name: str, query_input: Dict[str, Any], func: Any) -> Dict[str, Any]:
    status = "completed"
    error: Optional[str] = None
    result: Any = None
    try:
        result = func()
    except Exception as exc:
        status = "partial"
        error = str(exc)
        result = {"errors": [str(exc)]}
    return {
        "query_name": query_name,
        "input": {key: value for key, value in sorted(query_input.items()) if value is not None},
        "result": result,
        "raw_result": result,
        "duration_ms": 0,
        "status": status,
        "error": error,
        "sql_plan": {"read_only": True, "graph_db_path": normalize_path(graph_db_path)},
    }


def _query_result(raw_results: Dict[str, Any], name: str) -> Any:
    for item in raw_results.get("queries", []):
        if item.get("query_name") == name and item.get("status") == "completed":
            return item.get("result")
    return None


def _path_rows(graph_db_path: str) -> List[Dict[str, Any]]:
    with connect_readonly(graph_db_path) as connection:
        rows = select_all(connection, "SELECT path_id, partition_id, function_chain_json FROM paths ORDER BY path_id")
    for row in rows:
        row["function_chain"] = [str(item) for item in (parse_json(row.get("function_chain_json"), []) or [])]
    return rows


def _candidate_pairs(graph_db_path: str, max_paths: int) -> List[Dict[str, str]]:
    pairs: List[Dict[str, str]] = []
    seen: Set[Tuple[str, str, str]] = set()
    for row in _path_rows(graph_db_path):
        chain = row.get("function_chain") or []
        if len(chain) < 2:
            continue
        src = str(chain[0])
        dst = str(chain[-1])
        path_id = str(row.get("path_id") or "")
        key = (src, dst, path_id)
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"src": src, "dst": dst, "path_id": path_id})
        if len(pairs) >= max(1, max_paths):
            break
    return pairs


def _first_methods(relations: Iterable[Dict[str, Any]], limit: int) -> List[str]:
    methods: List[str] = []
    for relation in relations:
        method = str(relation.get("method_qn") or "").strip()
        if method and method not in methods:
            methods.append(method)
        if len(methods) >= limit:
            break
    return methods


def collect_graph_context(graph_db_path: str, *, top_k: int = 5, max_paths: int = 3, batch_path: str | None = None) -> Dict[str, Any]:
    validation = validate_graph_db(graph_db_path)
    raw_results: Dict[str, Any] = {
        "schema_version": "stage8.raw_graph_query_results.v1",
        "input": {"graph_db_path": normalize_path(graph_db_path), "top_k": int(top_k), "max_paths": int(max_paths), "batch_path": batch_path},
        "validation": validation,
        "queries": [],
        "errors": list(validation.get("errors") or []),
        "core_path_requirement": {"requested": int(max_paths), "available_candidate_pairs": 0, "collected": 0},
    }
    if validation.get("table_counts") == {} and validation.get("status") == "partial":
        return {"raw_results": raw_results, "core_paths": [], "graph_queries_used": [], "graph_section_map": GRAPH_SECTION_MAP}

    queries = raw_results["queries"]
    queries.append(_execute_query(graph_db_path, "get_architecture", {"top_k": top_k}, lambda: get_architecture(graph_db_path, top_k=top_k)))
    queries.append(_execute_query(graph_db_path, "get_partition_topology", {}, lambda: get_partition_topology(graph_db_path)))
    queries.append(_execute_query(graph_db_path, "find_hubs", {"top_k": top_k}, lambda: find_hubs(graph_db_path, top_k=top_k)))
    queries.append(_execute_query(graph_db_path, "list_relations", {}, lambda: list_relations(graph_db_path)))

    relations = _query_result(raw_results, "list_relations") or []
    for method in _first_methods(relations, max(3, int(top_k))):
        queries.append(_execute_query(graph_db_path, "get_node_info", {"method": method}, lambda method=method: get_node_info(graph_db_path, method)))
    for method in _first_methods(relations, 3):
        queries.append(_execute_query(graph_db_path, "impact_analysis", {"method": method, "max_depth": 3}, lambda method=method: impact_analysis(graph_db_path, method, max_depth=3)))

    candidate_pairs = _candidate_pairs(graph_db_path, max_paths=max_paths)
    raw_results["core_path_requirement"] = {
        "requested": int(max_paths),
        "available_candidate_pairs": len(candidate_pairs),
        "collected": 0,
    }
    core_paths: List[Dict[str, Any]] = []
    for pair in candidate_pairs:
        query_item = _execute_query(
            graph_db_path,
            "find_paths_between",
            {"src": pair["src"], "dst": pair["dst"], "max_depth": 8},
            lambda pair=pair: find_paths_between(graph_db_path, pair["src"], pair["dst"], max_depth=8),
        )
        queries.append(query_item)
        result_items = query_item.get("result")
        for path in (result_items if isinstance(result_items, list) else []):
            path_id = str(path.get("path_id") or "")
            if path_id.startswith("synthetic:"):
                continue
            if path_id == pair["path_id"]:
                core_paths.append(path)
                queries.append(_execute_query(graph_db_path, "get_path_detail", {"path_id": path_id}, lambda path_id=path_id: get_path_detail(graph_db_path, path_id)))
                break
        if len(core_paths) >= max_paths:
            break

    raw_results["core_path_requirement"]["collected"] = len(core_paths)
    for item in queries:
        if item.get("status") != "completed":
            raw_results["errors"].append(
                f"graph query {item.get('query_name') or 'unknown'} failed: {item.get('error') or item.get('result')}"
            )
    required_paths = min(int(max_paths), len(candidate_pairs))
    if required_paths and len(core_paths) < required_paths:
        raw_results["errors"].append(f"core_call_chains collected {len(core_paths)} of {required_paths} required persisted paths")

    graph_queries_used = sorted({str(item.get("query_name") or "") for item in queries if item.get("query_name")})
    return {
        "raw_results": raw_results,
        "core_paths": core_paths,
        "graph_queries_used": graph_queries_used,
        "graph_section_map": GRAPH_SECTION_MAP,
    }


def persisted_path_ids(graph_db_path: str) -> Set[str]:
    try:
        with connect_readonly(graph_db_path) as connection:
            return {str(row.get("path_id") or "") for row in select_all(connection, "SELECT path_id FROM paths ORDER BY path_id")}
    except Exception:
        return set()


def graph_claim_methods(graph_db_path: str) -> Set[str]:
    methods: Set[str] = set()
    try:
        with connect_readonly(graph_db_path) as connection:
            for row in select_all(connection, "SELECT method_qn FROM graph_relations ORDER BY method_qn"):
                methods.add(str(row.get("method_qn") or ""))
            for row in select_all(connection, "SELECT function_chain_json FROM paths ORDER BY path_id"):
                for item in parse_json(row.get("function_chain_json"), []) or []:
                    methods.add(str(item))
            for row in select_all(connection, "SELECT caller, callee FROM path_links ORDER BY caller, callee"):
                methods.add(str(row.get("caller") or ""))
                methods.add(str(row.get("callee") or ""))
    except Exception:
        pass
    return {item for item in methods if item}
