#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tool 抽象基类与 ToolRegistry 工具注册表

设计思路：
- Tool：定义工具的标准接口（name, description, input_schema, execute）
- ToolRegistry：管理所有工具的注册、查找和列表
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import json
import logging


logger = logging.getLogger("AgentTools")


@dataclass
class ToolInputSchema:
    """工具输入参数模式"""
    properties: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于 LLM 提示）"""
        return {
            "type": "object",
            "properties": self.properties,
            "required": self.required
        }
    
    def to_prompt_string(self) -> str:
        """转换为提示词字符串"""
        params = []
        for name, schema in self.properties.items():
            param_type = schema.get("type", "any")
            desc = schema.get("description", "")
            required = "必填" if name in self.required else "可选"
            params.append(f"  - {name} ({param_type}, {required}): {desc}")
        return "\n".join(params)


class Tool(ABC):
    """
    工具抽象基类
    
    所有工具必须继承此类并实现 execute 方法。
    工具的 name、description、input_schema 将被序列化给 LLM 作为"可用工具说明"。
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称（唯一标识符）"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（告诉 LLM 这个工具做什么）"""
        pass
    
    @property
    def input_schema(self) -> Optional[ToolInputSchema]:
        """
        输入参数模式（可选）
        定义工具接受的参数及其类型
        """
        return None
    
    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行工具
        
        Args:
            **kwargs: 工具参数
            
        Returns:
            执行结果字典，包含：
            - success: bool - 是否成功
            - result: Any - 执行结果
            - error: str (可选) - 错误信息
        """
        pass
    
    def to_prompt_dict(self) -> Dict[str, Any]:
        """转换为 LLM 提示词格式"""
        result = {
            "name": self.name,
            "description": self.description,
        }
        if self.input_schema:
            result["parameters"] = self.input_schema.to_dict()
        return result
    
    def to_prompt_string(self) -> str:
        """转换为可读的提示词字符串"""
        lines = [
            f"工具名称: {self.name}",
            f"描述: {self.description}",
        ]
        if self.input_schema:
            lines.append("参数:")
            lines.append(self.input_schema.to_prompt_string())
        return "\n".join(lines)


class ToolRegistry:
    """
    工具注册表
    
    管理所有可用工具的注册、查找和列表。
    """
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self.logger = logging.getLogger("ToolRegistry")
    
    def register(self, tool: Tool) -> None:
        """
        注册工具
        
        Args:
            tool: 要注册的工具实例
            
        Raises:
            ValueError: 如果工具名称已存在
        """
        if tool.name in self._tools:
            raise ValueError(f"工具 '{tool.name}' 已注册")
        self._tools[tool.name] = tool
        self.logger.debug(f"注册工具: {tool.name}")
    
    def unregister(self, name: str) -> bool:
        """
        取消注册工具
        
        Args:
            name: 工具名称
            
        Returns:
            是否成功取消注册
        """
        if name in self._tools:
            del self._tools[name]
            self.logger.debug(f"取消注册工具: {name}")
            return True
        return False
    
    def get(self, name: str) -> Optional[Tool]:
        """
        获取工具
        
        Args:
            name: 工具名称
            
        Returns:
            工具实例，如果不存在则返回 None
        """
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """
        列出所有已注册的工具名称
        
        Returns:
            工具名称列表
        """
        return list(self._tools.keys())
    
    def get_all_tools(self) -> List[Tool]:
        """
        获取所有已注册的工具实例
        
        Returns:
            工具实例列表
        """
        return list(self._tools.values())
    
    def execute(self, name: str, **kwargs) -> Dict[str, Any]:
        """
        执行指定工具
        
        Args:
            name: 工具名称
            **kwargs: 工具参数
            
        Returns:
            执行结果字典
        """
        tool = self.get(name)
        if not tool:
            return {
                "success": False,
                "error": f"工具 '{name}' 不存在"
            }
        
        try:
            result = tool.execute(**kwargs)
            return result
        except Exception as e:
            self.logger.error(f"执行工具 '{name}' 失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def to_prompt_string(self) -> str:
        """
        生成所有工具的提示词字符串
        
        Returns:
            格式化的工具说明
        """
        if not self._tools:
            return "暂无可用工具"
        
        lines = ["可用工具列表：", ""]
        for i, tool in enumerate(self._tools.values(), 1):
            lines.append(f"【工具 {i}】")
            lines.append(tool.to_prompt_string())
            lines.append("")
        return "\n".join(lines)
    
    def to_json(self) -> str:
        """
        生成所有工具的 JSON 格式描述
        
        Returns:
            JSON 字符串
        """
        tools_data = [tool.to_prompt_dict() for tool in self._tools.values()]
        return json.dumps(tools_data, ensure_ascii=False, indent=2)
