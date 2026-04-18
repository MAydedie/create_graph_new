#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""create_graph 内部三省六部最小编排服务。"""

from __future__ import annotations

import copy
import io
import json
import logging
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
import re

from flask import jsonify, request

from app.services.codebase_retrieval_service import run_codebase_retrieval
import importlib
from app.services import analysis_service
from config.config import get_deepseek_settings, has_deepseek_config
from data.data_accessor import get_data_accessor
from data.project_library_storage import ProjectLibraryStorage
from llm.agent.core.task_session import TaskSession
from llm.agent.utils.question_detector import QuestionDetector
from llm.rag_core.llm_api import DeepSeekAPI

data_accessor = get_data_accessor()
project_library_storage = ProjectLibraryStorage()

STAGE_SEQUENCE = ['taizi', 'zhongshu', 'menxia', 'shangshu']
STAGE_LABELS = {
    'taizi': '太子：识别任务意图',
    'zhongshu': '中书省：准备统一分析与检索',
    'menxia': '门下省：审议检索证据',
    'shangshu': '尚书省：汇总分析与代码片段',
    'done': '三省六部会话完成',
    'failed': '三省六部会话失败',
}

FAST_RAG_ENV = {
    'FH_ENABLE_ADVANCED_VISIBLE_LAYER': '1',
    'FH_ENABLE_PARTITION_LLM_SEMANTICS': '1',
    'FH_ENABLE_PATH_LLM_ANALYSIS': '1',
    'FH_ENABLE_PATH_SUPPLEMENT_GENERATION': '1',
    'FH_ENABLE_PATH_CFG_DFG_IO': '1',
    'FH_ENABLE_CFG_DFG_LLM_EXPLAIN': '1',
    'FH_INCLUDE_DEEP_ANALYSIS_IN_DEFAULT_RESULT': '1',
    'FH_PATH_ANALYSIS_PARTITION_LIMIT': '16',
    'FH_STRUCTURAL_PATH_PARTITION_LIMIT': '24',
    'FH_MAX_PATHS_PER_PARTITION': '10',
    'FH_PHASE5_TIMEOUT_SECONDS': '30',
    'FH_INDEX_REBUILD_MODE': 'deferred',
}

STOPWORDS = {
    'the', 'a', 'an', 'to', 'of', 'for', 'and', 'or', 'in', 'on', 'at', 'by', 'with',
    '请', '分析', '如何', '怎么', '这个', '那个', '一个', '进行', '相关', '代码', '功能', '路径', '问题',
}

ADVISOR_SIDECAR_ROOT = Path(__file__).resolve().parent.parent.parent / 'advisor_consultant_lab'
ADVISOR_RUNTIME_DIR = ADVISOR_SIDECAR_ROOT / 'runtime'
_ADVISOR_SIDECAR_LOCK = threading.Lock()

SWARM_AGENT_PROMPTS = {
    'taizi': (
        '你是太子Agent（任务定义官）。'
        '请基于用户目标与澄清上下文，输出结构化的任务定义结论。'
        '你必须只输出 JSON。'
    ),
    'zhongshu': (
        '你是中书Agent（证据组织官）。'
        '请基于检索与路径摘要，输出主路径判断、证据充分度与下一步建议。'
        '你必须只输出 JSON。'
    ),
    'menxia': (
        '你是门下Agent（审议官）。'
        '请评估当前证据和方案是否可执行，识别风险并给出审议结论。'
        '你必须只输出 JSON。'
    ),
    'shangshu': (
        '你是尚书Agent（执行统筹官）。'
        '请基于方案包输出最终执行摘要、优先改动项和验证顺序。'
        '你必须只输出 JSON。'
    ),
}

ADVISOR_ROLE_PROFILE = {
    'role_id': 'advisor',
    'role_name': 'Advisor Sidecar',
    'role_tier': 'specialist',
    'quality_profile': 'omo_aligned',
    'invocation_mode': 'on_demand',
    'description': '按需提供经验约束与调用链建议，且不主导 opencode 主流程',
}


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat() + 'Z'


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _create_swarm_llm_client() -> Optional[DeepSeekAPI]:
    if not has_deepseek_config():
        return None
    settings = get_deepseek_settings()
    api_key = str(settings.get('api_key') or '').strip()
    if not api_key:
        return None
    try:
        return DeepSeekAPI(
            api_key=api_key,
            base_url=str(settings.get('base_url') or 'https://api.deepseek.com/v1').strip(),
            model=str(settings.get('model') or 'deepseek-chat').strip(),
            timeout=45,
        )
    except Exception:
        return None


def _extract_llm_text(response: Dict[str, Any]) -> str:
    if not isinstance(response, dict):
        return ''
    choices = response.get('choices')
    if not isinstance(choices, list) or not choices:
        return ''
    first = choices[0]
    if not isinstance(first, dict):
        return ''
    message = first.get('message')
    if not isinstance(message, dict):
        return ''
    return str(message.get('content') or '').strip()


def _run_opencode_kernel_bridge(**kwargs: Any) -> Dict[str, Any]:
    module = importlib.import_module('app.services.opencode_kernel_service')
    runner = getattr(module, 'run_opencode_kernel', None)
    if not callable(runner):
        return {
            'type': 'OpenCodeKernelResult',
            'status': 'error',
            'reason': 'opencode_kernel_service_missing_runner',
            'duration_ms': 0,
        }
    result = runner(**kwargs)
    if isinstance(result, dict):
        return result
    return {
        'type': 'OpenCodeKernelResult',
        'status': 'error',
        'reason': 'opencode_kernel_invalid_return',
        'duration_ms': 0,
    }


def _parse_json_object(raw_text: str) -> Dict[str, Any]:
    text = str(raw_text or '').strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        pass

    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return {}
    candidate = text[start:end + 1]
    try:
        payload = json.loads(candidate)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _is_advisor_sidecar_enabled(payload: Optional[Dict[str, Any]] = None) -> bool:
    explicit = None
    if isinstance(payload, dict):
        if 'advisor_enabled' in payload:
            explicit = payload.get('advisor_enabled')
        elif 'advisorEnabled' in payload:
            explicit = payload.get('advisorEnabled')
    if explicit is not None:
        return _to_feature_flag(explicit, default=True)
    env_flag = os.getenv('FH_ENABLE_ADVISOR_SIDECAR', '1')
    return _to_feature_flag(env_flag, default=True)


def _advisor_pipeline_timeout_seconds() -> int:
    raw_value = os.getenv('FH_ADVISOR_PIPELINE_TIMEOUT_SECONDS', '120')
    try:
        timeout = int(raw_value)
    except (TypeError, ValueError):
        timeout = 120
    return max(15, min(timeout, 600))


def _advisor_reuse_runtime_enabled() -> bool:
    return _to_feature_flag(os.getenv('FH_ADVISOR_REUSE_RUNTIME', '1'), default=True)


def _workbench_ready_timeout_seconds() -> int:
    raw_value = os.getenv('FH_WORKBENCH_READY_TIMEOUT_SECONDS', '120')
    try:
        timeout = int(raw_value)
    except (TypeError, ValueError):
        timeout = 120
    return max(15, min(timeout, 900))


def _is_opencode_kernel_enabled(payload: Optional[Dict[str, Any]] = None) -> bool:
    explicit = None
    if isinstance(payload, dict):
        if 'opencode_enabled' in payload:
            explicit = payload.get('opencode_enabled')
        elif 'opencodeEnabled' in payload:
            explicit = payload.get('opencodeEnabled')
    if explicit is not None:
        return _to_feature_flag(explicit, default=True)
    return _to_feature_flag(os.getenv('FH_ENABLE_OPENCODE_KERNEL', '1'), default=True)


def _opencode_kernel_timeout_seconds() -> int:
    raw_value = os.getenv('FH_OPENCODE_KERNEL_TIMEOUT_SECONDS', '150')
    try:
        timeout = int(raw_value)
    except (TypeError, ValueError):
        timeout = 150
    return max(30, min(timeout, 600))


def _opencode_kernel_model() -> str:
    return str(os.getenv('FH_OPENCODE_MODEL', '') or '').strip()


def _opencode_kernel_agent() -> str:
    return str(os.getenv('FH_OPENCODE_AGENT', 'build') or 'build').strip()


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_read_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_advisor_runtime_payloads() -> Dict[str, Dict[str, Any]]:
    return {
        'step1': _safe_read_json_file(ADVISOR_RUNTIME_DIR / 'step1_match_result.json'),
        'step2': _safe_read_json_file(ADVISOR_RUNTIME_DIR / 'step2_analysis.json'),
        'step3': _safe_read_json_file(ADVISOR_RUNTIME_DIR / 'step3_design.json'),
        'step4': _safe_read_json_file(ADVISOR_RUNTIME_DIR / 'step4_codegen.json'),
    }


def _extract_file_path_from_source_target(token: str) -> str:
    normalized = str(token or '').strip()
    if not normalized:
        return ''
    if ':' in normalized:
        candidate = normalized.split(':', 1)[0].strip()
        if candidate:
            normalized = candidate
    if '|' in normalized:
        normalized = normalized.split('|', 1)[0].strip()
    lowered = normalized.lower()
    if lowered.endswith(('.py', '.ts', '.tsx', '.js', '.jsx', '.java', '.go', '.rs', '.cpp', '.c', '.cs', '.md', '.json', '.yaml', '.yml', '.toml')):
        return normalized
    return ''


def _extract_advisor_impacted_files(source_targets: Any) -> List[str]:
    impacted: List[str] = []
    if not isinstance(source_targets, list):
        return impacted
    for item in source_targets:
        if not isinstance(item, dict):
            continue
        for raw_target in item.get('source_targets') or []:
            file_path = _extract_file_path_from_source_target(str(raw_target))
            if file_path and file_path not in impacted:
                impacted.append(file_path)
    return impacted


def _build_disabled_advisor_packet() -> Dict[str, Any]:
    return {
        'type': 'AdvisorPacket',
        'version': 'advisor.integration.v1',
        'enabled': False,
        'status': 'disabled',
        'reason': 'feature_disabled',
        'role': dict(ADVISOR_ROLE_PROFILE),
        'invocation': {
            'decision': 'disabled',
            'reason': 'feature_disabled',
            'signals': {},
        },
    }


def _build_skipped_advisor_packet(reason: str, signals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        'type': 'AdvisorPacket',
        'version': 'advisor.integration.v1',
        'enabled': True,
        'status': 'skipped',
        'mode': 'on_demand',
        'reason': reason,
        'role': dict(ADVISOR_ROLE_PROFILE),
        'invocation': {
            'decision': 'skipped',
            'reason': reason,
            'signals': dict(signals or {}),
        },
    }


def _normalize_prioritized_libraries(raw_value: Any) -> List[str]:
    items: List[str] = []
    if isinstance(raw_value, list):
        items = [str(item).strip() for item in raw_value]
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if text:
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                items = [str(item).strip() for item in parsed]
            else:
                items = [part.strip() for part in re.split(r'[,\n\r]+', text)]

    normalized: List[str] = []
    seen: set[str] = set()
    for item in items:
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _resolve_project_experience_output_root(project_path: str) -> Optional[str]:
    profile = project_library_storage.load_project_profile(project_path) or {}
    value = str(profile.get('experience_output_root') or '').strip()
    if not value or not os.path.isabs(value):
        return None
    return os.path.normpath(os.path.abspath(value))


def _resolve_advisor_experience_paths_dir(experience_output_root: Optional[str] = None) -> str:
    if experience_output_root:
        return str(Path(experience_output_root) / 'experience_paths')
    try:
        module = importlib.import_module('advisor_consultant_lab.config')
        configured = getattr(module, 'EXPERIENCE_PATHS_DIR', None)
        if configured:
            return str(configured)
    except Exception:
        pass
    fallback = ADVISOR_SIDECAR_ROOT.parent / 'output_analysis' / 'experience_paths'
    return str(fallback)


def _should_invoke_advisor(user_query: str, task_mode: str, retrieval_bundle: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    selected_path = _as_dict(retrieval_bundle.get('selected_path'))
    function_chain = [str(item).strip() for item in _as_list(selected_path.get('function_chain')) if str(item).strip()]
    node_details = [item for item in _as_list(retrieval_bundle.get('node_details')) if isinstance(item, dict)]
    candidate_paths = [item for item in _as_list(retrieval_bundle.get('candidate_paths')) if isinstance(item, dict)]
    impacted_files = [str(item).strip() for item in _as_list(retrieval_bundle.get('impacted_files')) if str(item).strip()]

    has_anchor = any(str(item.get('file_path') or '').strip() for item in node_details)
    has_path = len(function_chain) >= 2
    confidence = str(retrieval_bundle.get('confidence') or '').strip().lower() or 'low'
    selection_mode = str(retrieval_bundle.get('selection_mode') or '').strip().lower() or 'unknown'

    query_lower = str(user_query or '').lower()
    risk_markers = (
        '架构', 'architecture', '重构', 'refactor', '迁移', 'migration',
        '安全', 'security', '性能', 'performance', '并发', 'concurrency',
        '依赖', 'dependency', 'integrat', '设计', '方案', '调用链', 'call chain'
    )
    locator_markers = (
        '在哪', '在哪里', '位置', '哪个文件', '哪一行', 'where', 'which file', 'endpoint', '接口'
    )
    has_risk_marker = any(marker in query_lower for marker in risk_markers)
    is_locator_query = any(marker in query_lower for marker in locator_markers)

    signals = {
        'task_mode': str(task_mode or ''),
        'confidence': confidence,
        'selection_mode': selection_mode,
        'has_path': has_path,
        'has_anchor': has_anchor,
        'candidate_path_count': len(candidate_paths),
        'impacted_file_count': len(impacted_files),
        'risk_marker_hit': has_risk_marker,
        'locator_query_hit': is_locator_query,
    }

    if has_risk_marker:
        return True, 'high_risk_query', signals
    if is_locator_query and has_anchor and len(candidate_paths) >= 3:
        return False, 'locator_query_with_anchor', signals
    if not has_path:
        return True, 'missing_path_chain', signals
    if not has_anchor:
        return True, 'missing_source_anchor', signals
    if selection_mode != 'path_analyses':
        return True, 'fallback_selection_mode', signals
    if confidence not in {'high', 'medium'}:
        return True, 'low_confidence', signals
    if len(candidate_paths) <= 1:
        return True, 'insufficient_candidate_paths', signals

    if str(task_mode or '').strip() == 'write_new_code' and confidence == 'high':
        return False, 'high_confidence_write_new_code', signals
    if confidence == 'high' and len(impacted_files) >= 1 and len(candidate_paths) >= 2:
        return False, 'high_confidence_direct_path', signals
    return True, 'default_invoke', signals


def _build_advisor_packet_from_runtime(
    runtime_payloads: Dict[str, Dict[str, Any]],
    user_query: str,
    project_path: str,
    mode: str,
    experience_paths_dir: Optional[str] = None,
) -> Dict[str, Any]:
    step2 = _as_dict(runtime_payloads.get('step2'))
    step3 = _as_dict(runtime_payloads.get('step3'))
    step4 = _as_dict(runtime_payloads.get('step4'))

    analysis_result = _as_dict(step2.get('analysis_result'))
    match_summary = _as_dict(step2.get('match_summary'))
    top_advisor = _as_dict(match_summary.get('top_advisor'))
    source_targets = _as_list(step4.get('source_targets'))

    constraints_summary = _as_dict(step2.get('constraints_structured_summary'))
    constraints_structured = _as_dict(step2.get('constraints_structured'))

    recommended_partition = str(analysis_result.get('recommended_partition') or '').strip()
    recommended = {
        'advisor_id': str(top_advisor.get('advisor_id') or '').strip(),
        'advisor_name': str(top_advisor.get('advisor_name') or analysis_result.get('recommended_advisor') or '').strip(),
        'partition_id': recommended_partition,
        'project_path': project_path,
    }

    analysis = {
        'what': str(step2.get('what') or '').strip(),
        'how': str(step2.get('how') or '').strip(),
        'next_step': str(analysis_result.get('next_step') or '').strip(),
        'key_call_chain': [str(item).strip() for item in (analysis_result.get('key_call_chain') or []) if str(item).strip()],
        'key_code_refs': [str(item).strip() for item in (analysis_result.get('key_code_refs') or []) if str(item).strip()],
    }

    followup_raw = _as_list(analysis_result.get('selected_advisors_for_followup'))
    followup_advisors: List[Dict[str, Any]] = []
    for item in followup_raw:
            if not isinstance(item, dict):
                continue
            followup_advisors.append(
                {
                    'advisor_id': str(item.get('advisor_id') or '').strip(),
                    'advisor_name': str(item.get('advisor_name') or '').strip(),
                    'partition_id': str(item.get('partition_id') or '').strip(),
                    'fused_score': item.get('fused_score'),
                }
            )

    has_step2 = bool(step2)
    has_any = bool(step2 or step3 or step4)
    status = 'ready' if has_step2 else 'partial' if has_any else 'failed'

    return {
        'type': 'AdvisorPacket',
        'version': 'advisor.integration.v1',
        'enabled': True,
        'status': status,
        'mode': mode,
        'requirement': str(step2.get('requirement') or user_query).strip(),
        'recommended': recommended,
        'analysis': analysis,
        'constraints': {
            'plain': [str(item).strip() for item in _as_list(step2.get('constraints')) if str(item).strip()],
            'types': [str(item).strip() for item in _as_list(constraints_summary.get('types')) if str(item).strip()],
            'structured_summary': constraints_summary,
            'structured': constraints_structured,
        },
        'followup_advisors': followup_advisors,
        'source_targets': source_targets,
        'role': dict(ADVISOR_ROLE_PROFILE),
        'artifacts': {
            'runtime_dir': str(ADVISOR_RUNTIME_DIR),
            'step2_file': str(ADVISOR_RUNTIME_DIR / 'step2_analysis.json'),
            'step3_file': str(ADVISOR_RUNTIME_DIR / 'step3_design.json'),
            'step4_file': str(ADVISOR_RUNTIME_DIR / 'step4_codegen.json'),
            'experience_paths_dir': str(experience_paths_dir or _resolve_advisor_experience_paths_dir()),
        },
    }


def _run_advisor_sidecar(
    project_path: str,
    user_query: str,
    retrieval_bundle: Dict[str, Any],
    prioritized_libraries: Optional[List[str]] = None,
    experience_paths_dir: Optional[str] = None,
) -> Dict[str, Any]:
    if not ADVISOR_SIDECAR_ROOT.exists():
        return {
            'type': 'AdvisorPacket',
            'version': 'advisor.integration.v1',
            'enabled': False,
            'status': 'unavailable',
            'reason': f'advisor_sidecar_not_found: {ADVISOR_SIDECAR_ROOT}',
            'role': dict(ADVISOR_ROLE_PROFILE),
        }

    started_at = time.perf_counter()
    mode = 'pipeline_ran'
    diagnostics: Dict[str, Any] = {}

    with _ADVISOR_SIDECAR_LOCK:
        runtime_payloads = _read_advisor_runtime_payloads()
        cached_step2 = runtime_payloads.get('step2') or {}
        cached_requirement = str(cached_step2.get('requirement') or '').strip()
        effective_prioritized_libraries = [item for item in (prioritized_libraries or []) if str(item).strip()]
        if _advisor_reuse_runtime_enabled() and not effective_prioritized_libraries and cached_step2 and cached_requirement == str(user_query or '').strip():
            mode = 'cached_runtime'
            packet = _build_advisor_packet_from_runtime(runtime_payloads, user_query, project_path, mode, experience_paths_dir=experience_paths_dir)
            packet['telemetry'] = {
                'duration_ms': int((time.perf_counter() - started_at) * 1000),
                'reuse_runtime': True,
            }
            return packet

        task_input_file = ADVISOR_SIDECAR_ROOT / 'task_input.txt'
        task_input_file.write_text(str(user_query or '').strip(), encoding='utf-8')

        timeout_seconds = _advisor_pipeline_timeout_seconds()
        command = [sys.executable, str(ADVISOR_SIDECAR_ROOT / 'run_pipeline.py')]
        env = os.environ.copy()
        if experience_paths_dir:
            env['FH_EXPERIENCE_PATHS_DIR'] = str(experience_paths_dir)
        if effective_prioritized_libraries:
            env['FH_ADVISOR_PRIORITY_LIBRARIES'] = json.dumps(effective_prioritized_libraries, ensure_ascii=False)
        try:
            completed = subprocess.run(
                command,
                cwd=str(ADVISOR_SIDECAR_ROOT),
                env=env,
                check=False,
                timeout=timeout_seconds,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
            )
            diagnostics = {
                'returncode': completed.returncode,
                'stdout_tail': (completed.stdout or '')[-2000:],
                'stderr_tail': (completed.stderr or '')[-2000:],
            }
        except subprocess.TimeoutExpired:
            return {
                'type': 'AdvisorPacket',
                'version': 'advisor.integration.v1',
                'enabled': True,
                'status': 'timeout',
                'reason': f'advisor_pipeline_timeout_{timeout_seconds}s',
                'role': dict(ADVISOR_ROLE_PROFILE),
                'telemetry': {
                    'duration_ms': int((time.perf_counter() - started_at) * 1000),
                    'timeout_seconds': timeout_seconds,
                },
            }

        runtime_payloads = _read_advisor_runtime_payloads()
        packet = _build_advisor_packet_from_runtime(runtime_payloads, user_query, project_path, mode, experience_paths_dir=experience_paths_dir)
        packet['diagnostics'] = diagnostics
        packet['telemetry'] = {
            'duration_ms': int((time.perf_counter() - started_at) * 1000),
            'reuse_runtime': False,
            'selection_mode': retrieval_bundle.get('selection_mode'),
            'selection_reason': retrieval_bundle.get('selection_reason'),
            'prioritized_libraries_count': len(effective_prioritized_libraries),
            'experience_paths_dir': str(experience_paths_dir or ''),
        }
        if diagnostics.get('returncode') not in {None, 0} and packet.get('status') == 'failed':
            packet['status'] = 'error'
            packet['reason'] = f'advisor_pipeline_exit_{diagnostics.get("returncode")}'
        return packet


def _merge_advisor_context_into_analysis(analysis_payload: Dict[str, Any], advisor_packet: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(analysis_payload, dict):
        return analysis_payload
    if not isinstance(advisor_packet, dict):
        return analysis_payload

    status = str(advisor_packet.get('status') or '').strip().lower()
    if status not in {'ready', 'partial'}:
        analysis_payload['advisor'] = {
            'status': status or 'disabled',
            'enabled': bool(advisor_packet.get('enabled')),
            'reason': advisor_packet.get('reason'),
        }
        return analysis_payload

    advisor_analysis = _as_dict(advisor_packet.get('analysis'))
    advisor_constraints = _as_dict(advisor_packet.get('constraints'))
    recommended = _as_dict(advisor_packet.get('recommended'))

    key_reasoning = analysis_payload.get('key_reasoning')
    if not isinstance(key_reasoning, list):
        key_reasoning = []
        analysis_payload['key_reasoning'] = key_reasoning

    advisor_how = str(advisor_analysis.get('how') or '').strip()
    if advisor_how:
        advisor_line = f'顾问建议: {advisor_how}'
        if advisor_line not in key_reasoning:
            key_reasoning.append(advisor_line)

    advisor_files = _extract_advisor_impacted_files(advisor_packet.get('source_targets'))
    impacted_files = analysis_payload.get('impacted_files')
    if not isinstance(impacted_files, list):
        impacted_files = []
        analysis_payload['impacted_files'] = impacted_files
    for file_path in advisor_files:
        if file_path not in impacted_files:
            impacted_files.append(file_path)

    selected_path = analysis_payload.get('selected_path')
    advisor_chain_raw = _as_list(advisor_analysis.get('key_call_chain'))
    if (not isinstance(selected_path, dict) or not selected_path) and advisor_chain_raw:
        advisor_chain = [str(item).strip() for item in advisor_chain_raw if str(item).strip()]
        if advisor_chain:
            analysis_payload['selected_path'] = {
                'path_id': 'advisor_sidecar_path',
                'path_name': '顾问主路径',
                'path_description': str(advisor_analysis.get('what') or '').strip() or '由顾问侧车返回的主路径',
                'function_chain': advisor_chain,
                'path': advisor_chain,
                'deep_analysis_status': 'advisor_sidecar',
            }

    analysis_payload['advisor'] = {
        'status': status,
        'enabled': bool(advisor_packet.get('enabled')),
        'mode': advisor_packet.get('mode'),
        'recommended': recommended,
        'analysis': {
            'what': advisor_analysis.get('what'),
            'how': advisor_analysis.get('how'),
            'next_step': advisor_analysis.get('next_step'),
            'key_call_chain': _as_list(advisor_analysis.get('key_call_chain')),
            'key_code_refs': _as_list(advisor_analysis.get('key_code_refs')),
        },
        'constraints': {
            'plain': _as_list(advisor_constraints.get('plain')),
            'types': _as_list(advisor_constraints.get('types')),
            'structured_summary': _as_dict(advisor_constraints.get('structured_summary')),
            'structured': _as_dict(advisor_constraints.get('structured')),
        },
        'constraint_types': _as_list(advisor_constraints.get('types')),
        'source_targets': _as_list(advisor_packet.get('source_targets')),
        'followup_advisors': _as_list(advisor_packet.get('followup_advisors')),
    }
    return analysis_payload


def _summarize_retrieval_for_swarm(retrieval_bundle: Dict[str, Any]) -> Dict[str, Any]:
    selected_path_raw = retrieval_bundle.get('selected_path')
    selected_path: Dict[str, Any] = selected_path_raw if isinstance(selected_path_raw, dict) else {}
    candidate_paths_raw = retrieval_bundle.get('candidate_paths')
    candidate_paths: List[Any] = candidate_paths_raw if isinstance(candidate_paths_raw, list) else []
    impacted_files_raw = retrieval_bundle.get('impacted_files')
    impacted_files: List[Any] = impacted_files_raw if isinstance(impacted_files_raw, list) else []
    evidence_raw = retrieval_bundle.get('evidence')
    evidence: List[Any] = evidence_raw if isinstance(evidence_raw, list) else []

    path_chain_raw = selected_path.get('function_chain')
    path_chain: List[Any] = path_chain_raw if isinstance(path_chain_raw, list) else []
    candidate_preview: List[Dict[str, Any]] = []
    for item in candidate_paths[:5]:
        if not isinstance(item, dict):
            continue
        candidate_preview.append(
            {
                'path_id': item.get('path_id'),
                'path_name': item.get('path_name'),
                'selection_score': item.get('selection_score'),
                'worthiness_score': item.get('worthiness_score'),
            }
        )

    evidence_preview: List[Dict[str, Any]] = []
    for item in evidence[:6]:
        if not isinstance(item, dict):
            continue
        evidence_preview.append(
            {
                'label': item.get('label') or item.get('node_id') or item.get('id'),
                'file_path': item.get('file_path') or item.get('file'),
                'score': item.get('score'),
                'source': item.get('source'),
            }
        )

    return {
        'selected_partition_id': retrieval_bundle.get('selected_partition_id'),
        'selection_mode': retrieval_bundle.get('selection_mode'),
        'selection_reason': retrieval_bundle.get('selection_reason'),
        'confidence': retrieval_bundle.get('confidence'),
        'selected_path': {
            'path_id': selected_path.get('path_id'),
            'path_name': selected_path.get('path_name'),
            'path_description': selected_path.get('path_description'),
            'function_chain': path_chain[:12],
            'selection_score': selected_path.get('selection_score'),
        },
        'candidate_paths': candidate_preview,
        'impacted_files': [str(item) for item in impacted_files[:10]],
        'evidence_preview': evidence_preview,
    }


def _summarize_solution_for_swarm(solution_packet: Dict[str, Any]) -> Dict[str, Any]:
    analysis_raw = solution_packet.get('analysis')
    analysis: Dict[str, Any] = analysis_raw if isinstance(analysis_raw, dict) else {}
    edit_plan_raw = solution_packet.get('edit_plan')
    edit_plan: List[Any] = edit_plan_raw if isinstance(edit_plan_raw, list) else []
    snippet_blocks_raw = solution_packet.get('snippet_blocks')
    snippet_blocks: List[Any] = snippet_blocks_raw if isinstance(snippet_blocks_raw, list) else []
    output_protocol_raw = solution_packet.get('output_protocol')
    output_protocol: Dict[str, Any] = output_protocol_raw if isinstance(output_protocol_raw, dict) else {}

    edit_preview: List[Dict[str, Any]] = []
    for item in edit_plan[:8]:
        if not isinstance(item, dict):
            continue
        edit_preview.append(
            {
                'file_path': item.get('file_path'),
                'action': item.get('action'),
                'anchor': item.get('anchor'),
                'reason': item.get('reason'),
            }
        )

    return {
        'summary': analysis.get('summary'),
        'key_reasoning': analysis.get('key_reasoning') if isinstance(analysis.get('key_reasoning'), list) else [],
        'impacted_files': analysis.get('impacted_files') if isinstance(analysis.get('impacted_files'), list) else [],
        'edit_plan_preview': edit_preview,
        'snippet_block_count': len(snippet_blocks),
        'protocol_judgment': output_protocol.get('judgment') if isinstance(output_protocol.get('judgment'), dict) else {},
    }


def _fallback_swarm_output(agent_name: str, stage_payload: Dict[str, Any]) -> Dict[str, Any]:
    if agent_name == 'taizi':
        return {
            'agent': 'taizi',
            'summary': str(((stage_payload.get('review') if isinstance(stage_payload.get('review'), dict) else {}) or {}).get('clarified_target') or stage_payload.get('feature_scope') or '任务目标已整理'),
            'confidence': 'medium',
            'risks': [],
            'actions': ['继续进入证据准备阶段'],
            'status': 'fallback',
        }
    if agent_name == 'zhongshu':
        review_raw = stage_payload.get('review')
        review: Dict[str, Any] = review_raw if isinstance(review_raw, dict) else {}
        candidate_paths_raw = review.get('candidate_paths')
        candidate_paths: List[Any] = candidate_paths_raw if isinstance(candidate_paths_raw, list) else []
        return {
            'agent': 'zhongshu',
            'summary': f"证据已整理，候选路径 {len(candidate_paths)} 条",
            'confidence': str(((stage_payload.get('summary') if isinstance(stage_payload.get('summary'), dict) else {}) or {}).get('confidence') or 'medium'),
            'risks': [],
            'actions': ['进入证据审议'],
            'status': 'fallback',
        }
    if agent_name == 'menxia':
        return {
            'agent': 'menxia',
            'summary': f"审议结论：{stage_payload.get('verdict') or 'requery'}",
            'confidence': str(stage_payload.get('confidence') or 'medium'),
            'risks': [str(item) for item in (stage_payload.get('refinement_needed') or []) if str(item).strip()][:6],
            'actions': ['根据审议结果生成方案'],
            'status': 'fallback',
        }
    return {
        'agent': 'shangshu',
        'summary': str(((stage_payload.get('analysis') if isinstance(stage_payload.get('analysis'), dict) else {}) or {}).get('summary') or '执行方案已生成'),
        'confidence': 'medium',
        'risks': [str(item) for item in (stage_payload.get('validation') or []) if str(item).strip()][:6],
        'actions': ['输出最终方案给用户'],
        'status': 'fallback',
    }


def _run_swarm_agent_step(
    llm_client: Optional[DeepSeekAPI],
    agent_name: str,
    stage_payload: Dict[str, Any],
    shared_context: Dict[str, Any],
) -> Dict[str, Any]:
    if llm_client is None:
        return _fallback_swarm_output(agent_name, stage_payload)

    system_prompt = SWARM_AGENT_PROMPTS.get(agent_name) or SWARM_AGENT_PROMPTS['taizi']
    user_payload = {
        'agent': agent_name,
        'shared_context': shared_context,
        'stage_payload': stage_payload,
        'output_schema': {
            'summary': 'string',
            'confidence': 'high|medium|low',
            'risks': ['string'],
            'actions': ['string'],
        },
    }
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': json.dumps(user_payload, ensure_ascii=False)},
    ]
    try:
        response = llm_client.chat(messages=messages, temperature=0.15, max_tokens=700, timeout=35)
        text = _extract_llm_text(response)
        payload = _parse_json_object(text)
    except Exception:
        return _fallback_swarm_output(agent_name, stage_payload)

    if not isinstance(payload, dict):
        return _fallback_swarm_output(agent_name, stage_payload)

    summary = str(payload.get('summary') or '').strip()
    if not summary:
        return _fallback_swarm_output(agent_name, stage_payload)
    confidence = str(payload.get('confidence') or 'medium').strip().lower()
    if confidence not in {'high', 'medium', 'low'}:
        confidence = 'medium'

    risks_raw = payload.get('risks')
    risks: List[str] = []
    if isinstance(risks_raw, list):
        risks = [str(item).strip() for item in risks_raw if str(item).strip()][:8]

    actions_raw = payload.get('actions')
    actions: List[str] = []
    if isinstance(actions_raw, list):
        actions = [str(item).strip() for item in actions_raw if str(item).strip()][:8]

    return {
        'agent': agent_name,
        'summary': summary,
        'confidence': confidence,
        'risks': risks,
        'actions': actions,
        'status': 'ok',
    }


def _build_swarm_consensus(agents_payload: Dict[str, Any]) -> Dict[str, Any]:
    summaries: List[str] = []
    merged_risks: List[str] = []
    merged_actions: List[str] = []
    confidence_scores = {'low': 0.4, 'medium': 0.65, 'high': 0.85}
    score_sum = 0.0
    score_count = 0

    for stage in ('taizi', 'zhongshu', 'menxia', 'shangshu'):
        agent_payload = agents_payload.get(stage)
        if not isinstance(agent_payload, dict):
            continue
        summary = str(agent_payload.get('summary') or '').strip()
        if summary:
            summaries.append(f"{stage}: {summary}")
        confidence = str(agent_payload.get('confidence') or 'medium').strip().lower()
        score_sum += confidence_scores.get(confidence, 0.65)
        score_count += 1

        risks_raw = agent_payload.get('risks')
        risks: List[Any] = risks_raw if isinstance(risks_raw, list) else []
        for item in risks:
            risk_text = str(item).strip()
            if risk_text and risk_text not in merged_risks:
                merged_risks.append(risk_text)

        actions_raw = agent_payload.get('actions')
        actions: List[Any] = actions_raw if isinstance(actions_raw, list) else []
        for item in actions:
            action_text = str(item).strip()
            if action_text and action_text not in merged_actions:
                merged_actions.append(action_text)

    avg_conf = (score_sum / score_count) if score_count else 0.65
    conf_level = 'high' if avg_conf >= 0.8 else 'medium' if avg_conf >= 0.55 else 'low'
    return {
        'summary': '\n'.join(summaries) if summaries else '暂无 swarm 结论',
        'confidence': conf_level,
        'risks': merged_risks[:10],
        'actions': merged_actions[:10],
    }


@contextmanager
def _temporary_env(overrides: Dict[str, str]):
    old_values: Dict[str, Optional[str]] = {}
    try:
        for key, value in overrides.items():
            old_values[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _normalize_project_path(project_path: Optional[str]) -> str:
    if not project_path:
        return ''
    return os.path.normpath(os.path.abspath(project_path))


def _normalize_output_root(raw_output_root: Any) -> Optional[str]:
    text = str(raw_output_root or '').strip()
    if not text:
        return None
    if not os.path.isabs(text):
        return None
    return os.path.normpath(os.path.abspath(text))


def _safe_output_segment(value: Any, fallback: str = 'snippet', max_len: int = 64) -> str:
    text = str(value or '').strip()
    if not text:
        return fallback
    text = re.sub(r'[^0-9a-zA-Z_\-一-鿿]+', '_', text)
    text = text.strip('_')
    if not text:
        return fallback
    return text[:max_len]


def _derive_output_relative_path(project_path: str, block: Dict[str, Any], index: int) -> str:
    raw_file_path = str(block.get('file_path') or '').strip()
    project_root = _normalize_project_path(project_path)

    candidate = ''
    if raw_file_path:
        if os.path.isabs(raw_file_path):
            absolute_file_path = os.path.normpath(os.path.abspath(raw_file_path))
            if project_root and absolute_file_path.startswith(project_root):
                try:
                    candidate = os.path.relpath(absolute_file_path, project_root)
                except Exception:
                    candidate = os.path.basename(absolute_file_path)
            else:
                candidate = os.path.basename(absolute_file_path)
        else:
            candidate = raw_file_path

    candidate = candidate.replace('\\', '/').strip('/ ')
    raw_parts = [part for part in candidate.split('/') if part not in {'', '.', '..'}]

    if not raw_parts:
        anchor = _safe_output_segment(block.get('anchor') or f'snippet_{index + 1}', fallback=f'snippet_{index + 1}', max_len=40)
        return f'generated/{anchor}.txt'

    safe_parts: List[str] = []
    for idx, part in enumerate(raw_parts):
        if idx == len(raw_parts) - 1:
            stem, ext = os.path.splitext(part)
            safe_stem = _safe_output_segment(stem, fallback=f'snippet_{index + 1}', max_len=56)
            safe_ext = ext if re.match(r'^\.[A-Za-z0-9_]{1,12}$', ext or '') else '.txt'
            safe_parts.append(f'{safe_stem}{safe_ext}')
        else:
            safe_parts.append(_safe_output_segment(part, fallback='dir', max_len=56))

    relative_path = '/'.join(safe_parts).strip('/ ')
    return relative_path or f'generated/snippet_{index + 1}.txt'


def _resolve_output_target(output_root: str, relative_path: str) -> Tuple[Optional[Path], Optional[str]]:
    try:
        root = Path(output_root).resolve()
        target = (root / relative_path).resolve()
        target.relative_to(root)
        return target, None
    except Exception:
        return None, 'path_traversal_blocked_or_invalid_target'


def _apply_solution_packet_output(
    project_path: str,
    solution_packet: Dict[str, Any],
    output_root: Optional[str],
    auto_apply_output: bool,
) -> Dict[str, Any]:
    normalized_output_root = _normalize_output_root(output_root)
    result: Dict[str, Any] = {
        'enabled': bool(auto_apply_output),
        'outputRoot': normalized_output_root,
        'writtenFiles': [],
        'failedFiles': [],
        'writtenCount': 0,
        'failedCount': 0,
    }

    if not auto_apply_output:
        result['reason'] = 'auto_apply_output_disabled'
        return result
    if not normalized_output_root:
        result['reason'] = 'missing_or_invalid_output_root'
        return result

    snippet_blocks_raw = solution_packet.get('snippet_blocks')
    snippet_blocks = [item for item in _as_list(snippet_blocks_raw) if isinstance(item, dict)]
    if not snippet_blocks:
        result['reason'] = 'no_snippet_blocks'
        return result

    for index, block in enumerate(snippet_blocks):
        relative_path = _derive_output_relative_path(project_path, block, index)
        target, error = _resolve_output_target(normalized_output_root, relative_path)
        if error or target is None:
            result['failedFiles'].append({
                'relativePath': relative_path,
                'sourceFile': block.get('file_path'),
                'reason': error or 'invalid_target',
            })
            continue

        content = str(block.get('code') or '').rstrip()
        if not content:
            result['failedFiles'].append({
                'relativePath': relative_path,
                'sourceFile': block.get('file_path'),
                'reason': 'empty_snippet_code',
            })
            continue

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content + '\n', encoding='utf-8')
            result['writtenFiles'].append({
                'path': str(target),
                'relativePath': relative_path,
                'sourceFile': block.get('file_path'),
                'bytes': len((content + '\n').encode('utf-8')),
            })
        except Exception as exc:
            result['failedFiles'].append({
                'relativePath': relative_path,
                'sourceFile': block.get('file_path'),
                'reason': f'write_failed: {exc}',
            })

    result['writtenCount'] = len(result['writtenFiles'])
    result['failedCount'] = len(result['failedFiles'])
    result['reason'] = 'ok' if result['failedCount'] == 0 else 'partial_failure'
    return result


def _extract_query_terms(query: str) -> List[str]:
    raw_terms = re.split(r'[^\w\u4e00-\u9fff]+', query.lower())
    terms: List[str] = []
    for term in raw_terms:
        normalized = term.strip()
        if not normalized or normalized in STOPWORDS or len(normalized) <= 1:
            continue
        if normalized not in terms:
            terms.append(normalized)
    return terms


def _create_multi_agent_session(
    project_path: str,
    user_query: str,
    task_mode: str,
    clarification_context: Optional[Dict[str, Any]] = None,
    swarm_enabled: bool = True,
    conversation_id: Optional[str] = None,
    advisor_enabled: Optional[bool] = None,
    opencode_enabled: Optional[bool] = None,
    output_root: Optional[str] = None,
    auto_apply_output: bool = False,
) -> Dict[str, Any]:
    session_id = uuid4().hex
    deepseek_settings = get_deepseek_settings()
    task_session = TaskSession.create(user_goal=user_query, task_id=session_id)
    task_session.plan = {
        'plan_id': f'multi_agent_{session_id}',
        'steps': [
            {'id': index, 'stage': stage, 'description': STAGE_LABELS[stage]}
            for index, stage in enumerate(STAGE_SEQUENCE)
        ],
    }
    task_session.execution_state.total_steps = len(STAGE_SEQUENCE)
    normalized_output_root = _normalize_output_root(output_root)
    payload = {
        'sessionId': session_id,
        'projectPath': project_path,
        'userQuery': user_query,
        'taskMode': task_mode,
        'clarificationContext': clarification_context or {},
        'conversationId': str(conversation_id or '').strip() or None,
        'swarmEnabled': bool(swarm_enabled),
        'outputRoot': normalized_output_root,
        'autoApplyOutput': bool(auto_apply_output),
        'advisorEnabled': _is_advisor_sidecar_enabled({'advisor_enabled': advisor_enabled}),
        'opencodeEnabled': _is_opencode_kernel_enabled({'opencode_enabled': opencode_enabled}),
        'status': 'starting',
        'stage': 'taizi',
        'message': '三省六部会话已创建',
        'packets': {
            'swarm_packet': {
                'enabled': bool(swarm_enabled),
                'llm_enabled': bool(swarm_enabled and has_deepseek_config()),
                'model': str(deepseek_settings.get('model') or ''),
                'agents': {},
                'consensus': {},
                'updatedAt': _utcnow_iso(),
            },
            'roles': {
                'advisor': dict(ADVISOR_ROLE_PROFILE),
            },
        },
        'result': None,
        'error': None,
        'taskSession': task_session.to_dict(),
        'startedAt': _utcnow_iso(),
        'updatedAt': _utcnow_iso(),
        'completedAt': None,
    }
    data_accessor.save_multi_agent_session(session_id, payload)
    return payload


def _get_multi_agent_session(session_id: str) -> Optional[Dict[str, Any]]:
    return data_accessor.get_multi_agent_session(session_id)


def _update_multi_agent_session(session_id: str, **changes: Any) -> Optional[Dict[str, Any]]:
    payload = _get_multi_agent_session(session_id)
    if not payload:
        return None
    payload = copy.deepcopy(payload)
    payload.update(changes)
    payload['updatedAt'] = _utcnow_iso()
    data_accessor.save_multi_agent_session(session_id, payload)
    return payload


def _emit_conversation_event(conversation_id: Optional[str], event_type: str, payload: Dict[str, Any]) -> None:
    cid = str(conversation_id or '').strip()
    if not cid:
        return
    try:
        data_accessor.append_conversation_event(cid, event_type, payload)
    except Exception:
        return


def _emit_multi_agent_conversation_event(session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    session_payload = _get_multi_agent_session(session_id)
    if not isinstance(session_payload, dict):
        return
    conversation_id = session_payload.get('conversationId')
    event_payload = {
        'multiAgentSessionId': session_id,
        **(payload or {}),
    }
    _emit_conversation_event(conversation_id, event_type, event_payload)


def _load_task_session(payload: Dict[str, Any]) -> TaskSession:
    task_session_data = payload.get('taskSession') or {}
    if isinstance(task_session_data, dict) and task_session_data:
        return TaskSession.from_dict(task_session_data)
    return TaskSession.create(user_goal=str(payload.get('userQuery') or ''), task_id=str(payload.get('sessionId') or uuid4().hex))


def _sync_task_session(payload: Dict[str, Any], task_session: TaskSession) -> Dict[str, Any]:
    if payload.get('conversationId'):
        task_session.messages = []
    payload['taskSession'] = task_session.to_dict()
    return payload


def _build_stage_history_from_task_session(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    task_session = _load_task_session(payload)
    events = getattr(task_session.event_log, 'events', []) or []
    history: List[Dict[str, Any]] = []

    for event in events:
        event_type = str(getattr(event, 'event_type', '') or '').strip()
        event_agent = str(getattr(event, 'agent', '') or '').strip()
        event_summary = str(getattr(event, 'summary', '') or '').strip()
        event_timestamp = getattr(event, 'timestamp', None)
        timestamp = _utcnow_iso()
        if event_timestamp is not None:
            timestamp = str(event_timestamp.isoformat())

        stage: Optional[str] = None
        if event_type == 'step_start' and event_agent in STAGE_SEQUENCE:
            stage = event_agent
        elif event_type == 'task_complete':
            stage = 'done'
        elif event_type == 'task_fail':
            stage = 'failed'

        if not stage:
            continue

        history.append(
            {
                'stage': stage,
                'message': event_summary or STAGE_LABELS.get(stage, stage),
                'timestamp': timestamp,
            }
        )

    if history:
        return history

    fallback_stage = str(payload.get('stage') or '').strip()
    fallback_message = str(payload.get('message') or '').strip()
    if fallback_stage:
        return [
            {
                'stage': fallback_stage,
                'message': fallback_message or STAGE_LABELS.get(fallback_stage, fallback_stage),
                'timestamp': str(payload.get('updatedAt') or payload.get('startedAt') or _utcnow_iso()),
            }
        ]
    return []


def _record_stage_transition(session_id: str, stage: str, message: Optional[str] = None) -> Optional[Dict[str, Any]]:
    payload = _get_multi_agent_session(session_id)
    if not payload:
        return None
    payload = copy.deepcopy(payload)
    task_session = _load_task_session(payload)
    stage_message = message or STAGE_LABELS.get(stage, stage)
    timestamp = _utcnow_iso()

    if stage in STAGE_SEQUENCE:
        step_index = STAGE_SEQUENCE.index(stage)
        task_session.execution_state.current_step_id = step_index
        task_session.update_state(stage, 'start_step', {'summary': stage_message})
    elif stage == 'done':
        last_index = len(STAGE_SEQUENCE) - 1
        task_session.execution_state.current_step_id = last_index
        task_session.update_state('shangshu', 'complete_step', {'summary': stage_message})
        task_session.mark_completed()
    elif stage == 'failed':
        task_session.mark_failed(stage_message)

    payload.update({
        'stage': stage,
        'message': stage_message,
        'updatedAt': timestamp,
    })
    _sync_task_session(payload, task_session)
    data_accessor.save_multi_agent_session(session_id, payload)

    _emit_conversation_event(
        payload.get('conversationId'),
        'multi_agent.stage',
        {
            'multiAgentSessionId': session_id,
            'stage': stage,
            'message': stage_message,
            'timestamp': timestamp,
        },
    )
    return payload


def _make_intent_packet(
    user_query: str,
    project_path: str,
    task_mode: str,
    clarification_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    clarification_context = clarification_context or {}
    selected_option_labels = clarification_context.get('selectedOptionLabels') or []
    expected_result = clarification_context.get('latestUserReply') or user_query
    clarified_target = clarification_context.get('inferredIntent') or user_query[:120]
    constraints = ['输出必须同时包含分析与可直接复制代码片段']
    if isinstance(selected_option_labels, list):
        constraints.extend(str(item) for item in selected_option_labels if str(item).strip())
    return {
        'type': 'IntentPacket',
        'task_mode': task_mode,
        'target_repo': project_path,
        'user_goal': user_query,
        'feature_scope': user_query[:120],
        'constraints': constraints,
        'expected_output': ['analysis', 'copyable_code_snippets'],
        'clarification_context': clarification_context,
        'review': {
            'clarified_target': clarified_target,
            'expected_result': expected_result,
            'constraints': constraints,
            'needs_evidence_backing': True,
            'allowed_goals': ['modify_existing', 'write_new_code'],
        },
    }


def _normalize_selected_node(raw_selected_node: Any) -> Dict[str, Any]:
    return raw_selected_node if isinstance(raw_selected_node, dict) else {}


def _extract_candidate_partition_ids(evidence: List[Dict[str, Any]], preferred_partition_id: Optional[str]) -> List[str]:
    candidate_ids: List[str] = []
    if isinstance(preferred_partition_id, str) and preferred_partition_id.strip():
        candidate_ids.append(preferred_partition_id.strip())

    for item in evidence:
        if not isinstance(item, dict):
            continue
        graph_context = item.get('graph_context') or {}
        if isinstance(graph_context, dict):
            partition_id = graph_context.get('partition_id')
            if isinstance(partition_id, str) and partition_id and partition_id not in candidate_ids:
                candidate_ids.append(partition_id)
        elif isinstance(graph_context, list):
            for ctx in graph_context:
                if not isinstance(ctx, dict):
                    continue
                partition_id = ctx.get('partition_id')
                if isinstance(partition_id, str) and partition_id and partition_id not in candidate_ids:
                    candidate_ids.append(partition_id)
    return candidate_ids


def _augment_candidate_partitions_from_selected_node(
    project_path: str,
    selected_node: Dict[str, Any],
    preferred_partition_id: Optional[str],
    candidate_ids: List[str],
) -> List[str]:
    if not selected_node:
        return candidate_ids
    hierarchy_cached = data_accessor.get_function_hierarchy(project_path)
    if not hierarchy_cached:
        return candidate_ids
    contract_payload = analysis_service._build_phase6_read_contract(project_path, hierarchy_cached)
    summary = analysis_service._resolve_partition_summary_for_rag(contract_payload, selected_node, preferred_partition_id or '')
    if not isinstance(summary, dict):
        return candidate_ids
    partition_id = summary.get('partition_id')
    if isinstance(partition_id, str) and partition_id and partition_id not in candidate_ids:
        candidate_ids.insert(0, partition_id)
    return candidate_ids


def _score_selected_node(selected_node: Dict[str, Any], path_analysis: Dict[str, Any]) -> float:
    if not selected_node:
        return 0.0
    candidates = [
        selected_node.get('id'),
        selected_node.get('name'),
        selected_node.get('label'),
        selected_node.get('signature'),
        selected_node.get('method_signature'),
        selected_node.get('fqmn'),
    ]
    normalized_candidates = [str(value).strip() for value in candidates if isinstance(value, str) and value.strip()]
    if not normalized_candidates:
        return 0.0
    chain = [str(item).strip() for item in (path_analysis.get('function_chain') or path_analysis.get('path') or []) if isinstance(item, str)]
    leaf_node = str(path_analysis.get('leaf_node') or '').strip()
    bonus = 0.0
    for candidate in normalized_candidates:
        if candidate in chain or any(node.endswith(f'.{candidate}') for node in chain):
            bonus += 1.0
        if leaf_node and (candidate == leaf_node or leaf_node.endswith(f'.{candidate}')):
            bonus += 0.6
    return bonus


def _build_deferred_path_fallback(partition_payload: Dict[str, Any], query: str, selected_node: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    info = partition_payload.get('path_analysis_info') or {}
    deferred = info.get('deferred_path_summaries') or []
    if not deferred or not isinstance(deferred, list):
        return {}
    best_summary: Dict[str, Any] = {}
    best_score = -1.0
    for item in deferred:
        if not isinstance(item, dict):
            continue
        score = _score_path(query, item, selected_node=selected_node, candidate_partition_bonus=0.2)
        if score > best_score:
            best_score = score
            best_summary = item
    first = best_summary or (deferred[0] if isinstance(deferred[0], dict) else {})
    path_nodes = first.get('path') or first.get('function_chain') or []
    return {
        'path_id': first.get('path_id'),
        'path_name': first.get('path_name') or first.get('leaf_node'),
        'path_description': first.get('reason') or info.get('user_message') or '基于分区延后路径摘要生成的候选链',
        'function_chain': path_nodes,
        'leaf_node': first.get('leaf_node'),
        'semantics': {'source': 'deferred_path_summary'},
        'selection_reason': 'deferred_path_summary',
        'selection_score': best_score,
    }


def _ensure_workbench_ready(project_path: str) -> Dict[str, Any]:
    existing_hierarchy = analysis_service._resolve_function_hierarchy_cached(project_path)
    best_existing_payload = analysis_service._select_best_phase6_hierarchy_payload(project_path, existing_hierarchy)
    existing_richness = analysis_service._measure_hierarchy_path_richness(best_existing_payload)
    if existing_hierarchy and existing_richness > 0:
        return {
            'bootstrapReady': True,
            'projectPath': project_path,
            'status': 'completed',
            'bootstrap': None,
        }

    if existing_hierarchy and existing_richness <= 0:
        data_accessor.delete_function_hierarchy(project_path)
        data_accessor.delete_function_hierarchy_layer_cache(project_path)

    workbench = analysis_service._create_workbench_session(project_path)
    session_id = str(workbench.get('sessionId') or '')
    timeout_seconds = _workbench_ready_timeout_seconds()

    run_result: Dict[str, Any] = {'error': None}

    def _run_workbench() -> None:
        try:
            with _temporary_env(FAST_RAG_ENV), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                analysis_service._run_workbench_session(session_id, project_path)
        except Exception as exc:
            run_result['error'] = str(exc)

    worker = threading.Thread(target=_run_workbench, daemon=True)

    previous_disable = logging.root.manager.disable
    root_logger_level = logging.getLogger().level
    logging.disable(logging.ERROR)
    logging.getLogger().setLevel(logging.ERROR)
    try:
        worker.start()
        worker.join(timeout=timeout_seconds)
    finally:
        logging.disable(previous_disable)
        logging.getLogger().setLevel(root_logger_level)

    session_payload: Dict[str, Any] = analysis_service._get_workbench_session_or_none(session_id) or workbench

    if worker.is_alive():
        session_payload = dict(session_payload) if isinstance(session_payload, dict) else {'sessionId': session_id}
        session_payload['status'] = 'timeout'
        session_payload['bootstrapReady'] = bool(session_payload.get('bootstrapReady'))
        session_payload['message'] = f'workbench_prepare_timeout_{timeout_seconds}s'
        session_payload['projectPath'] = project_path
        return session_payload

    if run_result.get('error'):
        session_payload = dict(session_payload) if isinstance(session_payload, dict) else {'sessionId': session_id}
        session_payload['status'] = 'failed'
        session_payload['bootstrapReady'] = bool(session_payload.get('bootstrapReady'))
        session_payload['message'] = f'workbench_prepare_error: {run_result.get("error")}'
        session_payload['projectPath'] = project_path
        return session_payload

    return session_payload


def _score_path(query: str, path_analysis: Dict[str, Any], selected_node: Optional[Dict[str, Any]] = None, candidate_partition_bonus: float = 0.0) -> float:
    query_tokens = set(_extract_query_terms(query))
    if not query_tokens:
        return 0.0
    text_parts: List[str] = []
    for key in ('path_name', 'path_description', 'leaf_node'):
        value = path_analysis.get(key)
        if isinstance(value, str):
            text_parts.append(value)
    semantics = path_analysis.get('semantics') or {}
    if isinstance(semantics, dict):
        for value in semantics.values():
            if isinstance(value, str):
                text_parts.append(value)
    for item in path_analysis.get('function_chain') or path_analysis.get('path') or []:
        if isinstance(item, str):
            text_parts.append(item)
    corpus = ' '.join(text_parts).lower()
    hits = sum(1 for token in query_tokens if token in corpus)
    base_score = float(path_analysis.get('worthiness_score') or 0.0)
    selected_node_bonus = _score_selected_node(selected_node or {}, path_analysis)
    return base_score + hits * 0.35 + selected_node_bonus + candidate_partition_bonus


def _summarize_path_candidate(path_analysis: Dict[str, Any], score: float, partition_id: str = '') -> Dict[str, Any]:
    return {
        'partition_id': partition_id,
        'path_id': path_analysis.get('path_id'),
        'path_name': path_analysis.get('path_name'),
        'path_description': path_analysis.get('path_description'),
        'function_chain': path_analysis.get('function_chain') or path_analysis.get('path') or [],
        'leaf_node': path_analysis.get('leaf_node'),
        'worthiness_score': path_analysis.get('worthiness_score'),
        'selection_score': round(score, 4),
        'selection_reason': path_analysis.get('selection_reason'),
        'semantics': path_analysis.get('semantics') or {},
        'source': path_analysis.get('source') or (path_analysis.get('semantics') or {}).get('source') or '',
    }


def _pick_best_path(
    query: str,
    project_path: str,
    candidate_partition_ids: Optional[List[str]] = None,
    selected_node: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    best_partition_id: Optional[str] = None
    best_partition_payload: Dict[str, Any] = {}
    best_path: Dict[str, Any] = {}
    best_score = -1.0
    candidate_path_summaries: List[Dict[str, Any]] = []

    all_partitions = [partition for partition in data_accessor.get_all_partitions(project_path) if isinstance(partition, dict)]
    prioritized_partitions: List[Dict[str, Any]] = []
    remaining_partitions: List[Dict[str, Any]] = []
    prioritized_ids = set(candidate_partition_ids or [])

    for partition in all_partitions:
        partition_id = partition.get('partition_id') or partition.get('id')
        if isinstance(partition_id, str) and partition_id in prioritized_ids:
            prioritized_partitions.append(partition)
        else:
            remaining_partitions.append(partition)

    ordered_partitions = prioritized_partitions + remaining_partitions

    for partition in ordered_partitions:
        if not isinstance(partition, dict):
            continue
        partition_id = partition.get('partition_id') or partition.get('id')
        if not isinstance(partition_id, str):
            continue
        path_analyses = partition.get('path_analyses') or []
        partition_bonus = 0.5 if partition_id in prioritized_ids else 0.0
        for path_analysis in path_analyses:
            if not isinstance(path_analysis, dict):
                continue
            score = _score_path(query, path_analysis, selected_node=selected_node, candidate_partition_bonus=partition_bonus)
            candidate_path_summaries.append(_summarize_path_candidate(path_analysis, score, partition_id=partition_id))
            if score > best_score:
                best_score = score
                best_partition_id = partition_id
                best_partition_payload = partition
                best_path = dict(path_analysis)
                best_path['selection_score'] = round(score, 4)

    candidate_path_summaries.sort(key=lambda item: float(item.get('selection_score') or 0.0), reverse=True)
    top_candidates = candidate_path_summaries[:24]

    if not best_path and prioritized_partitions:
        for partition in prioritized_partitions:
            deferred_path = _build_deferred_path_fallback(partition, query, selected_node=selected_node)
            if deferred_path:
                deferred_path['candidate_path_summaries'] = top_candidates
                return str(partition.get('partition_id') or ''), partition, deferred_path, top_candidates

    if best_path:
        best_path['candidate_path_summaries'] = top_candidates
    return best_partition_id, best_partition_payload, best_path, top_candidates


def _extract_search_evidence(query: str, project_path: str) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    seen_keys: set = set()

    code_result = run_codebase_retrieval(project_path=project_path, query=query, top_k=8)
    raw_code_hits = code_result.get('hits')
    code_hits: List[Dict[str, Any]] = []
    if isinstance(raw_code_hits, list):
        for raw_item in raw_code_hits:
            if isinstance(raw_item, dict):
                code_hits.append(raw_item)
    for index, hit in enumerate(code_hits, start=1):
        file_path = str(hit.get('file') or hit.get('file_path') or '').strip()
        label = str(hit.get('label') or file_path or f'code_hit_{index}').strip()
        key = (file_path.lower(), label.lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        evidence.append(
            {
                'rank': index,
                'source': str(hit.get('source') or 'codebase_scan'),
                'score': hit.get('score'),
                'node_id': str(hit.get('node_id') or ''),
                'id': str(hit.get('id') or ''),
                'file_path': file_path,
                'file': file_path,
                'label': label,
                'line_start': hit.get('line_start'),
                'line_end': hit.get('line_end'),
                'snippet': hit.get('snippet'),
                'graph_context': hit.get('graph_context') if isinstance(hit.get('graph_context'), list) else [],
            }
        )

    graph_data = analysis_service._resolve_graph_data_for_project(project_path, allow_global_fallback=False)
    if isinstance(graph_data, dict):
        try:
            shadow_result = analysis_service.run_hybrid_shadow(
                graph_data=graph_data,
                query=query,
                top_k=8,
                enable_graph_context=True,
            )
            candidates = shadow_result.get('flat_hits') or shadow_result.get('hybrid_results') or []
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                file_path = str(item.get('file_path') or item.get('file') or '').strip()
                label = str(item.get('label') or item.get('node_id') or item.get('id') or '').strip()
                key = (file_path.lower(), label.lower())
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                evidence.append(item)
        except Exception:
            pass

    return evidence[:8]


def _build_search_fallback_candidates(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    seen: set = set()

    for index, item in enumerate(evidence[:24], start=1):
        if not isinstance(item, dict):
            continue
        file_path = str(item.get('file_path') or item.get('file') or '').strip()
        label = str(item.get('label') or item.get('node_id') or item.get('id') or file_path or f'evidence_{index}').strip()
        key = (file_path.lower(), label.lower())
        if key in seen:
            continue
        seen.add(key)

        graph_context = item.get('graph_context')
        graph_path = [str(entry).strip() for entry in graph_context if isinstance(entry, str) and str(entry).strip()] if isinstance(graph_context, list) else []
        function_chain: List[str] = []
        if label:
            function_chain.append(label)
        function_chain.extend(graph_path[:4])

        score = _safe_float(item.get('score'), default=max(0.0, 1.0 - index * 0.08))
        candidate = {
            'partition_id': '',
            'path_id': f'search_fallback_{index}',
            'path_name': label or f'Fallback Candidate {index}',
            'path_description': (str(item.get('snippet') or '').strip()[:220] or f'Fallback evidence from {file_path or label}'),
            'function_chain': function_chain,
            'leaf_node': label,
            'worthiness_score': round(score, 4),
            'selection_score': round(score, 4),
            'selection_reason': 'search_fallback_candidate',
            'semantics': {'source': 'search_fallback', 'file_path': file_path, 'label': label},
            'source': 'search_fallback',
        }
        candidates.append(candidate)

    return candidates


def _build_node_detail_payload(project_path: str, entity_id: str) -> Optional[Dict[str, Any]]:
    report = analysis_service._resolve_report_cached(project_path, allow_global_fallback=False)
    node_data = analysis_service._resolve_graph_node_data(project_path, entity_id, allow_global_fallback=False) or {}
    if not report and not node_data:
        return None

    node_kind = str(node_data.get('type') or 'unknown')
    display_name = str(node_data.get('label') or node_data.get('name') or entity_id)
    file_path = node_data.get('file') or node_data.get('file_path')
    line_start = node_data.get('line')
    line_end = None
    source_code = None
    cfg_payload = {
        'cfg': None,
        'dfg': None,
        'io': {
            'inputs': [],
            'outputs': [],
            'global_reads': [],
            'global_writes': [],
        },
    }

    if report:
        resolved_method = analysis_service._resolve_method_or_function_from_report(report, entity_id)
        if resolved_method:
            info = resolved_method['info']
            node_kind = resolved_method['kind']
            display_name = getattr(info, 'name', None) or entity_id
            source_code = getattr(info, 'source_code', None)
            if getattr(info, 'source_location', None):
                file_path = info.source_location.file_path
                line_start = info.source_location.line_start
                line_end = info.source_location.line_end
            cfg_payload = analysis_service._generate_cfg_dfg_io(info)

    source_payload = analysis_service._build_source_payload(
        project_path,
        source_code=source_code,
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
    )
    return {
        'entity_id': entity_id,
        'kind': node_kind,
        'display_name': display_name,
        'file_path': source_payload.get('file_path') or file_path,
        'line_start': source_payload.get('line_start') or line_start,
        'line_end': source_payload.get('line_end') or line_end,
        'signature': entity_id,
        'has_cfg': bool(cfg_payload.get('cfg')),
        'has_dfg': bool(cfg_payload.get('dfg')),
        'has_io': bool((cfg_payload.get('io') or {}).get('inputs') or (cfg_payload.get('io') or {}).get('outputs')),
        'cfg': cfg_payload.get('cfg'),
        'dfg': cfg_payload.get('dfg'),
        'io': cfg_payload.get('io') or {},
        'source': source_payload,
    }


def _normalize_text_evidence_items(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for index, item in enumerate(evidence[:8], start=1):
        if not isinstance(item, dict):
            continue
        items.append({
            'id': f'text_{index}',
            'kind': 'text',
            'role': 'primary' if index <= 3 else 'supporting',
            'grounding': 'direct',
            'claim': item.get('label') or item.get('node_id') or 'unknown',
            'source': {
                'file_path': item.get('file_path') or item.get('file'),
                'symbol': item.get('label') or item.get('node_id'),
                'node_id': item.get('node_id') or item.get('id'),
                'line_start': item.get('line_start'),
                'line_end': item.get('line_end'),
            },
            'snippet': item.get('snippet'),
            'trace': item.get('graph_context') or [],
            'score': item.get('score'),
            'raw_refs': [f"search:{item.get('source') or 'hybrid'}"],
        })
    return items


def _normalize_path_evidence_items(selected_path: Dict[str, Any], candidate_paths: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if isinstance(selected_path, dict) and selected_path:
        items.append({
            'id': f"path:{selected_path.get('path_id') or 'selected'}",
            'kind': 'functional_path',
            'role': 'primary',
            'grounding': 'derived',
            'claim': selected_path.get('path_description') or selected_path.get('path_name') or 'selected_path',
            'source': {
                'partition_id': selected_path.get('partition_id'),
                'path_id': selected_path.get('path_id'),
                'symbol': (selected_path.get('function_chain') or [None])[0],
            },
            'snippet': None,
            'trace': selected_path.get('function_chain') or selected_path.get('path') or [],
            'score': selected_path.get('selection_score') or selected_path.get('worthiness_score'),
            'raw_refs': ['path:selected'],
        })
    for index, item in enumerate(candidate_paths[:4], start=1):
        if not isinstance(item, dict):
            continue
        items.append({
            'id': f"path_candidate_{index}",
            'kind': 'functional_path',
            'role': 'supporting',
            'grounding': 'derived',
            'claim': item.get('path_description') or item.get('path_name') or 'candidate_path',
            'source': {
                'path_id': item.get('path_id'),
                'symbol': (item.get('function_chain') or [None])[0],
            },
            'snippet': None,
            'trace': item.get('function_chain') or [],
            'score': item.get('selection_score') or item.get('worthiness_score'),
            'raw_refs': ['path:candidate'],
        })
    return items


def _normalize_call_chain_evidence_items(selected_path: Dict[str, Any], selected_partition: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    call_chain = selected_path.get('call_chain_analysis') or {}
    highlight = selected_path.get('highlight_config') or {}
    call_graph = selected_partition.get('call_graph') or {}
    if call_chain:
        items.append({
            'id': 'call_chain:selected',
            'kind': 'call_chain',
            'role': 'supporting',
            'grounding': 'derived',
            'claim': call_chain.get('explanation') or call_chain.get('call_chain_type') or 'call_chain',
            'source': {
                'symbol': call_chain.get('main_method'),
                'path_id': selected_path.get('path_id'),
            },
            'snippet': None,
            'trace': [call_chain.get('main_method'), *(call_chain.get('intermediate_methods') or []), *(call_chain.get('direct_calls') or [])],
            'score': selected_path.get('worthiness_score'),
            'raw_refs': ['call_chain_analysis'],
        })
    if highlight:
        items.append({
            'id': 'call_chain:highlight',
            'kind': 'call_chain',
            'role': 'context',
            'grounding': 'derived',
            'claim': highlight.get('explanation') or 'highlight_config',
            'source': {
                'symbol': highlight.get('main_method'),
                'path_id': selected_path.get('path_id'),
            },
            'snippet': None,
            'trace': highlight.get('path_methods') or [],
            'score': selected_path.get('worthiness_score'),
            'raw_refs': ['highlight_config'],
        })
    if call_graph:
        items.append({
            'id': 'call_graph:partition',
            'kind': 'call_chain',
            'role': 'context',
            'grounding': 'derived',
            'claim': 'partition_call_graph',
            'source': {
                'partition_id': selected_partition.get('partition_id') or selected_partition.get('id'),
            },
            'snippet': None,
            'trace': call_graph.get('internal_edges') or [],
            'score': None,
            'raw_refs': ['partition_call_graph'],
        })
    return items


def _normalize_graph_evidence_items(node_details: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for index, detail in enumerate(node_details[:5], start=1):
        if not isinstance(detail, dict):
            continue
        source = detail.get('source') or {}
        items.append({
            'id': f'graph_{index}',
            'kind': 'graph',
            'role': 'primary' if source.get('snippet') else 'supporting',
            'grounding': 'direct' if source.get('snippet') else 'derived',
            'claim': detail.get('display_name') or detail.get('entity_id') or 'graph_node',
            'source': {
                'file_path': detail.get('file_path'),
                'symbol': detail.get('signature') or detail.get('entity_id'),
                'line_start': detail.get('line_start'),
                'line_end': detail.get('line_end'),
            },
            'snippet': source.get('snippet'),
            'trace': [detail.get('entity_id')],
            'score': None,
            'raw_refs': ['node_detail'],
        })
    return items


def _build_evidence_packet(retrieval_bundle: Dict[str, Any]) -> Dict[str, Any]:
    text_items = _normalize_text_evidence_items(retrieval_bundle.get('evidence') or [])
    path_items = _normalize_path_evidence_items(
        retrieval_bundle.get('selected_path') or {},
        retrieval_bundle.get('candidate_paths') or [],
    )
    call_chain_items = _normalize_call_chain_evidence_items(
        retrieval_bundle.get('selected_path') or {},
        retrieval_bundle.get('selected_partition') or {},
    )
    graph_items = _normalize_graph_evidence_items(retrieval_bundle.get('node_details') or [])
    items = [*text_items, *path_items, *call_chain_items, *graph_items]
    primary_ids = [item['id'] for item in items if item.get('role') == 'primary']
    supporting_ids = [item['id'] for item in items if item.get('role') == 'supporting']
    confidence = retrieval_bundle.get('confidence', 'low')
    return {
        'type': 'EvidencePacket',
        'summary': {
            'confidence': confidence,
            'primary_ids': primary_ids,
            'supporting_ids': supporting_ids,
            'conflict_ids': [],
            'coverage': {
                'text': len(text_items),
                'graph': len(graph_items),
                'functional_path': len(path_items),
                'call_chain': len(call_chain_items),
            },
        },
        'items': items,
        'functional_context': retrieval_bundle.get('functional_context') or {},
        'review': {
            'selected_partition_id': retrieval_bundle.get('selected_partition_id'),
            'selected_path': retrieval_bundle.get('selected_path') or {},
            'candidate_paths': retrieval_bundle.get('candidate_paths') or [],
            'impacted_files': retrieval_bundle.get('impacted_files') or [],
            'selection_mode': retrieval_bundle.get('selection_mode'),
            'selection_reason': retrieval_bundle.get('selection_reason'),
            'anchor_ready': any(
                isinstance(item.get('source'), dict)
                and (
                    item['source'].get('file_path')
                    or item['source'].get('symbol')
                )
                for item in items
            ),
        },
    }


def _build_stage_output_packet(stage: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'stage': stage,
        'label': STAGE_LABELS.get(stage, stage),
        'completed_at': _utcnow_iso(),
        'payload': payload,
    }


def _build_stage_message(stage: str, payload: Dict[str, Any]) -> str:
    if stage == 'taizi':
        review = payload.get('review') or {}
        return f"任务卡已确认：{review.get('clarified_target') or payload.get('feature_scope') or '目标待补充'}"
    if stage == 'zhongshu':
        review = payload.get('review') or {}
        candidate_paths = review.get('candidate_paths') or []
        return f"统一证据已整理：主路径={bool(review.get('selected_path'))}，候选路径={len(candidate_paths)}"
    if stage == 'menxia':
        verdict = payload.get('verdict') or 'requery'
        return f"证据审议完成：{verdict}"
    if stage == 'shangshu':
        edit_plan = payload.get('edit_plan') or []
        return f"方案汇总完成：生成 {len(edit_plan)} 个编辑目标"
    return STAGE_LABELS.get(stage, stage)


def _build_opencode_system_context(task_mode: str, analysis: Dict[str, Any], advisor_section: Dict[str, Any]) -> str:
    selected_path = _as_dict(analysis.get('selected_path'))
    chain = [str(item).strip() for item in _as_list(selected_path.get('function_chain')) if str(item).strip()]
    reasoning = [str(item).strip() for item in _as_list(analysis.get('key_reasoning')) if str(item).strip()]
    chain_node_details = [item for item in _as_list(analysis.get('chain_node_details')) if isinstance(item, dict)]

    advisor_analysis = _as_dict(advisor_section.get('analysis'))
    advisor_how = str(advisor_analysis.get('how') or '').strip()
    constraint_types = [str(item).strip() for item in _as_list(advisor_section.get('constraint_types')) if str(item).strip()]

    chain_refs: List[str] = []
    chain_explanations: List[str] = []
    for item in chain_node_details[:12]:
        symbol = str(item.get('signature') or item.get('entity_id') or '').strip()
        source_payload = _as_dict(item.get('source'))
        file_path = str(item.get('file_path') or source_payload.get('file_path') or '').strip()
        line_start = item.get('line_start') or source_payload.get('line_start')
        call_explanation = str(item.get('call_explanation') or '').strip()
        if symbol and file_path and isinstance(line_start, int):
            chain_refs.append(f"{symbol}@{file_path}:{line_start}")
        elif symbol and file_path:
            chain_refs.append(f"{symbol}@{file_path}")
        elif symbol:
            chain_refs.append(symbol)
        if call_explanation and call_explanation not in chain_explanations:
            chain_explanations.append(call_explanation)

    lines: List[str] = [
        f"task_mode={task_mode}",
        f"analysis_summary={str(analysis.get('summary') or '').strip()}",
    ]
    if chain:
        lines.append(f"primary_call_chain={' -> '.join(chain[:12])}")
    if chain_refs:
        lines.append(f"chain_source_refs={' | '.join(chain_refs[:8])}")
    if chain_explanations:
        lines.append(f"chain_explanations={' | '.join(chain_explanations[:4])}")
    if reasoning:
        lines.append(f"key_reasoning={' | '.join(reasoning[:4])}")
    if advisor_how:
        lines.append(f"advisor_how={advisor_how}")
    if constraint_types:
        lines.append(f"advisor_constraint_types={','.join(constraint_types[:8])}")
    return '\n'.join(lines)


def _build_output_protocol(
    task_mode: str,
    analysis: Dict[str, Any],
    snippet_blocks: List[Dict[str, Any]],
    validation: List[str],
    evidence_verdict: Dict[str, Any],
    intent_review: Dict[str, Any],
    advisor_packet: Optional[Dict[str, Any]] = None,
    opencode_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    reasons = [str(item) for item in (evidence_verdict.get('reasons') or []) if str(item).strip()]
    refinement_needed = [str(item) for item in (evidence_verdict.get('refinement_needed') or []) if str(item).strip()]
    validation_notes = [str(item) for item in validation if str(item).strip()]
    intent_constraints = [str(item) for item in (intent_review.get('constraints') or []) if str(item).strip()]
    remaining_risks_constraints: List[str] = []

    advisor_payload = advisor_packet if isinstance(advisor_packet, dict) else {}
    advisor_constraints = _as_dict(advisor_payload.get('constraints'))
    advisor_section = {
        'enabled': bool(advisor_payload.get('enabled')),
        'status': advisor_payload.get('status') or 'disabled',
        'mode': advisor_payload.get('mode'),
        'recommended': advisor_payload.get('recommended') if isinstance(advisor_payload.get('recommended'), dict) else {},
        'analysis': advisor_payload.get('analysis') if isinstance(advisor_payload.get('analysis'), dict) else {},
        'constraint_types': _as_list(advisor_constraints.get('types')),
        'constraints': {
            'plain': _as_list(advisor_constraints.get('plain')),
            'types': _as_list(advisor_constraints.get('types')),
            'structured_summary': _as_dict(advisor_constraints.get('structured_summary')),
        },
        'source_targets': _as_list(advisor_payload.get('source_targets')),
        'followup_advisors': _as_list(advisor_payload.get('followup_advisors')),
    }

    opencode_payload = opencode_result if isinstance(opencode_result, dict) else {}
    opencode_validation = [str(item).strip() for item in _as_list(opencode_payload.get('validation_commands')) if str(item).strip()]

    for item in [*validation_notes, *opencode_validation, *refinement_needed, *intent_constraints]:
        if item not in remaining_risks_constraints:
            remaining_risks_constraints.append(item)

    analysis_view = {
        'summary': analysis.get('summary') or '',
        'key_reasoning': analysis.get('key_reasoning') or [],
        'impacted_files': analysis.get('impacted_files') or [],
        'selected_path': analysis.get('selected_path') or {},
        'candidate_paths': analysis.get('candidate_paths') or [],
        'chain_node_details': analysis.get('chain_node_details') or [],
        'selection_mode': analysis.get('selection_mode'),
        'selection_reason': analysis.get('selection_reason'),
        'advisor': analysis.get('advisor') if isinstance(analysis.get('advisor'), dict) else {},
    }
    advisor_for_context = _as_dict(analysis_view.get('advisor')) or advisor_section
    opencode_context = {
        'system_context': _build_opencode_system_context(task_mode, analysis_view, advisor_for_context),
        'preferred_files': [str(item).strip() for item in _as_list(analysis_view.get('impacted_files')) if str(item).strip()][:12],
        'preferred_symbols': [
            str(item).strip()
            for item in (
                _as_list(_as_dict(_as_dict(analysis_view.get('advisor')).get('analysis')).get('key_code_refs'))
                + _as_list(_as_dict(analysis_view.get('selected_path')).get('function_chain'))
                + [
                    str(detail.get('signature') or detail.get('entity_id') or '').strip()
                    for detail in _as_list(analysis_view.get('chain_node_details'))
                    if isinstance(detail, dict)
                ]
            )
            if str(item).strip()
        ][:20],
    }

    return {
        'version': '1.0',
        'task_mode': task_mode,
        'judgment': {
            'status': 'ready' if evidence_verdict.get('approved') else 'needs_refinement',
            'confidence': evidence_verdict.get('confidence') or 'low',
            'reasons': reasons,
        },
        'analysis': analysis_view,
        'advisor': advisor_section,
        'opencode': opencode_context,
        'code_snippets': snippet_blocks,
        'validation_commands': opencode_validation,
        'remaining_risks_constraints': remaining_risks_constraints,
        'constraints': intent_constraints,
        'opencode_kernel': {
            'status': opencode_payload.get('status') or 'disabled',
            'reason': opencode_payload.get('reason'),
            'duration_ms': opencode_payload.get('duration_ms'),
            'model': opencode_payload.get('model'),
            'agent': opencode_payload.get('agent'),
            'session_id': opencode_payload.get('session_id'),
        },
    }


def _build_node_details(project_path: str, evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
    seen: set = set()
    for item in evidence[:5]:
        source_name = str(item.get('source') or '').strip()
        if source_name in {'codebase_scan', 'codebase_symbol_hunt', 'python_ast_hunt', 'codebase_import_hunt'}:
            file_path = str(item.get('file_path') or item.get('file') or '').strip()
            if not file_path or file_path in seen:
                continue
            seen.add(file_path)
            source_payload = analysis_service._build_source_payload(
                project_path,
                source_code=None,
                file_path=file_path,
                line_start=item.get('line_start'),
                line_end=item.get('line_end'),
            )
            details.append(
                {
                    'entity_id': str(item.get('id') or file_path),
                    'kind': 'file_snippet',
                    'display_name': str(item.get('label') or file_path),
                    'file_path': source_payload.get('file_path') or file_path,
                    'line_start': source_payload.get('line_start') or item.get('line_start'),
                    'line_end': source_payload.get('line_end') or item.get('line_end'),
                    'signature': str(item.get('label') or file_path),
                    'has_cfg': False,
                    'has_dfg': False,
                    'has_io': False,
                    'cfg': None,
                    'dfg': None,
                    'io': {},
                    'source': source_payload,
                }
            )
            continue
        entity_id = item.get('node_id') or item.get('id')
        if not isinstance(entity_id, str) or not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        detail = _build_node_detail_payload(project_path, entity_id)
        if detail:
            details.append(detail)
    return details


def _build_chain_explanation_lookup(selected_path: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    chain = [str(item).strip() for item in (selected_path.get('function_chain') or selected_path.get('path') or []) if isinstance(item, str) and str(item).strip()]
    call_chain = _as_dict(selected_path.get('call_chain_analysis'))
    highlight = _as_dict(selected_path.get('highlight_config'))

    main_method = str(call_chain.get('main_method') or highlight.get('main_method') or '').strip()
    intermediate_methods = {str(item).strip() for item in _as_list(call_chain.get('intermediate_methods')) if str(item).strip()}
    direct_calls = {str(item).strip() for item in _as_list(call_chain.get('direct_calls')) if str(item).strip()}
    path_methods = {str(item).strip() for item in _as_list(highlight.get('path_methods')) if str(item).strip()}
    global_explanation = str(call_chain.get('explanation') or highlight.get('explanation') or '').strip()

    explanation_lookup: Dict[str, str] = {}
    role_lookup: Dict[str, str] = {}
    for symbol in chain:
        role = 'path_node'
        if symbol and symbol == main_method:
            role = 'main_method'
        elif symbol in intermediate_methods:
            role = 'intermediate_method'
        elif symbol in direct_calls:
            role = 'direct_call'
        elif symbol in path_methods:
            role = 'path_node'

        role_text = {
            'main_method': '主方法节点',
            'intermediate_method': '中间调用节点',
            'direct_call': '直接调用节点',
            'path_node': '路径节点',
        }.get(role, '路径节点')
        explanation_lookup[symbol] = f"{role_text}。{global_explanation}" if global_explanation else role_text
        role_lookup[symbol] = role

    return explanation_lookup, role_lookup


def _build_path_node_details(project_path: str, selected_path: Dict[str, Any], fallback_details: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
    seen: set = set()
    explanation_lookup, role_lookup = _build_chain_explanation_lookup(selected_path)

    fallback_lookup: Dict[str, Dict[str, Any]] = {}
    for detail in fallback_details:
        if not isinstance(detail, dict):
            continue
        signature = str(detail.get('signature') or detail.get('entity_id') or detail.get('display_name') or '').strip()
        if signature and signature not in fallback_lookup:
            fallback_lookup[signature] = detail

    chain_symbols = [
        str(item).strip()
        for item in (selected_path.get('function_chain') or selected_path.get('path') or [])[:12]
        if isinstance(item, str) and str(item).strip()
    ]

    for step_index, symbol in enumerate(chain_symbols, start=1):
        if symbol in seen:
            continue
        seen.add(symbol)
        detail = _build_node_detail_payload(project_path, symbol)
        if not detail:
            fallback = fallback_lookup.get(symbol)
            if isinstance(fallback, dict):
                detail = dict(fallback)
            else:
                detail = {
                    'entity_id': symbol,
                    'kind': 'method_or_function',
                    'display_name': symbol,
                    'file_path': '',
                    'line_start': None,
                    'line_end': None,
                    'signature': symbol,
                    'has_cfg': False,
                    'has_dfg': False,
                    'has_io': False,
                    'cfg': None,
                    'dfg': None,
                    'io': {},
                    'source': {},
                }
        detail = dict(detail)
        detail['step_index'] = step_index
        detail['chain_role'] = role_lookup.get(symbol, 'path_node')
        detail['call_explanation'] = explanation_lookup.get(symbol, '路径节点')
        details.append(detail)

    if details:
        return details

    indexed_fallback: List[Dict[str, Any]] = []
    for index, detail in enumerate(fallback_details[:5], start=1):
        if not isinstance(detail, dict):
            continue
        item = dict(detail)
        item.setdefault('step_index', index)
        item.setdefault('chain_role', 'evidence_fallback')
        item.setdefault('call_explanation', '路径未解析成功，回退到证据节点')
        indexed_fallback.append(item)
    return indexed_fallback


def _collect_impacted_files_from_path(node_details: List[Dict[str, Any]], fallback_files: List[str]) -> List[str]:
    impacted: List[str] = []
    for detail in node_details:
        file_path = detail.get('file_path')
        if isinstance(file_path, str) and file_path and file_path not in impacted:
            impacted.append(file_path)
    for file_path in fallback_files:
        if isinstance(file_path, str) and file_path and file_path not in impacted:
            impacted.append(file_path)
    return impacted


def _resolve_callable_from_report(project_path: str, symbol: str):
    report = analysis_service._resolve_report_cached(project_path, allow_global_fallback=False)
    if not report or not symbol:
        return None
    target = str(symbol).strip()
    if '.' in target:
        class_name, method_name = target.rsplit('.', 1)
        class_info = report.classes.get(class_name)
        if class_info and method_name in class_info.methods:
            return class_info.methods[method_name]
    for func_info in getattr(report, 'functions', []) or []:
        if func_info.name == target or getattr(func_info, 'signature', None) == target:
            return func_info
    return None


def _build_snippet_blocks(project_path: str, selected_path: Dict[str, Any]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for symbol in (selected_path.get('function_chain') or selected_path.get('path') or [])[:3]:
        if not isinstance(symbol, str):
            continue
        info = _resolve_callable_from_report(project_path, symbol)
        if not info:
            continue
        file_path = getattr(getattr(info, 'source_location', None), 'file_path', None)
        line_start = getattr(getattr(info, 'source_location', None), 'line_start', None)
        line_end = getattr(getattr(info, 'source_location', None), 'line_end', None)
        source_code = getattr(info, 'source_code', None)
        if not source_code:
            continue
        blocks.append({
            'file_path': file_path or 'unknown',
            'action': 'replace',
            'anchor': symbol,
            'line_start': line_start,
            'line_end': line_end,
            'reason': '命中主功能路径中的关键函数，优先以原函数为修改锚点',
            'before': source_code,
            'after_hint': '在当前函数基础上修改，而不是脱离原函数重新生成',
            'code': source_code,
        })
    return blocks


def _build_modify_existing_template(block: Dict[str, Any]) -> str:
    before = str(block.get('before') or '').rstrip()
    anchor = str(block.get('anchor') or 'target_symbol')
    line_start = block.get('line_start')
    line_end = block.get('line_end')
    line_hint = f"lines {line_start}-{line_end}" if line_start and line_end else 'the matched block'
    return (
        f"# Modify the existing implementation around `{anchor}`\n"
        f"# Suggested edit target: {line_hint}\n"
        f"# Keep the original structure and edit only the necessary logic.\n"
        f"# Recommended action: preserve function signature and change only the affected branch/logic.\n"
        f"# BEFORE\n{before}\n\n"
        f"# AFTER (edit this block directly)\n"
        f"{before}\n"
    )


def _build_write_new_code_scaffold(block: Dict[str, Any]) -> str:
    anchor = str(block.get('anchor') or 'target_anchor')
    file_path = str(block.get('file_path') or 'new_module.py')
    return (
        f"# Add new code around `{anchor}` in `{file_path}`\n"
        f"# Reuse the surrounding conventions and naming style.\n"
        f"def new_logic_for_{anchor.replace('.', '_')}(context):\n"
        f"    # TODO: implement new behavior based on the selected path\n"
        f"    pass\n"
    )


def _apply_snippet_templates(task_mode: str, snippet_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    templated: List[Dict[str, Any]] = []
    for block in snippet_blocks:
        item = dict(block)
        if task_mode == 'modify_existing':
            item['code'] = _build_modify_existing_template(item)
        else:
            item['code'] = _build_write_new_code_scaffold(item)
        templated.append(item)
    return templated


def _build_evidence_based_snippets(node_details: List[Dict[str, Any]], task_mode: str) -> List[Dict[str, Any]]:
    snippets: List[Dict[str, Any]] = []
    for detail in node_details[:3]:
        source = ((detail.get('source') or {}).get('snippet') if isinstance(detail.get('source'), dict) else None)
        if not isinstance(source, str) or not source.strip():
            continue
        snippets.append({
            'file_path': detail.get('file_path') or 'unknown',
            'action': 'insert_after' if task_mode == 'write_new_code' else 'replace',
            'anchor': detail.get('display_name') or detail.get('entity_id') or 'unknown',
            'line_start': detail.get('line_start'),
            'line_end': detail.get('line_end'),
            'reason': '未拿到完整主路径源码时，退回到证据节点源码片段',
            'before': source,
            'after_hint': '优先参考该证据节点的现有实现做增量修改',
            'node_capabilities': {
                'has_cfg': detail.get('has_cfg'),
                'has_dfg': detail.get('has_dfg'),
                'has_io': detail.get('has_io'),
            },
            'code': source,
        })
    return snippets


def _build_write_new_code_template(retrieval_bundle: Dict[str, Any]) -> Dict[str, Any]:
    selected_path = retrieval_bundle.get('selected_path') or {}
    anchor = (selected_path.get('function_chain') or ['待定位'])[0]
    file_path = (retrieval_bundle.get('impacted_files') or ['待定位'])[0]
    action = 'insert_after' if file_path not in {'待定位', '', None} else 'create_file'
    return {
        'file_path': file_path,
        'action': action,
        'anchor': anchor,
        'line_start': None,
        'line_end': None,
        'reason': '当前任务是基于已有代码写新代码，优先沿主路径锚点新增逻辑；若无现成文件则创建新文件',
        'before': '',
        'after_hint': '在该锚点后新增函数、分支或流程封装代码；若为 create_file 则以新模块形式落地',
        'code': _build_write_new_code_scaffold({'anchor': anchor}),
    }


def _infer_edit_action(task_mode: str, index: int, block: Dict[str, Any], retrieval_bundle: Dict[str, Any]) -> str:
    if task_mode == 'write_new_code':
        file_path = str(block.get('file_path') or '')
        if not file_path or file_path == '待定位':
            return 'create_file'
        return 'insert_after' if index == 0 else 'insert_before'
    if block.get('line_start') and block.get('line_end'):
        return 'replace'
    if (retrieval_bundle.get('selected_path') or {}).get('function_chain'):
        return 'insert_after'
    return 'replace'


def _infer_edit_priority(index: int, selection_mode: str) -> str:
    if selection_mode == 'path_analyses':
        return 'high' if index == 0 else 'medium'
    return 'medium' if index == 0 else 'low'


def _build_execution_summary(task_mode: str, retrieval_bundle: Dict[str, Any], edit_plan: List[Dict[str, Any]]) -> Dict[str, Any]:
    selected_path = retrieval_bundle.get('selected_path') or {}
    return {
        'task_mode': task_mode,
        'selection_mode': retrieval_bundle.get('selection_mode'),
        'selection_reason': retrieval_bundle.get('selection_reason'),
        'selected_partition_id': retrieval_bundle.get('selected_partition_id'),
        'path_anchor': (selected_path.get('function_chain') or [None])[0],
        'edit_targets': len(edit_plan),
        'requires_manual_refinement': any(item.get('file_path') in {None, '', '待定位'} for item in edit_plan),
    }


def _build_edit_plan(task_mode: str, retrieval_bundle: Dict[str, Any], snippet_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    selected_path = retrieval_bundle.get('selected_path') or {}
    selection_mode = retrieval_bundle.get('selection_mode') or 'unknown'
    edit_plan: List[Dict[str, Any]] = []

    for index, block in enumerate(snippet_blocks):
        action = _infer_edit_action(task_mode, index, block, retrieval_bundle)
        edit_plan.append({
            'file_path': block.get('file_path'),
            'action': block.get('action') or action,
            'anchor': block.get('anchor'),
            'line_start': block.get('line_start'),
            'line_end': block.get('line_end'),
            'reason': block.get('reason') or ('基于主路径关键节点生成' if selection_mode == 'path_analyses' else '基于回退证据生成'),
            'priority': _infer_edit_priority(index, selection_mode),
            'after_hint': block.get('after_hint'),
        })

    if not edit_plan and selected_path:
        chain = selected_path.get('function_chain') or []
        if chain:
            edit_plan.append({
                'file_path': (retrieval_bundle.get('impacted_files') or ['待定位'])[0],
                'action': 'insert_after' if task_mode == 'write_new_code' else 'replace',
                'anchor': chain[0],
                'line_start': None,
                'line_end': None,
                'reason': '已命中功能路径，但还需要进一步定位精确源码锚点',
                'priority': 'high',
                'after_hint': '先围绕该锚点落位，再细化真实代码内容',
            })
    return edit_plan


def _build_retrieval_bundle(project_path: str, user_query: str, preferred_partition_id: Optional[str] = None, selected_node: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    evidence = _extract_search_evidence(user_query, project_path)
    candidate_partition_ids = _extract_candidate_partition_ids(evidence, preferred_partition_id)
    candidate_partition_ids = _augment_candidate_partitions_from_selected_node(
        project_path,
        selected_node or {},
        preferred_partition_id,
        candidate_partition_ids,
    )
    partition_id, partition_payload, selected_path, candidate_paths = _pick_best_path(
        user_query,
        project_path,
        candidate_partition_ids=candidate_partition_ids,
        selected_node=selected_node,
    )
    if not candidate_paths:
        candidate_paths = _build_search_fallback_candidates(evidence)
    if not selected_path and candidate_paths:
        selected_path = dict(candidate_paths[0])
        selected_path.setdefault('path', selected_path.get('function_chain') or [])
        selected_path.setdefault('deep_analysis_status', 'search_fallback')

    evidence_node_details = _build_node_details(project_path, evidence)
    selected_source = str(selected_path.get('source') or (selected_path.get('semantics') or {}).get('source') or '').strip() if isinstance(selected_path, dict) else ''
    selection_mode = 'path_analyses' if selected_path and selected_source != 'search_fallback' else 'search_fallback'
    selection_reason = 'hybrid_search_match'
    if preferred_partition_id and partition_id == preferred_partition_id:
        selection_reason = 'preferred_partition_match'
    elif selected_node and partition_id in candidate_partition_ids:
        selection_reason = 'selected_node_partition_match'

    if not selected_path and not evidence:
        selection_mode = 'project_scoped_miss'
        selection_reason = 'project_evidence_unavailable'

    chain_node_details = _build_path_node_details(project_path, selected_path, evidence_node_details)
    node_details = chain_node_details
    hierarchy_cached = analysis_service._resolve_function_hierarchy_cached(project_path) or {}

    fallback_impacted_files: List[str] = []
    for item in evidence[:5]:
        file_path = item.get('file') or item.get('file_path')
        if isinstance(file_path, str) and file_path and file_path not in fallback_impacted_files:
            fallback_impacted_files.append(file_path)

    impacted_files = _collect_impacted_files_from_path(node_details, fallback_impacted_files)

    retrieval_bundle = {
        'type': 'RetrievalBundle',
        'target_repo': project_path,
        'query_summary': user_query,
        'selected_partition_id': partition_id,
        'candidate_partition_ids': candidate_partition_ids,
        'selected_partition': partition_payload,
        'selected_path': selected_path,
        'candidate_paths': candidate_paths,
        'evidence': evidence,
        'node_details': node_details,
        'chain_node_details': chain_node_details,
        'impacted_files': impacted_files,
        'selection_mode': selection_mode,
        'selection_reason': selection_reason,
        'confidence': 'high' if partition_id and selected_path and selection_mode == 'path_analyses' else 'medium' if selected_path else 'low',
        'text_evidence': {
            'flat_hits': evidence,
        },
        'path_evidence': {
            'selected_path': selected_path,
            'candidate_paths': candidate_paths,
            'path_analysis_info': partition_payload.get('path_analysis_info') or {},
        },
        'call_chain_evidence': {
            'call_chain_analysis': selected_path.get('call_chain_analysis') if isinstance(selected_path, dict) else {},
            'highlight_config': selected_path.get('highlight_config') if isinstance(selected_path, dict) else {},
            'call_graph': partition_payload.get('call_graph') or {},
        },
        'functional_context': {
            'entry_points_shadow': hierarchy_cached.get('entry_points_shadow') or {},
            'process_shadow': hierarchy_cached.get('process_shadow') or {},
            'community_shadow': hierarchy_cached.get('community_shadow') or {},
        },
    }
    retrieval_bundle['evidence_packet'] = _build_evidence_packet(retrieval_bundle)

    return retrieval_bundle


def _build_evidence_verdict(retrieval_bundle: Dict[str, Any]) -> Dict[str, Any]:
    evidence_packet = retrieval_bundle.get('evidence_packet') or {}
    summary = evidence_packet.get('summary') or {}
    review = evidence_packet.get('review') or {}
    selected_path = retrieval_bundle.get('selected_path') or {}
    coverage = summary.get('coverage') or {}
    has_primary = bool(summary.get('primary_ids'))
    has_path = bool(selected_path) and coverage.get('functional_path', 0) > 0
    code_first_ready = coverage.get('text', 0) >= 2 and bool(retrieval_bundle.get('impacted_files') or [])
    has_anchor = bool(review.get('anchor_ready')) and bool(review.get('impacted_files') or [])
    approved = has_primary and (has_path or code_first_ready) and has_anchor
    selection_mode = retrieval_bundle.get('selection_mode') or 'unknown'
    selection_reason = retrieval_bundle.get('selection_reason') or 'unknown'
    refinement_needed = []
    if not has_primary:
        refinement_needed.append('缺少可直接引用的主证据')
    if not has_path:
        if not code_first_ready:
            refinement_needed.append('缺少稳定功能路径')
        else:
            refinement_needed.append('功能路径不稳定，已使用代码证据回退')
    if not has_anchor:
        refinement_needed.append('缺少可落位的编辑锚点')
    return {
        'type': 'EvidenceVerdict',
        'approved': approved,
        'verdict': 'approve' if approved else 'requery',
        'reasons': [
            '已找到代表性功能路径' if approved else '未找到足够明确的功能路径',
            f'命中模式: {selection_mode}',
            f'命中原因: {selection_reason}',
            f"证据覆盖: text={coverage.get('text', 0)}, graph={coverage.get('graph', 0)}, path={coverage.get('functional_path', 0)}, call_chain={coverage.get('call_chain', 0)}",
        ],
        'confidence': summary.get('confidence') or retrieval_bundle.get('confidence', 'low'),
        'primary_evidence_ids': summary.get('primary_ids') or [],
        'supporting_evidence_ids': summary.get('supporting_ids') or [],
        'refinement_needed': refinement_needed,
        'refinement_hint': '优先补强路径锚点与源码级主证据，再继续生成代码方案' if refinement_needed else None,
    }


def _build_solution_packet(
    project_path: str,
    user_query: str,
    task_mode: str,
    retrieval_bundle: Dict[str, Any],
    intent_packet: Optional[Dict[str, Any]] = None,
    evidence_verdict: Optional[Dict[str, Any]] = None,
    opencode_enabled: bool = True,
) -> Dict[str, Any]:
    selected_path = retrieval_bundle.get('selected_path') or {}
    advisor_packet_raw = retrieval_bundle.get('advisor_packet')
    advisor_packet: Dict[str, Any] = advisor_packet_raw if isinstance(advisor_packet_raw, dict) else {}
    evidence_packet = retrieval_bundle.get('evidence_packet') or {}
    evidence_review = evidence_packet.get('review') or {}
    verdict = evidence_verdict or {}
    approved = bool(verdict.get('approved')) if verdict else True
    if not approved:
        analysis_payload = {
            'summary': '当前证据尚不足以安全产出高精度代码方案',
            'key_reasoning': list(verdict.get('reasons') or []),
            'impacted_files': evidence_review.get('impacted_files') or retrieval_bundle.get('impacted_files') or [],
            'selected_path': selected_path,
            'candidate_paths': evidence_review.get('candidate_paths') or retrieval_bundle.get('candidate_paths') or [],
            'chain_node_details': retrieval_bundle.get('chain_node_details') or retrieval_bundle.get('node_details') or [],
            'selection_mode': retrieval_bundle.get('selection_mode'),
            'selection_reason': retrieval_bundle.get('selection_reason'),
            'evidence_packet': evidence_packet,
            'intent_review': (intent_packet or {}).get('review') or {},
        }
        analysis_payload = _merge_advisor_context_into_analysis(analysis_payload, advisor_packet)
        validation_notes = [verdict.get('refinement_hint') or '证据不足，暂不生成代码片段']
        opencode_result = {
            'type': 'OpenCodeKernelResult',
            'status': 'skipped',
            'reason': 'evidence_not_approved',
            'duration_ms': 0,
        }
        return {
            'type': 'SolutionPacket',
            'task_mode': task_mode,
            'analysis': analysis_payload,
            'execution_summary': _build_execution_summary(task_mode, retrieval_bundle, []),
            'edit_plan': [],
            'snippet_blocks': [],
            'validation': validation_notes,
            'opencode_kernel': opencode_result,
            'output_protocol': _build_output_protocol(
                task_mode,
                analysis_payload,
                [],
                validation_notes,
                verdict,
                (intent_packet or {}).get('review') or {},
                advisor_packet=advisor_packet,
                opencode_result=opencode_result,
            ),
        }

    snippet_blocks = _build_snippet_blocks(project_path, selected_path)
    if not snippet_blocks:
        snippet_blocks = _build_evidence_based_snippets(retrieval_bundle.get('node_details') or [], task_mode)
    if task_mode == 'write_new_code' and not snippet_blocks:
        snippet_blocks = [_build_write_new_code_template(retrieval_bundle)]
    if not snippet_blocks and selected_path:
        snippet_blocks.append({
            'file_path': (retrieval_bundle.get('impacted_files') or ['待定位'])[0],
            'action': 'insert_after' if task_mode == 'write_new_code' else 'replace',
            'anchor': (selected_path.get('function_chain') or ['待定位'])[0],
            'line_start': None,
            'line_end': None,
            'reason': '已命中功能路径，但当前仅能给出占位草案，需要继续提升精度',
            'before': '',
            'after_hint': '继续围绕该锚点补足高精度代码',
            'code': _build_write_new_code_scaffold({'anchor': (selected_path.get('function_chain') or ['待定位'])[0]}) if task_mode == 'write_new_code' else '# Modify the existing implementation here\n# TODO: refine the replacement block\npass',
        })

    snippet_blocks = _apply_snippet_templates(task_mode, snippet_blocks)

    edit_plan = _build_edit_plan(task_mode, retrieval_bundle, snippet_blocks)

    analysis_payload = {
        'summary': selected_path.get('path_description') or '已基于当前代码上下文生成方案',
        'key_reasoning': [
            f"主路径: {' -> '.join(selected_path.get('function_chain') or [])}" if selected_path else '当前未命中稳定主路径，使用回退证据链'
        ],
        'impacted_files': retrieval_bundle.get('impacted_files') or [],
        'selected_path': selected_path,
        'candidate_paths': retrieval_bundle.get('candidate_paths') or [],
        'chain_node_details': retrieval_bundle.get('chain_node_details') or retrieval_bundle.get('node_details') or [],
        'selection_mode': retrieval_bundle.get('selection_mode'),
        'selection_reason': retrieval_bundle.get('selection_reason'),
        'evidence_packet': evidence_packet,
        'intent_review': (intent_packet or {}).get('review') or {},
    }
    analysis_payload = _merge_advisor_context_into_analysis(analysis_payload, advisor_packet)

    opencode_seed = {'opencode': {'system_context': _build_opencode_system_context(task_mode, analysis_payload, _as_dict(analysis_payload.get('advisor')))}}
    opencode_result = _run_opencode_kernel_bridge(
        project_path=project_path,
        user_query=user_query,
        task_mode=task_mode,
        retrieval_bundle=retrieval_bundle,
        advisor_packet=advisor_packet,
        output_protocol=opencode_seed,
        enabled=bool(opencode_enabled),
        model=_opencode_kernel_model(),
        agent=_opencode_kernel_agent(),
        timeout_seconds=_opencode_kernel_timeout_seconds(),
    )

    kernel_snippet_blocks = [item for item in _as_list(opencode_result.get('snippet_blocks')) if isinstance(item, dict)]
    if kernel_snippet_blocks:
        snippet_blocks = _apply_snippet_templates(task_mode, kernel_snippet_blocks)

    kernel_edit_plan = [item for item in _as_list(opencode_result.get('edit_plan')) if isinstance(item, dict)]
    if kernel_edit_plan:
        edit_plan = kernel_edit_plan

    kernel_validation = [str(item).strip() for item in _as_list(opencode_result.get('validation_commands')) if str(item).strip()]
    validation_notes = ['继续结合真实任务测试提高路径命中率和代码片段精度']
    for item in kernel_validation:
        if item and item not in validation_notes:
            validation_notes.append(item)
    return {
        'type': 'SolutionPacket',
        'task_mode': task_mode,
        'analysis': analysis_payload,
        'execution_summary': _build_execution_summary(task_mode, retrieval_bundle, edit_plan),
        'edit_plan': edit_plan,
        'snippet_blocks': snippet_blocks,
        'validation': validation_notes,
        'opencode_kernel': opencode_result,
        'output_protocol': _build_output_protocol(
            task_mode,
            analysis_payload,
            snippet_blocks,
            validation_notes,
            verdict,
            (intent_packet or {}).get('review') or {},
            advisor_packet=advisor_packet,
            opencode_result=opencode_result,
        ),
    }


def _run_multi_agent_session(
    session_id: str,
    project_path: str,
    user_query: str,
    task_mode: str,
    preferred_partition_id: Optional[str] = None,
    selected_node: Optional[Dict[str, Any]] = None,
    clarification_context: Optional[Dict[str, Any]] = None,
    swarm_enabled: bool = True,
    output_root: Optional[str] = None,
    auto_apply_output: bool = False,
) -> None:
    try:
        _update_multi_agent_session(session_id, status='running')
        _emit_multi_agent_conversation_event(
            session_id,
            'multi_agent.started',
            {
                'projectPath': project_path,
                'taskMode': task_mode,
                'query': user_query,
            },
        )
        swarm_client = _create_swarm_llm_client() if swarm_enabled else None
        deepseek_settings = get_deepseek_settings()
        swarm_packet: Dict[str, Any] = {
            'enabled': bool(swarm_enabled),
            'llm_enabled': bool(swarm_client is not None),
            'model': str(deepseek_settings.get('model') or ''),
            'agents': {},
            'consensus': {},
            'updatedAt': _utcnow_iso(),
        }
        shared_swarm_context = {
            'project_path': project_path,
            'user_query': user_query,
            'task_mode': task_mode,
            'preferred_partition_id': preferred_partition_id,
            'selected_node': selected_node or {},
            'clarification_context': clarification_context or {},
        }
        prioritized_libraries = _normalize_prioritized_libraries((clarification_context or {}).get('prioritizedExperienceLibraries'))
        experience_output_root = _resolve_project_experience_output_root(project_path)
        experience_paths_dir = _resolve_advisor_experience_paths_dir(experience_output_root)

        intent_packet = _make_intent_packet(user_query, project_path, task_mode, clarification_context)
        if preferred_partition_id:
            intent_packet['preferred_partition_id'] = preferred_partition_id
        if selected_node:
            intent_packet['selected_node'] = selected_node

        taizi_swarm = _run_swarm_agent_step(
            swarm_client,
            'taizi',
            {
                'intent_packet': intent_packet,
            },
            shared_swarm_context,
        )
        swarm_packet['agents']['taizi'] = taizi_swarm
        swarm_packet['updatedAt'] = _utcnow_iso()
        _emit_multi_agent_conversation_event(
            session_id,
            'swarm.agent.updated',
            {
                'agent': 'taizi',
                'decision': taizi_swarm,
            },
        )

        intent_stage_output = _build_stage_output_packet('taizi', intent_packet)
        stage_outputs = {'taizi': intent_stage_output}
        _record_stage_transition(session_id, 'taizi', _build_stage_message('taizi', intent_packet))

        _update_multi_agent_session(
            session_id,
            packets={
                'intent_packet': intent_packet,
                'stage_outputs': stage_outputs,
                'swarm_packet': swarm_packet,
            },
        )
        workbench_payload = _ensure_workbench_ready(project_path)
        retrieval_bundle = _build_retrieval_bundle(project_path, user_query, preferred_partition_id=preferred_partition_id, selected_node=selected_node)

        session_snapshot = _get_multi_agent_session(session_id) or {}
        advisor_enabled = _is_advisor_sidecar_enabled({'advisor_enabled': (session_snapshot or {}).get('advisorEnabled')})
        opencode_enabled = _is_opencode_kernel_enabled({'opencode_enabled': (session_snapshot or {}).get('opencodeEnabled')})
        session_output_root = _normalize_output_root((session_snapshot or {}).get('outputRoot'))
        request_output_root = _normalize_output_root(output_root)
        effective_output_root = request_output_root or session_output_root
        effective_auto_apply_output = bool(auto_apply_output or (session_snapshot or {}).get('autoApplyOutput'))
        advisor_packet = _build_disabled_advisor_packet()
        advisor_decision = 'disabled'
        advisor_reason = 'feature_disabled'
        advisor_signals: Dict[str, Any] = {}
        if advisor_enabled:
            should_invoke, advisor_reason, advisor_signals = _should_invoke_advisor(user_query, task_mode, retrieval_bundle)
            if should_invoke:
                advisor_packet = _run_advisor_sidecar(
                    project_path,
                    user_query,
                    retrieval_bundle,
                    prioritized_libraries=prioritized_libraries,
                    experience_paths_dir=experience_paths_dir,
                )
                advisor_decision = 'invoked'
            else:
                advisor_packet = _build_skipped_advisor_packet(advisor_reason, advisor_signals)
                advisor_decision = 'skipped'

        invocation_payload = {
            'decision': advisor_decision,
            'reason': advisor_reason,
            'signals': advisor_signals,
        }
        if isinstance(advisor_packet, dict):
            advisor_packet['role'] = advisor_packet.get('role') or dict(ADVISOR_ROLE_PROFILE)
            advisor_packet['invocation'] = invocation_payload

        retrieval_bundle['advisor_packet'] = advisor_packet
        _emit_multi_agent_conversation_event(
            session_id,
            'advisor.sidecar.updated',
            {
                'status': advisor_packet.get('status'),
                'enabled': advisor_enabled,
                'mode': advisor_packet.get('mode'),
                'decision': advisor_decision,
                'reason': advisor_reason,
            },
        )

        evidence_packet = retrieval_bundle.get('evidence_packet') or {}

        zhongshu_swarm = _run_swarm_agent_step(
            swarm_client,
            'zhongshu',
            {
                'retrieval_summary': _summarize_retrieval_for_swarm(retrieval_bundle),
                'evidence_packet_summary': {
                    'summary': evidence_packet.get('summary') if isinstance(evidence_packet.get('summary'), dict) else {},
                    'review': evidence_packet.get('review') if isinstance(evidence_packet.get('review'), dict) else {},
                },
            },
            shared_swarm_context,
        )
        swarm_packet['agents']['zhongshu'] = zhongshu_swarm
        swarm_packet['updatedAt'] = _utcnow_iso()
        _emit_multi_agent_conversation_event(
            session_id,
            'swarm.agent.updated',
            {
                'agent': 'zhongshu',
                'decision': zhongshu_swarm,
            },
        )

        evidence_stage_output = _build_stage_output_packet('zhongshu', evidence_packet)
        stage_outputs['zhongshu'] = evidence_stage_output

        packets = {
            'intent_packet': intent_packet,
            'retrieval_bundle': retrieval_bundle,
            'evidence_packet': evidence_packet,
            'advisor_packet': advisor_packet,
            'stage_outputs': stage_outputs,
            'swarm_packet': swarm_packet,
        }
        _update_multi_agent_session(session_id, packets=packets)
        _record_stage_transition(session_id, 'zhongshu', _build_stage_message('zhongshu', evidence_packet))
        evidence_verdict = _build_evidence_verdict(retrieval_bundle)

        menxia_swarm = _run_swarm_agent_step(
            swarm_client,
            'menxia',
            {
                'evidence_verdict': evidence_verdict,
                'retrieval_summary': _summarize_retrieval_for_swarm(retrieval_bundle),
            },
            shared_swarm_context,
        )
        swarm_packet['agents']['menxia'] = menxia_swarm
        swarm_packet['updatedAt'] = _utcnow_iso()
        _emit_multi_agent_conversation_event(
            session_id,
            'swarm.agent.updated',
            {
                'agent': 'menxia',
                'decision': menxia_swarm,
            },
        )

        packets['evidence_verdict'] = evidence_verdict
        menxia_stage_output = _build_stage_output_packet('menxia', evidence_verdict)
        stage_outputs['menxia'] = menxia_stage_output
        packets['stage_outputs'] = stage_outputs
        packets['swarm_packet'] = swarm_packet

        _update_multi_agent_session(session_id, packets=packets)
        _record_stage_transition(session_id, 'menxia', _build_stage_message('menxia', evidence_verdict))
        solution_packet = _build_solution_packet(
            project_path,
            user_query,
            task_mode,
            retrieval_bundle,
            intent_packet=intent_packet,
            evidence_verdict=evidence_verdict,
            opencode_enabled=opencode_enabled,
        )
        output_write = _apply_solution_packet_output(
            project_path,
            solution_packet,
            effective_output_root,
            effective_auto_apply_output,
        )
        solution_packet['output_write'] = output_write
        _emit_multi_agent_conversation_event(
            session_id,
            'multi_agent.output_write',
            {
                'enabled': output_write.get('enabled'),
                'outputRoot': output_write.get('outputRoot'),
                'writtenCount': output_write.get('writtenCount'),
                'failedCount': output_write.get('failedCount'),
                'reason': output_write.get('reason'),
            },
        )

        shangshu_swarm = _run_swarm_agent_step(
            swarm_client,
            'shangshu',
            {
                'solution_summary': _summarize_solution_for_swarm(solution_packet),
                'evidence_verdict': evidence_verdict,
            },
            shared_swarm_context,
        )
        swarm_packet['agents']['shangshu'] = shangshu_swarm
        swarm_agents_raw = swarm_packet.get('agents')
        swarm_agents: Dict[str, Any] = swarm_agents_raw if isinstance(swarm_agents_raw, dict) else {}
        swarm_packet['consensus'] = _build_swarm_consensus(swarm_agents)
        swarm_packet['updatedAt'] = _utcnow_iso()
        _emit_multi_agent_conversation_event(
            session_id,
            'swarm.agent.updated',
            {
                'agent': 'shangshu',
                'decision': shangshu_swarm,
            },
        )
        _emit_multi_agent_conversation_event(
            session_id,
            'swarm.consensus.updated',
            {
                'consensus': swarm_packet.get('consensus') if isinstance(swarm_packet.get('consensus'), dict) else {},
                'model': swarm_packet.get('model'),
                'llm_enabled': swarm_packet.get('llm_enabled'),
            },
        )

        packets['solution_packet'] = solution_packet
        shangshu_stage_output = _build_stage_output_packet('shangshu', solution_packet)
        stage_outputs['shangshu'] = shangshu_stage_output
        packets['stage_outputs'] = stage_outputs
        packets['swarm_packet'] = swarm_packet

        _update_multi_agent_session(
            session_id,
            status='completed',
            packets=packets,
            result={
                'workbench': workbench_payload,
                'intent_packet': intent_packet,
                'retrieval_bundle': retrieval_bundle,
                'evidence_packet': evidence_packet,
                'advisor_packet': advisor_packet,
                'evidence_verdict': evidence_verdict,
                'solution_packet': solution_packet,
                'output_protocol': solution_packet.get('output_protocol') or {},
                'opencode_kernel': solution_packet.get('opencode_kernel') if isinstance(solution_packet.get('opencode_kernel'), dict) else {},
                'output_write': output_write,
                'stage_outputs': stage_outputs,
                'swarm_packet': swarm_packet,
            },
            completedAt=_utcnow_iso(),
        )
        _record_stage_transition(session_id, 'shangshu', _build_stage_message('shangshu', solution_packet))
        _record_stage_transition(session_id, 'done')
        _emit_multi_agent_conversation_event(
            session_id,
            'multi_agent.completed',
            {
                'taskMode': task_mode,
                'hasSolution': bool(solution_packet),
            },
        )
    except Exception as exc:
        _update_multi_agent_session(
            session_id,
            status='failed',
            error=str(exc),
            completedAt=_utcnow_iso(),
        )
        _record_stage_transition(session_id, 'failed', f'三省六部会话失败: {exc}')
        _emit_multi_agent_conversation_event(
            session_id,
            'multi_agent.failed',
            {
                'error': str(exc),
            },
        )


def api_multi_agent_session_start():
    data = request.json or {}
    project_path = _normalize_project_path(data.get('project_path'))
    user_query = str(data.get('query') or '').strip()
    task_mode = str(data.get('task_mode') or 'modify_existing').strip() or 'modify_existing'
    preferred_partition_id = str(data.get('partition_id') or '').strip() or None
    selected_node = _normalize_selected_node(data.get('selected_node'))
    clarification_context = data.get('clarification_context') if isinstance(data.get('clarification_context'), dict) else {}
    swarm_enabled = bool(data.get('swarm_enabled', True))
    advisor_enabled_raw = data.get('advisor_enabled') if 'advisor_enabled' in data else data.get('advisorEnabled')
    advisor_enabled = _is_advisor_sidecar_enabled({'advisor_enabled': advisor_enabled_raw})
    opencode_enabled_raw = data.get('opencode_enabled') if 'opencode_enabled' in data else data.get('opencodeEnabled')
    opencode_enabled = _is_opencode_kernel_enabled({'opencode_enabled': opencode_enabled_raw})
    conversation_id = str(data.get('conversation_id') or '').strip() or None
    raw_output_root = data.get('output_root')
    output_root = _normalize_output_root(raw_output_root)
    auto_apply_output = bool(data.get('auto_apply_output', False))
    if not user_query:
        return jsonify({'error': 'query 不能为空'}), 400
    if not os.path.isdir(project_path):
        return jsonify({'error': f'project_path 不存在或不是目录: {project_path}'}), 400
    if raw_output_root is not None and str(raw_output_root).strip() and not output_root:
        return jsonify({'error': 'output_root 必须是绝对路径'}), 400
    if auto_apply_output and not output_root:
        return jsonify({'error': '开启 auto_apply_output 时必须提供 output_root'}), 400

    payload = _create_multi_agent_session(
        project_path,
        user_query,
        task_mode,
        clarification_context,
        swarm_enabled=swarm_enabled,
        conversation_id=conversation_id,
        advisor_enabled=advisor_enabled,
        opencode_enabled=opencode_enabled,
        output_root=output_root,
        auto_apply_output=auto_apply_output,
    )
    thread = threading.Thread(
        target=_run_multi_agent_session,
        args=(
            payload['sessionId'],
            project_path,
            user_query,
            task_mode,
            preferred_partition_id,
            selected_node,
            clarification_context,
            swarm_enabled,
            output_root,
            auto_apply_output,
        ),
        daemon=True,
    )
    thread.start()
    return jsonify({
        'sessionId': payload['sessionId'],
        'projectPath': project_path,
        'status': payload['status'],
        'stage': payload['stage'],
        'message': payload['message'],
        'swarmEnabled': payload.get('swarmEnabled', swarm_enabled),
        'advisorEnabled': payload.get('advisorEnabled', advisor_enabled),
        'opencodeEnabled': payload.get('opencodeEnabled', opencode_enabled),
        'conversationId': payload.get('conversationId'),
        'outputRoot': payload.get('outputRoot'),
        'autoApplyOutput': payload.get('autoApplyOutput', auto_apply_output),
    })


def _confidence_level(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 'medium'
    if numeric >= 0.8:
        return 'high'
    if numeric >= 0.55:
        return 'medium'
    return 'low'


def _to_feature_flag(raw_value: Any, default: bool = False) -> bool:
    if raw_value is None:
        return bool(default)
    normalized = str(raw_value).strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    return bool(default)


def _is_front_door_conversation_bridge_enabled(payload: Dict[str, Any]) -> bool:
    explicit = payload.get('use_conversation_core')
    if explicit is not None:
        return _to_feature_flag(explicit, default=False)
    env_flag = os.getenv('FH_FRONT_DOOR_CONVERSATION_BRIDGE', '0')
    return _to_feature_flag(env_flag, default=False)


def _legacy_front_door_deprecation_info() -> Dict[str, Any]:
    return {
        'deprecated': True,
        'replacement': {
            'start': '/api/conversations/session/start',
            'status': '/api/conversations/session/<session_id>/status',
            'result': '/api/conversations/session/<session_id>/result',
            'reply': '/api/conversations/<conversation_id>/reply',
            'events': '/api/conversations/<conversation_id>/events',
        },
        'notice': 'front_door/route 已进入兼容模式，请迁移到 conversations API。',
    }


def _is_legacy_front_door_enabled() -> bool:
    env_flag = os.getenv('FH_ENABLE_LEGACY_FRONT_DOOR', '1')
    return _to_feature_flag(env_flag, default=True)


def _legacy_front_door_response(payload: Dict[str, Any], status_code: int = 200):
    response = jsonify(payload)
    response.headers['X-CreateGraph-Legacy-API'] = 'front_door/route'
    response.headers['X-CreateGraph-Replacement-API'] = '/api/conversations/session/start'
    response.status_code = status_code
    return response


def api_front_door_route():
    if not _is_legacy_front_door_enabled():
        return _legacy_front_door_response(
            {
                'error': 'front_door/route 已停用，请改用 conversations API',
                'legacy': _legacy_front_door_deprecation_info(),
            },
            status_code=410,
        )

    data = request.json or {}
    project_path = _normalize_project_path(data.get('project_path'))
    user_query = str(data.get('query') or '').strip()
    preferred_partition_id = str(data.get('partition_id') or '').strip() or None
    selected_node = _normalize_selected_node(data.get('selected_node'))
    clarification_context = data.get('clarificationContext') if isinstance(data.get('clarificationContext'), dict) else {}
    if not user_query:
        return jsonify({'error': 'query 不能为空'}), 400
    if not os.path.isdir(project_path):
        return jsonify({'error': f'project_path 不存在或不是目录: {project_path}'}), 400

    decision = QuestionDetector.assess_clarification_need(
        user_query,
        has_context=bool(preferred_partition_id or selected_node),
        clarification_context=clarification_context,
    )
    route = str(decision.get('route') or 'modify_existing')
    task_mode = decision.get('task_mode') or 'modify_existing'
    confidence = _confidence_level(decision.get('confidence'))
    if route == 'general_chat':
        return _legacy_front_door_response({
            'intentGuess': 'general_chat',
            'nextStep': 'send_chat',
            'safeToCodegen': False,
            'confidence': confidence,
            'reason': str(decision.get('reason') or '命中问答路由'),
            'taskMode': None,
            'projectPath': project_path,
            'clarification': decision.get('clarification'),
            'legacy': _legacy_front_door_deprecation_info(),
        })

    if route == 'clarify':
        clarification_payload = dict(decision.get('clarification') or {})
        clarification_payload.setdefault('id', uuid4().hex)
        return _legacy_front_door_response({
            'intentGuess': task_mode,
            'nextStep': 'ask_clarification',
            'safeToCodegen': False,
            'confidence': confidence,
            'reason': str(decision.get('reason') or '需要进一步澄清'),
            'taskMode': task_mode,
            'projectPath': project_path,
            'clarification': clarification_payload,
            'legacy': _legacy_front_door_deprecation_info(),
        })

    return _legacy_front_door_response({
        'intentGuess': task_mode,
        'nextStep': 'start_multi_agent',
        'safeToCodegen': True,
        'confidence': confidence,
        'reason': str(decision.get('reason') or '保持代码修改流'),
        'taskMode': task_mode,
        'projectPath': project_path,
        'clarification': decision.get('clarification'),
        'legacy': _legacy_front_door_deprecation_info(),
    })


def api_multi_agent_session_status(session_id: str):
    payload = _get_multi_agent_session(session_id)
    if not isinstance(payload, dict):
        return jsonify({'error': '未找到三省六部会话'}), 404
    packets_raw = payload.get('packets')
    packets: Dict[str, Any] = packets_raw if isinstance(packets_raw, dict) else {}
    swarm_packet_raw = packets.get('swarm_packet')
    swarm_packet: Dict[str, Any] = swarm_packet_raw if isinstance(swarm_packet_raw, dict) else {}
    advisor_packet_raw = packets.get('advisor_packet')
    advisor_packet: Dict[str, Any] = advisor_packet_raw if isinstance(advisor_packet_raw, dict) else {}
    solution_packet_raw = packets.get('solution_packet')
    solution_packet: Dict[str, Any] = solution_packet_raw if isinstance(solution_packet_raw, dict) else {}
    opencode_kernel_raw = solution_packet.get('opencode_kernel')
    opencode_kernel: Dict[str, Any] = opencode_kernel_raw if isinstance(opencode_kernel_raw, dict) else {}
    stage_history = _build_stage_history_from_task_session(payload)
    if not stage_history:
        stage_history = payload.get('stageHistory') or []

    return jsonify({
        'sessionId': payload.get('sessionId'),
        'projectPath': payload.get('projectPath'),
        'status': payload.get('status'),
        'stage': payload.get('stage'),
        'message': payload.get('message'),
        'swarmEnabled': payload.get('swarmEnabled', True),
        'advisorEnabled': payload.get('advisorEnabled', _is_advisor_sidecar_enabled()),
        'opencodeEnabled': payload.get('opencodeEnabled', _is_opencode_kernel_enabled()),
        'advisor': {
            'status': advisor_packet.get('status') or 'disabled',
            'enabled': advisor_packet.get('enabled', payload.get('advisorEnabled', _is_advisor_sidecar_enabled())),
            'mode': advisor_packet.get('mode'),
            'reason': advisor_packet.get('reason'),
            'recommended': advisor_packet.get('recommended') if isinstance(advisor_packet.get('recommended'), dict) else {},
            'analysis': advisor_packet.get('analysis') if isinstance(advisor_packet.get('analysis'), dict) else {},
            'constraints': advisor_packet.get('constraints') if isinstance(advisor_packet.get('constraints'), dict) else {},
            'sourceTargetsCount': len(_as_list(advisor_packet.get('source_targets'))),
        },
        'opencode': {
            'status': opencode_kernel.get('status') or 'disabled',
            'reason': opencode_kernel.get('reason'),
            'enabled': payload.get('opencodeEnabled', _is_opencode_kernel_enabled()),
            'duration_ms': opencode_kernel.get('duration_ms'),
            'session_id': opencode_kernel.get('session_id'),
            'model': opencode_kernel.get('model'),
            'agent': opencode_kernel.get('agent'),
        },
        'swarm': {
            'enabled': swarm_packet.get('enabled', payload.get('swarmEnabled', True)),
            'llm_enabled': swarm_packet.get('llm_enabled', bool(payload.get('swarmEnabled', True) and has_deepseek_config())),
            'model': swarm_packet.get('model') or str(get_deepseek_settings().get('model') or ''),
            'consensus': swarm_packet.get('consensus') if isinstance(swarm_packet.get('consensus'), dict) else {},
            'agents': swarm_packet.get('agents') if isinstance(swarm_packet.get('agents'), dict) else {},
            'updatedAt': swarm_packet.get('updatedAt'),
        },
        'stageHistory': stage_history,
        'taskSummary': (_load_task_session(payload).get_summary() if payload.get('taskSession') else None),
        'error': payload.get('error'),
        'startedAt': payload.get('startedAt'),
        'updatedAt': payload.get('updatedAt'),
        'completedAt': payload.get('completedAt'),
    })


def api_multi_agent_session_result(session_id: str):
    payload = _get_multi_agent_session(session_id)
    if not payload:
        return jsonify({'error': '未找到三省六部会话'}), 404
    if payload.get('status') == 'failed':
        return jsonify({'error': payload.get('error') or '三省六部会话失败'}), 400
    if payload.get('status') != 'completed':
        return jsonify({'error': '结果尚未就绪'}), 409
    return jsonify(payload.get('result') or {})
