#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def append_audit_row(audit_log_path: str | Path, row: Dict[str, Any]) -> None:
    path = Path(audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_audit_row(
    *,
    ts: str,
    run_id: str,
    graph_db_path: str,
    segment6_json_path: str,
    project_path: str,
    user_intent: str,
    template_used: str,
    skip_llm: bool,
    status: str,
    llm_status: str,
    sections_filled: int,
    queries_used: int,
    output_path: str,
    spec_json_path: str,
    raw_results_path: str,
    duration_ms: int,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "ts": ts,
        "run_id": run_id,
        "input_summary": {
            "graph_db_path": graph_db_path,
            "segment6_json_path": segment6_json_path,
            "project_path": project_path,
            "user_intent": user_intent,
            "template_used": template_used,
            "skip_llm": bool(skip_llm),
        },
        "output_summary": {
            "status": status,
            "sections_filled": int(sections_filled),
            "queries_used": int(queries_used),
            "output_path": output_path,
            "spec_json_path": spec_json_path,
            "raw_results_path": raw_results_path,
            "duration_ms": int(duration_ms),
        },
        "duration_ms": int(duration_ms),
        "status": status,
        "llm_status": llm_status,
        "error": error,
    }
