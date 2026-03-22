#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
记忆模块 (Memory) - Phase 3.5 增强版

实现语义化上下文记忆系统：
- ConversationMemory: 会话级记忆（跨轮对话）
- AgentMemory: Agent 执行记忆（单次任务）

核心创新：
1. 上下文单元化 - 将对话切分为语义单元
2. 按需检索 - 只加载相关上下文，节省 Token
3. 自动摘要 - 为每个单元生成简洁摘要
"""

import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

from .context_unit import ContextUnit
from .context_compressor import ContextCompressor
from .semantic_retriever import SemanticRetriever


class AgentMemory:
    """
    Agent 执行记忆
    
    管理单次任务执行过程中的记忆，包括：
    - 最近的工具调用
    - 执行结果
    - 当前任务状态
    - 错误历史
    """
    
    def __init__(self, max_actions: int = 10):
        """
        初始化 Agent 记忆
        
        Args:
            max_actions: 保留的最大动作数
        """
        self.max_actions = max_actions
        
        # 最近的工具调用
        self.recent_actions: List[Dict[str, Any]] = []
        
        # 最近的执行结果（按工具名索引）
        self.recent_results: Dict[str, Dict[str, Any]] = {}
        
        # 当前任务状态
        self.current_task: Dict[str, Any] = {
            "goal": None,
            "steps_completed": [],
            "steps_remaining": [],
        }
        
        # 错误历史（用于 Reflexion）
        self.error_history: List[Dict[str, Any]] = []
    
    def add_action(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Dict[str, Any]
    ) -> None:
        """
        记录工具调用
        
        Args:
            tool_name: 工具名称
            args: 工具参数
            result: 执行结果
        """
        action = {
            "tool": tool_name,
            "args": args,
            "result": result,
            "timestamp": datetime.now().isoformat(),
            "success": result.get("success", True)
        }
        
        self.recent_actions.append(action)
        
        # 只保留最近 N 条
        if len(self.recent_actions) > self.max_actions:
            self.recent_actions = self.recent_actions[-self.max_actions:]
        
        # 更新最近结果
        self.recent_results[tool_name] = result
        
        # 如果是错误，记录到错误历史
        if not result.get("success", True):
            self.error_history.append({
                "tool": tool_name,
                "error": result.get("error", "Unknown error"),
                "timestamp": datetime.now().isoformat()
            })
    
    def get_last_result(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        获取某个工具的最近结果
        
        Args:
            tool_name: 工具名称
            
        Returns:
            最近的执行结果，不存在则返回 None
        """
        return self.recent_results.get(tool_name)
    
    def get_last_error(self) -> Optional[Dict[str, Any]]:
        """
        获取最近的错误
        
        Returns:
            最近的错误记录
        """
        return self.error_history[-1] if self.error_history else None
    
    def set_task_goal(self, goal: str) -> None:
        """
        设置当前任务目标
        
        Args:
            goal: 任务目标描述
        """
        self.current_task["goal"] = goal
    
    def complete_step(self, step: str) -> None:
        """
        标记步骤完成
        
        Args:
            step: 完成的步骤描述
        """
        self.current_task["steps_completed"].append(step)
        # 从待完成中移除
        if step in self.current_task["steps_remaining"]:
            self.current_task["steps_remaining"].remove(step)
    
    def to_context_string(self) -> str:
        """
        转换为上下文字符串（用于 Prompt）
        
        Returns:
            格式化的上下文信息
        """
        lines = []
        
        # 当前目标
        if self.current_task["goal"]:
            lines.append(f"【当前目标】{self.current_task['goal']}")
        
        # 最近的操作
        if self.recent_actions:
            lines.append("\n【最近操作】")
            for action in self.recent_actions[-3:]:
                status = "✓" if action.get("success", True) else "✗"
                lines.append(f"  {status} {action['tool']}")
        
        # 最近的错误
        if self.error_history:
            last_error = self.error_history[-1]
            lines.append(f"\n【最近错误】{last_error['tool']}: {last_error['error'][:50]}")
        
        return "\n".join(lines)
    
    def clear(self) -> None:
        """清空所有记忆"""
        self.recent_actions = []
        self.recent_results = {}
        self.current_task = {
            "goal": None,
            "steps_completed": [],
            "steps_remaining": [],
        }
        self.error_history = []


class ConversationMemory:
    """
    会话记忆（增强版）
    
    实现语义化上下文管理：
    - 上下文单元化：将对话切分为语义单元
    - 自动摘要：为每个单元生成摘要
    - 按需检索：只加载相关上下文
    
    核心创新点（来自用户的 Skill 思路）：
    - 类似于 Skill 技术的按需分配
    - 通过单元摘要让模型选择相关上下文
    - 大幅节省 Token（约 80%）
    """
    
    def __init__(
        self,
        session_id: str = None,
        llm_api = None,
        storage_path: str = None
    ):
        """
        初始化会话记忆
        
        Args:
            session_id: 会话 ID（可选，自动生成）
            llm_api: LLM API 客户端（用于生成摘要）
            storage_path: 持久化存储路径（可选）
        """
        self.session_id = session_id or self._generate_session_id()
        self.storage_path = Path(storage_path) if storage_path else None
        
        # 用户上下文（用户说过的约定）
        self.user_context: Dict[str, Any] = {
            "preferences": {},      # 如：{"target_dir": "output/"}
            "conventions": {},      # 如：{"code_style": "PEP8"}
            "recent_files": [],     # 最近操作的文件
        }
        
        # 当前工作上下文
        self.working_context: Dict[str, Any] = {
            "current_file": None,
            "current_task": None,
            "last_error": None,
        }
        
        # 上下文单元列表
        self.conversation_units: List[ContextUnit] = []
        
        # 当前正在构建的消息
        self.current_messages: List[Dict[str, str]] = []
        
        # 组件
        self.compressor = ContextCompressor(llm_api)
        self.retriever = SemanticRetriever()
    
    def _generate_session_id(self) -> str:
        """生成会话 ID"""
        return str(uuid.uuid4())[:8]
    
    # ========================
    # 用户偏好管理
    # ========================
    
    def update_preference(self, key: str, value: Any) -> None:
        """
        更新用户偏好
        
        例如：用户说"把文件保存到 output/ 目录"
        调用：update_preference("target_dir", "output/")
        
        Args:
            key: 偏好键名
            value: 偏好值
        """
        self.user_context["preferences"][key] = value
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """
        获取用户偏好
        
        Args:
            key: 偏好键名
            default: 默认值
            
        Returns:
            偏好值
        """
        return self.user_context["preferences"].get(key, default)
    
    def add_recent_file(self, file_path: str) -> None:
        """
        记录最近操作的文件
        
        Args:
            file_path: 文件路径
        """
        # 移除重复
        if file_path in self.user_context["recent_files"]:
            self.user_context["recent_files"].remove(file_path)
        
        # 添加到最前面
        self.user_context["recent_files"].insert(0, file_path)
        
        # 只保留最近 10 个
        self.user_context["recent_files"] = self.user_context["recent_files"][:10]
        
        # 更新当前文件
        self.working_context["current_file"] = file_path
    
    def get_current_file(self) -> Optional[str]:
        """获取当前操作的文件"""
        return self.working_context.get("current_file")
    
    def get_recent_files(self, n: int = 5) -> List[str]:
        """获取最近操作的 n 个文件"""
        return self.user_context["recent_files"][:n]
    
    # ========================
    # 对话管理
    # ========================
    
    def add_conversation(self, user_msg: str, agent_response: str) -> Optional[ContextUnit]:
        """
        添加对话
        
        自动检测是否需要创建新单元
        
        Args:
            user_msg: 用户消息
            agent_response: Agent 回复
            
        Returns:
            如果创建了新单元则返回，否则返回 None
        """
        created_unit = None
        
        # 添加用户消息
        user_message = {"role": "user", "content": user_msg}
        unit = self.compressor.add_message(user_message)
        if unit:
            self.conversation_units.append(unit)
            created_unit = unit
        
        # 添加 Agent 回复
        agent_message = {"role": "assistant", "content": agent_response}
        unit = self.compressor.add_message(agent_message)
        if unit:
            self.conversation_units.append(unit)
            created_unit = unit
        
        # 同步当前消息
        self.current_messages = self.compressor.get_current_messages()
        
        return created_unit
    
    def add_message(self, role: str, content: str) -> Optional[ContextUnit]:
        """
        添加单条消息
        
        Args:
            role: 角色（user/assistant）
            content: 消息内容
            
        Returns:
            如果创建了新单元则返回
        """
        message = {"role": role, "content": content}
        unit = self.compressor.add_message(message)
        
        if unit:
            self.conversation_units.append(unit)
        
        self.current_messages = self.compressor.get_current_messages()
        return unit
    
    # ========================
    # 上下文检索（核心）
    # ========================
    
    def get_relevant_context(
        self,
        query: str,
        max_units: int = 3,
        include_current: bool = True
    ) -> str:
        """
        获取相关上下文（核心方法）
        
        这是用户创新点的实现：按需检索！
        
        Args:
            query: 当前问题
            max_units: 最大检索单元数
            include_current: 是否包含当前正在构建的消息
            
        Returns:
            格式化的上下文字符串
        """
        lines = []
        
        # 1. 用户偏好
        prefs = self.user_context["preferences"]
        if prefs:
            pref_lines = [f"  - {k}: {v}" for k, v in prefs.items()]
            lines.append("【用户偏好】\n" + "\n".join(pref_lines))
        
        # 2. 当前工作上下文
        if self.working_context["current_file"]:
            lines.append(f"【当前文件】{self.working_context['current_file']}")
        
        # 3. 检索相关单元
        if self.conversation_units:
            relevant_units = self.retriever.retrieve_relevant_units(
                query=query,
                units=self.conversation_units,
                top_k=max_units
            )
            
            if relevant_units:
                lines.append("\n【相关对话上下文】")
                for unit in relevant_units:
                    lines.append(f"  • {unit.to_context_string()}")
        
        # 4. 当前正在构建的消息（最近的对话）
        if include_current and self.current_messages:
            recent = self.current_messages[-4:]  # 最近 2 轮
            if recent:
                lines.append("\n【最近对话】")
                for msg in recent:
                    role = "用户" if msg["role"] == "user" else "助手"
                    content = msg["content"][:100]
                    if len(msg["content"]) > 100:
                        content += "..."
                    lines.append(f"  {role}: {content}")
        
        return "\n".join(lines) if lines else ""
    
    def get_all_units_summary(self) -> str:
        """
        获取所有单元的摘要列表
        
        用于调试或展示对话历史概览
        
        Returns:
            格式化的摘要列表
        """
        if not self.conversation_units:
            return "暂无对话历史"
        
        lines = ["【对话历史概览】"]
        for i, unit in enumerate(self.conversation_units, 1):
            lines.append(f"{i}. {unit.to_context_string()}")
        
        return "\n".join(lines)
    
    # ========================
    # 持久化
    # ========================
    
    def save(self, path: str = None) -> None:
        """
        保存会话记忆到文件
        
        Args:
            path: 保存路径（可选，使用初始化时的路径）
        """
        save_path = Path(path) if path else self.storage_path
        if not save_path:
            return
        
        # 确保目录存在
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 强制刷新当前单元
        pending_unit = self.compressor.flush_current_unit()
        if pending_unit:
            self.conversation_units.append(pending_unit)
        
        data = {
            "session_id": self.session_id,
            "user_context": self.user_context,
            "working_context": self.working_context,
            "conversation_units": [
                unit.to_dict() for unit in self.conversation_units
            ],
            "current_messages": self.current_messages,
            "saved_at": datetime.now().isoformat()
        }
        
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, path: str, llm_api=None) -> "ConversationMemory":
        """
        从文件加载会话记忆
        
        Args:
            path: 文件路径
            llm_api: LLM API 客户端
            
        Returns:
            加载的会话记忆
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        memory = cls(
            session_id=data["session_id"],
            llm_api=llm_api,
            storage_path=path
        )
        
        memory.user_context = data["user_context"]
        memory.working_context = data["working_context"]
        memory.conversation_units = [
            ContextUnit.from_dict(unit_data)
            for unit_data in data.get("conversation_units", [])
        ]
        memory.current_messages = data.get("current_messages", [])
        
        return memory
    
    # ========================
    # 统计信息
    # ========================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取记忆统计信息
        
        Returns:
            统计信息字典
        """
        total_messages = sum(
            len(unit.messages) for unit in self.conversation_units
        ) + len(self.current_messages)
        
        total_tokens = sum(
            unit.get_token_estimate() for unit in self.conversation_units
        )
        
        summary_tokens = sum(
            unit.get_summary_token_estimate() for unit in self.conversation_units
        )
        
        return {
            "session_id": self.session_id,
            "total_units": len(self.conversation_units),
            "total_messages": total_messages,
            "current_messages": len(self.current_messages),
            "total_tokens_estimate": total_tokens,
            "summary_tokens_estimate": summary_tokens,
            "token_savings_ratio": 1 - (summary_tokens / max(total_tokens, 1)),
            "preferences_count": len(self.user_context["preferences"]),
            "recent_files_count": len(self.user_context["recent_files"])
        }
    
    def clear(self) -> None:
        """清空所有记忆"""
        self.user_context = {
            "preferences": {},
            "conventions": {},
            "recent_files": [],
        }
        self.working_context = {
            "current_file": None,
            "current_task": None,
            "last_error": None,
        }
        self.conversation_units = []
        self.current_messages = []


# 保持向后兼容
class Memory(AgentMemory):
    """向后兼容的别名"""
    pass
