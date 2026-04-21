#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProjectLibraryStorage:
    def __init__(self, storage_dir: str = 'output_analysis/project_library') -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _normalize_path(self, project_path: str) -> str:
        return os.path.normpath(project_path or '')

    def _project_id(self, project_path: str) -> str:
        normalized = self._normalize_path(project_path)
        digest = hashlib.md5(normalized.encode('utf-8')).hexdigest()[:12]
        project_name = os.path.basename(normalized) or 'unknown_project'
        safe_name = ''.join(ch if ch.isalnum() or ch in {'_', '-'} else '_' for ch in project_name)
        return f'{safe_name}_{digest}'

    def _project_dir(self, project_path: str) -> Path:
        folder = self.storage_dir / self._project_id(project_path)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

    def _read_json(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists() or not path.is_file():
            return None
        try:
            with path.open('r', encoding='utf-8') as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _metadata_path(self, project_path: str) -> Path:
        return self._project_dir(project_path) / 'metadata.json'

    def _graph_path(self, project_path: str) -> Path:
        return self._project_dir(project_path) / 'graph_data.json'

    def _hierarchy_path(self, project_path: str) -> Path:
        return self._project_dir(project_path) / 'function_hierarchy.json'

    def save_project_profile(self, project_path: str, profile: Dict[str, Any]) -> Path:
        normalized = self._normalize_path(project_path)
        now = datetime.utcnow().isoformat() + 'Z'
        payload = {
            'project_path': normalized,
            'project_name': str(profile.get('project_name') or os.path.basename(normalized) or 'unknown_project'),
            'display_name': str(profile.get('display_name') or '').strip(),
            'analysis_timestamp': str(profile.get('analysis_timestamp') or now),
            'updated_at': now,
            'has_graph': bool(profile.get('has_graph', False)),
            'has_hierarchy': bool(profile.get('has_hierarchy', False)),
            'path_count': int(profile.get('path_count') or 0),
            'experience_output_root': str(profile.get('experience_output_root') or '').strip() or None,
        }
        path = self._metadata_path(normalized)
        existing = self._read_json(path)
        if isinstance(existing, dict):
            merged = dict(existing)
            merged.update({k: v for k, v in payload.items() if v not in {'', None}})
            payload = merged
            payload['project_path'] = normalized
            payload['updated_at'] = now
            payload.setdefault('project_name', os.path.basename(normalized) or 'unknown_project')
        self._write_json(path, payload)
        return path

    def load_project_profile(self, project_path: str) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_path(project_path)
        payload = self._read_json(self._metadata_path(normalized))
        if not isinstance(payload, dict):
            return None
        if self._normalize_path(str(payload.get('project_path') or '')) != normalized:
            return None
        return payload

    def save_graph_data(self, project_path: str, graph_data: Dict[str, Any]) -> Path:
        normalized = self._normalize_path(project_path)
        payload: Dict[str, Any] = dict(graph_data) if isinstance(graph_data, dict) else {}
        metadata_raw = payload.get('metadata')
        metadata: Dict[str, Any] = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
        metadata.setdefault('analysis_timestamp', datetime.utcnow().isoformat() + 'Z')
        payload['metadata'] = metadata
        path = self._graph_path(normalized)
        self._write_json(path, payload)
        self.save_project_profile(
            normalized,
            {
                'project_name': os.path.basename(normalized) or 'unknown_project',
                'analysis_timestamp': metadata.get('analysis_timestamp'),
                'has_graph': True,
            },
        )
        return path

    def load_graph_data(self, project_path: str) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_path(project_path)
        payload = self._read_json(self._graph_path(normalized))
        if not isinstance(payload, dict):
            return None
        if not isinstance(payload.get('nodes'), list) or not isinstance(payload.get('edges'), list):
            return None
        return payload

    def save_function_hierarchy(self, project_path: str, hierarchy_data: Dict[str, Any]) -> Path:
        normalized = self._normalize_path(project_path)
        payload = dict(hierarchy_data or {})
        payload.setdefault('project_path', normalized)
        path = self._hierarchy_path(normalized)
        self._write_json(path, payload)
        partition_analyses_raw = payload.get('partition_analyses')
        partition_analyses: Dict[str, Any] = partition_analyses_raw if isinstance(partition_analyses_raw, dict) else {}
        path_count = 0
        for item in partition_analyses.values():
            if isinstance(item, dict):
                paths_raw = item.get('path_analyses')
                path_count += len(paths_raw) if isinstance(paths_raw, list) else 0
        self.save_project_profile(
            normalized,
            {
                'project_name': os.path.basename(normalized) or 'unknown_project',
                'analysis_timestamp': datetime.utcnow().isoformat() + 'Z',
                'has_hierarchy': True,
                'path_count': path_count,
            },
        )
        return path

    def load_function_hierarchy(self, project_path: str) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_path(project_path)
        payload = self._read_json(self._hierarchy_path(normalized))
        if not isinstance(payload, dict):
            return None
        stored_path = self._normalize_path(str(payload.get('project_path') or normalized))
        if stored_path != normalized:
            return None
        return payload

    def list_projects(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for directory in self.storage_dir.iterdir():
            if not directory.is_dir():
                continue
            metadata = self._read_json(directory / 'metadata.json')
            if not isinstance(metadata, dict):
                continue
            project_path = self._normalize_path(str(metadata.get('project_path') or ''))
            if not project_path:
                continue
            items.append(
                {
                    'project_path': project_path,
                    'project_name': str(metadata.get('project_name') or os.path.basename(project_path) or 'unknown_project'),
                    'display_name': str(metadata.get('display_name') or '').strip(),
                    'analysis_timestamp': str(metadata.get('analysis_timestamp') or ''),
                    'updated_at': str(metadata.get('updated_at') or ''),
                    'has_graph': bool(metadata.get('has_graph', False)),
                    'has_hierarchy': bool(metadata.get('has_hierarchy', False)),
                    'path_count': int(metadata.get('path_count') or 0),
                    'experience_output_root': str(metadata.get('experience_output_root') or '').strip() or None,
                }
            )
        items.sort(key=lambda item: item.get('updated_at') or item.get('analysis_timestamp') or '', reverse=True)
        return items
