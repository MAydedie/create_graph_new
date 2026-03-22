#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件管理器 (FileManager)

提供安全的文件操作能力：
- safe_read: 安全读取文件（带大小限制、编码处理）
- safe_write: 安全写入文件（带备份机制）
- list_dir: 列出目录内容

安全特性：
- 路径白名单：只允许操作项目目录内的文件
- 大文件截断：读取大文件时自动截断
- 自动备份：写入前自动创建备份
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import logging


logger = logging.getLogger("FileManager")


@dataclass
class DirEntry:
    """目录条目"""
    name: str
    path: str
    is_dir: bool
    size: int = 0  # 文件大小（字节）
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "is_dir": self.is_dir,
            "size": self.size
        }


class FileManager:
    """
    安全的文件管理器
    
    特性：
    - 路径白名单控制
    - 大文件自动截断
    - 写入前自动备份
    """
    
    # 默认配置
    DEFAULT_MAX_READ_BYTES = 50_000  # 50KB
    DEFAULT_MAX_ENTRIES = 200
    BACKUP_DIR = ".agent_backups"
    
    def __init__(
        self,
        project_root: Optional[str] = None,
        allowed_paths: Optional[List[str]] = None,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
        max_entries: int = DEFAULT_MAX_ENTRIES
    ):
        """
        初始化文件管理器
        
        Args:
            project_root: 项目根目录（默认自动检测）
            allowed_paths: 允许访问的路径白名单（默认为项目根目录）
            max_read_bytes: 最大读取字节数
            max_entries: 目录列表最大条目数
        """
        self.project_root = Path(project_root) if project_root else self._find_project_root()
        self.allowed_paths = [Path(p) for p in (allowed_paths or [str(self.project_root)])]
        self.max_read_bytes = max_read_bytes
        self.max_entries = max_entries
        self.logger = logging.getLogger("FileManager")
    
    def _find_project_root(self) -> Path:
        """查找项目根目录"""
        # 从当前文件向上查找
        current = Path(__file__).resolve().parent
        while current != current.parent:
            if (current / "config" / "config.py").exists():
                return current
            current = current.parent
        
        # 回退到当前工作目录
        return Path.cwd()
    
    def _is_path_allowed(self, path: Path) -> bool:
        """检查路径是否在白名单内"""
        resolved = path.resolve()
        for allowed in self.allowed_paths:
            try:
                resolved.relative_to(allowed.resolve())
                return True
            except ValueError:
                continue
        return False
    
    def _resolve_path(self, path: str) -> Path:
        """
        解析路径（相对路径转绝对路径）
        
        Args:
            path: 文件路径（相对或绝对）
            
        Returns:
            绝对路径
        """
        p = Path(path)
        if not p.is_absolute():
            p = self.project_root / p
        return p.resolve()
    
    def safe_read(
        self,
        path: str,
        max_bytes: Optional[int] = None,
        encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        """
        安全读取文件
        
        Args:
            path: 文件路径
            max_bytes: 最大读取字节数（可选，默认使用 self.max_read_bytes）
            encoding: 文件编码
            
        Returns:
            包含以下字段的字典：
            - success: bool
            - content: str (成功时)
            - truncated: bool (是否被截断)
            - total_size: int (文件总大小)
            - error: str (失败时)
        """
        max_bytes = max_bytes or self.max_read_bytes
        resolved = self._resolve_path(path)
        
        # 安全检查
        if not self._is_path_allowed(resolved):
            return {
                "success": False,
                "error": f"路径不在允许范围内: {path}"
            }
        
        if not resolved.exists():
            return {
                "success": False,
                "error": f"文件不存在: {path}"
            }
        
        if not resolved.is_file():
            return {
                "success": False,
                "error": f"不是文件: {path}"
            }
        
        try:
            file_size = resolved.stat().st_size
            truncated = file_size > max_bytes
            
            with open(resolved, "r", encoding=encoding, errors="replace") as f:
                if truncated:
                    content = f.read(max_bytes)
                    content += f"\n\n... [内容已截断，共 {file_size} 字节，显示前 {max_bytes} 字节]"
                else:
                    content = f.read()
            
            return {
                "success": True,
                "content": content,
                "truncated": truncated,
                "total_size": file_size
            }
        except Exception as e:
            self.logger.error(f"读取文件失败 {path}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def safe_write(
        self,
        path: str,
        content: str,
        backup: bool = True,
        encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        """
        安全写入文件（带备份）
        
        Args:
            path: 文件路径
            content: 要写入的内容
            backup: 是否创建备份
            encoding: 文件编码
            
        Returns:
            包含以下字段的字典：
            - success: bool
            - backup_path: str (如果有备份)
            - error: str (失败时)
        """
        resolved = self._resolve_path(path)
        
        # 安全检查
        if not self._is_path_allowed(resolved):
            return {
                "success": False,
                "error": f"路径不在允许范围内: {path}"
            }
        
        try:
            # 创建备份
            backup_path = None
            if backup and resolved.exists():
                backup_path = self._create_backup(resolved)
            
            # 确保目录存在
            resolved.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            with open(resolved, "w", encoding=encoding) as f:
                f.write(content)
            
            result = {
                "success": True,
                "path": str(resolved)
            }
            if backup_path:
                result["backup_path"] = str(backup_path)
            
            return result
        except Exception as e:
            self.logger.error(f"写入文件失败 {path}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _create_backup(self, path: Path) -> Path:
        """
        创建文件备份
        
        备份路径: {project_root}/.agent_backups/{relative_path}.{timestamp}.bak
        """
        try:
            relative = path.relative_to(self.project_root)
        except ValueError:
            relative = Path(path.name)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.project_root / self.BACKUP_DIR / relative.parent
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        backup_path = backup_dir / f"{relative.name}.{timestamp}.bak"
        shutil.copy2(path, backup_path)
        
        self.logger.debug(f"创建备份: {backup_path}")
        return backup_path
    
    def list_dir(
        self,
        path: str,
        max_entries: Optional[int] = None,
        include_hidden: bool = False
    ) -> Dict[str, Any]:
        """
        列出目录内容
        
        Args:
            path: 目录路径
            max_entries: 最大条目数
            include_hidden: 是否包含隐藏文件
            
        Returns:
            包含以下字段的字典：
            - success: bool
            - entries: List[DirEntry] (成功时)
            - truncated: bool (是否被截断)
            - total_count: int (总条目数)
            - error: str (失败时)
        """
        max_entries = max_entries or self.max_entries
        resolved = self._resolve_path(path)
        
        # 安全检查
        if not self._is_path_allowed(resolved):
            return {
                "success": False,
                "error": f"路径不在允许范围内: {path}"
            }
        
        if not resolved.exists():
            return {
                "success": False,
                "error": f"路径不存在: {path}"
            }
        
        if not resolved.is_dir():
            return {
                "success": False,
                "error": f"不是目录: {path}"
            }
        
        try:
            all_entries = []
            for item in resolved.iterdir():
                # 跳过隐藏文件
                if not include_hidden and item.name.startswith("."):
                    continue
                
                entry = DirEntry(
                    name=item.name,
                    path=str(item),
                    is_dir=item.is_dir(),
                    size=item.stat().st_size if item.is_file() else 0
                )
                all_entries.append(entry)
            
            # 排序：目录在前，然后按名称
            all_entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
            
            total_count = len(all_entries)
            truncated = total_count > max_entries
            entries = all_entries[:max_entries]
            
            return {
                "success": True,
                "entries": [e.to_dict() for e in entries],
                "truncated": truncated,
                "total_count": total_count
            }
        except Exception as e:
            self.logger.error(f"列出目录失败 {path}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_file_info(self, path: str) -> Dict[str, Any]:
        """
        获取文件信息
        
        Args:
            path: 文件路径
            
        Returns:
            文件信息字典
        """
        resolved = self._resolve_path(path)
        
        if not self._is_path_allowed(resolved):
            return {
                "success": False,
                "error": f"路径不在允许范围内: {path}"
            }
        
        if not resolved.exists():
            return {
                "success": False,
                "error": f"路径不存在: {path}"
            }
        
        try:
            stat = resolved.stat()
            return {
                "success": True,
                "path": str(resolved),
                "name": resolved.name,
                "is_file": resolved.is_file(),
                "is_dir": resolved.is_dir(),
                "size": stat.st_size,
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
