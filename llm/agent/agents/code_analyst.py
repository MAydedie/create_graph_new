#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CodeAnalystAgent - 代码分析 Agent

单体 ReAct Agent，用于代码理解和分析。
封装 ReActEngine，自动注册常用工具，提供简单易用的接口。

使用示例：
    from llm.agent.agents.code_analyst import CodeAnalystAgent
    
    agent = CodeAnalystAgent()
    answer = agent.answer("解释一下 GraphRAGSystem.query() 方法")
    print(answer)
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging


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


logger = logging.getLogger("CodeAnalystAgent")


class CodeAnalystAgent:
    """
    代码分析 Agent (Phase 3.5 增强版)
    
    自动注册常用工具，提供简单的问答接口。
    支持通过 ReAct 循环进行多步推理。
    
    Phase 3.5 新增：
    - 会话记忆支持（ConversationMemory）
    - 自动上下文管理
    - 多轮对话优化
    """
    
    def __init__(
        self,
        config = None,
        auto_register_tools: bool = True,
        verbose: bool = True,
        conversation_memory = None,
        enable_memory: bool = False
    ):
        """
        初始化 CodeAnalystAgent
        
        Args:
            config: AgentConfig 配置，如果为 None 则使用默认配置
            auto_register_tools: 是否自动注册常用工具
            verbose: 是否输出详细日志
            conversation_memory: 会话记忆实例（Phase 3.5）
            enable_memory: 是否自动创建会话记忆（如果未提供）
        """
        from ..core.engine import AgentConfig, ReActEngine
        from ..tools.base import ToolRegistry
        
        self.config = config or AgentConfig(verbose=verbose)
        self.tool_registry = ToolRegistry()
        self.logger = logging.getLogger("CodeAnalystAgent")
        
        # Phase 3.5: 会话记忆
        self.conversation_memory = conversation_memory
        if enable_memory and not conversation_memory:
            from ..cognitive.memory import ConversationMemory
            self.conversation_memory = ConversationMemory()
            self.logger.info("已创建会话记忆")
        
        # 配置日志
        if verbose and not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
        # 自动注册工具
        if auto_register_tools:
            self._register_default_tools()
        
        # 创建引擎（传入会话记忆）
        self.engine = ReActEngine(
            config=self.config,
            tool_registry=self.tool_registry,
            conversation_memory=self.conversation_memory
        )
        
        memory_status = "启用" if self.conversation_memory else "禁用"
        self.logger.info(f"CodeAnalystAgent 初始化完成，已注册 {len(self.tool_registry.list_tools())} 个工具，会话记忆: {memory_status}")
    
    def _register_default_tools(self) -> None:
        """注册默认工具"""
        # 文件工具
        try:
            from ..tools.file_tools import ReadFileTool, WriteFileTool, ListDirTool
            self.tool_registry.register(ReadFileTool())
            self.tool_registry.register(ListDirTool())
            # WriteFileTool 默认不注册，避免意外修改文件
            # self.tool_registry.register(WriteFileTool())
            self.logger.debug("已注册文件工具")
        except Exception as e:
            self.logger.warning(f"注册文件工具失败: {e}")
        
        # 图谱工具
        try:
            from ..tools.graph_tools import QueryKnowledgeGraphTool, RetrieveContextTool
            self.tool_registry.register(QueryKnowledgeGraphTool())
            self.tool_registry.register(RetrieveContextTool())
            self.logger.debug("已注册图谱工具")
        except Exception as e:
            self.logger.warning(f"注册图谱工具失败: {e}")
    
    def register_tool(self, tool) -> None:
        """
        注册额外的工具
        
        Args:
            tool: 工具实例
        """
        self.tool_registry.register(tool)
        self.logger.info(f"已注册工具: {tool.name}")
    
    def list_tools(self) -> List[str]:
        """
        列出所有已注册的工具
        
        Returns:
            工具名称列表
        """
        return self.tool_registry.list_tools()
    
    def answer(self, question: str) -> str:
        """
        回答问题（简单接口）
        
        Args:
            question: 用户问题
            
        Returns:
            回答文本
        """
        result = self.run(question)
        return result.get("answer", "抱歉，无法回答这个问题。")
    
    def run(self, question: str) -> Dict[str, Any]:
        """
        运行 Agent（详细结果接口）
        
        Phase 3.5: 自动记录对话到会话记忆
        
        Args:
            question: 用户问题
            
        Returns:
            包含以下字段的字典：
            - success: bool - 是否成功
            - answer: str - 回答文本
            - steps: List - 思考步骤列表
            - total_steps: int - 总步数
            - tool_calls: int - 工具调用次数
            - error: str - 错误信息（如果有）
        """
        self.logger.info(f"开始分析问题: {question[:50]}...")
        
        try:
            result = self.engine.run(question)
            
            # 转换步骤为可序列化格式
            steps = []
            for step in result.steps:
                steps.append({
                    "step": step.step_num,
                    "thinking": step.thinking,
                    "action": step.action,
                    "observation": step.observation[:500] if step.observation else "",
                    "final_answer": step.final_answer
                })
            
            answer = result.answer
            
            # Phase 3.5: 自动记录对话到会话记忆
            if self.conversation_memory and result.success:
                self.conversation_memory.add_conversation(question, answer)
                self.logger.debug("对话已记录到会话记忆")
            
            return {
                "success": result.success,
                "answer": answer,
                "steps": steps,
                "total_steps": result.total_steps,
                "tool_calls": result.tool_calls,
                "error": result.error
            }
        except Exception as e:
            self.logger.error(f"运行失败: {e}")
            return {
                "success": False,
                "answer": f"抱歉，处理问题时出现错误: {e}",
                "steps": [],
                "total_steps": 0,
                "tool_calls": 0,
                "error": str(e)
            }
    
    def debug_run(self, question: str) -> Dict[str, Any]:
        """
        调试模式运行（返回完整信息）
        
        Args:
            question: 用户问题
            
        Returns:
            包含完整调试信息的字典
        """
        result = self.run(question)
        
        # 添加工具列表
        result["available_tools"] = self.list_tools()
        result["config"] = {
            "model_name": self.config.model_name,
            "max_steps": self.config.max_steps,
            "max_tool_calls": self.config.max_tool_calls,
            "temperature": self.config.temperature
        }
        
        return result


# 便捷函数
def create_code_analyst(verbose: bool = True) -> CodeAnalystAgent:
    """
    创建 CodeAnalystAgent 实例
    
    Args:
        verbose: 是否输出详细日志
        
    Returns:
        CodeAnalystAgent 实例
    """
    return CodeAnalystAgent(verbose=verbose)


# 命令行测试入口
if __name__ == "__main__":
    print("=" * 60)
    print("CodeAnalystAgent 交互式测试")
    print("=" * 60)
    
    try:
        agent = create_code_analyst(verbose=True)
        print(f"\n已注册工具: {agent.list_tools()}")
        
        print("\n输入问题进行测试（输入 'quit' 退出）：")
        while True:
            question = input("\n问题: ").strip()
            if question.lower() in ['quit', 'exit', 'q']:
                break
            if not question:
                continue
            
            result = agent.run(question)
            
            print("\n" + "=" * 40)
            print(f"成功: {result['success']}")
            print(f"步数: {result['total_steps']}, 工具调用: {result['tool_calls']}")
            print("\n答案:")
            print(result["answer"])
            
            if result.get("error"):
                print(f"\n错误: {result['error']}")
            
    except Exception as e:
        print(f"初始化失败: {e}")
        import traceback
        traceback.print_exc()
