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
            "version": "0.3",
            "project_path": project_path,
            "project_name": project_name,
            "analysis_timestamp": datetime.now().isoformat(),
            "total_paths": len(experience_paths),
            "partitions": [],
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

        print(f"[ExperiencePathStorage] ✅ 经验路径已保存到: {filepath}")
        return filepath

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





