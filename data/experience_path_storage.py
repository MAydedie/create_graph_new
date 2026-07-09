#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
经验路径存储服务 - 负责经验路径的持久化和加载

Phase 1 / Task 1.2 实现：
- 将内存中的经验路径（由 DataAccessor / analysis_service 生成）保存为 JSON 文件
- 支持按项目路径加载对应的经验路径数据
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
import json
import os
import hashlib

from data.data_accessor import get_data_accessor


class ExperiencePathStorage:
    """经验路径存储服务"""

    def __init__(self, storage_dir: str = "output_analysis/experience_paths") -> None:
        """
        初始化存储服务

        Args:
            storage_dir: 存储目录（相对项目根路径）
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _build_filepath(self, project_path: str) -> Path:
        project_path = os.path.normpath(project_path or "")
        project_name = os.path.basename(project_path) or "unknown_project"
        project_hash = hashlib.md5(project_path.encode("utf-8")).hexdigest()[:8]
        filename = f"{project_name}_{project_hash}.json"
        return self.storage_dir / filename

    def save_experience_paths(
        self,
        project_path: str,
        experience_paths: List[Dict[str, Any]],
        partition_analyses: Dict[str, Dict[str, Any]],
    ) -> Path:
        """
        保存经验路径到 JSON 文件。

        Args:
            project_path: 项目路径
            experience_paths: 由 DataAccessor.get_experience_paths 返回的列表
            partition_analyses: analyze_function_hierarchy 生成的分区分析结果
        """
        filepath = self._build_filepath(project_path)
        project_path = os.path.normpath(project_path or "")
        project_name = os.path.basename(project_path) or "unknown_project"

        data: Dict[str, Any] = {
            "version": "0.4",
            "project_path": project_path,
            "project_name": project_name,
            "analysis_timestamp": datetime.now().isoformat(),
            "total_paths": len(experience_paths),
            "partitions": [],
            "resolution_coverage": self._build_resolution_coverage(experience_paths),
        }

        # 按分区聚合路径
        partition_paths_map: Dict[str, List[Dict[str, Any]]] = {}
        for p in experience_paths or []:
            pid = p.get("partition_id", "unknown")
            partition_paths_map.setdefault(pid, []).append(p)

        for partition_id, paths in partition_paths_map.items():
            partition_data = partition_analyses.get(partition_id, {}) or {}

            # 与网页/运行时契约保持一致：以 DataAccessor 产出的 experience_paths 为唯一持久化来源。
            # 这样可避免再次从 path_analyses 重建时丢失 what/how/constraints_structured 等字段。
            final_paths = paths or []

            entry = {
                "partition_id": partition_id,
                "partition_name": (
                    partition_data.get("partition_name")
                    or partition_data.get("name")
                    or partition_id
                ),
                "total_paths": len(final_paths),
                "paths": final_paths,
            }
            data["partitions"].append(entry)


        with filepath.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[ExperiencePathStorage] Experience paths saved to: {filepath}")
        return filepath

    @staticmethod
    def _build_resolution_coverage(experience_paths: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_paths = 0
        fully_exact_paths = 0
        paths_with_fallback = 0
        total_method_entries = 0
        exact_owner_count = 0
        heuristic_owner_count = 0
        fallback_owner_count = 0
        non_empty_absolute_path_count = 0
        for path in experience_paths or []:
            if not isinstance(path, dict):
                continue
            total_paths += 1
            raw_coverage = path.get('ownership_coverage')
            coverage: Dict[str, Any] = raw_coverage if isinstance(raw_coverage, dict) else {}
            total_entries = int(coverage.get('total_method_entries') or 0)
            exact_entries = int(coverage.get('exact_owner_count') or 0)
            heuristic_entries = int(coverage.get('heuristic_owner_count') or 0)
            fallback_entries = int(coverage.get('fallback_owner_count') or 0)
            non_empty_entries = int(coverage.get('non_empty_absolute_path_count') or 0)
            total_method_entries += total_entries
            exact_owner_count += exact_entries
            heuristic_owner_count += heuristic_entries
            fallback_owner_count += fallback_entries
            non_empty_absolute_path_count += non_empty_entries
            if total_entries > 0 and exact_entries == total_entries:
                fully_exact_paths += 1
            if fallback_entries > 0:
                paths_with_fallback += 1

        unresolved_owner_count = max(total_method_entries - exact_owner_count - heuristic_owner_count - fallback_owner_count, 0)
        return {
            'total_paths': total_paths,
            'paths_with_full_exact_ownership': fully_exact_paths,
            'paths_with_fallback_ownership': paths_with_fallback,
            'full_exact_path_percent': round((fully_exact_paths / total_paths) * 100, 2) if total_paths else 0.0,
            'total_method_entries': total_method_entries,
            'exact_owner_count': exact_owner_count,
            'heuristic_owner_count': heuristic_owner_count,
            'fallback_owner_count': fallback_owner_count,
            'unresolved_owner_count': unresolved_owner_count,
            'non_empty_absolute_path_count': non_empty_absolute_path_count,
            'exact_owner_percent': round((exact_owner_count / total_method_entries) * 100, 2) if total_method_entries else 0.0,
            'heuristic_owner_percent': round((heuristic_owner_count / total_method_entries) * 100, 2) if total_method_entries else 0.0,
            'fallback_owner_percent': round((fallback_owner_count / total_method_entries) * 100, 2) if total_method_entries else 0.0,
            'non_empty_absolute_path_percent': round((non_empty_absolute_path_count / total_method_entries) * 100, 2) if total_method_entries else 0.0,
        }

    def load_experience_paths(self, project_path: str) -> Optional[Dict[str, Any]]:
        """
        加载指定项目的经验路径 JSON。

        Returns:
            JSON 对象，如果不存在或加载失败则返回 None。
        """
        project_path = os.path.normpath(project_path or "")
        filepath = self._build_filepath(project_path)
        if not filepath.exists():
            return None

        try:
            with filepath.open("r", encoding="utf-8") as f:
                data = json.load(f)
            accessor = get_data_accessor()
            resolver = accessor._build_method_file_path_resolver(project_path)
            for partition in data.get('partitions', []) or []:
                if not isinstance(partition, dict):
                    continue
                paths = partition.get('paths')
                if not isinstance(paths, list):
                    continue
                partition['paths'] = [
                    accessor._enrich_experience_path_payload(item, project_path=project_path, resolver=resolver) if isinstance(item, dict) else item
                    for item in paths
                ]
            # 轻量校验
            if data.get("project_path") and os.path.normpath(data["project_path"]) != project_path:
                # 同名工程但路径不一致，视为不匹配
                return None
            return data
        except Exception as e:
            print(f"[ExperiencePathStorage] ⚠️ 加载文件失败 {filepath}: {e}")
            return None

    def list_all_projects(self) -> List[Dict[str, str]]:
        """列出当前存储目录下已保存的所有项目信息。"""
        projects: List[Dict[str, str]] = []
        for filepath in self.storage_dir.glob("*.json"):
            try:
                with filepath.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                projects.append(
                    {
                        "project_path": data.get("project_path", ""),
                        "project_name": data.get("project_name", ""),
                        "analysis_timestamp": data.get("analysis_timestamp", ""),
                        "total_paths": str(data.get("total_paths", 0)),
                    }
                )
            except Exception as e:
                print(f"[ExperiencePathStorage] ⚠️ 读取文件失败 {filepath}: {e}")
        return projects

    def delete_project_entries(self, project_path: str) -> int:
        """删除 experience_paths 目录下属于指定项目的所有 JSON 文件。"""
        normalized = os.path.normpath(project_path or "")
        if not normalized:
            return 0

        removed = 0
        for filepath in self.storage_dir.glob("*.json"):
            try:
                with filepath.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                payload_project_path = os.path.normpath(str(data.get("project_path") or ""))
                if payload_project_path != normalized:
                    continue
                filepath.unlink(missing_ok=True)
                if not filepath.exists():
                    removed += 1
            except Exception:
                continue
        return removed
