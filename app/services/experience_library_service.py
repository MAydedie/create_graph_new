from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import jsonify, request

from data.project_library_storage import ProjectLibraryStorage


_project_library_storage = ProjectLibraryStorage()
_APP_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_EXPERIENCE_OUTPUT_ROOT = _APP_ROOT / 'output_analysis'


def _normalize_project_path(project_path: str) -> str:
    raw_value = str(project_path or '').strip()
    if not raw_value:
        raise ValueError('project_path 不能为空')

    if not os.path.isabs(raw_value):
        raise ValueError('project_path 必须是绝对路径')

    normalized = os.path.normpath(os.path.abspath(raw_value))
    if not os.path.isdir(normalized):
        raise ValueError(f'project_path 不存在或不是目录: {normalized}')

    return normalized


def _project_hash(project_path: str) -> str:
    return hashlib.md5(project_path.encode('utf-8')).hexdigest()[:8]


def _safe_project_name(project_path: str) -> str:
    project_name = os.path.basename(project_path) or 'unknown_project'
    return ''.join(ch if ch.isalnum() or ch in {'_', '-'} else '_' for ch in project_name)


def _generated_filename(project_path: str) -> str:
    return f'{_safe_project_name(project_path)}_{_project_hash(project_path)}.json'


def _import_prefix(project_path: str) -> str:
    return f'imported_{_project_hash(project_path)}_'


def _resolve_project_experience_output_root(project_path: str) -> Path:
    profile = _project_library_storage.load_project_profile(project_path) or {}
    raw_root = str(profile.get('experience_output_root') or '').strip()
    if raw_root and os.path.isabs(raw_root):
        return Path(os.path.normpath(os.path.abspath(raw_root)))
    return _DEFAULT_EXPERIENCE_OUTPUT_ROOT


def _resolve_project_experience_paths_dir(project_path: str) -> Path:
    experience_root = _resolve_project_experience_output_root(project_path)
    experience_paths_dir = experience_root / 'experience_paths'
    experience_paths_dir.mkdir(parents=True, exist_ok=True)
    return experience_paths_dir


def _sanitize_import_stem(stem: str) -> str:
    sanitized = re.sub(r'[^\w\u4e00-\u9fff-]+', '_', stem.strip(), flags=re.UNICODE)
    sanitized = re.sub(r'_+', '_', sanitized).strip('_')
    return sanitized[:64] or 'entry'


def _is_allowed_filename(project_path: str, filename: str) -> bool:
    if not filename or os.path.basename(filename) != filename:
        return False
    if not filename.endswith('.json'):
        return False
    if filename == _generated_filename(project_path):
        return True
    return filename.startswith(_import_prefix(project_path))


def _resolve_allowed_file(project_path: str, relative_path: str) -> Path:
    relative_name = str(relative_path or '').strip()
    if not _is_allowed_filename(project_path, relative_name):
        raise ValueError('relative_path 不合法或不属于当前项目经验库')
    absolute_path = _resolve_project_experience_paths_dir(project_path) / relative_name
    resolved = absolute_path.resolve()
    experience_dir = _resolve_project_experience_paths_dir(project_path).resolve()
    if resolved.parent != experience_dir:
        raise ValueError('relative_path 超出经验库目录范围')
    return resolved


def _compute_etag(content: str) -> str:
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def _read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _load_json_payload(path: Path) -> Optional[Any]:
    try:
        return json.loads(_read_text(path))
    except Exception:
        return None


def _parse_day(value: str) -> Optional[str]:
    text = str(value or '').strip()
    if not text:
        return None
    try:
        normalized = text.replace('Z', '+00:00') if text.endswith('Z') else text
        return datetime.fromisoformat(normalized).date().isoformat()
    except Exception:
        return None


def _extract_day(payload: Any, path: Path) -> Tuple[str, Optional[str]]:
    analysis_timestamp = None
    if isinstance(payload, dict):
        raw_timestamp = payload.get('analysis_timestamp')
        if isinstance(raw_timestamp, str):
            analysis_timestamp = raw_timestamp
            parsed = _parse_day(raw_timestamp)
            if parsed:
                return parsed, raw_timestamp
    return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat(), analysis_timestamp


def _extract_entry_metadata(project_path: str, path: Path) -> Dict[str, Any]:
    payload = _load_json_payload(path)
    day, analysis_timestamp = _extract_day(payload, path)
    content = _read_text(path)
    filename = path.name
    return {
        'relativePath': filename,
        'absolutePath': str(path),
        'filename': filename,
        'type': 'generated' if filename == _generated_filename(project_path) else 'imported',
        'projectName': payload.get('project_name') if isinstance(payload, dict) else None,
        'analysisTimestamp': analysis_timestamp,
        'updatedAt': datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        'day': day,
        'size': len(content.encode('utf-8')),
        'etag': _compute_etag(content),
    }


def _collect_entries(project_path: str) -> List[Dict[str, Any]]:
    experience_dir = _resolve_project_experience_paths_dir(project_path)
    entries: List[Dict[str, Any]] = []
    for path in sorted(experience_dir.glob('*.json')):
        if _is_allowed_filename(project_path, path.name):
            entries.append(_extract_entry_metadata(project_path, path))
    entries.sort(key=lambda item: (item.get('updatedAt') or '', item.get('filename') or ''), reverse=True)
    return entries


def _summary_from_entries(entries: List[Dict[str, Any]]) -> Dict[str, int]:
    days = {str(item.get('day') or '').strip() for item in entries if str(item.get('day') or '').strip()}
    generated = sum(1 for item in entries if item.get('type') == 'generated')
    imported = sum(1 for item in entries if item.get('type') == 'imported')
    return {
        'totalFiles': len(entries),
        'generatedFiles': generated,
        'importedFiles': imported,
        'experienceDays': len(days),
    }


def _make_import_target(project_path: str, source_name: str) -> Path:
    experience_dir = _resolve_project_experience_paths_dir(project_path)
    safe_stem = _sanitize_import_stem(Path(source_name).stem)
    prefix = _import_prefix(project_path)
    candidate = experience_dir / f'{prefix}{safe_stem}.json'
    index = 2
    while candidate.exists():
        candidate = experience_dir / f'{prefix}{safe_stem}_{index}.json'
        index += 1
    return candidate


def _to_markdown_experience_payload(project_path: str, source_name: str, markdown_text: str) -> Dict[str, Any]:
    normalized_project_path = _normalize_project_path(project_path)
    safe_stem = _sanitize_import_stem(Path(source_name).stem)
    path_signature = f'ImportedMarkdown.{safe_stem}'
    now = datetime.utcnow().isoformat() + 'Z'
    stripped = markdown_text.strip()
    path_description = stripped or f'Imported markdown from {source_name}'
    return {
        'version': '0.3',
        'project_path': normalized_project_path,
        'project_name': os.path.basename(normalized_project_path) or 'unknown_project',
        'analysis_timestamp': now,
        'total_paths': 1,
        'source_type': 'imported_markdown',
        'source_markdown_filename': source_name,
        'partitions': [
            {
                'partition_id': 'imported_markdown',
                'partition_name': Path(source_name).stem or 'Imported Markdown',
                'total_paths': 1,
                'paths': [
                    {
                        'path_id': f'imported_md_{_project_hash(normalized_project_path)}_{safe_stem}',
                        'path_name': Path(source_name).stem or 'Imported Markdown',
                        'path_description': path_description,
                        'function_chain': [path_signature],
                        'path': [path_signature],
                        'leaf_node': path_signature,
                        'semantics': {
                            'semantic_label': Path(source_name).stem or 'Imported Markdown',
                            'description': path_description,
                            'functional_domain': 'Imported Experience',
                        },
                        'source': 'imported_markdown',
                        'raw_markdown': markdown_text,
                    }
                ],
            }
        ],
    }


def api_experience_library_overview():
    try:
        project_path = _normalize_project_path(request.args.get('project_path', ''))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    experience_root = _resolve_project_experience_output_root(project_path)
    experience_dir = _resolve_project_experience_paths_dir(project_path)
    entries = _collect_entries(project_path)
    return jsonify(
        {
            'projectPath': project_path,
            'experienceOutputRoot': str(experience_root),
            'experiencePathsDir': str(experience_dir),
            'entries': entries,
            'summary': _summary_from_entries(entries),
        }
    )


def api_experience_library_file():
    try:
        project_path = _normalize_project_path(request.args.get('project_path', ''))
        target = _resolve_allowed_file(project_path, request.args.get('relative_path', ''))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if not target.exists() or not target.is_file():
        return jsonify({'error': f'文件不存在: {target.name}'}), 404

    content = _read_text(target)
    return jsonify(
        {
            'projectPath': project_path,
            'relativePath': target.name,
            'absolutePath': str(target),
            'filename': target.name,
            'content': content,
            'etag': _compute_etag(content),
            'updatedAt': datetime.fromtimestamp(target.stat().st_mtime).isoformat(),
            'size': len(content.encode('utf-8')),
        }
    )


def api_experience_library_file_save():
    data = request.get_json(silent=True) or {}
    try:
        project_path = _normalize_project_path(str(data.get('project_path') or ''))
        target = _resolve_allowed_file(project_path, str(data.get('relative_path') or ''))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if not target.exists() or not target.is_file():
        return jsonify({'error': f'文件不存在: {target.name}'}), 404

    content = data.get('content')
    if not isinstance(content, str):
        return jsonify({'error': 'content 必须是字符串'}), 400

    current_content = _read_text(target)
    current_etag = _compute_etag(current_content)
    provided_etag = str(data.get('etag') or '').strip()
    if provided_etag and provided_etag != current_etag:
        return jsonify({'error': '文件已被其他修改覆盖，请先刷新后再保存', 'code': 'etag_mismatch'}), 409

    try:
        parsed = json.loads(content)
    except Exception as exc:
        return jsonify({'error': f'保存失败，JSON 无法解析: {exc}'}), 400

    normalized_text = json.dumps(parsed, indent=2, ensure_ascii=False) + '\n'
    target.write_text(normalized_text, encoding='utf-8')
    updated_at = datetime.fromtimestamp(target.stat().st_mtime).isoformat()
    updated_etag = _compute_etag(normalized_text)
    return jsonify(
        {
            'ok': True,
            'relativePath': target.name,
            'absolutePath': str(target),
            'etag': updated_etag,
            'updatedAt': updated_at,
            'size': len(normalized_text.encode('utf-8')),
        }
    )


def api_experience_library_import():
    try:
        project_path = _normalize_project_path(request.form.get('project_path', ''))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'files 不能为空'}), 400

    imported: List[Dict[str, Any]] = []
    for file_storage in files:
        source_name = os.path.basename(str(file_storage.filename or '').strip())
        if not source_name:
            return jsonify({'error': '存在空文件名导入项'}), 400

        suffix = Path(source_name).suffix.lower()
        if suffix not in {'.json', '.md'}:
            return jsonify({'error': f'仅支持导入 .json / .md，收到: {source_name}'}), 400

        raw_text = file_storage.read().decode('utf-8')
        target = _make_import_target(project_path, source_name)

        try:
            if suffix == '.json':
                parsed = json.loads(raw_text)
                serialized = json.dumps(parsed, indent=2, ensure_ascii=False) + '\n'
                stored_type = 'json'
            else:
                payload = _to_markdown_experience_payload(project_path, source_name, raw_text)
                serialized = json.dumps(payload, indent=2, ensure_ascii=False) + '\n'
                stored_type = 'md'
        except Exception as exc:
            return jsonify({'error': f'导入失败 {source_name}: {exc}'}), 400

        target.write_text(serialized, encoding='utf-8')
        imported.append(
            {
                'sourceName': source_name,
                'storedRelativePath': target.name,
                'storedAbsolutePath': str(target),
                'type': stored_type,
            }
        )

    return jsonify({'ok': True, 'imported': imported})
