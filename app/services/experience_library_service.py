from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import jsonify, request

from data.data_accessor import get_data_accessor
from data.project_library_storage import ProjectLibraryStorage
from data.experience_path_storage import ExperiencePathStorage


_project_library_storage = ProjectLibraryStorage()
_experience_path_storage = ExperiencePathStorage()
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


def _normalize_project_path_for_delete(project_path: str) -> str:
    raw_value = str(project_path or '').strip()
    if not raw_value:
        raise ValueError('project_path 不能为空')
    normalized = os.path.normpath(os.path.abspath(raw_value)) if os.path.isabs(raw_value) else os.path.normpath(raw_value)
    return normalized


def _resolve_delete_roots(project_path: str) -> List[Path]:
    roots: List[Path] = []
    profile = _project_library_storage.load_project_profile(project_path) or {}
    profile_root = str(profile.get('experience_output_root') or '').strip()
    if profile_root and os.path.isabs(profile_root):
        roots.append(Path(os.path.normpath(os.path.abspath(profile_root))))
    roots.append(_DEFAULT_EXPERIENCE_OUTPUT_ROOT)

    deduped: List[Path] = []
    seen: set[str] = set()
    for item in roots:
        key = str(item.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _delete_project_artifacts_under_root(project_path: str, root: Path) -> int:
    removed = 0
    generated_filename = _generated_filename(project_path)
    digest_filename = _architecture_digest_filename(project_path)
    import_prefix = _import_prefix(project_path)

    experience_paths_dir = root / 'experience_paths'
    if experience_paths_dir.is_dir():
        for candidate in experience_paths_dir.glob('*.json'):
            if candidate.name in {generated_filename, digest_filename} or candidate.name.startswith(import_prefix):
                try:
                    candidate.unlink(missing_ok=True)
                    if not candidate.exists():
                        removed += 1
                except Exception:
                    pass

    for bucket in ['community_shadow', 'process_shadow', 'entry_points_shadow']:
        bucket_dir = root / bucket
        if not bucket_dir.is_dir():
            continue
        target = bucket_dir / generated_filename
        if not target.exists():
            continue
        try:
            target.unlink(missing_ok=True)
            if not target.exists():
                removed += 1
        except Exception:
            pass

    return removed


def _sanitize_import_stem(stem: str) -> str:
    sanitized = re.sub(r'[^\w\u4e00-\u9fff-]+', '_', stem.strip(), flags=re.UNICODE)
    sanitized = re.sub(r'_+', '_', sanitized).strip('_')
    return sanitized[:64] or 'entry'


def _architecture_digest_filename(project_path: str) -> str:
    name = _safe_project_name(project_path)
    h = _project_hash(project_path)
    return f'architecture_digest_{name}_{h}.json'


def _is_allowed_filename(project_path: str, filename: str) -> bool:
    if not filename or os.path.basename(filename) != filename:
        return False
    if not filename.endswith('.json'):
        return False
    if filename == _generated_filename(project_path):
        return True
    if filename == _architecture_digest_filename(project_path):
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
        'type': 'generated' if filename == _generated_filename(project_path) else ('digest' if filename == _architecture_digest_filename(project_path) else 'imported'),
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
        'version': '0.4',
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
                        'method_path_entries': [
                            {
                                'step_index': 1,
                                'method_signature': path_signature,
                                'display_name': path_signature,
                                'chain_role': 'entry_method',
                                'is_entry': True,
                                'is_leaf': True,
                                'prev_method': None,
                                'next_method': None,
                                'path_to_method': path_signature,
                            }
                        ],
                        'chained_call_path': {
                            'chain_version': 'callpath.v1',
                            'path_methods': [path_signature],
                            'method_count': 1,
                            'path_links': [],
                            'main_method': path_signature,
                            'intermediate_methods': [],
                            'leaf_node': path_signature,
                            'entry_method': path_signature,
                            'chain_text': path_signature,
                            'explanation': '导入 Markdown 经验，仅包含单节点路径。',
                        },
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


# ---------------------------------------------------------------------------
# Architecture Digest: 自顶向下的架构摘要，补充经验库缺失的全局上下文
# ---------------------------------------------------------------------------

_TECH_STACK_INDICATORS = {
    'requirements.txt': 'Python',
    'setup.py': 'Python',
    'pyproject.toml': 'Python',
    'package.json': 'Node.js / JavaScript',
    'tsconfig.json': 'TypeScript',
    'Cargo.toml': 'Rust',
    'go.mod': 'Go',
    'pom.xml': 'Java (Maven)',
    'build.gradle': 'Java (Gradle)',
    'Gemfile': 'Ruby',
    'composer.json': 'PHP',
    'CMakeLists.txt': 'C/C++',
}

_FRAMEWORK_INDICATORS = {
    'flask': 'Flask',
    'django': 'Django',
    'fastapi': 'FastAPI',
    'express': 'Express.js',
    'react': 'React',
    'vue': 'Vue.js',
    'angular': 'Angular',
    'next': 'Next.js',
    'vite': 'Vite',
    'spring': 'Spring',
    'gin': 'Gin',
    'actix': 'Actix',
}

_DESIGN_PATTERN_HEURISTICS = [
    {'pattern': 'singleton', 'files': ['**/data_accessor*', '**/get_*_instance*'], 'name': '单例模式', 'description': '通过全局访问器确保唯一实例'},
    {'pattern': 'factory', 'files': ['**/*factory*', '**/*create_app*'], 'name': '工厂模式', 'description': '通过工厂函数创建对象/应用实例'},
    {'pattern': 'blueprint', 'files': ['**/routes/*', '**/blueprint*'], 'name': 'Blueprint/路由模式', 'description': '将路由按功能分组注册'},
    {'pattern': 'service_layer', 'files': ['**/services/*'], 'name': '服务层模式', 'description': '业务逻辑与路由/视图分离'},
    {'pattern': 'storage_abstraction', 'files': ['**/*storage*'], 'name': '存储抽象', 'description': '通过存储类封装持久化细节'},
]


def _detect_tech_stack(project_path: str) -> List[str]:
    detected: List[str] = []
    for indicator_file, label in _TECH_STACK_INDICATORS.items():
        if os.path.exists(os.path.join(project_path, indicator_file)):
            if label not in detected:
                detected.append(label)
    return detected


def _detect_frameworks(project_path: str) -> List[str]:
    detected: List[str] = []
    requirements_path = os.path.join(project_path, 'requirements.txt')
    package_json_path = os.path.join(project_path, 'package.json')
    texts: List[str] = []
    for candidate in [requirements_path, package_json_path]:
        if os.path.isfile(candidate):
            try:
                texts.append(Path(candidate).read_text(encoding='utf-8').lower())
            except Exception:
                pass
    combined = ' '.join(texts)
    for keyword, label in _FRAMEWORK_INDICATORS.items():
        if keyword in combined and label not in detected:
            detected.append(label)
    return detected


def _detect_design_patterns(project_path: str) -> List[Dict[str, str]]:
    import glob
    patterns_found: List[Dict[str, str]] = []
    for heuristic in _DESIGN_PATTERN_HEURISTICS:
        for file_glob in heuristic['files']:
            full_glob = os.path.join(project_path, file_glob)
            matches = glob.glob(full_glob, recursive=True)
            if matches:
                patterns_found.append({
                    'name': heuristic['name'],
                    'description': heuristic['description'],
                    'evidence': os.path.relpath(matches[0], project_path).replace('\\', '/'),
                })
                break
    return patterns_found


def _scan_top_modules(project_path: str, max_depth: int = 2) -> List[Dict[str, Any]]:
    modules: List[Dict[str, Any]] = []
    try:
        for entry in sorted(os.scandir(project_path), key=lambda e: e.name):
            if not entry.is_dir():
                continue
            name = entry.name
            if name.startswith('.') or name.startswith('__') or name in {
                'node_modules', 'dist', 'build', '.git', 'venv', 'env', '__pycache__',
                'output_analysis', '.vscode', '.idea', 'logs', 'tmp',
            }:
                continue
            file_count = 0
            key_files: List[str] = []
            try:
                for root, _dirs, files in os.walk(entry.path):
                    depth = root.replace(entry.path, '').count(os.sep)
                    if depth >= max_depth:
                        continue
                    for f in files:
                        if f.endswith(('.py', '.ts', '.tsx', '.js', '.jsx', '.java', '.go')):
                            file_count += 1
                            if len(key_files) < 5:
                                rel = os.path.relpath(os.path.join(root, f), project_path).replace('\\', '/')
                                key_files.append(rel)
            except Exception:
                pass
            if file_count > 0:
                modules.append({
                    'name': name,
                    'path': name + '/',
                    'file_count': file_count,
                    'key_files': key_files,
                })
    except Exception:
        pass
    return modules


def _read_readme_summary(project_path: str, max_chars: int = 800) -> Optional[str]:
    for candidate in ['README.md', 'readme.md', 'README.txt', 'README']:
        readme_path = os.path.join(project_path, candidate)
        if os.path.isfile(readme_path):
            try:
                text = Path(readme_path).read_text(encoding='utf-8')
                lines = text.strip().split('\n')
                summary_lines: List[str] = []
                char_count = 0
                for line in lines:
                    if char_count > max_chars:
                        break
                    summary_lines.append(line)
                    char_count += len(line)
                return '\n'.join(summary_lines)
            except Exception:
                pass
    return None


def _detect_entry_point(project_path: str) -> Optional[str]:
    for candidate in ['app.py', 'main.py', 'manage.py', 'server.py', 'run.py', 'index.js', 'index.ts']:
        if os.path.isfile(os.path.join(project_path, candidate)):
            return candidate
    return None


def _collect_api_routes_from_flask(project_path: str) -> List[Dict[str, Any]]:
    route_groups: List[Dict[str, Any]] = []
    routes_dir = os.path.join(project_path, 'app', 'routes')
    if not os.path.isdir(routes_dir):
        return route_groups
    try:
        for fname in sorted(os.listdir(routes_dir)):
            if not fname.endswith('.py') or fname.startswith('__'):
                continue
            fpath = os.path.join(routes_dir, fname)
            content = Path(fpath).read_text(encoding='utf-8')
            routes: List[str] = []
            for line in content.split('\n'):
                line_stripped = line.strip()
                if 'add_url_rule' in line_stripped:
                    match = re.search(r'["\']([^"\']*/[^"\']*)["\'\)]', line_stripped)
                    if match:
                        routes.append(match.group(1))
                elif '@' in line_stripped and '.route(' in line_stripped:
                    match = re.search(r'\.route\(["\']([^"\']+)', line_stripped)
                    if match:
                        routes.append(match.group(1))
            if routes:
                route_groups.append({
                    'source_file': f'app/routes/{fname}',
                    'route_count': len(routes),
                    'routes': routes[:20],
                })
    except Exception:
        pass
    return route_groups


def _gather_experience_library_stats(project_path: str) -> Dict[str, Any]:
    stats: Dict[str, Any] = {}
    profile = _project_library_storage.load_project_profile(project_path)
    if isinstance(profile, dict):
        stats['has_graph'] = bool(profile.get('has_graph'))
        stats['has_hierarchy'] = bool(profile.get('has_hierarchy'))
        stats['path_count'] = int(profile.get('path_count') or 0)

    experience_root = _resolve_project_experience_output_root(project_path)

    community_shadow_dir = experience_root / 'community_shadow'
    if community_shadow_dir.is_dir():
        cs_file = community_shadow_dir / _generated_filename(project_path)
        if cs_file.is_file():
            try:
                cs_data = json.loads(cs_file.read_text(encoding='utf-8'))
                communities = cs_data.get('communities', [])
                stats['community_count'] = len(communities)
                stats['top_communities'] = [
                    {'label': c.get('label', ''), 'size': c.get('size', 0), 'cohesion': c.get('cohesion', 0)}
                    for c in (communities[:5] if isinstance(communities, list) else [])
                ]
            except Exception:
                pass

    process_shadow_dir = experience_root / 'process_shadow'
    if process_shadow_dir.is_dir():
        ps_file = process_shadow_dir / _generated_filename(project_path)
        if ps_file.is_file():
            try:
                ps_data = json.loads(ps_file.read_text(encoding='utf-8'))
                stats['process_count'] = len(ps_data.get('processes', []))
                summary = ps_data.get('summary', {})
                stats['step_edge_count'] = summary.get('step_edge_count', 0)
            except Exception:
                pass

    experience_paths_dir = experience_root / 'experience_paths'
    if experience_paths_dir.is_dir():
        ep_file = experience_paths_dir / _generated_filename(project_path)
        if ep_file.is_file():
            try:
                ep_data = json.loads(ep_file.read_text(encoding='utf-8'))
                stats['experience_path_total'] = ep_data.get('total_paths', 0)
                stats['experience_partition_count'] = len(ep_data.get('partitions', []))
            except Exception:
                pass

    conversations_dir = experience_root / 'conversations'
    if conversations_dir.is_dir():
        try:
            stats['conversation_count'] = sum(1 for f in conversations_dir.iterdir() if f.is_file() and f.suffix == '.json')
        except Exception:
            pass

    return stats


def generate_architecture_digest(project_path: str) -> Dict[str, Any]:
    normalized = _normalize_project_path(project_path)
    project_name = os.path.basename(normalized) or 'unknown_project'

    tech_stack = _detect_tech_stack(normalized)
    frameworks = _detect_frameworks(normalized)
    design_patterns = _detect_design_patterns(normalized)
    modules = _scan_top_modules(normalized)
    readme_summary = _read_readme_summary(normalized)
    entry_point = _detect_entry_point(normalized)
    api_routes = _collect_api_routes_from_flask(normalized)
    experience_stats = _gather_experience_library_stats(normalized)

    total_route_count = sum(g.get('route_count', 0) for g in api_routes)
    total_module_files = sum(m.get('file_count', 0) for m in modules)

    digest: Dict[str, Any] = {
        'version': '1.0',
        'digest_type': 'architecture_digest',
        'project_path': normalized,
        'project_name': project_name,
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'overview': {
            'purpose': readme_summary.split('\n')[0] if readme_summary else f'{project_name} 项目',
            'tech_stack': tech_stack,
            'frameworks': frameworks,
            'entry_point': entry_point,
            'module_count': len(modules),
            'total_code_files': total_module_files,
            'api_route_count': total_route_count,
        },
        'modules': modules,
        'design_patterns': design_patterns,
        'api_catalog': api_routes,
        'readme_summary': readme_summary,
        'experience_library_stats': experience_stats,
        'quick_start': {
            'run_command': f'python {entry_point}' if entry_point and entry_point.endswith('.py') else None,
            'url': 'http://localhost:5000' if entry_point == 'app.py' else None,
            'prerequisites': ['pip install -r requirements.txt'] if 'Python' in tech_stack else [],
        },
        'cross_conversation_context': _build_cross_conversation_context(
            project_name, tech_stack, frameworks, design_patterns, modules, experience_stats, entry_point, total_route_count,
        ),
    }
    return digest


def generate_spec(
    project_path: str,
    user_intent: str = '项目说明书',
    graph_db_path: Optional[str] = None,
    segment6_json_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    skip_llm: bool = True,
) -> Dict[str, Any]:
    normalized = _normalize_project_path(project_path)
    architecture_digest = generate_architecture_digest(normalized)
    if not graph_db_path or not segment6_json_path:
        return {
            'status': 'fallback_architecture_digest',
            'fallback_reason': 'stage6 graph artifacts were not provided',
            'user_intent': user_intent,
            'architecture_digest': architecture_digest,
        }

    graph_db = Path(graph_db_path)
    segment6_json = Path(segment6_json_path)
    if not graph_db.is_file() or not segment6_json.is_file():
        return {
            'status': 'fallback_architecture_digest',
            'fallback_reason': 'stage6 graph artifacts were not readable',
            'user_intent': user_intent,
            'architecture_digest': architecture_digest,
        }

    try:
        from segment_8_spec_generator.spec_generator import run_stage8

        spec_root = Path(output_dir) if output_dir else _resolve_project_experience_output_root(normalized) / 'specs'
        spec_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        md_path = spec_root / f'spec_{timestamp}.md'
        json_path = spec_root / f'spec_{timestamp}.json'
        raw_path = spec_root / 'raw_graph_query_results.json'
        audit_path = spec_root / 'logs' / 'spec_generator_audit.jsonl'
        run_stage8(
            graph_db_path=str(graph_db),
            segment6_json_path=str(segment6_json),
            project_path=normalized,
            output_path=str(md_path),
            spec_json_path=str(json_path),
            raw_results_path=str(raw_path),
            audit_log_path=str(audit_path),
            user_intent=user_intent,
            skip_llm=skip_llm,
        )
        spec_payload = json.loads(json_path.read_text(encoding='utf-8'))
        spec_payload['artifacts'] = {
            'spec_md_path': str(md_path).replace('\\', '/'),
            'spec_json_path': str(json_path).replace('\\', '/'),
            'raw_results_path': str(raw_path).replace('\\', '/'),
            'audit_log_path': str(audit_path).replace('\\', '/'),
        }
        return spec_payload
    except Exception as exc:
        return {
            'status': 'fallback_architecture_digest',
            'fallback_reason': f'stage8 spec generation failed: {exc}',
            'user_intent': user_intent,
            'architecture_digest': architecture_digest,
        }


def _build_cross_conversation_context(
    project_name: str,
    tech_stack: List[str],
    frameworks: List[str],
    design_patterns: List[Dict[str, str]],
    modules: List[Dict[str, Any]],
    experience_stats: Dict[str, Any],
    entry_point: Optional[str],
    total_route_count: int,
) -> str:
    lines: List[str] = []
    lines.append(f'## {project_name} 架构摘要（可跨对话复用）')
    lines.append('')
    lines.append(f'**技术栈**: {" / ".join(tech_stack) if tech_stack else "未检测到"}')
    lines.append(f'**框架**: {" / ".join(frameworks) if frameworks else "未检测到"}')
    if entry_point:
        lines.append(f'**入口**: `{entry_point}`')
    lines.append(f'**API路由**: {total_route_count} 条')
    lines.append('')

    if modules:
        lines.append('### 模块结构')
        for m in modules[:12]:
            lines.append(f'- **{m["name"]}/**: {m.get("file_count", 0)} 个代码文件')
        lines.append('')

    if design_patterns:
        lines.append('### 设计模式')
        for p in design_patterns:
            lines.append(f'- **{p["name"]}**: {p["description"]} (证据: `{p.get("evidence", "")}`)')
        lines.append('')

    if experience_stats:
        lines.append('### 经验库数据量')
        if experience_stats.get('community_count'):
            lines.append(f'- 社区分区: {experience_stats["community_count"]} 个')
        if experience_stats.get('process_count'):
            lines.append(f'- 业务流程: {experience_stats["process_count"]} 个')
        if experience_stats.get('experience_path_total'):
            lines.append(f'- 经验路径: {experience_stats["experience_path_total"]} 条')
        if experience_stats.get('conversation_count'):
            lines.append(f'- 历史对话: {experience_stats["conversation_count"]} 次')
        lines.append('')

    lines.append('### 如何使用此摘要')
    lines.append('1. 在新对话框中，AI 可直接读取此摘要快速理解项目全貌')
    lines.append('2. QA 回答时此摘要作为全局上下文提升答案相关性')
    lines.append('3. 前端展示此摘要帮助用户一目了然地学习项目结构')

    return '\n'.join(lines)


def api_experience_library_architecture_digest():
    try:
        project_path = _normalize_project_path(request.args.get('project_path', ''))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    try:
        digest = generate_architecture_digest(project_path)
    except Exception as exc:
        return jsonify({'error': f'架构摘要生成失败: {exc}'}), 500

    return jsonify(digest)


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


def api_experience_library_project_delete():
    data = request.get_json(silent=True) or {}
    try:
        project_path = _normalize_project_path_for_delete(str(data.get('project_path') or ''))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    removed_files = 0
    for root in _resolve_delete_roots(project_path):
        removed_files += _delete_project_artifacts_under_root(project_path, root)

    profile_deleted = _project_library_storage.delete_project(project_path)

    data_accessor = get_data_accessor()
    cache_cleared = {
        'main_analysis': bool(data_accessor.delete_main_analysis(project_path)),
        'function_hierarchy': bool(data_accessor.delete_function_hierarchy(project_path)),
        'function_hierarchy_layer': bool(data_accessor.delete_function_hierarchy_layer_cache(project_path)),
        'process_shadow': bool(data_accessor.delete_process_shadow(project_path)),
        'community_shadow': bool(data_accessor.delete_community_shadow(project_path)),
    }

    return jsonify(
        {
            'ok': True,
            'projectPath': project_path,
            'removedFiles': removed_files,
            'profileDeleted': profile_deleted,
            'cacheCleared': cache_cleared,
        }
    )
