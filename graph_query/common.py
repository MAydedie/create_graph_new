#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


REQUIRED_STAGE7_TABLES: Set[str] = {
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
    "graph_relations",
    "graph_summary",
}

WRITE_SQL_PREFIXES = (
    "alter",
    "attach",
    "create",
    "delete",
    "detach",
    "drop",
    "insert",
    "pragma writable_schema",
    "reindex",
    "replace",
    "update",
    "vacuum",
)


class GraphQueryError(RuntimeError):
    pass


def parse_json(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def normalize_path(path: str | Path) -> str:
    return str(Path(path).resolve()).replace("\\", "/")


def connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    uri = "file:" + path.resolve().as_posix() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def dict_rows(rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows]


def list_tables(connection: sqlite3.Connection) -> Set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def table_counts(connection: sqlite3.Connection, tables: Optional[Iterable[str]] = None) -> Dict[str, int]:
    present = list_tables(connection)
    selected = sorted(set(tables or present) & present)
    counts: Dict[str, int] = {}
    for table in selected:
        counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    return counts


def validate_graph_db(db_path: str | Path, required_tables: Optional[Set[str]] = None) -> Dict[str, Any]:
    required = set(required_tables or REQUIRED_STAGE7_TABLES)
    path = Path(db_path)
    if not path.exists():
        return {
            "status": "partial",
            "errors": [f"graph.db does not exist: {path}"],
            "missing_tables": sorted(required),
            "table_counts": {},
        }
    try:
        with connect_readonly(path) as connection:
            present = list_tables(connection)
            missing = sorted(required - present)
            errors = [f"missing table: {table}" for table in missing]
            return {
                "status": "partial" if missing else "ok",
                "errors": errors,
                "missing_tables": missing,
                "table_counts": table_counts(connection, present & required),
            }
    except sqlite3.Error as exc:
        return {
            "status": "partial",
            "errors": [f"cannot open graph.db read-only: {exc}"],
            "missing_tables": sorted(required),
            "table_counts": {},
        }


def ensure_readonly_sql(sql: str) -> None:
    normalized = " ".join(sql.strip().lower().split())
    if normalized.startswith(WRITE_SQL_PREFIXES):
        raise GraphQueryError(f"write SQL is not allowed in stage7 graph query: {sql[:80]}")


def select_all(
    connection: sqlite3.Connection,
    sql: str,
    params: Sequence[Any] = (),
) -> List[Dict[str, Any]]:
    ensure_readonly_sql(sql)
    return dict_rows(connection.execute(sql, tuple(params)).fetchall())


def first_value(connection: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Any:
    ensure_readonly_sql(sql)
    row = connection.execute(sql, tuple(params)).fetchone()
    return row[0] if row else None


def relation_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = parse_json(row.get("relation_payload_json"), {}) or {}
    path_ids = parse_json(row.get("path_ids_json"), []) or []
    return {
        "partition_id": row.get("partition_id"),
        "method_qn": row.get("method_qn"),
        "symbol_id": row.get("symbol_id"),
        "relation_type": row.get("relation_type"),
        "path_ids": sorted(str(item) for item in path_ids),
        "path_count": int(row.get("path_count") or 0),
        "first_path_id": row.get("first_path_id"),
        "community_label": row.get("community_label"),
        "summary_status": row.get("summary_status"),
        "source_project_path": row.get("source_project_path"),
        "run_id": row.get("run_id"),
        "file_path": payload.get("file_path"),
        "line_start": payload.get("line_start"),
        "line_end": payload.get("line_end"),
        "path_names": payload.get("path_names") or [],
        "path_statuses": payload.get("path_statuses") or [],
    }


def sorted_unique(values: Iterable[Any]) -> List[str]:
    return sorted({str(value) for value in values if str(value or "").strip()})


def edge_key(caller: str, callee: str) -> Tuple[str, str]:
    return str(caller), str(callee)
