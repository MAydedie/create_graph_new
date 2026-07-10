#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from graph_store.sqlite_store import persist_stage6_snapshot  # noqa: E402


STAGE1_TO_STAGE5_TABLES = {
    "partitions",
    "partition_assignments",
    "partition_topology",
    "partitions_optimized",
    "optimization_history",
    "community_summaries",
    "community_summary_history",
    "paths",
    "path_links",
    "path_cfg",
    "path_dfg",
    "path_reverse_index",
    "path_history",
}

STAGE6_TABLES = {"graph_relations", "graph_summary"}
COUNTABLE_TABLES = STAGE1_TO_STAGE5_TABLES | STAGE6_TABLES


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 6 persistence: segment5_output.json -> segment6_output.json + graph.db")
    parser.add_argument("--input", required=True, help="Path to segment5_output.json")
    parser.add_argument("--output", required=True, help="Path to segment6_output.json")
    parser.add_argument("--graph-db", default=None, help="Optional graph.db path to update in place")
    parser.add_argument("--force", action="store_true", help="Rebuild stage6 tables even when they already exist")
    parser.add_argument("--skip-validation", action="store_true", help="Skip referential validation but still merge relations")
    parser.add_argument("--max-relations", type=int, default=None, help="Optional relation row cap for smoke tests")
    parser.add_argument("--verbose", action="store_true", help="Print extra progress logs")
    return parser


def _load_json(path: str) -> Dict[str, Any]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    if not text.strip():
        return {}
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("输入 JSON 顶层必须是对象")
    return payload


def _is_sqlite_file(path: Path) -> bool:
    try:
        return path.is_file() and path.open("rb").read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _is_path_within_root(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _candidate_trust_roots(input_path: str) -> List[Path]:
    input_file = Path(input_path).resolve()
    roots = [input_file.parent]
    if input_file.parent.parent != input_file.parent:
        roots.append(input_file.parent.parent)
    return roots


def _is_path_within_any_root(candidate: Path, roots: List[Path]) -> bool:
    return any(_is_path_within_root(candidate, root) for root in roots)


def _resolve_source_graph_db_path(stage5_payload: Dict[str, Any], input_path: str) -> Path:
    trust_roots = _candidate_trust_roots(input_path)
    artifacts = stage5_payload.get("artifacts") or {}
    for key in ("stage5_graph_db_copy", "graph_db_path"):
        raw = str(artifacts.get(key) or "").strip()
        if not raw:
            continue
        candidate = Path(raw)
        if _is_sqlite_file(candidate) and _is_path_within_any_root(candidate, trust_roots):
            return candidate
    sibling = Path(input_path).resolve().parent / "graph.db"
    if _is_sqlite_file(sibling):
        return sibling
    raise FileNotFoundError("未找到可复用的 stage5 graph.db，请显式传入 --graph-db 或确保 stage5 artifact 存在")


def _prepare_target_graph_db(source_db_path: Path, output_path: str, graph_db_path: Optional[str]) -> Tuple[Path, Optional[Path]]:
    if not _is_sqlite_file(source_db_path):
        raise ValueError(f"无效 graph.db 源文件: {source_db_path}")
    if graph_db_path:
        explicit_path = Path(graph_db_path)
        explicit_path.parent.mkdir(parents=True, exist_ok=True)
        if source_db_path.resolve() == explicit_path.resolve():
            return explicit_path, None
        shutil.copy2(str(source_db_path), str(explicit_path))
        return explicit_path, explicit_path
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    target_path = output_file.parent / "graph.db"
    if source_db_path.resolve() == target_path.resolve():
        return target_path, target_path
    shutil.copy2(str(source_db_path), str(target_path))
    return target_path, target_path


def _load_stage1_symbols(stage5_payload: Dict[str, Any], input_path: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], str]:
    stage1_path = str(((stage5_payload.get("input") or {}).get("stage1_output_path")) or "").strip()
    if not stage1_path:
        return {}, {}, ""
    stage1_file = Path(stage1_path)
    trust_roots = _candidate_trust_roots(input_path)
    if not stage1_file.exists() or not _is_path_within_any_root(stage1_file, trust_roots):
        return {}, {}, stage1_path
    try:
        stage1_payload = _load_json(str(stage1_file))
    except Exception:
        return {}, {}, stage1_path
    symbols = []
    ir_payload = stage1_payload.get("ir") or {}
    if isinstance(ir_payload, dict) and isinstance(ir_payload.get("symbols"), list):
        symbols = [item for item in ir_payload.get("symbols") or [] if isinstance(item, dict)]
    else:
        symbols = [item for item in stage1_payload.get("symbols") or [] if isinstance(item, dict)]
    by_id: Dict[str, Dict[str, Any]] = {}
    by_qn: Dict[str, Dict[str, Any]] = {}
    for symbol in symbols:
        symbol_id = str(symbol.get("id") or "").strip()
        qualified_name = str(symbol.get("qualified_name") or "").strip()
        if symbol_id:
            by_id[symbol_id] = symbol
        if qualified_name:
            by_qn[qualified_name] = symbol
    return by_id, by_qn, stage1_path


def _normalize_chain(chain: Iterable[Any]) -> List[str]:
    return [str(item).strip() for item in chain if str(item).strip()]


def _path_items_for_partition(partition_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [item for item in (partition_payload.get("path_analyses") or []) if isinstance(item, dict)]


def merge_graph_relations(
    stage5_payload: Dict[str, Any],
    *,
    symbol_by_qn: Optional[Dict[str, Dict[str, Any]]] = None,
    max_relations: Optional[int] = None,
) -> List[Dict[str, Any]]:
    symbol_by_qn = symbol_by_qn or {}
    partition_analyses = stage5_payload.get("partition_analyses") or {}
    if not isinstance(partition_analyses, dict):
        return []

    path_ids_by_pair: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    path_names_by_pair: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    status_by_pair: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    for partition_id_raw, partition_payload in partition_analyses.items():
        if not isinstance(partition_payload, dict):
            continue
        partition_id = str(partition_id_raw or "").strip()
        if not partition_id:
            continue
        for path_item in _path_items_for_partition(partition_payload):
            path_id = str(path_item.get("path_id") or "").strip()
            path_name = str(path_item.get("path_name") or "").strip()
            status = str(path_item.get("deep_analysis_status") or path_item.get("status") or "unknown").strip()
            for method_qn in _normalize_chain(path_item.get("function_chain") or path_item.get("path") or []):
                key = (partition_id, method_qn)
                if path_id:
                    path_ids_by_pair[key].add(path_id)
                if path_name:
                    path_names_by_pair[key].add(path_name)
                if status:
                    status_by_pair[key].add(status)

    community_by_partition = {
        str(item.get("partition_id") or "").strip(): item
        for item in (stage5_payload.get("community_summaries") or [])
        if isinstance(item, dict) and str(item.get("partition_id") or "").strip()
    }
    relations: List[Dict[str, Any]] = []
    for partition_id, method_qn in sorted(path_ids_by_pair):
        if max_relations is not None and len(relations) >= max(0, int(max_relations)):
            break
        symbol = symbol_by_qn.get(method_qn) or {}
        community = community_by_partition.get(partition_id) or {}
        path_ids = sorted(path_ids_by_pair[(partition_id, method_qn)])
        relations.append(
            {
                "partition_id": partition_id,
                "method_qn": method_qn,
                "symbol_id": str(symbol.get("id") or "").strip() or None,
                "relation_type": "path_membership",
                "path_ids": path_ids,
                "path_count": len(path_ids),
                "path_names": sorted(path_names_by_pair.get((partition_id, method_qn), set())),
                "path_statuses": sorted(status_by_pair.get((partition_id, method_qn), set())),
                "community_label": str(community.get("label") or community.get("name") or "").strip() or None,
                "summary_status": str(community.get("summary_status") or community.get("status") or "completed").strip(),
                "file_path": str(symbol.get("file_path") or "").strip() or None,
                "line_start": symbol.get("line_start"),
                "line_end": symbol.get("line_end"),
            }
        )
    return relations


def _table_counts(db_path: Path) -> Dict[str, int]:
    if not _is_sqlite_file(db_path):
        return {}
    with sqlite3.connect(str(db_path)) as connection:
        tables = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type=? ORDER BY name", ("table",))
        ]
        counts: Dict[str, int] = {}
        for table in sorted(table for table in tables if table in COUNTABLE_TABLES):
            counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        return counts


def _validate_references(stage5_payload: Dict[str, Any], db_path: Path, symbol_by_qn: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    counts = _table_counts(db_path)
    present_tables = set(counts.keys())
    partition_analyses = stage5_payload.get("partition_analyses") or {}
    partition_ids_json = {str(pid).strip() for pid in partition_analyses.keys()} if isinstance(partition_analyses, dict) else set()
    db_partition_ids: Set[str] = set()
    topology_refs: Set[str] = set()
    with sqlite3.connect(str(db_path)) as connection:
        if "partitions" in present_tables:
            db_partition_ids = {str(row[0]) for row in connection.execute('SELECT partition_id FROM "partitions"')}
        if "partition_topology" in present_tables:
            topology_refs = {
                str(value)
                for row in connection.execute('SELECT source_partition, target_partition FROM "partition_topology"')
                for value in row
            }
    relation_pairs = {
        (relation["partition_id"], relation["method_qn"])
        for relation in merge_graph_relations(stage5_payload, symbol_by_qn=symbol_by_qn)
    }
    missing_symbol_methods = sorted({method for _, method in relation_pairs if symbol_by_qn and method not in symbol_by_qn})
    missing_relation_partitions = sorted({pid for pid, _ in relation_pairs if pid not in db_partition_ids})
    missing_topology_partitions = sorted(topology_refs - db_partition_ids)
    missing_json_partitions = sorted(partition_ids_json - db_partition_ids)
    missing_tables = sorted(STAGE1_TO_STAGE5_TABLES - present_tables)
    status = "ok"
    if missing_tables or missing_relation_partitions or missing_topology_partitions or missing_json_partitions:
        status = "warning"
    return {
        "status": status,
        "stage1_to_stage5_tables_present": sorted(STAGE1_TO_STAGE5_TABLES.intersection(present_tables)),
        "missing_stage1_to_stage5_tables": missing_tables,
        "db_partition_count": len(db_partition_ids),
        "json_partition_analysis_count": len(partition_ids_json),
        "relation_pair_count": len(relation_pairs),
        "missing_json_partitions_in_db": missing_json_partitions,
        "missing_relation_partitions_in_db": missing_relation_partitions,
        "missing_topology_partitions_in_db": missing_topology_partitions,
        "missing_symbol_methods": missing_symbol_methods,
        "symbol_validation_mode": "enabled" if symbol_by_qn else "skipped_no_stage1_symbols",
    }


def _build_run_id(stage5_payload: Dict[str, Any], input_path: str) -> str:
    project = stage5_payload.get("project") or {}
    token = json.dumps(
        {
            "input": str(Path(input_path).resolve()).replace("\\", "/"),
            "project": project.get("path") or project.get("name") or "unknown",
            "schema_version": stage5_payload.get("schema_version") or "unknown",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return "stage6_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _build_graph_summary_rows(
    *,
    run_id: str,
    stage5_payload: Dict[str, Any],
    relations: List[Dict[str, Any]],
    validation: Dict[str, Any],
    duration_ms: int,
    status: str,
    skip_validation: bool,
) -> List[Dict[str, Any]]:
    summary = stage5_payload.get("summary") or {}
    table_counts = validation.get("table_counts_after") or validation.get("table_counts_before") or {}
    relation_counts_by_partition: Dict[str, int] = defaultdict(int)
    for relation in relations:
        relation_counts_by_partition[str(relation.get("partition_id") or "")] += 1
    rows: List[Dict[str, Any]] = [
        {
            "summary_key": f"{run_id}:global",
            "summary_type": "global",
            "status": status,
            "duration_ms": duration_ms,
            "skip_reason": "no_llm_required",
            "value": {
                "schema_version": "stage6.v1",
                "partition_count": int(summary.get("partition_count") or len(stage5_payload.get("partition_analyses") or {})),
                "path_count": int(summary.get("path_count") or len(stage5_payload.get("path_analyses") or [])),
                "community_summary_count": len(stage5_payload.get("community_summaries") or []),
                "relation_count": len(relations),
                "validation_status": validation.get("status"),
                "llm_status": "skipped_no_llm_required",
                "table_counts": table_counts,
            },
        },
        {
            "summary_key": f"{run_id}:validation",
            "summary_type": "validation",
            "status": "skipped" if skip_validation else validation.get("status", "unknown"),
            "duration_ms": 0,
            "skip_reason": "skip_validation flag enabled" if skip_validation else None,
            "value": validation,
        },
    ]
    partition_analyses = stage5_payload.get("partition_analyses") or {}
    if isinstance(partition_analyses, dict) and partition_analyses:
        for partition_id in sorted(str(pid) for pid in partition_analyses.keys()):
            started_at = time.perf_counter()
            rows.append(
                {
                    "summary_key": f"{run_id}:audit:{partition_id}",
                    "summary_type": "partition_audit",
                    "partition_id": partition_id,
                    "status": status,
                    "duration_ms": int((time.perf_counter() - started_at) * 1000),
                    "skip_reason": "no_llm_required",
                    "value": {
                        "partition_id": partition_id,
                        "merged_relations": int(relation_counts_by_partition.get(partition_id, 0)),
                        "status": status,
                        "llm_status": "skipped_no_llm_required",
                    },
                }
            )
    else:
        rows.append(
            {
                "summary_key": f"{run_id}:audit:partial",
                "summary_type": "partition_audit",
                "partition_id": None,
                "status": "partial",
                "duration_ms": 0,
                "skip_reason": "partition_analyses missing or empty",
                "value": {"merged_relations": 0, "status": "partial"},
            }
        )
    return rows


def run_stage6(
    input_path: str,
    output_path: str,
    *,
    graph_db_path: Optional[str] = None,
    force: bool = False,
    skip_validation: bool = False,
    max_relations: Optional[int] = None,
    verbose: bool = False,
) -> Path:
    started_at = time.perf_counter()
    stage5_payload = _load_json(input_path)
    source_graph_db_path = _resolve_source_graph_db_path(stage5_payload, input_path)
    resolved_graph_db_path, copied_db_path = _prepare_target_graph_db(source_graph_db_path, output_path, graph_db_path)
    run_id = _build_run_id(stage5_payload, input_path)
    _symbol_by_id, symbol_by_qn, stage1_path = _load_stage1_symbols(stage5_payload, input_path)

    relations = merge_graph_relations(stage5_payload, symbol_by_qn=symbol_by_qn, max_relations=max_relations)
    partition_analyses = stage5_payload.get("partition_analyses") or {}
    status = "completed" if isinstance(partition_analyses, dict) and partition_analyses else "partial"
    if not relations:
        status = "partial"
    validation: Dict[str, Any] = {"status": "skipped", "reason": "skip_validation flag enabled"} if skip_validation else _validate_references(stage5_payload, resolved_graph_db_path, symbol_by_qn)
    validation["table_counts_before"] = _table_counts(resolved_graph_db_path)
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    summary_rows = _build_graph_summary_rows(
        run_id=run_id,
        stage5_payload=stage5_payload,
        relations=relations,
        validation=validation,
        duration_ms=duration_ms,
        status=status,
        skip_validation=skip_validation,
    )

    project_path = str(((stage5_payload.get("project") or {}).get("path")) or "").strip() or None
    persist_stage6_snapshot(
        str(resolved_graph_db_path),
        graph_relations=relations,
        graph_summary_rows=summary_rows,
        run_id=run_id,
        source_project_path=project_path,
    )
    validation["table_counts_after"] = _table_counts(resolved_graph_db_path)

    output_payload = copy.deepcopy(stage5_payload)
    output_payload["schema_version"] = "stage6.v1"
    output_payload["input"] = {
        **copy.deepcopy(stage5_payload.get("input") or {}),
        "stage5_output_path": str(Path(input_path).resolve()).replace("\\", "/"),
        "stage1_output_path": stage1_path or (stage5_payload.get("input") or {}).get("stage1_output_path"),
        "skip_validation": bool(skip_validation),
        "max_relations": int(max_relations) if max_relations is not None else None,
        "force": bool(force),
    }
    output_payload["artifacts"] = {
        **copy.deepcopy(stage5_payload.get("artifacts") or {}),
        "source_graph_db_path": str(source_graph_db_path).replace("\\", "/"),
        "graph_db_path": str(resolved_graph_db_path).replace("\\", "/"),
        "stage6_graph_db_copy": (str(copied_db_path).replace("\\", "/") if copied_db_path else None),
    }
    output_payload["graph_relations"] = relations
    output_payload["graph_summary"] = summary_rows
    output_payload["persistence"] = {
        "run_id": run_id,
        "status": status,
        "skip_reason": "no_llm_required",
        "llm_status": "skipped_no_llm_required",
        "duration_ms": duration_ms,
        "validation": validation,
    }
    output_payload["summary"] = {
        **copy.deepcopy(stage5_payload.get("summary") or {}),
        "status": status,
        "stage6_status": status,
        "graph_relation_count": len(relations),
        "graph_summary_count": len(summary_rows),
        "validation_status": validation.get("status"),
        "llm_status": "skipped_no_llm_required",
        "skip_reason": "no_llm_required",
        "duration_ms": duration_ms,
    }

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    if verbose:
        print("[segment_6_persistence] 输出完成")
        print(f"  output: {output_file}")
        print(f"  graph_db: {resolved_graph_db_path}")
        print(f"  graph_relations: {len(relations)}")
        print(f"  graph_summary: {len(summary_rows)}")
        print(f"  status: {status}")
    return output_file


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        run_stage6(
            input_path=args.input,
            output_path=args.output,
            graph_db_path=args.graph_db,
            force=bool(args.force),
            skip_validation=bool(args.skip_validation),
            max_relations=args.max_relations,
            verbose=bool(args.verbose),
        )
        return 0
    except Exception as exc:
        print(f"[segment_6_persistence] ERROR: {exc}", file=sys.stderr)
        return 1
