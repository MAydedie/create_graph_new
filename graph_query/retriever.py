#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict, List

from .basic import get_node_info
from .hub_query import get_architecture


def build_graph_context(db_path: str, method_qns: List[str] | None = None, top_k: int = 5) -> Dict[str, Any]:
    methods = [get_node_info(db_path, method_qn) for method_qn in (method_qns or [])]
    return {
        "architecture": get_architecture(db_path, top_k=top_k),
        "methods": methods,
        "graph_queries_used": [
            {"tool": "get_architecture", "input": {"top_k": top_k}},
            *[{"tool": "get_node_info", "input": {"method": method_qn}} for method_qn in (method_qns or [])],
        ],
    }
