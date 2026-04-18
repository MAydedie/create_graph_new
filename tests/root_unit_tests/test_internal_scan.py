#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查 _execute_internal 中的文件扫描是否被调用
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(r"D:\代码仓库生图\create_graph")
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["WORKSPACE_ROOT"] = str(PROJECT_ROOT)

def test_internal_scan():
    """直接测试 _execute_internal 中的文件扫描"""
    print("=" * 60)
    print("测试 _execute_internal 中的文件扫描")
    print("=" * 60)
    
    from llm.agent.agents import orchestrator, planner_agent
    from llm.agent.core.task_session import TaskSession
    
    # 创建 Orchestrator
    orch = orchestrator.Orchestrator(verbose=True)
    orch.planner = planner_agent.PlannerAgent(verbose=True)
    
    user_goal = r"只为D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"
    
    print(f"\n用户目标: {user_goal}")
    
    # 模拟 _execute_internal 的前几步
    print("\n--- 步骤 1: 创建 Session ---")
    session = TaskSession.create(user_goal=user_goal)
    orch.current_session = session
    
    print("\n--- 步骤 2: 扫描文件 ---")
    file_scan_result = orch._scan_files_from_goal(user_goal)
    print(f"扫描结果: scanned={file_scan_result.get('scanned')}")
    print(f"源文件数量: {len(file_scan_result.get('source_files', []))}")
    
    if file_scan_result.get("scanned"):
        session.set_file_structure(file_scan_result)
        print("✓ 文件结构已注入 Session")
    
    print("\n--- 步骤 3: 获取 Planner 上下文 ---")
    planner_context = session.get_context_for_agent("planner")
    
    fs = planner_context.get("file_structure", {})
    print(f"file_structure in context: scanned={fs.get('scanned')}")
    print(f"source_files in context: {len(fs.get('source_files', []))}")
    
    print("\n--- 步骤 4: 构建 Prompt ---")
    prompt = orch.planner._build_prompt(user_goal, planner_context)
    
    # 检查 Prompt 内容
    has_file_list = "源文件（需要生成测试）" in prompt
    has_calculator = "calculator.py" in prompt
    has_no_wildcard_rule = "禁止使用通配符" in prompt
    
    print(f"Prompt 长度: {len(prompt)}")
    print(f"包含 '源文件（需要生成测试）': {has_file_list}")
    print(f"包含 'calculator.py': {has_calculator}")
    print(f"包含 '禁止使用通配符' 规则: {has_no_wildcard_rule}")
    
    if has_file_list and has_calculator and has_no_wildcard_rule:
        print("\n✓ Prompt 构建正确！")
    else:
        print("\n❌ Prompt 缺少关键内容！")
        print("\nPrompt 内容:")
        print("-" * 40)
        print(prompt)
        print("-" * 40)
    
    # 可选：测试 LLM 调用
    print("\n--- 步骤 5: 调用 Planner 生成计划 ---")
    plan = orch.planner.plan(user_goal, planner_context)
    
    print(f"\n计划步骤数: {len(plan.get('steps', []))}")
    for step in plan.get("steps", []):
        target = step.get("target", "N/A")
        has_wildcard = "*" in target or "?" in target
        status = "❌" if has_wildcard else "✓"
        print(f"  {status} 步骤 {step.get('step_id')}: {step.get('action')} -> {target}")

if __name__ == "__main__":
    test_internal_scan()
