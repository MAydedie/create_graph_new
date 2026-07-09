#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.config import has_deepseek_config  # noqa: E402

from .basic import find_callees, find_callers, get_node_info, list_relations
from .hub_query import find_hubs, get_architecture, get_partition_topology
from .impact import detect_unused_functions, impact_analysis
from .path_query import find_paths_between, get_path_detail, is_on_same_path


def _object_schema(properties: Dict[str, Any], required: List[str] | None = None) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def as_llm_tool_schemas() -> List[Dict[str, Any]]:
    method_schema = {"type": "string", "description": "Fully qualified method name."}
    depth_schema = {"type": "integer", "minimum": 1, "default": 1, "description": "Maximum traversal depth."}
    max_depth_schema = {"type": "integer", "minimum": 1, "default": 8, "description": "Maximum path search depth."}
    top_k_schema = {"type": "integer", "minimum": 1, "default": 10, "description": "Maximum number of rows to return."}
    tools = [
        (
            "find_callers",
            "Find reverse caller chains for a method.",
            _object_schema({"method": method_schema, "depth": depth_schema}, ["method"]),
        ),
        (
            "find_callees",
            "Find forward callee chains for a method.",
            _object_schema({"method": method_schema, "depth": depth_schema}, ["method"]),
        ),
        (
            "get_node_info",
            "Return symbol, file, partition, and path membership for a method.",
            _object_schema({"method": method_schema}, ["method"]),
        ),
        (
            "find_paths_between",
            "Find persisted or graph-derived paths between two methods.",
            _object_schema({"src": method_schema, "dst": method_schema, "max_depth": max_depth_schema}, ["src", "dst"]),
        ),
        (
            "is_on_same_path",
            "Find paths containing two methods.",
            _object_schema({"src": method_schema, "dst": method_schema}, ["src", "dst"]),
        ),
        (
            "get_path_detail",
            "Return path metadata, links, CFG nodes, and DFG nodes.",
            _object_schema({"path_id": {"type": "string", "description": "Persisted path id."}}, ["path_id"]),
        ),
        (
            "find_hubs",
            "Return hub methods ranked by PageRank and indegree.",
            _object_schema({"top_k": top_k_schema}),
        ),
        (
            "get_partition_topology",
            "Return persisted partition topology edges.",
            _object_schema({}),
        ),
        (
            "get_architecture",
            "Return project-level graph summary.",
            _object_schema({"top_k": top_k_schema}),
        ),
        (
            "impact_analysis",
            "Return reverse impact, affected paths, and partition edges.",
            _object_schema({"method": method_schema, "max_depth": max_depth_schema}, ["method"]),
        ),
        (
            "detect_unused_functions",
            "List relation methods absent from path indexes and path links.",
            _object_schema({}),
        ),
        (
            "list_relations",
            "List stage6 graph_relations rows.",
            _object_schema({}),
        ),
    ]
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
            "llm_enabled": bool(has_deepseek_config()),
        }
        for name, description, parameters in tools
    ]


def execute_graph_query(db_path: str, query_dict: Dict[str, Any]) -> Dict[str, Any]:
    name = str(query_dict.get("query") or query_dict.get("name") or "").strip()
    if name == "find_callers":
        return {"result": find_callers(db_path, str(query_dict.get("method") or ""), int(query_dict.get("depth") or 1))}
    if name == "find_callees":
        return {"result": find_callees(db_path, str(query_dict.get("method") or ""), int(query_dict.get("depth") or 1))}
    if name == "get_node_info":
        return {"result": get_node_info(db_path, str(query_dict.get("method") or ""))}
    if name == "find_paths_between":
        return {
            "result": find_paths_between(
                db_path,
                str(query_dict.get("src") or ""),
                str(query_dict.get("dst") or ""),
                int(query_dict.get("max_depth") or 8),
            )
        }
    if name == "is_on_same_path":
        return {"result": is_on_same_path(db_path, str(query_dict.get("src") or ""), str(query_dict.get("dst") or ""))}
    if name == "get_path_detail":
        return {"result": get_path_detail(db_path, str(query_dict.get("path_id") or ""))}
    if name == "find_hubs":
        return {"result": find_hubs(db_path, int(query_dict.get("top_k") or 10))}
    if name == "get_partition_topology":
        return {"result": get_partition_topology(db_path)}
    if name == "get_architecture":
        return {"result": get_architecture(db_path, int(query_dict.get("top_k") or 5))}
    if name == "impact_analysis":
        return {
            "result": impact_analysis(
                db_path,
                str(query_dict.get("method") or ""),
                int(query_dict.get("max_depth") or query_dict.get("depth") or 3),
            )
        }
    if name == "detect_unused_functions":
        return {"result": detect_unused_functions(db_path)}
    if name == "list_relations":
        return {"result": list_relations(db_path)}
    raise ValueError(f"unknown graph query: {name}")
