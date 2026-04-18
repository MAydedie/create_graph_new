#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Debug Script: 测试 Multi-Agent 系统的文件扫描和规划流程
"""

import sys
import json
from pathlib import Path

# 确保项目路径
PROJECT_ROOT = Path(r"D:\代码仓库生图\create_graph")
sys.path.insert(0, str(PROJECT_ROOT))

def test_scanner():
    """测试扫描器"""
    print("=" * 60)
    print("测试1：文件扫描器")
    print("=" * 60)
    
    from llm.agent.agents.orchestrator import Orchestrator
    
    orchestrator = Orchestrator(verbose=True)
    user_goal = r"只为D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"
    
    result = orchestrator._scan_files_from_goal(user_goal)
    
    print("\n扫描结果:")
    print(f"  scanned: {result.get('scanned')}")
    print(f"  paths: {result.get('paths')}")
    print(f"  source_files 数量: {len(result.get('source_files', []))}")
    print(f"  test_files 数量: {len(result.get('test_files', []))}")
    
    print("\n源文件列表:")
    for f in result.get("source_files", []):
        print(f"    - {f}")
    
    print("\n文件结构内容:")
    print(result.get("file_structure", ""))
    
    return result

def test_planner_prompt(file_scan_result):
    """测试 Planner Prompt 构建"""
    print("\n" + "=" * 60)
    print("测试2：Planner Prompt 构建")
    print("=" * 60)
    
    from llm.agent.agents.planner_agent import PlannerAgent
    
    planner = PlannerAgent(verbose=True)
    user_goal = r"只为D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"
    
    # 模拟 TaskSession 传递的 context
    context = {
        "task_id": "test_task",
        "user_goal": user_goal,
        "rag_knowledge": {},
        "conversation_context": {},
        "file_structure": file_scan_result,  # 注入扫描结果
    }
    
    prompt = planner._build_prompt(user_goal, context)
    
    print("\n生成的 Prompt (前2000字符):")
    print("-" * 40)
    print(prompt[:2000])
    if len(prompt) > 2000:
        print(f"\n... (总共 {len(prompt)} 字符)")
    
    return prompt

def test_full_plan_generation(file_scan_result):
    """测试完整的计划生成（调用 LLM）"""
    print("\n" + "=" * 60)
    print("测试3：完整计划生成（调用 LLM）")
    print("=" * 60)
    
    from llm.agent.agents.planner_agent import PlannerAgent
    
    planner = PlannerAgent(verbose=True)
    user_goal = r"只为D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"
    
    context = {
        "task_id": "test_task",
        "user_goal": user_goal,
        "rag_knowledge": {},
        "conversation_context": {},
        "file_structure": file_scan_result,
    }
    
    plan = planner.plan(user_goal, context)
    
    print("\n生成的计划:")
    print("-" * 40)
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    
    # 检查是否有通配符
    print("\n检查通配符:")
    steps = plan.get("steps", [])
    has_wildcard = False
    for step in steps:
        target = step.get("target", "")
        if "*" in target or "?" in target:
            print(f"  ❌ 步骤 {step.get('step_id')}: 目标包含通配符 -> {target}")
            has_wildcard = True
        else:
            print(f"  ✓ 步骤 {step.get('step_id')}: 目标正常 -> {target}")
    
    if has_wildcard:
        print("\n⚠️ 发现通配符问题！")
    else:
        print("\n✓ 所有步骤都使用具体路径")
    
    return plan

if __name__ == "__main__":
    print("开始 Multi-Agent 调试测试\n")
    
    # 测试1：扫描器
    scan_result = test_scanner()
    
    # 测试2：Prompt 构建
    prompt = test_planner_prompt(scan_result)
    
    # 测试3：完整计划生成（可选，会调用 LLM）
    user_input = input("\n是否测试完整计划生成（会调用 LLM）？(y/n): ")
    if user_input.lower() == 'y':
        plan = test_full_plan_generation(scan_result)
    
    print("\n调试测试完成")
