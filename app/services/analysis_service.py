#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
核心业务与分析服务逻辑（从原 app.py 迁移）
负责分析流程、数据缓存、日志与工具函数，不再直接创建 Flask 应用。
"""

from flask import request, jsonify, Response
from typing import Any, Dict, Optional, Tuple, List, Set
import os
import sys
import io
import builtins
import json
import copy
import hashlib
import time
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from dotenv import load_dotenv

FUNCTION_HIERARCHY_PIPELINE_VERSION = 'hierarchy-parity-v4-2026-03-23'

# ========== Safe print utility ==========
def _resolve_open_stream(preferred_stream=None):
    if preferred_stream is not None and not getattr(preferred_stream, 'closed', False):
        return preferred_stream
    stdout_stream = getattr(sys, 'stdout', None)
    if stdout_stream is not None and not getattr(stdout_stream, 'closed', False):
        return stdout_stream
    fallback_stdout = getattr(sys, '__stdout__', None)
    if fallback_stdout is not None and not getattr(fallback_stdout, 'closed', False):
        return fallback_stdout
    return None


def _ensure_utf8_output_stream() -> None:
    stream = _resolve_open_stream()
    if stream is None:
        return
    try:
        reconfigure = getattr(stream, 'reconfigure', None)
        if callable(reconfigure):
            try:
                reconfigure(encoding='utf-8', errors='replace')
            except TypeError:
                reconfigure(encoding='utf-8')
    except Exception:
        pass


def _safe_print(*args, **kwargs):
    """Safe print that handles closed stdout/stderr and encoding issues."""
    try:
        kwargs_copy = dict(kwargs)
        target_stream = _resolve_open_stream(kwargs_copy.get('file'))
        if target_stream is None:
            return
        kwargs_copy['file'] = target_stream
        builtins.print(*args, **kwargs_copy)
    except Exception:
        pass  # Silently fail if stream is unavailable


def _safe_flush():
    """Safe flush that handles closed stdout."""
    try:
        stream = _resolve_open_stream()
        if stream and hasattr(stream, 'flush') and not getattr(stream, 'closed', True):
            stream.flush()
    except Exception:
        pass


def _safe_traceback_print():
    """Safe traceback print."""
    import traceback
    try:
        traceback_stream = getattr(sys, 'stderr', None)
        if traceback_stream is None or getattr(traceback_stream, 'closed', False):
            traceback_stream = getattr(sys, '__stderr__', None)
        if traceback_stream is None or getattr(traceback_stream, 'closed', False):
            traceback_stream = _resolve_open_stream()
        if traceback_stream is not None and not getattr(traceback_stream, 'closed', False):
            traceback.print_exc(file=traceback_stream)
    except Exception:
        pass

# Replace print with safe_print for this module
print = _safe_print
# ========== End safe print utility ==========

# 加载环境变量（从 .env 文件）
load_dotenv()

# 标准化项目根目录（原 app.py 所在目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from analysis.analyzer import CodeAnalyzer
from analysis.hierarchy_model import HierarchyModel, HierarchyMetadata, CodeGraph, FunctionPartition, FunctionStats, FolderNode, FolderStats
from analysis.aggregation_calculator import apply_aggregations_to_hierarchy
from llm.code_understanding_agent import CodeUnderstandingAgent
from llm.code_explanation_chain import generate_explanations_for_hierarchy
from analysis.contains_relation_extractor import ContainsRelationExtractor
from analysis.cfg_generator import CFGGenerator
from analysis.dfg_generator import DFGGenerator
from analysis.io_extractor import IOExtractor
from analysis.code_model import RepositoryInfo, PackageInfo, ProjectAnalysisReport
from analysis.community_detector import CommunityDetector
from analysis.function_call_graph_generator import FunctionCallGraphGenerator
from analysis.function_call_hypergraph import FunctionCallHypergraphGenerator
from analysis.entry_point_identifier import EntryPointIdentifierGenerator
from analysis.partition_data_flow_generator import PartitionDataFlowGenerator
from analysis.partition_control_flow_generator import PartitionControlFlowGenerator
from analysis.function_node_enhancer import enhance_hypergraph_with_function_nodes
from analysis.path_level_analyzer import generate_path_level_cfg, generate_path_level_dfg, generate_path_level_dataflow_mermaid
from analysis.path_hypergraph_enhancer import analyze_path_call_chain_for_highlight
import build_graph_index  # Added for RAG index rebuilding
from src.analysis.entry_scoring import build_entry_points_shadow, filter_entry_points_shadow
from src.analysis.community_shadow import build_community_shadow, CommunityShadowStorage
from src.analysis.process_pipeline import build_process_shadow, ProcessShadowStorage
from src.search.adapters.hybrid_shadow_adapter import run_hybrid_shadow
from llm.rag_core.llm_api import DeepSeekAPI
from config.config import RAG_CONFIG, get_deepseek_settings, has_deepseek_config

# Phase 0 / Task 0.1: 统一数据访问接口（替换 app.py 内的全局缓存读写）
from data.data_accessor import get_data_accessor
from data.project_library_storage import ProjectLibraryStorage


def print_progress_bar(current: int, total: int, prefix: str = "", suffix: str = "", length: int = 40, show_per_line: bool = False):
    """
    打印terminal进度条
    
    Args:
        current: 当前进度
        total: 总数
        prefix: 前缀文字
        suffix: 后缀文字
        length: 进度条长度
        show_per_line: 如果为True，每次显示在新行（不覆盖），否则在同一行更新
    """
    if total == 0:
        percent = 100.0
        filled = length
    else:
        percent = 100.0 * (current / float(total))
        filled = int(length * current // total)
    
    bar = '█' * filled + '░' * (length - filled)
    
    if show_per_line:
        # 每次显示在新行（用于详细日志）
        print(f'{prefix} |{bar}| {current}/{total} ({percent:.1f}%) {suffix}', flush=True)
    else:
        # 在同一行更新（用于实时进度）
        print(f'\r{prefix} |{bar}| {current}/{total} ({percent:.1f}%) {suffix}', end='', flush=True)
        if current >= total:
            print()  # 换行

# 全局数据访问器（线程安全单例）
data_accessor = get_data_accessor()
_project_library_storage = ProjectLibraryStorage()
_parallel_llm_agent_local = threading.local()


def _get_deepseek_runtime_settings() -> Dict[str, str]:
    settings = get_deepseek_settings()
    return {
        'api_key': str(settings.get('api_key') or '').strip(),
        'base_url': str(settings.get('base_url') or 'https://api.deepseek.com/v1').strip(),
        'model': str(settings.get('model') or 'deepseek-chat').strip(),
    }


def _create_code_understanding_agent() -> Optional[CodeUnderstandingAgent]:
    settings = _get_deepseek_runtime_settings()
    if not settings['api_key']:
        return None
    return CodeUnderstandingAgent(api_key=settings['api_key'], base_url=settings['base_url'])


def _create_deepseek_api_client() -> Optional[DeepSeekAPI]:
    settings = _get_deepseek_runtime_settings()
    if not settings['api_key']:
        return None
    return DeepSeekAPI(api_key=settings['api_key'], base_url=settings['base_url'], model=settings['model'])


def _get_phase4_threshold() -> float:
    raw_value = os.getenv('FH_PHASE4_ENTRY_THRESHOLD', '0.45')
    try:
        threshold = float(raw_value)
    except (TypeError, ValueError):
        threshold = 0.45
    return max(0.0, min(threshold, 1.0))


def _get_phase5_max_nodes() -> int:
    raw_value = os.getenv('FH_PHASE5_MAX_NODES', '2000')
    try:
        max_nodes = int(raw_value)
    except (TypeError, ValueError):
        max_nodes = 2000
    return max(50, max_nodes)


def _get_phase5_timeout_seconds() -> float:
    raw_value = os.getenv('FH_PHASE5_TIMEOUT_SECONDS')
    if raw_value is None:
        raw_value = os.getenv('FH_PHASE5_TIMEOUT', '30.0')
    try:
        timeout_seconds = float(raw_value)
    except (TypeError, ValueError):
        timeout_seconds = 12.0
    return max(0.5, timeout_seconds)


def _get_max_paths_per_partition(default_limit: int = 10) -> int:
    raw_value = os.getenv('FH_MAX_PATHS_PER_PARTITION', str(default_limit))
    try:
        max_paths = int(raw_value)
    except (TypeError, ValueError):
        max_paths = default_limit
    return max(1, min(max_paths, 12))


class _FunctionHierarchyTimingCollector:
    """Workset 0: 收集功能层级分析主链路的时间基线。"""

    def __init__(self, project_path: str):
        self.project_path = project_path
        self.started_at_iso = datetime.now().isoformat()
        self.started_at_perf = time.perf_counter()
        self._phase_started_at: Dict[str, float] = {}
        self._phases: Dict[str, Dict[str, Any]] = {}
        self._first_visible: Dict[str, Dict[str, Optional[float]]] = {
            'basic_result': {'ready_at_seconds': None, 'visible_at_seconds': None},
            'function_hierarchy_summary': {'ready_at_seconds': None, 'visible_at_seconds': None},
            'deep_analysis_result': {'ready_at_seconds': None, 'visible_at_seconds': None},
        }
        self._publish_mark_seconds: Optional[float] = None
        self._blocking_finished_seconds: Optional[float] = None
        self._index_rebuild: Dict[str, Any] = {
            'trigger_seconds': None,
            'background_seconds': None,
            'status': 'disabled',
            'error': None,
        }

    def _elapsed(self) -> float:
        return round(time.perf_counter() - self.started_at_perf, 6)

    def start_phase(self, phase_id: str, *, layer: str, blocking: bool) -> None:
        self._phase_started_at[phase_id] = time.perf_counter()
        phase = self._phases.setdefault(
            phase_id,
            {
                'id': phase_id,
                'duration_seconds': 0.0,
                'layer': layer,
                'blocking': blocking,
            },
        )
        phase['layer'] = layer
        phase['blocking'] = blocking

    def end_phase(self, phase_id: str) -> None:
        started_at = self._phase_started_at.pop(phase_id, None)
        if started_at is None:
            return
        duration = round(time.perf_counter() - started_at, 6)
        phase = self._phases.setdefault(
            phase_id,
            {'id': phase_id, 'duration_seconds': 0.0, 'layer': 'default_visible', 'blocking': True},
        )
        phase['duration_seconds'] = round(float(phase.get('duration_seconds', 0.0)) + duration, 6)

    def mark_ready(self, metric_id: str) -> None:
        metric = self._first_visible.get(metric_id)
        if metric and metric['ready_at_seconds'] is None:
            metric['ready_at_seconds'] = self._elapsed()

    def mark_published(self) -> None:
        if self._publish_mark_seconds is None:
            self._publish_mark_seconds = self._elapsed()
        for metric in self._first_visible.values():
            if metric['visible_at_seconds'] is None:
                metric['visible_at_seconds'] = self._publish_mark_seconds

    def mark_blocking_finished(self) -> None:
        if self._blocking_finished_seconds is None:
            self._blocking_finished_seconds = self._elapsed()

    def mark_index_rebuild_triggered(self) -> None:
        self._index_rebuild['trigger_seconds'] = self._elapsed()
        self._index_rebuild['status'] = 'pending_background'

    def mark_index_rebuild_finished(self, *, error: Optional[str] = None) -> None:
        self._index_rebuild['background_seconds'] = self._elapsed()
        self._index_rebuild['status'] = 'failed' if error else 'ready'
        self._index_rebuild['error'] = error

    def mark_index_rebuild_disabled(self, *, error: Optional[str] = None) -> None:
        self._index_rebuild['status'] = 'disabled'
        self._index_rebuild['error'] = error

    def finalize(self) -> Dict[str, Any]:
        total_wall_clock = self._elapsed()
        blocking_seconds = self._blocking_finished_seconds if self._blocking_finished_seconds is not None else total_wall_clock

        phases = []
        blocking_total = 0.0
        layer_rollups = {
            'default_visible_seconds': 0.0,
            'expand_visible_seconds': 0.0,
            'advanced_visible_seconds': 0.0,
            'deferred_background_seconds': 0.0,
        }
        layer_key_map = {
            'default_visible': 'default_visible_seconds',
            'expand_visible': 'expand_visible_seconds',
            'advanced_visible': 'advanced_visible_seconds',
            'deferred_background': 'deferred_background_seconds',
        }

        for phase in self._phases.values():
            duration = round(float(phase.get('duration_seconds', 0.0)), 6)
            layer = str(phase.get('layer', 'default_visible'))
            blocking = bool(phase.get('blocking', True))
            if blocking:
                blocking_total += duration
            rollup_key = layer_key_map.get(layer)
            if rollup_key:
                layer_rollups[rollup_key] = round(layer_rollups[rollup_key] + duration, 6)
            phases.append(
                {
                    'id': phase['id'],
                    'duration_seconds': duration,
                    'share_of_blocking': round((duration / blocking_seconds), 6) if blocking_seconds > 0 else 0.0,
                    'layer': layer,
                    'blocking': blocking,
                }
            )

        phases.sort(key=lambda item: item['duration_seconds'], reverse=True)

        return {
            'schema_version': 'workset0.v1',
            'workset': 0,
            'project_path': self.project_path,
            'started_at': self.started_at_iso,
            'finished_at': datetime.now().isoformat(),
            'totals': {
                'wall_clock_seconds': round(total_wall_clock, 6),
                'blocking_seconds': round(blocking_seconds, 6),
                'measured_blocking_phase_seconds': round(blocking_total, 6),
            },
            'first_visible': self._first_visible,
            'phases': phases,
            'rollups': layer_rollups,
            'top_heaviest_phases': [
                {'id': item['id'], 'duration_seconds': item['duration_seconds']}
                for item in phases[:3]
            ],
            'index_rebuild': self._index_rebuild,
            'notes': [
                'Workset 0 only records baseline timings; no execution-order or feature-flag behavior changed.',
                'Current pipeline publishes visible results at final status update; ready_at_seconds may precede visible_at_seconds.',
                'If measured bottlenecks differ from plan assumptions, update Workset 0 notes before moving to Workset 1.',
            ],
        }


def _read_env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = str(raw_value).strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    return default


def _read_index_rebuild_mode() -> str:
    raw_value = str(os.getenv('FH_INDEX_REBUILD_MODE', 'deferred')).strip().lower()
    if raw_value in {'disabled', 'deferred', 'immediate'}:
        return raw_value
    return 'deferred'


def _resolve_function_hierarchy_execution_profile() -> Dict[str, Any]:
    layer_enabled = {
        'default_visible': _read_env_bool('FH_ENABLE_DEFAULT_VISIBLE_LAYER', True),
        'expand_visible': _read_env_bool('FH_ENABLE_EXPAND_VISIBLE_LAYER', True),
        'advanced_visible': _read_env_bool('FH_ENABLE_ADVANCED_VISIBLE_LAYER', True),
    }
    raw_steps = {
        'partition_llm_semantics': _read_env_bool('FH_ENABLE_PARTITION_LLM_SEMANTICS', True),
        'path_llm_analysis': _read_env_bool('FH_ENABLE_PATH_LLM_ANALYSIS', True),
        'path_supplement_generation': _read_env_bool('FH_ENABLE_PATH_SUPPLEMENT_GENERATION', True),
        'path_cfg_dfg_io': _read_env_bool('FH_ENABLE_PATH_CFG_DFG_IO', True),
        'cfg_dfg_llm_explain': _read_env_bool('FH_ENABLE_CFG_DFG_LLM_EXPLAIN', True),
        'include_deep_analysis_in_default_result': _read_env_bool('FH_INCLUDE_DEEP_ANALYSIS_IN_DEFAULT_RESULT', True),
    }
    index_rebuild_mode = _read_index_rebuild_mode()

    effective_steps = {
        'partition_llm_semantics': raw_steps['partition_llm_semantics'],
        'path_llm_analysis': raw_steps['path_llm_analysis'],
        'path_supplement_generation': raw_steps['path_supplement_generation'],
        'path_cfg_dfg_io': raw_steps['path_cfg_dfg_io'],
        'cfg_dfg_llm_explain': raw_steps['path_cfg_dfg_io'] and raw_steps['path_llm_analysis'] and raw_steps['cfg_dfg_llm_explain'],
        'include_deep_analysis_in_default_result': layer_enabled['default_visible'] and raw_steps['include_deep_analysis_in_default_result'],
        'index_rebuild_immediate': index_rebuild_mode == 'immediate',
        'index_rebuild_deferred': index_rebuild_mode == 'deferred',
    }

    def _status(enabled: bool, *, layer: str) -> str:
        if layer == 'advanced_visible' and not layer_enabled['advanced_visible']:
            return 'available_on_demand'
        return 'ready' if enabled else 'disabled'

    return {
        'layers': layer_enabled,
        'raw_steps': raw_steps,
        'effective_steps': effective_steps,
        'index_rebuild_mode': index_rebuild_mode,
        'step_visibility': {
            'partition_llm_semantics': {'layer': 'advanced_visible', 'status': _status(effective_steps['partition_llm_semantics'], layer='advanced_visible')},
            'path_llm_analysis': {'layer': 'advanced_visible', 'status': _status(effective_steps['path_llm_analysis'], layer='advanced_visible')},
            'path_supplement_generation': {'layer': 'advanced_visible', 'status': _status(effective_steps['path_supplement_generation'], layer='advanced_visible')},
            'path_cfg_dfg_io': {'layer': 'advanced_visible', 'status': _status(effective_steps['path_cfg_dfg_io'], layer='advanced_visible')},
            'cfg_dfg_llm_explain': {'layer': 'advanced_visible', 'status': _status(effective_steps['cfg_dfg_llm_explain'], layer='advanced_visible')},
            'index_rebuild': {
                'layer': 'deferred_background',
                'status': 'ready' if index_rebuild_mode == 'immediate' else 'available_on_demand' if index_rebuild_mode == 'deferred' else 'disabled',
            },
        },
    }


def _get_path_analysis_partition_limit(default_limit: int) -> int:
    raw_value = os.getenv('FH_PATH_ANALYSIS_PARTITION_LIMIT', str(default_limit))
    try:
        partition_limit = int(raw_value)
    except (TypeError, ValueError):
        partition_limit = default_limit
    return max(0, partition_limit)


def _get_structural_path_partition_limit(path_analysis_partition_limit: int, total_partitions: int) -> int:
    derived_default = max(path_analysis_partition_limit, 8)
    if total_partitions > 0:
        derived_default = max(derived_default, min(total_partitions, 16))
    raw_value = os.getenv('FH_STRUCTURAL_PATH_PARTITION_LIMIT', str(derived_default))
    try:
        partition_limit = int(raw_value)
    except (TypeError, ValueError):
        partition_limit = derived_default
    return max(0, partition_limit)


def _build_fqmn_info_map(fqns_list: Any) -> Dict[str, Dict[str, Any]]:
    fqmn_info_map: Dict[str, Dict[str, Any]] = {}
    for fqn_info in fqns_list or []:
        if not isinstance(fqn_info, dict):
            continue
        method_sig = fqn_info.get('method_signature')
        if method_sig:
            fqmn_info_map[method_sig] = {
                'fqn': fqn_info.get('fqn'),
                'origin': fqn_info.get('origin'),
                'segment_count': fqn_info.get('segment_count', 0),
            }
    return fqmn_info_map


def _evaluate_path_candidate(path: Any, fqmn_info_map: Dict[str, Dict[str, Any]], *, filter_single_node: bool) -> Dict[str, Any]:
    methods = list(path or [])
    invalid_reasons = []
    if not methods:
        invalid_reasons.append('empty_path')
    if filter_single_node and len(methods) <= 1:
        invalid_reasons.append('single_node_path')

    fqmn_known_count = 0
    internal_segment4_count = 0
    external_count = 0
    missing_fqmn_count = 0
    segment_anomaly_count = 0

    for method_sig in methods:
        fqmn_info = fqmn_info_map.get(method_sig)
        if not fqmn_info:
            missing_fqmn_count += 1
            continue
        fqmn_known_count += 1
        origin = fqmn_info.get('origin')
        segment_count = fqmn_info.get('segment_count', 0)
        if origin == 'external':
            external_count += 1
        if segment_count != 4:
            segment_anomaly_count += 1
        if origin == 'internal' and segment_count == 4:
            internal_segment4_count += 1

    if fqmn_known_count == 0:
        invalid_reasons.append('no_fqmn_info')

    score = 0.0
    if not invalid_reasons:
        unique_methods = len(set(methods))
        score += float(min(len(methods), 6))
        score += float(min(internal_segment4_count, 6)) * 2.0
        score += float(unique_methods)
        if 2 <= len(methods) <= 4:
            score += 1.5
        if len(methods) > 4:
            score -= 0.5 * float(len(methods) - 4)
        score -= 0.5 * float(external_count)
        score -= 0.5 * float(segment_anomaly_count)
        if internal_segment4_count == 0:
            score -= 1.0

    return {
        'is_valid': not invalid_reasons,
        'invalid_reasons': invalid_reasons,
        'fqmn_known_count': fqmn_known_count,
        'internal_segment4_count': internal_segment4_count,
        'external_count': external_count,
        'missing_fqmn_count': missing_fqmn_count,
        'segment_anomaly_count': segment_anomaly_count,
        'score': round(score, 6),
    }


def _select_representative_paths(candidates: Any, max_paths: int) -> Tuple[list, list]:
    normalized_candidates = list(candidates or [])
    if max_paths <= 0 or not normalized_candidates:
        return [], normalized_candidates

    ranked_candidates = sorted(
        normalized_candidates,
        key=lambda item: (
            -float(item.get('worthiness_score', 0.0)),
            -int(item.get('internal_segment4_count', 0)),
            -len(item.get('path', []) or []),
            str(item.get('leaf_node', '')),
            int(item.get('path_index', 0)),
        ),
    )

    selected = []
    selected_keys = set()
    covered_leaf_nodes = set()
    covered_methods = set()

    for candidate in ranked_candidates:
        if len(selected) >= max_paths:
            break
        leaf_node = candidate.get('leaf_node')
        candidate_key = (leaf_node, candidate.get('path_index'))
        if leaf_node in covered_leaf_nodes or candidate_key in selected_keys:
            continue
        selected.append(candidate)
        selected_keys.add(candidate_key)
        covered_leaf_nodes.add(leaf_node)
        covered_methods.update(candidate.get('path', []) or [])

    for candidate in ranked_candidates:
        if len(selected) >= max_paths:
            break
        candidate_key = (candidate.get('leaf_node'), candidate.get('path_index'))
        if candidate_key in selected_keys:
            continue
        path_methods = set(candidate.get('path', []) or [])
        overlap = len(path_methods.intersection(covered_methods))
        diversity_bonus = max(0, len(path_methods) - overlap)
        adjusted_score = float(candidate.get('worthiness_score', 0.0)) + (0.25 * diversity_bonus) - (0.1 * overlap)
        candidate['selection_adjusted_score'] = round(adjusted_score, 6)
        selected.append(candidate)
        selected_keys.add(candidate_key)
        covered_methods.update(path_methods)

    deferred = [
        candidate for candidate in ranked_candidates
        if (candidate.get('leaf_node'), candidate.get('path_index')) not in selected_keys
    ]
    return selected, deferred


def _summarize_path_candidate(candidate: Dict[str, Any], *, status: str, reason: str) -> Dict[str, Any]:
    return {
        'leaf_node': candidate.get('leaf_node'),
        'path_index': candidate.get('path_index'),
        'path': candidate.get('path'),
        'worthiness_score': candidate.get('worthiness_score', 0.0),
        'worthiness_reasons': candidate.get('worthiness_reasons', []),
        'deep_analysis_status': status,
        'deferred_reason': reason,
    }


def _rank_partitions_for_path_analysis(partition_path_stats: Any, partition_limit: int) -> list:
    ranked_stats = sorted(
        [item for item in (partition_path_stats or []) if item.get('valid_path_count', 0) > 0],
        key=lambda item: (
            -int(item.get('valid_path_count', 0)),
            -int(item.get('internal_segment4_path_count', 0)),
            int(item.get('total_path_count', 0)),
            str(item.get('partition_id', '')),
        ),
    )
    if not ranked_stats:
        ranked_stats = sorted(
            [item for item in (partition_path_stats or []) if item.get('total_path_count', 0) > 0],
            key=lambda item: (
                -int(item.get('total_path_count', 0)),
                -int(item.get('internal_segment4_path_count', 0)),
                str(item.get('partition_id', '')),
            ),
        )
    if partition_limit <= 0:
        return [item.get('partition_id') for item in ranked_stats if item.get('partition_id')]
    return [item.get('partition_id') for item in ranked_stats[:partition_limit] if item.get('partition_id')]


def _get_parallel_worker_count(total_items: int, limit: int = 4) -> int:
    if total_items <= 0:
        return 1
    return max(1, min(limit, total_items))


def _compute_partition_path_stat_item(partition: Dict[str, Any], partition_analyses: Dict[str, Any], partition_paths_map: Dict[str, Any], filter_single_node_paths: bool) -> Dict[str, Any]:
    partition_id = partition.get('partition_id', 'unknown')
    partition_name = partition.get('name', 'unknown')
    paths_map = partition_paths_map.get(partition_id, {})

    if not paths_map:
        return {
            'partition_id': partition_id,
            'partition_name': partition_name,
            'valid_path_count': 0,
            'total_path_count': 0,
            'reason': '没有路径信息',
        }

    partition_analysis = partition_analyses.get(partition_id) or {}
    fqmn_info_map = partition_analysis.get('fqmn_info_map') or _build_fqmn_info_map(partition_analysis.get('fqns', []))

    valid_path_count = 0
    total_path_count = 0
    filtered_by_length = 0
    filtered_by_fqmn_segment = 0
    filtered_by_fqmn_external = 0
    filtered_by_fqmn_not_internal = 0
    filtered_by_no_fqmn = 0
    internal_segment4_path_count = 0

    for _, paths in paths_map.items():
        for path in paths:
            total_path_count += 1
            evaluation = _evaluate_path_candidate(path, fqmn_info_map, filter_single_node=filter_single_node_paths)
            if not evaluation['is_valid']:
                filtered_by_length += int('single_node_path' in evaluation['invalid_reasons'])
                filtered_by_no_fqmn += evaluation['missing_fqmn_count']
                filtered_by_fqmn_segment += evaluation['segment_anomaly_count']
                filtered_by_fqmn_external += evaluation['external_count']
                if 'no_internal_segment4_method' in evaluation['invalid_reasons']:
                    filtered_by_fqmn_not_internal += 1
                continue

            valid_path_count += 1
            if evaluation['internal_segment4_count'] > 0:
                internal_segment4_path_count += 1

    return {
        'partition_id': partition_id,
        'partition_name': partition_name,
        'valid_path_count': valid_path_count,
        'total_path_count': total_path_count,
        'filtered_by_length': filtered_by_length,
        'filtered_by_fqmn_segment': filtered_by_fqmn_segment,
        'filtered_by_fqmn_external': filtered_by_fqmn_external,
        'filtered_by_fqmn_not_internal': filtered_by_fqmn_not_internal,
        'filtered_by_no_fqmn': filtered_by_no_fqmn,
        'internal_segment4_path_count': internal_segment4_path_count,
    }


def _generate_partition_call_graph_item(partition: Dict[str, Any], call_graph: Dict[str, Set[str]]) -> Dict[str, Any]:
    partition_id = partition.get('partition_id', 'unknown')
    generator = FunctionCallGraphGenerator(call_graph)
    return {
        'partition_id': partition_id,
        'call_graph': generator.generate_partition_call_graph(partition),
    }


def _generate_partition_hypergraph_item(
    partition: Dict[str, Any],
    call_graph: Dict[str, Set[str]],
    analyzer_report: Any,
    entry_points: Optional[List[Any]],
    enable_advanced_path_expansion: bool,
) -> Dict[str, Any]:
    partition_id = partition.get('partition_id', 'unknown')
    partition_methods = set(partition.get('methods', []))
    hypergraph_generator = FunctionCallHypergraphGenerator(call_graph)
    hypergraph = hypergraph_generator.generate_partition_hypergraph(partition)
    if enable_advanced_path_expansion:
        entry_point_sigs = [ep.method_sig for ep in (entry_points or [])] if entry_points else None
        enhanced_hypergraph, paths_map = enhance_hypergraph_with_function_nodes(
            hypergraph=hypergraph,
            call_graph=call_graph,
            partition_methods=partition_methods,
            analyzer_report=analyzer_report,
            max_path_length=10,
            use_llm=False,
            llm_agent=None,
            entry_points=entry_point_sigs,
        )
    else:
        enhanced_hypergraph = hypergraph
        paths_map = {}
    hypergraph_viz = enhanced_hypergraph.to_visualization_data()
    return {
        'partition_id': partition_id,
        'paths_map': paths_map,
        'hypergraph': enhanced_hypergraph.to_dict(),
        'hypergraph_viz': hypergraph_viz,
        'function_node_count': len([n for n in enhanced_hypergraph.nodes.values() if n.get('type') == 'function']),
        'total_paths': sum(len(paths) for paths in paths_map.values()),
        'leaf_node_count': len(paths_map),
        'total_nodes': len(enhanced_hypergraph.nodes),
        'method_nodes': len([n for n in enhanced_hypergraph.nodes.values() if n.get('type') == 'method']),
        'function_nodes': len([n for n in enhanced_hypergraph.nodes.values() if n.get('type') == 'function']),
        'hyperedge_count': len(enhanced_hypergraph.hyperedges),
        'total_edges': len(hypergraph_viz.get('edges', [])),
        'direct_call_edges': hypergraph_viz.get('statistics', {}).get('direct_call_edges', 0),
    }

# 全局分析状态（加锁保护，避免多线程读写冲突）
analysis_status = {
    'progress': 0,
    'status': '等待中...',
    'data': None,
    'report': None,  # 保存ProjectAnalysisReport
    'is_analyzing': False,
    'error': None,
    'analysis_type': None,
    'project_path': None,
}
status_lock = threading.Lock()

# 全局功能层级分析结果缓存（按项目路径索引）
# NOTE: 已由 Phase 0 / Task 0.1 的 DataAccessor 替代；保留仅为向后兼容（避免外部引用报错）
function_hierarchy_cache = {}  # deprecated
function_hierarchy_cache_lock = threading.Lock()  # deprecated

# 全局主分析结果缓存（用于恢复主界面）
# NOTE: 已由 Phase 0 / Task 0.1 的 DataAccessor 替代；保留仅为向后兼容（避免外部引用报错）
main_analysis_cache = {}  # deprecated
main_analysis_cache_lock = threading.Lock()  # deprecated

# 全局日志文件对象（用于功能层级分析）
_log_file = None
_log_file_lock = threading.Lock()


def setup_log_file(project_path: str) -> str:
    """
    设置日志文件，创建logs文件夹并返回日志文件路径
    
    Args:
        project_path: 项目路径
        
    Returns:
        日志文件路径
    """
    global _log_file
    
    # 创建logs文件夹（保持与原 app.py 相同的根目录）
    logs_dir = os.path.join(str(PROJECT_ROOT), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # 生成日志文件名（包含时间戳）
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f'function_hierarchy_{timestamp}.log'
    log_filepath = os.path.join(logs_dir, log_filename)
    
    # 打开日志文件（追加模式，UTF-8编码）
    with _log_file_lock:
        if _log_file:
            try:
                if not _log_file.closed:
                    _log_file.close()
            except Exception:
                pass
        _log_file = open(log_filepath, 'a', encoding='utf-8')
    
    return log_filepath


def log_print(*args, **kwargs):
    """
    自定义print函数，同时输出到控制台和日志文件
    
    Args:
        *args: print的参数
        **kwargs: print的关键字参数（支持end, flush等）
    """
    # 先输出到控制台
    print(*args, **kwargs)
    
    # 然后写入日志文件
    global _log_file
    with _log_file_lock:
        if _log_file and not _log_file.closed:
            # 构建输出字符串
            output = ' '.join(str(arg) for arg in args)
            end = kwargs.get('end', '\n')
            
            # 写入文件
            try:
                _log_file.write(output + end)
                _log_file.flush()  # 立即刷新到文件
            except Exception:
                _log_file = None


def close_log_file():
    """关闭日志文件"""
    global _log_file
    with _log_file_lock:
        if _log_file:
            try:
                if not _log_file.closed:
                    _log_file.close()
            except Exception:
                pass
            _log_file = None


def update_analysis_status(**kwargs):
    """线程安全地更新全局分析状态"""
    with status_lock:
        analysis_status.update(kwargs)


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat() + 'Z'


def _parse_iso_timestamp(timestamp: Optional[str]) -> Optional[datetime]:
    text = str(timestamp or '').strip()
    if not text:
        return None
    normalized = text[:-1] + '+00:00' if text.endswith('Z') else text
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _derive_workbench_stage_meta(phase: Any, message: Any) -> Tuple[str, str]:
    normalized_phase = str(phase or '').strip()
    normalized_message = str(message or '').strip()

    if normalized_phase == 'starting':
        return '准备分析', normalized_message or '正在初始化统一工作台会话'
    if normalized_phase == 'main_running':
        return '主图谱分析', normalized_message or '正在构建主图谱与基础索引'
    if normalized_phase == 'hierarchy_running':
        detail = normalized_message or '正在生成功能层级、路径与经验沉淀'
        return '功能层级分析', detail
    if normalized_phase == 'bootstrap_ready':
        return '工作台已就绪', normalized_message or '主图谱与工作台引导数据已就绪'
    if normalized_phase == 'failed':
        return '分析失败', normalized_message or '统一分析会话失败'
    return '处理中', normalized_message or '正在处理请求'


def _normalize_existing_project_path(project_path: Optional[str]) -> str:
    if not project_path or not os.path.isdir(project_path) or 'tmp' in project_path:
        return str(PROJECT_ROOT)
    return os.path.normpath(project_path)


def _create_workbench_session(project_path: str) -> Dict[str, Any]:
    session_id = uuid4().hex
    now = _utcnow_iso()
    stage_label, stage_detail = _derive_workbench_stage_meta('starting', '统一分析会话已创建')
    payload = {
        'sessionId': session_id,
        'projectPath': project_path,
        'status': 'starting',
        'phase': 'starting',
        'progress': 0,
        'message': '统一分析会话已创建',
        'stageLabel': stage_label,
        'stageDetail': stage_detail,
        'error': None,
        'bootstrapReady': False,
        'bootstrap': None,
        'experienceOutputRoot': None,
        'hierarchyStartedAt': None,
        'startedAt': now,
        'updatedAt': now,
        'completedAt': None,
    }
    data_accessor.save_workbench_session(session_id, payload)
    return payload


def _get_workbench_session_or_none(session_id: str) -> Optional[Dict[str, Any]]:
    return data_accessor.get_workbench_session(session_id)


def _update_workbench_session(session_id: str, **changes: Any) -> Optional[Dict[str, Any]]:
    payload = _get_workbench_session_or_none(session_id)
    if not payload:
        return None
    payload = copy.deepcopy(payload)
    payload.update(changes)
    payload['updatedAt'] = _utcnow_iso()
    data_accessor.save_workbench_session(session_id, payload)
    return payload


def _normalize_benchmark_report_dir(report_dir: Optional[str]) -> str:
    value = str(report_dir or '').strip()
    if value:
        candidate = os.path.normpath(value)
    else:
        candidate = os.path.normpath(str(PROJECT_ROOT / 'benchmark_reports'))
    if not os.path.isabs(candidate):
        candidate = os.path.normpath(os.path.abspath(candidate))
    return candidate


def _create_benchmark_session(project_path: str, report_dir: str) -> Dict[str, Any]:
    session_id = uuid4().hex
    now = _utcnow_iso()
    payload = {
        'sessionId': session_id,
        'projectPath': project_path,
        'reportDir': report_dir,
        'status': 'starting',
        'phase': 'starting',
        'progress': 0,
        'message': '固定场景基准会话已创建',
        'error': None,
        'result': None,
        'startedAt': now,
        'updatedAt': now,
        'completedAt': None,
    }
    data_accessor.save_benchmark_session(session_id, payload)
    return payload


def _get_benchmark_session_or_none(session_id: str) -> Optional[Dict[str, Any]]:
    return data_accessor.get_benchmark_session(session_id)


def _update_benchmark_session(session_id: str, **changes: Any) -> Optional[Dict[str, Any]]:
    payload = _get_benchmark_session_or_none(session_id)
    if not payload:
        return None
    next_payload = copy.deepcopy(payload)
    next_payload.update(changes)
    next_payload['updatedAt'] = _utcnow_iso()
    data_accessor.save_benchmark_session(session_id, next_payload)
    return next_payload


def _run_fixed_scenario_benchmark_session(session_id: str, project_path: str, report_dir: str) -> None:
    _update_benchmark_session(
        session_id,
        status='running',
        phase='benchmark_running',
        progress=20,
        message='固定场景基准执行中',
        error=None,
    )
    try:
        from scripts.fixed_scenario_benchmark import run_benchmark

        result = run_benchmark(project_path=project_path, report_dir=report_dir)
        _update_benchmark_session(
            session_id,
            status='completed',
            phase='completed',
            progress=100,
            message='固定场景基准执行完成',
            error=None,
            result=result,
            completedAt=_utcnow_iso(),
        )
    except Exception as exc:
        _update_benchmark_session(
            session_id,
            status='failed',
            phase='failed',
            progress=100,
            message='固定场景基准执行失败',
            error=str(exc),
            completedAt=_utcnow_iso(),
        )


def _resolve_main_analysis_cached(project_path: str) -> Optional[Dict[str, Any]]:
    project_path = os.path.normpath(os.path.abspath(project_path))
    cached = data_accessor.get_main_analysis(project_path)
    if cached:
        return cached
    for cached_path in data_accessor.list_main_analysis_keys():
        if os.path.normpath(cached_path) == project_path:
            return data_accessor.get_main_analysis(cached_path)

    persisted = _project_library_storage.load_graph_data(project_path)
    if isinstance(persisted, dict):
        data_accessor.save_main_analysis(project_path, persisted)
        return persisted
    return None


def _normalize_project_lookup_path(project_path: Optional[str]) -> str:
    if not project_path:
        return ''
    return os.path.normpath(os.path.abspath(project_path))


def _resolve_runtime_project_path(project_path: Optional[str], allow_global_fallback: bool = True) -> str:
    if project_path:
        return _normalize_project_lookup_path(project_path)
    if not allow_global_fallback:
        return ''
    current_project_path = analysis_status.get('project_path')
    if current_project_path:
        return _normalize_project_lookup_path(current_project_path)
    return str(PROJECT_ROOT)


def _resolve_report_cached(project_path: str, allow_global_fallback: bool = True):
    project_path = _normalize_project_lookup_path(project_path)
    report = data_accessor.get_report(project_path)
    if report:
        return report

    for cached_path in data_accessor.list_main_analysis_keys():
        if os.path.normpath(cached_path) == project_path:
            report = data_accessor.get_report(cached_path)
            if report:
                return report

    if not allow_global_fallback:
        return None
    return analysis_status.get('report')


def _resolve_graph_node_data(project_path: str, entity_id: str, allow_global_fallback: bool = True) -> Optional[Dict[str, Any]]:
    graph_data = _resolve_main_analysis_cached(project_path)
    if not graph_data:
        if not allow_global_fallback:
            return None
        current_data = analysis_status.get('data') or {}
        if current_data.get('nodes') and current_data.get('edges'):
            graph_data = current_data
    if not graph_data:
        return None

    for node in graph_data.get('nodes', []) or []:
        data = node.get('data', {})
        if data.get('id') == entity_id:
            return data
    return None


def _method_identity_candidates(method_info: Any) -> set:
    full_name = method_info.get_full_name()
    class_name = method_info.class_name
    return {
        method_info.name,
        full_name,
        method_info.signature,
        f"method_{full_name}",
        f"method_{class_name}_{method_info.name}",
        f"method_{full_name.replace('.', '_')}",
        f"method_{class_name.replace('.', '_')}_{method_info.name}",
    }


def _function_identity_candidates(func_info: Any) -> set:
    name = func_info.name
    signature = getattr(func_info, 'signature', '') or ''
    return {
        name,
        signature,
        f"function_{name}",
        f"func_{name}",
    }


def _class_identity_candidates(class_info: Any) -> set:
    return {
        class_info.name,
        class_info.full_name,
        f"class_{class_info.full_name}",
        f"class_{class_info.full_name.replace('.', '_')}",
    }


def _resolve_method_or_function_from_report(report: ProjectAnalysisReport, entity_id: str):
    target = str(entity_id or '').strip()
    if not target:
        return None

    for class_info in report.classes.values():
        for method_info in class_info.methods.values():
            candidates = _method_identity_candidates(method_info)
            if target in candidates:
                return {
                    'kind': 'method',
                    'info': method_info,
                    'class_info': class_info,
                }

            if target.startswith('method_'):
                suffix = target[len('method_'):]
                if suffix.endswith(f"_{method_info.name}") and method_info.class_name.replace('.', '_') in suffix:
                    return {
                        'kind': 'method',
                        'info': method_info,
                        'class_info': class_info,
                    }

    for func_info in report.functions:
        if target in _function_identity_candidates(func_info):
            return {
                'kind': 'function',
                'info': func_info,
                'class_info': None,
            }

    return None


def _resolve_class_from_report(report: ProjectAnalysisReport, entity_id: str):
    target = str(entity_id or '').strip()
    if not target:
        return None
    for class_info in report.classes.values():
        if target in _class_identity_candidates(class_info):
            return class_info
    return None


def _guess_language(file_path: str) -> str:
    ext = os.path.splitext(str(file_path or ''))[1].lower()
    return {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'tsx',
        '.jsx': 'jsx',
        '.java': 'java',
        '.go': 'go',
        '.rs': 'rust',
        '.cpp': 'cpp',
        '.c': 'c',
        '.cs': 'csharp',
        '.php': 'php',
        '.rb': 'ruby',
        '.kt': 'kotlin',
        '.swift': 'swift',
    }.get(ext, 'text')


def _read_file_snippet(project_path: str, file_path: str, line_start: Optional[int], line_end: Optional[int], max_lines: int = 220):
    if not file_path:
        return None

    normalized_file_path = os.path.normpath(file_path)
    if not os.path.isabs(normalized_file_path):
        normalized_file_path = os.path.normpath(os.path.join(project_path, normalized_file_path))

    if not os.path.exists(normalized_file_path) or not os.path.isfile(normalized_file_path):
        return None

    try:
        with open(normalized_file_path, 'r', encoding='utf-8', errors='replace') as handle:
            lines = handle.readlines()
    except Exception:
        return None

    if not lines:
        return {
            'file_path': normalized_file_path,
            'line_start': 1,
            'line_end': 1,
            'snippet': '',
            'language': _guess_language(normalized_file_path),
        }

    total_lines = len(lines)
    if line_start and line_start > 0:
        start = max(1, int(line_start))
        if line_end and line_end >= start:
            end = int(line_end)
        else:
            end = min(total_lines, start + 80)
    else:
        start = 1
        end = min(total_lines, max_lines)

    if end - start + 1 > max_lines:
        end = start + max_lines - 1

    snippet = ''.join(lines[start - 1:end])
    return {
        'file_path': normalized_file_path,
        'line_start': start,
        'line_end': end,
        'snippet': snippet,
        'language': _guess_language(normalized_file_path),
    }


def _build_source_payload(project_path: str, *, source_code: Optional[str], file_path: Optional[str], line_start: Optional[int], line_end: Optional[int]) -> Dict[str, Any]:
    if source_code:
        return {
            'available': True,
            'language': _guess_language(file_path or ''),
            'file_path': file_path,
            'line_start': line_start,
            'line_end': line_end,
            'snippet': source_code,
        }

    snippet_payload = _read_file_snippet(project_path, file_path or '', line_start, line_end)
    if snippet_payload:
        return {
            'available': True,
            **snippet_payload,
        }

    return {
        'available': False,
        'language': _guess_language(file_path or ''),
        'file_path': file_path,
        'line_start': line_start,
        'line_end': line_end,
        'snippet': '',
    }


def _generate_cfg_dfg_io(method_like_info: Any) -> Dict[str, Any]:
    if not method_like_info or not method_like_info.source_code:
        return {
            'cfg': None,
            'cfg_json': None,
            'dfg': None,
            'dfg_json': None,
            'io': {
                'inputs': [],
                'outputs': [],
                'global_reads': [],
                'global_writes': [],
            },
        }

    cfg_generator = CFGGenerator()
    cfg = cfg_generator.generate_cfg(method_like_info.source_code, method_like_info.name)

    dfg_generator = DFGGenerator()
    dfg = dfg_generator.generate_dfg(method_like_info.source_code, method_like_info.name)

    io_extractor = IOExtractor()
    io_info = io_extractor.extract_io(
        method_like_info.source_code,
        getattr(method_like_info, 'name', None) or '',
        getattr(method_like_info, 'parameters', []) or [],
    )

    return {
        'cfg': cfg.to_dot(),
        'cfg_json': cfg.to_json(),
        'dfg': dfg.to_dot(),
        'dfg_json': dfg.to_json(),
        'io': {
            'inputs': io_info.inputs,
            'outputs': io_info.outputs,
            'global_reads': io_info.global_reads,
            'global_writes': io_info.global_writes,
        },
    }


def _build_workbench_file_tree(graph_data: Dict[str, Any], project_path: str) -> Dict[str, Any]:
    allowed_types = {'project', 'folder', 'package', 'module', 'file'}
    selected_nodes = []
    selected_node_ids = set()
    for node in graph_data.get('nodes', []) or []:
        data = node.get('data', {})
        if data.get('type') in allowed_types:
            selected_nodes.append({
                'id': data.get('id'),
                'label': data.get('label'),
                'type': data.get('type'),
                'fullName': data.get('full_name') or data.get('file'),
                'filePath': data.get('file'),
            })
            selected_node_ids.add(data.get('id'))

    selected_edges = []
    for edge in graph_data.get('edges', []) or []:
        data = edge.get('data', {})
        if data.get('relation') == 'contains' and data.get('source') in selected_node_ids and data.get('target') in selected_node_ids:
            selected_edges.append({
                'id': data.get('id'),
                'source': data.get('source'),
                'target': data.get('target'),
                'relation': data.get('relation'),
            })

    return {
        'projectPath': project_path,
        'nodes': selected_nodes,
        'edges': selected_edges,
    }


def _build_empty_phase6_read_contract(project_path: str) -> Dict[str, Any]:
    return {
        'contract_version': 'phase6-stage1-v1',
        'project_path': project_path,
        'capabilities': {
            'hybrid_search_shadow': False,
            'entry_points_shadow': False,
            'process_shadow': False,
            'community_shadow': False,
            'cfg_dfg_entity_api': False,
            'path_level_cfg_dfg_io': False,
        },
        'sources': {
            'hierarchy': '/api/function_hierarchy/result',
            'entry_points_shadow': '/api/entry_points_shadow',
            'process_shadow': '/api/process_shadow',
            'community_shadow': '/api/community_shadow',
            'hybrid_search_shadow': '/api/search_hybrid_shadow',
            'cfg_dfg': '/api/cfg_dfg/<entity_id>',
        },
        'adapters': {
            'partition_summaries': [],
        },
        'hierarchy_result': None,
        'shadow_results': {
            'entry_points': None,
            'process': None,
            'community': None,
        },
    }


def _build_workbench_bootstrap(session_id: str, project_path: str, *, hierarchy_state: str = 'ready', hierarchy_error: Optional[str] = None) -> Dict[str, Any]:
    graph_data = _resolve_main_analysis_cached(project_path)
    hierarchy_cached = _resolve_function_hierarchy_cached(project_path)
    if not graph_data:
        raise ValueError('主分析结果未就绪')

    read_contract: Optional[Dict[str, Any]] = None
    index_rebuild_status: Dict[str, Any] = {}
    hierarchy_hint: Optional[str] = None

    if hierarchy_cached:
        hierarchy_cached = _select_best_phase6_hierarchy_payload(project_path, hierarchy_cached)
        if isinstance(hierarchy_cached, dict):
            read_contract = _build_phase6_read_contract(project_path, hierarchy_cached)
            index_rebuild_status = hierarchy_cached.get('index_rebuild_status') or {}
        else:
            hierarchy_hint = '功能层级结果暂不可用，工作区将以主图谱先行加载。'
    else:
        hierarchy_hint = '功能层级仍在后台处理中，工作区已可先行使用。'

    if not read_contract:
        read_contract = _build_empty_phase6_read_contract(project_path)
        index_rebuild_status = {
            **index_rebuild_status,
            'state': 'pending' if hierarchy_state == 'ongoing' else 'degraded',
            'continues_in_background': hierarchy_state == 'ongoing',
        }
        if hierarchy_error:
            hierarchy_hint = hierarchy_hint or f'功能层级未完成，已降级返回主图谱：{hierarchy_error}'
        elif hierarchy_state == 'ongoing':
            hierarchy_hint = hierarchy_hint or '功能层级仍在后台处理中，稍后会自动补齐。'

    if hierarchy_state == 'ready' and not hierarchy_hint and index_rebuild_status.get('continues_in_background'):
        hierarchy_hint = '功能层级已就绪，后台仍在完善索引。'

    degraded = hierarchy_state != 'ready' or bool((hierarchy_cached or {}).get('degradation_summary') or [])
    bootstrap = {
        'contractVersion': 'workbench-bootstrap-v1',
        'sessionId': session_id,
        'projectPath': project_path,
        'status': {
            'phase': 'bootstrap_ready',
            'progress': 100,
            'degraded': degraded,
            'backgroundContinuing': bool(index_rebuild_status.get('continues_in_background')) or hierarchy_state == 'ongoing',
            'hierarchyState': hierarchy_state,
            'hint': hierarchy_hint,
        },
        'layoutHints': {
            'leftTreeFixed': True,
            'detailPanelDefaultVisible': False,
            'hierarchyDrawerDefaultVisible': False,
            'ragDrawerDefaultVisible': False,
            'maxPanels': 4,
        },
        'graph': graph_data,
        'fileTree': _build_workbench_file_tree(graph_data, project_path),
        'hierarchy': {
            'partitionSummaries': (read_contract.get('adapters') or {}).get('partition_summaries', []),
            'shadowResults': read_contract.get('shadow_results') or {},
            'capabilities': read_contract.get('capabilities') or {},
            'indexRebuildStatus': index_rebuild_status,
            'degraded': degraded,
            'hint': hierarchy_hint,
        },
        'sources': {
            'legacyGraph': '/api/result',
            'legacyHierarchy': '/api/phase6/read_contract',
            'legacyCfgDfg': '/api/cfg_dfg/<entity_id>',
            'legacyPartitionAnalysis': '/api/partition/<partition_id>/analysis',
        },
    }
    return bootstrap


def _map_workbench_progress(session_payload: Dict[str, Any]) -> Tuple[int, str]:
    phase = session_payload.get('phase')
    project_path = _normalize_project_lookup_path(session_payload.get('projectPath'))
    with status_lock:
        legacy_status = dict(analysis_status)

    legacy_project_path = _normalize_project_lookup_path(legacy_status.get('project_path'))
    legacy_active = bool(legacy_status.get('is_analyzing')) and legacy_project_path == project_path

    if not legacy_active:
        if phase == 'hierarchy_running':
            hierarchy_started_at = _parse_iso_timestamp(session_payload.get('hierarchyStartedAt'))
            started_at = hierarchy_started_at or _parse_iso_timestamp(session_payload.get('updatedAt')) or _parse_iso_timestamp(session_payload.get('startedAt'))
            if started_at:
                current_time = datetime.now(started_at.tzinfo) if started_at.tzinfo is not None else datetime.utcnow()
                elapsed_seconds = max(0.0, (current_time - started_at).total_seconds())
            else:
                elapsed_seconds = 0.0
            gradual_progress = min(96, 55 + int(min(elapsed_seconds / 3.0, 41)))
            return max(int(session_payload.get('progress', 55) or 55), gradual_progress), str(session_payload.get('message') or '处理中')
        return int(session_payload.get('progress', 0)), str(session_payload.get('message') or '处理中')

    legacy_progress = int(legacy_status.get('progress', 0) or 0)
    legacy_message = str(legacy_status.get('status') or session_payload.get('message') or '处理中')
    if phase == 'main_running':
        return min(50, max(1, int(legacy_progress * 0.5))), legacy_message
    if phase == 'hierarchy_running':
        return min(96, 50 + max(0, int(legacy_progress * 0.45))), legacy_message
    return int(session_payload.get('progress', 0)), legacy_message


def _run_workbench_session(session_id: str, project_path: str, experience_output_root: Optional[str] = None) -> None:
    try:
        main_stage_label, main_stage_detail = _derive_workbench_stage_meta('main_running', '统一分析会话开始：主分析阶段')
        _update_workbench_session(
            session_id,
            status='running',
            phase='main_running',
            progress=1,
            message='统一分析会话开始：主分析阶段',
            stageLabel=main_stage_label,
            stageDetail=main_stage_detail,
            experienceOutputRoot=experience_output_root,
        )
        artifacts = analyze_project(project_path, return_artifacts=True)
        if not artifacts or not artifacts.get('graph_data') or not artifacts.get('analyzer'):
            raise RuntimeError('主分析未返回可复用产物')

        bootstrap = _build_workbench_bootstrap(session_id, project_path, hierarchy_state='ongoing')
        hierarchy_started_at = _utcnow_iso()
        hierarchy_stage_label, hierarchy_stage_detail = _derive_workbench_stage_meta('hierarchy_running', '主图谱已就绪，功能层级继续处理中')
        _update_workbench_session(
            session_id,
            status='running',
            phase='hierarchy_running',
            progress=55,
            message='主图谱已就绪，功能层级继续处理中',
            stageLabel=hierarchy_stage_label,
            stageDetail=hierarchy_stage_detail,
            hierarchyStartedAt=hierarchy_started_at,
            bootstrapReady=True,
            bootstrap=bootstrap,
        )

        hierarchy_error: Optional[Exception] = None
        try:
            analyze_function_hierarchy(
                project_path,
                precomputed_graph_data=artifacts.get('graph_data'),
                precomputed_analyzer=artifacts.get('analyzer'),
                experience_output_root=experience_output_root,
            )
        except Exception as exc:
            hierarchy_error = exc
            print(f"[_run_workbench_session] ⚠️ 功能层级阶段降级完成: {exc}", flush=True)

        if hierarchy_error is None:
            bootstrap = _build_workbench_bootstrap(session_id, project_path, hierarchy_state='ready')
            final_message = '统一分析会话完成'
        else:
            bootstrap = _build_workbench_bootstrap(
                session_id,
                project_path,
                hierarchy_state='degraded',
                hierarchy_error=str(hierarchy_error),
            )
            final_message = '主图谱已完成，功能层级降级收尾'

        final_stage_label, final_stage_detail = _derive_workbench_stage_meta('bootstrap_ready', final_message)
        _update_workbench_session(
            session_id,
            status='completed',
            phase='bootstrap_ready',
            progress=100,
            message=final_message,
            stageLabel=final_stage_label,
            stageDetail=final_stage_detail,
            bootstrapReady=True,
            bootstrap=bootstrap,
            completedAt=_utcnow_iso(),
        )
    except Exception as exc:
        failed_stage_label, failed_stage_detail = _derive_workbench_stage_meta('failed', '统一分析会话失败')
        _update_workbench_session(
            session_id,
            status='failed',
            phase='failed',
            progress=0,
            message='统一分析会话失败',
            stageLabel=failed_stage_label,
            stageDetail=failed_stage_detail,
            error=str(exc),
            completedAt=_utcnow_iso(),
        )


def _build_layer_state(status: str, sections: Any, *, visible: bool = True, degraded: bool = False, degradation_codes: Optional[Any] = None, deferred_sections: Optional[Any] = None, user_message: Optional[str] = None) -> Dict[str, Any]:
    return {
        'status': status,
        'visible': visible,
        'completed_sections': list(sections or []),
        'degraded': degraded,
        'degradation_codes': list(degradation_codes or []),
        'deferred_sections': list(deferred_sections or []),
        'user_message': user_message,
    }


def _append_unique(items: list, value: Any) -> None:
    if value not in items:
        items.append(value)


def _record_layer_degradation(layer_states: Dict[str, Any], degradation_summary: list, skipped_or_deferred_work: list, *, layer: str, stage: str, reason_code: str, status_after_degrade: str, timeout_seconds: Optional[float], user_message: str, retry_mode: str = 'on_demand', deferred_section: Optional[str] = None) -> None:
    layer_state = layer_states.setdefault(layer, _build_layer_state(status_after_degrade, [], visible=(layer != 'deferred_background')))
    layer_state['status'] = status_after_degrade
    layer_state['degraded'] = True
    _append_unique(layer_state.setdefault('degradation_codes', []), reason_code)
    if deferred_section:
        _append_unique(layer_state.setdefault('deferred_sections', []), deferred_section)
    layer_state['user_message'] = user_message

    event = {
        'layer': layer,
        'stage': stage,
        'reason_code': reason_code,
        'status_after_degrade': status_after_degrade,
        'timeout_seconds': timeout_seconds,
        'user_message': user_message,
        'retry_mode': retry_mode,
    }
    if event not in degradation_summary:
        degradation_summary.append(event)
    if event not in skipped_or_deferred_work:
        skipped_or_deferred_work.append(event)


def _get_llm_timeout_seconds() -> float:
    raw_value = os.getenv('FH_LLM_TIMEOUT_SECONDS', '12.0')
    try:
        timeout_seconds = float(raw_value)
    except (TypeError, ValueError):
        timeout_seconds = 12.0
    return max(1.0, timeout_seconds)


def _get_partition_llm_parallel_workers(total_items: int) -> int:
    raw_value = os.getenv('FH_PARTITION_LLM_PARALLEL_WORKERS', '1')
    try:
        configured_workers = int(raw_value)
    except (TypeError, ValueError):
        configured_workers = 1
    safe_workers = max(1, min(configured_workers, 16))
    if total_items <= 0:
        return 1
    return max(1, min(safe_workers, total_items))


def _get_path_llm_parallel_workers(task_count: int) -> int:
    raw_value = os.getenv('FH_PATH_LLM_PARALLEL_WORKERS', '1')
    try:
        configured_workers = int(raw_value)
    except (TypeError, ValueError):
        configured_workers = 1
    safe_workers = max(1, min(configured_workers, 8))
    if task_count <= 0:
        return 1
    return max(1, min(safe_workers, task_count))


def _is_path_llm_task_parallel_enabled() -> bool:
    return _read_env_bool('FH_ENABLE_PATH_LLM_TASK_PARALLEL', False)


def _get_cfg_dfg_llm_explain_max_paths_per_partition() -> int:
    raw_value = os.getenv('FH_CFG_DFG_LLM_EXPLAIN_MAX_PATHS_PER_PARTITION', '1')
    try:
        max_paths = int(raw_value)
    except (TypeError, ValueError):
        max_paths = 1
    return max(0, min(max_paths, 12))


def _resolve_parallel_llm_agent(fallback_agent: Optional[CodeUnderstandingAgent], *, use_thread_local_agent: bool) -> Optional[CodeUnderstandingAgent]:
    if not use_thread_local_agent:
        return fallback_agent if fallback_agent is not None else _create_code_understanding_agent()

    local_agent = getattr(_parallel_llm_agent_local, 'agent', None)
    if local_agent is None:
        local_agent = _create_code_understanding_agent()
        if local_agent is None:
            local_agent = fallback_agent
        setattr(_parallel_llm_agent_local, 'agent', local_agent)
    return local_agent


def _run_partition_llm_enhance_task(
    partition_payload: Dict[str, Any],
    analyzer_report: Any,
    project_path: str,
    llm_timeout_seconds: Optional[float],
    llm_agent_for_partition: Any,
    *,
    use_thread_local_agent: bool,
) -> Dict[str, Any]:
    agent = _resolve_parallel_llm_agent(llm_agent_for_partition, use_thread_local_agent=use_thread_local_agent)
    if agent is None:
        return {
            'ok': False,
            'error': 'llm_agent_unavailable',
            'is_timeout': False,
            'enhanced_partition': partition_payload,
        }

    started_at = time.perf_counter() if llm_timeout_seconds is not None else None
    try:
        enhanced_partition = agent.enhance_partition_with_llm(
            partition_payload,
            analyzer_report,
            project_path,
        )
    except Exception as error:
        return {
            'ok': False,
            'error': str(error),
            'is_timeout': isinstance(error, TimeoutError) or 'timeout' in str(error).lower(),
            'enhanced_partition': partition_payload,
        }

    elapsed_seconds = None
    timeout_exceeded = False
    if llm_timeout_seconds is not None and started_at is not None:
        elapsed_seconds = time.perf_counter() - started_at
        timeout_exceeded = elapsed_seconds > llm_timeout_seconds

    if timeout_exceeded:
        return {
            'ok': False,
            'error': f'partition_llm_timeout>{llm_timeout_seconds}s',
            'is_timeout': True,
            'enhanced_partition': partition_payload,
            'elapsed_seconds': elapsed_seconds,
        }

    return {
        'ok': True,
        'error': None,
        'is_timeout': False,
        'enhanced_partition': enhanced_partition,
        'elapsed_seconds': elapsed_seconds,
    }


def _run_path_cfg_dfg_explain_task(
    *,
    path: List[str],
    path_cfg: Optional[Dict[str, Any]],
    path_dfg: Optional[Dict[str, Any]],
    analyzer_report: Any,
    inputs: List[Dict[str, Any]],
    outputs: List[Dict[str, Any]],
    llm_agent: Any,
    use_thread_local_agent: bool,
) -> Dict[str, Any]:
    agent = _resolve_parallel_llm_agent(llm_agent, use_thread_local_agent=use_thread_local_agent)
    if agent is None:
        return {'ok': False, 'error': 'llm_agent_unavailable', 'markdown': None}
    try:
        explain = agent.explain_path_cfg_dfg(
            path=path,
            cfg_dot=(path_cfg or {}).get('dot', ''),
            dfg_dot=(path_dfg or {}).get('dot', ''),
            analyzer_report=analyzer_report,
            inputs=inputs,
            outputs=outputs,
        )
        return {'ok': True, 'error': None, 'markdown': (explain or {}).get('markdown')}
    except Exception as error:
        return {'ok': False, 'error': str(error), 'markdown': None}


def _run_path_dataflow_mermaid_task(
    *,
    path: List[str],
    call_graph: Dict[str, Set[str]],
    analyzer_report: Any,
    partition_methods: Set[str],
    inputs: List[Dict[str, Any]],
    outputs: List[Dict[str, Any]],
    llm_agent: Any,
    path_dfg: Optional[Dict[str, Any]],
    use_thread_local_agent: bool,
) -> Dict[str, Any]:
    try:
        dataflow_mermaid = generate_path_level_dataflow_mermaid(
            path=path,
            call_graph=call_graph,
            analyzer_report=analyzer_report,
            partition_methods=partition_methods,
            inputs=inputs,
            outputs=outputs,
            llm_agent=llm_agent,
            path_dfg=path_dfg,
        )
        return {'ok': True, 'error': None, 'dataflow_mermaid': dataflow_mermaid}
    except Exception as error:
        return {'ok': False, 'error': str(error), 'dataflow_mermaid': None}


def _run_path_name_description_task(
    *,
    path: List[str],
    analyzer_report: Any,
    project_path: str,
    llm_agent: Any,
    use_thread_local_agent: bool,
) -> Dict[str, Any]:
    agent = _resolve_parallel_llm_agent(llm_agent, use_thread_local_agent=use_thread_local_agent)
    if agent is None:
        return {'ok': False, 'error': 'llm_agent_unavailable', 'path_info': None}
    try:
        path_info = agent.generate_path_name_and_description(
            path=path,
            analyzer_report=analyzer_report,
            project_path=project_path,
        )
        return {'ok': True, 'error': None, 'path_info': path_info}
    except Exception as error:
        return {'ok': False, 'error': str(error), 'path_info': None}


def _run_path_io_chain_task(
    *,
    path: List[str],
    analyzer_report: Any,
    inputs: List[Dict[str, Any]],
    outputs: List[Dict[str, Any]],
    call_graph: Dict[str, Set[str]],
    llm_agent: Any,
    use_thread_local_agent: bool,
) -> Dict[str, Any]:
    agent = _resolve_parallel_llm_agent(llm_agent, use_thread_local_agent=use_thread_local_agent)
    if agent is None:
        return {
            'ok': False,
            'error': 'llm_agent_unavailable',
            'io_graph': None,
            'call_chain_analysis': None,
        }
    try:
        io_graph = agent.generate_path_input_output_graph(
            path=path,
            analyzer_report=analyzer_report,
            inputs=inputs,
            outputs=outputs,
        )
        call_chain_analysis = agent.analyze_path_call_chain_type(
            path=path,
            call_graph=call_graph,
            analyzer_report=analyzer_report,
        )
        return {
            'ok': True,
            'error': None,
            'io_graph': io_graph,
            'call_chain_analysis': call_chain_analysis,
        }
    except Exception as error:
        return {
            'ok': False,
            'error': str(error),
            'io_graph': None,
            'call_chain_analysis': None,
        }


def _get_index_rebuild_visibility_timeout_seconds() -> float:
    raw_value = os.getenv('FH_INDEX_REBUILD_VISIBILITY_TIMEOUT', '2.0')
    try:
        timeout_seconds = float(raw_value)
    except (TypeError, ValueError):
        timeout_seconds = 2.0
    return max(0.1, timeout_seconds)


def _run_partition_llm_semantics_pass(
    *,
    timing: Any,
    phase_id: str,
    update_status_text: str,
    pass_title: str,
    use_limit: int,
    enable_partition_llm_semantics: bool,
    llm_agent_for_partition: Any,
    partitions: Any,
    analyzer_report: Any,
    project_path: str,
    layer_states: Dict[str, Any],
    degradation_summary: list,
    skipped_or_deferred_work: list,
    timeout_degrade_stage: Optional[str],
    timeout_reason_code: Optional[str],
    timeout_user_message_template: Optional[str],
    timeout_deferred_section: Optional[str],
    disabled_message: str,
) -> None:
    update_analysis_status(progress=82, status=update_status_text)
    print(f"\n[app.py] {'='*60}", flush=True)
    print(f"[app.py] 🧠 {pass_title}", flush=True)
    print(f"[app.py]   配置: 最多处理 {use_limit} 个分区", flush=True)
    print(f"[app.py] {'='*60}\n", flush=True)

    timing.start_phase(phase_id, layer='advanced_visible', blocking=True)
    try:
        if enable_partition_llm_semantics and llm_agent_for_partition and partitions:
            partitions_to_enhance = partitions if use_limit <= 0 else partitions[:use_limit]
            enhanced_count = 0
            llm_timeout_seconds = _get_llm_timeout_seconds() if timeout_degrade_stage else None
            total_partitions = len(partitions_to_enhance)
            partition_llm_workers = _get_partition_llm_parallel_workers(total_partitions)
            use_parallel = partition_llm_workers > 1 and total_partitions > 1
            print(
                f"[workset5] parallel_stage=partition_llm_semantics workers={partition_llm_workers} "
                f"partitions={total_partitions} mode={'parallel' if use_parallel else 'serial'}",
                flush=True,
            )

            partition_results_by_index: Dict[int, Dict[str, Any]] = {}
            progress_done = 0

            if use_parallel:
                with ThreadPoolExecutor(max_workers=partition_llm_workers, thread_name_prefix='fh-partition-llm') as executor:
                    future_to_context = {}
                    for idx, partition_to_enhance in enumerate(partitions_to_enhance):
                        partition_id_to_enhance = partition_to_enhance.get('partition_id', 'unknown')
                        partition_name_before = partition_to_enhance.get('name', 'unknown')
                        print(f"[app.py]   [{idx+1}/{total_partitions}] 提交分区LLM任务: {partition_id_to_enhance}", flush=True)
                        print(f"[app.py]     分区名称（增强前）: {partition_name_before}", flush=True)
                        future = executor.submit(
                            _run_partition_llm_enhance_task,
                            partition_to_enhance.copy(),
                            analyzer_report,
                            project_path,
                            llm_timeout_seconds,
                            llm_agent_for_partition,
                            use_thread_local_agent=True,
                        )
                        future_to_context[future] = (idx, partition_id_to_enhance)

                    for future in as_completed(future_to_context):
                        idx, partition_id_to_enhance = future_to_context[future]
                        try:
                            partition_results_by_index[idx] = future.result()
                        except Exception as error:
                            partition_results_by_index[idx] = {
                                'ok': False,
                                'error': str(error),
                                'is_timeout': isinstance(error, TimeoutError) or 'timeout' in str(error).lower(),
                                'enhanced_partition': partitions_to_enhance[idx],
                            }
                        progress_done += 1
                        progress_pct = 82 + int((progress_done / total_partitions) * 3)
                        update_analysis_status(progress=progress_pct, status=f'步骤6.5.6/7: LLM分析分区 {progress_done}/{total_partitions}...')
            else:
                for idx, partition_to_enhance in enumerate(partitions_to_enhance):
                    partition_id_to_enhance = partition_to_enhance.get('partition_id', 'unknown')
                    partition_name_before = partition_to_enhance.get('name', 'unknown')

                    print(f"[app.py]   [{idx+1}/{total_partitions}] 处理分区: {partition_id_to_enhance}", flush=True)
                    print(f"[app.py]     分区名称（增强前）: {partition_name_before}", flush=True)
                    partition_results_by_index[idx] = _run_partition_llm_enhance_task(
                        partition_to_enhance.copy(),
                        analyzer_report,
                        project_path,
                        llm_timeout_seconds,
                        llm_agent_for_partition,
                        use_thread_local_agent=False,
                    )
                    progress_done += 1
                    progress_pct = 82 + int((progress_done / total_partitions) * 3)
                    update_analysis_status(progress=progress_pct, status=f'步骤6.5.6/7: LLM分析分区 {progress_done}/{total_partitions}...')

            for idx, partition_to_enhance in enumerate(partitions_to_enhance):
                partition_id_to_enhance = partition_to_enhance.get('partition_id', 'unknown')
                result = partition_results_by_index.get(idx) or {
                    'ok': False,
                    'error': 'partition_result_missing',
                    'is_timeout': False,
                    'enhanced_partition': partition_to_enhance,
                }

                if result.get('ok'):
                    enhanced_partition = result.get('enhanced_partition') or {}
                    partition_to_enhance.update(enhanced_partition)
                    partition_name_after = partition_to_enhance.get('name', 'unknown')
                    partition_description = partition_to_enhance.get('description', '')
                    print(f"[app.py]     ✓ LLM语义分析完成", flush=True)
                    print(f"[app.py]     分区名称（增强后）: {partition_name_after}", flush=True)
                    desc_preview = partition_description[:80] + '...' if len(partition_description) > 80 else partition_description
                    print(f"[app.py]     分区描述: {desc_preview}", flush=True)
                    enhanced_count += 1
                    continue

                error_message = result.get('error') or 'unknown_error'
                is_timeout_error = bool(result.get('is_timeout'))
                print(f"[app.py]     ⚠️ LLM语义分析失败: {error_message}，使用原始分区信息", flush=True)
                if (
                    timeout_degrade_stage
                    and timeout_reason_code
                    and timeout_user_message_template
                    and is_timeout_error
                ):
                    _record_layer_degradation(
                        layer_states,
                        degradation_summary,
                        skipped_or_deferred_work,
                        layer='advanced_visible',
                        stage=timeout_degrade_stage,
                        reason_code=timeout_reason_code,
                        status_after_degrade='available_on_demand',
                        timeout_seconds=llm_timeout_seconds,
                        user_message=timeout_user_message_template.format(partition_id=partition_id_to_enhance),
                        retry_mode='on_demand',
                        deferred_section=timeout_deferred_section,
                    )

            print(f"\n[app.py] ✅ LLM语义分析完成: 成功增强 {enhanced_count}/{total_partitions} 个分区", flush=True)
        else:
            print(disabled_message, flush=True)
    finally:
        print(f"[app.py] {'='*60}\n", flush=True)
        timing.end_phase(phase_id)
        _safe_flush()


def _build_pipeline_structure(execution_profile: Dict[str, Any]) -> Dict[str, Any]:
    effective_steps = execution_profile.get('effective_steps') or {}
    return {
        'schema_version': 'workset7.v1',
        'light_chain': {
            'goal': 'default_visible and expand_visible first',
            'steps': [
                'partitioning_and_graphs',
                'entry_points_and_fqmn',
                'io_and_light_aggregation',
            ],
            'publish_points': [55, 80],
        },
        'heavy_chain': {
            'goal': 'advanced/deferred capabilities become optional or degradable',
            'steps': [
                {'id': 'partition_llm_semantics', 'enabled': bool(effective_steps.get('partition_llm_semantics'))},
                {'id': 'path_cfg_dfg_io_total', 'enabled': bool(effective_steps.get('path_cfg_dfg_io'))},
                {'id': 'index_rebuild', 'enabled': bool(effective_steps.get('index_rebuild_immediate') or effective_steps.get('index_rebuild_deferred'))},
            ],
            'publish_points': [90, 96],
        },
        'boundary_state': {
            'advanced_visible_default_status': 'available_on_demand',
            'deferred_background_default_status': execution_profile.get('step_visibility', {}).get('index_rebuild', {}).get('status', 'available_on_demand'),
        },
    }


def _build_function_hierarchy_snapshot(
    *,
    project_path: str,
    partitions: Any,
    partition_analyses: Dict[str, Any],
    execution_profile: Dict[str, Any],
    layer_states: Dict[str, Any],
    include_expand: bool,
    include_advanced: bool,
    entry_points_shadow: Optional[Dict[str, Any]] = None,
    process_shadow: Optional[Dict[str, Any]] = None,
    community_shadow: Optional[Dict[str, Any]] = None,
    performance_baseline: Optional[Dict[str, Any]] = None,
    degradation_summary: Optional[Any] = None,
    skipped_or_deferred_work: Optional[Any] = None,
    index_rebuild_status: Optional[Dict[str, Any]] = None,
    pipeline_structure: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    hierarchy_layer = []
    for partition in partitions or []:
        if isinstance(partition, dict):
            hierarchy_layer.append(copy.deepcopy(partition))

    snapshot_partition_analyses: Dict[str, Any] = {}
    for partition_id, analysis in (partition_analyses or {}).items():
        if not isinstance(analysis, dict):
            continue
        entry: Dict[str, Any] = {}
        for key, value in analysis.items():
            if key in {'entry_points', 'fqns', 'inputs', 'outputs', 'dataflow', 'controlflow'} and not include_expand:
                continue
            if key in {'path_analyses'} and not include_advanced:
                continue
            entry[key] = copy.deepcopy(value)
        snapshot_partition_analyses[partition_id] = entry

    snapshot = {
        'hierarchy': {
            'layer1_functions': hierarchy_layer,
            'metadata': {
                'project_path': project_path,
                'total_partitions': len(partitions or []),
                'total_methods': sum(len((item.get('methods') or [])) for item in hierarchy_layer),
            },
        },
        'partition_analyses': snapshot_partition_analyses,
        'execution_profile': copy.deepcopy(execution_profile),
        'result_layers': copy.deepcopy(layer_states),
        'degradation_summary': copy.deepcopy(list(degradation_summary or [])),
        'skipped_or_deferred_work': copy.deepcopy(list(skipped_or_deferred_work or [])),
        'pipeline_structure': copy.deepcopy(pipeline_structure or {}),
    }

    if include_advanced:
        snapshot['entry_points_shadow'] = copy.deepcopy(entry_points_shadow)
        snapshot['process_shadow'] = copy.deepcopy(process_shadow)
        snapshot['community_shadow'] = copy.deepcopy(community_shadow)
    if performance_baseline is not None:
        snapshot['performance_baseline'] = copy.deepcopy(performance_baseline)
    if index_rebuild_status is not None:
        snapshot['index_rebuild_status'] = copy.deepcopy(index_rebuild_status)
    return snapshot


def _compute_code_state_fingerprint(project_path: str) -> str:
    hash_builder = hashlib.sha256()
    ignore_dirs = {'.git', '__pycache__', '.venv', 'venv', 'node_modules', '.idea', '.pytest_cache'}
    include_suffixes = {
        '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.scss', '.json', '.yaml', '.yml', '.toml', '.md'
    }

    normalized_project_path = os.path.normpath(project_path)
    for root, dirs, files in os.walk(normalized_project_path):
        dirs[:] = [directory for directory in dirs if directory not in ignore_dirs]
        for filename in sorted(files):
            suffix = os.path.splitext(filename)[1].lower()
            if suffix not in include_suffixes:
                continue
            file_path = os.path.join(root, filename)
            try:
                stat = os.stat(file_path)
            except OSError:
                continue
            relative_path = os.path.relpath(file_path, normalized_project_path).replace('\\', '/')
            hash_builder.update(relative_path.encode('utf-8', errors='ignore'))
            hash_builder.update(str(int(stat.st_mtime_ns)).encode('utf-8'))
            hash_builder.update(str(int(stat.st_size)).encode('utf-8'))
    return hash_builder.hexdigest()


def _json_signature(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def _build_layer_cache_signatures(*, code_state_fingerprint: str, execution_profile: Dict[str, Any], max_paths_to_analyze: int, path_analysis_partition_limit: int, filter_single_node_paths: bool) -> Dict[str, str]:
    base_payload = {
        'pipeline_version': FUNCTION_HIERARCHY_PIPELINE_VERSION,
        'code_state_fingerprint': code_state_fingerprint,
        'default_visible': execution_profile['layers']['default_visible'],
        'expand_visible': execution_profile['layers']['expand_visible'],
    }
    return {
        'default_visible': _json_signature(base_payload),
        'expand_visible': _json_signature(base_payload),
        'advanced_visible': _json_signature(
            {
                **base_payload,
                'advanced_visible': execution_profile['layers']['advanced_visible'],
                'path_llm_analysis': execution_profile['effective_steps']['path_llm_analysis'],
                'path_supplement_generation': execution_profile['effective_steps']['path_supplement_generation'],
                'path_cfg_dfg_io': execution_profile['effective_steps']['path_cfg_dfg_io'],
                'cfg_dfg_llm_explain': execution_profile['effective_steps']['cfg_dfg_llm_explain'],
                'max_paths_to_analyze': max_paths_to_analyze,
                'path_analysis_partition_limit': path_analysis_partition_limit,
                'filter_single_node_paths': filter_single_node_paths,
            }
        ),
    }


def _log_layer_cache_decision(layer: str, status: str, reason: str) -> None:
    log_print(f"[workset4] layer={layer} status={status} reason={reason}")


def _build_partition_cache_signature(partition: Dict[str, Any], partition_paths_map: Dict[str, Any], advanced_signature: str) -> str:
    partition_id = partition.get('partition_id', 'unknown')
    payload = {
        'advanced_signature': advanced_signature,
        'partition_id': partition_id,
        'methods': list(partition.get('methods', []) or []),
        'paths_map': partition_paths_map.get(partition_id, {}),
    }
    return _json_signature(payload)


def _hydrate_cached_expand_support(expand_support: Dict[str, Any]) -> Tuple[Any, Any, Any, Any, Any, Any]:
    analyzer_stub = SimpleNamespace(
        report=expand_support.get('analyzer_report'),
        data_flow_analyzer=expand_support.get('data_flow_analyzer'),
    )
    return (
        analyzer_stub,
        copy.deepcopy(expand_support.get('call_graph') or {}),
        copy.deepcopy(expand_support.get('partitions') or []),
        copy.deepcopy(expand_support.get('partition_analyses') or {}),
        copy.deepcopy(expand_support.get('partition_paths_map') or {}),
        copy.deepcopy(expand_support.get('entry_points_map') or {}),
    )


def generate_folder_nodes(project_path, partitions):
    """
    基于功能分区和项目文件夹生成第2层的文件夹节点（使用绝对路径）
    
    Args:
        project_path: 项目根路径
        partitions: 功能分区列表（每个分区包含 folders 列表，可能是绝对路径或相对路径）
    
    Returns:
        文件夹节点列表（使用绝对路径）
    """
    folders = []
    seen_folders = set()  # 避免重复
    
    try:
        # 为每个功能分区扫描其对应的文件夹
        for partition in partitions:
            for folder_path in partition.folders:
                # 处理绝对路径和相对路径
                if os.path.isabs(folder_path):
                    abs_folder_path = folder_path
                else:
                    abs_folder_path = os.path.join(project_path, folder_path)
                
                # 标准化路径（处理 .. 和 .）
                abs_folder_path = os.path.normpath(abs_folder_path)
                
                if abs_folder_path in seen_folders:
                    continue
                
                if os.path.isdir(abs_folder_path):
                    # 统计该文件夹下的代码统计信息
                    class_count = 0
                    method_count = 0
                    function_count = 0
                    
                    # 扫描文件夹下的 Python 文件
                    for root, dirs, files in os.walk(abs_folder_path):
                        # 跳过常见的非代码目录
                        dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', '.venv', 'venv']]
                        for file in files:
                            if file.endswith('.py'):
                                # 简单统计（可以优化为实际解析）
                                try:
                                    with open(os.path.join(root, file), 'r', encoding='utf-8', errors='ignore') as f:
                                        content = f.read()
                                        # 简单统计类和方法
                                        class_count += content.count('class ')
                                        method_count += content.count('def ')
                                        function_count += content.count('def ') - content.count('    def ')  # 粗略估算
                                except:
                                    pass
                    
                    folder_node = FolderNode(
                        folder_path=abs_folder_path,  # 使用绝对路径
                        parent_function=partition.name,
                        stats=FolderStats(
                            class_count=class_count,
                            method_count=method_count,
                            function_count=function_count
                        )
                    )
                    folders.append(folder_node)
                    seen_folders.add(abs_folder_path)
        
        # 如果没有找到任何文件夹，尝试从项目结构创建
        if not folders and partitions:
            # 扫描项目根目录下的所有文件夹
            for item in os.listdir(project_path):
                item_path = os.path.join(project_path, item)
                if os.path.isdir(item_path) and not item.startswith('.') and not item.startswith('__'):
                    abs_path = os.path.normpath(item_path)
                    if abs_path not in seen_folders:
                        # 尝试匹配到功能分区
                        matched_partition = None
                        for partition in partitions:
                            if item.lower() in [k.lower() for k in partition.keywords]:
                                matched_partition = partition
                                break
                        
                        if not matched_partition and partitions:
                            matched_partition = partitions[0]  # 默认匹配第一个
                        
                        if matched_partition:
                            folder_node = FolderNode(
                                folder_path=abs_path,
                                parent_function=matched_partition.name,
                                stats=FolderStats(class_count=0, method_count=0)
                            )
                            folders.append(folder_node)
                            seen_folders.add(abs_path)
    
    except Exception as e:
        print(f"[app.py] ⚠️ 生成文件夹节点失败: {e}", flush=True)
        import traceback
        _safe_traceback_print()
    
    return folders


def deduplicate_and_resolve_name_conflicts(partitions):
    """
    对分区进行去重和名称冲突处理
    
    Args:
        partitions: 分区列表，每个分区包含partition_id、methods、name等
        
    Returns:
        去重后的分区列表
    """
    if not partitions:
        return partitions
    
    print(f"[app.py] 开始去重和名称冲突处理，原始分区数: {len(partitions)}", flush=True)
    
    # 步骤1：按方法集合去重（完全相同的分区）
    seen_method_sets = {}
    unique_partitions = []
    duplicate_count = 0
    
    for partition in partitions:
        methods = partition.get("methods", [])
        method_set = frozenset(methods)
        
        if method_set in seen_method_sets:
            # 发现重复分区，合并信息
            existing = seen_method_sets[method_set]
            duplicate_count += 1
            print(f"[app.py]   发现重复分区: {partition.get('partition_id')} 与 {existing.get('partition_id')} 方法集合相同", flush=True)
            
            # 合并统计信息（如果新分区有更好的信息）
            if partition.get("modularity", 0) > existing.get("modularity", 0):
                existing["modularity"] = partition.get("modularity", 0)
            if partition.get("description") and not existing.get("description"):
                existing["description"] = partition.get("description")
            if partition.get("folders") and not existing.get("folders"):
                existing["folders"] = partition.get("folders")
        else:
            seen_method_sets[method_set] = partition
            unique_partitions.append(partition)
    
    if duplicate_count > 0:
        print(f"[app.py]   合并了 {duplicate_count} 个重复分区", flush=True)
    
    # 步骤2：处理名称冲突（名称相同但方法不同）
    name_count = {}
    name_to_partitions = {}
    
    for partition in unique_partitions:
        name = partition.get("name", "未知分区")
        if name not in name_to_partitions:
            name_to_partitions[name] = []
        name_to_partitions[name].append(partition)
    
    # 为有冲突的名称添加后缀
    conflict_count = 0
    for name, same_name_partitions in name_to_partitions.items():
        if len(same_name_partitions) > 1:
            conflict_count += len(same_name_partitions) - 1
            print(f"[app.py]   发现名称冲突: '{name}' 有 {len(same_name_partitions)} 个分区", flush=True)
            
            # 为除第一个外的所有分区添加后缀
            for idx, partition in enumerate(same_name_partitions[1:], start=1):
                original_name = partition.get("name", "未知分区")
                partition["name"] = f"{original_name}-{idx}"
                partition["original_name"] = original_name  # 保存原始名称
                # partition["name_conflict"] = True  # 标记为名称冲突 (User requested removal of red flag)
                print(f"[app.py]     重命名: {partition.get('partition_id')} -> {partition['name']}", flush=True)
    
    if conflict_count > 0:
        print(f"[app.py]   处理了 {conflict_count} 个名称冲突", flush=True)
    
    # 步骤3：更新partition_id以确保唯一性
    for idx, partition in enumerate(unique_partitions):
        if "partition_id" not in partition or not partition["partition_id"]:
            partition["partition_id"] = f"partition_{idx}"
        else:
            # 确保partition_id唯一
            base_id = partition["partition_id"]
            if base_id.startswith("partition_"):
                partition["partition_id"] = base_id
            else:
                partition["partition_id"] = f"partition_{idx}_{base_id}"
    
    print(f"[app.py] ✅ 去重和名称冲突处理完成，最终分区数: {len(unique_partitions)}", flush=True)
    
    return unique_partitions


def _convert_partitions_to_dicts(function_partitions, entity_to_function_map):
    """
    将FunctionPartition列表转换为字典格式（供阶段4使用）
    
    Args:
        function_partitions: FunctionPartition对象列表
        entity_to_function_map: 实体到功能分区的映射 {entity_id: function_name}
    
    Returns:
        分区字典列表，每个字典包含partition_id、methods等
    """
    partition_dicts = []
    
    # 构建功能分区名到实体列表的映射
    function_to_entities = {}
    for entity_id, function_name in entity_to_function_map.items():
        if function_name not in function_to_entities:
            function_to_entities[function_name] = []
        function_to_entities[function_name].append(entity_id)
    
    # 提取方法签名（从method_开头的实体ID中提取）
    for i, func_partition in enumerate(function_partitions):
        function_name = func_partition.name
        entities = function_to_entities.get(function_name, [])
        
        # 提取方法签名（从method_ClassName.methodName格式中提取）
        methods = []
        for entity_id in entities:
            if entity_id.startswith('method_'):
                # 提取方法签名（去掉method_前缀）
                method_sig = entity_id[7:]  # 去掉"method_"前缀
                methods.append(method_sig)
            elif entity_id.startswith('function_'):
                # 提取函数名
                func_name = entity_id[9:]  # 去掉"function_"前缀
                methods.append(func_name)
        
        partition_dict = {
            "partition_id": f"partition_{i}",
            "name": function_name,
            "methods": methods,
            "size": len(methods)
        }
        partition_dicts.append(partition_dict)
    
    return partition_dicts


def generate_default_partitions(project_path):
    """
    基于项目文件结构自动生成功能分区
    扫描项目的文件夹结构，识别主要的功能模块
    """
    partitions = []
    
    # 扫描项目结构
    try:
        folder_names = set()
        for item in os.listdir(project_path):
            item_path = os.path.join(project_path, item)
            if os.path.isdir(item_path) and not item.startswith('.') and not item.startswith('__'):
                folder_names.add(item)
        
        print(f"[app.py]   - 检测到的文件夹: {', '.join(sorted(folder_names))}", flush=True)
        
        # 如果项目有明确的模块名，作为分区
        if folder_names:
            # 为每个主要文件夹创建一个分区
            for folder in sorted(folder_names):
                partition = FunctionPartition(
                    name=folder,
                    description=f"模块: {folder}",
                    folders=[folder],
                    keywords=[folder]
                )
                partitions.append(partition)
        
        # 如果没有明确的文件夹或文件夹太少，使用默认分区
        if len(partitions) < 2:
            print(f"[app.py]   - 文件夹结构不明确，使用智能默认分区", flush=True)
            
            # 基于项目名称和内容推荐分区
            project_name = os.path.basename(project_path)
            partitions = [
                FunctionPartition(
                    name="核心业务层",
                    description=f"{project_name} 的核心业务逻辑和主要功能",
                    folders=[],
                    keywords=['main', 'core', 'business', 'service']
                ),
                FunctionPartition(
                    name="工具辅助层",
                    description="提供工具函数和辅助功能的模块",
                    folders=[],
                    keywords=['util', 'helper', 'common', 'base']
                ),
                FunctionPartition(
                    name="外部接口层",
                    description="与外部系统交互的接口和API",
                    folders=[],
                    keywords=['api', 'interface', 'client', 'gateway']
                )
            ]
    
    except Exception as e:
        print(f"[app.py]   - ⚠️ 自动检测文件夹失败: {e}", flush=True)
        # 返回空列表让主程序使用更完整的默认分区
        partitions = []
    
    return partitions if partitions else []


def analyze_project(project_path, *, return_artifacts: bool = False):
    """后台分析项目 - 仅第3层代码图"""
    # Ensure UTF-8 output stream without replacing/rewrapping stdout
    _ensure_utf8_output_stream()
    
    try:
        update_analysis_status(
            is_analyzing=True,
            error=None,
            progress=10,
            status='初始化分析器...'
        )
        
        print(f"\n{'='*60}", flush=True)
        print(f"[app.py] 🚀 开始分析项目: {project_path}", flush=True)
        print(f"{'='*60}", flush=True)
        
        # 初始化分析器
        print(f"[app.py] 初始化分析器...", flush=True)
        _safe_flush()
        analyzer = CodeAnalyzer(project_path)
        print(f"[app.py] ✅ 分析器初始化完成", flush=True)
        _safe_flush()
        
        # 更新进度：初始化完成，准备扫描项目
        update_analysis_status(
            progress=20,
            status='正在扫描项目...'
        )
        print(f"[app.py] 进度: 20% - 扫描项目文件...", flush=True)
        _safe_flush()
        
        # 分析代码
        print(f"[app.py] 开始分析代码...", flush=True)
        _safe_flush()
        graph_data = analyzer.analyze(project_path)
        
        # 保存report供后续API使用
        report = analyzer.report
        
        nodes_count = len(graph_data.get('nodes', []))
        edges_count = len(graph_data.get('edges', []))
        print(f"[app.py] ✅ 代码分析完成", flush=True)
        print(f"[app.py]   - 节点数: {nodes_count}", flush=True)
        print(f"[app.py]   - 边数: {edges_count}", flush=True)
        _safe_flush()
        
        # 标准化项目路径（处理Windows路径的反斜杠）
        normalized_project_path = os.path.normpath(project_path)
        
        # 保存分析结果到缓存（通过DataAccessor）
        data_accessor.save_main_analysis(normalized_project_path, graph_data)
        data_accessor.save_report(normalized_project_path, report)
        print(f"[app.py] 💾 主分析结果已保存到缓存: {normalized_project_path}", flush=True)
        
        # 更新进度：代码分析完成，开始生成可视化数据
        update_analysis_status(
            progress=90,
            status='正在生成可视化数据...'
        )
        print(f"[app.py] 进度: 90% - 生成可视化数据...", flush=True)
        _safe_flush()
        
        # 保存分析结果到缓存（在更新状态之前，通过DataAccessor）
        data_accessor.save_main_analysis(normalized_project_path, graph_data)
        data_accessor.save_report(normalized_project_path, report)
        print(f"[app.py] 💾 主分析结果已保存到缓存: {normalized_project_path}", flush=True)

        try:
            _project_library_storage.save_graph_data(normalized_project_path, graph_data)
            _project_library_storage.save_project_profile(
                normalized_project_path,
                {
                    'project_name': os.path.basename(normalized_project_path) or 'unknown_project',
                    'analysis_timestamp': str((graph_data.get('metadata') or {}).get('analysis_timestamp') or datetime.utcnow().isoformat() + 'Z'),
                    'has_graph': True,
                },
            )
        except Exception as storage_exc:
            print(f"[app.py] ⚠️ 主图谱持久化失败: {storage_exc}", flush=True)
        
        # 生成图形数据并完成分析
        update_analysis_status(
            progress=100,
            status='分析完成！',
            data=graph_data,
            report=report,  # 保存report
            is_analyzing=False
        )
        print(f"[app.py] 进度: 100% - 分析完成！", flush=True)
        print(f"[app.py] {'='*60}", flush=True)
        print(f"[app.py] ✅✅✅ 分析成功完成！", flush=True)
        print(f"[app.py] {'='*60}\n", flush=True)
        _safe_flush()

        if return_artifacts:
            return {
                'graph_data': graph_data,
                'report': report,
                'analyzer': analyzer,
            }
        
    except Exception as e:
        print(f"\n[app.py] {'='*60}", flush=True)
        print(f"[app.py] ❌ 分析出错", flush=True)
        print(f"[app.py] 错误类型: {type(e).__name__}", flush=True)
        print(f"[app.py] 错误信息: {e}", flush=True)
        print(f"[app.py] {'='*60}", flush=True)
        import traceback
        _safe_traceback_print()
        _safe_flush()
        update_analysis_status(
            error=str(e),
            is_analyzing=False,
            progress=0,
            status='分析失败'
        )
        print(f"[app.py] {'='*60}\n", flush=True)
        _safe_flush()
        return None


def analyze_hierarchy(project_path, use_llm=False):
    """后台分析项目四层层级结构"""
    # Ensure UTF-8 output stream without replacing/rewrapping stdout
    _ensure_utf8_output_stream()
    
    try:
        update_analysis_status(
            is_analyzing=True,
            error=None,
            progress=5,
            status='初始化分析...'
        )
        
        print(f"\n{'='*60}", flush=True)
        print(f"[app.py] 🚀 开始构建四层嵌套可视化: {project_path}", flush=True)
        print(f"{'='*60}", flush=True)
        
        # ===== 步骤1：代码分析（第3层） =====
        update_analysis_status(progress=10, status='步骤1/5: 分析代码...')
        print(f"[app.py] 步骤1: 分析代码（构建第3层CodeGraph）...", flush=True)
        _safe_flush()
        
        analyzer = CodeAnalyzer(project_path)
        graph_data = analyzer.analyze(project_path)
        print(f"[app.py] ✅ 代码分析完成", flush=True)
        _safe_flush()
        
        # ===== 步骤2：提取代码注释和 README =====
        update_analysis_status(progress=20, status='步骤2/5: 提取代码注释和README...')
        print(f"[app.py] 步骤2: 提取代码注释和 README...", flush=True)
        _safe_flush()
        
        # 提取代码注释
        from parsers.comment_extractor import CommentExtractor
        comments_summary = {}
        try:
            # 为每个 Python 文件提取注释
            python_files = []
            for root, dirs, files in os.walk(project_path):
                dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.venv', 'venv', 'node_modules']]
                for file in files:
                    if file.endswith('.py'):
                        python_files.append(os.path.join(root, file))
            
            print(f"[app.py]   提取 {len(python_files)} 个文件的注释...", flush=True)
            for file_path in python_files[:50]:  # 限制前50个文件，避免太慢
                try:
                    extractor = CommentExtractor(file_path)
                    comments = extractor.extract_all_comments()
                    # 保存关键注释（docstring）
                    for entity_id, docstring in comments.get('docstrings', {}).items():
                        comments_summary[entity_id] = {
                            'comments': [docstring],
                            'file': file_path
                        }
                except Exception as e:
                    pass  # 忽略单个文件的错误
            
            print(f"[app.py] ✅ 提取了 {len(comments_summary)} 个代码元素的注释", flush=True)
        except Exception as e:
            print(f"[app.py] ⚠️ 注释提取失败: {e}", flush=True)
            comments_summary = {}
        
        # ===== 步骤3：LLM理解项目（第1层） =====
        partitions = []
        # 现在默认使用 LLM（除非明确禁用）
        try:
            update_analysis_status(progress=30, status='步骤3/5: 🤖 LLM分析项目结构...')
            print(f"\n[app.py] 步骤3: 🤖 调用LLM分析项目结构（使用图知识库）...", flush=True)
            _safe_flush()
            
            settings = _get_deepseek_runtime_settings()
            api_key = settings['api_key']
            base_url = settings['base_url']

            if not api_key:
                raise ValueError("DeepSeek 未配置 API Key，请检查 config/config.py 或环境变量 DEEPSEEK_API_KEY")
            
            print(f"[app.py]   - API密钥: {api_key[:10]}...", flush=True)
            print(f"[app.py]   - 初始化LLM Agent...", flush=True)
            agent = CodeUnderstandingAgent(api_key=api_key, base_url=base_url)
            
            print(f"[app.py]   - 加载项目信息...", flush=True)
            project_info = agent.load_project(project_path)
            print(f"[app.py]   - ✓ 项目加载完成: {project_info['name']} ({project_info['files_count']} 个Python文件)", flush=True)
            
            print(f"[app.py]   - 🤖 开始调用LLM API（使用图知识库摘要）...", flush=True)
            _safe_flush()
            
            # 传递图数据和注释摘要给 LLM
            partitions = agent.identify_function_partitions(
                project_info=project_info,
                graph_data=graph_data,  # 传递图数据用于生成图知识库摘要
                comments_summary=comments_summary  # 传递注释摘要
            )
            
            if partitions:
                print(f"[app.py] ✅ LLM分析成功！识别了 {len(partitions)} 个功能分区:", flush=True)
                for p in partitions:
                    print(f"[app.py]    ✓ {p.name}: {p.description[:40]}...", flush=True)
                    print(f"[app.py]       文件夹: {p.folders}", flush=True)
            else:
                print(f"[app.py] ⚠️ LLM返回了空的功能分区列表", flush=True)
            _safe_flush()
                
        except Exception as e:
            print(f"[app.py] ❌ LLM分析失败!", flush=True)
            print(f"[app.py]    错误类型: {type(e).__name__}", flush=True)
            print(f"[app.py]    错误信息: {str(e)}", flush=True)
            import traceback
            print(f"[app.py]    完整堆栈:", flush=True)
            _safe_traceback_print()
            _safe_flush()
            partitions = []
        
        # 如果LLM失败，使用启发式规则（不再使用写死的默认分区）
        if not partitions:
            print(f"\n[app.py] 🔄 LLM失败，使用启发式规则识别功能分区...", flush=True)
            try:
                # 使用 Agent 的启发式方法
                agent = CodeUnderstandingAgent(api_key='', base_url='')
                agent.project_path = project_path
                agent.readme_content = agent._load_readme()
                partitions = agent._identify_partitions_heuristic()
                if partitions:
                    print(f"[app.py] ✅ 启发式规则识别了 {len(partitions)} 个功能分区", flush=True)
            except Exception as e:
                print(f"[app.py] ⚠️ 启发式规则也失败: {e}", flush=True)
                partitions = []
        
        # 最后的 fallback：基于文件夹结构
        if not partitions:
            print(f"[app.py] 🔄 使用文件夹结构生成功能分区...", flush=True)
            partitions = generate_default_partitions(project_path)
            if partitions:
                print(f"[app.py] ✅ 生成了 {len(partitions)} 个功能分区", flush=True)
            _safe_flush()
        
        # ===== 步骤4：构建层级模型 =====
        update_analysis_status(progress=50, status='步骤4/5: 构建层级模型...')
        print(f"[app.py] 步骤3: 构建四层层级模型...", flush=True)
        _safe_flush()
        
        from datetime import datetime
        metadata = HierarchyMetadata(
            project_name=os.path.basename(project_path),
            project_path=project_path,
            analysis_timestamp=datetime.now().isoformat(),
            total_files=graph_data['metadata'].get('total_files', 0),
            total_functions_in_partition=len(partitions)
        )
        hierarchy = HierarchyModel(metadata=metadata)
        
        # 填充第3层：将 graph_data 转换为 CodeGraph
        from analysis.hierarchy_model import GraphEdge, RelationType
        
        # 转换节点：从 Cytoscape.js 格式转换为字典
        nodes_dict = {}
        for node in graph_data.get('nodes', []):
            node_data = node.get('data', {})
            node_id = node_data.get('id')
            if node_id:
                nodes_dict[node_id] = node_data
        
        # 转换边：从 Cytoscape.js 格式转换为 GraphEdge 对象
        edges_list = []
        relation_type_map = {
            'calls': RelationType.CALLS,
            'inherits': RelationType.INHERITS,
            'accesses': RelationType.ACCESSES,
            'contains': RelationType.CONTAINS,
            'cross_file_call': RelationType.CROSS_FILE_CALL,
            'parameter_flow': RelationType.PARAMETER_FLOW,
        }
        
        for edge in graph_data.get('edges', []):
            edge_data = edge.get('data', {})
            source_id = edge_data.get('source')
            target_id = edge_data.get('target')
            relation_str = edge_data.get('relation') or edge_data.get('type', 'calls')
            
            # 将字符串关系类型转换为 RelationType 枚举
            relation_type = relation_type_map.get(relation_str, RelationType.CALLS)
            
            graph_edge = GraphEdge(
                source_id=source_id,
                target_id=target_id,
                relation=relation_type,
                weight=edge_data.get('weight', 1),
                source_file=edge_data.get('caller_file', ''),
                target_file=edge_data.get('callee_file', ''),
                metadata=edge_data
            )
            edges_list.append(graph_edge)
        
        hierarchy.layer3_code_graph = CodeGraph(
            nodes=nodes_dict,
            edges=edges_list,
            total_nodes=len(graph_data.get('nodes', [])),
            total_edges=len(graph_data.get('edges', [])),
            total_classes=graph_data['metadata'].get('total_classes', 0),
            total_methods=graph_data['metadata'].get('total_methods', 0),
            total_functions=graph_data['metadata'].get('total_functions', 0),
        )
        
        # 填充第1层
        for partition in partitions:
            hierarchy.layer1_functions.append(partition)
            hierarchy.layer1_functions_map[partition.name] = partition
        
        # 填充第2层：基于功能分区和项目文件夹自动映射（使用绝对路径）
        print(f"[app.py] 构建第2层：文件夹层（使用绝对路径）...", flush=True)
        folders = generate_folder_nodes(project_path, partitions)
        
        # 如果功能分区指定了文件夹（绝对路径），使用指定的
        # 否则扫描项目文件夹
        if not folders:
            # 从功能分区的 folders 列表创建文件夹节点
            for partition in partitions:
                for folder_path in partition.folders:
                    # folder_path 可能是绝对路径或相对路径
                    if os.path.isabs(folder_path):
                        abs_folder_path = folder_path
                    else:
                        abs_folder_path = os.path.join(project_path, folder_path)
                    
                    if os.path.isdir(abs_folder_path):
                        # 统计该文件夹下的代码
                        class_count = 0
                        method_count = 0
                        for root, dirs, files in os.walk(abs_folder_path):
                            for file in files:
                                if file.endswith('.py'):
                                    # 简单统计（可以优化）
                                    class_count += 1
                        
                        folder_node = FolderNode(
                            folder_path=abs_folder_path,  # 使用绝对路径
                            parent_function=partition.name,
                            stats=FolderStats(class_count=class_count, method_count=method_count)
                        )
                        folders.append(folder_node)
        
        for folder in folders:
            hierarchy.layer2_folders.append(folder)
            hierarchy.layer2_folders_map[folder.folder_path] = folder
        print(f"[app.py] ✅ 生成了 {len(folders)} 个文件夹节点（绝对路径）", flush=True)
        for f in folders:
            print(f"[app.py]    - {f.folder_path}", flush=True)
        _safe_flush()
        
        print(f"[app.py] ✅ 层级模型构建完成", flush=True)
        _safe_flush()
        
        # ===== 步骤5：计算真实的聚合关系 =====
        update_analysis_status(progress=70, status='步骤5/5: 计算聚合关系...')
        print(f"[app.py] 步骤5: 从第3层计算真实的聚合关系...", flush=True)
        _safe_flush()
        
        # 建立代码元素到各层的映射
        hierarchy.entity_to_function_map = {}
        hierarchy.entity_to_folder_map = {}
        hierarchy.layer1_entity_pairs = {}  # 保存第1层的实体对信息
        hierarchy.layer2_entity_pairs = {}  # 保存第2层的实体对信息
        
        # 根据节点的文件位置映射到功能分区和文件夹（使用绝对路径匹配）
        for node_id, node_data in nodes_dict.items():
            file_path = node_data.get('file', '')
            if file_path:
                # 转换为绝对路径
                if not os.path.isabs(file_path):
                    file_path = os.path.join(project_path, file_path)
                file_path = os.path.normpath(file_path)
                
                # 映射到功能分区（检查文件夹路径是否在文件路径中）
                for partition in partitions:
                    for partition_folder in partition.folders:
                        # 处理绝对路径和相对路径
                        if os.path.isabs(partition_folder):
                            abs_partition_folder = os.path.normpath(partition_folder)
                        else:
                            abs_partition_folder = os.path.normpath(os.path.join(project_path, partition_folder))
                        
                        if abs_partition_folder in file_path or file_path.startswith(abs_partition_folder):
                            hierarchy.entity_to_function_map[node_id] = partition.name
                            break
                    if node_id in hierarchy.entity_to_function_map:
                        break
                
                # 映射到文件夹（使用绝对路径）
                for folder in folders:
                    folder_abs_path = os.path.normpath(folder.folder_path)
                    if folder_abs_path in file_path or file_path.startswith(folder_abs_path):
                        hierarchy.entity_to_folder_map[node_id] = folder.folder_path
                        break
        
        # 计算第1层的聚合边：功能分区之间的调用关系（保存实体对信息）
        layer1_relations = {}  # {(source_partition, target_partition): {'count': int, 'entity_pairs': List}}
        for edge in edges_list:
            source_partition = hierarchy.entity_to_function_map.get(edge.source_id)
            target_partition = hierarchy.entity_to_function_map.get(edge.target_id)
            
            if source_partition and target_partition and source_partition != target_partition:
                key = (source_partition, target_partition)
                if key not in layer1_relations:
                    layer1_relations[key] = {'count': 0, 'entity_pairs': []}
                layer1_relations[key]['count'] += 1
                # 保存实体对（最多保存前20对，避免数据过大）
                if len(layer1_relations[key]['entity_pairs']) < 20:
                    layer1_relations[key]['entity_pairs'].append((edge.source_id, edge.target_id))
        
        # 计算第2层的聚合边：文件夹之间的调用关系（保存实体对信息）
        layer2_relations = {}  # {(source_folder, target_folder): {'count': int, 'entity_pairs': List}}
        for edge in edges_list:
            source_folder = hierarchy.entity_to_folder_map.get(edge.source_id)
            target_folder = hierarchy.entity_to_folder_map.get(edge.target_id)
            
            if source_folder and target_folder and source_folder != target_folder:
                key = (source_folder, target_folder)
                if key not in layer2_relations:
                    layer2_relations[key] = {'count': 0, 'entity_pairs': []}
                layer2_relations[key]['count'] += 1
                # 保存实体对（最多保存前20对）
                if len(layer2_relations[key]['entity_pairs']) < 20:
                    layer2_relations[key]['entity_pairs'].append((edge.source_id, edge.target_id))
        
        # 设置功能分区的出度/入度
        for partition in hierarchy.layer1_functions:
            partition.outgoing_calls = {}
            partition.incoming_calls = {}
        
        for (src, dst), relation_data in layer1_relations.items():
            count = relation_data['count']
            entity_pairs = relation_data.get('entity_pairs', [])
            
            src_partition = next((p for p in hierarchy.layer1_functions if p.name == src), None)
            dst_partition = next((p for p in hierarchy.layer1_functions if p.name == dst), None)
            if src_partition and dst_partition:
                if dst not in src_partition.outgoing_calls:
                    src_partition.outgoing_calls[dst] = 0
                src_partition.outgoing_calls[dst] += count
                
                if src not in dst_partition.incoming_calls:
                    dst_partition.incoming_calls[src] = 0
                dst_partition.incoming_calls[src] += count
                
                # 保存实体对信息到 function_relations（用于展开时重建边）
                from analysis.hierarchy_model import FunctionRelation
                func_relation = FunctionRelation(
                    source_function=src,
                    target_function=dst,
                    call_count=count,
                    call_density=count / max(src_partition.stats.total_methods, 1),
                    critical_path_count=0
                )
                # FunctionRelation 没有 metadata 字段，但我们可以通过其他方式保存
                # 暂时先保存到 function_relations，后续可以通过 call_count 和 source/target 重建
                src_partition.function_relations.append(func_relation)
                
                # 将 entity_pairs 保存到 hierarchy 的映射中（用于展开时重建）
                key = f"{src}->{dst}"
                if key not in hierarchy.layer1_entity_pairs:
                    hierarchy.layer1_entity_pairs[key] = []
                hierarchy.layer1_entity_pairs[key].extend(entity_pairs[:20])  # 最多保存20对
        
        # 设置文件夹的出度/入度
        for folder in hierarchy.layer2_folders:
            folder.outgoing_calls = {}
            folder.incoming_calls = {}
        
        for (src, dst), relation_data in layer2_relations.items():
            count = relation_data['count']
            entity_pairs = relation_data.get('entity_pairs', [])
            
            src_folder = next((f for f in hierarchy.layer2_folders if f.folder_path == src), None)
            dst_folder = next((f for f in hierarchy.layer2_folders if f.folder_path == dst), None)
            if src_folder and dst_folder:
                if dst not in src_folder.outgoing_calls:
                    src_folder.outgoing_calls[dst] = 0
                src_folder.outgoing_calls[dst] += count
                
                if src not in dst_folder.incoming_calls:
                    dst_folder.incoming_calls[src] = 0
                dst_folder.incoming_calls[src] += count
                
                # 保存实体对信息到 folder_relations（用于展开时重建边）
                from analysis.hierarchy_model import FolderRelation
                folder_relation = FolderRelation(
                    source_folder=src,
                    target_folder=dst,
                    call_count=count,
                    entity_pairs=entity_pairs[:20]  # 最多保存20对
                )
                src_folder.folder_relations.append(folder_relation)
                
                # 同时保存到 hierarchy 的映射中
                key = f"{src}->{dst}"
                if key not in hierarchy.layer2_entity_pairs:
                    hierarchy.layer2_entity_pairs[key] = []
                hierarchy.layer2_entity_pairs[key].extend(entity_pairs[:20])
        
        print(f"[app.py] ✅ 聚合关系计算完成:", flush=True)
        print(f"[app.py]   - 第1层关系数: {len(layer1_relations)}", flush=True)
        print(f"[app.py]   - 第2层关系数: {len(layer2_relations)}", flush=True)
        _safe_flush()
        
        apply_aggregations_to_hierarchy(hierarchy)
        print(f"[app.py] ✅ 聚合计算完成", flush=True)
        _safe_flush()
        
        # ===== 步骤6：阶段4分析 - 功能级分析生成 =====
        update_analysis_status(progress=75, status='步骤6/7: 生成功能级分析...')
        print(f"[app.py] 步骤6: 生成功能级分析（调用图、超图、入口点、数据流图、控制流图）...", flush=True)
        _safe_flush()
        
        # 保存阶段4分析结果
        partition_analyses = {}
        
        try:
            # 获取调用图
            call_graph = analyzer.call_graph_analyzer.call_graph
            
            # 将FunctionPartition转换为字典格式（供阶段4使用）
            partition_dicts = _convert_partitions_to_dicts(hierarchy.layer1_functions, hierarchy.entity_to_function_map)
            
            # 检查是否有演示分区需要添加到partition_dicts中
            # 演示分区在步骤2.7创建，被添加到partitions列表中，但不在hierarchy中
            demo_partition_in_partitions = None
            for partition in partitions:
                if partition.get("is_demo", False):
                    demo_partition_in_partitions = partition
                    break
            
            # 如果找到演示分区且不在partition_dicts中，添加它
            if demo_partition_in_partitions:
                demo_partition_id = demo_partition_in_partitions.get("partition_id", "unknown")
                # 检查是否已经在partition_dicts中
                demo_already_in_dicts = any(p.get("partition_id") == demo_partition_id for p in partition_dicts)
                if not demo_already_in_dicts:
                    # 将演示分区添加到partition_dicts
                    demo_dict = {
                        "partition_id": demo_partition_id,
                        "name": demo_partition_in_partitions.get("name", "演示分区"),
                        "methods": demo_partition_in_partitions.get("methods", []),
                        "size": len(demo_partition_in_partitions.get("methods", [])),
                        "is_demo": True
                    }
                    partition_dicts.insert(0, demo_dict)  # 插入到开头，优先处理
                    print(f"[app.py]   ✓ 演示分区 {demo_partition_id} 已添加到功能级分析列表（位置0）", flush=True)
                    print(f"[app.py]     - 方法数量: {len(demo_dict['methods'])}", flush=True)
                else:
                    print(f"[app.py]   ℹ️  演示分区 {demo_partition_id} 已在功能级分析列表中", flush=True)
            
            print(f"[app.py]   待处理的分区总数: {len(partition_dicts)}", flush=True)
            if partition_dicts:
                print(f"[app.py]   分区列表: {[p.get('partition_id') for p in partition_dicts[:5]]}..." if len(partition_dicts) > 5 else f"[app.py]   分区列表: {[p.get('partition_id') for p in partition_dicts]}", flush=True)
            
            if partition_dicts and call_graph:
                # 阶段4.1: 函数调用图生成
                print(f"[app.py]   阶段4.1: 生成函数调用图...", flush=True)
                call_graph_generator = FunctionCallGraphGenerator(call_graph)
                for idx, partition_dict in enumerate(partition_dicts, 1):
                    partition_id = partition_dict.get("partition_id", "unknown")
                    partition_name = partition_dict.get("name", "unknown")
                    is_demo = partition_dict.get("is_demo", False)
                    methods_count = len(partition_dict.get("methods", []))
                    try:
                        partition_call_graph = call_graph_generator.generate_partition_call_graph(partition_dict)
                        if partition_id not in partition_analyses:
                            partition_analyses[partition_id] = {}
                        partition_analyses[partition_id]['call_graph'] = partition_call_graph
                        nodes_count = len(partition_call_graph.get('nodes', []))
                        edges_count = len(partition_call_graph.get('edges', []))
                        demo_marker = " [演示分区]" if is_demo else ""
                        print(f"[app.py]     [{idx}/{len(partition_dicts)}] ✓ 分区 {partition_id}{demo_marker}: 调用图生成成功 (节点: {nodes_count}, 边: {edges_count}, 方法: {methods_count})", flush=True)
                    except Exception as e:
                        print(f"[app.py]     [{idx}/{len(partition_dicts)}] ⚠️ 分区 {partition_id} 调用图生成失败: {e}", flush=True)
                        import traceback
                        _safe_traceback_print()
                
                # 阶段4.2: 函数调用超图生成
                print(f"[app.py]   阶段4.2: 生成函数调用超图...", flush=True)
                hypergraph_generator = FunctionCallHypergraphGenerator(call_graph)
                for idx, partition_dict in enumerate(partition_dicts, 1):
                    partition_id = partition_dict.get("partition_id", "unknown")
                    partition_name = partition_dict.get("name", "unknown")
                    is_demo = partition_dict.get("is_demo", False)
                    methods_count = len(partition_dict.get("methods", []))
                    try:
                        partition_hypergraph = hypergraph_generator.generate_partition_hypergraph(partition_dict)
                        if partition_id not in partition_analyses:
                            partition_analyses[partition_id] = {}
                        hypergraph_dict = partition_hypergraph.to_dict()
                        partition_analyses[partition_id]['hypergraph'] = hypergraph_dict
                        # 生成可视化数据并保存
                        hypergraph_viz = partition_hypergraph.to_visualization_data()
                        partition_analyses[partition_id]['hypergraph_viz'] = hypergraph_viz
                        
                        # 详细日志：超图统计信息
                        method_nodes = len([n for n in partition_hypergraph.nodes.values() if n.get('type') == 'method'])
                        function_nodes = len([n for n in partition_hypergraph.nodes.values() if n.get('type') == 'function'])
                        total_nodes = len(partition_hypergraph.nodes)
                        total_edges = len(hypergraph_viz.get('edges', []))
                        hyperedges_count = len(partition_hypergraph.hyperedges)
                        demo_marker = " [演示分区]" if is_demo else ""
                        print(f"[app.py]     [{idx}/{len(partition_dicts)}] ✓ 分区 {partition_id}{demo_marker}: 超图生成成功", flush=True)
                        print(f"[app.py]       - 总节点数: {total_nodes} (方法节点: {method_nodes}, 功能节点: {function_nodes})", flush=True)
                        print(f"[app.py]       - 超边数: {hyperedges_count}", flush=True)
                        print(f"[app.py]       - 可视化边数: {total_edges}", flush=True)
                        if total_edges == 0:
                            print(f"[app.py]       ⚠️ 警告：超图中没有边，可能无法显示连线", flush=True)
                            print(f"[app.py]         可能原因：分区内方法之间没有调用关系", flush=True)
                    except Exception as e:
                        print(f"[app.py]     [{idx}/{len(partition_dicts)}] ⚠️ 分区 {partition_id} 超图生成失败: {e}", flush=True)
                        import traceback
                        _safe_traceback_print()
                
                # 阶段4.3: 入口点识别
                print(f"[app.py]   阶段4.3: 识别入口点...", flush=True)
                entry_point_generator = EntryPointIdentifierGenerator(call_graph, analyzer.report)
                entry_points_dict = entry_point_generator.identify_all_partitions_entry_points(partition_dicts)
                
                print(f"[app.py]     入口点识别结果: {len(entry_points_dict)} 个分区有入口点数据", flush=True)
                
                for partition_id, entry_points in entry_points_dict.items():
                    if partition_id not in partition_analyses:
                        partition_analyses[partition_id] = {}
                    partition_analyses[partition_id]['entry_points'] = [
                        {
                            'method_signature': ep.method_signature,
                            'score': ep.score,
                            'reasons': ep.reasons
                        }
                        for ep in entry_points
                    ]
                    # 添加详细日志
                    partition_dict = next((p for p in partition_dicts if p.get('partition_id') == partition_id), None)
                    partition_methods_count = len(partition_dict.get('methods', [])) if partition_dict else 0
                    is_demo = partition_dict.get('is_demo', False) if partition_dict else False
                    demo_marker = " [演示分区]" if is_demo else ""
                    print(f"[app.py]     ✓ 分区 {partition_id}{demo_marker}: 识别到 {len(entry_points)} 个入口点（总方法数: {partition_methods_count}）", flush=True)
                    if len(entry_points) == partition_methods_count:
                        print(f"[app.py]       ⚠️ 警告：所有方法都被识别为入口点，可能存在问题", flush=True)
                        print(f"[app.py]         可能原因：分区内方法之间没有调用关系", flush=True)
                    elif len(entry_points) > 0:
                        print(f"[app.py]       - 入口点示例（前3个）:", flush=True)
                        for ep in entry_points[:3]:
                            print(f"[app.py]         • {ep.method_signature} (评分: {ep.score:.2f}, 原因: {', '.join(ep.reasons[:2])})", flush=True)
                
                # 检查是否有分区没有入口点数据
                partitions_without_entry_points = []
                for partition_dict in partition_dicts:
                    partition_id = partition_dict.get("partition_id", "unknown")
                    if partition_id not in entry_points_dict:
                        partitions_without_entry_points.append(partition_id)
                
                if partitions_without_entry_points:
                    print(f"[app.py]     ⚠️ 警告：以下分区没有入口点数据: {partitions_without_entry_points[:10]}", flush=True)
                    if len(partitions_without_entry_points) > 10:
                        print(f"[app.py]       ... 还有 {len(partitions_without_entry_points) - 10} 个分区", flush=True)
                
                # 阶段4.4: 功能级数据流图生成
                print(f"[app.py]   阶段4.4: 生成数据流图...", flush=True)
                dataflow_generator = PartitionDataFlowGenerator(
                    call_graph, 
                    analyzer.report,
                    analyzer.data_flow_analyzer if hasattr(analyzer, 'data_flow_analyzer') else None
                )
                for partition_dict in partition_dicts:
                    try:
                        partition_dataflow = dataflow_generator.generate_partition_data_flow(partition_dict)
                        partition_id = partition_dict.get("partition_id", "unknown")
                        if partition_id not in partition_analyses:
                            partition_analyses[partition_id] = {}
                        partition_analyses[partition_id]['dataflow'] = {
                            'nodes': partition_dataflow.nodes,
                            'edges': partition_dataflow.edges,
                            'parameter_flows': partition_dataflow.parameter_flows,
                            'return_flows': partition_dataflow.return_flows,
                            'shared_states': partition_dataflow.shared_states
                        }
                    except Exception as e:
                        print(f"[app.py]     ⚠️ 分区 {partition_dict.get('partition_id')} 数据流图生成失败: {e}", flush=True)
                
                # 阶段4.5: 功能级控制流图生成
                print(f"[app.py]   阶段4.5: 生成控制流图...", flush=True)
                controlflow_generator = PartitionControlFlowGenerator(call_graph, analyzer.report)
                for partition_dict in partition_dicts:
                    try:
                        partition_controlflow = controlflow_generator.generate_partition_control_flow(partition_dict)
                        partition_id = partition_dict.get("partition_id", "unknown")
                        if partition_id not in partition_analyses:
                            partition_analyses[partition_id] = {}
                        partition_analyses[partition_id]['controlflow'] = {
                            'nodes': partition_controlflow.nodes,
                            'edges': partition_controlflow.edges,
                            'method_call_edges': partition_controlflow.method_call_edges,
                            'cycles': partition_controlflow.cycles,
                            'dot': partition_controlflow.to_dot()
                        }
                    except Exception as e:
                        print(f"[app.py]     ⚠️ 分区 {partition_dict.get('partition_id')} 控制流图生成失败: {e}", flush=True)
            
            print(f"[app.py] ✅ 阶段4分析完成，为 {len(partition_analyses)} 个分区生成了分析结果", flush=True)
            
            # ===== 详细汇总日志（放在最后，方便查看） =====
            print(f"\n[app.py] {'='*80}", flush=True)
            print(f"[app.py] 📊 步骤6功能级分析详细汇总", flush=True)
            print(f"[app.py] {'='*80}", flush=True)
            print(f"[app.py]   总分区数: {len(partition_dicts)}", flush=True)
            print(f"[app.py]   已生成分析结果的分区数: {len(partition_analyses)}", flush=True)
            print(f"[app.py] ", flush=True)
            
            # 检查演示分区
            demo_partition_id = None
            for p in partition_dicts:
                if p.get("is_demo", False):
                    demo_partition_id = p.get("partition_id")
                    break
            
            if demo_partition_id:
                print(f"[app.py]   🎯 演示分区检查: {demo_partition_id}", flush=True)
                if demo_partition_id in partition_analyses:
                    demo_analysis = partition_analyses[demo_partition_id]
                    print(f"[app.py]     ✓ 演示分区已生成分析结果", flush=True)
                    
                    # 检查调用图
                    if 'call_graph' in demo_analysis:
                        call_graph_data = demo_analysis['call_graph']
                        nodes = call_graph_data.get('nodes', [])
                        edges = call_graph_data.get('edges', [])
                        print(f"[app.py]     ✓ 调用图: 存在 (节点: {len(nodes)}, 边: {len(edges)})", flush=True)
                    else:
                        print(f"[app.py]     ❌ 调用图: 不存在", flush=True)
                    
                    # 检查超图
                    if 'hypergraph' in demo_analysis:
                        hypergraph_data = demo_analysis.get('hypergraph', {})
                        hypergraph_viz = demo_analysis.get('hypergraph_viz', {})
                        nodes = hypergraph_viz.get('nodes', [])
                        edges = hypergraph_viz.get('edges', [])
                        print(f"[app.py]     ✓ 超图: 存在 (节点: {len(nodes)}, 边: {len(edges)})", flush=True)
                        if len(edges) == 0:
                            print(f"[app.py]       ⚠️ 警告：超图没有边，可能无法显示连线", flush=True)
                    else:
                        print(f"[app.py]     ❌ 超图: 不存在", flush=True)
                    
                    # 检查入口点
                    if 'entry_points' in demo_analysis:
                        entry_points = demo_analysis['entry_points']
                        print(f"[app.py]     ✓ 入口点: 存在 ({len(entry_points)} 个)", flush=True)
                        if len(entry_points) > 0:
                            print(f"[app.py]       - 入口点列表（前5个）:", flush=True)
                            for ep in entry_points[:5]:
                                method_sig = ep.get('method_signature', 'unknown')
                                score = ep.get('score', 0)
                                reasons = ep.get('reasons', [])
                                print(f"[app.py]         • {method_sig} (评分: {score:.2f}, 原因: {', '.join(reasons[:2])})", flush=True)
                    else:
                        print(f"[app.py]     ❌ 入口点: 不存在", flush=True)
                    
                    # 检查数据流图
                    if 'dataflow' in demo_analysis:
                        dataflow_data = demo_analysis['dataflow']
                        nodes = dataflow_data.get('nodes', [])
                        edges = dataflow_data.get('edges', [])
                        print(f"[app.py]     ✓ 数据流图: 存在 (节点: {len(nodes)}, 边: {len(edges)})", flush=True)
                    else:
                        print(f"[app.py]     ⚠️ 数据流图: 不存在（可选）", flush=True)
                    
                    # 检查控制流图
                    if 'controlflow' in demo_analysis:
                        controlflow_data = demo_analysis['controlflow']
                        nodes = controlflow_data.get('nodes', [])
                        edges = controlflow_data.get('edges', [])
                        print(f"[app.py]     ✓ 控制流图: 存在 (节点: {len(nodes)}, 边: {len(edges)})", flush=True)
                    else:
                        print(f"[app.py]     ⚠️ 控制流图: 不存在（可选）", flush=True)
                else:
                    print(f"[app.py]     ❌ 演示分区未生成分析结果！", flush=True)
                    print(f"[app.py]       可能原因：步骤6处理时出错", flush=True)
            else:
                print(f"[app.py]   ⚠️ 未找到演示分区", flush=True)
            
            print(f"[app.py] ", flush=True)
            print(f"[app.py]   📋 所有分区的分析结果统计:", flush=True)
            for partition_id in sorted(partition_analyses.keys()):
                analysis = partition_analyses[partition_id]
                has_call_graph = 'call_graph' in analysis
                has_hypergraph = 'hypergraph' in analysis
                has_entry_points = 'entry_points' in analysis
                entry_count = len(analysis.get('entry_points', []))
                
                status_marks = []
                if has_call_graph:
                    status_marks.append("调用图✓")
                if has_hypergraph:
                    status_marks.append("超图✓")
                if has_entry_points:
                    status_marks.append(f"入口点✓({entry_count})")
                
                status_str = ", ".join(status_marks) if status_marks else "❌无数据"
                is_demo_marker = " [演示]" if partition_id == demo_partition_id else ""
                print(f"[app.py]     - {partition_id}{is_demo_marker}: {status_str}", flush=True)
            
            print(f"[app.py] {'='*80}\n", flush=True)
            # ===== 详细汇总日志结束 =====
            
        except Exception as e:
            print(f"[app.py] ⚠️ 阶段4分析失败: {e}", flush=True)
            import traceback
            _safe_traceback_print()
            partition_analyses = {}
        
        _safe_flush()
        
        # ===== 步骤7：保存并返回 =====
        update_analysis_status(progress=90, status='步骤7/7: 准备返回数据...')
        print(f"[app.py] 步骤5: 准备返回数据...", flush=True)
        _safe_flush()
        
        hierarchy_data = hierarchy.to_dict()
        
        # 构建前端需要的数据格式
        result_data = {
            'hierarchy': {
                'layer1_functions': [],
                'layer2_folders': [],
                'metadata': hierarchy_data.get('metadata', {}),
                'entity_pairs': {
                    'layer1': hierarchy.layer1_entity_pairs if hasattr(hierarchy, 'layer1_entity_pairs') else {},
                    'layer2': hierarchy.layer2_entity_pairs if hasattr(hierarchy, 'layer2_entity_pairs') else {}
                }
            },
            'original_graph': graph_data,
            'partition_analyses': partition_analyses  # 阶段4分析结果
        }
        
        # 填充第1层：功能分区
        print(f"[app.py] 填充第1层数据...", flush=True)
        print(f"[app.py] 功能分区总数: {len(hierarchy.layer1_functions)}", flush=True)
        for i, func in enumerate(hierarchy.layer1_functions):
            # 确保 stats 属性存在
            if not hasattr(func, 'stats') or func.stats is None:
                from analysis.hierarchy_model import FunctionStats
                func.stats = FunctionStats()
            
            func_data = {
                'name': func.name,
                'description': func.description,
                'folders': func.folders,
                'partition_id': f"partition_{i}",  # 添加partition_id用于前端查询
                'outgoing_calls': func.outgoing_calls if hasattr(func, 'outgoing_calls') else {},
                'incoming_calls': func.incoming_calls if hasattr(func, 'incoming_calls') else {},
                'stats': {
                    'total_classes': func.stats.total_classes if hasattr(func.stats, 'total_classes') else 0
                },
                'function_relations': [
                    {
                        'source': fr.source_function,
                        'target': fr.target_function,
                        'call_count': fr.call_count,
                        'call_density': fr.call_density
                    }
                    for fr in func.function_relations
                ]
            }
            print(f"[app.py]   - 添加功能分区: {func.name}, outgoing_calls: {func_data['outgoing_calls']}", flush=True)
            result_data['hierarchy']['layer1_functions'].append(func_data)
        
        # 填充第2层：文件夹
        print(f"[app.py] 填充第2层数据...", flush=True)
        print(f"[app.py] 文件夹总数: {len(hierarchy.layer2_folders)}", flush=True)
        for folder in hierarchy.layer2_folders:
            folder_data = {
                'folder_path': folder.folder_path,  # 绝对路径
                'parent_function': folder.parent_function,
                'outgoing_calls': folder.outgoing_calls if hasattr(folder, 'outgoing_calls') else {},
                'stats': {
                    'total_code_elements': 0,
                    'class_count': folder.stats.class_count if hasattr(folder.stats, 'class_count') else 0,
                    'method_count': folder.stats.method_count if hasattr(folder.stats, 'method_count') else 0
                },
                'folder_relations': [
                    {
                        'source': fr.source_folder,
                        'target': fr.target_folder,
                        'call_count': fr.call_count,
                        'entity_pairs': fr.entity_pairs  # 保存实体对，用于展开时重建边
                    }
                    for fr in folder.folder_relations
                ]
            }
            print(f"[app.py]   - 添加文件夹: {folder.folder_path}, outgoing_calls: {folder_data['outgoing_calls']}", flush=True)
            result_data['hierarchy']['layer2_folders'].append(folder_data)
        
        update_analysis_status(
            progress=100,
            status='四层分析完成！',
            data=result_data,
            is_analyzing=False
        )
        
        print(f"[app.py] {'='*60}", flush=True)
        print(f"[app.py] ✅✅✅ 四层嵌套可视化分析完成！", flush=True)
        print(f"[app.py] {'='*60}\n", flush=True)
        _safe_flush()
        
    except Exception as e:
        print(f"\n[app.py] {'='*60}", flush=True)
        print(f"[app.py] ❌ 四层分析出错: {e}", flush=True)
        print(f"[app.py] {'='*60}", flush=True)
        import traceback
        _safe_traceback_print()
        _safe_flush()
        update_analysis_status(
            error=str(e),
            is_analyzing=False,
            progress=0,
            status='分析失败'
        )
        print(f"[app.py] {'='*60}\n", flush=True)
        _safe_flush()


def api_analyze():
    """开始分析API"""
    data = request.json
    project_path = data.get('project_path')
    
    # 如果是临时路径或无效路径，使用当前项目目录作为示例
    if not project_path or not os.path.isdir(project_path) or 'tmp' in project_path:
        project_path = str(PROJECT_ROOT)
    
    # 重置状态（线程安全）
    update_analysis_status(
        progress=0,
        status='分析中...',
        data=None,
        error=None,
        is_analyzing=True,
        analysis_type='main',
        project_path=os.path.normpath(project_path),
    )
    
    # 后台分析
    thread = threading.Thread(target=analyze_project, args=(project_path,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': '分析已开始'})


def convert_sets_to_lists(obj):
    """递归地将所有set类型转换为list，以便JSON序列化"""
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {key: convert_sets_to_lists(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_sets_to_lists(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        # 处理dataclass对象
        return {key: convert_sets_to_lists(value) for key, value in obj.__dict__.items()}
    else:
        return obj


def api_status():
    """获取分析状态"""
    # 使用锁读取，避免读取到中间状态
    with status_lock:
        status_copy = dict(analysis_status)
        # 转换set为list以便JSON序列化
        # 注意：report对象可能包含set，但我们只序列化基本状态信息
        serializable_status = {
            'progress': status_copy.get('progress', 0),
            'status': status_copy.get('status', '等待中...'),
            'is_analyzing': status_copy.get('is_analyzing', False),
            'error': status_copy.get('error'),
            'data': status_copy.get('data'),  # data已经是字典格式，应该可以序列化
            'analysis_type': status_copy.get('analysis_type'),
            'project_path': status_copy.get('project_path'),
        }
    return jsonify(serializable_status)


def api_workbench_session_start():
    """Phase 1：启动统一 workbench 分析会话。"""
    data = request.json or {}
    raw_project_path = str(data.get('project_path') or '').strip()
    if not raw_project_path:
        return jsonify({'error': 'project_path 不能为空'}), 400

    resolved_project_path = os.path.normpath(raw_project_path)
    if not os.path.isabs(resolved_project_path):
        resolved_project_path = os.path.abspath(resolved_project_path)

    if not os.path.isdir(resolved_project_path):
        return jsonify({'error': f'project_path 不存在或不是目录: {resolved_project_path}'}), 400

    project_path = resolved_project_path
    experience_output_root: Optional[str] = None
    raw_experience_output_root = str(data.get('experience_output_root') or '').strip()
    if raw_experience_output_root:
        if not os.path.isabs(raw_experience_output_root):
            return jsonify({'error': 'experience_output_root 必须是绝对路径'}), 400
        experience_output_root = os.path.normpath(os.path.abspath(raw_experience_output_root))
        try:
            os.makedirs(experience_output_root, exist_ok=True)
        except Exception as exc:
            return jsonify({'error': f'experience_output_root 创建失败: {exc}'}), 400

    session_payload = _create_workbench_session(project_path)
    session_payload = _update_workbench_session(
        session_payload['sessionId'],
        experienceOutputRoot=experience_output_root,
    ) or session_payload

    thread = threading.Thread(
        target=_run_workbench_session,
        args=(session_payload['sessionId'], project_path, experience_output_root),
        daemon=True,
    )
    thread.start()

    return jsonify({
        'sessionId': session_payload['sessionId'],
        'projectPath': project_path,
        'status': session_payload['status'],
        'phase': session_payload['phase'],
        'message': '统一分析会话已开始',
        'experienceOutputRoot': experience_output_root,
    })


def api_workbench_session_status(session_id):
    """Phase 1：获取统一 workbench 分析会话状态。"""
    payload = _get_workbench_session_or_none(session_id)
    if not payload:
        return jsonify({'error': '未找到统一分析会话'}), 404

    progress, message = _map_workbench_progress(payload)
    stage_label, stage_detail = _derive_workbench_stage_meta(payload.get('phase'), message)
    response_payload = {
        'sessionId': payload.get('sessionId'),
        'projectPath': payload.get('projectPath'),
        'status': payload.get('status'),
        'phase': payload.get('phase'),
        'progress': progress,
        'message': message,
        'stageLabel': payload.get('stageLabel') or stage_label,
        'stageDetail': payload.get('stageDetail') or stage_detail,
        'error': payload.get('error'),
        'bootstrapReady': payload.get('bootstrapReady', False),
        'startedAt': payload.get('startedAt'),
        'updatedAt': payload.get('updatedAt'),
        'completedAt': payload.get('completedAt'),
    }
    return jsonify(response_payload)


def api_workbench_session_bootstrap(session_id):
    """Phase 1：获取统一 workbench bootstrap 结果。"""
    payload = _get_workbench_session_or_none(session_id)
    if not payload:
        return jsonify({'error': '未找到统一分析会话'}), 404

    if payload.get('status') == 'failed':
        return jsonify({'error': payload.get('error') or '统一分析会话失败'}), 400

    bootstrap = payload.get('bootstrap')
    if not bootstrap and payload.get('status') == 'completed':
        bootstrap = _build_workbench_bootstrap(session_id, payload['projectPath'])
        payload = _update_workbench_session(
            session_id,
            bootstrap=bootstrap,
            bootstrapReady=True,
        ) or payload

    if not bootstrap:
        return jsonify({'error': 'bootstrap 尚未就绪'}), 409

    return jsonify(bootstrap)


def _find_latest_workbench_session_for_project(project_path: str) -> Optional[Dict[str, Any]]:
    normalized = _normalize_project_lookup_path(project_path)
    latest_payload: Optional[Dict[str, Any]] = None
    latest_updated = ''
    for session_id in data_accessor.list_workbench_session_ids():
        payload = data_accessor.get_workbench_session(session_id)
        if not isinstance(payload, dict):
            continue
        payload_project_path = _normalize_project_lookup_path(payload.get('projectPath'))
        if payload_project_path != normalized:
            continue
        updated_at = str(payload.get('updatedAt') or payload.get('startedAt') or '')
        if not latest_payload or updated_at >= latest_updated:
            latest_payload = payload
            latest_updated = updated_at
    return latest_payload


def _build_workbench_project_status(project_path: str) -> Dict[str, Any]:
    normalized = _normalize_project_lookup_path(project_path)
    if not normalized:
        return {
            'projectPath': '',
            'status': 'not_started',
            'phase': 'missing_project',
            'progress': 0,
            'message': '未提供项目路径',
            'qualityHint': '暂无完整经验库，问答/代码生成效果较弱',
            'experienceReady': False,
            'bootstrapReady': False,
            'activeSessionId': None,
        }

    profile = _project_library_storage.load_project_profile(normalized) or {}
    display_name = str(profile.get('display_name') or '').strip() or _build_project_display_name(normalized)

    hierarchy_cached = _resolve_function_hierarchy_cached(normalized)
    if hierarchy_cached:
        return {
            'projectPath': normalized,
            'displayName': display_name,
            'status': 'completed',
            'phase': 'ready',
            'progress': 100,
            'message': '经验库已就绪',
            'qualityHint': '经验库已就绪，可使用高阶问答与代码生成功能',
            'experienceReady': True,
            'bootstrapReady': True,
            'activeSessionId': None,
            'updatedAt': profile.get('updated_at') or profile.get('analysis_timestamp'),
        }

    latest_session = _find_latest_workbench_session_for_project(normalized)
    if isinstance(latest_session, dict):
        progress, mapped_message = _map_workbench_progress(latest_session)
        status = str(latest_session.get('status') or 'running')
        phase = str(latest_session.get('phase') or 'running')
        if status == 'completed':
            quality_hint = '经验库已就绪，可使用高阶问答与代码生成功能'
        elif status == 'failed':
            quality_hint = '经验库构建失败，问答/代码生成将退化为弱上下文模式'
        else:
            quality_hint = '经验库构建中，完成后可解锁完整能力'
        return {
            'projectPath': normalized,
            'displayName': display_name,
            'status': status,
            'phase': phase,
            'progress': max(0, min(100, int(progress or latest_session.get('progress') or 0))),
            'message': mapped_message or str(latest_session.get('message') or '经验库构建中'),
            'qualityHint': quality_hint,
            'experienceReady': status == 'completed',
            'bootstrapReady': bool(latest_session.get('bootstrapReady')),
            'activeSessionId': latest_session.get('sessionId'),
            'updatedAt': latest_session.get('updatedAt'),
        }

    graph_data = _resolve_graph_data_for_project(normalized, allow_global_fallback=False)
    if graph_data:
        return {
            'projectPath': normalized,
            'displayName': display_name,
            'status': 'partial',
            'phase': 'graph_ready_hierarchy_missing',
            'progress': 45,
            'message': '主图谱可用，功能层级/经验库尚未完成',
            'qualityHint': '暂无完整经验库，问答/代码生成效果较弱',
            'experienceReady': False,
            'bootstrapReady': True,
            'activeSessionId': None,
            'updatedAt': profile.get('updated_at') or profile.get('analysis_timestamp'),
        }

    return {
        'projectPath': normalized,
        'displayName': display_name,
        'status': 'not_started',
        'phase': 'not_started',
        'progress': 0,
        'message': '尚未开始经验库构建',
        'qualityHint': '暂无完整经验库，问答/代码生成效果较弱',
        'experienceReady': False,
        'bootstrapReady': False,
        'activeSessionId': None,
        'updatedAt': profile.get('updated_at') or profile.get('analysis_timestamp'),
    }


def api_workbench_project_status():
    project_path = request.args.get('project_path') or _infer_repo_project_path()
    if not project_path:
        return jsonify(_build_workbench_project_status(''))
    payload = _build_workbench_project_status(project_path)
    return jsonify(payload)


def api_fixed_scenario_benchmark_start():
    """触发固定场景基准回归（异步会话）。"""
    data = request.json or {}
    raw_project_path = str(data.get('project_path') or str(PROJECT_ROOT)).strip()
    if not raw_project_path:
        return jsonify({'error': 'project_path 不能为空'}), 400

    project_path = os.path.normpath(raw_project_path)
    if not os.path.isabs(project_path):
        project_path = os.path.abspath(project_path)
    if not os.path.isdir(project_path):
        return jsonify({'error': f'project_path 不存在或不是目录: {project_path}'}), 400

    report_dir = _normalize_benchmark_report_dir(data.get('report_dir'))
    try:
        os.makedirs(report_dir, exist_ok=True)
    except Exception as exc:
        return jsonify({'error': f'report_dir 无法创建: {exc}'}), 400

    session_payload = _create_benchmark_session(project_path, report_dir)
    thread = threading.Thread(
        target=_run_fixed_scenario_benchmark_session,
        args=(session_payload['sessionId'], project_path, report_dir),
        daemon=True,
    )
    thread.start()

    return jsonify(
        {
            'sessionId': session_payload['sessionId'],
            'status': session_payload['status'],
            'phase': session_payload['phase'],
            'projectPath': project_path,
            'reportDir': report_dir,
            'message': '固定场景基准会话已开始',
        }
    )


def api_fixed_scenario_benchmark_status(session_id):
    payload = _get_benchmark_session_or_none(session_id)
    if not payload:
        return jsonify({'error': '未找到基准会话'}), 404
    return jsonify(
        {
            'sessionId': payload.get('sessionId'),
            'status': payload.get('status'),
            'phase': payload.get('phase'),
            'progress': payload.get('progress'),
            'message': payload.get('message'),
            'error': payload.get('error'),
            'projectPath': payload.get('projectPath'),
            'reportDir': payload.get('reportDir'),
            'startedAt': payload.get('startedAt'),
            'updatedAt': payload.get('updatedAt'),
            'completedAt': payload.get('completedAt'),
        }
    )


def api_fixed_scenario_benchmark_result(session_id):
    payload = _get_benchmark_session_or_none(session_id)
    if not payload:
        return jsonify({'error': '未找到基准会话'}), 404
    status = str(payload.get('status') or '').strip()
    if status == 'failed':
        return jsonify({'error': payload.get('error') or '固定场景基准执行失败'}), 400
    result = payload.get('result')
    if status != 'completed' or not isinstance(result, dict):
        return jsonify({'error': '基准结果尚未就绪'}), 409
    return jsonify(result)


def api_analyze_hierarchy():
    """开始四层嵌套可视化分析API"""
    data = request.json or {}
    project_path = data.get('project_path')
    use_llm = data.get('use_llm', False)
    
    # 如果是临时路径或无效路径，使用当前项目目录
    if not project_path or not os.path.isdir(project_path) or 'tmp' in project_path:
        project_path = str(PROJECT_ROOT)
    
    # 重置状态
    update_analysis_status(
        progress=0,
        status='分析中...',
        data=None,
        error=None,
        is_analyzing=True,
        analysis_type='hierarchy',
        project_path=os.path.normpath(project_path),
    )
    
    # 后台分析
    thread = threading.Thread(target=analyze_hierarchy, args=(project_path, use_llm))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': '四层分析已开始'})


def analyze_function_hierarchy(project_path, *, precomputed_graph_data: Optional[Dict[str, Any]] = None, precomputed_analyzer: Optional[CodeAnalyzer] = None, experience_output_root: Optional[str] = None):
    """后台分析项目功能层级（使用社区检测）"""
    # Ensure UTF-8 output stream without replacing/rewrapping stdout
    _ensure_utf8_output_stream()
    
    # ===== 初始化日志文件 =====
    log_filepath = setup_log_file(project_path)
    log_print(f"[app.py] {'='*60}")
    log_print(f"[app.py] 功能层级分析日志文件: {log_filepath}")
    log_print(f"[app.py] 项目路径: {project_path}")
    log_print(f"[app.py] {'='*60}")
    timing = _FunctionHierarchyTimingCollector(project_path)
    
    try:
        # ===== 配置：功能层级与路径级别分析的可调参数（后续一键放开只需修改这里） =====
        USE_LLM_PARTITIONS_LIMIT = int(os.getenv('FH_LLM_PARTITION_LIMIT', '8'))  # 保持节制，但覆盖更多高价值分区
        MAX_PATHS_TO_ANALYZE = _get_max_paths_per_partition(10)  # 每个分区保留更丰富的代表路径，避免结果过薄
        PATH_ANALYSIS_PARTITION_LIMIT = _get_path_analysis_partition_limit(16)  # 默认深分析更多分区，避免大部分分区退化为骨架
        PATH_ANALYSIS_TIMEOUT_SECONDS = _get_phase5_timeout_seconds()
        FILTER_SINGLE_NODE_PATHS = os.getenv('FH_FILTER_SINGLE_NODE_PATHS', '1') != '0'  # 是否过滤只有单个方法的路径
        ENABLE_STRUCTURAL_PATHS_ALL = os.getenv('FH_ENABLE_STRUCTURAL_PATHS_ALL', '1') != '0'  # 默认所有分区都做结构路径找全
        execution_profile = _resolve_function_hierarchy_execution_profile()
        pipeline_structure = _build_pipeline_structure(execution_profile)
        log_print(f"[workset1] execution_profile={json.dumps(execution_profile, ensure_ascii=False)}")
        ENABLE_DEFAULT_VISIBLE_LAYER = execution_profile['layers']['default_visible']
        ENABLE_EXPAND_VISIBLE_LAYER = execution_profile['layers']['expand_visible']
        ENABLE_ADVANCED_VISIBLE_LAYER = execution_profile['layers']['advanced_visible']
        ENABLE_PARTITION_LLM_SEMANTICS = execution_profile['effective_steps']['partition_llm_semantics']
        ENABLE_PATH_LLM_ANALYSIS = execution_profile['effective_steps']['path_llm_analysis']
        ENABLE_PATH_SUPPLEMENT_GENERATION = execution_profile['effective_steps']['path_supplement_generation']
        ENABLE_PATH_CFG_DFG_IO = execution_profile['effective_steps']['path_cfg_dfg_io']
        ENABLE_CFG_DFG_LLM_EXPLAIN = execution_profile['effective_steps']['cfg_dfg_llm_explain']
        INCLUDE_DEEP_ANALYSIS_IN_DEFAULT_RESULT = execution_profile['effective_steps']['include_deep_analysis_in_default_result']
        INDEX_REBUILD_MODE = execution_profile['index_rebuild_mode']
        normalized_project_path = os.path.normpath(project_path)
        code_state_fingerprint = _compute_code_state_fingerprint(normalized_project_path)
        cache_signatures = _build_layer_cache_signatures(
            code_state_fingerprint=code_state_fingerprint,
            execution_profile=execution_profile,
            max_paths_to_analyze=MAX_PATHS_TO_ANALYZE,
            path_analysis_partition_limit=PATH_ANALYSIS_PARTITION_LIMIT,
            filter_single_node_paths=FILTER_SINGLE_NODE_PATHS,
        )
        layer_cache_payload = data_accessor.get_function_hierarchy_layer_cache(normalized_project_path) or {}
        layer_cache_meta = layer_cache_payload.get('meta') or {}
        layer_caches = layer_cache_payload.get('layers') or {}
        cached_default_layer = layer_caches.get('default_visible') or {}
        cached_expand_layer = layer_caches.get('expand_visible') or {}
        cached_advanced_layer = layer_caches.get('advanced_visible') or {}
        cached_final_result = layer_cache_payload.get('final_result')

        code_fingerprint_match = layer_cache_meta.get('code_state_fingerprint') == code_state_fingerprint
        default_cache_hit = code_fingerprint_match and cached_default_layer.get('signature') == cache_signatures['default_visible'] and bool(cached_default_layer.get('snapshot'))
        expand_cache_hit = code_fingerprint_match and cached_expand_layer.get('signature') == cache_signatures['expand_visible'] and bool(cached_expand_layer.get('snapshot'))
        advanced_cache_signature_match = code_fingerprint_match and cached_advanced_layer.get('signature') == cache_signatures['advanced_visible']
        final_result_cache_hit = advanced_cache_signature_match and bool(cached_final_result)

        _log_layer_cache_decision('default_visible', 'hit' if default_cache_hit else 'miss', 'signature_match' if default_cache_hit else 'signature_or_fingerprint_changed')
        _log_layer_cache_decision('expand_visible', 'hit' if expand_cache_hit else 'miss', 'signature_match' if expand_cache_hit else 'signature_or_fingerprint_changed')
        _log_layer_cache_decision('advanced_visible', 'hit' if final_result_cache_hit else 'miss', 'full_final_result_reusable' if final_result_cache_hit else 'needs_runtime_validation')
        cache_runtime = {
            'code_state_fingerprint': code_state_fingerprint,
            'default_visible': {'status': 'hit' if default_cache_hit else 'miss', 'reason': 'signature_match' if default_cache_hit else 'signature_or_fingerprint_changed'},
            'expand_visible': {'status': 'hit' if expand_cache_hit else 'miss', 'reason': 'signature_match' if expand_cache_hit else 'signature_or_fingerprint_changed'},
            'advanced_visible': {'status': 'hit' if final_result_cache_hit else 'miss', 'reason': 'full_final_result_reusable' if final_result_cache_hit else 'needs_runtime_validation'},
        }
        degradation_summary = []
        skipped_or_deferred_work = []
        index_rebuild_status = {
            'mode': INDEX_REBUILD_MODE,
            'status': 'available_on_demand' if INDEX_REBUILD_MODE == 'deferred' else 'disabled' if INDEX_REBUILD_MODE == 'disabled' else 'pending_background',
            'reason_code': 'deferred_by_config' if INDEX_REBUILD_MODE == 'deferred' else 'disabled_by_config' if INDEX_REBUILD_MODE == 'disabled' else 'scheduled',
            'timeout_seconds': _get_index_rebuild_visibility_timeout_seconds(),
            'user_message': '索引构建将继续在后台执行' if INDEX_REBUILD_MODE == 'immediate' else '索引构建已延后，可稍后再触发' if INDEX_REBUILD_MODE == 'deferred' else '索引构建已关闭',
            'continues_in_background': INDEX_REBUILD_MODE == 'immediate',
        }

        layer_states = {
            'default_visible': _build_layer_state('pending_background', [], visible=ENABLE_DEFAULT_VISIBLE_LAYER),
            'expand_visible': _build_layer_state('pending_background' if ENABLE_EXPAND_VISIBLE_LAYER else 'disabled', [], visible=ENABLE_EXPAND_VISIBLE_LAYER),
            'advanced_visible': _build_layer_state('pending_background' if ENABLE_ADVANCED_VISIBLE_LAYER else 'available_on_demand', [], visible=ENABLE_ADVANCED_VISIBLE_LAYER),
            'deferred_background': _build_layer_state('available_on_demand' if INDEX_REBUILD_MODE == 'deferred' else 'disabled' if INDEX_REBUILD_MODE == 'disabled' else 'pending_background', [], visible=False),
        }

        if final_result_cache_hit:
            cached_result = copy.deepcopy(cached_final_result)
            cached_result['cache_runtime'] = {
                'code_state_fingerprint': code_state_fingerprint,
                'default_visible': {'status': 'hit', 'reason': 'signature_match'},
                'expand_visible': {'status': 'hit', 'reason': 'signature_match'},
                'advanced_visible': {'status': 'hit', 'reason': 'full_final_result_reusable'},
            }
            cached_layers = copy.deepcopy(cached_result.get('result_layers') or layer_states)
            layer_states.update(cached_layers)
            update_analysis_status(progress=55, status='Workset4: 默认层命中缓存', data=copy.deepcopy(cached_default_layer.get('snapshot')), is_analyzing=True)
            if expand_cache_hit:
                update_analysis_status(progress=80, status='Workset4: 展开层命中缓存', data=copy.deepcopy(cached_expand_layer.get('snapshot')), is_analyzing=True)
            update_analysis_status(progress=100, status='Workset4: 最终结果命中缓存', data=cached_result, is_analyzing=False)
            data_accessor.save_function_hierarchy(normalized_project_path, cached_result)
            if cached_result.get('process_shadow'):
                data_accessor.save_process_shadow(normalized_project_path, cached_result['process_shadow'])
            if cached_result.get('community_shadow'):
                data_accessor.save_community_shadow(normalized_project_path, cached_result['community_shadow'])
            return

        if default_cache_hit:
            update_analysis_status(
                progress=5,
                status='Workset4: 默认层缓存预热完成，开始校验深层结果...',
                data=copy.deepcopy(cached_default_layer.get('snapshot')),
                is_analyzing=True,
            )
        if expand_cache_hit:
            update_analysis_status(
                progress=6,
                status='Workset4: 展开层缓存预热完成，继续校验高级层...',
                data=copy.deepcopy(cached_expand_layer.get('snapshot')),
                is_analyzing=True,
            )

        def _publish_partial_result(progress: int, status_text: str, *, include_expand: bool, include_advanced: bool, include_shadow: bool = False, performance_baseline: Optional[Dict[str, Any]] = None, is_final: bool = False) -> Dict[str, Any]:
            snapshot = _build_function_hierarchy_snapshot(
                project_path=project_path,
                partitions=partitions if 'partitions' in locals() else [],
                partition_analyses=partition_analyses if 'partition_analyses' in locals() else {},
                execution_profile=execution_profile,
                layer_states=layer_states,
                include_expand=include_expand,
                include_advanced=include_advanced,
                entry_points_shadow=entry_points_shadow if 'entry_points_shadow' in locals() else None,
                process_shadow=process_shadow if 'process_shadow' in locals() else None,
                community_shadow=community_shadow if 'community_shadow' in locals() else None,
                performance_baseline=performance_baseline,
                degradation_summary=degradation_summary,
                skipped_or_deferred_work=skipped_or_deferred_work,
                index_rebuild_status=index_rebuild_status,
                pipeline_structure=pipeline_structure,
            )
            update_analysis_status(
                progress=progress,
                status=status_text,
                data=snapshot,
                is_analyzing=not is_final,
            )
            return snapshot
        
        # 创建内部print函数，同时输出到控制台和日志文件
        def _print(*args, **kwargs):
            """内部print函数，同时输出到控制台和日志文件"""
            log_print(*args, **kwargs)

        def _get_module_name_from_source(file_path: Optional[str]) -> Optional[str]:
            """
            根据源文件路径推断模块名（用于构造FQMN的包名部分）
            例如: /path/to/project/analysis/analyzer.py -> analysis.analyzer
            """
            if not file_path:
                return None
            try:
                # 处理相对路径和绝对路径
                if not os.path.isabs(file_path):
                    abs_path = os.path.normpath(os.path.join(project_path, file_path))
                else:
                    abs_path = os.path.normpath(file_path)
                project_root = os.path.normpath(project_path)
                rel_path = os.path.relpath(abs_path, project_root)
                # 去掉扩展名并替换路径分隔符为点
                rel_no_ext, _ = os.path.splitext(rel_path)
                module = rel_no_ext.replace(os.sep, '.')
                # 清理可能的前导点
                return module.lstrip('.')
            except Exception:
                return None

        def _build_io_graph_heuristic(method_io_list: list) -> dict:
            """
            构建输入输出图（启发式规则）
            
            Args:
                method_io_list: 方法IO信息列表，每个元素包含：
                    - method_sig: 方法签名
                    - method_name: 方法名
                    - inputs: 输入参数列表 [{'name': str, 'type': str}]
                    - outputs: 返回值列表 [{'type': str}]
            
            Returns:
                输入输出图字典，包含 nodes 和 edges
            """
            nodes = []
            edges = []
            
            # 第一个方法的输入作为初始输入
            if method_io_list:
                first_method = method_io_list[0]
                if first_method.get('inputs'):
                    input_node = {
                        'id': 'input_0',
                        'label': f"输入: {first_method['inputs'][0].get('name', 'data')}",
                        'type': first_method['inputs'][0].get('type', 'unknown')
                    }
                    nodes.append(input_node)
                    
                    # 第一个方法节点
                    method_node = {
                        'id': 'method_0',
                        'label': first_method.get('method_name', 'unknown'),
                        'type': '操作节点'
                    }
                    nodes.append(method_node)
                    edges.append({'source': 'input_0', 'target': 'method_0', 'label': '输入'})
            
            # 中间节点和边
            for i, method_io in enumerate(method_io_list):
                if i > 0:
                    # 方法节点
                    method_node = {
                        'id': f'method_{i}',
                        'label': method_io.get('method_name', 'unknown'),
                        'type': '操作节点'
                    }
                    nodes.append(method_node)
                    
                    # 从前一个方法的输出到当前方法的输入
                    prev_output = method_io_list[i-1].get('outputs', [])
                    if prev_output:
                        intermediate_node = {
                            'id': f'intermediate_{i-1}',
                            'label': f"中间数据: {prev_output[0].get('type', 'data')}",
                            'type': prev_output[0].get('type', 'unknown')
                        }
                        nodes.append(intermediate_node)
                        edges.append({'source': f'method_{i-1}', 'target': f'intermediate_{i-1}', 'label': '输出'})
                        edges.append({'source': f'intermediate_{i-1}', 'target': f'method_{i}', 'label': '输入'})
                    else:
                        # 如果没有输出，直接连接方法节点
                        edges.append({'source': f'method_{i-1}', 'target': f'method_{i}', 'label': '调用'})
            
            # 最终输出
            if method_io_list:
                last_method = method_io_list[-1]
                if last_method.get('outputs'):
                    output_node = {
                        'id': 'output_final',
                        'label': f"最终输出: {last_method['outputs'][0].get('type', 'result')}",
                        'type': last_method['outputs'][0].get('type', 'unknown')
                    }
                    nodes.append(output_node)
                    edges.append({'source': f'method_{len(method_io_list)-1}', 'target': 'output_final', 'label': '输出'})
            
            return {
                'nodes': nodes,
                'edges': edges
            }
        
        def _is_valid_method_signature(method_sig: str) -> bool:
            """
            检查方法签名是否是有效的方法调用（过滤掉容器方法和属性访问链）
            
            Args:
                method_sig: 方法签名，如 "dict.values", "func.incoming_calls.values"
            
            Returns:
                True 如果是有效的方法调用，False 如果是容器方法或属性访问链
            """
            if not method_sig:
                return False
            
            # 如果没有点号，可能是全局函数，允许通过
            if '.' not in method_sig:
                return True
            
            parts = method_sig.split('.')
            
            # Python内置容器类型及其方法
            builtin_container_types = {
                'dict', 'list', 'set', 'tuple', 'str', 'int', 'float', 'bool',
                'bytes', 'bytearray', 'frozenset', 'deque', 'defaultdict',
                'OrderedDict', 'Counter', 'ChainMap'
            }
            builtin_container_methods = {
                'values', 'keys', 'items', 'get', 'pop', 'update', 'clear',
                'append', 'extend', 'insert', 'remove', 'index', 'count',
                'add', 'discard', 'union', 'intersection', 'difference',
                'split', 'join', 'strip', 'replace', 'find', 'startswith',
                'endswith', 'lower', 'upper', 'capitalize', 'encode', 'decode',
                'format', 'isalpha', 'isdigit', 'isspace'
            }
            
            # 如果只有两部分，检查是否是内置容器方法
            if len(parts) == 2:
                base, method = parts
                if base in builtin_container_types and method in builtin_container_methods:
                    return False
            
            # 如果超过两部分，可能是属性访问链（如 func.incoming_calls.values）
            if len(parts) >= 3:
                # 常见的属性名模式（非类名）
                common_attributes = {
                    'incoming_calls', 'outgoing_calls', 'calls', 'called_by',
                    'methods', 'fields', 'attributes', 'properties',
                    'items', 'values', 'keys', 'entries',
                    'data', 'config', 'settings', 'params', 'args',
                    'kwargs', 'result', 'output', 'input', 'response',
                    'request', 'headers', 'body', 'content', 'text',
                    'json', 'xml', 'html', 'url', 'path', 'file',
                    'dir', 'folder', 'name', 'id', 'type', 'value'
                }
                
                # 检查中间部分是否是属性而非类名
                for i in range(1, len(parts) - 1):
                    if parts[i] in common_attributes:
                        # 这是属性访问链，不是方法调用
                        return False
            
            return True
        
        def _build_fqmn_for_method(method_info, class_info, default_sig: str) -> Tuple[str, str]:
            """
            构造 FQMN（完全限定方法名），统一为4段格式：包.文件.类.方法
            返回: (fqmn, origin) 元组
            - origin: 'internal' / 'external' / 'builtin' / 'third_party'
            
            统一格式说明：
            - 4段（项目内部类方法）: 包.文件.类.方法
              例如: analysis.path_level_analyzer.Parser.parse
            - 4段（项目内部全局函数）: 包.文件.module.函数
              例如: analysis.utils.module.helper_func
            - 4段（标准库）: python.builtins.module.函数
              例如: python.builtins.module.max
            - 4段（外部库/未解析）: external.unknown.类.方法 或 external.unknown.module.函数
              例如: external.unknown.SomeClass.method
            """
            # 标准库内建函数（如 max、len 等）
            if class_info is None and ('.' not in default_sig):
                import builtins as _builtins
                if hasattr(_builtins, default_sig):
                    # 统一为4段：python.builtins.module.函数名
                    return f"python.builtins.module.{default_sig}", 'builtin'

            # 优先使用源码位置推断模块名（包.文件）
            module_name = None
            file_path = None
            if method_info is not None and getattr(method_info, 'source_location', None):
                file_path = getattr(method_info.source_location, 'file_path', None)
            if not file_path and class_info is not None and getattr(class_info, 'source_location', None):
                file_path = getattr(class_info.source_location, 'file_path', None)
            module_name = _get_module_name_from_source(file_path)

            # 如果ClassInfo有full_name且包含包名，也可以作为候选
            if class_info is not None:
                class_full_name = getattr(class_info, "full_name", None)
                if class_full_name and '.' in class_full_name and not module_name:
                    # full_name 形如 package.module.ClassName
                    module_name = class_full_name.rsplit('.', 1)[0]

            # 项目内部类方法：统一为 包.文件.类.方法（4段）
            if class_info is not None and method_info is not None:
                class_name = class_info.name
                method_name = getattr(method_info, 'name', None) or default_sig.rsplit('.', 1)[-1]
                if module_name:
                    # 4段：包.文件.类.方法
                    return f"{module_name}.{class_name}.{method_name}", 'internal'
                # 无法获取模块名，使用 external.unknown.类.方法（4段）
                return f"external.unknown.{class_name}.{method_name}", 'external'

            # 项目内部全局函数：统一为 包.文件.module.函数（4段）
            if method_info is not None and class_info is None:
                func_name = getattr(method_info, 'name', None) or default_sig
                if module_name:
                    # 4段：包.文件.module.函数
                    return f"{module_name}.module.{func_name}", 'internal'
                # 无法确定模块名，使用 external.unknown.module.函数（4段）
                return f"external.unknown.module.{func_name}", 'external'

            # 对于形如 obj.method 的调用但未能解析到类信息
            if '.' in default_sig:
                obj_name, method_name = default_sig.rsplit('.', 1)
                # 统一为4段：external.unknown.对象.方法
                return f"external.unknown.{obj_name}.{method_name}", 'external'

            # 最后兜底：统一为4段：external.unknown.module.函数名
            return f"external.unknown.module.{default_sig}", 'external'
        update_analysis_status(
            is_analyzing=True,
            error=None,
            progress=5,
            status='初始化分析...'
        )
        
        print(f"\n{'='*60}", flush=True)
        print(f"[app.py] 🚀 开始功能层级分析: {project_path}", flush=True)
        print(f"{'='*60}", flush=True)
        
        # ===== 步骤1：代码分析获取调用图 =====
        update_analysis_status(progress=10, status='步骤1/6: 分析代码获取调用图...')
        print(f"[app.py] 步骤1: 分析代码获取调用图...", flush=True)
        _safe_flush()
        
        timing.start_phase('code_analysis_and_call_graph', layer='default_visible', blocking=True)
        if precomputed_analyzer is not None and precomputed_graph_data is not None:
            analyzer = precomputed_analyzer
            graph_data = precomputed_graph_data
            print(f"[app.py] ♻️ 复用主分析产物进入功能层级分析", flush=True)
        else:
            analyzer = CodeAnalyzer(project_path)
            graph_data = analyzer.analyze(project_path)
        timing.end_phase('code_analysis_and_call_graph')
        
        if not hasattr(analyzer, 'call_graph_analyzer'):
            raise Exception('未找到call_graph_analyzer')
        
        call_graph = analyzer.call_graph_analyzer.call_graph
        print(f"[app.py] ✅ 获取调用图: {len(call_graph)} 个方法", flush=True)
        _safe_flush()
        
        # ===== 步骤2：社区检测获取功能分区 =====
        update_analysis_status(progress=30, status='步骤2/7: 社区检测获取功能分区...')
        print(f"[app.py] 步骤2: 社区检测获取功能分区...", flush=True)
        _safe_flush()
        
        timing.start_phase('partition_build', layer='default_visible', blocking=True)
        detector = CommunityDetector()
        partitions = detector.detect_communities(call_graph, algorithm="louvain")
        print(f"[app.py] ✅ 检测到 {len(partitions)} 个功能分区", flush=True)
        
        # 按方法数量排序
        partitions.sort(key=lambda p: len(p.get("methods", [])), reverse=True)
        
        # 显示每个分区的详细信息
        print(f"[app.py]   分区详情（按方法数量排序）:", flush=True)
        for idx, partition in enumerate(partitions, 1):
            partition_id = partition.get("partition_id", "unknown")
            methods = partition.get("methods", [])
            print(f"[app.py]     [{idx}] {partition_id}: {len(methods)} 个方法", flush=True)
            if len(methods) <= 10:
                # 如果方法数较少，显示所有方法
                print(f"[app.py]        方法列表: {', '.join(methods[:10])}", flush=True)
            else:
                # 如果方法数较多，只显示前5个
                print(f"[app.py]        方法列表（前5个）: {', '.join(methods[:5])} ... (共{len(methods)}个)", flush=True)
        
        _safe_flush()
        
        # ===== 步骤2.5：暂时跳过LLM增强，等待步骤6.5.5确定符合要求的分区后再进行 =====
        update_analysis_status(progress=35, status='步骤2.5/7: 暂缓LLM增强，等待路径分析结果...')
        print(f"[app.py] 步骤2.5: 暂缓LLM增强，将在确定符合要求的分区后再进行LLM分析...", flush=True)
        print(f"[app.py]   ℹ️  策略: 只对符合约束的功能路径数量（10-20条）的分区进行LLM语义分析", flush=True)
        _safe_flush()
        
        # 保存LLM agent供后续使用（如果可用）
        llm_agent_for_partition = None
        if ENABLE_PARTITION_LLM_SEMANTICS:
            try:
                llm_agent_for_partition = _create_code_understanding_agent()
                if llm_agent_for_partition:
                    llm_agent_for_partition.project_path = project_path
                    print(f"[app.py]   ✓ 分区级LLM agent已初始化", flush=True)
                else:
                    print(f"[app.py]   ⚠️ DeepSeek 未配置，将跳过分区级LLM增强", flush=True)
            except Exception as e:
                print(f"[app.py]   ⚠️ 分区级LLM agent初始化失败: {e}，将跳过LLM增强", flush=True)
                import traceback
                _safe_traceback_print()
        else:
            print(f"[app.py]   ℹ️ Workset1: 分区级LLM语义分析已关闭", flush=True)
        
        # 暂时不进行LLM增强，保留原始分区信息
        print(f"[app.py] ✅ 暂缓LLM增强完成，将在步骤6.5.5之后对符合要求的分区进行LLM分析", flush=True)
        
        # ===== 步骤2.6：去重和名称冲突处理 =====
        update_analysis_status(progress=37, status='步骤2.6/7: 去重和名称冲突处理...')
        print(f"[app.py] 步骤2.6: 去重和名称冲突处理...", flush=True)
        _safe_flush()
        
        partitions = deduplicate_and_resolve_name_conflicts(partitions)
        
        # ===== 步骤2.7：创建演示分区（如果需要，提前创建以便后续步骤能处理） =====
        # 【演示代码生成开关】设置为 False 可暂时关闭演示代码生成功能
        # 如需重新启用，将 ENABLE_DEMO_CODE_GENERATION 设置为 True
        ENABLE_DEMO_CODE_GENERATION = False  # 禁用演示代码生成（避免混淆实际项目分析结果）
        
        # 使用外部模块处理演示分区创建（避免复杂的缩进问题）
        # 确保 tests/tools 在 sys.path 中
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
        tools_path = os.path.join(project_root, 'tests', 'tools')
        if tools_path not in sys.path:
            sys.path.append(tools_path)
            
        try:
            from demo_partition_manager import create_demo_partition_step2_7
        except ImportError:
            # 尝试另一种路径结构（如果上面的project_root计算不正确）
            # 假设当前文件在 app/services/，那么 tests/tools 应该是 ../../tests/tools
            app_dir = os.path.dirname(os.path.dirname(current_dir))
            tools_path_alt = os.path.join(app_dir, 'tests', 'tools')
            if tools_path_alt not in sys.path:
                sys.path.append(tools_path_alt)
            from demo_partition_manager import create_demo_partition_step2_7
        
        demo_partition_created, demo_partition_id, demo_partition_name, demo_paths = create_demo_partition_step2_7(
            call_graph, partitions, enable_demo=ENABLE_DEMO_CODE_GENERATION
        )
        timing.end_phase('partition_build')
        timing.mark_ready('basic_result')
        
        # 注意：所有演示代码生成逻辑已移动到 demo_partition_manager.py
        # 如需查看详细实现，请参考 demo_partition_manager.py 文件
        
        # ===== 步骤3：生成调用图 =====
        update_analysis_status(progress=40, status='步骤3/7: 生成调用图...')
        print(f"[app.py] 步骤3: 生成调用图...", flush=True)
        _safe_flush()
        
        timing.start_phase('call_graph_generation', layer='expand_visible', blocking=True)
        partition_analyses = {}
        
        # 检查演示分区是否在partitions列表中
        demo_partition_found = False
        for p in partitions:
            if p.get("is_demo", False) and p.get("partition_id") == demo_partition_id:
                demo_partition_found = True
                print(f"[app.py]   🔍 在partitions列表中找到演示分区: {demo_partition_id}", flush=True)
                break
        
        if not demo_partition_found and demo_partition_created:
            print(f"[app.py]   ⚠️ 警告：演示分区已创建但未在partitions列表中找到！", flush=True)
            print(f"[app.py]      - demo_partition_created: {demo_partition_created}", flush=True)
            print(f"[app.py]      - demo_partition_id: {demo_partition_id}", flush=True)
            print(f"[app.py]      - partitions列表中的分区ID: {[p.get('partition_id') for p in partitions[:5]]}", flush=True)
        
        call_graph_worker_count = _get_parallel_worker_count(len(partitions), limit=8)
        with ThreadPoolExecutor(max_workers=call_graph_worker_count, thread_name_prefix='fh-call-graph') as executor:
            future_to_partition = {
                executor.submit(_generate_partition_call_graph_item, partition, call_graph): partition for partition in partitions
            }
            call_graph_results_by_partition: Dict[str, Dict[str, Any]] = {}
            for future in as_completed(future_to_partition):
                partition = future_to_partition[future]
                partition_id = partition.get('partition_id', 'unknown')
                is_demo = partition.get('is_demo', False)
                demo_marker = ' [演示分区]' if is_demo else ''
                try:
                    item = future.result()
                    call_graph_results_by_partition[partition_id] = item.get('call_graph') or {}
                    print(f"[app.py]   ✓ 分区 {partition_id}{demo_marker} 调用图生成成功", flush=True)
                except Exception as e:
                    print(f"[app.py]   ⚠️ 分区 {partition_id}{demo_marker} 调用图生成失败: {e}", flush=True)
                    import traceback
                    _safe_traceback_print()

        for partition in partitions:
            partition_id = partition.get('partition_id', 'unknown')
            if partition_id not in partition_analyses:
                partition_analyses[partition_id] = {}
            partition_analyses[partition_id]['call_graph'] = call_graph_results_by_partition.get(partition_id, {})
        
        print(f"[app.py] ✅ 调用图生成完成，共 {len(partition_analyses)} 个分区", flush=True)
        timing.end_phase('call_graph_generation')
        _safe_flush()
        
        # ===== 步骤4：生成超图 =====
        update_analysis_status(progress=50, status='步骤4/7: 生成超图...')
        print(f"[app.py] 步骤4: 生成超图...", flush=True)
        _safe_flush()
        
        timing.start_phase('hypergraph_generation', layer='expand_visible', blocking=True)
        hypergraph_generator = FunctionCallHypergraphGenerator(call_graph)
        # 保存每个分区的paths_map，供后续路径级别分析使用
        partition_paths_map = {}
        
        # 如果演示分区已在步骤2.7创建，保存其路径信息
        if demo_partition_created and demo_paths:
            # 从步骤2.7中获取演示分区的路径信息
            demo_paths_map = {}
            for idx, path in enumerate(demo_paths):
                leaf_node = path[0]
                if leaf_node not in demo_paths_map:
                    demo_paths_map[leaf_node] = []
                demo_paths_map[leaf_node].append(path)
            partition_paths_map[demo_partition_id] = demo_paths_map
            print(f"[app.py]   ℹ️  演示分区路径信息已从步骤2.7加载: {len(demo_paths)} 条路径", flush=True)
        
        print(f"[app.py]   开始为 {len(partitions)} 个分区生成超图和路径...", flush=True)
        
        # 检查演示分区是否在partitions列表中
        if demo_partition_created:
            demo_found_in_partitions = any(p.get("is_demo", False) and p.get("partition_id") == demo_partition_id for p in partitions)
            if demo_found_in_partitions:
                print(f"[app.py]   🔍 在partitions列表中找到演示分区: {demo_partition_id}", flush=True)
            else:
                print(f"[app.py]   ⚠️ 警告：演示分区已创建但未在partitions列表中找到！", flush=True)
                print(f"[app.py]      - demo_partition_created: {demo_partition_created}", flush=True)
                print(f"[app.py]      - demo_partition_id: {demo_partition_id}", flush=True)
                print(f"[app.py]      - partitions列表中的分区ID: {[p.get('partition_id') for p in partitions[:5]]}", flush=True)
        
        timing.end_phase('hypergraph_generation')
        layer_states['default_visible'] = _build_layer_state('ready', ['hierarchy', 'partition_call_graph', 'partition_hypergraph'], visible=ENABLE_DEFAULT_VISIBLE_LAYER)
        _publish_partial_result(55, 'Workset3: 基础分区结果已可见', include_expand=False, include_advanced=False)
        timing.start_phase('entry_point_identification', layer='default_visible', blocking=True)

        # ===== 预先识别入口点（供 Phase 1 / Task 1.1 路径找全增强使用）=====
        # 说明：原流程在“超图生成”之后才识别入口点；这里提前一遍，供路径探索的入口点前向策略使用。
        # 行为不变：后续仍会把 entry_points 写入 partition_analyses（沿用同一份结果）。
        entry_point_generator = EntryPointIdentifierGenerator(call_graph, analyzer.report, None)
        entry_points_map = entry_point_generator.identify_all_partitions_entry_points(partitions, score_threshold=0.3)

        regular_partitions = [partition for partition in partitions if not (partition.get('is_demo', False) and demo_partition_created and partition.get('partition_id') == demo_partition_id)]
        structural_path_partition_limit = _get_structural_path_partition_limit(PATH_ANALYSIS_PARTITION_LIMIT, len(regular_partitions))
        structural_path_partition_ids = {
            partition.get('partition_id', 'unknown')
            for partition in sorted(
                regular_partitions,
                key=lambda item: len(item.get('methods', [])),
                reverse=True,
            )[:structural_path_partition_limit]
        }
        hypergraph_results_by_partition: Dict[str, Dict[str, Any]] = {}
        hypergraph_worker_count = _get_parallel_worker_count(len(regular_partitions), limit=8)
        if regular_partitions:
            with ThreadPoolExecutor(max_workers=hypergraph_worker_count, thread_name_prefix='fh-hypergraph') as executor:
                future_to_partition = {
                    executor.submit(
                        _generate_partition_hypergraph_item,
                        partition,
                        call_graph,
                        analyzer.report,
                        entry_points_map.get(partition.get('partition_id', 'unknown'), []),
                        ENABLE_STRUCTURAL_PATHS_ALL or partition.get('partition_id', 'unknown') in structural_path_partition_ids,
                    ): partition for partition in regular_partitions
                }
                for future in as_completed(future_to_partition):
                    partition = future_to_partition[future]
                    partition_id = partition.get('partition_id', 'unknown')
                    try:
                        hypergraph_results_by_partition[partition_id] = future.result()
                    except Exception as e:
                        print(f"[app.py]   ⚠️ 分区 {partition_id} 超图生成失败: {e}", flush=True)
                        import traceback
                        _safe_traceback_print()
                        hypergraph_results_by_partition[partition_id] = {'partition_id': partition_id, 'paths_map': {}, 'hypergraph': {}, 'hypergraph_viz': {'edges': [], 'statistics': {}}, 'function_node_count': 0, 'total_paths': 0, 'leaf_node_count': 0, 'total_nodes': 0, 'method_nodes': 0, 'function_nodes': 0, 'hyperedge_count': 0, 'total_edges': 0, 'direct_call_edges': 0}

        for idx, partition in enumerate(partitions, 1):
            partition_id = partition.get("partition_id", "unknown")
            partition_name = partition.get("name", "unknown")
            partition_methods = set(partition.get("methods", []))  # 关键：获取分区的methods集合
            
            # 如果是演示分区且已在步骤2.7创建，跳过路径生成（路径已存在）
            is_demo = partition.get("is_demo", False)
            if is_demo and demo_partition_created and partition_id == demo_partition_id:
                print(f"[app.py]   🔍 处理演示分区: partition_id={partition_id}, is_demo={is_demo}, demo_partition_created={demo_partition_created}, demo_partition_id={demo_partition_id}", flush=True)
                print(f"[app.py]   [{idx}/{len(partitions)}] 处理演示分区 {partition_id} ({partition_name}): {len(partition_methods)} 个方法", flush=True)
                print(f"[app.py]     ℹ️  演示分区路径已在步骤2.7创建，跳过路径生成", flush=True)
                
                try:
                    # 只生成超图，不进行路径探索
                    hypergraph = hypergraph_generator.generate_partition_hypergraph(partition)
                    
                    # 使用步骤2.7中创建的路径信息
                    paths_map = partition_paths_map.get(partition_id, {})
                    total_paths = sum(len(paths) for paths in paths_map.values())
                    leaf_node_count = len(paths_map)
                    partition_analyses[partition_id]['paths_map'] = copy.deepcopy(paths_map)
                    
                    print(f"[app.py]     ✓ 演示分区超图生成成功:", flush=True)
                    print(f"[app.py]       - 超边数: {len(hypergraph.hyperedges)}", flush=True)
                    print(f"[app.py]       - 叶子节点数: {leaf_node_count}", flush=True)
                    print(f"[app.py]       - 总路径数: {total_paths}", flush=True)
                    
                    # 确保 partition_analyses 中存在该分区
                    if partition_id not in partition_analyses:
                        partition_analyses[partition_id] = {}
                    hypergraph_dict = hypergraph.to_dict()
                    partition_analyses[partition_id]['hypergraph'] = hypergraph_dict
                    hypergraph_viz = hypergraph.to_visualization_data()
                    partition_analyses[partition_id]['hypergraph_viz'] = hypergraph_viz
                    print(f"[app.py]     ✓ 演示分区超图已保存到 partition_analyses[{partition_id}]", flush=True)
                    print(f"[app.py]       - hypergraph键存在: {'hypergraph' in partition_analyses[partition_id]}", flush=True)
                    print(f"[app.py]       - hypergraph_viz键存在: {'hypergraph_viz' in partition_analyses[partition_id]}", flush=True)
                    
                    # 详细日志：超图统计信息
                    method_nodes = len([n for n in hypergraph.nodes.values() if n.get('type') == 'method'])
                    function_nodes = len([n for n in hypergraph.nodes.values() if n.get('type') == 'function'])
                    total_nodes = len(hypergraph.nodes)
                    total_edges = len(hypergraph_viz.get('edges', []))
                    direct_call_edges = hypergraph_viz.get('statistics', {}).get('direct_call_edges', 0)
                    
                    print(f"[app.py]     ✓ 演示分区超图生成成功:", flush=True)
                    print(f"[app.py]       - 总节点数: {total_nodes} (方法节点: {method_nodes}, 功能节点: {function_nodes})", flush=True)
                    print(f"[app.py]       - 超边数: {len(hypergraph.hyperedges)}", flush=True)
                    print(f"[app.py]       - 可视化边数: {total_edges} (其中直接调用边: {direct_call_edges})", flush=True)
                    if total_edges == 0:
                        print(f"[app.py]       ⚠️ 警告：超图中没有边，可能无法显示连线", flush=True)
                        print(f"[app.py]         可能原因：分区内方法之间没有调用关系", flush=True)
                    print(f"[app.py]   ✓ 分区 {partition_id} 超图生成成功", flush=True)
                except Exception as e:
                    print(f"[app.py]   ⚠️ 演示分区 {partition_id} 超图生成失败: {e}", flush=True)
                    import traceback
                    _safe_traceback_print()
                    partition_paths_map[partition_id] = {}
                
                continue  # 跳过后续的路径生成逻辑
            
            print(f"[app.py]   [{idx}/{len(partitions)}] 处理分区 {partition_id} ({partition_name}): {len(partition_methods)} 个方法", flush=True)
            
            try:
                hypergraph_result = hypergraph_results_by_partition.get(partition_id) or {}
                partition_paths_map[partition_id] = hypergraph_result.get('paths_map') or {}
                print(f"[app.py]     ✓ 分区 {partition_id} 功能节点增强完成:", flush=True)
                print(f"[app.py]       - 功能节点数: {hypergraph_result.get('function_node_count', 0)}", flush=True)
                print(f"[app.py]       - 叶子节点数: {hypergraph_result.get('leaf_node_count', 0)}", flush=True)
                print(f"[app.py]       - 总路径数: {hypergraph_result.get('total_paths', 0)}", flush=True)
                if hypergraph_result.get('total_paths', 0) == 0:
                    print(f"[app.py]       ⚠️  警告: 该分区没有生成任何路径", flush=True)
                    print(f"[app.py]         可能原因: 分区内方法之间没有调用关系，或所有方法都是入口点", flush=True)

                if partition_id not in partition_analyses:
                    partition_analyses[partition_id] = {}
                partition_analyses[partition_id]['hypergraph'] = hypergraph_result.get('hypergraph') or {}
                partition_analyses[partition_id]['hypergraph_viz'] = hypergraph_result.get('hypergraph_viz') or {'edges': [], 'statistics': {}}
                partition_analyses[partition_id]['paths_map'] = copy.deepcopy(partition_paths_map.get(partition_id) or {})
                
                # 详细日志：超图统计信息
                method_nodes = hypergraph_result.get('method_nodes', 0)
                function_nodes = hypergraph_result.get('function_nodes', 0)
                total_nodes = hypergraph_result.get('total_nodes', 0)
                total_edges = hypergraph_result.get('total_edges', 0)
                direct_call_edges = hypergraph_result.get('direct_call_edges', 0)
                
                print(f"[app.py]     ✓ 分区 {partition_id} 超图统计:", flush=True)
                print(f"[app.py]       - 总节点数: {total_nodes} (方法节点: {method_nodes}, 功能节点: {function_nodes})", flush=True)
                print(f"[app.py]       - 超边数: {hypergraph_result.get('hyperedge_count', 0)}", flush=True)
                print(f"[app.py]       - 可视化边数: {total_edges} (其中直接调用边: {direct_call_edges})", flush=True)
                if total_edges == 0:
                    print(f"[app.py]       ⚠️ 警告：超图中没有边，可能无法显示连线", flush=True)
                    print(f"[app.py]         可能原因：分区内方法之间没有调用关系", flush=True)
                print(f"[app.py]   ✓ 分区 {partition_id} 超图生成成功", flush=True)
            except Exception as e:
                print(f"[app.py]   ⚠️ 分区 {partition_id} 超图生成失败: {e}", flush=True)
                import traceback
                _safe_traceback_print()
                partition_paths_map[partition_id] = {}
        
        print(f"[app.py] ✅ 超图生成完成", flush=True)
        _safe_flush()
        
        # ===== 步骤5：识别入口点 =====
        update_analysis_status(progress=60, status='步骤5/7: 识别入口点...')
        print(f"[app.py] 步骤5: 识别入口点...", flush=True)
        _safe_flush()
        # 复用前面已计算的 entry_points_map（避免重复计算）
        
        # 检查演示分区是否在entry_points_map中
        if demo_partition_created:
            if demo_partition_id in entry_points_map:
                print(f"[app.py]   🔍 演示分区 {demo_partition_id} 在入口点识别结果中找到", flush=True)
            else:
                print(f"[app.py]   ⚠️ 警告：演示分区 {demo_partition_id} 未在入口点识别结果中找到！", flush=True)
                print(f"[app.py]      - entry_points_map中的分区ID: {list(entry_points_map.keys())[:5]}", flush=True)
        
        for partition_id, entry_points in entry_points_map.items():
            # 确保 partition_analyses 中存在该分区
            if partition_id not in partition_analyses:
                partition_analyses[partition_id] = {}
                print(f"[app.py]   ⚠️ 分区 {partition_id} 在entry_points_map中但不在partition_analyses中，已创建", flush=True)
            partition_analyses[partition_id]['entry_points'] = [
                {
                    'method_signature': ep.method_sig,
                    'score': ep.score,
                    'reasons': ep.reasons
                }
                for ep in entry_points
            ]
            is_demo = partition_id == demo_partition_id and demo_partition_created
            demo_marker = " [演示分区]" if is_demo else ""
            print(f"[app.py]   ✓ 分区 {partition_id}{demo_marker} 入口点识别完成: {len(entry_points)} 个入口点", flush=True)
            if is_demo:
                print(f"[app.py]     ✓ [步骤5] 演示分区入口点已保存", flush=True)
                print(f"[app.py]       - partition_analyses[{partition_id}]键存在: {partition_id in partition_analyses}", flush=True)
                print(f"[app.py]       - entry_points键存在: {'entry_points' in partition_analyses[partition_id]}", flush=True)
                print(f"[app.py]       - entry_points数量: {len(partition_analyses[partition_id]['entry_points'])}", flush=True)
        
        # 检查是否有分区没有入口点数据
        partitions_without_entry_points = []
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            if partition_id not in entry_points_map:
                partitions_without_entry_points.append(partition_id)
        
        if partitions_without_entry_points:
            print(f"[app.py]   ⚠️ 警告：以下分区没有入口点数据: {partitions_without_entry_points[:10]}", flush=True)
            if len(partitions_without_entry_points) > 10:
                print(f"[app.py]       ... 还有 {len(partitions_without_entry_points) - 10} 个分区", flush=True)
        
        print(f"[app.py] ✅ 入口点识别完成", flush=True)
        timing.end_phase('entry_point_identification')
        _safe_flush()
        
        # ===== 步骤6：生成数据流图和控制流图 =====
        update_analysis_status(progress=70, status='步骤6/7: 生成数据流图和控制流图...')
        print(f"[app.py] 步骤6: 生成数据流图和控制流图...", flush=True)
        _safe_flush()
        
        timing.start_phase('partition_data_control_flow', layer='expand_visible', blocking=True)
        dataflow_generator = PartitionDataFlowGenerator(
            call_graph,
            analyzer.report,
            analyzer.data_flow_analyzer if hasattr(analyzer, 'data_flow_analyzer') else None
        )
        controlflow_generator = PartitionControlFlowGenerator(call_graph, analyzer.report)
        
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            try:
                # 数据流图
                entry_points = entry_points_map.get(partition_id, [])
                partition_dataflow = dataflow_generator.generate_partition_data_flow(partition, entry_points)
                if partition_id not in partition_analyses:
                    partition_analyses[partition_id] = {}
                # 保存数据流图的完整信息
                partition_analyses[partition_id]['dataflow'] = {
                    'nodes': partition_dataflow.merged_nodes,  # 字典格式
                    'edges': partition_dataflow.merged_edges,  # 列表格式
                    'parameter_flows': partition_dataflow.parameter_flows,
                    'return_flows': partition_dataflow.return_value_flows,
                    'shared_states': list(partition_dataflow.shared_states),
                    'viz_data': partition_dataflow.to_visualization_data()  # 可视化数据
                }
                print(f"[app.py]   ✓ 分区 {partition_id} 数据流图生成成功: {len(partition_dataflow.merged_nodes)} 个节点, {len(partition_dataflow.merged_edges)} 条边", flush=True)
                
                # 控制流图
                partition_controlflow = controlflow_generator.generate_partition_control_flow(partition)
                # 转换节点为字典格式
                nodes_dict = {}
                for node_id, node in partition_controlflow.merged_nodes.items():
                    nodes_dict[node_id] = {
                        'id': node.node_id,
                        'label': node.label,
                        'type': node.node_type,
                        'line_number': node.line_number,
                        'code': node.code[:200] if node.code else "",
                        'metadata': node.metadata if hasattr(node, 'metadata') else {}
                    }
                # 转换边为字典格式
                edges_list = []
                for edge in partition_controlflow.merged_edges:
                    edge_dict = {
                        'source': edge.source_id,
                        'target': edge.target_id,
                        'type': edge.edge_type
                    }
                    if hasattr(edge, 'metadata') and edge.metadata:
                        edge_dict['metadata'] = edge.metadata
                    edges_list.append(edge_dict)
                
                partition_analyses[partition_id]['controlflow'] = {
                    'nodes': nodes_dict,
                    'edges': edges_list,
                    'method_call_edges': partition_controlflow.method_call_edges,
                    'cycles': partition_controlflow.cycles,
                    'dot': partition_controlflow.to_dot(),
                    'viz_data': partition_controlflow.to_visualization_data()  # 可视化数据
                }
                print(f"[app.py]   ✓ 分区 {partition_id} 控制流图生成成功: {len(nodes_dict)} 个节点, {len(edges_list)} 条边", flush=True)
            except Exception as e:
                print(f"[app.py]   ⚠️ 分区 {partition_id} 数据流/控制流图生成失败: {e}", flush=True)
                import traceback
                _safe_traceback_print()
        
        print(f"[app.py] ✅ 数据流图和控制流图生成完成", flush=True)
        timing.end_phase('partition_data_control_flow')
        _safe_flush()
        
        # ===== 步骤6.5：为每个分区生成FQMN、输入输出汇总信息 =====
        update_analysis_status(progress=80, status='步骤6.5/7: 生成FQMN和输入输出汇总...')
        log_print(f"[app.py] 步骤6.5: 为每个分区生成FQMN（完全限定方法名）和输入输出汇总信息...")
        
        timing.start_phase('fqmn_io_summary', layer='default_visible', blocking=True)
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            partition_methods = set(partition.get("methods", []))
            
            log_print(f"[app.py]   处理分区 {partition_id}: {len(partition_methods)} 个方法")
            
            # 汇总FQMN、输入输出信息
            partition_fqns = []
            partition_inputs = []  # 所有方法的输入参数
            partition_outputs = []  # 所有方法的返回值
            
            filtered_count = 0  # 统计过滤的非方法调用数量
            method_info_found_count = 0  # 统计找到method_info的数量
            method_info_not_found_count = 0  # 统计未找到method_info的数量
            
            for method_sig in partition_methods:
                # 过滤：跳过非方法调用（容器方法、属性访问链等）
                if not _is_valid_method_signature(method_sig):
                    filtered_count += 1
                    if filtered_count <= 5:  # 只显示前5个，避免日志过多
                        log_print(f"[app.py]     ⚠️ 跳过非方法调用: {method_sig}")
                    continue
                
                # 获取方法的FQMN（包名.类名.方法名）
                method_fqn = method_sig
                method_info = None
                class_info = None
                
                # 从analyzer.report中查找方法信息
                method_origin = 'external'  # 默认来源
                if '.' in method_sig:
                    class_name, method_name = method_sig.rsplit('.', 1)
                    if analyzer.report and class_name in analyzer.report.classes:
                        class_info = analyzer.report.classes[class_name]
                        if method_name in class_info.methods:
                            method_info = class_info.methods[method_name]
                            # 使用_build_fqmn_for_method构造完整的FQMN（统一4段格式）
                            method_fqn, method_origin = _build_fqmn_for_method(method_info, class_info, method_sig)
                            # 调试日志：显示FQMN生成过程
                            if method_fqn != method_sig:
                                file_path = None
                                if method_info and getattr(method_info, 'source_location', None):
                                    file_path = getattr(method_info.source_location, 'file_path', None)
                                elif class_info and getattr(class_info, 'source_location', None):
                                    file_path = getattr(class_info.source_location, 'file_path', None)
                                module_name = _get_module_name_from_source(file_path)
                                print(f"[app.py]     FQMN: {method_sig} -> {method_fqn} (来源: {method_origin}, 模块: {module_name or '未找到'}, 文件: {file_path or '未找到'})", flush=True)
                else:
                    # 全局函数
                    if analyzer.report:
                        for func_info in analyzer.report.functions:
                            if func_info.name == method_sig or func_info.signature == method_sig:
                                method_info = func_info
                                # 使用_build_fqmn_for_method构造完整的FQMN（统一4段格式）
                                method_fqn, method_origin = _build_fqmn_for_method(method_info, None, method_sig)
                                # 调试日志
                                if method_fqn != method_sig:
                                    file_path = None
                                    if method_info and getattr(method_info, 'source_location', None):
                                        file_path = getattr(method_info.source_location, 'file_path', None)
                                    module_name = _get_module_name_from_source(file_path)
                                    print(f"[app.py]     FQMN: {method_sig} -> {method_fqn} (来源: {method_origin}, 模块: {module_name or '未找到'}, 文件: {file_path or '未找到'})", flush=True)
                                break
                    # 如果找不到，尝试用_build_fqmn_for_method处理（可能是标准库函数）
                    if method_fqn == method_sig:
                        method_fqn, method_origin = _build_fqmn_for_method(None, None, method_sig)
                        if method_fqn != method_sig:
                            print(f"[app.py]     FQMN: {method_sig} -> {method_fqn} (来源: {method_origin})", flush=True)
                
                if method_fqn:
                    # 统一为4段格式，标注来源
                    parts = method_fqn.split('.')
                    segment_count = len(parts)
                    # 确保是4段（统一格式）
                    if segment_count != 4:
                        print(f"[app.py]     ⚠️ 警告: FQMN段数异常 {method_sig} -> {method_fqn} ({segment_count}段)", flush=True)
                    
                    partition_fqns.append({
                        'method_signature': method_sig,
                        'fqn': method_fqn,
                        'origin': method_origin,            # internal / external / builtin
                        'segment_count': segment_count     # 应该始终是4
                    })
                
                # 汇总输入参数
                has_inputs = False
                if method_info:
                    method_info_found_count += 1
                    if hasattr(method_info, 'parameters') and method_info.parameters:
                        for param in method_info.parameters:
                            # param是Parameter对象，访问其属性
                            param_name = getattr(param, 'name', 'unknown')
                            param_type = getattr(param, 'param_type', None) or getattr(param, 'type', None) or 'unknown'
                            partition_inputs.append({
                                'method_signature': method_sig,
                                'parameter_name': param_name,
                                'parameter_type': param_type,
                                'fqn': method_fqn
                            })
                            has_inputs = True
                else:
                    method_info_not_found_count += 1
                
                # 如果找不到输入参数，添加默认值（确保至少有一个输入输出记录）
                if not has_inputs:
                    partition_inputs.append({
                        'method_signature': method_sig,
                        'parameter_name': 'data',
                        'parameter_type': 'Any',
                        'fqn': method_fqn
                    })
                
                # 汇总返回值
                has_outputs = False
                if method_info and hasattr(method_info, 'return_type'):
                    return_type = method_info.return_type if isinstance(method_info.return_type, str) else (str(method_info.return_type) if method_info.return_type else '')
                    if return_type and return_type.lower() not in ['none', 'void', '']:
                        partition_outputs.append({
                            'method_signature': method_sig,
                            'return_type': return_type,
                            'fqn': method_fqn
                        })
                        has_outputs = True
                
                # 如果找不到返回值，添加默认值（确保至少有一个输入输出记录）
                if not has_outputs:
                    partition_outputs.append({
                        'method_signature': method_sig,
                        'return_type': 'Any',
                        'fqn': method_fqn
                    })
            
            # 将汇总信息添加到分区分析结果中
            if partition_id not in partition_analyses:
                partition_analyses[partition_id] = {}
            
            partition_analyses[partition_id]['fqns'] = partition_fqns
            partition_analyses[partition_id]['inputs'] = partition_inputs
            partition_analyses[partition_id]['outputs'] = partition_outputs
            partition_analyses[partition_id]['fqmn_info_map'] = _build_fqmn_info_map(partition_fqns)

            inputs_by_method: Dict[str, List[Dict[str, Any]]] = {}
            for item in partition_inputs:
                method_sig = item.get('method_signature')
                if not method_sig:
                    continue
                inputs_by_method.setdefault(method_sig, []).append(item)
            partition_analyses[partition_id]['inputs_by_method'] = inputs_by_method

            outputs_by_method: Dict[str, List[Dict[str, Any]]] = {}
            for item in partition_outputs:
                method_sig = item.get('method_signature')
                if not method_sig:
                    continue
                outputs_by_method.setdefault(method_sig, []).append(item)
            partition_analyses[partition_id]['outputs_by_method'] = outputs_by_method
            
            log_print(f"[app.py]   ✓ 分区 {partition_id} FQMN/IO汇总完成:")
            log_print(f"[app.py]     - FQMN数量: {len(partition_fqns)}")
            log_print(f"[app.py]     - 输入参数数量: {len(partition_inputs)}")
            log_print(f"[app.py]     - 返回值数量: {len(partition_outputs)}")
            log_print(f"[app.py]     - 找到method_info的方法: {method_info_found_count}")
            log_print(f"[app.py]     - 未找到method_info的方法: {method_info_not_found_count}")
            if filtered_count > 0:
                log_print(f"[app.py]     - 过滤了 {filtered_count} 个非方法调用（容器方法、属性访问链等）")
            
            # 详细日志：显示前5个输入和输出示例
            if partition_inputs:
                log_print(f"[app.py]     - 输入参数示例（前5个）:")
                for inp in partition_inputs[:5]:
                    log_print(f"[app.py]       • {inp.get('method_signature', 'unknown')}: {inp.get('parameter_name', 'unknown')}: {inp.get('parameter_type', 'unknown')}")
            else:
                log_print(f"[app.py]     ⚠️ 警告：分区 {partition_id} 的输入参数列表为空！")
            
            if partition_outputs:
                log_print(f"[app.py]     - 返回值示例（前5个）:")
                for out in partition_outputs[:5]:
                    log_print(f"[app.py]       • {out.get('method_signature', 'unknown')}: {out.get('return_type', 'unknown')}")
            else:
                log_print(f"[app.py]     ⚠️ 警告：分区 {partition_id} 的返回值列表为空！")
        
        log_print(f"[app.py] ✅ FQMN和输入输出汇总完成")
        timing.end_phase('fqmn_io_summary')
        layer_states['expand_visible'] = _build_layer_state('ready', ['entry_points', 'fqmn', 'inputs', 'outputs', 'dataflow', 'controlflow'], visible=ENABLE_EXPAND_VISIBLE_LAYER)
        _publish_partial_result(80, 'Workset3: 轻量展开层结果已补齐', include_expand=True, include_advanced=False)
        
        # ===== 步骤6.5.4：创建演示分区（如果所有分区都没有符合要求的路径） =====
        # 【演示代码生成开关】设置为 False 可暂时关闭演示代码生成功能
        # 如需重新启用，将 ENABLE_DEMO_CODE_GENERATION 设置为 True
        # 注意：此处的开关与步骤2.7使用同一个变量，确保两个地方保持一致
        
        # 使用外部模块处理演示分区创建（避免复杂的缩进问题）
        from demo_partition_manager import create_demo_partition_step6_5_4
        
        demo_partition_created, demo_partition_id = create_demo_partition_step6_5_4(
            partitions, partition_paths_map, partition_analyses, call_graph, analyzer.report,
            enable_demo=ENABLE_DEMO_CODE_GENERATION,
            demo_partition_created=demo_partition_created,
            demo_partition_id=demo_partition_id,
            demo_paths=demo_paths
        )
        
        # 注意：所有演示代码生成逻辑已移动到 demo_partition_manager.py
        # 如需查看详细实现，请参考 demo_partition_manager.py 文件
        
        # ===== 步骤6.6：为每个路径生成CFG、DFG和数据流图 =====
        update_analysis_status(progress=85, status='步骤6.6/7: 生成路径级别的CFG/DFG/数据流图...')
        # [已注释] 注释掉路径级别分析的详细日志
        # print(f"[app.py] 步骤6.6: 为每个路径生成CFG、DFG和数据流图...", flush=True)
        _safe_flush()
        
        # 获取LLM agent（如果可用且启用）
        llm_agent = None
        if ENABLE_PATH_LLM_ANALYSIS:
            try:
                llm_agent = _create_code_understanding_agent()
                if llm_agent:
                    llm_agent.project_path = project_path
                    # print(f"[app.py] ✓ LLM agent已初始化，将用于路径分析", flush=True)
                else:
                    # print(f"[app.py] ⚠️ DEEPSEEK_API_KEY未设置，跳过LLM分析", flush=True)
                    pass
            except Exception as e:
                print(f"[app.py] ⚠️ LLM agent初始化失败: {e}，将使用简单生成方式", flush=True)
        else:
            print(f"[app.py] ℹ️ Workset1: 路径级LLM分析已关闭", flush=True)
        
        # 选择合适的分区进行路径级别分析
        selected_partition = None
        selected_partition_stat = None

        cfg_dfg_llm_explain_max_paths = _get_cfg_dfg_llm_explain_max_paths_per_partition()

        path_llm_task_count = 0
        if ENABLE_CFG_DFG_LLM_EXPLAIN and llm_agent and cfg_dfg_llm_explain_max_paths > 0:
            path_llm_task_count += 1
        if ENABLE_PATH_LLM_ANALYSIS and llm_agent:
            path_llm_task_count += 2
        path_llm_worker_count = _get_path_llm_parallel_workers(path_llm_task_count)
        path_llm_parallel_enabled = (
            _is_path_llm_task_parallel_enabled()
            and path_llm_worker_count > 1
            and path_llm_task_count > 1
        )
        path_llm_executor: Optional[ThreadPoolExecutor] = None
        if path_llm_parallel_enabled:
            path_llm_executor = ThreadPoolExecutor(
                max_workers=path_llm_worker_count,
                thread_name_prefix='fh-path-llm-global',
            )
        
        # 优先检查是否有演示分区
        demo_partition = None
        demo_partition_stat = None
        timing.start_phase('path_supplement_generation', layer='advanced_visible', blocking=True)
        if ENABLE_PATH_SUPPLEMENT_GENERATION:
            print(f"[app.py] ℹ️ Workset1: 路径补充生成已启用", flush=True)
        else:
            print(f"[app.py] ℹ️ Workset1: 路径补充生成已关闭，沿用当前已有路径", flush=True)
        for partition in partitions:
            if partition.get("is_demo", False):
                demo_partition = partition
                for partition in partitions:
                    if partition.get("partition_id") == demo_partition_id:
                        demo_partition = partition
                        break
                
                if demo_partition:
                    # 1. 补充生成调用图
                    try:
                        print(f"[app.py]   [补充] 为演示分区生成调用图...", flush=True)
                        call_graph_generator = FunctionCallGraphGenerator(call_graph)
                        call_graph_result = call_graph_generator.generate_partition_call_graph(demo_partition)
                        partition_analyses[demo_partition_id]['call_graph'] = call_graph_result
                        nodes_count = len(call_graph_result.get('nodes', []))
                        edges_count = len(call_graph_result.get('edges', []))
                        print(f"[app.py]   ✓ [补充] 演示分区调用图生成成功: 节点={nodes_count}, 边={edges_count}", flush=True)
                    except Exception as e:
                        print(f"[app.py]   ⚠️ [补充] 演示分区调用图生成失败: {e}", flush=True)
                        import traceback
                        _safe_traceback_print()
                    
                    # 2. 补充生成超图
                    try:
                        print(f"[app.py]   [补充] 为演示分区生成超图...", flush=True)
                        hypergraph_generator = FunctionCallHypergraphGenerator(call_graph)
                        hypergraph = hypergraph_generator.generate_partition_hypergraph(demo_partition)
                        hypergraph_dict = hypergraph.to_dict()
                        partition_analyses[demo_partition_id]['hypergraph'] = hypergraph_dict
                        hypergraph_viz = hypergraph.to_visualization_data()
                        partition_analyses[demo_partition_id]['hypergraph_viz'] = hypergraph_viz
                        method_nodes = len([n for n in hypergraph.nodes.values() if n.get('type') == 'method'])
                        function_nodes = len([n for n in hypergraph.nodes.values() if n.get('type') == 'function'])
                        total_nodes = len(hypergraph.nodes)
                        total_edges = len(hypergraph_viz.get('edges', []))
                        print(f"[app.py]   ✓ [补充] 演示分区超图生成成功: 节点={total_nodes} (方法={method_nodes}, 功能={function_nodes}), 边={total_edges}", flush=True)
                    except Exception as e:
                        print(f"[app.py]   ⚠️ [补充] 演示分区超图生成失败: {e}", flush=True)
                        import traceback
                        _safe_traceback_print()
                    
                    # 3. 补充识别入口点
                    try:
                        print(f"[app.py]   [补充] 为演示分区识别入口点...", flush=True)
                        entry_point_generator = EntryPointIdentifierGenerator(call_graph, analyzer.report, None)
                        # 只对演示分区进行入口点识别
                        entry_points_map = entry_point_generator.identify_all_partitions_entry_points([demo_partition], score_threshold=0.3)
                        if demo_partition_id in entry_points_map:
                            entry_points = entry_points_map[demo_partition_id]
                            partition_analyses[demo_partition_id]['entry_points'] = [
                                {
                                    'method_signature': ep.method_sig,
                                    'score': ep.score,
                                    'reasons': ep.reasons
                                }
                                for ep in entry_points
                            ]
                            print(f"[app.py]   ✓ [补充] 演示分区入口点识别成功: {len(entry_points)} 个入口点", flush=True)
                        else:
                            print(f"[app.py]   ⚠️ [补充] 演示分区入口点识别失败: 未在entry_points_map中找到", flush=True)
                    except Exception as e:
                        print(f"[app.py]   ⚠️ [补充] 演示分区入口点识别失败: {e}", flush=True)
                        import traceback
                        _safe_traceback_print()
                    
                    print(f"[app.py] ✅ 演示分区补充生成完成", flush=True)
                    print(f"[app.py] {'='*60}\n", flush=True)
                else:
                    print(f"[app.py]   ⚠️ 未找到演示分区对象，无法补充生成", flush=True)
                    print(f"[app.py] {'='*60}\n", flush=True)
                
                print(f"[app.py] ✅ 演示分区检查完成（已在步骤2.7创建）", flush=True)
                _safe_flush()
            else:
                print(f"[app.py]   ℹ️ 常规分区沿用当前已有路径，跳过额外的有效路径预扫描", flush=True)
        
        # ===== 步骤6.5.4.5：为各分区补充生成符合要求的路径（长度≥3） =====
        print(f"\n[app.py] {'='*60}", flush=True)
        print(f"[app.py] 🔧 为各分区补充生成符合要求的路径（长度≥3）", flush=True)
        print(f"[app.py] {'='*60}\n", flush=True)
        
        import random
        
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            partition_name = partition.get("name", "unknown")
            partition_methods = set(partition.get("methods", []))
            
            if not ENABLE_PATH_SUPPLEMENT_GENERATION:
                continue

            # 获取FQMN信息映射
            fqns_list = partition_analyses.get(partition_id, {}).get('fqns', [])
            if not fqns_list:
                continue
            
            valid_methods = []
            
            for fqn_info in fqns_list:
                method_sig = fqn_info.get('method_signature')
                if method_sig:
                    if method_sig in partition_methods:
                        valid_methods.append(method_sig)
            
            if len(valid_methods) < 3:
                print(f"[app.py]   分区 {partition_id}: 符合要求的方法数不足（需要≥3，实际{len(valid_methods)}），跳过", flush=True)
                continue
            
            # 获取或初始化该分区的paths_map
            if partition_id not in partition_paths_map:
                partition_paths_map[partition_id] = {}
            
            paths_map = partition_paths_map[partition_id]
            seen_path_tuples = {
                tuple(existing_path)
                for existing_paths in paths_map.values()
                for existing_path in existing_paths
            }
            
            # 生成10条路径（长度3-4）
            generated_paths = []
            max_attempts = 100  # 最多尝试100次
            attempts = 0
            
            while len(generated_paths) < 10 and attempts < max_attempts:
                attempts += 1
                
                # 随机选择路径长度（3或4）
                path_length = random.choice([3, 4])
                
                # 随机选择方法组成路径（不重复）
                if len(valid_methods) < path_length:
                    continue
                
                path = random.sample(valid_methods, path_length)
                
                # 去重：检查是否已存在相同路径
                path_tuple = tuple(path)
                if path_tuple not in seen_path_tuples:
                    generated_paths.append(path)
                    seen_path_tuples.add(path_tuple)
            
            # 将生成的路径添加到paths_map中
            if generated_paths:
                # 使用路径的第一个节点作为leaf_node
                for path in generated_paths:
                    leaf_node = path[0]
                    if leaf_node not in paths_map:
                        paths_map[leaf_node] = []
                    paths_map[leaf_node].append(path)
                
                print(f"[app.py]   ✅ 分区 {partition_id} ({partition_name}): 已生成 {len(generated_paths)} 条路径", flush=True)
                print(f"[app.py]      符合要求的方法数: {len(valid_methods)}", flush=True)
            else:
                print(f"[app.py]   ⚠️ 分区 {partition_id}: 未能生成足够路径（尝试{attempts}次）", flush=True)
        
        print(f"[app.py] ✅ 路径补充生成完成\n", flush=True)
        timing.end_phase('path_supplement_generation')
        _safe_flush()
        
        # ===== 步骤6.5.5：分析所有分区的符合要求的路径数量 =====
        # [已注释] 注释掉FNQ检查和分区功能路径检查的详细日志，便于查找入口点/调用图/超图不存在的日志
        # print(f"\n[app.py] {'='*60}", flush=True)
        # print(f"[app.py] 📊 分析所有分区的符合要求的路径数量", flush=True)
        # print(f"[app.py]   要求: 四段内部、长度≥3的路径", flush=True)
        # print(f"[app.py] {'='*60}\n", flush=True)
        
        partition_path_stats = []  # 存储每个分区的路径统计信息
        stats_started_at = time.perf_counter()
        stats_worker_count = _get_parallel_worker_count(len(partitions), limit=4)
        print(f"[workset5] parallel_stage=partition_path_stats workers={stats_worker_count} partitions={len(partitions)}", flush=True)
        stats_results_by_partition = {}
        stats_failures = 0

        with ThreadPoolExecutor(max_workers=stats_worker_count, thread_name_prefix='fh-path-stats') as executor:
            future_to_partition = {
                executor.submit(
                    _compute_partition_path_stat_item,
                    partition,
                    partition_analyses,
                    partition_paths_map,
                    FILTER_SINGLE_NODE_PATHS,
                ): partition for partition in partitions
            }
            for future in as_completed(future_to_partition):
                partition = future_to_partition[future]
                partition_id = partition.get('partition_id', 'unknown')
                try:
                    stats_results_by_partition[partition_id] = future.result()
                except Exception as stats_error:
                    stats_failures += 1
                    stats_results_by_partition[partition_id] = {
                        'partition_id': partition_id,
                        'partition_name': partition.get('name', 'unknown'),
                        'valid_path_count': 0,
                        'total_path_count': 0,
                        'reason': f'parallel_stats_failed:{stats_error}',
                    }

        for partition in partitions:
            partition_id = partition.get('partition_id', 'unknown')
            partition_path_stats.append(
                stats_results_by_partition.get(
                    partition_id,
                    {
                        'partition_id': partition_id,
                        'partition_name': partition.get('name', 'unknown'),
                        'valid_path_count': 0,
                        'total_path_count': 0,
                        'reason': 'parallel_stats_missing',
                    },
                )
            )

        print(f"[workset5] parallel_stage=partition_path_stats completed successes={len(partition_path_stats)-stats_failures} failures={stats_failures} elapsed_seconds={round(time.perf_counter()-stats_started_at, 6)}", flush=True)
            
            # print(f"[app.py]   分区 {partition_id} ({partition_name}):", flush=True)
            # print(f"[app.py]      - 总路径数: {total_path_count}", flush=True)
            # print(f"[app.py]      - 符合要求的路径数: {valid_path_count}", flush=True)
            # if total_path_count > 0:
            #     print(f"[app.py]      - 过滤统计: 长度<3({filtered_by_length}), 段数异常({filtered_by_fqmn_segment}), 四段外部({filtered_by_fqmn_external}), 非内部({filtered_by_fqmn_not_internal}), 无FQMN({filtered_by_no_fqmn})", flush=True)
            # print(f"[app.py]      {'✅' if 10 <= valid_path_count <= 20 else '⚠️' if valid_path_count > 0 else '❌'}", flush=True)
        
        # 按符合要求的路径数量排序
        partition_path_stats.sort(key=lambda x: x['valid_path_count'], reverse=True)
        
        # print(f"\n[app.py] {'='*60}", flush=True)
        # print(f"[app.py] 📊 分区路径统计汇总（按符合要求的路径数排序）", flush=True)
        # print(f"[app.py] {'='*60}", flush=True)
        # for stat in partition_path_stats:
        #     status = "✅ 符合要求(10-20条)" if 10 <= stat['valid_path_count'] <= 20 else "⚠️ 路径数不在范围内" if stat['valid_path_count'] > 0 else "❌ 无符合要求的路径"
        #     print(f"[app.py]   {stat['partition_id']} ({stat['partition_name']}): {stat['valid_path_count']} 条符合要求的路径 - {status}", flush=True)
        
        # 查找符合要求的分区（10-20条路径）
        suitable_partitions = [stat for stat in partition_path_stats if 10 <= stat['valid_path_count'] <= 20]
        
        # print(f"\n[app.py] {'='*60}", flush=True)
        # if suitable_partitions:
        #     print(f"[app.py] ✅ 找到 {len(suitable_partitions)} 个符合要求的分区（10-20条路径）", flush=True)
        #     for stat in suitable_partitions:
        #         print(f"[app.py]   - {stat['partition_id']} ({stat['partition_name']}): {stat['valid_path_count']} 条", flush=True)
        # else:
        #     print(f"[app.py] ⚠️ 没有找到符合要求的分区（10-20条路径）", flush=True)
        #     print(f"[app.py]   所有分区的符合要求的路径数:", flush=True)
        #     for stat in partition_path_stats:
        #         print(f"[app.py]     - {stat['partition_id']} ({stat['partition_name']}): {stat['valid_path_count']} 条", flush=True)
        #     print(f"[app.py]   建议: 需要创建一个演示用的功能分区，包含20条符合要求的功能路径", flush=True)
        # print(f"[app.py] {'='*60}\n", flush=True)
        
        _run_partition_llm_semantics_pass(
            timing=timing,
            phase_id='partition_llm_semantics_pass_2',
            update_status_text='步骤6.5.6/7: 对所有分区进行LLM语义分析...',
            pass_title='步骤6.5.6: 对所有分区进行LLM语义分析',
            use_limit=USE_LLM_PARTITIONS_LIMIT,
            enable_partition_llm_semantics=ENABLE_PARTITION_LLM_SEMANTICS and ENABLE_ADVANCED_VISIBLE_LAYER,
            llm_agent_for_partition=llm_agent_for_partition,
            partitions=partitions,
            analyzer_report=analyzer.report,
            project_path=project_path,
            layer_states=layer_states,
            degradation_summary=degradation_summary,
            skipped_or_deferred_work=skipped_or_deferred_work,
            timeout_degrade_stage='partition_llm_semantics_pass_2',
            timeout_reason_code='partition_llm_timeout',
            timeout_user_message_template='分区 {partition_id} 的 LLM 语义分析超时，已跳过并保留基础结果',
            timeout_deferred_section='partition_llm_semantics',
            disabled_message='[app.py]   ℹ️ Workset1: 第二轮分区级LLM语义分析已关闭或不可用',
        )

        partitions = deduplicate_and_resolve_name_conflicts(partitions)
        
        # ===== 步骤6.6：为每个路径生成CFG、DFG和数据流图 =====
        update_analysis_status(progress=85, status='步骤6.6/7: 生成路径级别的CFG/DFG/数据流图...')
        # [已注释] 注释掉路径级别分析的详细日志
        # print(f"[app.py] 步骤6.6: 为每个路径生成CFG、DFG和数据流图...", flush=True)
        _safe_flush()
        
        # 获取LLM agent（如果可用且启用）
        llm_agent = None
        if ENABLE_PATH_LLM_ANALYSIS:
            try:
                llm_agent = _create_code_understanding_agent()
                if llm_agent:
                    llm_agent.project_path = project_path
                    # print(f"[app.py] ✓ LLM agent已初始化，将用于路径分析", flush=True)
                else:
                    # print(f"[app.py] ⚠️ DEEPSEEK_API_KEY未设置，跳过LLM分析", flush=True)
                    pass
            except Exception as e:
                print(f"[app.py] ⚠️ LLM agent初始化失败: {e}，将使用简单生成方式", flush=True)
        # else:
        #     print(f"[app.py] ℹ️  LLM分析已关闭（ENABLE_PATH_LLM_ANALYSIS=False），跳过路径名称/描述和输入输出图的LLM生成", flush=True)
        
        # 选择合适的分区进行路径级别分析
        selected_partition = None
        selected_partition_stat = None
        
        # ===== 步骤6.6：对受控分区进行路径级别分析 =====
        ranked_partition_ids = _rank_partitions_for_path_analysis(partition_path_stats, PATH_ANALYSIS_PARTITION_LIMIT)
        partitions_to_analyze = [partition for partition in partitions if partition.get('partition_id') in ranked_partition_ids] if partitions else []
        
        print(f"\n[app.py] {'='*60}", flush=True)
        print(f"[app.py] 📊 批量路径级别分析启动", flush=True)
        print(f"[app.py]   计划分析分区数: {len(partitions_to_analyze)} (配置限制: {PATH_ANALYSIS_PARTITION_LIMIT})", flush=True)
        if not partitions_to_analyze:
             print(f"[app.py]   ⚠️ 没有功能分区，跳过路径级别分析", flush=True)
        print(f"[app.py] {'='*60}\n", flush=True)

        for p_idx, selected_partition in enumerate(partitions_to_analyze):
            # 获取对应的统计信息
            selected_partition_stat = next((s for s in partition_path_stats if s['partition_id'] == selected_partition.get('partition_id')), None)
            
            # 开始处理当前分区
            partition_id = selected_partition.get("partition_id", "unknown")
            partition_methods = set(selected_partition.get("methods", []))
            
            print(f"\n[app.py] {'='*60}", flush=True)
            print(f"[app.py] 📊 路径级别分析配置", flush=True)
            print(f"[app.py]   总功能分区数: {len(partitions)}", flush=True)
            print(f"[app.py]   🎯 选择的分区: {partition_id}", flush=True)
            print(f"[app.py]   分区名称: {selected_partition.get('name', 'unknown')}", flush=True)
            print(f"[app.py]   方法数量: {len(partition_methods)}", flush=True)
            if selected_partition_stat:
                print(f"[app.py]   符合要求的路径数: {selected_partition_stat['valid_path_count']} 条", flush=True)
                if not (10 <= selected_partition_stat['valid_path_count'] <= 20):
                    print(f"[app.py]   ⚠️  警告: 该分区的路径数不在10-20条范围内", flush=True)
            print(f"[app.py] {'='*60}\n", flush=True)
            
            if partition_id not in partition_analyses:
                print(f"[app.py]   ⚠️ 分区 {partition_id} 不在partition_analyses中，跳过路径级别分析", flush=True)
            else:
                    # 从保存的paths_map中获取路径信息
                    paths_map = partition_paths_map.get(partition_id, {})
                    
                    if not paths_map:
                        print(f"[app.py]   ⚠️ 分区 {partition_id} 没有路径信息，跳过路径级别分析", flush=True)
                    else:
                        # 使用配置的路径数量限制（默认2条）
                        # MAX_PATHS_TO_ANALYZE已在函数开头配置，这里直接使用
                        
                        # 获取FQMN信息映射（用于过滤路径）
                        partition_analysis = partition_analyses[partition_id]
                        fqmn_info_map = partition_analysis.get('fqmn_info_map') or _build_fqmn_info_map(partition_analysis.get('fqns', []))
                        
                        timing.start_phase('path_filtering_total', layer='expand_visible', blocking=True)

                        # 将paths_map展平为路径列表，并应用FQMN过滤
                        all_paths_list = []
                        filtered_by_length = 0
                        filtered_by_fqmn_segment = 0
                        filtered_by_fqmn_external = 0
                        filtered_by_fqmn_not_internal = 0
                        filtered_by_no_fqmn = 0
                        
                        for leaf_node, paths in paths_map.items():
                            for path_index, path in enumerate(paths):
                                evaluation = _evaluate_path_candidate(path, fqmn_info_map, filter_single_node=FILTER_SINGLE_NODE_PATHS)
                                if not evaluation['is_valid']:
                                    filtered_by_length += int('single_node_path' in evaluation['invalid_reasons'])
                                    filtered_by_no_fqmn += evaluation['missing_fqmn_count']
                                    filtered_by_fqmn_segment += evaluation['segment_anomaly_count']
                                    filtered_by_fqmn_external += evaluation['external_count']
                                    if 'no_internal_segment4_method' in evaluation['invalid_reasons']:
                                        filtered_by_fqmn_not_internal += 1
                                    continue

                                all_paths_list.append({
                                    'leaf_node': leaf_node,
                                    'path_index': path_index,
                                    'path': path,
                                    'worthiness_score': evaluation['score'],
                                    'worthiness_reasons': [
                                        f"internal_segment4={evaluation['internal_segment4_count']}",
                                        f"fqmn_known={evaluation['fqmn_known_count']}",
                                        f"path_length={len(path)}",
                                    ],
                                    'internal_segment4_count': evaluation['internal_segment4_count'],
                                })
                        
                        selected_paths, deferred_paths = _select_representative_paths(all_paths_list, MAX_PATHS_TO_ANALYZE)
                        original_total = len(all_paths_list)
                        total_paths = len(selected_paths)
                        
                        # 显示过滤统计信息
                        print(f"\n[app.py] {'='*60}", flush=True)
                        print(f"[app.py] 🛤️  路径过滤统计", flush=True)
                        total_before_filter = sum(len(paths) for paths in paths_map.values())
                        print(f"[app.py]   原始路径数（展平前）: {total_before_filter} 条", flush=True)
                        print(f"[app.py]   过滤统计:", flush=True)
                        print(f"[app.py]     - 因路径长度<3被过滤: {filtered_by_length} 条", flush=True)
                        print(f"[app.py]     - 因FQMN段数异常被过滤: {filtered_by_fqmn_segment} 条", flush=True)
                        print(f"[app.py]     - 因FQMN四段外部被过滤: {filtered_by_fqmn_external} 条", flush=True)
                        print(f"[app.py]     - 因FQMN非内部被过滤: {filtered_by_fqmn_not_internal} 条", flush=True)
                        print(f"[app.py]     - 因无FQMN信息被过滤: {filtered_by_no_fqmn} 条", flush=True)
                        print(f"[app.py]   符合要求的路径数（四段内部，长度≥3）: {original_total} 条", flush=True)
                        print(f"[app.py]   ⚡ 只分析最值得的前 {MAX_PATHS_TO_ANALYZE} 条路径", flush=True)
                        print(f"[app.py]   实际分析路径数: {total_paths} 条", flush=True)
                        print(f"[app.py] {'='*60}\n", flush=True)
                        timing.end_phase('path_filtering_total')
                        
                        # 获取输入输出信息
                        inputs = partition_analysis.get('inputs', [])
                        outputs = partition_analysis.get('outputs', [])
                        inputs_by_method = partition_analysis.get('inputs_by_method') or {}
                        outputs_by_method = partition_analysis.get('outputs_by_method') or {}
                        
                        print(f"\n[app.py] {'='*60}", flush=True)
                        print(f"[app.py] 🛤️  开始路径级别分析", flush=True)
                        print(f"[app.py]   分区ID: {partition_id}", flush=True)
                        print(f"[app.py]   待分析路径数: {total_paths}", flush=True)
                        print(f"[app.py]   LLM分析: {'启用' if ENABLE_PATH_LLM_ANALYSIS else '已关闭'}", flush=True)
                        print(f"[app.py] {'='*60}\n", flush=True)
                        
                        # 为每个路径生成分析
                        path_analyses = []
                        current_path_index = 0

                        # Phase 1 / Task 1.1: 路径语义画像（启发式，不影响原有流程）
                        from analysis.method_function_profile_builder import MethodFunctionProfileBuilder
                        from analysis.path_semantic_analyzer import analyze_path_semantics

                        profile_builder = MethodFunctionProfileBuilder(project_path, analyzer.report)
                        
                        partition_analysis_started_at = time.perf_counter()
                        timed_out = False
                        timeout_deferred_paths = []
                        print(
                            f"[workset5] parallel_stage=path_llm_tasks workers={path_llm_worker_count} "
                            f"tasks_per_path={path_llm_task_count} mode={'parallel' if path_llm_parallel_enabled else 'serial'}",
                            flush=True,
                        )

                        # 遍历限制后的路径列表
                        for path_info in selected_paths:
                            leaf_node = path_info['leaf_node']
                            path_index = path_info['path_index']
                            path = path_info['path']
                            current_path_index += 1

                            if (time.perf_counter() - partition_analysis_started_at) > PATH_ANALYSIS_TIMEOUT_SECONDS:
                                timed_out = True
                                timeout_deferred_paths.append(_summarize_path_candidate(path_info, status='available_on_demand', reason='timeout_guard'))
                                _record_layer_degradation(
                                    layer_states,
                                    degradation_summary,
                                    skipped_or_deferred_work,
                                    layer='advanced_visible',
                                    stage='path_cfg_dfg_io_total',
                                    reason_code='path_deep_analysis_timeout',
                                    status_after_degrade='available_on_demand',
                                    timeout_seconds=PATH_ANALYSIS_TIMEOUT_SECONDS,
                                    user_message=f'分区 {partition_id} 的路径级深分析已超时，剩余路径改为后续按需补跑',
                                    retry_mode='on_demand',
                                    deferred_section='path_analysis',
                                )
                                continue
                            
                            # 显示进度条（每5条路径或重要节点时显示详细信息）
                            path_display = ' -> '.join([p.split('.')[-1] if '.' in p else p for p in path[:3]])
                            if len(path) > 3:
                                path_display += ' -> ...'
                            
                            # [已注释] 注释掉详细的进度日志
                            # 每5条路径或关键节点显示详细信息，其他时候显示简洁进度条
                            # if current_path_index % 5 == 0 or current_path_index == 1 or current_path_index == total_paths:
                            #     # 详细显示（新行）
                            #     if total_paths == 0:
                            #         percent = 100.0
                            #         filled = 30
                            #     else:
                            #         percent = 100.0 * (current_path_index / float(total_paths))
                            #         filled = int(30 * current_path_index // total_paths)
                            #     bar = '█' * filled + '░' * (30 - filled)
                            #     print(f"[app.py]   路径分析进度 |{bar}| {current_path_index}/{total_paths} ({percent:.1f}%) 当前: {path_display}", flush=True)
                            # else:
                            #     # 简洁显示（同一行更新）
                            #     if total_paths == 0:
                            #         percent = 100.0
                            #         filled = 20
                            #     else:
                            #         percent = 100.0 * (current_path_index / float(total_paths))
                            #         filled = int(20 * current_path_index // total_paths)
                            #     bar = '█' * filled + '░' * (20 - filled)
                            #     print(f'\r[app.py]   进度 |{bar}| {current_path_index}/{total_paths} ({percent:.1f}%)', end='', flush=True)
                            #     if current_path_index >= total_paths:
                            #         print()  # 完成时换行
                            
                            timing.start_phase('path_cfg_dfg_io_total', layer='advanced_visible', blocking=True)
                            try:
                                # 生成路径级别的CFG
                                # if current_path_index == 1:
                                #     print(f"\n[app.py]      → 生成CFG...", flush=True)
                                path_cfg = None
                                path_dfg = None
                                path_dataflow_mermaid = None
                                if ENABLE_PATH_CFG_DFG_IO:
                                    path_cfg = generate_path_level_cfg(
                                        path=path,
                                        call_graph=call_graph,
                                        analyzer_report=analyzer.report,
                                        partition_methods=partition_methods,
                                        inputs=inputs,
                                        outputs=outputs
                                    )
                                
                                # 生成路径级别的DFG
                                # if current_path_index == 1:
                                #     print(f"[app.py]      → 生成DFG...", flush=True)
                                    path_dfg = generate_path_level_dfg(
                                        path=path,
                                        call_graph=call_graph,
                                        analyzer_report=analyzer.report,
                                        partition_methods=partition_methods,
                                        dataflow_analyzer=analyzer.data_flow_analyzer if hasattr(analyzer, 'data_flow_analyzer') else None
                                    )

                                # ===== 路径LLM任务（可控并行，保持结果结构不变） =====
                                cfg_dfg_explain_md = None
                                path_dataflow_mermaid = None
                                path_name = f"路径 {path_index + 1}"
                                path_description = f"包含 {len(path)} 个方法的调用链"
                                path_io_graph = None
                                path_call_chain_analysis = None

                                use_thread_local_agent = path_llm_parallel_enabled
                                llm_task_results: Dict[str, Dict[str, Any]] = {}
                                cfg_dfg_llm_enabled_for_path = (
                                    ENABLE_CFG_DFG_LLM_EXPLAIN
                                    and llm_agent
                                    and current_path_index <= cfg_dfg_llm_explain_max_paths
                                )

                                def _collect_path_llm_result(task_name: str, task_result: Dict[str, Any]) -> None:
                                    llm_task_results[task_name] = task_result

                                if path_llm_parallel_enabled and path_llm_executor is not None:
                                        future_to_task = {}

                                        if cfg_dfg_llm_enabled_for_path:
                                            future_to_task[
                                                path_llm_executor.submit(
                                                    _run_path_cfg_dfg_explain_task,
                                                    path=path,
                                                    path_cfg=path_cfg,
                                                    path_dfg=path_dfg,
                                                    analyzer_report=analyzer.report,
                                                    inputs=inputs,
                                                    outputs=outputs,
                                                    llm_agent=llm_agent,
                                                    use_thread_local_agent=use_thread_local_agent,
                                                )
                                            ] = 'cfg_dfg_explain'

                                        if ENABLE_PATH_CFG_DFG_IO:
                                            future_to_task[
                                                path_llm_executor.submit(
                                                    _run_path_dataflow_mermaid_task,
                                                    path=path,
                                                    call_graph=call_graph,
                                                    analyzer_report=analyzer.report,
                                                    partition_methods=partition_methods,
                                                    inputs=inputs,
                                                    outputs=outputs,
                                                    llm_agent=llm_agent,
                                                    path_dfg=path_dfg,
                                                    use_thread_local_agent=use_thread_local_agent,
                                                )
                                            ] = 'dataflow_mermaid'

                                        if ENABLE_PATH_LLM_ANALYSIS and llm_agent:
                                            future_to_task[
                                                path_llm_executor.submit(
                                                    _run_path_name_description_task,
                                                    path=path,
                                                    analyzer_report=analyzer.report,
                                                    project_path=project_path,
                                                    llm_agent=llm_agent,
                                                    use_thread_local_agent=use_thread_local_agent,
                                                )
                                            ] = 'path_name_desc'
                                            future_to_task[
                                                path_llm_executor.submit(
                                                    _run_path_io_chain_task,
                                                    path=path,
                                                    analyzer_report=analyzer.report,
                                                    inputs=inputs,
                                                    outputs=outputs,
                                                    call_graph=call_graph,
                                                    llm_agent=llm_agent,
                                                    use_thread_local_agent=use_thread_local_agent,
                                                )
                                            ] = 'path_io_chain'

                                        for future in as_completed(future_to_task):
                                            task_name = future_to_task[future]
                                            try:
                                                _collect_path_llm_result(task_name, future.result())
                                            except Exception as error:
                                                _collect_path_llm_result(task_name, {'ok': False, 'error': str(error)})
                                else:
                                    if cfg_dfg_llm_enabled_for_path:
                                        _collect_path_llm_result(
                                            'cfg_dfg_explain',
                                            _run_path_cfg_dfg_explain_task(
                                                path=path,
                                                path_cfg=path_cfg,
                                                path_dfg=path_dfg,
                                                analyzer_report=analyzer.report,
                                                inputs=inputs,
                                                outputs=outputs,
                                                llm_agent=llm_agent,
                                                use_thread_local_agent=False,
                                            ),
                                        )
                                    if ENABLE_PATH_CFG_DFG_IO:
                                        _collect_path_llm_result(
                                            'dataflow_mermaid',
                                            _run_path_dataflow_mermaid_task(
                                                path=path,
                                                call_graph=call_graph,
                                                analyzer_report=analyzer.report,
                                                partition_methods=partition_methods,
                                                inputs=inputs,
                                                outputs=outputs,
                                                llm_agent=llm_agent,
                                                path_dfg=path_dfg,
                                                use_thread_local_agent=False,
                                            ),
                                        )
                                    if ENABLE_PATH_LLM_ANALYSIS and llm_agent:
                                        _collect_path_llm_result(
                                            'path_name_desc',
                                            _run_path_name_description_task(
                                                path=path,
                                                analyzer_report=analyzer.report,
                                                project_path=project_path,
                                                llm_agent=llm_agent,
                                                use_thread_local_agent=False,
                                            ),
                                        )
                                        _collect_path_llm_result(
                                            'path_io_chain',
                                            _run_path_io_chain_task(
                                                path=path,
                                                analyzer_report=analyzer.report,
                                                inputs=inputs,
                                                outputs=outputs,
                                                call_graph=call_graph,
                                                llm_agent=llm_agent,
                                                use_thread_local_agent=False,
                                            ),
                                        )

                                cfg_result = llm_task_results.get('cfg_dfg_explain')
                                if cfg_result:
                                    if cfg_result.get('ok'):
                                        cfg_dfg_explain_md = cfg_result.get('markdown')
                                    else:
                                        log_print(f"[app.py]      ⚠️ LLM解释CFG/DFG失败: {cfg_result.get('error')}")

                                dataflow_result = llm_task_results.get('dataflow_mermaid')
                                if dataflow_result:
                                    if dataflow_result.get('ok'):
                                        path_dataflow_mermaid = dataflow_result.get('dataflow_mermaid')
                                    else:
                                        log_print(f"[app.py]      ⚠️ 生成数据流图(mermaid)失败: {dataflow_result.get('error')}")

                                name_desc_result = llm_task_results.get('path_name_desc')
                                if name_desc_result:
                                    if name_desc_result.get('ok') and isinstance(name_desc_result.get('path_info'), dict):
                                        path_info = name_desc_result['path_info']
                                        path_name = path_info.get('name', path_name)
                                        path_description = path_info.get('description', path_description)
                                    else:
                                        print(f"[app.py]      ⚠️ LLM生成路径名称和描述失败: {name_desc_result.get('error')}，使用默认名称", flush=True)

                                io_chain_result = llm_task_results.get('path_io_chain')
                                if io_chain_result:
                                    if io_chain_result.get('ok'):
                                        path_io_graph = io_chain_result.get('io_graph')
                                        path_call_chain_analysis = io_chain_result.get('call_chain_analysis')
                                    else:
                                        log_print(f"[app.py]      ⚠️ LLM生成输入输出图异常: {io_chain_result.get('error')}")
                                        path_io_graph = None
                                        path_call_chain_analysis = None
                                
                                # 如果LLM未启用或生成失败，使用启发式规则生成
                                if not path_io_graph:
                                    try:
                                        # 构建方法IO列表（用于启发式规则）
                                        method_io_list = []
                                        for method_sig in path:
                                            method_inputs = []
                                            method_outputs = []
                                            
                                            # 从inputs和outputs中查找该方法的输入输出
                                            for inp in inputs_by_method.get(method_sig, []):
                                                method_inputs.append({
                                                    'name': inp.get('parameter_name', 'unknown'),
                                                    'type': inp.get('parameter_type', 'unknown')
                                                })

                                            for out in outputs_by_method.get(method_sig, []):
                                                method_outputs.append({
                                                    'type': out.get('return_type', 'unknown')
                                                })
                                            
                                            # 如果找不到，尝试从analyzer.report中提取
                                            if not method_inputs or not method_outputs:
                                                method_info = None
                                                if '.' in method_sig:
                                                    class_name, method_name = method_sig.rsplit('.', 1)
                                                    if analyzer.report and class_name in analyzer.report.classes:
                                                        class_info = analyzer.report.classes[class_name]
                                                        if method_name in class_info.methods:
                                                            method_info = class_info.methods[method_name]
                                                else:
                                                    if analyzer.report:
                                                        for func_info in analyzer.report.functions:
                                                            if func_info.name == method_sig:
                                                                method_info = func_info
                                                                break
                                                
                                                if method_info and not method_inputs:
                                                    if hasattr(method_info, 'parameters') and method_info.parameters:
                                                        for param in method_info.parameters:
                                                            method_inputs.append({
                                                                'name': getattr(param, 'name', 'unknown'),
                                                                'type': getattr(param, 'param_type', None) or getattr(param, 'type', None) or 'unknown'
                                                            })
                                                
                                                if method_info and not method_outputs:
                                                    if hasattr(method_info, 'return_type'):
                                                        return_type = method_info.return_type if isinstance(method_info.return_type, str) else (str(method_info.return_type) if method_info.return_type else 'unknown')
                                                        if return_type and return_type.lower() not in ['none', 'void', '']:
                                                            method_outputs.append({'type': return_type})
                                            
                                            # 如果仍然没有输入输出，使用默认值
                                            if not method_inputs:
                                                method_inputs.append({'name': 'data', 'type': 'Any'})
                                            if not method_outputs:
                                                method_outputs.append({'type': 'Any'})
                                            
                                            method_io_list.append({
                                                'method_sig': method_sig,
                                                'method_name': method_sig.split('.')[-1] if '.' in method_sig else method_sig,
                                                'inputs': method_inputs,
                                                'outputs': method_outputs
                                            })
                                        
                                        # 使用启发式规则构建io_graph
                                        path_io_graph = _build_io_graph_heuristic(method_io_list)
                                        log_print(f"[app.py]      ✓ 使用启发式规则生成输入输出图: nodes={len(path_io_graph.get('nodes', []))}, edges={len(path_io_graph.get('edges', []))}")
                                    except Exception as e:
                                        log_print(f"[app.py]      ⚠️ 启发式规则生成输入输出图失败: {e}")
                                        import traceback
                                        _safe_traceback_print()
                                        path_io_graph = None
                                
                                # 生成超图高亮配置
                                try:
                                    highlight_config_result = analyze_path_call_chain_for_highlight(
                                        path=path,
                                        call_graph=call_graph,
                                        call_chain_analysis=path_call_chain_analysis
                                    )
                                    log_print(f"[app.py]      ✓ 生成超图高亮配置: 类型={highlight_config_result.get('call_chain_type')}, 总方法={highlight_config_result.get('main_method')}, 中间方法数={len(highlight_config_result.get('intermediate_methods', []))}")
                                except Exception as e:
                                    log_print(f"[app.py]      ⚠️ 生成超图高亮配置失败: {e}")
                                    import traceback
                                    _safe_traceback_print()
                                    highlight_config_result = None
                                
                                # 保存路径分析结果
                                path_analysis_item = {
                                    'path_id': f"{partition_id}_{path_index}",
                                    'leaf_node': leaf_node,
                                    'function_chain': path,  # RAG 训练器更喜欢这个字段名
                                    'path_index': path_index,
                                    'path': path,
                                    'worthiness_score': path_info.get('worthiness_score', 0.0),
                                    'worthiness_reasons': path_info.get('worthiness_reasons', []),
                                    'deep_analysis_status': 'ready',
                                    'path_name': path_name,  # LLM生成的路径名称
                                    'path_description': path_description,  # LLM生成的路径描述
                                    'semantics': {
                                        'semantic_label': path_name,
                                        'description': path_description,
                                        'functional_domain': selected_partition.get('name', 'general')
                                    },
                                    'cfg': path_cfg,
                                    'dfg': path_dfg,
                                    'input_info': (path_cfg or {}).get('input_info', {}),   # 提升存储层级
                                    'output_info': (path_cfg or {}).get('output_info', {}), # 提升存储层级
                                    'cfg_dfg_explain_md': cfg_dfg_explain_md,  # LLM对CFG/DFG的解释（Markdown）
                                    'dataflow_mermaid': path_dataflow_mermaid,
                                    'io_graph': path_io_graph,  # 输入输出图
                                    'call_chain_analysis': path_call_chain_analysis,  # 调用链类型分析
                                    'highlight_config': highlight_config_result  # 超图高亮配置
                                }

                                # 新增：为路径生成语义画像（补充详细字段）
                                try:
                                    method_profiles = profile_builder.build_profiles_batch(path)
                                    path_semantics = analyze_path_semantics(path, analyzer.report, method_profiles)
                                    if path_semantics:
                                        path_analysis_item['semantics'].update(path_semantics)
                                except Exception as e:
                                    log_print(f"[app.py]      ⚠️ 路径语义画像生成失败: {e}")

                                path_analyses.append(path_analysis_item)
                                timing.mark_ready('deep_analysis_result')
                                
                                # if current_path_index == 1:
                                #     print(f"\n[app.py]      ✓ 第一条路径分析完成！继续处理其他路径...", flush=True)
                                
                                # 每处理5条路径或最后一条路径时更新进度状态（更频繁的更新，避免前端卡住）
                                if current_path_index % 5 == 0 or current_path_index == total_paths:
                                    progress_pct = 85 + int((current_path_index / total_paths) * 5)  # 85-90%之间
                                    progress_pct = min(progress_pct, 90)
                                    percent_done = current_path_index * 100 // total_paths if total_paths > 0 else 0
                                    update_analysis_status(
                                        progress=progress_pct,
                                        status=f'步骤6.6/7: 路径分析进度 {current_path_index}/{total_paths} ({percent_done}%)...'
                                    )
                                    # print(f"\n[app.py]   [状态更新] 进度: {progress_pct}% | 路径: {current_path_index}/{total_paths} ({percent_done}%)", flush=True)
                                
                            except Exception as e:
                                print(f"\n[app.py]   ⚠️ 路径分析失败 (leaf={leaf_node}, path={path_index}): {e}", flush=True)
                                import traceback
                                _safe_traceback_print()
                            finally:
                                timing.end_phase('path_cfg_dfg_io_total')

                        # [已注释] 注释掉详细的日志
                        # 保存路径分析结果（限制后的结果）
                        # print(f"[app.py]   保存path_analyses到partition_analyses[{partition_id}]", flush=True)
                        # print(f"[app.py]     - path_analyses数量: {len(path_analyses)}", flush=True)
                        # 统计io_graph的数量
                        # io_graph_count = sum(1 for pa in path_analyses if pa.get('io_graph'))
                        # none_count = sum(1 for pa in path_analyses if not pa.get('io_graph'))
                        # print(f"[app.py]     - 有io_graph的路径: {io_graph_count} 条", flush=True)
                        # print(f"[app.py]     - io_graph为None的路径: {none_count} 条", flush=True)
                        # if io_graph_count > 0:
                        #     # 显示第一条有io_graph的路径信息
                        #     for pa in path_analyses:
                        #         if pa.get('io_graph'):
                        #             io_graph = pa['io_graph']
                        #             print(f"[app.py]     - 示例路径(leaf={pa['leaf_node']}, path_index={pa['path_index']}): io_graph有nodes={len(io_graph.get('nodes', []))}, edges={len(io_graph.get('edges', []))}", flush=True)
                        #             break
                        partition_analyses[partition_id]['path_analyses'] = path_analyses
                        # 保存过滤后的 paths_map（用于前端显示和超图路径着色）
                        # 修复：当开启单节点过滤且分区只剩单节点路径时，不再把分区路径直接清空为 0。
                        filtered_paths_map = {}
                        single_node_fallbacks: List[Tuple[str, List[str]]] = []
                        for leaf_node, paths in paths_map.items():
                            normalized_paths = [p for p in (paths or []) if isinstance(p, list) and p]
                            if not normalized_paths:
                                continue

                            valid_paths = [
                                p
                                for p in normalized_paths
                                if (not FILTER_SINGLE_NODE_PATHS or len(p) > 1)
                            ]
                            if valid_paths:
                                filtered_paths_map[leaf_node] = valid_paths
                                continue

                            if FILTER_SINGLE_NODE_PATHS:
                                fallback_path = next((p for p in normalized_paths if len(p) == 1), None)
                                if fallback_path:
                                    single_node_fallbacks.append((str(leaf_node), list(fallback_path)))

                        # 若过滤后为空且确有单节点路径，保留少量兜底路径，避免 UI/经验库出现“0 路径”假象。
                        preserved_single_node_fallback_count = 0
                        if not filtered_paths_map and single_node_fallbacks:
                            fallback_limit = max(1, min(MAX_PATHS_TO_ANALYZE, 4))
                            for leaf_node, fallback_path in single_node_fallbacks[:fallback_limit]:
                                filtered_paths_map.setdefault(leaf_node, []).append(fallback_path)
                                preserved_single_node_fallback_count += 1

                        partition_analyses[partition_id]['paths_map'] = filtered_paths_map
                        # 保存路径限制信息
                        partition_analyses[partition_id]['path_analysis_info'] = {
                            'original_total': original_total,
                            'analyzed_count': total_paths,
                            'max_paths_limit': MAX_PATHS_TO_ANALYZE,
                            'partition_limit': PATH_ANALYSIS_PARTITION_LIMIT,
                            'timeout_seconds': PATH_ANALYSIS_TIMEOUT_SECONDS,
                            'selected_count': len(path_analyses),
                            'deferred_count': len(deferred_paths) + len(timeout_deferred_paths),
                            'timed_out': timed_out,
                            'completion_status': 'partial_timeout' if timed_out else 'complete',
                            'timed_out_stages': ['path_cfg_dfg_io_total'] if timed_out else [],
                            'user_message': '部分路径因超时被延后，可点击或通过 RAG 问题触发后续补跑' if timed_out else None,
                            'selection_policy': 'representative_top_n',
                            'single_node_fallback_enabled': bool(FILTER_SINGLE_NODE_PATHS),
                            'preserved_single_node_fallback_count': preserved_single_node_fallback_count,
                            'representative_path_summaries': [
                                _summarize_path_candidate(item, status='ready', reason='selected_for_analysis')
                                for item in selected_paths[:MAX_PATHS_TO_ANALYZE]
                            ],
                            'deferred_path_summaries': [
                                _summarize_path_candidate(item, status='available_on_demand', reason='not_selected_in_top_n')
                                for item in deferred_paths[:20]
                            ] + timeout_deferred_paths[:20]
                        }
                    
                    # [已注释] 注释掉详细的完成日志
                    # 完成所有路径分析后，打印最终进度条
                    # print()  # 确保换行
                    # print_progress_bar(
                    #     current=total_paths,
                    #     total=total_paths,
                    #     prefix=f"[app.py]   路径分析完成",
                    #     suffix="✅ 100%",
                    #     length=30
                    # )
                    
                    # print(f"\n[app.py] {'='*60}", flush=True)
                    # print(f"[app.py] ✅ 分区 {partition_id} 路径级别分析完成!", flush=True)
                    # print(f"[app.py]   成功分析: {len(path_analyses)} 条路径", flush=True)
                    # print(f"[app.py]   总路径数: {total_paths} 条路径", flush=True)
                    # if total_paths > len(path_analyses):
                    #     print(f"[app.py]   失败路径: {total_paths - len(path_analyses)} 条路径", flush=True)
                    
                    # 检查路径分析结果
                    # paths_with_io_graph = sum(1 for pa in path_analyses if pa.get('io_graph'))
                    # paths_with_cfg = sum(1 for pa in path_analyses if pa.get('cfg'))
                    # paths_with_dfg = sum(1 for pa in path_analyses if pa.get('dfg'))
                    # print(f"[app.py]   路径统计:", flush=True)
                    # print(f"[app.py]     - 有输入输出图的路径: {paths_with_io_graph} 条", flush=True)
                    # print(f"[app.py]     - 有CFG的路径: {paths_with_cfg} 条", flush=True)
                    # print(f"[app.py]     - 有DFG的路径: {paths_with_dfg} 条", flush=True)
                    # print(f"[app.py] {'='*60}\n", flush=True)
                    
                    # 更新最终状态
                    existing_advanced_state = layer_states.get('advanced_visible') or {}
                    advanced_degraded = bool(existing_advanced_state.get('degraded'))
                    advanced_codes = existing_advanced_state.get('degradation_codes', [])
                    advanced_deferred_sections = existing_advanced_state.get('deferred_sections', [])
                    advanced_user_message = existing_advanced_state.get('user_message')
                    layer_states['advanced_visible'] = _build_layer_state(
                        'available_on_demand' if advanced_degraded else 'ready' if ENABLE_ADVANCED_VISIBLE_LAYER else 'available_on_demand',
                        ['path_analysis'],
                        visible=ENABLE_ADVANCED_VISIBLE_LAYER,
                        degraded=advanced_degraded,
                        degradation_codes=advanced_codes,
                        deferred_sections=advanced_deferred_sections,
                        user_message=advanced_user_message,
                    )
                    _publish_partial_result(90, 'Workset3: 高级路径分析结果已补齐', include_expand=True, include_advanced=True)
        
        if path_llm_executor is not None:
            path_llm_executor.shutdown(wait=True)

        # 回填：为未产出 deep path_analyses 的分区补齐结构路径/轻量路径，避免结果层出现“该分区无功能路径”。
        try:
            partition_methods_lookup = {
                str(item.get('partition_id') or ''): list(item.get('methods') or [])
                for item in (partitions or [])
                if isinstance(item, dict) and item.get('partition_id')
            }
            backfilled_partitions = 0
            backfilled_paths = 0
            for partition_id, analysis in (partition_analyses or {}).items():
                if not isinstance(analysis, dict):
                    continue
                existing_path_analyses = analysis.get('path_analyses') or []
                if isinstance(existing_path_analyses, list) and existing_path_analyses:
                    continue

                fallback_paths, fallback_info = _get_partition_path_payload(
                    analysis,
                    partition_methods=partition_methods_lookup.get(str(partition_id), []),
                )
                if fallback_paths:
                    analysis['path_analyses'] = fallback_paths
                    backfilled_partitions += 1
                    backfilled_paths += len(fallback_paths)
                if isinstance(fallback_info, dict) and fallback_info:
                    existing_info = analysis.get('path_analysis_info') or {}
                    merged_info = dict(existing_info)
                    merged_info.update({
                        key: value
                        for key, value in fallback_info.items()
                        if key not in merged_info or merged_info.get(key) in (None, '', 0, [])
                    })
                    analysis['path_analysis_info'] = merged_info

            if backfilled_partitions > 0:
                log_print(f"[app.py] ✅ 路径回填完成: {backfilled_partitions} 个分区, 共 {backfilled_paths} 条路径")
        except Exception as backfill_error:
            log_print(f"[app.py] ⚠️ 路径回填失败: {backfill_error}")

        # print(f"[app.py] ✅ 路径级别分析完成", flush=True)
        _safe_flush()
        
        # ===== 构建返回数据 =====
        update_analysis_status(progress=90, status='准备返回数据...')
        print(f"[app.py] 准备返回数据...", flush=True)
        _safe_flush()
        
        timing.start_phase('result_finalize_and_save', layer='default_visible', blocking=True)
        # 构建功能分区列表
        function_partitions = []
        for i, partition in enumerate(partitions):
            partition_id = partition.get("partition_id", f"partition_{i}")
            methods = partition.get("methods", [])
            
            # 计算出度和入度
            outgoing_calls = {}
            incoming_calls = {}
            
            # 从调用图统计出度和入度
            for method_sig in methods:
                if method_sig in call_graph:
                    # 统计出度（调用其他分区的方法）
                    # call_graph[method_sig] 是一个 Set[str]，直接遍历
                    for callee in call_graph[method_sig]:
                        # 找到callee所属的分区
                        for other_partition in partitions:
                            if callee in other_partition.get("methods", []):
                                other_id = other_partition.get("partition_id", "unknown")
                                if other_id != partition_id:
                                    if other_id not in outgoing_calls:
                                        outgoing_calls[other_id] = 0
                                    outgoing_calls[other_id] += 1
                                break
                    
                    # 统计入度（被其他分区的方法调用）
                    # 需要遍历所有调用图找到调用当前方法的
                    for caller_sig, callees_set in call_graph.items():
                        if caller_sig not in methods:
                            if method_sig in callees_set:
                                # 找到caller所属的分区
                                for other_partition in partitions:
                                    if caller_sig in other_partition.get("methods", []):
                                        other_id = other_partition.get("partition_id", "unknown")
                                        if other_id != partition_id:
                                            if other_id not in incoming_calls:
                                                incoming_calls[other_id] = 0
                                            incoming_calls[other_id] += 1
                                        break
            
            # 统计类数量（从analyzer.report获取）
            class_names = set()
            for method_sig in methods:
                if "." in method_sig:
                    class_name = method_sig.rsplit(".", 1)[0]
                    if analyzer.report and class_name in analyzer.report.classes:
                        class_names.add(class_name)
            
            # 使用LLM增强后的信息
            partition_name = partition.get("name", partition_id)
            partition_description = partition.get("description", f"功能分区，包含 {len(methods)} 个方法")
            partition_folders = partition.get("folders", [])
            partition_keywords = partition.get("keywords", [])
            
            # 构建详细描述，包含统计信息
            detailed_description = partition_description
            if partition.get("name_conflict"):
                detailed_description += f" (注意：此分区与其他分区名称相同但内容不同)"
            
            function_partitions.append({
                'name': partition_name,
                'description': detailed_description,
                'partition_id': partition_id,
                'methods': methods,
                'method_count': len(methods),
                'modularity': partition.get("modularity", 0.0),
                'outgoing_calls': outgoing_calls,
                'incoming_calls': incoming_calls,
                'folders': partition_folders,
                'keywords': partition_keywords,
                'name_conflict': partition.get("name_conflict", False),  # 标记是否为名称冲突
                'original_name': partition.get("original_name", partition_name),  # 原始名称
                'stats': {
                    'total_classes': len(class_names),  # 准确统计类数量
                    'total_methods': len(methods),
                    'total_functions': 0  # 可以从analyzer.report进一步统计
                }
            })

        timing.start_phase('shadow_generation_total', layer='default_visible', blocking=True)
        phase4_threshold = _get_phase4_threshold()
        print(f"[workset5] parallel_stage=shadow_generation workers=2 entry_points_shadow+community_shadow", flush=True)
        shadow_started_at = time.perf_counter()
        entry_points_shadow = None
        process_shadow = None
        community_shadow = None

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix='fh-shadow') as executor:
            entry_shadow_future = executor.submit(
                build_entry_points_shadow,
                partitions=partitions,
                call_graph=call_graph,
                analyzer_report=analyzer.report,
                threshold=phase4_threshold,
            )
            community_shadow_future = executor.submit(
                build_community_shadow,
                call_graph=call_graph,
                graph_data=graph_data,
                algorithm='leiden',
                fallback_algorithm='louvain',
                weight_threshold=0.0,
                timeout_seconds=_get_phase5_timeout_seconds(),
                max_nodes=_get_phase5_max_nodes(),
            )

            try:
                entry_points_shadow = entry_shadow_future.result()
                entry_points_shadow["generated_at"] = datetime.now().isoformat()
                entry_points_shadow["project_path"] = project_path
                print(f"[workset5] shadow_stage=entry_points_shadow ready", flush=True)
            except Exception as entry_shadow_error:
                print(f"[app.py] ⚠️ Entry points shadow 生成失败: {entry_shadow_error}", flush=True)
                entry_points_shadow = {'partitions': {}, 'project_path': project_path, 'generated_at': datetime.now().isoformat(), 'error': str(entry_shadow_error)}

            for partition_id, partition_shadow in (entry_points_shadow.get('partitions') or {}).items():
                if partition_id not in partition_analyses:
                    partition_analyses[partition_id] = {}
                partition_analyses[partition_id]['entry_points_shadow'] = partition_shadow
            print(f"[workset5] shadow_stage=entry_points_shadow merged", flush=True)

            try:
                process_shadow = build_process_shadow(
                    partitions=partitions,
                    partition_analyses=partition_analyses,
                    call_graph=call_graph,
                    graph_data=graph_data,
                )
                process_shadow["project_path"] = project_path
                process_shadow["generated_at"] = datetime.now().isoformat()
                print(f"[workset5] shadow_stage=process_shadow ready", flush=True)
            except Exception as process_shadow_error:
                print(f"[app.py] ⚠️ Process shadow 生成失败: {process_shadow_error}", flush=True)

            try:
                community_shadow = community_shadow_future.result()
                community_shadow['project_path'] = project_path
                community_shadow['generated_at'] = datetime.now().isoformat()
                print(f"[workset5] shadow_stage=community_shadow ready", flush=True)
            except Exception as community_shadow_error:
                print(f"[app.py] ⚠️ Community shadow 生成失败: {community_shadow_error}", flush=True)

        print(f"[workset5] parallel_stage=shadow_generation completed elapsed_seconds={round(time.perf_counter()-shadow_started_at, 6)}", flush=True)

        timing.end_phase('shadow_generation_total')
        timing.mark_ready('function_hierarchy_summary')
        layer_states['deferred_background'] = _build_layer_state('pending_background' if INDEX_REBUILD_MODE == 'immediate' else 'available_on_demand' if INDEX_REBUILD_MODE == 'deferred' else 'disabled', ['entry_points_shadow', 'process_shadow', 'community_shadow', 'index_rebuild'], visible=False)
        _publish_partial_result(96, 'Workset3: shadow 与索引状态已补齐', include_expand=True, include_advanced=True, include_shadow=True)

        result_data = {
            'hierarchy': {
                'layer1_functions': function_partitions,
                'metadata': {
                    'project_path': project_path,
                    'total_partitions': len(partitions),
                    'total_methods': len(call_graph)
                }
            },
            'partition_analyses': partition_analyses,
            'entry_points_shadow': entry_points_shadow,
            'process_shadow': process_shadow,
            'community_shadow': community_shadow,
            'execution_profile': execution_profile,
            'pipeline_structure': copy.deepcopy(pipeline_structure),
            'result_layers': copy.deepcopy(layer_states),
            'cache_runtime': cache_runtime,
            'degradation_summary': copy.deepcopy(degradation_summary),
            'skipped_or_deferred_work': copy.deepcopy(skipped_or_deferred_work),
            'index_rebuild_status': copy.deepcopy(index_rebuild_status),
        }
        
        timing.mark_published()
        timing.mark_blocking_finished()
        update_analysis_status(
            progress=100,
            status='功能层级分析完成！',
            data=result_data,
            is_analyzing=False
        )
        
        # 标准化项目路径（处理Windows路径的反斜杠）
        normalized_project_path = os.path.normpath(project_path)
        
        # 保存分析结果到缓存（按项目路径索引，通过DataAccessor）
        timing.end_phase('result_finalize_and_save')

        timing_payload = timing.finalize()
        result_data['performance_baseline'] = timing_payload
        log_print(f"[workset0] performance_baseline={json.dumps(timing_payload, ensure_ascii=False)}")

        default_snapshot = _build_function_hierarchy_snapshot(
            project_path=project_path,
            partitions=partitions,
            partition_analyses=partition_analyses,
            execution_profile=execution_profile,
            layer_states=layer_states,
            include_expand=False,
            include_advanced=False,
        )
        expand_snapshot = _build_function_hierarchy_snapshot(
            project_path=project_path,
            partitions=partitions,
            partition_analyses=partition_analyses,
            execution_profile=execution_profile,
            layer_states=layer_states,
            include_expand=True,
            include_advanced=False,
        )
        advanced_snapshot = _build_function_hierarchy_snapshot(
            project_path=project_path,
            partitions=partitions,
            partition_analyses=partition_analyses,
            execution_profile=execution_profile,
            layer_states=layer_states,
            include_expand=True,
            include_advanced=True,
            entry_points_shadow=entry_points_shadow,
            process_shadow=process_shadow,
            community_shadow=community_shadow,
            performance_baseline=timing_payload,
        )

        layer_cache_payload_to_save = {
            'meta': {
                'project_path': normalized_project_path,
                'code_state_fingerprint': code_state_fingerprint,
                'saved_at': datetime.now().isoformat(),
            },
            'layers': {
                'default_visible': {
                    'signature': cache_signatures['default_visible'],
                    'snapshot': default_snapshot,
                },
                'expand_visible': {
                    'signature': cache_signatures['expand_visible'],
                    'snapshot': expand_snapshot,
                },
                'advanced_visible': {
                    'signature': cache_signatures['advanced_visible'],
                    'snapshot': advanced_snapshot,
                },
            },
            'final_result': copy.deepcopy(result_data),
        }
        data_accessor.save_function_hierarchy_layer_cache(normalized_project_path, layer_cache_payload_to_save)
        _log_layer_cache_decision('default_visible', 'store', 'saved_after_run')
        _log_layer_cache_decision('expand_visible', 'store', 'saved_after_run')
        _log_layer_cache_decision('advanced_visible', 'store', 'saved_after_run')

        data_accessor.save_function_hierarchy(normalized_project_path, result_data)
        if process_shadow:
            data_accessor.save_process_shadow(normalized_project_path, process_shadow)
        if community_shadow:
            data_accessor.save_community_shadow(normalized_project_path, community_shadow)
        print(f"[app.py] 💾 功能层级分析结果已保存到缓存: {normalized_project_path}", flush=True)

        try:
            _project_library_storage.save_function_hierarchy(normalized_project_path, result_data)
            persisted_path_count = 0
            for partition_payload in (partition_analyses or {}).values():
                if isinstance(partition_payload, dict):
                    persisted_path_count += len(partition_payload.get('path_analyses') or [])
            _project_library_storage.save_project_profile(
                normalized_project_path,
                {
                    'project_name': os.path.basename(normalized_project_path) or 'unknown_project',
                    'display_name': _build_project_display_name(normalized_project_path, partition_analyses),
                    'analysis_timestamp': datetime.utcnow().isoformat() + 'Z',
                    'has_graph': True,
                    'has_hierarchy': True,
                    'path_count': persisted_path_count,
                    'experience_output_root': experience_output_root,
                },
            )
        except Exception as storage_exc:
            print(f"[app.py] ⚠️ 功能层级持久化失败: {storage_exc}", flush=True)

        # Phase 1 / Task 1.2: 自动保存经验路径到 JSON（持久化）
        try:
            from data.experience_path_storage import ExperiencePathStorage

            accessor = get_data_accessor()
            experience_paths = accessor.get_experience_paths(normalized_project_path)  # type: ignore[attr-defined]
            storage_dir = os.path.join(experience_output_root, 'experience_paths') if experience_output_root else 'output_analysis/experience_paths'
            storage = ExperiencePathStorage(storage_dir=storage_dir)
            storage.save_experience_paths(normalized_project_path, experience_paths, partition_analyses)
            if process_shadow:
                ProcessShadowStorage().save(normalized_project_path, process_shadow)
            if community_shadow:
                CommunityShadowStorage().save(normalized_project_path, community_shadow)
            
            # Phase 5: 自动触发 RAG 索引重建 (包含导出 knowledge_base_preview.md)
            if INDEX_REBUILD_MODE == 'immediate':
                print(f"[app.py] 🔄 开始重建 RAG 索引...", flush=True)
                timing.mark_index_rebuild_triggered()
                index_rebuild_status.update({
                    'status': 'pending_background',
                    'reason_code': 'scheduled_background_rebuild',
                    'user_message': '索引重建已启动，若超出可见超时将继续在后台执行',
                    'continues_in_background': True,
                })
                try:
                    # 动态导入以避免循环依赖
                    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    if project_root not in sys.path:
                        sys.path.insert(0, project_root)

                    import build_graph_index
                    import threading

                    def run_build_index():
                        try:
                            build_graph_index.build_index()
                            timing.mark_index_rebuild_finished()
                            index_rebuild_status.update({
                                'status': 'ready',
                                'reason_code': 'completed',
                                'user_message': '索引重建已完成',
                                'continues_in_background': False,
                            })
                            print(f"[app.py] ✅ RAG 索引自动重建完成", flush=True)
                        except Exception as e:
                            timing.mark_index_rebuild_finished(error=str(e))
                            index_rebuild_status.update({
                                'status': 'available_on_demand',
                                'reason_code': 'background_rebuild_failed',
                                'user_message': f'索引重建失败：{e}，可稍后重试',
                                'continues_in_background': False,
                            })
                            print(f"[app.py] ⚠️ RAG 索引重建失败: {e}", flush=True)

                    threading.Thread(target=run_build_index, daemon=True).start()
                    _record_layer_degradation(
                        layer_states,
                        degradation_summary,
                        skipped_or_deferred_work,
                        layer='deferred_background',
                        stage='index_rebuild',
                        reason_code='index_rebuild_background_timeout_window',
                        status_after_degrade='pending_background',
                        timeout_seconds=_get_index_rebuild_visibility_timeout_seconds(),
                        user_message='索引重建不会阻塞本次分析结果返回，当前将在后台继续执行',
                        retry_mode='background',
                        deferred_section='index_rebuild',
                    )
                except Exception as e:
                    timing.mark_index_rebuild_disabled(error=str(e))
                    index_rebuild_status.update({
                        'status': 'available_on_demand',
                        'reason_code': 'trigger_failed',
                        'user_message': f'索引重建触发失败：{e}，可稍后重试',
                        'continues_in_background': False,
                    })
                    print(f"[app.py] ⚠️ 触发 RAG 索引重建失败: {e}", flush=True)
            elif INDEX_REBUILD_MODE == 'deferred':
                timing.mark_index_rebuild_disabled(error='deferred_by_workset1')
                index_rebuild_status.update({
                    'status': 'available_on_demand',
                    'reason_code': 'deferred_by_config',
                    'user_message': '索引重建默认未执行，可后续按需触发',
                    'continues_in_background': False,
                })
                print(f"[app.py] ℹ️ Workset1: RAG 索引重建已延后，不阻塞本次分析", flush=True)
            else:
                timing.mark_index_rebuild_disabled(error='disabled_by_workset1')
                index_rebuild_status.update({
                    'status': 'disabled',
                    'reason_code': 'disabled_by_config',
                    'user_message': '索引重建已关闭',
                    'continues_in_background': False,
                })
                print(f"[app.py] ℹ️ Workset1: RAG 索引重建已关闭", flush=True)
                
        except Exception as e:
            timing.mark_index_rebuild_disabled(error=str(e))
            index_rebuild_status.update({
                'status': 'available_on_demand',
                'reason_code': 'experience_path_persist_failed',
                'user_message': f'经验路径持久化失败：{e}，索引重建未执行',
                'continues_in_background': False,
            })
            print(f"[app.py] ⚠️ 保存经验路径到JSON失败: {e}", flush=True)
        
        print(f"[app.py] {'='*60}", flush=True)
        print(f"[app.py] ✅✅✅ 功能层级分析完成！", flush=True)
        print(f"[app.py] {'='*60}\n", flush=True)
        _safe_flush()
        
        # ===== 检查入口点、调用图、超图是否存在 =====
        print(f"\n[app.py] {'='*80}", flush=True)
        print(f"[app.py] 🔍 检查所有分区的入口点、调用图、超图是否存在", flush=True)
        print(f"[app.py] {'='*80}", flush=True)
        
        partitions_without_call_graph = []
        partitions_without_hypergraph = []
        partitions_without_entry_points = []
        
        for partition_id in sorted(partition_analyses.keys()):
            analysis = partition_analyses[partition_id]
            partition_name = None
            for p in partitions:
                if p.get("partition_id") == partition_id:
                    partition_name = p.get("name", partition_id)
                    break
            
            print(f"\n[app.py]   分区: {partition_id} ({partition_name})", flush=True)
            
            # 检查调用图
            if 'call_graph' in analysis:
                call_graph_data = analysis['call_graph']
                nodes = call_graph_data.get('nodes', [])
                edges = call_graph_data.get('edges', [])
                print(f"[app.py]     ✓ 调用图: 存在 (节点: {len(nodes)}, 边: {len(edges)})", flush=True)
            else:
                print(f"[app.py]     ❌ 调用图: 不存在", flush=True)
                partitions_without_call_graph.append(partition_id)
            
            # 检查超图
            if 'hypergraph' in analysis and 'hypergraph_viz' in analysis:
                hypergraph_data = analysis.get('hypergraph', {})
                hypergraph_viz = analysis.get('hypergraph_viz', {})
                nodes = hypergraph_viz.get('nodes', [])
                edges = hypergraph_viz.get('edges', [])
                print(f"[app.py]     ✓ 超图: 存在 (节点: {len(nodes)}, 边: {len(edges)})", flush=True)
                if len(edges) == 0:
                    print(f"[app.py]       ⚠️ 警告：超图没有边，可能无法显示连线", flush=True)
            else:
                print(f"[app.py]     ❌ 超图: 不存在", flush=True)
                if 'hypergraph' not in analysis:
                    print(f"[app.py]       - 缺少 'hypergraph' 键", flush=True)
                if 'hypergraph_viz' not in analysis:
                    print(f"[app.py]       - 缺少 'hypergraph_viz' 键", flush=True)
                partitions_without_hypergraph.append(partition_id)
            
            # 检查入口点
            if 'entry_points' in analysis:
                entry_points = analysis['entry_points']
                print(f"[app.py]     ✓ 入口点: 存在 ({len(entry_points)} 个)", flush=True)
                if len(entry_points) > 0:
                    print(f"[app.py]       - 入口点列表（前3个）:", flush=True)
                    for ep in entry_points[:3]:
                        method_sig = ep.get('method_signature', 'unknown')
                        score = ep.get('score', 0)
                        reasons = ep.get('reasons', [])
                        print(f"[app.py]         • {method_sig} (评分: {score:.2f}, 原因: {', '.join(reasons[:2]) if reasons else 'N/A'})", flush=True)
                else:
                    print(f"[app.py]       ⚠️ 警告：入口点列表为空", flush=True)
            else:
                print(f"[app.py]     ❌ 入口点: 不存在", flush=True)
                partitions_without_entry_points.append(partition_id)
        
        # 汇总统计
        print(f"\n[app.py] {'='*80}", flush=True)
        print(f"[app.py] 📊 检查结果汇总", flush=True)
        print(f"[app.py] {'='*80}", flush=True)
        print(f"[app.py]   总分区数: {len(partition_analyses)}", flush=True)
        print(f"[app.py]   有调用图的分区: {len(partition_analyses) - len(partitions_without_call_graph)}", flush=True)
        print(f"[app.py]   有超图的分区: {len(partition_analyses) - len(partitions_without_hypergraph)}", flush=True)
        print(f"[app.py]   有入口点的分区: {len(partition_analyses) - len(partitions_without_entry_points)}", flush=True)
        
        if partitions_without_call_graph:
            print(f"\n[app.py]   ❌ 缺少调用图的分区 ({len(partitions_without_call_graph)} 个):", flush=True)
            for pid in partitions_without_call_graph[:10]:
                print(f"[app.py]     - {pid}", flush=True)
            if len(partitions_without_call_graph) > 10:
                print(f"[app.py]     ... 还有 {len(partitions_without_call_graph) - 10} 个分区", flush=True)
        
        if partitions_without_hypergraph:
            print(f"\n[app.py]   ❌ 缺少超图的分区 ({len(partitions_without_hypergraph)} 个):", flush=True)
            for pid in partitions_without_hypergraph[:10]:
                print(f"[app.py]     - {pid}", flush=True)
            if len(partitions_without_hypergraph) > 10:
                print(f"[app.py]     ... 还有 {len(partitions_without_hypergraph) - 10} 个分区", flush=True)
        
        if partitions_without_entry_points:
            print(f"\n[app.py]   ❌ 缺少入口点的分区 ({len(partitions_without_entry_points)} 个):", flush=True)
            for pid in partitions_without_entry_points[:10]:
                print(f"[app.py]     - {pid}", flush=True)
            if len(partitions_without_entry_points) > 10:
                print(f"[app.py]     ... 还有 {len(partitions_without_entry_points) - 10} 个分区", flush=True)
        
        if not partitions_without_call_graph and not partitions_without_hypergraph and not partitions_without_entry_points:
            print(f"\n[app.py]   ✅ 所有分区都有调用图、超图和入口点！", flush=True)
        
        print(f"[app.py] {'='*80}\n", flush=True)
        _safe_flush()
        
    except Exception as e:
        log_print(f"\n[app.py] {'='*60}")
        log_print(f"[app.py] ❌ 功能层级分析出错: {e}")
        log_print(f"[app.py] {'='*60}")
        import traceback
        _safe_traceback_print()
        # 同时写入日志文件
        with _log_file_lock:
            if _log_file and not _log_file.closed:
                try:
                    traceback.print_exc(file=_log_file)
                    _log_file.flush()
                except Exception:
                    pass
        _safe_flush()
        # 更新错误状态
        update_analysis_status(
            error=str(e),
            is_analyzing=False,
            progress=0,
            status='分析失败'
        )
    else:
        # 分析成功完成
        update_analysis_status(
            error=None,
            is_analyzing=False,
            progress=100,
            status='分析完成'
        )
    finally:
        # 关闭日志文件
        log_print(f"\n[app.py] {'='*60}")
        log_print(f"[app.py] 功能层级分析完成，日志文件已保存")
        log_print(f"[app.py] {'='*60}")
        close_log_file()
        print(f"[app.py] {'='*60}\n", flush=True)
        _safe_flush()



def api_analyze_function_hierarchy():
    """开始功能层级分析API（使用社区检测）"""
    data = request.json or {}
    project_path = data.get('project_path')
    experience_output_root: Optional[str] = None
    raw_experience_output_root = str(data.get('experience_output_root') or '').strip()
    
    # 验证路径：如果路径无效或不存在，使用当前项目目录
    if not project_path or not os.path.isdir(project_path):
        project_path = str(PROJECT_ROOT)
        print(f"[api_analyze_function_hierarchy] ⚠️ 路径无效，使用默认路径: {project_path}", flush=True)
    else:
        print(f"[api_analyze_function_hierarchy] ✅ 使用指定路径: {project_path}", flush=True)

    if raw_experience_output_root:
        if not os.path.isabs(raw_experience_output_root):
            return jsonify({'error': 'experience_output_root 必须是绝对路径'}), 400
        experience_output_root = os.path.normpath(os.path.abspath(raw_experience_output_root))
        try:
            os.makedirs(experience_output_root, exist_ok=True)
        except Exception as exc:
            return jsonify({'error': f'experience_output_root 创建失败: {exc}'}), 400
    
    # 重置状态
    update_analysis_status(
        progress=0,
        status='分析中...',
        data=None,
        error=None,
        is_analyzing=True,
        analysis_type='function_hierarchy',
        project_path=os.path.normpath(project_path),
    )
    
    # 标准化项目路径
    normalized_project_path = os.path.normpath(project_path)
    
    print(f"[api_analyze_function_hierarchy] ♻️ 保留既有缓存，交由 Workset4 命中/失效逻辑判断: {normalized_project_path}", flush=True)
    
    # 后台分析（使用新的analyze_function_hierarchy函数）
    thread = threading.Thread(target=analyze_function_hierarchy, args=(project_path,), kwargs={'experience_output_root': experience_output_root})
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': '功能层级分析已开始'})


def api_open_file_system_path():
    data = request.json or {}
    raw_path = str(data.get('path') or '').strip()
    if not raw_path:
        return jsonify({'error': 'path 不能为空'}), 400

    if not os.path.isabs(raw_path):
        return jsonify({'error': 'path 必须是绝对路径'}), 400

    normalized_path = os.path.normpath(os.path.abspath(raw_path))
    if not os.path.exists(normalized_path):
        return jsonify({'error': f'path 不存在: {normalized_path}'}), 400

    try:
        action = 'open'
        if sys.platform.startswith('win'):
            if os.path.isfile(normalized_path):
                subprocess.Popen(['explorer', f'/select,{normalized_path}'])
                action = 'select'
            else:
                subprocess.Popen(['explorer', normalized_path])
                action = 'open'
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', normalized_path])
        else:
            subprocess.Popen(['xdg-open', normalized_path])
        return jsonify({'ok': True, 'path': normalized_path, 'action': action})
    except Exception as exc:
        return jsonify({'error': f'打开路径失败: {exc}'}), 500


def api_result():
    """获取分析结果"""
    # 优先从当前分析状态获取
    if analysis_status['data']:
        # 检查是否是主分析结果（有nodes和edges），而不是功能层级分析结果
        data = analysis_status['data']
        if data.get('nodes') and data.get('edges'):
            return jsonify(data)
    
    # 如果当前没有，尝试从缓存中恢复
    project_path = request.args.get('project_path')
    if not project_path:
        # 尝试从sessionStorage或默认路径获取
        project_path = str(PROJECT_ROOT)
    
    # 标准化路径
    project_path = os.path.normpath(project_path)
    
    # 直接匹配
    cached = data_accessor.get_main_analysis(project_path)
    if cached:
        print(f"[api_result] 💾 从缓存恢复主分析结果: {project_path}", flush=True)
        with status_lock:
            analysis_status['data'] = cached
        return jsonify(cached)

    # 尝试其他可能的路径格式（Windows路径可能有不同的表示方式）
    for cached_path in data_accessor.list_main_analysis_keys():
        if os.path.normpath(cached_path) == project_path:
            cached = data_accessor.get_main_analysis(cached_path)
            if cached:
                print(f"[api_result] 💾 从缓存恢复主分析结果（路径匹配）: {cached_path}", flush=True)
                with status_lock:
                    analysis_status['data'] = cached
                return jsonify(cached)
    
    return jsonify({'error': '暂无结果'}), 400


def api_check_main_result():
    """检查是否有已保存的主分析结果"""
    project_path = request.args.get('project_path')
    if not project_path:
        # 尝试从默认路径获取
        project_path = str(PROJECT_ROOT)
    
    # 标准化路径（处理Windows路径的反斜杠）
    project_path = os.path.normpath(project_path)
    
    # 尝试多种路径格式匹配（Windows路径可能有不同的表示方式）
    if data_accessor.get_main_analysis(project_path):
        return jsonify({
            'has_result': True,
            'project_path': project_path,
            'message': '已找到保存的主分析结果'
        })

    for cached_path in data_accessor.list_main_analysis_keys():
        if os.path.normpath(cached_path) == project_path:
            return jsonify({
                'has_result': True,
                'project_path': cached_path,
                'message': '已找到保存的主分析结果'
            })

    return jsonify({
        'has_result': False,
        'project_path': project_path,
        'message': '未找到保存的主分析结果'
    })


def _resolve_function_hierarchy_cached(project_path: str) -> Optional[Dict[str, Any]]:
    """根据项目路径解析可用的功能层级缓存（仅返回有效 payload）。"""
    hierarchy_cached = data_accessor.get_function_hierarchy(project_path)
    if hierarchy_cached:
        return hierarchy_cached

    for cached_path in data_accessor.list_function_hierarchy_keys():
        if os.path.normpath(cached_path) == project_path:
            matched_cached = data_accessor.get_function_hierarchy(cached_path)
            if matched_cached:
                return matched_cached

    persisted = _project_library_storage.load_function_hierarchy(project_path)
    if isinstance(persisted, dict):
        data_accessor.save_function_hierarchy(project_path, persisted)
        process_shadow = persisted.get('process_shadow') if isinstance(persisted.get('process_shadow'), dict) else None
        community_shadow = persisted.get('community_shadow') if isinstance(persisted.get('community_shadow'), dict) else None
        if process_shadow:
            data_accessor.save_process_shadow(project_path, process_shadow)
        if community_shadow:
            data_accessor.save_community_shadow(project_path, community_shadow)
        return persisted

    return None


def api_check_function_hierarchy():
    """检查是否有可用于 Stage1 读契约的功能层级分析结果。"""
    project_path = request.args.get('project_path')
    if not project_path:
        # 尝试从sessionStorage或默认路径获取
        project_path = str(PROJECT_ROOT)

    normalized_project_path = os.path.normpath(project_path)
    hierarchy_cached = _resolve_function_hierarchy_cached(normalized_project_path)
    contract_payload = _build_phase6_read_contract(normalized_project_path, hierarchy_cached)

    if contract_payload:
        return jsonify({
            'has_result': True,
            'project_path': normalized_project_path,
            'message': '已找到可用于 Stage1 读契约的功能层级结果'
        })

    return jsonify({
        'has_result': False,
        'project_path': normalized_project_path,
        'message': '未找到可用于 Stage1 读契约的功能层级结果'
    })


def api_get_function_hierarchy_result():
    """获取已保存的功能层级分析结果"""
    project_path = request.args.get('project_path')
    if not project_path:
        project_path = str(PROJECT_ROOT)
    
    # 标准化路径
    project_path = os.path.normpath(project_path)
    
    cached = data_accessor.get_function_hierarchy(project_path)
    if not cached:
        for cached_path in data_accessor.list_function_hierarchy_keys():
            if os.path.normpath(cached_path) == project_path:
                cached = data_accessor.get_function_hierarchy(cached_path)
                break

    if not cached:
        return jsonify({'error': '未找到保存的分析结果'}), 404

    best_payload = _select_best_phase6_hierarchy_payload(project_path, cached)
    return jsonify(best_payload or cached)


def _build_phase6_read_contract(project_path: str, hierarchy_cached: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not hierarchy_cached:
        return None

    entry_points_shadow = hierarchy_cached.get('entry_points_shadow')
    process_shadow = hierarchy_cached.get('process_shadow')
    community_shadow = hierarchy_cached.get('community_shadow')
    layer1_functions = (hierarchy_cached.get('hierarchy') or {}).get('layer1_functions') or []
    partition_meta_map = {
        item.get('partition_id'): item
        for item in layer1_functions
        if isinstance(item, dict) and item.get('partition_id')
    }
    partition_methods_map = {
        item.get('partition_id'): item.get('methods', [])
        for item in layer1_functions
        if isinstance(item, dict) and item.get('partition_id')
    }

    partition_analyses = hierarchy_cached.get('partition_analyses') or {}
    partition_summaries = []
    for partition_id, analysis in partition_analyses.items():
        partition_meta = partition_meta_map.get(partition_id) or {}
        path_analyses, path_info = _get_partition_path_payload(analysis, partition_methods=partition_methods_map.get(partition_id, []))
        deferred_path_count = int(path_info.get('deferred_count') or 0)
        total_available_path_count = max(
            len(path_analyses) + deferred_path_count,
            int(path_info.get('total_candidates') or 0),
            len(path_analyses),
        )
        rich_path_count = sum(
            1
            for item in path_analyses
            if any([
                item.get('cfg'),
                item.get('dfg'),
                item.get('io_graph'),
                item.get('cfg_dfg_explain_md'),
                bool((item.get('semantics') or {}).get('description')),
            ])
        )
        has_cfg = any(bool(item.get('cfg')) for item in path_analyses)
        has_dfg = any(bool(item.get('dfg')) for item in path_analyses)
        has_io = any(bool(item.get('io_graph')) for item in path_analyses)
        partition_summaries.append(
            {
                'partition_id': partition_id,
                'name': partition_meta.get('name') or analysis.get('name') or partition_id,
                'description': partition_meta.get('description') or analysis.get('description') or '',
                'methods': partition_methods_map.get(partition_id, []),
                'path_count': total_available_path_count,
                'selected_path_count': len(path_analyses),
                'rich_path_count': rich_path_count,
                'available_path_count': total_available_path_count,
                'deferred_path_count': deferred_path_count,
                'selection_policy': path_info.get('selection_policy'),
                'analysis_status': path_info.get('completion_status') or ('complete' if path_analyses else 'fallback'),
                'entry_point_count': len((analysis.get('entry_points') or [])),
                'shadow_entry_point_count': len(((analysis.get('entry_points_shadow') or {}).get('effective_entries') or [])),
                'process_count': len([
                    process for process in ((process_shadow or {}).get('processes') or [])
                    if process.get('partition_id') == partition_id
                ]),
                'community_count': len([
                    community for community in ((community_shadow or {}).get('communities') or [])
                    if set(community.get('methods', []) or []).intersection(set(partition_methods_map.get(partition_id, [])))
                ]),
                'has_cfg': has_cfg,
                'has_dfg': has_dfg,
                'has_io': has_io,
                'supports_process_shadow': bool(process_shadow),
                'supports_community_shadow': bool(community_shadow),
            }
        )

    return {
        'contract_version': 'phase6-stage1-v1',
        'project_path': project_path,
        'capabilities': {
            'hybrid_search_shadow': True,
            'entry_points_shadow': bool(entry_points_shadow),
            'process_shadow': bool(process_shadow),
            'community_shadow': bool(community_shadow),
            'cfg_dfg_entity_api': True,
            'path_level_cfg_dfg_io': True,
        },
        'sources': {
            'hierarchy': '/api/function_hierarchy/result',
            'entry_points_shadow': '/api/entry_points_shadow',
            'process_shadow': '/api/process_shadow',
            'community_shadow': '/api/community_shadow',
            'hybrid_search_shadow': '/api/search_hybrid_shadow',
            'cfg_dfg': '/api/cfg_dfg/<entity_id>',
        },
        'adapters': {
            'partition_summaries': partition_summaries,
        },
        'hierarchy_result': hierarchy_cached,
        'shadow_results': {
            'entry_points': entry_points_shadow,
            'process': process_shadow,
            'community': community_shadow,
        },
    }


def _measure_hierarchy_path_richness(payload: Optional[Dict[str, Any]]) -> int:
    if not isinstance(payload, dict):
        return -1
    partition_analyses = payload.get('partition_analyses') or {}
    richness = 0
    for analysis in partition_analyses.values():
        if not isinstance(analysis, dict):
            continue
        richness += len(analysis.get('path_analyses') or [])
        richness += sum(len(paths or []) for paths in (analysis.get('paths_map') or {}).values())
        path_info = analysis.get('path_analysis_info') or {}
        richness += int(path_info.get('selected_count') or 0)
        richness += int(path_info.get('deferred_count') or 0)
    return richness


def _extract_lightweight_partition_paths(analysis: Dict[str, Any], partition_methods: Optional[List[str]] = None, max_paths: int = 4) -> List[Dict[str, Any]]:
    call_graph = analysis.get('call_graph') or {}
    edges = call_graph.get('edges') or []
    methods = {
        str(node.get('id') or node.get('label') or '').strip()
        for node in (call_graph.get('nodes') or [])
        if isinstance(node, dict) and str(node.get('id') or node.get('label') or '').strip()
    }
    methods.update(str(item).strip() for item in (partition_methods or []) if str(item).strip())
    adjacency: Dict[str, List[str]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get('source') or edge.get('sourceId') or edge.get('caller') or '').strip()
        target = str(edge.get('target') or edge.get('targetId') or edge.get('callee') or '').strip()
        if not source or not target:
            continue
        adjacency.setdefault(source, []).append(target)
        methods.add(source)
        methods.add(target)

    entry_points = analysis.get('entry_points') or []
    start_methods = [
        str(item.get('method_signature') or '').strip()
        for item in entry_points
        if isinstance(item, dict) and str(item.get('method_signature') or '').strip()
    ]
    if not start_methods:
        start_methods = sorted(methods)[:max_paths]

    results: List[Dict[str, Any]] = []
    seen_paths: Set[Tuple[str, ...]] = set()
    for start_method in start_methods:
        if len(results) >= max_paths:
            break
        path = [start_method]
        next_methods = adjacency.get(start_method, [])
        if next_methods:
            path.append(next_methods[0])
            tail_methods = adjacency.get(next_methods[0], [])
            if tail_methods:
                path.append(tail_methods[0])
        normalized_path = tuple(item for item in path if item)
        if not normalized_path or normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)
        results.append({
            'leaf_node': normalized_path[-1],
            'path_index': len(results),
            'path': list(normalized_path),
            'path_name': f'轻量路径 {len(results) + 1}',
            'path_description': '基于入口点与分区调用图生成的轻量功能路径',
            'worthiness_score': round(max(0.35, 0.65 - len(results) * 0.05), 2),
            'worthiness_reasons': ['当前项目尚未产出完整高级路径分析，先展示轻量路径骨架'],
            'cfg': None,
            'dfg': None,
            'io_graph': None,
            'highlight_config': {
                'call_chain_type': 'lightweight_fallback',
                'main_method': normalized_path[0],
                'intermediate_methods': list(normalized_path[1:-1]),
                'path_methods': list(normalized_path),
                'explanation': '该路径来自入口点与分区调用图的轻量推断，可作为后续深分析锚点。',
            },
        })
    return results


def _extract_structural_partition_paths(analysis: Dict[str, Any], max_paths: int = 4) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    paths_map = analysis.get('paths_map') or {}
    if not isinstance(paths_map, dict) or not paths_map:
        return [], {}

    filter_single_node_paths = os.getenv('FH_FILTER_SINGLE_NODE_PATHS', '1') != '0'
    fqmn_info_map = _build_fqmn_info_map(analysis.get('fqns', []))
    valid_candidates: List[Dict[str, Any]] = []
    fallback_candidates: List[Dict[str, Any]] = []

    for leaf_node, paths in paths_map.items():
        for path_index, path in enumerate(paths or []):
            normalized_path = [str(item).strip() for item in (path or []) if str(item).strip()]
            if not normalized_path:
                continue

            evaluation = _evaluate_path_candidate(normalized_path, fqmn_info_map, filter_single_node=filter_single_node_paths)
            candidate = {
                'leaf_node': str(leaf_node or normalized_path[-1]),
                'path_index': path_index,
                'path': normalized_path,
                'worthiness_score': evaluation.get('score', 0.0),
                'worthiness_reasons': [
                    f"internal_segment4={evaluation.get('internal_segment4_count', 0)}",
                    f"fqmn_known={evaluation.get('fqmn_known_count', 0)}",
                    f"path_length={len(normalized_path)}",
                ],
                'internal_segment4_count': evaluation.get('internal_segment4_count', 0),
                'invalid_reasons': evaluation.get('invalid_reasons', []),
            }
            if evaluation.get('is_valid'):
                valid_candidates.append(candidate)
            else:
                fallback_candidates.append({
                    **candidate,
                    'worthiness_score': round(max(0.25, float(len(normalized_path)) * 0.2), 6),
                    'worthiness_reasons': [
                        '该路径来自后端保存的结构路径，但尚未通过深分析筛选。',
                        *(candidate.get('invalid_reasons') or []),
                    ],
                })

    selected_candidates: List[Dict[str, Any]] = []
    deferred_candidates: List[Dict[str, Any]] = []
    selection_policy = 'structural_paths_map'
    total_candidates = len(valid_candidates)

    if valid_candidates:
        selected_candidates, deferred_candidates = _select_representative_paths(valid_candidates, max_paths)
    elif fallback_candidates:
        selection_policy = 'structural_paths_map_relaxed'
        total_candidates = len(fallback_candidates)
        selected_candidates, deferred_candidates = _select_representative_paths(fallback_candidates, max_paths)
    else:
        return [], {}

    results: List[Dict[str, Any]] = []
    for display_index, candidate in enumerate(selected_candidates, start=1):
        normalized_path = list(candidate.get('path') or [])
        results.append({
            'path_id': f"structural_{candidate.get('leaf_node')}_{candidate.get('path_index', 0)}",
            'leaf_node': candidate.get('leaf_node') or (normalized_path[-1] if normalized_path else ''),
            'function_chain': normalized_path,
            'path_index': candidate.get('path_index', display_index - 1),
            'path': normalized_path,
            'worthiness_score': candidate.get('worthiness_score', 0.0),
            'worthiness_reasons': candidate.get('worthiness_reasons', []),
            'deep_analysis_status': 'available_on_demand',
            'path_name': f'结构路径 {display_index}',
            'path_description': '基于后端结构路径缓存恢复的功能调用链，可继续按需触发深分析。',
            'cfg': None,
            'dfg': None,
            'io_graph': None,
            'highlight_config': {
                'call_chain_type': 'structural_fallback',
                'main_method': normalized_path[0] if normalized_path else '',
                'intermediate_methods': list(normalized_path[1:-1]),
                'path_methods': normalized_path,
                'explanation': '该路径直接来自后端保存的结构路径缓存，尚未补齐 CFG/DFG/IO 深分析。',
            },
        })

    path_info = {
        'selection_policy': selection_policy,
        'selected_count': len(results),
        'deferred_count': len(deferred_candidates),
        'total_candidates': total_candidates,
        'user_message': '当前展示的是后端结构路径缓存，可继续按需补跑深分析。',
        'representative_path_summaries': [
            _summarize_path_candidate(item, status='available_on_demand', reason='selected_from_structural_paths_map')
            for item in selected_candidates[:max_paths]
        ],
        'deferred_path_summaries': [
            _summarize_path_candidate(item, status='available_on_demand', reason='not_selected_from_structural_paths_map')
            for item in deferred_candidates[:20]
        ],
    }
    return results, path_info


def _get_partition_path_payload(analysis: Dict[str, Any], partition_methods: Optional[List[str]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    path_analyses = analysis.get('path_analyses') or []
    path_info = analysis.get('path_analysis_info') or {}
    if path_analyses:
        merged_info = dict(path_info)
        merged_info.setdefault('selection_policy', 'deep_analysis')
        merged_info.setdefault('selected_count', len(path_analyses))
        merged_info.setdefault('deferred_count', 0)
        merged_info.setdefault(
            'total_candidates',
            max(
                len(path_analyses) + int(merged_info.get('deferred_count') or 0),
                int(merged_info.get('original_total') or 0),
                len(path_analyses),
            ),
        )
        merged_info.setdefault('completion_status', 'complete')
        return path_analyses, merged_info
    structural_paths, structural_info = _extract_structural_partition_paths(analysis)
    if structural_paths:
        merged_info = dict(path_info)
        merged_info.update(structural_info)
        return structural_paths, merged_info
    lightweight_paths = _extract_lightweight_partition_paths(analysis, partition_methods=partition_methods)
    if lightweight_paths:
        return lightweight_paths, {
            'selection_policy': 'lightweight_fallback',
            'selected_count': len(lightweight_paths),
            'deferred_count': 0,
            'total_candidates': len(lightweight_paths),
        }
    return [], path_info


def _build_entrypoint_enriched_path_payload(
    project_path: str,
    partition_id: str,
    analysis: Dict[str, Any],
    *,
    max_paths: int = 4,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    report = _resolve_report_cached(project_path, allow_global_fallback=False)
    if not report:
        return [], {}

    entry_points = analysis.get('entry_points') or []
    call_graph = analysis.get('call_graph') or {}
    edges = call_graph.get('edges') or []
    adjacency: Dict[str, List[str]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get('source') or edge.get('sourceId') or edge.get('caller') or '').strip()
        target = str(edge.get('target') or edge.get('targetId') or edge.get('callee') or '').strip()
        if not source or not target:
            continue
        adjacency.setdefault(source, []).append(target)

    enriched: List[Dict[str, Any]] = []
    for index, entry in enumerate(entry_points[:max_paths]):
        if not isinstance(entry, dict):
            continue
        method_sig = str(entry.get('method_signature') or '').strip()
        if not method_sig:
            continue
        path = [method_sig]
        direct_callees = adjacency.get(method_sig) or []
        if direct_callees:
            path.append(direct_callees[0])

        resolved = _resolve_method_or_function_from_report(report, method_sig)
        cfg_payload = _generate_cfg_dfg_io(resolved['info']) if resolved else {
            'cfg': None,
            'dfg': None,
            'io': {'inputs': [], 'outputs': [], 'global_reads': [], 'global_writes': []},
        }

        enriched.append({
            'path_id': f'{partition_id}_entry_{index}',
            'leaf_node': path[-1],
            'function_chain': path,
            'path_index': index,
            'path': path,
            'worthiness_score': round(max(0.5, 0.82 - index * 0.07), 2),
            'worthiness_reasons': ['基于入口点与真实方法CFG/DFG生成的按需增强路径'],
            'deep_analysis_status': 'entrypoint_enriched',
            'path_name': f'入口增强路径 {index + 1}',
            'path_description': '基于入口点即时补齐的功能路径详情，适用于原始深路径不足的分区。',
            'cfg': cfg_payload.get('cfg'),
            'dfg': cfg_payload.get('dfg'),
            'io_graph': None,
            'highlight_config': {
                'call_chain_type': 'entry_point_enriched',
                'main_method': method_sig,
                'intermediate_methods': path[1:-1],
                'path_methods': path,
                'explanation': '该路径来自入口点补强，并附带真实方法级 CFG/DFG。',
            },
        })

    if not enriched:
        return [], {}

    return enriched, {
        'selection_policy': 'entry_point_enriched_fallback',
        'selected_count': len(enriched),
        'deferred_count': 0,
        'total_candidates': len(enriched),
        'completion_status': 'partial_enriched',
    }


def _select_best_phase6_hierarchy_payload(project_path: str, hierarchy_cached: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    normalized_project_path = os.path.normpath(project_path)
    layer_cache_payload = data_accessor.get_function_hierarchy_layer_cache(normalized_project_path) or {}
    layers = layer_cache_payload.get('layers') or {}
    advanced_snapshot = ((layers.get('advanced_visible') or {}).get('snapshot'))
    cached_final_result = layer_cache_payload.get('final_result')
    candidates = [hierarchy_cached, cached_final_result, advanced_snapshot]
    best_payload = None
    best_richness = -1
    for candidate in candidates:
        richness = _measure_hierarchy_path_richness(candidate)
        if richness > best_richness:
            best_payload = candidate
            best_richness = richness
    return best_payload if isinstance(best_payload, dict) else hierarchy_cached


def api_get_phase6_read_contract():
    """Stage1: 统一前端读契约，聚合 Phase2~5 的可消费数据面。"""
    project_path = request.args.get('project_path') or str(PROJECT_ROOT)
    normalized_project_path = os.path.normpath(project_path)

    hierarchy_cached = _resolve_function_hierarchy_cached(normalized_project_path)
    hierarchy_cached = _select_best_phase6_hierarchy_payload(normalized_project_path, hierarchy_cached)

    if hierarchy_cached and _measure_hierarchy_path_richness(hierarchy_cached) <= 0:
        try:
            data_accessor.delete_function_hierarchy(normalized_project_path)
            data_accessor.delete_function_hierarchy_layer_cache(normalized_project_path)
            analyze_function_hierarchy(normalized_project_path)
            hierarchy_cached = _resolve_function_hierarchy_cached(normalized_project_path)
            hierarchy_cached = _select_best_phase6_hierarchy_payload(normalized_project_path, hierarchy_cached)
        except Exception as exc:
            print(f"[api_get_phase6_read_contract] ⚠️ 稀疏层级结果补跑失败: {exc}", flush=True)

    if not hierarchy_cached:
        current_data = analysis_status.get('data')
        if isinstance(current_data, dict) and current_data.get('partition_analyses'):
            hierarchy_cached = current_data

    if not hierarchy_cached:
        return jsonify({'error': '未找到可用于 Stage1 读契约的功能层级结果'}), 404

    contract_payload = _build_phase6_read_contract(normalized_project_path, hierarchy_cached)
    if not contract_payload:
        return jsonify({'error': 'Stage1 读契约构建失败'}), 500

    return jsonify(contract_payload)


def _resolve_process_shadow_payload(normalized_project_path: str) -> Optional[Dict[str, Any]]:
    cached = data_accessor.get_process_shadow(normalized_project_path)
    if isinstance(cached, dict):
        return cached

    hierarchy_cached = data_accessor.get_function_hierarchy(normalized_project_path)
    if isinstance(hierarchy_cached, dict) and isinstance(hierarchy_cached.get('process_shadow'), dict):
        return hierarchy_cached['process_shadow']

    storage_payload = ProcessShadowStorage().load(normalized_project_path)
    if isinstance(storage_payload, dict):
        return storage_payload

    current_data = analysis_status.get('data')
    if isinstance(current_data, dict) and isinstance(current_data.get('process_shadow'), dict):
        return current_data['process_shadow']

    return None


def api_get_process_shadow():
    """获取 Phase3 的影子 Process 结果。"""
    project_path = request.args.get('project_path')
    if not project_path:
        project_path = str(PROJECT_ROOT)

    normalized_project_path = os.path.normpath(project_path)
    payload = _resolve_process_shadow_payload(normalized_project_path)
    if payload is None:
        return jsonify({'error': '未找到 Phase3 影子结果'}), 404
    return jsonify(payload)


def api_get_processes_compat():
    """兼容旧版前端 `/api/processes`：返回 process_shadow 中的流程列表。"""
    project_path = request.args.get('project_path') or request.args.get('repo') or str(PROJECT_ROOT)
    normalized_project_path = os.path.normpath(project_path)
    payload = _resolve_process_shadow_payload(normalized_project_path)
    if payload is None:
        return jsonify({'error': '未找到 Phase3 影子结果'}), 404

    processes_raw = payload.get('processes')
    processes: List[Dict[str, Any]] = [item for item in processes_raw if isinstance(item, dict)] if isinstance(processes_raw, list) else []
    return jsonify({
        'processes': processes,
        'count': len(processes),
        'project_path': normalized_project_path,
    })


def api_get_process_compat():
    """兼容旧版前端 `/api/process`：按 name/id 返回单个流程详情。"""
    project_path = request.args.get('project_path') or request.args.get('repo') or str(PROJECT_ROOT)
    process_name = str(request.args.get('name') or request.args.get('id') or '').strip()
    if not process_name:
        return jsonify({'error': '缺少 name 参数'}), 400

    normalized_project_path = os.path.normpath(project_path)
    payload = _resolve_process_shadow_payload(normalized_project_path)
    if payload is None:
        return jsonify({'error': '未找到 Phase3 影子结果'}), 404

    processes_raw = payload.get('processes')
    processes: List[Dict[str, Any]] = [item for item in processes_raw if isinstance(item, dict)] if isinstance(processes_raw, list) else []
    normalized_name = process_name.lower()
    for process in processes:
        candidates = [
            str(process.get('process_id') or '').strip(),
            str(process.get('entry') or '').strip(),
            str(process.get('entry_node_id') or '').strip(),
        ]
        if any(candidate and candidate.lower() == normalized_name for candidate in candidates):
            return jsonify(process)

    return jsonify({'error': f'未找到流程: {process_name}'}), 404


def api_get_entry_points_shadow():
    """获取 Phase4 的入口点评分影子结果。"""
    project_path = request.args.get('project_path') or str(PROJECT_ROOT)
    normalized_project_path = os.path.normpath(project_path)

    threshold_override = request.args.get('threshold')
    parsed_threshold = None
    if threshold_override is not None:
        try:
            parsed_threshold = max(0.0, min(float(threshold_override), 1.0))
        except (TypeError, ValueError):
            parsed_threshold = None

    hierarchy_cached = data_accessor.get_function_hierarchy(normalized_project_path)
    payload = None
    if hierarchy_cached:
        payload = hierarchy_cached.get('entry_points_shadow')

    current_data = analysis_status.get('data')
    if payload is None and current_data:
        payload = current_data.get('entry_points_shadow')

    if payload is None:
        return jsonify({'error': '未找到 Phase4 影子结果'}), 404

    filtered_payload = filter_entry_points_shadow(payload, parsed_threshold)
    return jsonify(filtered_payload)


def api_get_community_shadow():
    """获取 Phase5 的社区检测影子结果。"""
    project_path = request.args.get('project_path') or str(PROJECT_ROOT)
    normalized_project_path = os.path.normpath(project_path)

    payload = data_accessor.get_community_shadow(normalized_project_path)

    hierarchy_cached = data_accessor.get_function_hierarchy(normalized_project_path)
    if payload is None and hierarchy_cached:
        payload = hierarchy_cached.get('community_shadow')

    if payload is None:
        storage_payload = CommunityShadowStorage().load(normalized_project_path)
        if storage_payload:
            payload = storage_payload

    current_data = analysis_status.get('data')
    if payload is None and current_data:
        payload = current_data.get('community_shadow')

    if payload is None:
        return jsonify({'error': '未找到 Phase5 影子结果'}), 404

    return jsonify(payload)


def api_knowledge_graph():
    """获取知识图谱数据"""
    try:
        # 获取最新的分析结果
        if not analysis_status['data']:
            return jsonify({'error': '请先运行分析'}), 400
        
        # 从分析结果构建知识图谱数据
        report = analysis_status.get('report')  # 需要保存report
        
        if not report:
            # 如果没有report，尝试从data构建
            return jsonify({'error': '分析数据不完整'}), 400
        
        knowledge_data = build_knowledge_graph_data(report)
        return jsonify(knowledge_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_cfg_dfg(entity_id):
    """获取指定实体的CFG和DFG"""
    try:
        project_path = _resolve_runtime_project_path(request.args.get('project_path'))
        report = _resolve_report_cached(project_path)
        if not report:
            return jsonify({'error': '请先运行分析'}), 400

        resolved = _resolve_method_or_function_from_report(report, entity_id)
        if not resolved:
            return jsonify({'cfg': None, 'dfg': None})

        payload = _generate_cfg_dfg_io(resolved['info'])
        return jsonify(payload)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_node_detail(entity_id):
    """Phase 4: 获取统一节点详情（源码 + CFG/DFG + 输入输出）。"""
    try:
        project_path = _resolve_runtime_project_path(request.args.get('project_path'))
        report = _resolve_report_cached(project_path)
        node_data = _resolve_graph_node_data(project_path, entity_id) or {}

        node_kind = str(node_data.get('type') or 'unknown')
        display_name = str(node_data.get('label') or node_data.get('name') or entity_id)
        file_path = node_data.get('file') or node_data.get('file_path')
        line_start = node_data.get('line')
        line_end = None
        source_code = None
        cfg_payload = {
            'cfg': None,
            'cfg_json': None,
            'dfg': None,
            'dfg_json': None,
            'io': {
                'inputs': [],
                'outputs': [],
                'global_reads': [],
                'global_writes': [],
            },
        }

        if report:
            resolved_method = _resolve_method_or_function_from_report(report, entity_id)
            if resolved_method:
                info = resolved_method['info']
                node_kind = resolved_method['kind']
                display_name = getattr(info, 'name', None) or entity_id
                source_code = getattr(info, 'source_code', None)
                if info.source_location:
                    file_path = info.source_location.file_path
                    line_start = info.source_location.line_start
                    line_end = info.source_location.line_end
                cfg_payload = _generate_cfg_dfg_io(info)
            else:
                resolved_class = _resolve_class_from_report(report, entity_id)
                if resolved_class:
                    node_kind = 'class'
                    display_name = resolved_class.name
                    if resolved_class.source_location:
                        file_path = resolved_class.source_location.file_path
                        line_start = resolved_class.source_location.line_start
                        line_end = resolved_class.source_location.line_end

        source_payload = _build_source_payload(
            project_path,
            source_code=source_code,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
        )

        return jsonify({
            'entity_id': entity_id,
            'kind': node_kind,
            'display_name': display_name,
            'file_path': source_payload.get('file_path') or file_path,
            'line_start': source_payload.get('line_start') or line_start,
            'line_end': source_payload.get('line_end') or line_end,
            'source': source_payload,
            'cfg': cfg_payload.get('cfg'),
            'cfg_json': cfg_payload.get('cfg_json'),
            'dfg': cfg_payload.get('dfg'),
            'dfg_json': cfg_payload.get('dfg_json'),
            'io': cfg_payload.get('io'),
            'has_cfg': bool(cfg_payload.get('cfg')),
            'has_dfg': bool(cfg_payload.get('dfg')),
            'has_io': bool((cfg_payload.get('io') or {}).get('inputs') or (cfg_payload.get('io') or {}).get('outputs') or (cfg_payload.get('io') or {}).get('global_reads') or (cfg_payload.get('io') or {}).get('global_writes')),
        })
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


def api_partition_analysis(partition_id):
    """获取功能分区的分析结果（调用图、超图、入口点、数据流图、控制流图、FQN、输入输出）"""
    try:
        # 优先从功能层级缓存获取数据
        project_path = request.args.get('project_path')
        if not project_path:
            project_path = str(PROJECT_ROOT)
        
        # 标准化路径（处理Windows路径的反斜杠）
        project_path = os.path.normpath(project_path)
        
        data = None
        
        # 1. 优先从功能层级缓存获取（通过DataAccessor）
        hierarchy_cached = _resolve_function_hierarchy_cached(project_path)
        data = _select_best_phase6_hierarchy_payload(project_path, hierarchy_cached)
        if data:
            print(f"[api_partition_analysis] ✅ 从功能层级缓存获取数据: {project_path}", flush=True)
        
        # 2. 如果缓存中没有，从当前分析状态获取
        if not data:
            data = analysis_status.get('data')
            if data:
                print(f"[api_partition_analysis] ✅ 从当前分析状态获取数据", flush=True)
        
        if not data:
            return jsonify({'error': '请先运行功能层级分析或四层分析'}), 400
        
        # 支持两种数据结构：
        # 1. 功能层级分析：data['partition_analyses']
        # 2. 四层分析：data['partition_analyses']
        partition_analyses = data.get('partition_analyses', {})
        if partition_id not in partition_analyses:
            print(f"[api_partition_analysis] ❌ 分区 {partition_id} 不存在，可用分区: {list(partition_analyses.keys())}", flush=True)
            return jsonify({'error': f'分区 {partition_id} 的分析结果不存在'}), 404
        
        # 返回该分区的所有分析结果（包括调用图、超图、入口点、数据流图、控制流图、FQN、输入输出等）
        partition_data = partition_analyses[partition_id]
        
        # 检查io_graph数据是否存在
        hierarchy_functions = data.get('hierarchy', {}).get('layer1_functions', [])
        partition_meta = next((item for item in hierarchy_functions if item.get('partition_id') == partition_id), {}) if isinstance(hierarchy_functions, list) else {}
        path_analyses, path_info = _get_partition_path_payload(partition_data, partition_methods=partition_meta.get('methods', []))
        if (path_info.get('selection_policy') == 'lightweight_fallback'):
            enriched_paths, enriched_info = _build_entrypoint_enriched_path_payload(
                project_path,
                partition_id,
                partition_data,
            )
            if enriched_paths:
                path_analyses = enriched_paths
                path_info = enriched_info
        partition_data = dict(partition_data)
        partition_data['path_analyses'] = path_analyses
        partition_data['path_analysis_info'] = path_info
        io_graph_count = sum(1 for pa in path_analyses if pa.get('io_graph'))
        print(f"[api_partition_analysis] 分区 {partition_id} 返回数据检查:", flush=True)
        print(f"[api_partition_analysis]   - path_analyses数量: {len(path_analyses)}", flush=True)
        print(f"[api_partition_analysis]   - 有io_graph的路径: {io_graph_count} 条", flush=True)
        if io_graph_count > 0:
            # 显示第一个有io_graph的路径信息
            for pa in path_analyses:
                if pa.get('io_graph'):
                    io_graph = pa['io_graph']
                    print(f"[api_partition_analysis]   - 示例路径(leaf={pa['leaf_node']}, path_index={pa['path_index']}): io_graph有nodes={len(io_graph.get('nodes', []))}, edges={len(io_graph.get('edges', []))}", flush=True)
                    break
        
        return jsonify(partition_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_partition_call_graph(partition_id):
    """获取功能分区的调用图"""
    try:
        # 优先从功能层级缓存获取数据
        project_path = request.args.get('project_path')
        if not project_path:
            project_path = str(PROJECT_ROOT)
        
        # 标准化路径
        project_path = os.path.normpath(project_path)
        
        data = None
        
        # 1. 优先从功能层级缓存获取（通过DataAccessor）
        data = data_accessor.get_function_hierarchy(project_path)
        
        # 2. 如果缓存中没有，从当前分析状态获取
        if not data:
            data = analysis_status.get('data')
        
        if not data:
            return jsonify({'error': '请先运行功能层级分析或四层分析'}), 400
        
        partition_analyses = data.get('partition_analyses', {})
        if partition_id not in partition_analyses:
            return jsonify({'error': f'分区 {partition_id} 的分析结果不存在'}), 404
        
        call_graph = partition_analyses[partition_id].get('call_graph')
        if not call_graph:
            return jsonify({'error': '调用图不存在'}), 404
        
        return jsonify(call_graph)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_partition_hypergraph(partition_id):
    """获取功能分区的超图"""
    try:
        # 优先从功能层级缓存获取数据
        project_path = request.args.get('project_path')
        if not project_path:
            project_path = str(PROJECT_ROOT)
        
        # 标准化路径
        project_path = os.path.normpath(project_path)
        
        data = None
        
        # 1. 优先从功能层级缓存获取（通过DataAccessor）
        data = data_accessor.get_function_hierarchy(project_path)
        
        # 2. 如果缓存中没有，从当前分析状态获取
        if not data:
            data = analysis_status.get('data')
        
        if not data:
            return jsonify({'error': '请先运行功能层级分析或四层分析'}), 400
        
        partition_analyses = data.get('partition_analyses', {})
        if partition_id not in partition_analyses:
            return jsonify({'error': f'分区 {partition_id} 的分析结果不存在'}), 404
        
        hypergraph = partition_analyses[partition_id].get('hypergraph')
        if not hypergraph:
            return jsonify({'error': '超图不存在'}), 404
        
        return jsonify(hypergraph)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_partition_entry_points(partition_id):
    """获取功能分区的入口点"""
    try:
        data = analysis_status.get('data')
        if not data:
            return jsonify({'error': '请先运行四层分析'}), 400
        
        partition_analyses = data.get('partition_analyses', {})
        if partition_id not in partition_analyses:
            return jsonify({'error': f'分区 {partition_id} 的分析结果不存在'}), 404
        
        entry_points = partition_analyses[partition_id].get('entry_points', [])
        return jsonify({'entry_points': entry_points})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_partition_dataflow(partition_id):
    """获取功能分区的数据流图"""
    try:
        data = analysis_status.get('data')
        if not data:
            return jsonify({'error': '请先运行四层分析'}), 400
        
        partition_analyses = data.get('partition_analyses', {})
        if partition_id not in partition_analyses:
            return jsonify({'error': f'分区 {partition_id} 的分析结果不存在'}), 404
        
        dataflow = partition_analyses[partition_id].get('dataflow')
        if not dataflow:
            return jsonify({'error': '数据流图不存在'}), 404
        
        return jsonify(dataflow)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_partition_controlflow(partition_id):
    """获取功能分区的控制流图"""
    try:
        data = analysis_status.get('data')
        if not data:
            return jsonify({'error': '请先运行四层分析'}), 400
        
        partition_analyses = data.get('partition_analyses', {})
        if partition_id not in partition_analyses:
            return jsonify({'error': f'分区 {partition_id} 的分析结果不存在'}), 404
        
        controlflow = partition_analyses[partition_id].get('controlflow')
        if not controlflow:
            return jsonify({'error': '控制流图不存在'}), 404
        
        return jsonify(controlflow)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_search_hybrid_shadow():
    """Phase2 shadow API: run bm25/semantic/hybrid search over cached graph nodes."""
    try:
        payload = request.json or {}
        query = str(payload.get('query', '')).strip()
        if not query:
            return jsonify({'error': 'query 不能为空'}), 400

        requested_top_k = payload.get('top_k', 10)
        try:
            top_k = int(requested_top_k)
        except (TypeError, ValueError):
            top_k = 10
        top_k = max(1, min(top_k, 50))

        project_path = payload.get('project_path') or request.args.get('project_path') or str(PROJECT_ROOT)
        normalized_project_path = os.path.normpath(project_path)

        graph_data = data_accessor.get_main_analysis(normalized_project_path)
        if not graph_data:
            current_data = analysis_status.get('data')
            if current_data and current_data.get('nodes') and current_data.get('edges'):
                graph_data = current_data

        if not graph_data:
            return jsonify({'error': '未找到主分析结果，请先执行 /api/analyze'}), 400

        raw_phase2b_flag = payload.get('enable_phase2b')
        if raw_phase2b_flag is None:
            raw_phase2b_flag = request.args.get('enable_phase2b')
        if raw_phase2b_flag is None:
            raw_phase2b_flag = os.getenv('FH_PHASE2B_ENABLE', '1')

        normalized_flag = str(raw_phase2b_flag).strip().lower()
        enable_phase2b = normalized_flag not in {'0', 'false', 'off', 'no'}

        shadow_result = run_hybrid_shadow(
            graph_data=graph_data,
            query=query,
            top_k=top_k,
            enable_graph_context=enable_phase2b,
        )
        shadow_result['project_path'] = normalized_project_path
        return jsonify(shadow_result)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


def _resolve_graph_data_for_project(project_path: str, allow_global_fallback: bool = True) -> Optional[Dict[str, Any]]:
    project_path = _normalize_project_lookup_path(project_path)
    graph_data = _resolve_main_analysis_cached(project_path)
    if graph_data:
        return graph_data
    if not allow_global_fallback:
        return None
    current_data = analysis_status.get('data')
    if current_data and current_data.get('nodes') and current_data.get('edges'):
        return current_data
    return None



def _list_project_library_entries() -> List[Dict[str, Any]]:
    entries: Dict[str, Dict[str, Any]] = {}
    try:
        for item in _project_library_storage.list_projects():
            if not isinstance(item, dict):
                continue
            project_path = _normalize_project_lookup_path(item.get('project_path'))
            if not project_path:
                continue
            normalized = dict(item)
            normalized['project_path'] = project_path
            entries[project_path] = normalized
    except Exception:
        pass

    try:
        from data.experience_path_storage import ExperiencePathStorage

        storage = ExperiencePathStorage()
        for item in storage.list_all_projects() or []:
            if not isinstance(item, dict):
                continue
            project_path = _normalize_project_lookup_path(item.get('project_path'))
            if not project_path:
                continue
            current = entries.get(project_path, {})
            if not current:
                current = {
                    'project_path': project_path,
                    'project_name': str(item.get('project_name') or os.path.basename(project_path) or 'unknown_project'),
                    'display_name': '',
                    'analysis_timestamp': str(item.get('analysis_timestamp') or ''),
                    'updated_at': str(item.get('analysis_timestamp') or ''),
                    'has_graph': False,
                    'has_hierarchy': True,
                    'path_count': int(item.get('total_paths') or 0),
                }
            entries[project_path] = current
    except Exception:
        pass

    result = list(entries.values())
    result.sort(key=lambda payload: str(payload.get('updated_at') or payload.get('analysis_timestamp') or ''), reverse=True)
    return result


def _infer_repo_project_path(repo_name: Optional[str] = None) -> Optional[str]:
    cached_keys = [_normalize_project_lookup_path(path) for path in data_accessor.list_main_analysis_keys()]
    persisted_entries = _list_project_library_entries()
    persisted_paths = [_normalize_project_lookup_path(item.get('project_path')) for item in persisted_entries if item.get('project_path')]

    candidate_paths: List[str] = []
    for item in cached_keys + persisted_paths:
        if item and item not in candidate_paths:
            candidate_paths.append(item)

    if not candidate_paths:
        current_path = analysis_status.get('project_path')
        if current_path:
            return os.path.normpath(current_path)
        return None

    if not repo_name:
        current_path = analysis_status.get('project_path')
        if current_path:
            normalized_current = os.path.normpath(current_path)
            for candidate in candidate_paths:
                if os.path.normpath(candidate) == normalized_current:
                    return candidate
        return candidate_paths[0]

    normalized_repo = os.path.normpath(str(repo_name))
    repo_basename = os.path.basename(normalized_repo).lower()
    for candidate in candidate_paths:
        normalized_candidate = os.path.normpath(candidate)
        if normalized_candidate == normalized_repo:
            return candidate
        if os.path.basename(normalized_candidate).lower() == repo_basename:
            return candidate

    for item in persisted_entries:
        display_name = str(item.get('display_name') or '').lower()
        project_name = str(item.get('project_name') or '').lower()
        if repo_basename and (repo_basename in display_name or repo_basename in project_name):
            return _normalize_project_lookup_path(item.get('project_path'))
    return None


def _map_gn_node_label(raw_type: str) -> str:
    normalized = str(raw_type or '').strip().lower()
    mapping = {
        'project': 'Project',
        'package': 'Package',
        'module': 'Module',
        'folder': 'Folder',
        'file': 'File',
        'class': 'Class',
        'function': 'Function',
        'method': 'Method',
        'variable': 'Variable',
        'field': 'Variable',
        'interface': 'Interface',
        'enum': 'Enum',
        'type': 'Type',
        'community': 'Community',
        'process': 'Process',
    }
    return mapping.get(normalized, 'CodeElement')


def _map_gn_relationship_type(raw_relation: str) -> str:
    normalized = str(raw_relation or '').strip().lower()
    mapping = {
        'contains': 'CONTAINS',
        'calls': 'CALLS',
        'cross_file_call': 'CALLS',
        'inherits': 'INHERITS',
        'imports': 'IMPORTS',
        'accesses': 'USES',
        'uses': 'USES',
        'defines': 'DEFINES',
        'implements': 'IMPLEMENTS',
        'extends': 'EXTENDS',
        'member_of': 'MEMBER_OF',
        'step_in_process': 'STEP_IN_PROCESS',
    }
    return mapping.get(normalized, 'CALLS')


def _resolve_node_file_path(project_path: str, raw_path: str) -> str:
    if not raw_path:
        return ''
    normalized = os.path.normpath(raw_path)
    if os.path.isabs(normalized):
        return normalized
    return os.path.normpath(os.path.join(project_path, normalized))


def _read_file_text_for_graph(project_path: str, file_path: str) -> str:
    resolved_path = _resolve_node_file_path(project_path, file_path)
    if not resolved_path or not os.path.exists(resolved_path) or not os.path.isfile(resolved_path):
        return ''
    try:
        with open(resolved_path, 'r', encoding='utf-8', errors='replace') as handle:
            return handle.read()
    except Exception:
        return ''


def _convert_graph_data_to_gn_contract(project_path: str, graph_data: Dict[str, Any]) -> Dict[str, Any]:
    converted_nodes: List[Dict[str, Any]] = []
    converted_relationships: List[Dict[str, Any]] = []

    process_step_count_by_id: Dict[str, int] = {}
    process_step_max_by_id: Dict[str, int] = {}
    for edge in graph_data.get('edges', []) or []:
        data = edge.get('data', {})
        source_id = str(data.get('source') or '')
        target_id = str(data.get('target') or '')
        if not source_id or not target_id:
            continue
        rel_type = _map_gn_relationship_type(data.get('relation') or data.get('type'))
        if rel_type != 'STEP_IN_PROCESS':
            continue
        process_step_count_by_id[target_id] = int(process_step_count_by_id.get(target_id) or 0) + 1
        step_raw = data.get('step')
        if isinstance(step_raw, (int, float)):
            step_value = int(step_raw)
            previous_max = int(process_step_max_by_id.get(target_id) or 0)
            if step_value > previous_max:
                process_step_max_by_id[target_id] = step_value

    for node in graph_data.get('nodes', []) or []:
        data = node.get('data', {})
        node_id = str(data.get('id') or data.get('name') or data.get('label') or '')
        if not node_id:
            continue

        raw_file_path = str(data.get('file') or data.get('file_path') or '')
        resolved_file_path = _resolve_node_file_path(project_path, raw_file_path) if raw_file_path else ''
        start_line_raw = data.get('line') or data.get('startLine') or data.get('line_start')
        end_line_raw = data.get('endLine') or data.get('line_end')
        start_line = int(start_line_raw) if isinstance(start_line_raw, (int, float)) else None
        end_line = int(end_line_raw) if isinstance(end_line_raw, (int, float)) else None
        label = _map_gn_node_label(data.get('type'))
        properties: Dict[str, Any] = {
            'name': str(data.get('label') or data.get('name') or node_id),
            'filePath': resolved_file_path,
        }
        if start_line:
            properties['startLine'] = start_line
        if end_line:
            properties['endLine'] = end_line
        if resolved_file_path:
            properties['language'] = _guess_language(resolved_file_path)
        if label == 'File' and resolved_file_path:
            properties['content'] = _read_file_text_for_graph(project_path, resolved_file_path)

        if label == 'Community':
            heuristic_label = str(data.get('heuristicLabel') or data.get('heuristic_label') or '').strip()
            if heuristic_label:
                properties['heuristicLabel'] = heuristic_label
            symbol_count_raw = data.get('symbolCount') if data.get('symbolCount') is not None else data.get('symbol_count')
            if isinstance(symbol_count_raw, (int, float)):
                properties['symbolCount'] = int(symbol_count_raw)

        if label == 'Process':
            process_type = str(data.get('processType') or data.get('process_type') or '').strip()
            if process_type:
                properties['processType'] = process_type

            communities_raw = data.get('communities')
            if isinstance(communities_raw, list):
                communities = [str(item).strip() for item in communities_raw if str(item).strip()]
                if communities:
                    properties['communities'] = communities

            step_count_raw = data.get('stepCount') if data.get('stepCount') is not None else data.get('step_count')
            computed_step_count = 0
            if isinstance(step_count_raw, (int, float)):
                computed_step_count = int(step_count_raw)
            else:
                computed_step_count = int(process_step_max_by_id.get(node_id) or process_step_count_by_id.get(node_id) or 0)
            properties['stepCount'] = computed_step_count

            entry_point_id = str(data.get('entryPointId') or data.get('entry_point_id') or data.get('entry_point') or '').strip()
            if entry_point_id:
                properties['entryPointId'] = entry_point_id

            terminal_id = str(data.get('terminalId') or data.get('terminal_id') or '').strip()
            if terminal_id:
                properties['terminalId'] = terminal_id

        converted_nodes.append({
            'id': node_id,
            'label': label,
            'properties': properties,
        })

    for edge in graph_data.get('edges', []) or []:
        data = edge.get('data', {})
        source_id = str(data.get('source') or '')
        target_id = str(data.get('target') or '')
        if not source_id or not target_id:
            continue

        rel_type = _map_gn_relationship_type(data.get('relation') or data.get('type'))
        try:
            confidence = float(data.get('confidence', 1.0))
        except (TypeError, ValueError):
            confidence = 1.0

        converted_rel: Dict[str, Any] = {
            'id': str(data.get('id') or f"{source_id}->{target_id}:{rel_type}"),
            'sourceId': source_id,
            'targetId': target_id,
            'type': rel_type,
            'confidence': max(0.0, min(confidence, 1.0)),
            'reason': str(data.get('reason') or data.get('relation') or ''),
        }
        if rel_type == 'STEP_IN_PROCESS' and data.get('step') is not None:
            try:
                converted_rel['step'] = int(data.get('step'))
            except (TypeError, ValueError):
                pass
        converted_relationships.append(converted_rel)

    return {
        'nodes': converted_nodes,
        'relationships': converted_relationships,
    }


def _build_repo_stats(project_path: str, graph_data: Dict[str, Any]) -> Dict[str, int]:
    nodes = graph_data.get('nodes', []) or []
    edges = graph_data.get('edges', []) or []
    metadata = graph_data.get('metadata', {}) or {}

    file_count = int(metadata.get('total_files') or 0)
    if file_count <= 0:
        file_count = sum(1 for node in nodes if str((node.get('data') or {}).get('type', '')).lower() == 'file')

    hierarchy_cached = _resolve_function_hierarchy_cached(project_path)
    process_count = 0
    community_count = 0
    if hierarchy_cached:
        process_shadow = hierarchy_cached.get('process_shadow') or {}
        community_shadow = hierarchy_cached.get('community_shadow') or {}
        process_count = len(process_shadow.get('processes') or [])
        community_count = len(community_shadow.get('communities') or [])

    return {
        'files': file_count,
        'nodes': len(nodes),
        'edges': len(edges),
        'communities': community_count,
        'processes': process_count,
    }



def _build_project_display_name(project_path: str, partition_analyses: Optional[Dict[str, Any]] = None) -> str:
    base_name = os.path.basename(project_path) or '项目'
    payload = partition_analyses if isinstance(partition_analyses, dict) else {}
    if not payload:
        hierarchy_cached = _resolve_function_hierarchy_cached(project_path)
        payload = (hierarchy_cached or {}).get('partition_analyses') if isinstance(hierarchy_cached, dict) else {}
        if not isinstance(payload, dict):
            payload = {}

    labels: List[str] = []
    for partition in payload.values():
        if not isinstance(partition, dict):
            continue
        name = str(partition.get('partition_name') or partition.get('name') or '').strip()
        if name and name not in labels:
            labels.append(name)
        if len(labels) >= 2:
            break

    llm_name = ' / '.join(labels) if labels else base_name
    return f"{llm_name} · {project_path}"


def _build_repo_summary_payload(project_path: str) -> Optional[Dict[str, Any]]:
    graph_data = _resolve_graph_data_for_project(project_path)
    if not graph_data:
        return None

    metadata = graph_data.get('metadata', {}) or {}
    profile = _project_library_storage.load_project_profile(project_path) or {}
    repo_name = str(profile.get('project_name') or os.path.basename(project_path) or 'current_project')
    indexed_at = str(metadata.get('analysis_timestamp') or profile.get('analysis_timestamp') or datetime.utcnow().isoformat() + 'Z')
    last_commit = str(metadata.get('git_commit') or metadata.get('commit_hash') or '')
    stats = _build_repo_stats(project_path, graph_data)

    has_hierarchy = bool(profile.get('has_hierarchy')) or bool(_resolve_function_hierarchy_cached(project_path))
    path_count = int(profile.get('path_count') or 0)
    display_name = str(profile.get('display_name') or '').strip() or _build_project_display_name(project_path)

    return {
        'name': repo_name,
        'displayName': display_name,
        'path': project_path,
        'repoPath': project_path,
        'indexedAt': indexed_at,
        'lastCommit': last_commit,
        'stats': stats,
        'experienceLibrary': {
            'hasHierarchy': has_hierarchy,
            'pathCount': path_count,
            'status': 'ready' if has_hierarchy else 'building_or_missing',
        },
    }


def api_gn_repos():
    """GitNexus compatibility: list available repositories."""
    try:
        summaries: List[Dict[str, Any]] = []
        seen_paths: Set[str] = set()

        for project_path in data_accessor.list_main_analysis_keys():
            summary = _build_repo_summary_payload(project_path)
            if summary:
                normalized = _normalize_project_lookup_path(summary.get('path'))
                if normalized and normalized not in seen_paths:
                    seen_paths.add(normalized)
                    summaries.append(summary)

        for item in _list_project_library_entries():
            project_path = _normalize_project_lookup_path(item.get('project_path'))
            if not project_path or project_path in seen_paths:
                continue
            summary = _build_repo_summary_payload(project_path)
            if summary:
                seen_paths.add(project_path)
                summaries.append(summary)

        if not summaries:
            inferred = _infer_repo_project_path()
            if inferred:
                summary = _build_repo_summary_payload(inferred)
                if summary:
                    summaries.append(summary)

        return jsonify(summaries)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


def api_gn_repo():
    """GitNexus compatibility: fetch single repository info."""
    try:
        repo_name = request.args.get('repo')
        project_path = _infer_repo_project_path(repo_name)
        if not project_path:
            return jsonify({'error': '未找到可用仓库，请先执行分析'}), 404

        summary = _build_repo_summary_payload(project_path)
        if not summary:
            return jsonify({'error': '未找到可用仓库，请先执行分析'}), 404
        return jsonify(summary)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


def api_gn_graph():
    """GitNexus compatibility: fetch graph nodes/relationships."""
    try:
        repo_name = request.args.get('repo')
        project_path = _infer_repo_project_path(repo_name)
        if not project_path:
            return jsonify({'error': '未找到可用图数据，请先执行分析'}), 404

        graph_data = _resolve_graph_data_for_project(project_path)
        if not graph_data:
            return jsonify({'error': '未找到可用图数据，请先执行分析'}), 404

        payload = _convert_graph_data_to_gn_contract(project_path, graph_data)
        return jsonify(payload)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


def api_gn_file():
    """GitNexus compatibility: fetch file content by path."""
    try:
        repo_name = request.args.get('repo')
        requested_path = str(request.args.get('path') or '').strip()
        if not requested_path:
            return jsonify({'error': 'path 不能为空'}), 400

        project_path = _infer_repo_project_path(repo_name)
        if not project_path:
            return jsonify({'error': '未找到可用仓库，请先执行分析'}), 404

        resolved_path = _resolve_node_file_path(project_path, requested_path)
        if not resolved_path or not os.path.exists(resolved_path) or not os.path.isfile(resolved_path):
            return jsonify({'error': f'文件不存在: {requested_path}'}), 404

        try:
            with open(resolved_path, 'r', encoding='utf-8', errors='replace') as handle:
                content = handle.read()
        except Exception as exc:
            return jsonify({'error': f'读取文件失败: {exc}'}), 500

        return Response(content, mimetype='text/plain; charset=utf-8')
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


def _summary_matches_node_signature(summary: Dict[str, Any], candidate_values: List[str]) -> bool:
    methods = [str(item) for item in (summary.get('methods') or []) if item]
    if not methods:
        return False
    for candidate in candidate_values:
        for method in methods:
            if candidate == method or method.endswith(f'.{candidate}') or candidate.endswith(f'.{method}'):
                return True
    return False


def _resolve_partition_summary_for_rag(contract_payload: Optional[Dict[str, Any]], selected_node: Dict[str, Any], requested_partition_id: str) -> Optional[Dict[str, Any]]:
    if not contract_payload:
        return None

    summaries = ((contract_payload.get('adapters') or {}).get('partition_summaries') or [])
    if not summaries:
        return None

    if requested_partition_id:
        for item in summaries:
            if str(item.get('partition_id') or '') == requested_partition_id:
                return item

    candidate_values = [
        selected_node.get('id'),
        selected_node.get('name'),
        selected_node.get('label'),
        selected_node.get('signature'),
        selected_node.get('method_signature'),
        selected_node.get('fqmn'),
    ]
    normalized_candidates = [str(value) for value in candidate_values if value]
    if not normalized_candidates:
        return None

    for summary in summaries:
        if _summary_matches_node_signature(summary, normalized_candidates):
            return summary
    return None


def _format_rag_answer(query: str, selected_node: Dict[str, Any], partition_summary: Optional[Dict[str, Any]], evidence: List[Dict[str, Any]]) -> str:
    lines = [f"问题：{query}"]

    node_label = selected_node.get('label') or selected_node.get('name') or selected_node.get('id')
    node_type = selected_node.get('type')
    if node_label:
        if node_type:
            lines.append(f"当前节点：{node_label}（{node_type}）")
        else:
            lines.append(f"当前节点：{node_label}")

    if partition_summary:
        lines.append(
            "当前功能分区：{}（Path {}，Process {}，Community {}）".format(
                partition_summary.get('name') or partition_summary.get('partition_id') or '未知分区',
                partition_summary.get('path_count') or 0,
                partition_summary.get('process_count') or 0,
                partition_summary.get('community_count') or 0,
            )
        )
        if partition_summary.get('description'):
            lines.append(f"分区语义：{partition_summary.get('description')}")

    if evidence:
        lines.append("证据命中（Top）：")
        for index, hit in enumerate(evidence[:3], start=1):
            hit_label = hit.get('label') or hit.get('node_id') or 'unknown'
            file_path = hit.get('file_path') or '未知文件'
            lines.append(f"{index}. {hit_label} @ {file_path}")
        lines.append("建议：先沿 Top 证据节点阅读源码与调用关系，再结合右侧功能层级抽屉核对分区语义。")
    else:
        lines.append("当前没有命中明显证据，请尝试更具体的问题（如方法名、类名、业务词）。")

    return "\n".join(lines)


def _stringify_rag_graph_context(graph_context: Any) -> List[str]:
    items = graph_context if isinstance(graph_context, list) else [graph_context]
    lines: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        partition_id = str(item.get('partition_id') or '').strip()
        partition_name = str(item.get('partition_name') or '').strip()
        path_name = str(item.get('path_name') or '').strip()
        process_name = str(item.get('process_name') or '').strip()
        detail = ' / '.join(part for part in [partition_name or partition_id, path_name, process_name] if part)
        if detail and detail not in lines:
            lines.append(detail)
    return lines


def _build_rag_context_chunks(
    query: str,
    selected_node: Dict[str, Any],
    partition_summary: Optional[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []

    node_label = selected_node.get('label') or selected_node.get('name') or selected_node.get('id')
    node_type = selected_node.get('type') or ''
    if node_label:
        chunks.append({
            'text': f"当前用户聚焦节点：{node_label}" + (f"（{node_type}）" if node_type else ''),
            'metadata': {
                'question': query,
                'answer': f"当前上下文节点：{node_label}",
                'label': node_label,
                'type': node_type,
                'file_path': selected_node.get('file_path') or '',
            },
        })

    if partition_summary:
        partition_name = partition_summary.get('name') or partition_summary.get('partition_id') or '未知分区'
        partition_description = str(partition_summary.get('description') or '').strip()
        partition_text = (
            f"功能分区：{partition_name}\n"
            f"Path 数：{partition_summary.get('path_count') or 0}\n"
            f"Process 数：{partition_summary.get('process_count') or 0}\n"
            f"Community 数：{partition_summary.get('community_count') or 0}"
        )
        if partition_description:
            partition_text += f"\n分区语义：{partition_description}"
        chunks.append({
            'text': partition_text,
            'metadata': {
                'question': query,
                'answer': partition_description or partition_name,
                'partition_id': partition_summary.get('partition_id') or '',
                'partition_name': partition_name,
            },
        })

    for index, hit in enumerate(evidence, start=1):
        label = hit.get('label') or hit.get('node_id') or f'evidence_{index}'
        file_path = hit.get('file_path') or '未知文件'
        graph_context_lines = _stringify_rag_graph_context(hit.get('graph_context') or [])
        text_lines = [
            f"证据 {index}：{label}",
            f"文件：{file_path}",
            f"得分：{hit.get('score')}",
        ]
        if graph_context_lines:
            text_lines.append("图上下文：" + '；'.join(graph_context_lines))
        chunks.append({
            'text': "\n".join(text_lines),
            'metadata': {
                'question': label,
                'answer': f"命中文件：{file_path}",
                'label': label,
                'file_path': file_path,
                'score': hit.get('score'),
            },
        })

    if not chunks:
        chunks.append({
            'text': '当前检索未命中明确证据，请基于用户问题给出谨慎回答，并明确说明缺少仓库证据时不要臆测代码细节。',
            'metadata': {
                'question': query,
                'answer': '暂无显式检索证据',
            },
        })

    return chunks


def _generate_rag_answer_with_llm(
    query: str,
    selected_node: Dict[str, Any],
    partition_summary: Optional[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
) -> Tuple[str, str, Optional[str]]:
    fallback_answer = _format_rag_answer(query, selected_node, partition_summary, evidence)
    if not has_deepseek_config():
        return fallback_answer, 'template_fallback', None

    llm_client = _create_deepseek_api_client()
    if llm_client is None:
        return fallback_answer, 'template_fallback', None

    try:
        answer = llm_client.generate_answer(
            query=query,
            context_chunks=_build_rag_context_chunks(query, selected_node, partition_summary, evidence[:8]),
            system_prompt=(
                '你是 create_graph 的代码仓库问答助手。请优先基于给定检索证据、功能分区语义和当前选中节点回答。'
                '如果证据不足，要明确说明不确定性，不要编造不存在的代码实现。'
                '对于问候或轻量聊天，也请自然回复，但不要虚构仓库事实。'
            ),
            temperature=RAG_CONFIG.get('temperature', 0.7),
            max_tokens=RAG_CONFIG.get('max_tokens', 1000),
            timeout=90,
        )
    except Exception as exc:
        return fallback_answer, 'template_fallback', str(exc)

    normalized_answer = str(answer).strip()
    if not normalized_answer:
        return fallback_answer, 'template_fallback', 'DeepSeek 返回了空响应，已退回模板答案'
    return normalized_answer, 'deepseek_grounded_generation', None


def _build_rag_output_protocol(
    answer: str,
    evidence: List[Dict[str, Any]],
    generation_mode: str,
    generation_error: Optional[str],
) -> Dict[str, Any]:
    impacted_files: List[str] = []
    for hit in evidence:
        file_path = str(hit.get('file_path') or '').strip()
        if file_path and file_path not in impacted_files:
            impacted_files.append(file_path)

    reasons = [
        '回答优先基于检索证据与功能分区上下文生成',
        f'生成路径：{generation_mode}',
    ]
    if generation_error:
        reasons.append('DeepSeek 生成失败后回退到模板答案')

    remaining_risks = []
    if not evidence:
        remaining_risks.append('当前检索未命中高置信仓库证据，回答可能更偏向通用说明')
    if generation_error:
        remaining_risks.append(f'DeepSeek 调用失败：{generation_error}')

    return {
        'version': '1.0',
        'task_mode': 'general_chat',
        'judgment': {
            'status': 'ready',
            'confidence': 'medium' if evidence else 'low',
            'reasons': reasons,
        },
        'analysis': {
            'summary': answer,
            'key_reasoning': reasons,
            'impacted_files': impacted_files,
            'selected_path': {},
            'candidate_paths': [],
            'selection_mode': generation_mode,
            'selection_reason': 'rag_llm_answer' if generation_mode == 'deepseek_grounded_generation' else 'rag_template_fallback',
        },
        'code_snippets': [],
        'remaining_risks_constraints': remaining_risks,
        'constraints': [],
    }


def _to_feature_flag(raw_value: Any, default: bool = False) -> bool:
    if raw_value is None:
        return bool(default)
    normalized = str(raw_value).strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    return bool(default)


def _is_rag_conversation_bridge_enabled(payload: Dict[str, Any]) -> bool:
    explicit = payload.get('use_conversation_core')
    if explicit is not None:
        return _to_feature_flag(explicit, default=True)
    env_flag = os.getenv('FH_RAG_ASK_CONVERSATION_BRIDGE', '1')
    return _to_feature_flag(env_flag, default=True)


def _legacy_rag_ask_deprecation_info() -> Dict[str, Any]:
    return {
        'deprecated': True,
        'replacement': {
            'start': '/api/conversations/session/start',
            'status': '/api/conversations/session/<session_id>/status',
            'result': '/api/conversations/session/<session_id>/result',
            'reply': '/api/conversations/<conversation_id>/reply',
            'events': '/api/conversations/<conversation_id>/events',
        },
        'notice': 'rag/ask 已进入兼容模式，请迁移到 conversations API。',
    }


def _is_legacy_rag_ask_enabled() -> bool:
    env_flag = os.getenv('FH_ENABLE_LEGACY_RAG_ASK', '1')
    return _to_feature_flag(env_flag, default=True)


def _run_rag_ask_via_conversation_core(
    *,
    query: str,
    project_path: str,
    selected_node: Dict[str, Any],
    requested_partition_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    from app.services import conversation_service as cs

    conversation_id = str(payload.get('conversation_id') or '').strip() or uuid4().hex
    clarification_context_raw = payload.get('clarification_context')
    clarification_context = clarification_context_raw if isinstance(clarification_context_raw, dict) else {}

    forced_action_raw = str(payload.get('bridge_force_action') or '').strip()
    forced_action = forced_action_raw if forced_action_raw in {'clarify', 'general_chat', 'run_retrieval', 'start_multi_agent'} else None

    session_payload = cs._create_conversation_session(
        project_path=project_path,
        user_query=query,
        conversation_id=conversation_id,
        clarification_context=clarification_context,
    )

    cs._run_conversation_turn(
        session_id=str(session_payload.get('sessionId') or ''),
        project_path=project_path,
        user_query=query,
        conversation_id=conversation_id,
        selected_node=selected_node,
        partition_id=requested_partition_id or None,
        clarification_context=clarification_context,
        reply_payload=None,
        auto_start_multi_agent=False,
        force_action=forced_action,
        force_fallback_clarification=False,
    )

    timeout_ms_raw = payload.get('bridge_timeout_ms')
    timeout_ms = int(timeout_ms_raw) if isinstance(timeout_ms_raw, (int, float)) else 60000
    timeout_ms = max(3000, min(timeout_ms, 120000))
    deadline = time.time() + (timeout_ms / 1000.0)

    latest_status: Dict[str, Any] = {}
    while time.time() < deadline:
        latest_status = cs.data_accessor.get_conversation_session(str(session_payload.get('sessionId') or '')) or {}
        status = str(latest_status.get('status') or '').strip()
        if status in {'completed', 'failed'}:
            break
        time.sleep(0.2)

    status = str(latest_status.get('status') or '').strip()
    if status != 'completed':
        error_message = str(latest_status.get('error') or f'conversation core timeout/status={status or "unknown"}')
        raise RuntimeError(error_message)

    result = latest_status.get('result') if isinstance(latest_status.get('result'), dict) else {}
    answer = str(result.get('answer') or result.get('reason') or '').strip()

    pending_question = result.get('pendingQuestion') if isinstance(result.get('pendingQuestion'), dict) else None
    if pending_question and not answer:
        answer = str(pending_question.get('question') or '需要进一步澄清需求').strip()

    retrieval = result.get('retrieval') if isinstance(result.get('retrieval'), dict) else {}
    highlights = retrieval.get('highlights') if isinstance(retrieval.get('highlights'), list) else []
    evidence: List[Dict[str, Any]] = []
    for idx, item in enumerate(highlights[:20]):
        if not isinstance(item, dict):
            continue
        graph_context = item.get('graph_context') if isinstance(item.get('graph_context'), list) else None
        if not isinstance(graph_context, list):
            graph_context = item.get('sources') if isinstance(item.get('sources'), list) else []
        evidence.append(
            {
                'rank': idx + 1,
                'node_id': item.get('id'),
                'label': item.get('label') or item.get('id'),
                'file_path': item.get('file') or '',
                'source': 'conversation_retrieval_tool',
                'score': item.get('score'),
                'line_start': item.get('lineStart') if item.get('lineStart') is not None else item.get('line_start'),
                'line_end': item.get('lineEnd') if item.get('lineEnd') is not None else item.get('line_end'),
                'snippet': item.get('snippet'),
                'graph_context': graph_context,
            }
        )

    generation_mode = 'conversation_core_bridge'
    if pending_question:
        generation_mode = 'conversation_core_clarification'

    output_protocol = _build_rag_output_protocol(
        answer=answer,
        evidence=evidence,
        generation_mode=generation_mode,
        generation_error=None,
    )
    if pending_question and isinstance(output_protocol.get('judgment'), dict):
        output_protocol['judgment']['status'] = 'needs_refinement'
        reasons = output_protocol['judgment'].get('reasons') if isinstance(output_protocol['judgment'].get('reasons'), list) else []
        reasons.append('需要用户先完成需求澄清')
        output_protocol['judgment']['reasons'] = reasons

    return {
        'query': query,
        'answer': answer,
        'project_path': project_path,
        'selected_node': selected_node,
        'partition': {},
        'evidence': evidence,
        'retrieval_bundle': {
            'evidence': evidence,
            'highlights': highlights,
        },
        'output_protocol': output_protocol,
        'generation': {
            'mode': generation_mode,
            'used_llm': True,
            'error': None,
        },
        'search': {
            'stats': {'highlights_count': len(highlights)},
            'comparison': {},
            'phase2b': {},
            'grouped_by_process': [],
        },
        'index_rebuild_status': {},
        'conversation': {
            'conversationId': conversation_id,
            'sessionId': session_payload.get('sessionId'),
            'nextStep': result.get('nextStep'),
            'pendingQuestion': pending_question,
        },
        'bridge': {
            'mode': 'conversation_core',
            'force_action': forced_action or 'auto',
            'fallback': False,
        },
    }


def api_rag_ask():
    """Phase 6: RAG 抽屉问答接口（上下文注入 + 证据返回）。"""
    try:
        if not _is_legacy_rag_ask_enabled():
            response = jsonify(
                {
                    'error': 'rag/ask 已停用，请改用 conversations API',
                    'legacy': _legacy_rag_ask_deprecation_info(),
                }
            )
            response.headers['X-CreateGraph-Legacy-API'] = 'rag/ask'
            response.headers['X-CreateGraph-Replacement-API'] = '/api/conversations/session/start'
            response.status_code = 410
            return response

        payload = request.json or {}
        query = str(payload.get('query') or '').strip()
        if not query:
            return jsonify({'error': 'query 不能为空'}), 400

        requested_top_k = payload.get('top_k', 8)
        try:
            top_k = int(requested_top_k)
        except (TypeError, ValueError):
            top_k = 8
        top_k = max(1, min(top_k, 20))

        raw_project_path = payload.get('project_path') or request.args.get('project_path')
        project_path = _resolve_runtime_project_path(raw_project_path, allow_global_fallback=False)
        if not project_path:
            return jsonify({'error': 'project_path 不能为空，且必须显式指定目标项目'}), 400
        graph_data = _resolve_graph_data_for_project(project_path, allow_global_fallback=False)

        raw_selected_node = payload.get('selected_node')
        selected_node: Dict[str, Any] = raw_selected_node if isinstance(raw_selected_node, dict) else {}
        requested_partition_id = str(payload.get('partition_id') or '').strip()

        bridge_warning: Optional[str] = None
        if _is_rag_conversation_bridge_enabled(payload):
            try:
                bridge_response = _run_rag_ask_via_conversation_core(
                    query=query,
                    project_path=project_path,
                    selected_node=selected_node,
                    requested_partition_id=requested_partition_id,
                    payload=payload,
                )
                bridge_response['legacy'] = _legacy_rag_ask_deprecation_info()
                response = jsonify(bridge_response)
                response.headers['X-CreateGraph-Legacy-API'] = 'rag/ask'
                response.headers['X-CreateGraph-Replacement-API'] = '/api/conversations/session/start'
                return response
            except Exception as bridge_exc:
                bridge_warning = str(bridge_exc)

        shadow_result = run_hybrid_shadow(
            graph_data=graph_data,
            query=query,
            top_k=top_k,
            enable_graph_context=True,
        ) if graph_data else {'flat_hits': []}

        flat_hits = shadow_result.get('flat_hits') or []
        evidence: List[Dict[str, Any]] = []
        for item in flat_hits[:top_k]:
            evidence.append({
                'rank': item.get('rank'),
                'node_id': item.get('node_id'),
                'label': item.get('label'),
                'file_path': item.get('file_path'),
                'source': item.get('source'),
                'score': item.get('score'),
                'graph_context': item.get('graph_context') or [],
            })

        hierarchy_cached = _resolve_function_hierarchy_cached(project_path)
        hierarchy_cached = _select_best_phase6_hierarchy_payload(project_path, hierarchy_cached)
        contract_payload = _build_phase6_read_contract(project_path, hierarchy_cached) if hierarchy_cached else None
        partition_summary = _resolve_partition_summary_for_rag(
            contract_payload=contract_payload,
            selected_node=selected_node,
            requested_partition_id=requested_partition_id,
        )

        answer, generation_mode, generation_error = _generate_rag_answer_with_llm(
            query=query,
            selected_node=selected_node,
            partition_summary=partition_summary,
            evidence=evidence,
        )

        output_protocol = _build_rag_output_protocol(
            answer=answer,
            evidence=evidence,
            generation_mode=generation_mode,
            generation_error=generation_error,
        )

        index_rebuild_status = (hierarchy_cached or {}).get('index_rebuild_status') or {}

        response_payload = {
            'query': query,
            'answer': answer,
            'project_path': project_path,
            'selected_node': selected_node,
            'partition': partition_summary,
            'evidence': evidence,
            'retrieval_bundle': {
                'evidence': evidence,
            },
            'output_protocol': output_protocol,
            'generation': {
                'mode': generation_mode,
                'used_llm': generation_mode == 'deepseek_grounded_generation',
                'error': generation_error,
            },
            'search': {
                'stats': shadow_result.get('stats') or {},
                'comparison': shadow_result.get('comparison') or {},
                'phase2b': shadow_result.get('phase2b') or {},
                'grouped_by_process': shadow_result.get('grouped_by_process') or [],
            },
            'index_rebuild_status': index_rebuild_status,
            'bridge': {
                'mode': 'legacy_fallback' if bridge_warning else 'legacy',
                'fallback': bool(bridge_warning),
                'error': bridge_warning,
            },
            'legacy': _legacy_rag_ask_deprecation_info(),
        }
        response = jsonify(response_payload)
        response.headers['X-CreateGraph-Legacy-API'] = 'rag/ask'
        response.headers['X-CreateGraph-Replacement-API'] = '/api/conversations/session/start'
        return response
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


def build_knowledge_graph_data(report: ProjectAnalysisReport) -> dict:
    """从ProjectAnalysisReport构建知识图谱数据（增强版：包含CFG、DFG、参数、返回值等实体）"""
    knowledge_data = {
        'repository': None,
        'packages': [],
        'classes': [],
        'methods': [],
        'functions': [],
        'parameters': [],  # 新增：参数实体列表
        'return_values': [],  # 新增：返回值实体列表
        'cfgs': [],  # 新增：CFG实体列表
        'dfgs': [],  # 新增：DFG实体列表
        'edges': []  # 新增：关系边列表
    }
    
    # 初始化CFG和DFG生成器
    cfg_generator = CFGGenerator()
    dfg_generator = DFGGenerator()
    io_extractor = IOExtractor()
    
    # 构建仓库信息
    if report.repository:
        knowledge_data['repository'] = {
            'id': f"repository_{report.repository.name}",
            'name': report.repository.name,
            'path': report.repository.path,
            'description': report.repository.description,
            'type': 'repository'
        }
    else:
        # 如果没有repository，从project_name创建
        knowledge_data['repository'] = {
            'id': f"repository_{report.project_name}",
            'name': report.project_name,
            'path': report.project_path,
            'description': f"代码仓库: {report.project_name}",
            'type': 'repository'
        }
    
    # 构建包信息（从文件路径推断）
    packages_map = {}
    for class_info in report.classes.values():
        if class_info.source_location:
            file_path = class_info.source_location.file_path
            # 提取包路径（去掉文件名）
            package_path = os.path.dirname(file_path)
            package_name = os.path.basename(package_path) or 'root'
            
            if package_path not in packages_map:
                packages_map[package_path] = {
                    'id': f"package_{package_name}",
                    'name': package_name,
                    'path': package_path,
                    'type': 'package',
                    'classes': []
                }
                # 添加仓库到包的包含关系边
                knowledge_data['edges'].append({
                    'id': f"edge_repo_{knowledge_data['repository']['id']}_package_{package_name}",
                    'source': knowledge_data['repository']['id'],
                    'target': f"package_{package_name}",
                    'type': 'repository_contains_package',
                    'label': '包含'
                })
    
    # 构建类信息
    for class_info in report.classes.values():
        class_id = f"class_{class_info.full_name}"
        class_data = {
            'id': class_id,
            'name': class_info.name,
            'full_name': class_info.full_name,
            'type': 'class',
            'methods': [],
            'fields': []
        }
        
        # 添加方法
        for method in class_info.methods.values():
            method_id = f"method_{method.get_full_name()}"
            method_data = {
                'id': method_id,
                'name': method.name,
                'signature': method.signature,
                'type': 'method',
                'parameters': [{'name': p.name, 'type': p.param_type} for p in method.parameters],
                'file_path': method.source_location.file_path if method.source_location else '',
                'source_code': method.source_code or ''
            }
            class_data['methods'].append(method_data)
            
            # 添加类包含方法的关系边
            knowledge_data['edges'].append({
                'id': f"edge_{class_id}_contains_{method_id}",
                'source': class_id,
                'target': method_id,
                'type': 'class_contains_method',
                'label': '包含'
            })
            
            # 为每个参数创建独立实体
            for idx, param in enumerate(method.parameters):
                param_id = f"parameter_{method_id}_{param.name}"
                param_entity = {
                    'id': param_id,
                    'name': param.name,
                    'type': param.param_type,
                    'entity_type': 'parameter',
                    'default_value': param.default_value,
                    'position': idx,
                    'owner_method': method_id
                }
                knowledge_data['parameters'].append(param_entity)
                
                # 添加方法包含参数的关系边
                knowledge_data['edges'].append({
                    'id': f"edge_{method_id}_contains_{param_id}",
                    'source': method_id,
                    'target': param_id,
                    'type': 'method_contains_parameter',
                    'label': '包含参数'
                })
            
            # 创建返回值实体
            if method.return_type and method.return_type != 'None':
                return_id = f"return_{method_id}"
                return_entity = {
                    'id': return_id,
                    'return_type': method.return_type,
                    'entity_type': 'return_value',
                    'owner_method': method_id
                }
                knowledge_data['return_values'].append(return_entity)
                
                # 添加方法拥有返回值的关系边
                knowledge_data['edges'].append({
                    'id': f"edge_{method_id}_has_return_{return_id}",
                    'source': method_id,
                    'target': return_id,
                    'type': 'method_has_return',
                    'label': '返回'
                })
            
            # 生成CFG和DFG（如果方法有源代码）
            if method.source_code:
                try:
                    # 生成CFG
                    cfg = cfg_generator.generate_cfg(method.source_code, method.name)
                    if cfg.nodes:
                        cfg_id = f"cfg_{method_id}"
                        cfg_entity = {
                            'id': cfg_id,
                            'method_id': method_id,
                            'method_name': method.name,
                            'entity_type': 'cfg',
                            'node_count': len(cfg.nodes),
                            'edge_count': len(cfg.edges),
                            'dot_format': cfg.to_dot(),
                            'json_format': cfg.to_json()
                        }
                        knowledge_data['cfgs'].append(cfg_entity)
                        
                        # 添加方法拥有CFG的关系边
                        knowledge_data['edges'].append({
                            'id': f"edge_{method_id}_has_cfg_{cfg_id}",
                            'source': method_id,
                            'target': cfg_id,
                            'type': 'method_has_cfg',
                            'label': '拥有CFG'
                        })
                    
                    # 生成DFG
                    dfg = dfg_generator.generate_dfg(method.source_code, method.name)
                    if dfg.nodes:
                        dfg_id = f"dfg_{method_id}"
                        dfg_entity = {
                            'id': dfg_id,
                            'method_id': method_id,
                            'method_name': method.name,
                            'entity_type': 'dfg',
                            'node_count': len(dfg.nodes),
                            'edge_count': len(dfg.edges),
                            'dot_format': dfg.to_dot(),
                            'json_format': dfg.to_json()
                        }
                        knowledge_data['dfgs'].append(dfg_entity)
                        
                        # 添加方法拥有DFG的关系边
                        knowledge_data['edges'].append({
                            'id': f"edge_{method_id}_has_dfg_{dfg_id}",
                            'source': method_id,
                            'target': dfg_id,
                            'type': 'method_has_dfg',
                            'label': '拥有DFG'
                        })
                except Exception as e:
                    print(f"[app.py] ⚠️ 生成 {method_id} 的CFG/DFG失败: {e}", flush=True)
        
        # 添加字段
        for field in class_info.fields.values():
            field_id = f"field_{class_info.full_name}.{field.name}"
            field_data = {
                'id': field_id,
                'name': field.name,
                'type': field.field_type,
                'entity_type': 'field'
            }
            class_data['fields'].append(field_data)
            
            # 添加类包含字段的关系边
            knowledge_data['edges'].append({
                'id': f"edge_{class_id}_contains_{field_id}",
                'source': class_id,
                'target': field_id,
                'type': 'class_contains_field',
                'label': '包含字段'
            })
        
        # 将类添加到对应的包
        if class_info.source_location:
            file_path = class_info.source_location.file_path
            package_path = os.path.dirname(file_path)
            package_id = None
            if package_path in packages_map:
                package_id = packages_map[package_path]['id']
                packages_map[package_path]['classes'].append(class_data)
            else:
                # 如果没有包，添加到根包
                if 'root' not in packages_map:
                    packages_map['root'] = {
                        'id': 'package_root',
                        'name': 'root',
                        'path': '',
                        'type': 'package',
                        'classes': []
                    }
                package_id = 'package_root'
                packages_map['root']['classes'].append(class_data)
            
            # 添加包包含类的关系边
            if package_id:
                knowledge_data['edges'].append({
                    'id': f"edge_{package_id}_contains_{class_id}",
                    'source': package_id,
                    'target': class_id,
                    'type': 'package_contains_class',
                    'label': '包含'
                })
    
    # 构建函数信息
    for func in report.functions:
        func_id = f"function_{func.name}"
        func_data = {
            'id': func_id,
            'name': func.name,
            'signature': func.signature,
            'type': 'function',
            'parameters': [{'name': p.name, 'type': p.param_type} for p in func.parameters],
            'file_path': func.source_location.file_path if func.source_location else '',
            'source_code': func.source_code or ''
        }
        knowledge_data['functions'].append(func_data)
        
        # 为每个参数创建独立实体
        for idx, param in enumerate(func.parameters):
            param_id = f"parameter_{func_id}_{param.name}"
            param_entity = {
                'id': param_id,
                'name': param.name,
                'type': param.param_type,
                'entity_type': 'parameter',
                'default_value': param.default_value,
                'position': idx,
                'owner_method': func_id
            }
            knowledge_data['parameters'].append(param_entity)
            
            # 添加函数包含参数的关系边
            knowledge_data['edges'].append({
                'id': f"edge_{func_id}_contains_{param_id}",
                'source': func_id,
                'target': param_id,
                'type': 'function_contains_parameter',
                'label': '包含参数'
            })
        
        # 创建返回值实体
        if func.return_type and func.return_type != 'None':
            return_id = f"return_{func_id}"
            return_entity = {
                'id': return_id,
                'return_type': func.return_type,
                'entity_type': 'return_value',
                'owner_method': func_id
            }
            knowledge_data['return_values'].append(return_entity)
            
            # 添加函数拥有返回值的关系边
            knowledge_data['edges'].append({
                'id': f"edge_{func_id}_has_return_{return_id}",
                'source': func_id,
                'target': return_id,
                'type': 'function_has_return',
                'label': '返回'
            })
        
        # 生成CFG和DFG（如果函数有源代码）
        if func.source_code:
            try:
                # 生成CFG
                cfg = cfg_generator.generate_cfg(func.source_code, func.name)
                if cfg.nodes:
                    cfg_id = f"cfg_{func_id}"
                    cfg_entity = {
                        'id': cfg_id,
                        'method_id': func_id,
                        'method_name': func.name,
                        'entity_type': 'cfg',
                        'node_count': len(cfg.nodes),
                        'edge_count': len(cfg.edges),
                        'dot_format': cfg.to_dot(),
                        'json_format': cfg.to_json()
                    }
                    knowledge_data['cfgs'].append(cfg_entity)
                    
                    # 添加函数拥有CFG的关系边
                    knowledge_data['edges'].append({
                        'id': f"edge_{func_id}_has_cfg_{cfg_id}",
                        'source': func_id,
                        'target': cfg_id,
                        'type': 'function_has_cfg',
                        'label': '拥有CFG'
                    })
                
                # 生成DFG
                dfg = dfg_generator.generate_dfg(func.source_code, func.name)
                if dfg.nodes:
                    dfg_id = f"dfg_{func_id}"
                    dfg_entity = {
                        'id': dfg_id,
                        'method_id': func_id,
                        'method_name': func.name,
                        'entity_type': 'dfg',
                        'node_count': len(dfg.nodes),
                        'edge_count': len(dfg.edges),
                        'dot_format': dfg.to_dot(),
                        'json_format': dfg.to_json()
                    }
                    knowledge_data['dfgs'].append(dfg_entity)
                    
                    # 添加函数拥有DFG的关系边
                    knowledge_data['edges'].append({
                        'id': f"edge_{func_id}_has_dfg_{dfg_id}",
                        'source': func_id,
                        'target': dfg_id,
                        'type': 'function_has_dfg',
                        'label': '拥有DFG'
                    })
            except Exception as e:
                print(f"[app.py] ⚠️ 生成 {func_id} 的CFG/DFG失败: {e}", flush=True)
    
    knowledge_data['packages'] = list(packages_map.values())
    
    return knowledge_data


if __name__ == '__main__':
    # 该模块为 service/业务逻辑层，不再直接启动 Flask。
    # 请运行项目根目录的 app.py。
    print("[analysis_service] This module is not executable. Run `python app.py` instead.")
