#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试脚本：验证代码生成系统修复是否有效
"""
import sys
sys.path.insert(0, r"D:\代码仓库生图\create_graph")

import asyncio
from llm.agent.agents.orchestrator import Orchestrator
from llm.agent.agents.planner_agent import PlannerAgent
from llm.agent.agents.coder_agent import CoderAgent
from llm.agent.agents.reviewer_agent import ReviewerAgent
from llm.agent.agents.error_solver_agent import ErrorSolverAgent

def test_unit_test_generation():
    """测试单元测试生成（原来会无限循环的场景）"""
    print("=" * 60)
    print("测试：为 utils.py 生成单元测试")
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
    
    # 用户请求
    user_goal = r"为 D:\catnet\CAT-Net-main\lib\utils\utils.py 中的 DCT 处理逻辑编写单元测试。在D:\catnet\CAT-Net-main\lib下新建一个test文件夹，并且将单元测试代码放在这个test文件夹下。"
    
    print(f"\n用户请求: {user_goal}\n")
    print("-" * 60)
    
    # 执行（使用 V4 模式）
    result = orchestrator.execute_with_resolution_loop(user_goal)
    
    print("\n" + "=" * 60)
    print("执行结果:")
    print("=" * 60)
    print(f"成功: {result.get('success')}")
    print(f"状态: {result.get('status')}")
    
    if result.get("error"):
        print(f"错误: {result.get('error')}")
    
    if result.get("resolution_info"):
        info = result["resolution_info"]
        print(f"总错误数: {info.get('total_errors', 0)}")
        print(f"修复计划数: {info.get('micro_plans_executed', 0)}")
    
    print(f"\n摘要:\n{result.get('summary', 'N/A')}")
    
    return result

if __name__ == "__main__":
    test_unit_test_generation()
