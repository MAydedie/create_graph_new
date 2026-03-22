#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MemoryAgent - 记忆 Agent - Phase 4

封装 ConversationMemory，提供与 TaskSession 集成的统一接口。

职责：
- 管理对话历史
- 提取相关上下文
- 与 TaskSession 协同工作
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

# 确保项目路径
def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "config" / "config.py").exists():
            return current
        current = current.parent
    return Path.cwd()

PROJECT_ROOT = _find_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from .memory import ConversationMemory, AgentMemory


logger = logging.getLogger("MemoryAgent")


class MemoryAgent:
    """
    记忆 Agent - 封装 ConversationMemory
    
    作为 Multi-Agent 集群的记忆成员，负责：
    1. 管理对话历史
    2. 提供相关上下文检索
    3. 与 TaskSession 协同
    
    Attributes:
        conversation_memory: 对话记忆
        agent_memory: Agent 执行记忆
    """
    
    def __init__(
        self,
        conversation_memory: ConversationMemory = None,
        session_id: str = None,
        llm_api = None,
        storage_path: str = None
    ):
        """
        初始化 MemoryAgent
        
        Args:
            conversation_memory: 已有的对话记忆（可选）
            session_id: 会话 ID（可选）
            llm_api: LLM API（用于生成摘要）
            storage_path: 存储路径
        """
        if conversation_memory:
            self.conversation_memory = conversation_memory
        else:
            self.conversation_memory = ConversationMemory(
                session_id=session_id,
                llm_api=llm_api,
                storage_path=storage_path
            )
        
        self.agent_memory = AgentMemory()
        self.logger = logging.getLogger("MemoryAgent")
    
    def get_relevant_context(self, query: str, max_chars: int = 2000) -> str:
        """
        获取与查询相关的上下文
        
        这是 TaskSession 初始化时调用的主要方法。
        
        Args:
            query: 查询字符串（通常是用户目标）
            max_chars: 最大字符数
            
        Returns:
            格式化的上下文字符串
        """
        try:
            # 使用 ConversationMemory 的语义检索
            context = self.conversation_memory.get_relevant_context(
                query=query,
                max_units=3,
                include_current=True
            )
            
            # 截断过长内容
            if len(context) > max_chars:
                context = context[:max_chars] + "..."
            
            return context
        except Exception as e:
            self.logger.warning(f"获取上下文失败: {e}")
            return ""
    
    def get_conversation_context(self, query: str = None) -> Dict[str, Any]:
        """
        获取对话上下文（用于 TaskSession）
        
        Args:
            query: 可选的查询字符串
            
        Returns:
            对话上下文字典，包含：
            - context: 相关上下文字符串
            - recent_messages: 最近的消息
            - preferences: 用户偏好
            - recent_files: 最近操作的文件
        """
        result = {
            "context": "",
            "recent_messages": [],
            "preferences": {},
            "recent_files": []
        }
        
        try:
            # 获取相关上下文
            if query:
                result["context"] = self.get_relevant_context(query)
            
            # 获取最近消息（使用 current_messages 属性）
            result["recent_messages"] = self.conversation_memory.current_messages[-10:]
            
            # 获取用户偏好（从 user_context 字典获取）
            result["preferences"] = dict(self.conversation_memory.user_context.get("preferences", {}))
            
            # 获取最近文件
            result["recent_files"] = self.conversation_memory.get_recent_files(5)
            
        except Exception as e:
            self.logger.warning(f"获取对话上下文失败: {e}")
        
        return result
    
    def add_conversation(self, user_msg: str, agent_response: str):
        """
        添加对话
        
        Args:
            user_msg: 用户消息
            agent_response: Agent 回复
        """
        self.conversation_memory.add_conversation(user_msg, agent_response)
    
    def add_message(self, role: str, content: str):
        """
        添加单条消息
        
        Args:
            role: 角色（user/assistant）
            content: 消息内容
        """
        self.conversation_memory.add_message(role, content)
    
    def record_action(self, tool_name: str, args: Dict, result: Dict):
        """
        记录工具调用
        
        Args:
            tool_name: 工具名称
            args: 工具参数
            result: 执行结果
        """
        self.agent_memory.add_action(tool_name, args, result)
    
    def update_preference(self, key: str, value: Any):
        """
        更新用户偏好
        
        Args:
            key: 偏好键
            value: 偏好值
        """
        self.conversation_memory.update_preference(key, value)
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """
        获取用户偏好
        
        Args:
            key: 偏好键
            default: 默认值
            
        Returns:
            偏好值
        """
        return self.conversation_memory.get_preference(key, default)
    
    def add_recent_file(self, file_path: str):
        """
        记录最近操作的文件
        
        Args:
            file_path: 文件路径
        """
        self.conversation_memory.add_recent_file(file_path)
    
    def get_current_file(self) -> Optional[str]:
        """获取当前操作的文件"""
        return self.conversation_memory.get_current_file()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        conv_stats = self.conversation_memory.get_stats()
        agent_stats = {
            "action_count": len(self.agent_memory.recent_actions),
            "error_count": len(self.agent_memory.error_history),
            "completed_steps": len(self.agent_memory.current_task.get("steps_completed", []))
        }
        
        return {
            "conversation": conv_stats,
            "agent": agent_stats
        }
    
    def save(self, path: str = None):
        """保存记忆到文件"""
        try:
            self.conversation_memory.save(path)
        except Exception as e:
            self.logger.error(f"保存失败: {e}")
    
    @classmethod
    def load(cls, path: str, llm_api=None) -> "MemoryAgent":
        """
        从文件加载记忆
        
        Args:
            path: 文件路径
            llm_api: LLM API
            
        Returns:
            MemoryAgent 实例
        """
        memory = ConversationMemory.load(path, llm_api)
        return cls(conversation_memory=memory)
    
    def clear(self):
        """清空所有记忆"""
        self.conversation_memory.clear()
        self.agent_memory.clear()


# 便捷函数
def create_memory_agent(
    session_id: str = None,
    llm_api = None,
    storage_path: str = None
) -> MemoryAgent:
    """
    创建 MemoryAgent
    
    Args:
        session_id: 会话 ID
        llm_api: LLM API
        storage_path: 存储路径
        
    Returns:
        MemoryAgent 实例
    """
    return MemoryAgent(
        session_id=session_id,
        llm_api=llm_api,
        storage_path=storage_path
    )
