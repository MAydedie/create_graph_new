#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
完整集成测试：模拟实际用户请求，验证 Planner 生成的计划不含通配符
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(r"D:\代码仓库生图\create_graph")
sys.path.insert(0, str(PROJECT_ROOT))

def test_full_flow():
    """测试完整流程"""
    print("=" * 60)
    print("完整集成测试：验证 Planner 计划生成")
    print("=" * 60)
    
    from llm.agent.agents.orchestrator import Orchestrator
    from llm.agent.agents.planner_agent import PlannerAgent
    from llm.agent.core.task_session import TaskSession
    
    user_goal = r"只为D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"
    
    print(f"\n用户目标: {user_goal}")
    
    # Step 1: 创建 Orchestrator 并扫描文件
    print("\n--- Step 1: 扫描文件 ---")
    orchestrator = Orchestrator(verbose=True)
    file_scan_result = orchestrator._scan_files_from_goal(user_goal)
    
    print(f"\n扫描结果:")
    print(f"  - 源文件: {len(file_scan_result.get('source_files', []))} 个")
    print(f"  - 测试文件: {len(file_scan_result.get('test_files', []))} 个")
    
    # Step 2: 创建 TaskSession 并注入文件结构
    print("\n--- Step 2: 创建 TaskSession ---")
    session = TaskSession.create(user_goal=user_goal)
    session.set_file_structure(file_scan_result)
    
    planner_context = session.get_context_for_agent("planner")
    
    # Step 3: 生成计划
    print("\n--- Step 3: 调用 Planner 生成计划 ---")
    planner = PlannerAgent(verbose=True)
    plan = planner.plan(user_goal, planner_context)
    
    # Step 4: 检查计划
    print("\n--- Step 4: 检查计划 ---")
    print(f"\n生成的计划:")
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    
    # 检查通配符
    print("\n" + "=" * 60)
    print("通配符检查结果")
    print("=" * 60)
    
    steps = plan.get("steps", [])
    wildcard_found = False
    
    for step in steps:
        target = step.get("target", "")
        action = step.get("action", "")
        step_id = step.get("step_id", "?")
        
        if "*" in target or "?" in target:
            print(f"❌ 步骤 {step_id} ({action}): 包含通配符 -> {target}")
            wildcard_found = True
        else:
            print(f"✓ 步骤 {step_id} ({action}): OK -> {target}")
    
    print("\n" + "=" * 60)
    if wildcard_found:
        print("⚠️ 仍然存在通配符问题！")
    else:
        print("✓ 所有步骤都使用具体路径！")
    print("=" * 60)
    
    return plan, wildcard_found

if __name__ == "__main__":
    plan, has_wildcards = test_full_flow()
    
    if has_wildcards:
        print("\n需要进一步调查为什么 LLM 仍然生成通配符。")
    else:
        print("\n修复成功！可以进行实际测试。")
