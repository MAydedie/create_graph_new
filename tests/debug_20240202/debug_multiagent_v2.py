#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Debug Script V2: 精确追踪文件扫描和上下文传递
"""

import sys
import json
from pathlib import Path

# 确保项目路径
PROJECT_ROOT = Path(r"D:\代码仓库生图\create_graph")
sys.path.insert(0, str(PROJECT_ROOT))

def test_scanner_detailed():
    """详细测试扫描器"""
    print("=" * 60)
    print("测试1：详细扫描器测试")
    print("=" * 60)
    
    from llm.agent.agents.orchestrator import Orchestrator
    
    orchestrator = Orchestrator(verbose=False)  # 关闭默认日志
    user_goal = r"只为D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"
    
    result = orchestrator._scan_files_from_goal(user_goal)
    
    print(f"\n返回结果类型: {type(result)}")
    print(f"返回结果 keys: {result.keys()}")
    print(f"\nscanned: {result.get('scanned')}")
    print(f"paths: {result.get('paths')}")
    print(f"source_files: {result.get('source_files')}")
    print(f"test_files: {result.get('test_files')}")
    print(f"\nfile_structure 内容长度: {len(result.get('file_structure', ''))}")
    print(f"\nfile_structure 内容预览:\n{result.get('file_structure', '')[:500]}")
    
    return result

def test_task_session_context(file_scan_result):
    """测试 TaskSession 上下文传递"""
    print("\n" + "=" * 60)
    print("测试2：TaskSession 上下文传递")
    print("=" * 60)
    
    from llm.agent.core.task_session import TaskSession
    
    user_goal = r"只为D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"
    
    # 创建 TaskSession
    session = TaskSession.create(user_goal=user_goal)
    
    # 设置文件结构
    print(f"\n设置前 file_structure: {session.file_structure}")
    session.set_file_structure(file_scan_result)
    print(f"设置后 file_structure: {session.file_structure}")
    
    # 获取 planner 上下文
    planner_context = session.get_context_for_agent("planner")
    
    print(f"\nplanner_context keys: {planner_context.keys()}")
    
    fs_in_context = planner_context.get("file_structure", {})
    print(f"\n从上下文获取的 file_structure:")
    print(f"  类型: {type(fs_in_context)}")
    print(f"  scanned: {fs_in_context.get('scanned')}")
    print(f"  source_files 数量: {len(fs_in_context.get('source_files', []))}")
    print(f"  test_files 数量: {len(fs_in_context.get('test_files', []))}")
    
    return planner_context

def test_build_prompt(planner_context):
    """测试 _build_prompt"""
    print("\n" + "=" * 60)
    print("测试3：_build_prompt 构建")
    print("=" * 60)
    
    from llm.agent.agents.planner_agent import PlannerAgent
    
    planner = PlannerAgent(verbose=False)
    user_goal = r"只为D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"
    
    prompt = planner._build_prompt(user_goal, planner_context)
    
    print(f"\nPrompt 长度: {len(prompt)}")
    print(f"\n是否包含 '源文件（需要生成测试）': {'源文件（需要生成测试）' in prompt}")
    print(f"是否包含 '禁止使用通配符': {'禁止使用通配符' in prompt}")
    print(f"是否包含 'calculator.py': {'calculator.py' in prompt}")
    
    print(f"\n完整 Prompt:\n")
    print("-" * 40)
    print(prompt)
    print("-" * 40)
    
    return prompt

if __name__ == "__main__":
    print("开始 Multi-Agent 详细调试测试\n")
    
    # 测试1：扫描器
    scan_result = test_scanner_detailed()
    
    # 测试2：TaskSession 上下文
    planner_context = test_task_session_context(scan_result)
    
    # 测试3：_build_prompt
    prompt = test_build_prompt(planner_context)
    
    print("\n调试测试完成")
