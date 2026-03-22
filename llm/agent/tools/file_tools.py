#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件系统工具 (File Tools)

提供给 Agent 使用的文件操作工具：
- ReadFileTool: 读取文件内容
- WriteFileTool: 写入文件内容
- ListDirTool: 列出目录内容
"""

from typing import Dict, Any, Optional
from .base import Tool, ToolInputSchema
from ..infrastructure.file_manager import FileManager


class ReadFileTool(Tool):
    """读取文件内容工具"""
    
    def __init__(self, file_manager: Optional[FileManager] = None):
        self._file_manager = file_manager or FileManager()
    
    @property
    def name(self) -> str:
        return "ReadFile"
    
    @property
    def description(self) -> str:
        return "读取指定文件的内容。支持文本文件，大文件会自动截断。"
    
    @property
    def input_schema(self) -> ToolInputSchema:
        return ToolInputSchema(
            properties={
                "path": {
                    "type": "string",
                    "description": "文件路径（相对于项目根目录或绝对路径）"
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "最大读取字节数（可选，默认 50000）"
                }
            },
            required=["path"]
        )
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        path = kwargs.get("path")
        if not path:
            return {"success": False, "error": "缺少必填参数: path"}
        
        max_bytes = kwargs.get("max_bytes")
        result = self._file_manager.safe_read(path, max_bytes=max_bytes)
        
        if result["success"]:
            return {
                "success": True,
                "result": result["content"],
                "truncated": result.get("truncated", False),
                "total_size": result.get("total_size", 0)
            }
        else:
            return result


class WriteFileTool(Tool):
    """写入文件内容工具"""
    
    def __init__(self, file_manager: Optional[FileManager] = None):
        self._file_manager = file_manager or FileManager()
    
    @property
    def name(self) -> str:
        return "WriteFile"
    
    @property
    def description(self) -> str:
        return "将内容写入指定文件。写入前会自动创建备份。"
    
    @property
    def input_schema(self) -> ToolInputSchema:
        return ToolInputSchema(
            properties={
                "path": {
                    "type": "string",
                    "description": "文件路径（相对于项目根目录或绝对路径）"
                },
                "content": {
                    "type": "string",
                    "description": "要写入的内容"
                },
                "create_backup": {
                    "type": "boolean",
                    "description": "是否创建备份（可选，默认 true）"
                }
            },
            required=["path", "content"]
        )
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        path = kwargs.get("path")
        content = kwargs.get("content")
        
        if not path:
            return {"success": False, "error": "缺少必填参数: path"}
        if content is None:
            return {"success": False, "error": "缺少必填参数: content"}
        
        backup = kwargs.get("create_backup", True)
        result = self._file_manager.safe_write(path, content, backup=backup)
        
        if result["success"]:
            return {
                "success": True,
                "result": f"文件已写入: {result['path']}",
                "backup_path": result.get("backup_path")
            }
        else:
            return result


class ListDirTool(Tool):
    """列出目录内容工具"""
    
    def __init__(self, file_manager: Optional[FileManager] = None):
        self._file_manager = file_manager or FileManager()
    
    @property
    def name(self) -> str:
        return "ListDir"
    
    @property
    def description(self) -> str:
        return "列出指定目录的内容，包括文件和子目录。"
    
    @property
    def input_schema(self) -> ToolInputSchema:
        return ToolInputSchema(
            properties={
                "path": {
                    "type": "string",
                    "description": "目录路径（相对于项目根目录或绝对路径）"
                },
                "max_entries": {
                    "type": "integer",
                    "description": "最大返回条目数（可选，默认 200）"
                }
            },
            required=["path"]
        )
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        path = kwargs.get("path")
        if not path:
            return {"success": False, "error": "缺少必填参数: path"}
        
        max_entries = kwargs.get("max_entries")
        result = self._file_manager.list_dir(path, max_entries=max_entries)
        
        if result["success"]:
            # 格式化输出
            entries = result["entries"]
            formatted = []
            for entry in entries:
                if entry["is_dir"]:
                    formatted.append(f"[目录] {entry['name']}/")
                else:
                    size_kb = entry["size"] / 1024
                    formatted.append(f"[文件] {entry['name']} ({size_kb:.1f} KB)")
            
            return {
                "success": True,
                "result": "\n".join(formatted),
                "entries": entries,
                "truncated": result.get("truncated", False),
                "total_count": result.get("total_count", 0)
            }
        else:
            return result
