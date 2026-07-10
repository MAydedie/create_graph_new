#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from analysis.llm_partition_optimizer import (  # noqa: E402
    LLMPartitionOptimizer,
    OptimizationResult,
    plan_partition_optimization,
)
from analysis.stage3_partition_runtime import (  # noqa: E402
    build_multi_source_info,
    build_error_history,
    build_skip_history,
    build_stage3_run_id,
    clone_partition,
    prepare_partitions_for_optimizer,
    restore_optimized_partitions,
    sort_partitions,
)
from config.config import get_deepseek_settings, has_deepseek_config  # noqa: E402
from data.project_library_storage import ProjectLibraryStorage  # noqa: E402
from graph_store.sqlite_store import persist_stage3_snapshot  # noqa: E402
from segment_2_partition.cli import _build_symbol_indexes, _normalize_call_graph  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage 3 function partition optimization: stage2_output.json -> segment3_output.json",
    )
    parser.add_argument("--input", required=True, help="Path to segment2_output.json")
    parser.add_argument("--output", required=True, help="Path to segment3_output.json")
    parser.add_argument("--graph-db", default=None, help="Optional output path for graph.db")
    parser.add_argument("--force", action="store_true", default=None, help="Force LLM partition optimization")
    parser.add_argument("--threshold", type=float, default=None, help="Avg modularity threshold for optimization")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM optimization even if it would trigger")
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


def _resolve_graph_db_path(stage2_payload: Dict[str, Any], input_path: str, output_path: str, graph_db_path: str | None) -> Path:
    if graph_db_path:
        return Path(graph_db_path)
    trust_root = Path(input_path).resolve().parent
    artifact_path = str((((stage2_payload.get("artifacts") or {}).get("graph_db_path")) or "")).strip()
    if artifact_path:
        candidate = Path(artifact_path)
        if candidate.exists() and _is_path_within_root(candidate, trust_root):
            return candidate
    project_path = str((((stage2_payload.get("project") or {}).get("path")) or "")).strip()
    if project_path:
        return ProjectLibraryStorage().graph_db_path(project_path)
    return Path(output_path).resolve().parent / "graph.db"


def _load_call_graph_from_stage1(stage2_payload: Dict[str, Any], input_path: str) -> Dict[str, Set[str]]:
    stage1_path = str((((stage2_payload.get("input") or {}).get("stage1_output_path")) or "")).strip()
    if not stage1_path:
        return {}
    stage1_file = Path(stage1_path)
    trust_root = Path(input_path).resolve().parent
    if not stage1_file.exists() or not _is_path_within_root(stage1_file, trust_root):
        return {}
    stage1_payload = _load_json(str(stage1_file))
    qn_to_symbol, simple_name_to_qn = _build_symbol_indexes(stage1_payload)
    return _normalize_call_graph(stage1_payload, qn_to_symbol, simple_name_to_qn)


def _load_call_graph_from_partition_graphs(stage2_payload: Dict[str, Any]) -> Dict[str, Set[str]]:
    call_graph: Dict[str, Set[str]] = {}
    partition_graphs = stage2_payload.get("partition_call_graphs") or {}
    for payload in partition_graphs.values():
        if not isinstance(payload, dict):
            continue
        for edge in (payload.get("internal_edges") or []) + (payload.get("external_edges") or []):
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source") or "").strip()
            target = str(edge.get("target") or "").strip()
            if not source or not target:
                continue
            call_graph.setdefault(source, set()).add(target)
            call_graph.setdefault(target, set())
    return {key: set(sorted(value)) for key, value in sorted(call_graph.items())}


def _build_call_graph(stage2_payload: Dict[str, Any], input_path: str) -> Dict[str, Set[str]]:
    call_graph = _load_call_graph_from_stage1(stage2_payload, input_path)
    if call_graph:
        return call_graph
    return _load_call_graph_from_partition_graphs(stage2_payload)


def _output_summary(
    *,
    original_partitions: List[Dict[str, Any]],
    effective_partitions: List[Dict[str, Any]],
    optimized_partitions: List[Dict[str, Any]],
    optimization_history: List[Dict[str, Any]],
    plan: Dict[str, Any],
    optimization_applied: bool,
) -> Dict[str, Any]:
    return {
        "partition_count": len(effective_partitions),
        "original_partition_count": len(original_partitions),
        "optimized_partition_count": len(optimized_partitions),
        "avg_modularity": float(plan.get("avg_modularity") or 0.0),
        "optimization_triggered": bool(plan.get("should_run")),
        "optimization_applied": bool(optimization_applied),
        "trigger_mode": str(plan.get("trigger_mode") or "skip"),
        "threshold": float(plan.get("threshold") or 0.4),
        "history_count": len(optimization_history),
        "skip_reason": None if optimization_applied else str(plan.get("reason") or ""),
    }


def run_stage3(
    input_path: str,
    output_path: str,
    *,
    force: Optional[bool] = None,
    threshold: float | None = None,
    skip_llm: bool = False,
    verbose: bool = False,
    graph_db_path: str | None = None,
) -> Path:
    stage2_payload = _load_json(input_path)
    original_partitions = sort_partitions([clone_partition(item) for item in (stage2_payload.get("partitions") or [])])
    if not original_partitions:
        raise ValueError("输入文件中未找到有效 partitions")

    call_graph = _build_call_graph(stage2_payload, input_path)
    if not call_graph:
        raise ValueError("输入文件中未找到可用于阶段3优化的调用图")

    plan = plan_partition_optimization(original_partitions, threshold=threshold, force=force, skip_llm=skip_llm)
    optimization_history = build_skip_history(plan)
    optimized_partitions: List[Dict[str, Any]] = []
    effective_partitions = [clone_partition(item) for item in original_partitions]
    optimization_applied = False

    if plan["should_run"]:
        if not has_deepseek_config():
            plan = dict(plan)
            plan["should_run"] = False
            plan["reason"] = "LLM config missing; fallback to original partitions"
            plan["trigger_mode"] = "skip"
            optimization_history = build_skip_history(plan)
        else:
            try:
                project_path = str((((stage2_payload.get("project") or {}).get("path")) or "")).strip() or None
                multi_source_info = build_multi_source_info(project_path, report=None)
                settings = get_deepseek_settings()
                optimizer = LLMPartitionOptimizer(
                    api_key=str(settings.get("api_key") or ""),
                    base_url=str(settings.get("base_url") or "https://api.deepseek.com/v1"),
                    project_path=project_path,
                    report=None,
                )
                result = optimizer.optimize_partitions(
                    initial_partitions=prepare_partitions_for_optimizer(original_partitions),
                    call_graph=call_graph,
                    multi_source_info=multi_source_info,
                )
                if not isinstance(result, OptimizationResult):
                    raise TypeError("optimizer must return OptimizationResult")
                optimized_partitions = restore_optimized_partitions(result.partitions, original_partitions)
                optimization_history = [copy.deepcopy(item) for item in result.to_dict().get("optimization_history", [])]
                effective_partitions = optimized_partitions or effective_partitions
                optimization_applied = bool(optimized_partitions)
            except Exception as exc:
                plan = dict(plan)
                plan["should_run"] = False
                plan["reason"] = f"LLM optimization failed: {exc}"
                plan["trigger_mode"] = "skip"
                optimized_partitions = []
                effective_partitions = [clone_partition(item) for item in original_partitions]
                optimization_history = build_error_history(plan, exc)

    resolved_graph_db_path = _resolve_graph_db_path(stage2_payload, input_path, output_path, graph_db_path)
    project_path = str((((stage2_payload.get("project") or {}).get("path")) or "")).strip() or None
    stable_run_token = ""
    if not optimization_applied:
        stable_run_token = json.dumps(
            {
                "input_path": str(Path(input_path).resolve()),
                "graph_db_path": str(resolved_graph_db_path.resolve()),
                "trigger_mode": str(plan.get("trigger_mode") or "skip"),
                "threshold": float(plan.get("threshold") or 0.4),
                "skip_llm": bool(skip_llm),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    optimization_run_id = build_stage3_run_id(project_path or input_path, stable_token=stable_run_token)
    persist_stage3_snapshot(
        db_path=str(resolved_graph_db_path),
        partitions_optimized=optimized_partitions,
        optimization_history=optimization_history,
        source_project_path=project_path,
        optimization_run_id=optimization_run_id,
        trigger_mode=str(plan.get("trigger_mode") or "skip"),
        threshold=float(plan.get("threshold") or 0.4),
        was_optimized=optimization_applied,
    )

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    stage3_db_copy_path = output_file.parent / "graph.db"
    copied_db_path: Optional[Path] = None
    try:
        if resolved_graph_db_path.resolve() == stage3_db_copy_path.resolve():
            copied_db_path = stage3_db_copy_path
        else:
            if not resolved_graph_db_path.exists():
                resolved_graph_db_path.parent.mkdir(parents=True, exist_ok=True)
                resolved_graph_db_path.touch(exist_ok=True)
            shutil.copy2(str(resolved_graph_db_path), str(stage3_db_copy_path))
            copied_db_path = stage3_db_copy_path
    except OSError as exc:
        print(f"[segment_3_function_partition] graph.db copy failed: {exc} (src={resolved_graph_db_path}, dst={stage3_db_copy_path})", flush=True)
        copied_db_path = None

    output_payload = copy.deepcopy(stage2_payload)
    output_payload["schema_version"] = "stage3.v1"
    output_payload["input"] = {
        **copy.deepcopy(stage2_payload.get("input") or {}),
        "stage2_output_path": str(Path(input_path).resolve()).replace("\\", "/"),
        "force": bool(force),
        "threshold": float(plan.get("threshold") or 0.4),
        "skip_llm": bool(skip_llm),
    }
    output_payload["artifacts"] = {
        **copy.deepcopy(stage2_payload.get("artifacts") or {}),
        "graph_db_path": str(resolved_graph_db_path).replace("\\", "/"),
        "stage3_graph_db_copy": (str(copied_db_path).replace("\\", "/") if copied_db_path else None),
    }
    output_payload["partitions_original"] = original_partitions
    output_payload["partitions_optimized"] = optimized_partitions
    output_payload["partitions"] = effective_partitions
    output_payload["optimization_history"] = optimization_history
    output_payload["optimization"] = {
        "run_id": optimization_run_id,
        "trigger": plan,
        "applied": optimization_applied,
        "effective_partition_source": "optimized" if optimization_applied else "original",
    }
    output_payload["summary"] = _output_summary(
        original_partitions=original_partitions,
        effective_partitions=effective_partitions,
        optimized_partitions=optimized_partitions,
        optimization_history=optimization_history,
        plan=plan,
        optimization_applied=optimization_applied,
    )

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(output_payload, handle, indent=2, ensure_ascii=False, sort_keys=True)

    if verbose:
        print("[segment_3_function_partition] 输出完成")
        print(f"  output: {output_file}")
        print(f"  graph_db: {resolved_graph_db_path}")
        if copied_db_path:
            print(f"  graph_db_copy: {copied_db_path}")
        print(f"  optimization_triggered: {output_payload['summary']['optimization_triggered']}")
        print(f"  optimization_applied: {output_payload['summary']['optimization_applied']}")
        print(f"  optimized_partition_count: {output_payload['summary']['optimized_partition_count']}")

    return output_file


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        run_stage3(
            input_path=args.input,
            output_path=args.output,
            force=args.force,
            threshold=args.threshold,
            skip_llm=bool(args.skip_llm),
            verbose=bool(args.verbose),
            graph_db_path=args.graph_db,
        )
        return 0
    except Exception as exc:
        print(f"[segment_3_function_partition] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
