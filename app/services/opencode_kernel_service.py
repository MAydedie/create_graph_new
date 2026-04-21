#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OpenCode kernel bridge service."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _as_text(value: Any) -> str:
    return str(value or '').strip()


def _resolve_opencode_executable() -> str:
    explicit = _as_text(os.getenv('FH_OPENCODE_BIN') or os.getenv('OPENCODE_BIN'))
    if explicit:
        return explicit
    for name in ('opencode', 'opencode.cmd', 'opencode.exe'):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return ''


def _build_opencode_command(executable: str) -> List[str]:
    if not executable:
        return []
    suffix = Path(executable).suffix.lower()
    if suffix in {'.cmd', '.bat'}:
        return ['cmd', '/c', executable, 'run', '--format', 'json']
    return [executable, 'run', '--format', 'json']


def _extract_existing_files(project_path: str, impacted_files: Any, limit: int = 8) -> List[str]:
    root = Path(project_path)
    if not root.exists() or not root.is_dir():
        return []
    files: List[str] = []
    for item in _as_list(impacted_files):
        raw = _as_text(item)
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / raw
        candidate = candidate.resolve()
        if candidate.exists() and candidate.is_file():
            text = str(candidate)
            if text not in files:
                files.append(text)
        if len(files) >= max(1, limit):
            break
    return files


def _safe_json_loads(text: str) -> Dict[str, Any]:
    body = _as_text(text)
    if not body:
        return {}
    try:
        payload = json.loads(body)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        pass
    start = body.find('{')
    end = body.rfind('}')
    if start == -1 or end <= start:
        return {}
    try:
        payload = json.loads(body[start:end + 1])
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _parse_opencode_stdout(stdout: str) -> Dict[str, str]:
    text_chunks: List[str] = []
    session_id = ''
    for raw_line in (stdout or '').splitlines():
        line = raw_line.strip()
        if not line.startswith('{'):
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if not session_id:
            session_id = _as_text(payload.get('sessionID'))
        if payload.get('type') != 'text':
            continue
        part = _as_dict(payload.get('part'))
        text = _as_text(part.get('text'))
        if text:
            text_chunks.append(text)
    return {'session_id': session_id, 'text': '\n'.join(text_chunks).strip()}


def _build_message(user_query: str, task_mode: str, retrieval_bundle: Dict[str, Any], advisor_packet: Dict[str, Any], output_protocol: Dict[str, Any]) -> str:
    selected_path = _as_dict(retrieval_bundle.get('selected_path'))
    system_context = _as_dict(_as_dict(output_protocol.get('opencode')).get('system_context'))
    required_files = [str(item).strip() for item in _as_list(system_context.get('required_files')) if str(item).strip()]

    payload = {
        'task_mode': task_mode,
        'requirement': user_query,
        'selected_path': {
            'path_id': selected_path.get('path_id'),
            'path_name': selected_path.get('path_name'),
            'path_description': selected_path.get('path_description'),
            'function_chain': _as_list(selected_path.get('function_chain'))[:16],
        },
        'impacted_files': [str(item).strip() for item in _as_list(retrieval_bundle.get('impacted_files')) if str(item).strip()][:16],
        'advisor_summary': {
            'what': _as_text(_as_dict(advisor_packet.get('analysis')).get('what')),
            'how': _as_text(_as_dict(advisor_packet.get('analysis')).get('how')),
            'constraint_types': _as_list(_as_dict(advisor_packet.get('constraints')).get('types')),
            'source_targets': _as_list(advisor_packet.get('source_targets'))[:12],
        },
        'required_files': required_files,
        'system_context': system_context,
    }

    instructions = {
        'goal': 'Generate runnable project code now. Advisor context is auxiliary, not authoritative.',
        'must_output_only_json': True,
        'schema': {
            'analysis_summary': 'string',
            'implementation_targets': [{'file_path': 'string', 'purpose': 'string', 'language': 'string', 'anchor_targets': ['string']}],
            'snippet_blocks': [{'file_path': 'string', 'language': 'string', 'reason': 'string', 'action': 'create_file|replace', 'code': 'string'}],
            'validation_commands': ['string'],
        },
        'hard_rules': [
            'Do not ask follow-up questions.',
            'Do not output markdown.',
            'Return exactly one JSON object.',
            'Every snippet_blocks entry must contain full file code.',
            'Keep all file_path values inside repository.',
        ],
    }

    if required_files:
        instructions['hard_rules'].append(f'Include at least {len(required_files)} files in snippet_blocks and cover required_files.')

    return 'You are OpenCode code generator in strict JSON mode. DATA=' + json.dumps(payload, ensure_ascii=True) + ' INSTRUCTIONS=' + json.dumps(instructions, ensure_ascii=True)


def run_opencode_kernel(*, project_path: str, user_query: str, task_mode: str, retrieval_bundle: Dict[str, Any], advisor_packet: Dict[str, Any], output_protocol: Dict[str, Any], enabled: bool, model: str = '', agent: str = 'build', timeout_seconds: int = 150) -> Dict[str, Any]:
    started_at = time.perf_counter()
    if not enabled:
        return {'type': 'OpenCodeKernelResult', 'status': 'disabled', 'reason': 'feature_disabled', 'duration_ms': int((time.perf_counter() - started_at) * 1000)}

    root = Path(project_path)
    if not root.exists() or not root.is_dir():
        return {'type': 'OpenCodeKernelResult', 'status': 'error', 'reason': f'project_path_invalid: {project_path}', 'duration_ms': int((time.perf_counter() - started_at) * 1000)}

    timeout_seconds = max(30, min(int(timeout_seconds or 150), 600))
    attach_files = _extract_existing_files(project_path, retrieval_bundle.get('impacted_files'))
    message = _build_message(user_query, task_mode, retrieval_bundle, advisor_packet, output_protocol)
    temp_message_file = ''
    if len(message) > 1800:
        temp_path = root / '.tmp_opencode_kernel_input.json'
        try:
            temp_path.write_text(json.dumps({'message': message}, ensure_ascii=True), encoding='utf-8')
            attach_files.append(str(temp_path))
            temp_message_file = str(temp_path)
            message = "Use the attached context file and return one strict JSON object only."
        except Exception:
            temp_message_file = ''

    executable = _resolve_opencode_executable()
    if not executable:
        return {
            'type': 'OpenCodeKernelResult',
            'status': 'error',
            'reason': 'opencode_cli_not_found',
            'duration_ms': int((time.perf_counter() - started_at) * 1000),
            'attached_files': attach_files,
        }

    command: List[str] = _build_opencode_command(executable)
    command.extend(['--dir', str(root)])
    if model:
        command.extend(['--model', model])
    if agent:
        command.extend(['--agent', agent])
    for file_path in attach_files:
        command.extend(['--file', file_path])
    completed = None
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            check=False,
            timeout=timeout_seconds,
            input=message,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return {
            'type': 'OpenCodeKernelResult',
            'status': 'timeout',
            'reason': f'opencode_timeout_{timeout_seconds}s',
            'duration_ms': int((time.perf_counter() - started_at) * 1000),
            'attached_files': attach_files,
        }
    except Exception as exc:
        return {
            'type': 'OpenCodeKernelResult',
            'status': 'error',
            'reason': f'opencode_runtime_error: {exc}',
            'duration_ms': int((time.perf_counter() - started_at) * 1000),
            'attached_files': attach_files,
        }
    finally:
        if temp_message_file:
            try:
                Path(temp_message_file).unlink(missing_ok=True)
            except Exception:
                pass

    parsed = _parse_opencode_stdout((completed.stdout or '') if completed else '')
    text_output = _as_text(parsed.get('text'))
    structured = _safe_json_loads(text_output)

    snippet_blocks = [item for item in _as_list(structured.get('snippet_blocks')) if isinstance(item, dict)]
    generated_code_blocks = [item for item in _as_list(structured.get('generated_code_blocks')) if isinstance(item, dict)]
    if not snippet_blocks and generated_code_blocks:
        for item in generated_code_blocks:
            file_path = _as_text(item.get('file_path'))
            code = _as_text(item.get('code'))
            if not file_path or not code:
                continue
            snippet_blocks.append(
                {
                    'file_path': file_path,
                    'language': _as_text(item.get('language')),
                    'reason': _as_text(item.get('purpose')) or 'generated_code_blocks_fallback',
                    'action': 'create_file',
                    'code': code,
                }
            )

    edit_plan = [item for item in _as_list(structured.get('edit_plan')) if isinstance(item, dict)]
    implementation_targets = [item for item in _as_list(structured.get('implementation_targets')) if isinstance(item, dict)]
    validation_commands = [str(item).strip() for item in _as_list(structured.get('validation_commands')) if str(item).strip()]

    status = 'ready' if (snippet_blocks or edit_plan or implementation_targets or structured) else 'no_structured_output'
    if completed.returncode != 0 and status == 'no_structured_output':
        status = 'error'

    return {
        'type': 'OpenCodeKernelResult',
        'status': status,
        'reason': None if status == 'ready' else f'opencode_exit_{completed.returncode}',
        'duration_ms': int((time.perf_counter() - started_at) * 1000),
        'returncode': completed.returncode,
        'model': model,
        'agent': agent,
        'session_id': _as_text(parsed.get('session_id')),
        'attached_files': attach_files,
        'analysis_summary': _as_text(structured.get('analysis_summary')),
        'edit_plan': edit_plan,
        'snippet_blocks': snippet_blocks,
        'generated_code_blocks': generated_code_blocks,
        'implementation_targets': implementation_targets,
        'validation_commands': validation_commands,
        'structured': structured,
        'text': text_output[:6000],
        'stdout_tail': (completed.stdout or '')[-2000:],
        'stderr_tail': (completed.stderr or '')[-2000:],
    }
