#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SubAgent 使用示例

演示如何使用 SubAgent 机制：
1. 基本使用
2. 在 Orchestrator 中使用
3. 实际场景示例
"""

import sys
from pathlib import Path

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


from llm.agent.core.subagent import SubAgent
from llm.agent.core.task_session import TaskSession
from llm.agent.tools.tool_registry import ToolRegistry
from llm.agent.agents.orchestrator import Orchestrator


def example_1_basic_usage():
    """示例 1: 基本使用"""
    print("=" * 60)
    print("示例 1: 基本使用 SubAgent")
    print("=" * 60)
    
    # 创建工具注册表
    tool_registry = ToolRegistry()
    
    # 创建 research 类型的 SubAgent
    subagent = SubAgent(
        agent_type="research",
        prompt="列出当前目录下的所有 Python 文件",
        tool_registry=tool_registry,
        verbose=True
    )
    
    # 执行
    print("\n执行 SubAgent...")
    summary = subagent.run()
    
    print(f"\n总结: {summary}")
    print("\n" + "=" * 60 + "\n")


def example_2_with_parent_session():
    """示例 2: 带父 Session 的 SubAgent"""
    print("=" * 60)
    print("示例 2: 带父 Session 的 SubAgent")
    print("=" * 60)
    
    # 创建父 Session
    parent_session = TaskSession.create(user_goal="主任务：分析代码库")
    parent_session.set_rag_knowledge({
        "project_name": "create_graph",
        "main_modules": ["llm", "visualization", "config"]
    })
    
    # 创建工具注册表
    tool_registry = ToolRegistry()
    
    # 创建 SubAgent（继承父 Session 的 RAG 知识）
    subagent = SubAgent(
        agent_type="search",
        prompt="搜索 Orchestrator 类的定义位置",
        tool_registry=tool_registry,
        parent_session=parent_session,
        verbose=True
    )
    
    # 执行
    print("\n执行 SubAgent...")
    summary = subagent.run()
    
    print(f"\n总结: {summary}")
    print(f"\n父 Session 的消息历史长度: {len(parent_session.messages)}")
    print(f"SubAgent Session 的消息历史长度: {len(subagent.session.messages)}")
    print("\n" + "=" * 60 + "\n")


def example_3_orchestrator_spawn():
    """示例 3: 在 Orchestrator 中孵化 SubAgent"""
    print("=" * 60)
    print("示例 3: Orchestrator 孵化 SubAgent")
    print("=" * 60)
    
    # 创建工具注册表
    tool_registry = ToolRegistry()
    
    # 创建 Orchestrator
    orchestrator = Orchestrator(
        tool_registry=tool_registry,
        verbose=True
    )
    
    # 创建主 Session
    session = TaskSession.create(user_goal="主任务：代码分析")
    orchestrator.current_session = session
    
    # 孵化 SubAgent
    print("\n孵化 research 类型的 SubAgent...")
    summary = orchestrator.spawn_subagent(
        agent_type="research",
        prompt="找到项目中所有的 Agent 类"
    )
    
    print(f"\nSubAgent 返回的总结:\n{summary}")
    
    # 检查主 Session 的 event_log
    print(f"\n主 Session 的事件日志数量: {len(session.event_log.events)}")
    if session.event_log.events:
        last_event = session.event_log.events[-1]
        print(f"最后一个事件类型: {last_event.event_type}")
        print(f"最后一个事件总结: {last_event.summary}")
    
    print("\n" + "=" * 60 + "\n")


def example_4_multiple_subagents():
    """示例 4: 串行使用多个 SubAgent"""
    print("=" * 60)
    print("示例 4: 串行使用多个 SubAgent")
    print("=" * 60)
    
    tool_registry = ToolRegistry()
    orchestrator = Orchestrator(tool_registry=tool_registry, verbose=True)
    session = TaskSession.create(user_goal="多步骤分析")
    orchestrator.current_session = session
    
    # 步骤 1: 调研
    print("\n步骤 1: 调研项目结构...")
    summary1 = orchestrator.spawn_subagent(
        agent_type="research",
        prompt="列出 llm/agent 目录下的所有模块"
    )
    print(f"调研结果: {summary1[:100]}...")
    
    # 步骤 2: 搜索
    print("\n步骤 2: 搜索特定类...")
    summary2 = orchestrator.spawn_subagent(
        agent_type="search",
        prompt="找到 TaskSession 类的定义"
    )
    print(f"搜索结果: {summary2[:100]}...")
    
    # 步骤 3: 诊断（模拟）
    print("\n步骤 3: 诊断分析...")
    summary3 = orchestrator.spawn_subagent(
        agent_type="diagnostic",
        prompt="分析项目的依赖关系"
    )
    print(f"诊断结果: {summary3[:100]}...")
    
    print(f"\n总共执行了 {len(session.event_log.events)} 个 SubAgent")
    print("\n" + "=" * 60 + "\n")


def example_5_tool_restriction():
    """示例 5: 验证工具限制"""
    print("=" * 60)
    print("示例 5: 验证工具限制")
    print("=" * 60)
    
    tool_registry = ToolRegistry()
    
    # 创建不同类型的 SubAgent
    agent_types = ["research", "search", "diagnostic"]
    
    for agent_type in agent_types:
        subagent = SubAgent(
            agent_type=agent_type,
            prompt="测试任务",
            tool_registry=tool_registry,
            verbose=False
        )
        
        allowed_tools = subagent.config["tools"]
        print(f"\n{agent_type} 类型允许的工具: {', '.join(allowed_tools)}")
        print(f"  - 最大步数: {subagent.config['max_steps']}")
        print(f"  - 最大工具调用: {subagent.config['max_tool_calls']}")
    
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("SubAgent 机制使用示例")
    print("=" * 60 + "\n")
    
    # 运行示例（注释掉需要实际执行的示例，避免耗时）
    # example_1_basic_usage()
    # example_2_with_parent_session()
    # example_3_orchestrator_spawn()
    # example_4_multiple_subagents()
    example_5_tool_restriction()
    
    print("\n所有示例完成！")
