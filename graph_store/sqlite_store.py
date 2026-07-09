#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from graph_store.extractors.from_optimizer import (
    extract_optimization_history_records,
    extract_optimized_partition_records,
)
from graph_store.extractors.from_community_semantics import (
    extract_community_summary_history_records,
    extract_community_summary_records,
)
from graph_store.extractors.from_paths import (
    extract_path_cfg_records,
    extract_path_dfg_records,
    extract_path_link_records,
    extract_path_records,
    extract_path_reverse_index_records,
)
from graph_store.extractors.from_partitions import extract_partition_members, extract_partition_records


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS partitions (
            partition_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            original_name TEXT,
            modularity REAL NOT NULL,
            cohesion_score REAL NOT NULL,
            internal_calls INTEGER NOT NULL,
            external_calls INTEGER NOT NULL,
            size INTEGER NOT NULL,
            method_count INTEGER NOT NULL,
            source_project_path TEXT
        );

        CREATE TABLE IF NOT EXISTS partition_assignments (
            partition_id TEXT NOT NULL,
            member_order INTEGER NOT NULL,
            symbol_id TEXT NOT NULL,
            symbol_qualified_name TEXT NOT NULL,
            PRIMARY KEY (partition_id, symbol_id),
            FOREIGN KEY (partition_id) REFERENCES partitions(partition_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS partition_topology (
            source_partition TEXT NOT NULL,
            target_partition TEXT NOT NULL,
            edge_count INTEGER NOT NULL,
            weight REAL NOT NULL,
            call_examples_json TEXT NOT NULL,
            PRIMARY KEY (source_partition, target_partition),
            FOREIGN KEY (source_partition) REFERENCES partitions(partition_id) ON DELETE CASCADE,
            FOREIGN KEY (target_partition) REFERENCES partitions(partition_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_partition_assignments_partition_id
        ON partition_assignments(partition_id);

        CREATE INDEX IF NOT EXISTS idx_partition_assignments_symbol_id
        ON partition_assignments(symbol_id);

        CREATE INDEX IF NOT EXISTS idx_partition_assignments_symbol_qn
        ON partition_assignments(symbol_qualified_name);

        CREATE INDEX IF NOT EXISTS idx_partition_topology_source
        ON partition_topology(source_partition);

        CREATE INDEX IF NOT EXISTS idx_partition_topology_target
        ON partition_topology(target_partition);

        CREATE TABLE IF NOT EXISTS partitions_optimized (
            optimization_run_id TEXT NOT NULL,
            partition_id TEXT NOT NULL,
            name TEXT NOT NULL,
            original_name TEXT,
            modularity REAL NOT NULL,
            cohesion_score REAL NOT NULL,
            internal_calls INTEGER NOT NULL,
            external_calls INTEGER NOT NULL,
            size INTEGER NOT NULL,
            method_count INTEGER NOT NULL,
            methods_json TEXT NOT NULL,
            qualified_methods_json TEXT NOT NULL,
            member_symbols_json TEXT NOT NULL,
            source_project_path TEXT,
            trigger_mode TEXT NOT NULL,
            threshold REAL NOT NULL,
            was_optimized INTEGER NOT NULL,
            PRIMARY KEY (optimization_run_id, partition_id)
        );

        CREATE TABLE IF NOT EXISTS optimization_history (
            optimization_run_id TEXT NOT NULL,
            history_index INTEGER NOT NULL,
            iteration INTEGER NOT NULL,
            action TEXT NOT NULL,
            partitions_before_json TEXT NOT NULL,
            partitions_after_json TEXT NOT NULL,
            modularity_before REAL NOT NULL,
            modularity_after REAL NOT NULL,
            modularity_improvement REAL NOT NULL,
            llm_reasoning TEXT NOT NULL,
            details_json TEXT NOT NULL,
            source_project_path TEXT,
            trigger_mode TEXT NOT NULL,
            threshold REAL NOT NULL,
            status TEXT NOT NULL,
            skip_reason TEXT,
            PRIMARY KEY (optimization_run_id, history_index)
        );

        CREATE INDEX IF NOT EXISTS idx_partitions_optimized_partition_id
        ON partitions_optimized(partition_id);

        CREATE INDEX IF NOT EXISTS idx_optimization_history_iteration
        ON optimization_history(iteration);

        CREATE TABLE IF NOT EXISTS community_summaries (
            community_run_id TEXT NOT NULL,
            partition_id TEXT NOT NULL,
            name TEXT NOT NULL,
            original_name TEXT,
            modularity REAL NOT NULL,
            cohesion_score REAL NOT NULL,
            internal_calls INTEGER NOT NULL,
            external_calls INTEGER NOT NULL,
            size INTEGER NOT NULL,
            method_count INTEGER NOT NULL,
            methods_json TEXT NOT NULL,
            qualified_methods_json TEXT NOT NULL,
            member_symbols_json TEXT NOT NULL,
            semantic_label TEXT NOT NULL,
            description TEXT NOT NULL,
            functional_domain TEXT NOT NULL,
            key_concepts_json TEXT NOT NULL,
            top_files_json TEXT NOT NULL,
            top_dependencies_json TEXT NOT NULL,
            source_project_path TEXT,
            trigger_mode TEXT NOT NULL,
            threshold REAL NOT NULL,
            status TEXT NOT NULL,
            skip_reason TEXT,
            model TEXT,
            duration_ms INTEGER NOT NULL,
            PRIMARY KEY (community_run_id, partition_id)
        );

        CREATE TABLE IF NOT EXISTS community_summary_history (
            community_run_id TEXT NOT NULL,
            history_index INTEGER NOT NULL,
            partition_id TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            llm_reasoning TEXT NOT NULL,
            details_json TEXT NOT NULL,
            source_project_path TEXT,
            trigger_mode TEXT NOT NULL,
            threshold REAL NOT NULL,
            skip_reason TEXT,
            model TEXT,
            duration_ms INTEGER NOT NULL,
            PRIMARY KEY (community_run_id, history_index)
        );

        CREATE INDEX IF NOT EXISTS idx_community_summaries_partition_id
        ON community_summaries(partition_id);

        CREATE INDEX IF NOT EXISTS idx_community_summaries_status
        ON community_summaries(status);

        CREATE INDEX IF NOT EXISTS idx_community_summary_history_partition_id
        ON community_summary_history(partition_id);

        CREATE INDEX IF NOT EXISTS idx_community_summary_history_status
        ON community_summary_history(status);

        CREATE TABLE IF NOT EXISTS paths (
            path_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            partition_id TEXT NOT NULL,
            leaf_node TEXT NOT NULL,
            function_chain_json TEXT NOT NULL,
            path_name TEXT NOT NULL,
            path_description TEXT NOT NULL,
            semantic_label TEXT NOT NULL,
            keywords_json TEXT NOT NULL,
            functional_domain TEXT NOT NULL,
            worthiness_score REAL NOT NULL,
            deep_analysis_status TEXT NOT NULL,
            cfg_dfg_explain_md TEXT NOT NULL,
            model TEXT,
            duration_ms INTEGER NOT NULL,
            source_project_path TEXT,
            skip_reason TEXT,
            trigger_mode TEXT NOT NULL,
            llm_reasoning TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS path_links (
            link_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            path_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            caller TEXT NOT NULL,
            callee TEXT NOT NULL,
            is_direct_call INTEGER,
            caller_file_path TEXT NOT NULL,
            callee_file_path TEXT NOT NULL,
            FOREIGN KEY (path_id) REFERENCES paths(path_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS path_cfg (
            cfg_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            path_id TEXT NOT NULL,
            method_sig TEXT NOT NULL,
            node_id TEXT NOT NULL,
            line_number INTEGER NOT NULL,
            node_type TEXT NOT NULL,
            code_excerpt TEXT NOT NULL,
            FOREIGN KEY (path_id) REFERENCES paths(path_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS path_dfg (
            dfg_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            path_id TEXT NOT NULL,
            method_sig TEXT NOT NULL,
            variable_name TEXT NOT NULL,
            node_id TEXT NOT NULL,
            line_number INTEGER NOT NULL,
            node_type TEXT NOT NULL,
            method_node_id TEXT NOT NULL,
            FOREIGN KEY (path_id) REFERENCES paths(path_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS path_reverse_index (
            method_qn TEXT NOT NULL,
            run_id TEXT NOT NULL,
            path_id TEXT NOT NULL,
            PRIMARY KEY (method_qn, run_id, path_id),
            FOREIGN KEY (path_id) REFERENCES paths(path_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_paths_partition_id ON paths(partition_id);
        CREATE INDEX IF NOT EXISTS idx_paths_source_project_path ON paths(source_project_path);
        CREATE INDEX IF NOT EXISTS idx_path_links_path_id ON path_links(path_id);
        CREATE INDEX IF NOT EXISTS idx_path_cfg_path_id ON path_cfg(path_id);
        CREATE INDEX IF NOT EXISTS idx_path_dfg_path_id ON path_dfg(path_id);
        CREATE INDEX IF NOT EXISTS idx_path_reverse_index_method_qn ON path_reverse_index(method_qn);

        CREATE TABLE IF NOT EXISTS path_history (
            history_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            path_id TEXT NOT NULL,
            partition_id TEXT NOT NULL,
            status TEXT NOT NULL,
            model TEXT,
            duration_ms INTEGER NOT NULL,
            skip_reason TEXT,
            llm_reasoning TEXT NOT NULL,
            source_project_path TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_path_history_run_id ON path_history(run_id);
        CREATE INDEX IF NOT EXISTS idx_path_history_status ON path_history(status);

        CREATE TABLE IF NOT EXISTS graph_relations (
            partition_id TEXT NOT NULL,
            method_qn TEXT NOT NULL,
            symbol_id TEXT,
            relation_type TEXT NOT NULL,
            path_ids_json TEXT NOT NULL,
            path_count INTEGER NOT NULL,
            first_path_id TEXT,
            community_label TEXT,
            summary_status TEXT NOT NULL,
            source_project_path TEXT,
            run_id TEXT NOT NULL,
            relation_payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (partition_id, method_qn)
        );

        CREATE INDEX IF NOT EXISTS idx_graph_relations_partition_id
        ON graph_relations(partition_id);

        CREATE INDEX IF NOT EXISTS idx_graph_relations_method_qn
        ON graph_relations(method_qn);

        CREATE TABLE IF NOT EXISTS graph_summary (
            summary_key TEXT PRIMARY KEY,
            summary_type TEXT NOT NULL,
            partition_id TEXT,
            status TEXT NOT NULL,
            value_json TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            skip_reason TEXT,
            source_project_path TEXT,
            run_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_graph_summary_type
        ON graph_summary(summary_type);

        CREATE INDEX IF NOT EXISTS idx_graph_summary_partition_id
        ON graph_summary(partition_id);
        """
    )


def persist_stage2_snapshot(
    db_path: str,
    partitions: List[Dict[str, Any]],
    partition_topology: List[Dict[str, Any]],
    source_project_path: Optional[str] = None,
) -> Path:
    target_path = Path(db_path)
    _ensure_parent(target_path)

    partition_records = extract_partition_records(partitions, source_project_path=source_project_path)
    partition_member_records = extract_partition_members(partitions)
    topology_rows = sorted(
        [
            {
                "source_partition": str(item.get("source_partition") or "unknown"),
                "target_partition": str(item.get("target_partition") or "unknown"),
                "edge_count": int(item.get("edge_count") or 0),
                "weight": float(item.get("weight") or 0.0),
                "call_examples_json": json.dumps(
                    sorted(
                        item.get("call_examples", []) or [],
                        key=lambda pair: (
                            str(pair.get("source_symbol_id") or ""),
                            str(pair.get("source_qualified_name") or ""),
                            str(pair.get("target_symbol_id") or ""),
                            str(pair.get("target_qualified_name") or ""),
                        ),
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
            for item in (partition_topology or [])
        ],
        key=lambda item: (item["source_partition"], item["target_partition"]),
    )

    with sqlite3.connect(str(target_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _create_schema(connection)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM partition_topology")
            connection.execute("DELETE FROM partition_assignments")
            connection.execute("DELETE FROM partitions")
            connection.executemany(
                """
                INSERT INTO partitions (
                    partition_id, name, original_name, modularity, cohesion_score,
                    internal_calls, external_calls, size, method_count, source_project_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.partition_id,
                        record.name,
                        record.original_name,
                        record.modularity,
                        record.cohesion_score,
                        record.internal_calls,
                        record.external_calls,
                        record.size,
                        record.method_count,
                        record.source_project_path,
                    )
                    for record in partition_records
                ],
            )
            connection.executemany(
                """
                INSERT INTO partition_assignments (
                    partition_id, member_order, symbol_id, symbol_qualified_name
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        record.partition_id,
                        record.member_order,
                        record.symbol_id,
                        record.symbol_qualified_name,
                    )
                    for record in partition_member_records
                ],
            )
            connection.executemany(
                """
                INSERT INTO partition_topology (
                    source_partition, target_partition, edge_count, weight, call_examples_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["source_partition"],
                        row["target_partition"],
                        row["edge_count"],
                        row["weight"],
                        row["call_examples_json"],
                    )
                    for row in topology_rows
                ],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return target_path


def persist_stage3_snapshot(
    db_path: str,
    partitions_optimized: List[Dict[str, Any]],
    optimization_history: List[Dict[str, Any]],
    *,
    source_project_path: Optional[str] = None,
    optimization_run_id: str = "stage3_latest",
    trigger_mode: str = "skip",
    threshold: float = 0.4,
    was_optimized: bool = False,
) -> Path:
    target_path = Path(db_path)
    _ensure_parent(target_path)

    optimized_records = extract_optimized_partition_records(
        partitions_optimized,
        optimization_run_id=optimization_run_id,
        source_project_path=source_project_path,
        trigger_mode=trigger_mode,
        threshold=threshold,
        was_optimized=was_optimized,
    )
    history_records = extract_optimization_history_records(
        optimization_history,
        optimization_run_id=optimization_run_id,
        source_project_path=source_project_path,
        trigger_mode=trigger_mode,
        threshold=threshold,
    )

    with sqlite3.connect(str(target_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _create_schema(connection)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM optimization_history WHERE source_project_path IS ?",
                (source_project_path,),
            )
            connection.execute(
                "DELETE FROM partitions_optimized WHERE source_project_path IS ?",
                (source_project_path,),
            )
            connection.executemany(
                """
                INSERT INTO partitions_optimized (
                    optimization_run_id, partition_id, name, original_name, modularity,
                    cohesion_score, internal_calls, external_calls, size, method_count,
                    methods_json, qualified_methods_json, member_symbols_json,
                    source_project_path, trigger_mode, threshold, was_optimized
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.optimization_run_id,
                        record.partition_id,
                        record.name,
                        record.original_name,
                        record.modularity,
                        record.cohesion_score,
                        record.internal_calls,
                        record.external_calls,
                        record.size,
                        record.method_count,
                        record.methods_json,
                        record.qualified_methods_json,
                        record.member_symbols_json,
                        record.source_project_path,
                        record.trigger_mode,
                        record.threshold,
                        int(record.was_optimized),
                    )
                    for record in optimized_records
                ],
            )
            connection.executemany(
                """
                INSERT INTO optimization_history (
                    optimization_run_id, history_index, iteration, action,
                    partitions_before_json, partitions_after_json,
                    modularity_before, modularity_after, modularity_improvement,
                    llm_reasoning, details_json, source_project_path,
                    trigger_mode, threshold, status, skip_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.optimization_run_id,
                        record.history_index,
                        record.iteration,
                        record.action,
                        record.partitions_before_json,
                        record.partitions_after_json,
                        record.modularity_before,
                        record.modularity_after,
                        record.modularity_improvement,
                        record.llm_reasoning,
                        record.details_json,
                        record.source_project_path,
                        record.trigger_mode,
                        record.threshold,
                        record.status,
                        record.skip_reason,
                    )
                    for record in history_records
                ],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return target_path


def persist_stage4_snapshot(
    db_path: str,
    community_summaries: List[Dict[str, Any]],
    community_summary_history: List[Dict[str, Any]],
    *,
    source_project_path: Optional[str] = None,
    community_run_id: str = "stage4_latest",
    trigger_mode: str = "skip",
    threshold: float = 0.4,
) -> Path:
    target_path = Path(db_path)
    _ensure_parent(target_path)

    summary_records = extract_community_summary_records(
        community_summaries,
        community_run_id=community_run_id,
        source_project_path=source_project_path,
        trigger_mode=trigger_mode,
        threshold=threshold,
    )
    history_records = extract_community_summary_history_records(
        community_summary_history,
        community_run_id=community_run_id,
        source_project_path=source_project_path,
        trigger_mode=trigger_mode,
        threshold=threshold,
    )

    with sqlite3.connect(str(target_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _create_schema(connection)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM community_summary_history WHERE source_project_path IS ?",
                (source_project_path,),
            )
            connection.execute(
                "DELETE FROM community_summaries WHERE source_project_path IS ?",
                (source_project_path,),
            )
            connection.executemany(
                """
                INSERT INTO community_summaries (
                    community_run_id, partition_id, name, original_name, modularity,
                    cohesion_score, internal_calls, external_calls, size, method_count,
                    methods_json, qualified_methods_json, member_symbols_json,
                    semantic_label, description, functional_domain, key_concepts_json,
                    top_files_json, top_dependencies_json, source_project_path,
                    trigger_mode, threshold, status, skip_reason, model, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.community_run_id,
                        record.partition_id,
                        record.name,
                        record.original_name,
                        record.modularity,
                        record.cohesion_score,
                        record.internal_calls,
                        record.external_calls,
                        record.size,
                        record.method_count,
                        record.methods_json,
                        record.qualified_methods_json,
                        record.member_symbols_json,
                        record.semantic_label,
                        record.description,
                        record.functional_domain,
                        record.key_concepts_json,
                        record.top_files_json,
                        record.top_dependencies_json,
                        record.source_project_path,
                        record.trigger_mode,
                        record.threshold,
                        record.status,
                        record.skip_reason,
                        record.model,
                        record.duration_ms,
                    )
                    for record in summary_records
                ],
            )
            connection.executemany(
                """
                INSERT INTO community_summary_history (
                    community_run_id, history_index, partition_id, action, status,
                    llm_reasoning, details_json, source_project_path, trigger_mode,
                    threshold, skip_reason, model, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.community_run_id,
                        record.history_index,
                        record.partition_id,
                        record.action,
                        record.status,
                        record.llm_reasoning,
                        record.details_json,
                        record.source_project_path,
                        record.trigger_mode,
                        record.threshold,
                        record.skip_reason,
                        record.model,
                        record.duration_ms,
                    )
                    for record in history_records
                ],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return target_path


def load_stage4_community_summaries(
    db_path: str,
    *,
    source_project_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    target_path = Path(db_path)
    if not target_path.exists() or not target_path.is_file():
        return []

    normalized_project_path = os.path.normpath(str(source_project_path)) if source_project_path not in {None, ''} else None

    with sqlite3.connect(str(target_path)) as connection:
        connection.row_factory = sqlite3.Row
        _create_schema(connection)
        rows = connection.execute(
            """
            SELECT
                community_run_id,
                partition_id,
                name,
                original_name,
                modularity,
                cohesion_score,
                internal_calls,
                external_calls,
                size,
                method_count,
                methods_json,
                qualified_methods_json,
                member_symbols_json,
                semantic_label,
                description,
                functional_domain,
                key_concepts_json,
                top_files_json,
                top_dependencies_json,
                source_project_path,
                trigger_mode,
                threshold,
                status,
                skip_reason,
                model,
                duration_ms
            FROM community_summaries
            WHERE source_project_path IS ?
            ORDER BY partition_id ASC
            """,
            (normalized_project_path,),
        ).fetchall()

    payloads: List[Dict[str, Any]] = []
    for row in rows:
        payloads.append(
            {
                "community_run_id": row["community_run_id"],
                "partition_id": row["partition_id"],
                "name": row["name"],
                "original_name": row["original_name"],
                "modularity": float(row["modularity"] or 0.0),
                "cohesion_score": float(row["cohesion_score"] or 0.0),
                "internal_calls": int(row["internal_calls"] or 0),
                "external_calls": int(row["external_calls"] or 0),
                "size": int(row["size"] or 0),
                "method_count": int(row["method_count"] or 0),
                "methods": json.loads(row["methods_json"] or "[]"),
                "qualified_methods": json.loads(row["qualified_methods_json"] or "[]"),
                "member_symbols": json.loads(row["member_symbols_json"] or "[]"),
                "label": str(row["semantic_label"] or "").strip(),
                "description": str(row["description"] or "").strip(),
                "functional_domain": str(row["functional_domain"] or "").strip(),
                "key_concepts": json.loads(row["key_concepts_json"] or "[]"),
                "top_files": json.loads(row["top_files_json"] or "[]"),
                "top_dependencies": json.loads(row["top_dependencies_json"] or "[]"),
                "source_project_path": row["source_project_path"],
                "trigger_mode": str(row["trigger_mode"] or "").strip(),
                "threshold": float(row["threshold"] or 0.0),
                "summary_status": str(row["status"] or "").strip(),
                "skip_reason": row["skip_reason"],
                "model": row["model"],
                "duration_ms": int(row["duration_ms"] or 0),
            }
        )
    return payloads


def persist_stage5_snapshot(
    db_path: str,
    path_analyses: List[Dict[str, Any]],
    *,
    run_id: str,
    source_project_path: Optional[str] = None,
    symbol_by_qn: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Path:
    target_path = Path(db_path)
    _ensure_parent(target_path)

    path_records = extract_path_records(path_analyses, run_id=run_id, source_project_path=source_project_path)
    link_records = extract_path_link_records(path_analyses, run_id=run_id, symbol_by_qn=symbol_by_qn)
    cfg_records = extract_path_cfg_records(path_analyses, run_id=run_id)
    dfg_records = extract_path_dfg_records(path_analyses, run_id=run_id)
    reverse_index_records = extract_path_reverse_index_records(path_analyses, run_id=run_id)
    history_rows = [
        (
            f"{run_id}:{str(item.get('path_id') or 'run').strip()}",
            run_id,
            str(item.get("path_id") or "").strip(),
            str(item.get("partition_id") or "").strip(),
            str(item.get("deep_analysis_status") or "unknown").strip(),
            (str(item.get("model")) if item.get("model") not in {None, ""} else None),
            int(item.get("duration_ms") or 0),
            (str(item.get("skip_reason")) if item.get("skip_reason") not in {None, ""} else None),
            str(item.get("llm_reasoning") or "").strip(),
            source_project_path,
        )
        for item in (path_analyses or [])
    ]
    if not history_rows:
        history_rows.append((f"{run_id}:run", run_id, "", "", "partial", None, 0, "no_paths_generated", "no_paths_generated", source_project_path))

    with sqlite3.connect(str(target_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _create_schema(connection)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM path_history WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM path_reverse_index WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM path_dfg WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM path_cfg WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM path_links WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM paths WHERE run_id = ?", (run_id,))
            connection.executemany(
                """
                INSERT INTO paths (
                    path_id, run_id, partition_id, leaf_node, function_chain_json,
                    path_name, path_description, semantic_label, keywords_json,
                    functional_domain, worthiness_score, deep_analysis_status,
                    cfg_dfg_explain_md, model, duration_ms, source_project_path,
                    skip_reason, trigger_mode, llm_reasoning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.path_id,
                        record.run_id,
                        record.partition_id,
                        record.leaf_node,
                        record.function_chain_json,
                        record.path_name,
                        record.path_description,
                        record.semantic_label,
                        record.keywords_json,
                        record.functional_domain,
                        record.worthiness_score,
                        record.deep_analysis_status,
                        record.cfg_dfg_explain_md,
                        record.model,
                        record.duration_ms,
                        record.source_project_path,
                        record.skip_reason,
                        record.trigger_mode,
                        record.llm_reasoning,
                    )
                    for record in path_records
                ],
            )
            connection.executemany(
                """
                INSERT INTO path_links (
                    link_id, run_id, path_id, step_index, caller, callee,
                    is_direct_call, caller_file_path, callee_file_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.link_id,
                        record.run_id,
                        record.path_id,
                        record.step_index,
                        record.caller,
                        record.callee,
                        None if record.is_direct_call is None else int(record.is_direct_call),
                        record.caller_file_path,
                        record.callee_file_path,
                    )
                    for record in link_records
                ],
            )
            connection.executemany(
                """
                INSERT INTO path_cfg (
                    cfg_id, run_id, path_id, method_sig, node_id, line_number, node_type, code_excerpt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.cfg_id,
                        record.run_id,
                        record.path_id,
                        record.method_sig,
                        record.node_id,
                        record.line_number,
                        record.node_type,
                        record.code_excerpt,
                    )
                    for record in cfg_records
                ],
            )
            connection.executemany(
                """
                INSERT INTO path_dfg (
                    dfg_id, run_id, path_id, method_sig, variable_name, node_id, line_number, node_type, method_node_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.dfg_id,
                        record.run_id,
                        record.path_id,
                        record.method_sig,
                        record.variable_name,
                        record.node_id,
                        record.line_number,
                        record.node_type,
                        record.method_node_id,
                    )
                    for record in dfg_records
                ],
            )
            connection.executemany(
                """
                INSERT INTO path_reverse_index (method_qn, run_id, path_id)
                VALUES (?, ?, ?)
                """,
                [
                    (record.method_qn, record.run_id, record.path_id)
                    for record in reverse_index_records
                ],
            )
            connection.executemany(
                """
                INSERT INTO path_history (
                    history_id, run_id, path_id, partition_id, status, model,
                    duration_ms, skip_reason, llm_reasoning, source_project_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                history_rows,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return target_path


def persist_stage6_snapshot(
    db_path: str,
    *,
    graph_relations: List[Dict[str, Any]],
    graph_summary_rows: List[Dict[str, Any]],
    run_id: str,
    source_project_path: Optional[str] = None,
) -> Path:
    target_path = Path(db_path)
    _ensure_parent(target_path)

    normalized_project_path = os.path.normpath(str(source_project_path)) if source_project_path not in {None, ""} else None
    created_at = "stage6-deterministic"

    relation_rows = []
    for relation in sorted(
        graph_relations or [],
        key=lambda item: (str(item.get("partition_id") or ""), str(item.get("method_qn") or "")),
    ):
        partition_id = str(relation.get("partition_id") or "").strip()
        method_qn = str(relation.get("method_qn") or "").strip()
        if not partition_id or not method_qn:
            continue
        path_ids = sorted(dict.fromkeys(str(item).strip() for item in (relation.get("path_ids") or []) if str(item).strip()))
        payload = {
            key: relation.get(key)
            for key in sorted(relation.keys())
            if key not in {"partition_id", "method_qn"}
        }
        relation_rows.append(
            (
                partition_id,
                method_qn,
                (str(relation.get("symbol_id")) if relation.get("symbol_id") not in {None, ""} else None),
                str(relation.get("relation_type") or "path_membership").strip(),
                json.dumps(path_ids, ensure_ascii=False, sort_keys=True),
                int(relation.get("path_count") or len(path_ids)),
                (path_ids[0] if path_ids else None),
                (str(relation.get("community_label")) if relation.get("community_label") not in {None, ""} else None),
                str(relation.get("summary_status") or "completed").strip(),
                normalized_project_path,
                run_id,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                created_at,
            )
        )

    summary_rows = []
    for row in sorted(graph_summary_rows or [], key=lambda item: str(item.get("summary_key") or "")):
        summary_key = str(row.get("summary_key") or "").strip()
        if not summary_key:
            continue
        value = row.get("value") if "value" in row else row.get("value_json", {})
        if isinstance(value, str):
            value_json = value
        else:
            value_json = json.dumps(value, ensure_ascii=False, sort_keys=True)
        summary_rows.append(
            (
                summary_key,
                str(row.get("summary_type") or "summary").strip(),
                (str(row.get("partition_id")) if row.get("partition_id") not in {None, ""} else None),
                str(row.get("status") or "completed").strip(),
                value_json,
                int(row.get("duration_ms") or 0),
                (str(row.get("skip_reason")) if row.get("skip_reason") not in {None, ""} else None),
                normalized_project_path,
                run_id,
                created_at,
            )
        )

    with sqlite3.connect(str(target_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _create_schema(connection)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM graph_relations")
            connection.execute("DELETE FROM graph_summary")
            connection.executemany(
                """
                INSERT INTO graph_relations (
                    partition_id, method_qn, symbol_id, relation_type, path_ids_json,
                    path_count, first_path_id, community_label, summary_status,
                    source_project_path, run_id, relation_payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                relation_rows,
            )
            connection.executemany(
                """
                INSERT INTO graph_summary (
                    summary_key, summary_type, partition_id, status, value_json,
                    duration_ms, skip_reason, source_project_path, run_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                summary_rows,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return target_path
