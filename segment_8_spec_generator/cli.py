#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from .spec_generator import run_stage8  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 8 graph-aware spec generator: stage6 graph.db -> spec.md + spec.json")
    parser.add_argument("--graph-db", required=True, help="Path to stage6 graph.db")
    parser.add_argument("--segment6-json", required=True, help="Path to stage6 segment6_output.json")
    parser.add_argument("--project", default="", help="Source project path for README/module/API scanning")
    parser.add_argument("--intent", default="项目说明书", help="User intent for the generated specification")
    parser.add_argument("--output", required=True, help="Path to spec_<timestamp>.md")
    parser.add_argument("--spec-json", default=None, help="Path to spec_<timestamp>.json")
    parser.add_argument("--raw-results", default=None, help="Path to raw_graph_query_results.json")
    parser.add_argument("--audit-log", default=None, help="Path to logs/spec_generator_audit.jsonl")
    parser.add_argument("--template", default=None, help="Path to templates/spec_template_v2.md")
    parser.add_argument("--top-k", type=int, default=5, help="Hub count for graph_query.find_hubs/get_architecture")
    parser.add_argument("--max-paths", type=int, default=3, help="Maximum persisted core call chains")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM enrichment and render graph skeleton")
    parser.add_argument("--batch", default=None, help="Reserved batch query file path for replay metadata")
    parser.add_argument("--verbose", action="store_true", help="Print extra progress logs")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        run_stage8(
            graph_db_path=args.graph_db,
            segment6_json_path=args.segment6_json,
            project_path=args.project,
            output_path=args.output,
            spec_json_path=args.spec_json,
            raw_results_path=args.raw_results,
            audit_log_path=args.audit_log,
            template_path=args.template,
            user_intent=args.intent,
            top_k=args.top_k,
            max_paths=args.max_paths,
            skip_llm=bool(args.skip_llm),
            batch_path=args.batch,
            verbose=bool(args.verbose),
        )
        return 0
    except Exception as exc:
        print(f"[segment_8_spec_generator] ERROR: {exc}", file=sys.stderr)
        return 1
