#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SubAgent - 子代理模块 - Phase 3

实现独立上下文的子代理机制，用于：
- 调研代码库 (research)
- 精确搜索 (search)
- 错误诊断 (diagnostic)

核心特性：
1. 独立的消息历史（不污染主 Agent）
2. 受限的工具集（只能使用特定工具）
3. 一次性执行（返回简洁总结）
4. 复用 ReAct Engine
"""

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


from llm.agent.core.engine import ReActEngine, AgentConfig, RunResult
from llm.agent.core.task_session import TaskSession


logger = logging.getLogger("SubAgent")


class SubAgent:
    """
    子代理 - 独立上下文的一次性执行 Agent
    
    特点：
    - 独立 context（空历史或轻量级历史）
    - 受限工具集（只能使用特定工具）
    - 一次性执行（执行完成后只返回总结）
    - 不污染主 Agent 的上下文
    
    使用场景：
    - research: 探索代码库、搜索文件
    - search: 精确查找函数/类定义
    - diagnostic: 分析错误日志
    """
    
    AGENT_TYPES = {
        "research": {
            "description": "调研型 Agent，用于探索代码库、搜索文件",
            "tools": ["Read", "Grep", "Glob", "Ls"],
            "max_steps": 10,
            "max_tool_calls": 15,
            "system_prompt": """你是一个调研型 Agent。

任务：探索代码库，找到用户需要的信息。

工作流程：
1. 使用 Ls 或 Glob 列出文件
2. 使用 Grep 搜索关键字
3. 使用 Read 读取相关文件
4. 总结发现的信息

输出要求：
- 简洁的总结（10 行以内）
- 包含文件路径和行号
- 突出关键发现

可用工具：Read, Grep, Glob, Ls
"""
        },
        "search": {
            "description": "搜索型 Agent，用于精确查找函数/类定义",
            "tools": ["Grep", "Read"],
            "max_steps": 5,
            "max_tool_calls": 8,
            "system_prompt": """你是一个搜索型 Agent。

任务：精确定位函数或类的定义位置。

工作流程：
1. 使用 Grep 搜索函数/类名
2. 使用 Read 确认定义位置
3. 返回精确的文件路径和行号

输出要求：
- 格式：file_path:line_number
- 如果有多个匹配，列出所有位置
- 最多 5 行

可用工具：Grep, Read
"""
        },
        "diagnostic": {
            "description": "诊断型 Agent，用于分析错误日志",
            "tools": ["Read", "Grep"],
            "max_steps": 5,
            "max_tool_calls": 8,
            "system_prompt": """你是一个诊断型 Agent。

任务：分析错误日志，提取关键信息。

工作流程：
1. 读取错误日志
2. 识别错误类型和根因
3. 查找相关文件（如果需要）
4. 提出诊断结论

输出要求：
- 错误原因（1-2 行）
- 相关文件（如果有）
- 建议修复方案（3 行以内）

可用工具：Read, Grep
"""
        }
    }
    
    def __init__(
        self,
        agent_type: str,
        prompt: str,
        tool_registry,
        parent_session: Optional[TaskSession] = None,
        verbose: bool = True
    ):
        """
        初始化子代理
        
        Args:
            agent_type: Agent 类型（research/search/diagnostic）
            prompt: 任务描述
            tool_registry: 工具注册表
            parent_session: 父 Session（可选，用于继承 RAG 知识）
            verbose: 是否输出详细日志
        """
        if agent_type not in self.AGENT_TYPES:
            raise ValueError(f"未知 Agent 类型: {agent_type}。可用类型: {list(self.AGENT_TYPES.keys())}")
        
        self.agent_type = agent_type
        self.config = self.AGENT_TYPES[agent_type]
        self.prompt = prompt
        self.tool_registry = tool_registry
        self.parent_session = parent_session
        self.verbose = verbose
        self.logger = logging.getLogger(f"SubAgent.{agent_type}")
        
        # 创建轻量级 Session
        self.session = self._create_lightweight_session()
        
        # 创建受限的工具注册表
        self.sub_tool_registry = self._create_filtered_tool_registry()
        
        # 创建 ReAct Engine 配置
        self.engine_config = AgentConfig(
            max_steps=self.config["max_steps"],
            max_tool_calls=self.config["max_tool_calls"],
            temperature=0.1,  # 低温度，更确定性
            timeout=60,
            max_tokens=2048,
            verbose=verbose
        )
    
    def _create_lightweight_session(self) -> TaskSession:
        """
        创建轻量级 Session
        
        特点：
        - 独立的消息历史（空历史）
        - 可以继承父 Session 的 RAG 知识
        - 不继承对话历史
        """
        session = TaskSession.create(
            user_goal=self.prompt,
            task_id=f"subagent_{self.agent_type}_{id(self)}"
        )
        
        # 继承父 Session 的 RAG 知识（如果有）
        if self.parent_session:
            session.set_rag_knowledge(self.parent_session.rag_knowledge)
            if self.verbose:
                self.logger.info(f"继承父 Session 的 RAG 知识")
        
        return session
    
    def _create_filtered_tool_registry(self):
        """
        创建受限的工具注册表
        
        只包含当前 Agent 类型允许的工具
        """
        allowed_tools = self.config["tools"]
        
        # 检查 tool_registry 是否有 filter 方法
        if hasattr(self.tool_registry, 'filter'):
            return self.tool_registry.filter(allowed_tools)
        else:
            # 如果没有 filter 方法，手动创建子注册表
            from llm.agent.tools.tool_registry import ToolRegistry
            sub_registry = ToolRegistry()
            
            for tool_name in allowed_tools:
                tool = self.tool_registry.get(tool_name)
                if tool:
                    sub_registry.register(tool)
                else:
                    self.logger.warning(f"工具 {tool_name} 不存在，跳过")
            
            return sub_registry
    
    def run(self) -> str:
        """
        运行子代理
        
        Returns:
            简洁的总结（不超过 200 字）
        """
        if self.verbose:
            self.logger.info(f"[{self.agent_type}] 开始执行: {self.prompt[:50]}...")
        
        # 构建带有 system prompt 的输入
        full_prompt = f"""{self.config['system_prompt']}

---

用户任务：
{self.prompt}

请开始执行，并在完成后给出简洁的总结。
"""
        
        # 创建 ReAct Engine
        engine = ReActEngine(
            config=self.engine_config,
            tool_registry=self.sub_tool_registry,
            conversation_memory=None  # SubAgent 不使用会话记忆
        )
        
        # 执行
        try:
            result: RunResult = engine.run(full_prompt)
            
            if result.success:
                summary = self._extract_summary(result)
                if self.verbose:
                    self.logger.info(f"[{self.agent_type}] 执行成功，共 {result.total_steps} 步，{result.tool_calls} 次工具调用")
                return summary
            else:
                error_msg = result.error or "执行失败"
                if self.verbose:
                    self.logger.warning(f"[{self.agent_type}] 执行失败: {error_msg}")
                return f"执行失败: {error_msg}"
        
        except Exception as e:
            self.logger.error(f"[{self.agent_type}] 执行异常: {e}")
            return f"执行异常: {str(e)}"
    
    def _extract_summary(self, result: RunResult) -> str:
        """
        从 RunResult 中提取简洁总结
        
        Args:
            result: ReAct Engine 的执行结果
            
        Returns:
            简洁总结（不超过 200 字）
        """
        # 优先使用 final_answer
        if result.answer:
            summary = result.answer.strip()
        else:
            # 如果没有 final_answer，尝试从最后一步的 thinking 提取
            if result.steps:
                last_step = result.steps[-1]
                summary = last_step.thinking or last_step.observation or "无总结"
            else:
                summary = "无总结"
        
        # 截断过长的总结
        if len(summary) > 500:
            summary = summary[:500] + "..."
        
        return summary
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """
        获取执行统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "agent_type": self.agent_type,
            "prompt": self.prompt[:100],
            "allowed_tools": self.config["tools"],
            "max_steps": self.config["max_steps"],
            "max_tool_calls": self.config["max_tool_calls"],
        }


# 便捷函数
def create_subagent(
    agent_type: str,
    prompt: str,
    tool_registry,
    parent_session: Optional[TaskSession] = None,
    verbose: bool = True
) -> SubAgent:
    """
    创建 SubAgent
    
    Args:
        agent_type: Agent 类型
        prompt: 任务描述
        tool_registry: 工具注册表
        parent_session: 父 Session
        verbose: 是否输出详细日志
        
    Returns:
        SubAgent 实例
    """
    return SubAgent(
        agent_type=agent_type,
        prompt=prompt,
        tool_registry=tool_registry,
        parent_session=parent_session,
        verbose=verbose
    )
