#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from analysis.community_semantics_runtime import (  # noqa: E402
    build_history_entry,
    build_llm_helper,
    build_placeholder_summary,
    build_stage4_run_id,
    clone_partition,
    plan_community_semantics,
    summarize_partition_with_llm,
)
from analysis.stage3_partition_runtime import sort_partitions  # noqa: E402
from config.config import get_deepseek_settings, has_deepseek_config  # noqa: E402
from data.project_library_storage import ProjectLibraryStorage  # noqa: E402
from graph_store.sqlite_store import persist_stage4_snapshot  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage 4 community semantics: stage3_output.json -> segment4_output.json"
    )
    parser.add_argument("--input", required=True, help="Path to segment3_output.json")
    parser.add_argument("--output", required=True, help="Path to segment4_output.json")
    parser.add_argument("--graph-db", default=None, help="Optional output path for graph.db")
    parser.add_argument("--force", action="store_true", default=None, help="Force community LLM summarization")
    parser.add_argument("--max-communities", type=int, default=None, help="Limit the number of communities summarized")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM summarization and emit placeholders")
    parser.add_argument("--verbose", action="store_true", help="Print extra progress logs")
    return parser


def _load_json(path: str) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("输入 JSON 顶层必须是对象")
    return payload


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


def _resolve_source_graph_db_path(stage3_payload: Dict[str, Any], input_path: str) -> Path:
    trust_roots = _candidate_trust_roots(input_path)
    artifacts = stage3_payload.get("artifacts") or {}
    for key in ("stage3_graph_db_copy", "graph_db_path"):
        artifact_path = str(artifacts.get(key) or "").strip()
        if not artifact_path:
            continue
        candidate = Path(artifact_path)
        if candidate.exists() and _is_path_within_any_root(candidate, trust_roots):
            return candidate
    project_path = str((((stage3_payload.get("project") or {}).get("path")) or "")).strip()
    if project_path:
        candidate = ProjectLibraryStorage().graph_db_path(project_path)
        if candidate.exists():
            return candidate
    raise FileNotFoundError("未找到可复用的 stage3 graph.db，请显式传入 --graph-db 或确保 stage3 artifact 存在")


def _prepare_target_graph_db(source_db_path: Path, output_path: str, graph_db_path: str | None) -> Tuple[Path, Optional[Path]]:
    if graph_db_path:
        explicit_path = Path(graph_db_path)
        explicit_path.parent.mkdir(parents=True, exist_ok=True)
        if source_db_path.resolve() == explicit_path.resolve():
            return explicit_path, None
        if source_db_path.exists() and not explicit_path.exists():
            shutil.copy2(str(source_db_path), str(explicit_path))
        return explicit_path, explicit_path if explicit_path.exists() else None

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    target_db_path = output_file.parent / "graph.db"
    if source_db_path.resolve() == target_db_path.resolve():
        return target_db_path, target_db_path
    shutil.copy2(str(source_db_path), str(target_db_path))
    return target_db_path, target_db_path


def _extract_stage1_symbols(stage1_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    ir_payload = stage1_payload.get("ir") or {}
    if isinstance(ir_payload, dict) and isinstance(ir_payload.get("symbols"), list):
        return [item for item in ir_payload.get("symbols") or [] if isinstance(item, dict)]
    return [item for item in stage1_payload.get("symbols") or [] if isinstance(item, dict)]


def _load_stage1_payload(stage3_payload: Dict[str, Any], input_path: str) -> Dict[str, Any]:
    stage1_path = str((((stage3_payload.get("input") or {}).get("stage1_output_path")) or "")).strip()
    if not stage1_path:
        return {}
    stage1_file = Path(stage1_path)
    trust_roots = _candidate_trust_roots(input_path)
    if not stage1_file.exists() or not _is_path_within_any_root(stage1_file, trust_roots):
        return {}
    return _load_json(str(stage1_file))


def _build_symbol_indexes(stage1_payload: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    by_symbol_id: Dict[str, Dict[str, Any]] = {}
    by_qualified_name: Dict[str, Dict[str, Any]] = {}
    for symbol in _extract_stage1_symbols(stage1_payload):
        symbol_id = str(symbol.get("id") or "").strip()
        qualified_name = str(symbol.get("qualified_name") or "").strip()
        if symbol_id:
            by_symbol_id[symbol_id] = symbol
        if qualified_name:
            by_qualified_name[qualified_name] = symbol
    return by_symbol_id, by_qualified_name


def _attach_symbol_context(
    partition: Dict[str, Any],
    by_symbol_id: Dict[str, Dict[str, Any]],
    by_qualified_name: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    partition_copy = clone_partition(partition)
    member_symbols = partition_copy.get("member_symbols") or []
    resolved_symbols: List[Dict[str, Any]] = []
    for member in member_symbols:
        if not isinstance(member, dict):
            continue
        symbol_id = str(member.get("symbol_id") or "").strip()
        qualified_name = str(member.get("qualified_name") or "").strip()
        symbol = by_symbol_id.get(symbol_id) or by_qualified_name.get(qualified_name)
        if symbol:
            resolved_symbols.append(copy.deepcopy(symbol))
    if not resolved_symbols:
        for key in partition_copy.get("qualified_methods") or partition_copy.get("methods") or []:
            normalized = str(key).strip()
            symbol = by_symbol_id.get(normalized) or by_qualified_name.get(normalized)
            if symbol:
                resolved_symbols.append(copy.deepcopy(symbol))
    partition_copy["resolved_symbols"] = resolved_symbols

    file_counter = Counter()
    for symbol in resolved_symbols:
        file_path = str(symbol.get("file_path") or "").strip()
        if file_path:
            file_counter[file_path.replace("\\", "/")] += 1
    partition_copy["top_files"] = [path for path, _ in file_counter.most_common(5)]
    return partition_copy


def _build_partition_maps(partitions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        str(partition.get("partition_id") or ""): partition
        for partition in partitions
        if isinstance(partition, dict) and partition.get("partition_id")
    }


def _build_neighbor_map(stage3_payload: Dict[str, Any], partition_map: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    neighbors: Dict[str, Counter[str]] = {}
    for edge in stage3_payload.get("partition_topology") or []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source_partition") or "").strip()
        target = str(edge.get("target_partition") or "").strip()
        if not source or not target or source == target:
            continue
        edge_count = int(edge.get("edge_count") or 0)
        if edge_count <= 0:
            continue
        neighbors.setdefault(source, Counter())[target] += edge_count
        neighbors.setdefault(target, Counter())[source] += edge_count
    result: Dict[str, List[str]] = {}
    for partition_id, counter in neighbors.items():
        top_neighbors = []
        for neighbor_id, _ in counter.most_common(3):
            neighbor = partition_map.get(neighbor_id) or {}
            top_neighbors.append(str(neighbor.get("name") or neighbor_id))
        result[partition_id] = top_neighbors
    return result


def _build_partition_call_context(stage3_payload: Dict[str, Any], partition: Dict[str, Any]) -> Dict[str, Any]:
    partition_id = str(partition.get("partition_id") or "")
    call_graph_payload = ((stage3_payload.get("partition_call_graphs") or {}).get(partition_id) or {})
    internal_edges = [item for item in (call_graph_payload.get("internal_edges") or []) if isinstance(item, dict)]
    external_edges = [item for item in (call_graph_payload.get("external_edges") or []) if isinstance(item, dict)]
    methods = set(str(item).strip() for item in (partition.get("qualified_methods") or partition.get("methods") or []) if str(item).strip())

    incoming_internal = Counter()
    outgoing_internal = Counter()
    incoming_external = Counter()
    external_callers = Counter()
    external_callees = Counter()

    for edge in internal_edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if source:
            outgoing_internal[source] += 1
        if target:
            incoming_internal[target] += 1

    for edge in external_edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if source in methods and target:
            external_callees[target] += 1
        elif target in methods and source:
            external_callers[source] += 1
            incoming_external[target] += 1

    entry_points = sorted(
        [method for method in methods if incoming_internal.get(method, 0) == 0 or incoming_external.get(method, 0) > 0]
    )[:3]
    if not entry_points:
        entry_points = sorted(methods)[:3]

    return {
        "entry_points": entry_points,
        "top_callers": [item for item, _ in external_callers.most_common(3)],
        "top_callees": [item for item, _ in external_callees.most_common(3)],
        "total_edges": int((call_graph_payload.get("statistics") or {}).get("total_edges") or 0),
    }


def _build_community_context(
    partition: Dict[str, Any],
    stage3_payload: Dict[str, Any],
    top_dependencies: List[str],
) -> Dict[str, Any]:
    call_context = _build_partition_call_context(stage3_payload, partition)
    methods = [
        {
            "symbol_id": str(item.get("id") or item.get("symbol_id") or "").strip(),
            "qualified_name": str(item.get("qualified_name") or "").strip(),
            "kind": str(item.get("kind") or "").strip(),
            "file_path": str(item.get("file_path") or "").strip().replace("\\", "/"),
            "signature": str(item.get("signature") or "").strip(),
        }
        for item in (partition.get("resolved_symbols") or [])
        if isinstance(item, dict)
    ]
    return {
        "partition_id": partition.get("partition_id"),
        "name": partition.get("name") or partition.get("partition_id"),
        "method_count": len(methods) or int(partition.get("size") or 0),
        "modularity": float(partition.get("modularity") or 0.0),
        "cohesion_score": float(partition.get("cohesion_score") or 0.0),
        "entry_points": call_context["entry_points"],
        "top_callers": call_context["top_callers"],
        "top_callees": call_context["top_callees"],
        "top_files": partition.get("top_files") or [],
        "top_dependencies": top_dependencies,
        "methods": methods,
    }


def _merge_semantic_payload(partition: Dict[str, Any], semantic_payload: Dict[str, Any], model: str) -> Dict[str, Any]:
    partition_copy = clone_partition(partition)
    label = str(semantic_payload.get("label") or partition_copy.get("name") or partition_copy.get("partition_id") or "").strip()
    raw_key_concepts = semantic_payload.get("key_concepts")
    raw_top_files = semantic_payload.get("top_files")
    raw_top_dependencies = semantic_payload.get("top_dependencies")
    key_concepts = [str(item).strip() for item in (raw_key_concepts if isinstance(raw_key_concepts, list) else []) if str(item).strip()]
    top_files = [
        str(item).strip()
        for item in (raw_top_files if isinstance(raw_top_files, list) else (partition_copy.get("top_files") or []))
        if str(item).strip()
    ]
    top_dependencies = [
        str(item).strip()
        for item in (raw_top_dependencies if isinstance(raw_top_dependencies, list) else (partition_copy.get("top_dependencies") or []))
        if str(item).strip()
    ]
    partition_copy.update(
        {
            "label": label[:80],
            "description": str(semantic_payload.get("description") or "").strip(),
            "functional_domain": str(semantic_payload.get("functional_domain") or "").strip(),
            "key_concepts": key_concepts,
            "top_files": top_files,
            "top_dependencies": top_dependencies,
            "summary_status": "completed",
            "skip_reason": None,
            "model": model,
            "duration_ms": int(semantic_payload.get("duration_ms") or 0),
        }
    )
    return partition_copy


def _output_summary(
    *,
    effective_partitions: List[Dict[str, Any]],
    selected_partitions: List[Dict[str, Any]],
    community_summaries: List[Dict[str, Any]],
    community_summary_history: List[Dict[str, Any]],
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    status_counts = Counter(str(item.get("summary_status") or "unknown") for item in community_summaries)
    applied = status_counts.get("completed", 0) > 0
    return {
        "partition_count": len(effective_partitions),
        "selected_community_count": len(selected_partitions),
        "summary_count": len(community_summaries),
        "history_count": len(community_summary_history),
        "avg_modularity": float(plan.get("avg_modularity") or 0.0),
        "community_llm_triggered": bool(plan.get("should_run")),
        "community_llm_applied": applied,
        "trigger_mode": str(plan.get("trigger_mode") or "skip"),
        "threshold": float(plan.get("threshold") or 0.4),
        "skipped_count": int(status_counts.get("skipped", 0)),
        "error_count": int(status_counts.get("error", 0)),
        "completed_count": int(status_counts.get("completed", 0)),
        "skip_reason": None if applied else str(plan.get("reason") or ""),
    }


def run_stage4(
    input_path: str,
    output_path: str,
    *,
    force: Optional[bool] = None,
    max_communities: Optional[int] = None,
    skip_llm: bool = False,
    verbose: bool = False,
    graph_db_path: str | None = None,
) -> Path:
    stage3_payload = _load_json(input_path)
    effective_partitions = sort_partitions([clone_partition(item) for item in (stage3_payload.get("partitions") or [])])
    if not effective_partitions:
        raise ValueError("输入文件中未找到有效 partitions")

    selected_partitions = effective_partitions[: max_communities or len(effective_partitions)]
    plan = plan_community_semantics(effective_partitions, force=force, skip_llm=skip_llm)
    project_path_raw = str((((stage3_payload.get("project") or {}).get("path")) or "")).strip()
    project_path = os.path.normpath(project_path_raw) if project_path_raw else None

    source_graph_db_path = _resolve_source_graph_db_path(stage3_payload, input_path)
    resolved_graph_db_path, copied_db_path = _prepare_target_graph_db(source_graph_db_path, output_path, graph_db_path)

    stage1_payload = _load_stage1_payload(stage3_payload, input_path)
    by_symbol_id, by_qualified_name = _build_symbol_indexes(stage1_payload)
    partition_map = _build_partition_maps(effective_partitions)
    neighbor_map = _build_neighbor_map(stage3_payload, partition_map)
    selected_partitions = [
        _attach_symbol_context(partition, by_symbol_id, by_qualified_name)
        for partition in selected_partitions
    ]
    for partition in selected_partitions:
        partition["top_dependencies"] = neighbor_map.get(str(partition.get("partition_id") or ""), [])

    stable_run_token = ""
    if not plan["should_run"]:
        stable_run_token = json.dumps(
            {
                "input_path": str(Path(input_path).resolve()),
                "graph_db_path": str(resolved_graph_db_path.resolve()),
                "trigger_mode": str(plan.get("trigger_mode") or "skip"),
                "threshold": float(plan.get("threshold") or 0.4),
                "skip_llm": bool(skip_llm),
                "max_communities": int(max_communities or 0),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    community_run_id = build_stage4_run_id(project_path or input_path, stable_token=stable_run_token)

    community_summaries: List[Dict[str, Any]] = []
    community_summary_history: List[Dict[str, Any]] = []
    model_name = str(get_deepseek_settings().get("model") or "").strip()

    if not plan["should_run"]:
        for partition in selected_partitions:
            placeholder = build_placeholder_summary(
                partition,
                status="skipped",
                reason=str(plan.get("reason") or "stage4 skipped"),
            )
            community_summaries.append(placeholder)
            community_summary_history.append(
                build_history_entry(
                    str(partition.get("partition_id") or "unknown"),
                    status="skipped",
                    reason=str(plan.get("reason") or "stage4 skipped"),
                    trigger_mode=str(plan.get("trigger_mode") or "skip"),
                    threshold=float(plan.get("threshold") or 0.4),
                    details={"status": "skipped", "partition_size": int(partition.get("size") or 0)},
                )
            )
    elif not has_deepseek_config():
        plan = dict(plan)
        plan["reason"] = "LLM config missing; placeholder summaries emitted"
        for partition in selected_partitions:
            placeholder = build_placeholder_summary(
                partition,
                status="error",
                reason=str(plan.get("reason") or "LLM config missing"),
                model=model_name,
            )
            community_summaries.append(placeholder)
            community_summary_history.append(
                build_history_entry(
                    str(partition.get("partition_id") or "unknown"),
                    status="error",
                    reason=str(plan.get("reason") or "LLM config missing"),
                    trigger_mode=str(plan.get("trigger_mode") or "force"),
                    threshold=float(plan.get("threshold") or 0.4),
                    model=model_name,
                    details={"status": "error", "error": "missing_llm_config"},
                )
            )
    else:
        helper = build_llm_helper(get_deepseek_settings())
        model_name = helper.config.model
        for partition in selected_partitions:
            partition_id = str(partition.get("partition_id") or "unknown")
            try:
                semantic_payload = summarize_partition_with_llm(
                    helper,
                    _build_community_context(
                        partition,
                        stage3_payload,
                        neighbor_map.get(partition_id, []),
                    ),
                )
                merged_summary = _merge_semantic_payload(partition, semantic_payload, model_name)
                community_summaries.append(merged_summary)
                community_summary_history.append(
                    build_history_entry(
                        partition_id,
                        status="completed",
                        reason="community summary generated",
                        trigger_mode=str(plan.get("trigger_mode") or "threshold"),
                        threshold=float(plan.get("threshold") or 0.4),
                        model=model_name,
                        duration_ms=int(merged_summary.get("duration_ms") or 0),
                        details={
                            "status": "completed",
                            "key_concepts_count": len(merged_summary.get("key_concepts") or []),
                        },
                    )
                )
            except Exception as exc:
                placeholder = build_placeholder_summary(
                    partition,
                    status="error",
                    reason=f"LLM summarization failed: {exc}",
                    model=model_name,
                )
                community_summaries.append(placeholder)
                community_summary_history.append(
                    build_history_entry(
                        partition_id,
                        status="error",
                        reason=f"LLM summarization failed: {exc}",
                        trigger_mode=str(plan.get("trigger_mode") or "threshold"),
                        threshold=float(plan.get("threshold") or 0.4),
                        model=model_name,
                        details={"status": "error", "error": str(exc)},
                    )
                )

    persist_stage4_snapshot(
        db_path=str(resolved_graph_db_path),
        community_summaries=community_summaries,
        community_summary_history=community_summary_history,
        source_project_path=project_path,
        community_run_id=community_run_id,
        trigger_mode=str(plan.get("trigger_mode") or "skip"),
        threshold=float(plan.get("threshold") or 0.4),
    )

    canonical_graph_db_path: Optional[Path] = None
    if project_path:
        canonical_graph_db_path = ProjectLibraryStorage().graph_db_path(project_path)
        if canonical_graph_db_path.resolve() != resolved_graph_db_path.resolve():
            persist_stage4_snapshot(
                db_path=str(canonical_graph_db_path),
                community_summaries=community_summaries,
                community_summary_history=community_summary_history,
                source_project_path=project_path,
                community_run_id=community_run_id,
                trigger_mode=str(plan.get("trigger_mode") or "skip"),
                threshold=float(plan.get("threshold") or 0.4),
            )

    output_payload = copy.deepcopy(stage3_payload)
    output_payload["schema_version"] = "stage4.v1"
    output_payload["input"] = {
        **copy.deepcopy(stage3_payload.get("input") or {}),
        "stage3_output_path": str(Path(input_path).resolve()).replace("\\", "/"),
        "force": bool(force),
        "max_communities": int(max_communities) if max_communities else None,
        "skip_llm": bool(skip_llm),
    }
    output_payload["artifacts"] = {
        **copy.deepcopy(stage3_payload.get("artifacts") or {}),
        "source_graph_db_path": str(source_graph_db_path).replace("\\", "/"),
        "graph_db_path": str(resolved_graph_db_path).replace("\\", "/"),
        "stage4_graph_db_copy": (str(copied_db_path).replace("\\", "/") if copied_db_path else None),
        "canonical_graph_db_path": (str(canonical_graph_db_path).replace("\\", "/") if canonical_graph_db_path else None),
    }
    output_payload["community_summaries"] = community_summaries
    output_payload["community_summary_history"] = community_summary_history
    output_payload["community_semantics"] = {
        "run_id": community_run_id,
        "trigger": plan,
        "applied": any(item.get("summary_status") == "completed" for item in community_summaries),
        "effective_summary_source": "llm"
        if any(item.get("summary_status") == "completed" for item in community_summaries)
        else "placeholder",
    }
    output_payload["summary"] = {
        **copy.deepcopy(stage3_payload.get("summary") or {}),
        **_output_summary(
            effective_partitions=effective_partitions,
            selected_partitions=selected_partitions,
            community_summaries=community_summaries,
            community_summary_history=community_summary_history,
            plan=plan,
        ),
    }

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(output_payload, handle, indent=2, ensure_ascii=False, sort_keys=True)

    if verbose:
        print("[segment_4_community_semantics] 输出完成")
        print(f"  output: {output_file}")
        print(f"  source_graph_db: {source_graph_db_path}")
        print(f"  graph_db: {resolved_graph_db_path}")
        if copied_db_path:
            print(f"  graph_db_copy: {copied_db_path}")
        print(f"  community_llm_triggered: {output_payload['summary']['community_llm_triggered']}")
        print(f"  community_llm_applied: {output_payload['summary']['community_llm_applied']}")
        print(f"  summary_count: {output_payload['summary']['summary_count']}")

    return output_file


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        run_stage4(
            input_path=args.input,
            output_path=args.output,
            force=args.force,
            max_communities=args.max_communities,
            skip_llm=bool(args.skip_llm),
            verbose=bool(args.verbose),
            graph_db_path=args.graph_db,
        )
        return 0
    except Exception as exc:
        print(f"[segment_4_community_semantics] ERROR: {exc}", file=sys.stderr)
        return 1
