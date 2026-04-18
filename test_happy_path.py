#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试脚本：验证 Happy Path 和 总结生成
"""
import sys
import os
import json
sys.path.insert(0, r"D:\代码仓库生图\create_graph")

from llm.agent.agents.orchestrator import Orchestrator
from llm.agent.agents.planner_agent import PlannerAgent
from llm.agent.agents.coder_agent import CoderAgent
from llm.agent.agents.reviewer_agent import ReviewerAgent
from llm.agent.agents.error_solver_agent import ErrorSolverAgent

def test_happy_path():
    """测试正常流程并验证总结生成"""
    print("=" * 60)
    print("测试：Happy Path + 总结生成")
    print("=" * 60)
    
    # 创建各 Agent
    planner = PlannerAgent(verbose=True)
    coder = CoderAgent(verbose=True)
    reviewer = ReviewerAgent(verbose=True)
    error_solver = ErrorSolverAgent(verbose=True)
    
    # 创建 Orchestrator
    orchestrator = Orchestrator(
        planner=planner,
        coder=coder,
        reviewer=reviewer,
        error_solver=error_solver,
        verbose=True
    )
    
    # 简单的用户请求 - 纯计算，避免复杂文件操作
    workspace = r"D:\代码仓库生图\create_graph"
    os.environ["WORKSPACE_ROOT"] = workspace
    user_goal = "Use python to calculate 12345 * 6789 and print the result."
    
    print(f"\n用户请求: {user_goal}\n")
    print("-" * 60)
    
    # 执行（使用 V4 模式）
    result = orchestrator.execute_with_resolution_loop(user_goal)
    
    print("\n" + "=" * 60)
    print("执行结果验证:")
    print("=" * 60)
    print(f"Success: {result.get('success')}")
    
    # 验证是否生成了 summary
    session = orchestrator.get_current_session()
    events = session.event_log.events
    
    summary_event = None
    for evt in events:
        if evt.event_type == "final_summary":
            summary_event = evt
            break
            
    if summary_event:
        print("✅ 检测到 final_summary 事件")
        print(f"总结内容:\n{summary_event.summary}")
    else:
        print("❌ 未检测到 final_summary 事件")
        
    return result

if __name__ == "__main__":
    test_happy_path()
