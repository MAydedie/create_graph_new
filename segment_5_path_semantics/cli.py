#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from analysis.code_model import ClassInfo, MethodInfo, Parameter, ProjectAnalysisReport, SourceLocation  # noqa: E402
from analysis.community_semantics_runtime import build_llm_helper  # noqa: E402
from analysis.function_call_hypergraph import FunctionCallHypergraphGenerator  # noqa: E402
from analysis.function_node_enhancer import enhance_hypergraph_with_function_nodes  # noqa: E402
from analysis.method_function_profile_builder import MethodFunctionProfileBuilder  # noqa: E402
from analysis.path_ir import PathIR  # noqa: E402
from analysis.path_level_analyzer import generate_path_level_cfg, generate_path_level_dfg  # noqa: E402
from analysis.path_semantic_analyzer import analyze_path_semantics  # noqa: E402
from analysis.stage3_partition_runtime import build_stage3_run_id, sort_partitions  # noqa: E402
from app.services.analysis_service import _extract_lightweight_partition_paths, _extract_structural_partition_paths  # noqa: E402
from config.config import get_deepseek_settings, has_deepseek_config  # noqa: E402
from data.project_library_storage import ProjectLibraryStorage  # noqa: E402
from graph_store.extractors.from_paths import (  # noqa: E402
    extract_path_cfg_records,
    extract_path_dfg_records,
    extract_path_link_records,
    extract_path_reverse_index_records,
)
from graph_store.sqlite_store import persist_stage5_snapshot  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage 5 path semantics: stage4_output.json -> segment5_output.json"
    )
    parser.add_argument("--input", required=True, help="Path to segment4_output.json")
    parser.add_argument("--stage1", default=None, help="Optional explicit path to segment1_output.json")
    parser.add_argument("--output", required=True, help="Path to segment5_output.json")
    parser.add_argument("--graph-db", default=None, help="Optional output path for graph.db")
    parser.add_argument("--max-paths", type=int, default=10, help="Maximum paths analyzed per partition")
    parser.add_argument("--skip-llm-explain", action="store_true", help="Skip CFG/DFG explanation")
    parser.add_argument("--force-llm-explain", action="store_true", help="Force CFG/DFG explanation")
    parser.add_argument("--skip-cfg-dfg", action="store_true", help="Skip CFG/DFG generation")
    parser.add_argument("--skip-llm-explain-env", action="store_true", help="Ignore FH_ENABLE_CFG_DFG_LLM_EXPLAIN")
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


def _resolve_source_graph_db_path(stage4_payload: Dict[str, Any], input_path: str) -> Path:
    trust_roots = _candidate_trust_roots(input_path)
    artifacts = stage4_payload.get("artifacts") or {}
    for key in ("stage4_graph_db_copy", "graph_db_path"):
        artifact_path = str(artifacts.get(key) or "").strip()
        if not artifact_path:
            continue
        candidate = Path(artifact_path)
        if candidate.exists() and candidate.is_file() and _is_path_within_any_root(candidate, trust_roots):
            try:
                if candidate.open("rb").read(16) == b"SQLite format 3\x00":
                    return candidate
            except OSError:
                continue
    project_path = str((((stage4_payload.get("project") or {}).get("path")) or "")).strip()
    if project_path:
        candidate = ProjectLibraryStorage().graph_db_path(project_path)
        if candidate.exists() and candidate.is_file():
            try:
                if candidate.open("rb").read(16) == b"SQLite format 3\x00":
                    return candidate
            except OSError:
                pass
    raise FileNotFoundError("未找到可复用的 stage4 graph.db，请显式传入 --graph-db 或确保 stage4 artifact 存在")


def _prepare_target_graph_db(source_db_path: Path, output_path: str, graph_db_path: str | None) -> Tuple[Path, Optional[Path]]:
    try:
        if source_db_path.open("rb").read(16) != b"SQLite format 3\x00":
            raise ValueError(f"无效 graph.db 源文件: {source_db_path}")
    except OSError as exc:
        raise ValueError(f"无法读取 graph.db 源文件: {source_db_path}") from exc

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


def _load_stage3_payload_from_stage4(stage4_payload: Dict[str, Any], input_path: str) -> Dict[str, Any]:
    stage3_path = str((((stage4_payload.get("input") or {}).get("stage3_output_path")) or "")).strip()
    if not stage3_path:
        return {}
    stage3_file = Path(stage3_path)
    trust_roots = _candidate_trust_roots(input_path)
    if not stage3_file.exists() or not _is_path_within_any_root(stage3_file, trust_roots):
        return {}
    return _load_json(str(stage3_file))


def _extract_stage1_symbols(stage1_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    ir_payload = stage1_payload.get("ir") or {}
    if isinstance(ir_payload, dict) and isinstance(ir_payload.get("symbols"), list):
        return [item for item in ir_payload.get("symbols") or [] if isinstance(item, dict)]
    return [item for item in stage1_payload.get("symbols") or [] if isinstance(item, dict)]


def _resolve_stage1_payload(explicit_stage1: Optional[str], stage4_payload: Dict[str, Any], input_path: str) -> Tuple[Dict[str, Any], str]:
    if explicit_stage1:
        resolved = str(Path(explicit_stage1).resolve()).replace("\\", "/")
        return _load_json(explicit_stage1), resolved

    stage3_payload = _load_stage3_payload_from_stage4(stage4_payload, input_path)
    stage1_path = str((((stage3_payload.get("input") or {}).get("stage1_output_path")) or "")).strip()
    if not stage1_path:
        raise FileNotFoundError("未能从 stage4 -> stage3 回溯 stage1_output.json，请显式传入 --stage1")
    stage1_file = Path(stage1_path)
    trust_roots = _candidate_trust_roots(input_path)
    if not stage1_file.exists() or not _is_path_within_any_root(stage1_file, trust_roots):
        raise FileNotFoundError("回溯得到的 stage1_output.json 不可用，请显式传入 --stage1")
    return _load_json(str(stage1_file)), str(stage1_file.resolve()).replace("\\", "/")


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


def _build_report_from_stage1(stage1_payload: Dict[str, Any]) -> ProjectAnalysisReport:
    project = stage1_payload.get("project") or {}
    report = ProjectAnalysisReport(
        project_name=str(project.get("name") or "unknown_project"),
        project_path=str(project.get("path") or "").strip(),
        analysis_timestamp="stage5-rehydrated",
    )

    for symbol in _extract_stage1_symbols(stage1_payload):
        qualified_name = str(symbol.get("qualified_name") or "").strip()
        if not qualified_name:
            continue
        source_location = SourceLocation(
            file_path=str(symbol.get("file_path") or "").replace("\\", "/"),
            line_start=int(symbol.get("line_start") or 0),
            line_end=int(symbol.get("line_end") or 0),
        )
        method_info = MethodInfo(
            name=str(symbol.get("name") or qualified_name.split(".")[-1]).strip(),
            class_name="",
            signature=str(symbol.get("signature") or qualified_name).strip(),
            return_type=str(symbol.get("return_type") or "Any").strip() or "Any",
            parameters=[
                Parameter(
                    name=str(param.get("name") or "arg").strip(),
                    param_type=str(param.get("type") or "Any").strip() or "Any",
                    default_value=(str(param.get("default_value")) if param.get("default_value") not in {None, ""} else None),
                    position=int(param.get("position") or 0),
                )
                for param in (symbol.get("parameters") or [])
                if isinstance(param, dict)
            ],
            decorators=[str(item).strip() for item in (symbol.get("decorators") or []) if str(item).strip()],
            docstring=(str(symbol.get("docstring")) if symbol.get("docstring") not in {None, ""} else None),
            source_code=(str(symbol.get("source_code")) if symbol.get("source_code") not in {None, ""} else None),
            source_location=source_location,
            cyclomatic_complexity=int(((symbol.get("metadata") or {}).get("cyclomatic_complexity")) or 1),
            lines_of_code=int(((symbol.get("metadata") or {}).get("lines_of_code")) or 0),
        )

        owner = str(symbol.get("parent_class") or symbol.get("owner_name") or "").strip()
        if not owner and "." in qualified_name:
            owner = qualified_name.rsplit(".", 1)[0]
        if owner:
            method_info.class_name = owner
            class_info = report.classes.get(owner)
            if class_info is None:
                class_info = ClassInfo(name=owner.split(".")[-1], full_name=owner, source_location=source_location)
                report.add_class(class_info)
            class_info.methods[method_info.name] = method_info
        else:
            report.functions.append(method_info)

    return report


def _build_call_graph(stage1_payload: Dict[str, Any]) -> Dict[str, Set[str]]:
    adjacency = ((stage1_payload.get("call_graph") or {}).get("adjacency") or {})
    return {
        str(caller).strip(): {str(callee).strip() for callee in (callees or []) if str(callee).strip()}
        for caller, callees in adjacency.items()
        if str(caller).strip()
    }


def _resolve_partition_methods(partition: Dict[str, Any]) -> List[str]:
    qualified_methods = [str(item).strip() for item in (partition.get("qualified_methods") or []) if str(item).strip()]
    if qualified_methods:
        return qualified_methods
    members = [
        str(item.get("qualified_name") or item.get("symbol_id") or "").strip()
        for item in (partition.get("member_symbols") or [])
        if isinstance(item, dict)
    ]
    members = [item for item in members if item]
    if members:
        return sorted(dict.fromkeys(members))
    return [str(item).strip() for item in (partition.get("methods") or []) if str(item).strip()]


def _build_partition_local_graph(
    partition: Dict[str, Any],
    stage4_payload: Dict[str, Any],
    stage1_call_graph: Dict[str, Set[str]],
) -> Tuple[Dict[str, Set[str]], Set[str], Set[str]]:
    methods = _resolve_partition_methods(partition)
    method_set = set(methods)
    partition_id = str(partition.get("partition_id") or "")
    call_graph_payload = ((stage4_payload.get("partition_call_graphs") or {}).get(partition_id) or {})
    adjacency: Dict[str, Set[str]] = {method: set() for method in methods}
    external_incoming: Set[str] = set()

    internal_edges = [item for item in (call_graph_payload.get("internal_edges") or []) if isinstance(item, dict)]
    if internal_edges:
        for edge in internal_edges:
            source = str(edge.get("source") or "").strip()
            target = str(edge.get("target") or "").strip()
            if source in method_set and target in method_set:
                adjacency.setdefault(source, set()).add(target)
                adjacency.setdefault(target, set())
    else:
        for source, targets in stage1_call_graph.items():
            if source not in method_set:
                continue
            for target in targets:
                if target in method_set:
                    adjacency.setdefault(source, set()).add(target)
                    adjacency.setdefault(target, set())

    for edge in (call_graph_payload.get("external_edges") or []):
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if target in method_set and source not in method_set:
            external_incoming.add(target)

    return adjacency, method_set, external_incoming


def _build_partition_entry_points(methods: Iterable[str], adjacency: Dict[str, Set[str]], external_incoming: Set[str]) -> List[Dict[str, Any]]:
    method_list = sorted(dict.fromkeys(str(item).strip() for item in methods if str(item).strip()))
    indegree = {method: 0 for method in method_list}
    for targets in adjacency.values():
        for target in targets:
            if target in indegree:
                indegree[target] += 1
    entries = [method for method in method_list if indegree.get(method, 0) == 0 or method in external_incoming]
    if not entries:
        entries = method_list[:]
    return [{"method_signature": method} for method in sorted(dict.fromkeys(entries))]


def _build_partition_call_graph_payload(adjacency: Dict[str, Set[str]], methods: Iterable[str]) -> Dict[str, Any]:
    method_list = sorted(dict.fromkeys(str(item).strip() for item in methods if str(item).strip()))
    return {
        "nodes": [{"id": method} for method in method_list],
        "edges": [
            {"source": source, "target": target}
            for source in sorted(adjacency)
            for target in sorted(adjacency.get(source, set()))
        ],
    }


def _build_partition_fqns(methods: Iterable[str]) -> List[Dict[str, Any]]:
    fqns: List[Dict[str, Any]] = []
    for method in sorted(dict.fromkeys(str(item).strip() for item in methods if str(item).strip())):
        raw_segment_count = len([part for part in method.split(".") if part])
        fqns.append(
            {
                "method_signature": method,
                "fqn": method,
                "origin": "internal",
                "segment_count": max(4, raw_segment_count),
            }
        )
    return fqns


def _canonical_partition_path_candidates(
    paths_map: Dict[str, Any],
    analysis_payload: Dict[str, Any],
    *,
    max_paths: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Stage5 canonical multi-hop path selection.

    Goal: prefer real multi-hop paths from the enhancer-produced paths_map over
    lightweight single-node fallback. Single-node filler paths from
    paths_map are dropped at the canonical stage (they are not user-requested
    behaviour), and we ignore the strict 4-segment / FQMN gates used in
    _extract_structural_partition_paths so segment-aware scoring from the main
    pipeline does not push JUnitGenie-style partitions back to fallback.
    """

    candidate_paths: List[Dict[str, Any]] = []
    seen_paths: Set[Tuple[str, ...]] = set()
    for leaf_node, paths in (paths_map or {}).items():
        for path_index, path in enumerate(paths or []):
            normalized_path = [str(item).strip() for item in (path or []) if str(item).strip()]
            if len(normalized_path) < 2:
                continue
            unique_methods = list(dict.fromkeys(normalized_path))
            if len(unique_methods) < 2:
                continue
            key = tuple(unique_methods)
            if key in seen_paths:
                continue
            seen_paths.add(key)
            candidate_paths.append(
                {
                    "leaf_node": str(leaf_node or unique_methods[-1]),
                    "path_index": path_index,
                    "path": unique_methods,
                    "function_chain": unique_methods,
                    "worthiness_score": round(float(len(unique_methods)), 6),
                    "internal_segment4_count": 0,
                    "fqmn_known_count": 0,
                    "fqmn_known_method": f"canonical_chain={len(unique_methods)}",
                    "invalid_reasons": [],
                    "deep_analysis_status": "ready",
                    "path_name": f"结构路径 {len(candidate_paths) + 1}",
                    "path_description": "直接来自 stage5 paths_map 的非单节点路径，更接近主流程风格。",
                }
            )

    candidate_paths.sort(key=lambda item: (-len(item.get("path") or []), str(item.get("leaf_node") or ""), int(item.get("path_index", 0))))
    selected = candidate_paths[: max(1, max_paths)]
    if not selected:
        return [], {"selection_policy": "canonical_structural", "selected_count": 0, "deferred_count": 0, "total_candidates": 0}
    return selected, {
        "selection_policy": "canonical_structural",
        "selected_count": len(selected),
        "deferred_count": max(0, len(candidate_paths) - len(selected)),
        "total_candidates": len(candidate_paths),
    }


def _select_partition_path_candidates(
    partition: Dict[str, Any],
    stage4_payload: Dict[str, Any],
    call_graph: Dict[str, Set[str]],
    *,
    max_paths: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    partition_methods_list = _resolve_partition_methods(partition)
    adjacency, partition_methods, external_incoming = _build_partition_local_graph(partition, stage4_payload, call_graph)
    entry_points = _build_partition_entry_points(partition_methods_list, adjacency, external_incoming)
    hypergraph = FunctionCallHypergraphGenerator(call_graph).generate_partition_hypergraph(
        {"partition_id": partition.get("partition_id"), "methods": partition_methods_list}
    )
    enhanced_hypergraph, paths_map = enhance_hypergraph_with_function_nodes(
        hypergraph=hypergraph,
        call_graph=call_graph,
        partition_methods=partition_methods,
        analyzer_report=None,
        max_path_length=10,
        use_llm=False,
        llm_agent=None,
        entry_points=[item["method_signature"] for item in entry_points],
    )
    _ = enhanced_hypergraph
    multi_hop_paths_map: Dict[Any, Any] = {}
    for leaf, paths in (paths_map or {}).items():
        non_single = [
            path for path in (paths or [])
            if len([str(item).strip() for item in (path or []) if str(item).strip()]) > 1
        ]
        if non_single:
            multi_hop_paths_map[leaf] = non_single

    analysis_payload_multi_hop = {
        "paths_map": multi_hop_paths_map or {},
        "fqns": _build_partition_fqns(partition_methods_list),
        "call_graph": _build_partition_call_graph_payload(adjacency, partition_methods_list),
        "entry_points": entry_points,
    }

    candidate_paths, candidate_info = _canonical_partition_path_candidates(
        multi_hop_paths_map or {},
        analysis_payload_multi_hop,
        max_paths=max_paths,
    )
    if candidate_paths:
        return candidate_paths, candidate_info, analysis_payload_multi_hop

    structural_paths, structural_info = _extract_structural_partition_paths(analysis_payload_multi_hop, max_paths=max_paths)
    if structural_paths:
        return structural_paths, structural_info, analysis_payload_multi_hop

    placeholder_path = {
        "leaf_node": "",
        "path_index": 0,
        "path": [],
        "function_chain": [],
        "worthiness_score": 0.0,
        "internal_segment4_count": 0,
        "fqmn_known_count": 0,
        "fqmn_known_method": "no_multi_hop_path",
        "invalid_reasons": ["no_multi_hop_path"],
        "deep_analysis_status": "no_multi_hop_path",
        "path_name": "无多跳路径",
        "path_description": "该分区在 paths_map 中没有长度>=2 的候选路径，未选择任何 path。",
    }
    return [placeholder_path], {
        "selection_policy": "no_multi_hop_path",
        "selected_count": 1,
        "deferred_count": 0,
        "total_candidates": 0,
    }, analysis_payload_multi_hop
    return lightweight_paths, {
        "selection_policy": "lightweight_fallback",
        "selected_count": len(lightweight_paths),
        "deferred_count": 0,
        "total_candidates": len(lightweight_paths),
    }, analysis_payload


def _resolve_explain_mode(
    *,
    force_llm_explain: bool,
    skip_llm_explain: bool,
    skip_llm_explain_env: bool,
) -> Tuple[bool, str]:
    env_enabled = str(os.getenv("FH_ENABLE_CFG_DFG_LLM_EXPLAIN") or "").strip().lower() in {"1", "true", "yes", "on"}
    if skip_llm_explain:
        return False, "skip"
    if force_llm_explain:
        return True, "force"
    if not skip_llm_explain_env and env_enabled:
        return True, "env"
    return False, "skip"


def _replace_path_ir(path_ir: PathIR, **updates: Any) -> PathIR:
    payload = path_ir.to_dict()
    payload.pop("path", None)
    payload.pop("semantics", None)
    payload.update(updates)
    return PathIR(**payload)


def _explain_cfg_dfg(helper: Any, path_ir: PathIR) -> str:
    payload = {
        "path_id": path_ir.path_id,
        "function_chain": path_ir.function_chain,
        "cfg": path_ir.cfg,
        "dfg": path_ir.dfg,
        "input_info": path_ir.input_info,
        "output_info": path_ir.output_info,
    }
    return str(
        helper.call(
            system_prompt=(
                "你是代码路径语义解释器。"
                "请输出简洁 Markdown，总结该调用路径的控制流与数据流。"
                "不要输出 JSON。"
            ),
            user_prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            use_cache=False,
        )
        or ""
    ).strip()


def _build_path_ir(
    *,
    partition: Dict[str, Any],
    partition_methods: Set[str],
    path_index: int,
    path: List[str],
    run_id: str,
    report: ProjectAnalysisReport,
    call_graph: Dict[str, Set[str]],
    project_path: str,
    profile_builder: MethodFunctionProfileBuilder,
    explain_enabled: bool,
    explain_trigger_mode: str,
    skip_cfg_dfg: bool,
    explain_helper: Any,
    symbols_available: bool,
    candidate: Optional[Dict[str, Any]] = None,
) -> PathIR:
    started_at = time.perf_counter()
    cfg_payload: Optional[Dict[str, Any]] = None
    dfg_payload: Optional[Dict[str, Any]] = None
    if not skip_cfg_dfg:
        cfg_payload = generate_path_level_cfg(
            path=path,
            call_graph=call_graph,
            analyzer_report=report,
            partition_methods=partition_methods,
            inputs=[],
            outputs=[],
        )
        dfg_payload = generate_path_level_dfg(
            path=path,
            call_graph=call_graph,
            analyzer_report=report,
            partition_methods=partition_methods,
            dataflow_analyzer=None,
        )

    method_profiles: Dict[str, Any] = {}
    profile_error = ""
    try:
        method_profiles = profile_builder.build_profiles_batch(path)
    except Exception as exc:
        profile_error = f"method_profile_builder_failed: {exc}"

    semantics = analyze_path_semantics(path, report, method_profiles)
    path_ir = PathIR(
        path_id=str((candidate or {}).get("path_id") or f"{str(partition.get('partition_id') or 'partition')}_{path_index}"),
        run_id=run_id,
        partition_id=str(partition.get("partition_id") or "unknown"),
        leaf_node=str((candidate or {}).get("leaf_node") or (path[-1] if path else "")),
        function_chain=path,
        path_index=int((candidate or {}).get("path_index") or path_index),
        path_name=str((candidate or {}).get("path_name") or semantics.get("semantic_label") or f"路径 {path_index + 1}"),
        path_description=str((candidate or {}).get("path_description") or semantics.get("description") or f"包含 {len(path)} 个方法的调用链"),
        semantic_label=str(semantics.get("semantic_label") or f"路径 {path_index + 1}"),
        keywords=[str(item).strip() for item in (semantics.get("keywords") or []) if str(item).strip()],
        functional_domain=str(semantics.get("functional_domain") or "general"),
        description=str(semantics.get("description") or ""),
        worthiness_score=float((candidate or {}).get("worthiness_score") or len(path)),
        worthiness_reasons=list((candidate or {}).get("worthiness_reasons") or ["selected_by_partition_path_coverage"]),
        deep_analysis_status=str((candidate or {}).get("deep_analysis_status") or "ready"),
        cfg=cfg_payload,
        dfg=dfg_payload,
        input_info=(cfg_payload or {}).get("input_info", {}) if isinstance(cfg_payload, dict) else {},
        output_info=(cfg_payload or {}).get("output_info", {}) if isinstance(cfg_payload, dict) else {},
        cfg_dfg_explain_md="",
        source_project_path=project_path or None,
        skip_reason=None,
        trigger_mode=explain_trigger_mode,
        llm_reasoning=profile_error,
        model=None,
        duration_ms=0,
    )

    if skip_cfg_dfg:
        path_ir = _replace_path_ir(path_ir, deep_analysis_status="skipped_cfg_dfg", skip_reason="cfg_dfg skipped by flag")
    elif explain_enabled:
        try:
            if explain_helper is None:
                raise RuntimeError("missing_llm_config")
            explain_md = _explain_cfg_dfg(explain_helper, path_ir)
            if explain_md:
                path_ir = _replace_path_ir(
                    path_ir,
                    cfg_dfg_explain_md=explain_md,
                    model=str(explain_helper.config.model),
                )
            else:
                path_ir = _replace_path_ir(
                    path_ir,
                    deep_analysis_status="error_explain",
                    skip_reason="empty_explain_response",
                    llm_reasoning="empty_explain_response",
                    model=str(explain_helper.config.model),
                )
        except Exception as exc:
            path_ir = _replace_path_ir(
                path_ir,
                deep_analysis_status=("error_explain_config_missing" if "missing_llm_config" in str(exc) else "error_explain"),
                skip_reason=str(exc),
                llm_reasoning=str(exc),
                model=(str(get_deepseek_settings().get("model") or "") or None),
            )
    else:
        path_ir = _replace_path_ir(
            path_ir,
            deep_analysis_status="skipped_explain",
            skip_reason="未指定 --force-llm-explain 时 explain 留空是预期行为",
        )

    if not symbols_available:
        path_ir = _replace_path_ir(path_ir, deep_analysis_status="partial", skip_reason=path_ir.skip_reason or "stage1 symbols missing")

    duration_ms = int((time.perf_counter() - started_at) * 1000)
    if not explain_enabled:
        duration_ms = 0
    path_ir = _replace_path_ir(path_ir, duration_ms=duration_ms)
    return path_ir


def _output_summary(
    *,
    partitions: List[Dict[str, Any]],
    path_analyses: List[Dict[str, Any]],
    method_population: Set[str],
    max_paths: int,
    skip_llm_explain: bool,
    skip_cfg_dfg: bool,
) -> Dict[str, Any]:
    explain_count = sum(1 for item in path_analyses if str(item.get("cfg_dfg_explain_md") or "").strip())
    covered_methods: Set[str] = set()
    for item in path_analyses:
        covered_methods.update(str(part).strip() for part in (item.get("function_chain") or []) if str(part).strip())
    coverage = (len(covered_methods) / len(method_population)) if method_population else 0.0
    status = "completed"
    if not partitions or not path_analyses:
        status = "partial"
    elif any(str(item.get("deep_analysis_status") or "") in {"partial", "error_explain", "error_explain_config_missing"} for item in path_analyses):
        status = "partial"
    return {
        "status": status,
        "path_count": len(path_analyses),
        "partition_count": len(partitions),
        "max_paths": int(max_paths),
        "skip_llm_explain": bool(skip_llm_explain),
        "skip_cfg_dfg": bool(skip_cfg_dfg),
        "explain_filled_ratio": round((explain_count / len(path_analyses)), 4) if path_analyses else 0.0,
        "path_method_coverage": round(coverage, 4),
    }


def run_stage5(
    input_path: str,
    output_path: str,
    *,
    stage1_path: str | None = None,
    graph_db_path: str | None = None,
    max_paths: int = 10,
    skip_llm_explain: bool = False,
    force_llm_explain: bool = False,
    skip_cfg_dfg: bool = False,
    skip_llm_explain_env: bool = False,
    verbose: bool = False,
) -> Path:
    stage4_payload = _load_json(input_path)
    stage3_payload = _load_stage3_payload_from_stage4(stage4_payload, input_path)
    stage1_payload, resolved_stage1_path = _resolve_stage1_payload(stage1_path, stage4_payload, input_path)
    partitions = sort_partitions([copy.deepcopy(item) for item in (stage4_payload.get("partitions") or []) if isinstance(item, dict)])

    source_graph_db_path = _resolve_source_graph_db_path(stage4_payload, input_path)
    resolved_graph_db_path, copied_db_path = _prepare_target_graph_db(source_graph_db_path, output_path, graph_db_path)

    project = stage4_payload.get("project") or {}
    project_path_raw = str(project.get("path") or "").strip()
    project_path = os.path.normpath(project_path_raw) if project_path_raw else ""
    run_id = str((((stage3_payload.get("optimization") or {}).get("run_id")) or "")).strip()
    if not run_id:
        stable_token = json.dumps(
            {
                "input_path": str(Path(input_path).resolve()),
                "graph_db_path": str(resolved_graph_db_path.resolve()),
                "max_paths": int(max_paths),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        run_id = build_stage3_run_id(project_path or input_path, stable_token=stable_token)

    explain_enabled, explain_trigger_mode = _resolve_explain_mode(
        force_llm_explain=force_llm_explain,
        skip_llm_explain=skip_llm_explain,
        skip_llm_explain_env=skip_llm_explain_env,
    )

    report = _build_report_from_stage1(stage1_payload)
    call_graph = _build_call_graph(stage1_payload)
    _, symbol_by_qn = _build_symbol_indexes(stage1_payload)
    profile_builder = MethodFunctionProfileBuilder(project_path or report.project_path or str(BASE_DIR), report)
    explain_helper = build_llm_helper(get_deepseek_settings()) if explain_enabled and has_deepseek_config() else None

    path_irs: List[PathIR] = []
    method_population: Set[str] = set()
    symbols_available = bool(_extract_stage1_symbols(stage1_payload))
    partition_analyses_payload: Dict[str, Dict[str, Any]] = {}
    for partition in partitions:
        partition_methods_list = _resolve_partition_methods(partition)
        partition_methods = set(partition_methods_list)
        method_population.update(partition_methods)
        candidate_paths, candidate_info, analysis_payload = _select_partition_path_candidates(
            partition,
            stage4_payload,
            call_graph,
            max_paths=max_paths,
        )
        partition_id = str(partition.get("partition_id") or "unknown")
        partition_path_analyses: List[Dict[str, Any]] = []
        for path_index, candidate in enumerate(candidate_paths[: max(1, max_paths)]):
            path = [str(item).strip() for item in (candidate.get("function_chain") or candidate.get("path") or []) if str(item).strip()]
            path_ir = _build_path_ir(
                    partition=partition,
                    partition_methods=partition_methods,
                    path_index=path_index,
                    path=path,
                    run_id=run_id,
                    report=report,
                    call_graph=call_graph,
                    project_path=project_path,
                    profile_builder=profile_builder,
                    explain_enabled=explain_enabled,
                    explain_trigger_mode=explain_trigger_mode,
                    skip_cfg_dfg=skip_cfg_dfg,
                    explain_helper=explain_helper,
                    symbols_available=symbols_available,
                    candidate=candidate,
                )
            path_irs.append(path_ir)
            partition_path_analyses.append(path_ir.to_dict())
        partition_analyses_payload[partition_id] = {
            "paths_map": copy.deepcopy(analysis_payload.get("paths_map") or {}),
            "call_graph": copy.deepcopy(analysis_payload.get("call_graph") or {}),
            "entry_points": copy.deepcopy(analysis_payload.get("entry_points") or []),
            "fqns": copy.deepcopy(analysis_payload.get("fqns") or []),
            "path_analyses": partition_path_analyses,
            "path_analysis_info": {
                "selection_policy": str(candidate_info.get("selection_policy") or "unknown"),
                "selected_count": len(partition_path_analyses),
                "deferred_count": int(candidate_info.get("deferred_count") or 0),
                "total_candidates": int(candidate_info.get("total_candidates") or len(partition_path_analyses)),
                "completion_status": "complete" if partition_path_analyses else "partial",
            },
        }

    path_analyses = [item.to_dict() for item in path_irs]
    persist_stage5_snapshot(
        db_path=str(resolved_graph_db_path),
        path_analyses=path_analyses,
        run_id=run_id,
        source_project_path=project_path or None,
        symbol_by_qn=symbol_by_qn,
    )

    canonical_graph_db_path: Optional[Path] = None
    if project_path:
        canonical_graph_db_path = ProjectLibraryStorage().graph_db_path(project_path)

    path_links = [record.__dict__ for record in extract_path_link_records(path_analyses, run_id=run_id, symbol_by_qn=symbol_by_qn)]
    path_cfg_nodes = [record.__dict__ for record in extract_path_cfg_records(path_analyses, run_id=run_id)]
    path_dfg_nodes = [record.__dict__ for record in extract_path_dfg_records(path_analyses, run_id=run_id)]
    path_reverse_index: Dict[str, List[str]] = defaultdict(list)
    for record in extract_path_reverse_index_records(path_analyses, run_id=run_id):
        path_reverse_index[record.method_qn].append(record.path_id)
    normalized_reverse_index = {key: sorted(dict.fromkeys(value)) for key, value in sorted(path_reverse_index.items())}

    output_payload = copy.deepcopy(stage4_payload)
    output_payload["schema_version"] = "stage5.v1"
    output_payload["input"] = {
        "stage4_output_path": str(Path(input_path).resolve()).replace("\\", "/"),
        "stage1_output_path": resolved_stage1_path,
        "max_paths": int(max_paths),
        "skip_llm_explain": not explain_enabled,
        "skip_cfg_dfg": bool(skip_cfg_dfg),
        "force_llm_explain": bool(force_llm_explain),
    }
    output_payload["artifacts"] = {
        **copy.deepcopy(stage4_payload.get("artifacts") or {}),
        "source_graph_db_path": str(source_graph_db_path).replace("\\", "/"),
        "graph_db_path": str(resolved_graph_db_path).replace("\\", "/"),
        "stage5_graph_db_copy": (str(copied_db_path).replace("\\", "/") if copied_db_path else None),
        "canonical_graph_db_path": (str(canonical_graph_db_path).replace("\\", "/") if canonical_graph_db_path else None),
    }
    output_payload["path_analyses"] = path_analyses
    output_payload["partition_analyses"] = partition_analyses_payload
    output_payload["path_links"] = path_links
    output_payload["path_cfg_nodes"] = path_cfg_nodes
    output_payload["path_dfg_nodes"] = path_dfg_nodes
    output_payload["path_history"] = [
        {
            "history_id": f"{run_id}:{item['path_id'] or 'run'}",
            "run_id": run_id,
            "path_id": item.get("path_id") or "",
            "partition_id": item.get("partition_id") or "",
            "status": item.get("deep_analysis_status") or "unknown",
            "model": item.get("model"),
            "duration_ms": int(item.get("duration_ms") or 0),
            "skip_reason": item.get("skip_reason"),
            "llm_reasoning": item.get("llm_reasoning") or "",
        }
        for item in path_analyses
    ] or [
        {
            "history_id": f"{run_id}:run",
            "run_id": run_id,
            "path_id": "",
            "partition_id": "",
            "status": "partial",
            "model": None,
            "duration_ms": 0,
            "skip_reason": "no_paths_generated",
            "llm_reasoning": "no_paths_generated",
        }
    ]
    output_payload["path_reverse_index"] = normalized_reverse_index
    output_payload["summary"] = {
        **copy.deepcopy(stage4_payload.get("summary") or {}),
        **_output_summary(
            partitions=partitions,
            path_analyses=path_analyses,
            method_population=method_population,
            max_paths=max_paths,
            skip_llm_explain=not explain_enabled,
            skip_cfg_dfg=skip_cfg_dfg,
        ),
    }

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(output_payload, handle, indent=2, ensure_ascii=False, sort_keys=True)

    if verbose:
        print("[segment_5_path_semantics] 输出完成")
        print(f"  output: {output_file}")
        print(f"  graph_db: {resolved_graph_db_path}")
        print(f"  path_count: {len(path_analyses)}")
        print(f"  status: {output_payload['summary']['status']}")

    return output_file


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        run_stage5(
            input_path=args.input,
            output_path=args.output,
            stage1_path=args.stage1,
            graph_db_path=args.graph_db,
            max_paths=args.max_paths,
            skip_llm_explain=bool(args.skip_llm_explain),
            force_llm_explain=bool(args.force_llm_explain),
            skip_cfg_dfg=bool(args.skip_cfg_dfg),
            skip_llm_explain_env=bool(args.skip_llm_explain_env),
            verbose=bool(args.verbose),
        )
        return 0
    except Exception as exc:
        print(f"[segment_5_path_semantics] ERROR: {exc}", file=sys.stderr)
        return 1
