#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模拟生产环境测试：使用与服务器相同的 execute_with_retry 路径
"""

import sys
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(r"D:\代码仓库生图\create_graph")
sys.path.insert(0, str(PROJECT_ROOT))

# 设置工作区
os.environ["WORKSPACE_ROOT"] = str(PROJECT_ROOT)

def test_production_flow():
    """模拟服务器的实际调用路径"""
    print("=" * 60)
    print("模拟生产环境测试")
    print("(使用与服务器相同的 execute_with_retry 路径)")
    print("=" * 60)
    
    # 模拟服务器初始化
    from llm.agent.agents import orchestrator, planner_agent, coder_agent, reviewer_agent
    from llm.agent.cognitive import knowledge_agent
    
    ka = knowledge_agent.KnowledgeAgent()
    planner = planner_agent.PlannerAgent()
    coder = coder_agent.CoderAgent()
    reviewer = reviewer_agent.ReviewerAgent()
    
    orch = orchestrator.create_orchestrator(
        knowledge_agent=ka,
        memory_agent=None,  # 简化测试
        planner=planner,
        coder=coder,
        reviewer=reviewer,
        verbose=True
    )
    
    user_goal = r"只为D:\代码仓库生图\create_graph\test_sandbox下的所有函数生成测试文件"
    
    print(f"\n用户目标: {user_goal}")
    print("\n---开始执行（与服务器相同的路径）---\n")
    
    # 使用与服务器相同的方法
    result = orch.execute_with_retry(user_goal, max_retries=1)
    
    print("\n---执行结果---")
    print(f"成功: {result.get('success')}")
    
    session = orch.get_current_session()
    if session and session.plan:
        print(f"\n生成的计划步骤:")
        for step in session.plan.get("steps", []):
            target = step.get("target", "")
            action = step.get("action", "")
            step_id = step.get("step_id", "?")
            has_wildcard = "*" in target or "?" in target
            status = "❌ 含通配符" if has_wildcard else "✓"
            print(f"  {status} 步骤 {step_id} ({action}): {target}")
    
    return result

if __name__ == "__main__":
    result = test_production_flow()
    print("\n测试完成")
