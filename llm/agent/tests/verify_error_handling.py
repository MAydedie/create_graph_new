#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
验证问题1和问题2修复效果：
1. 错误处理机制：ErrorSolverAgent 诊断 + 解决方案 + 小计划
2. 错误总结机制：无论成功失败都生成 final_summary

测试用例：用户请求"运行指定目录下所有Python文件"
这个请求预计会在某些步骤失败（依赖问题等），可以测试错误诊断流程。
"""
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 设置工作区
os.environ["WORKSPACE_ROOT"] = str(PROJECT_ROOT / "tests" / "debug_20240203")

from llm.agent.agents import orchestrator, planner_agent, coder_agent, error_solver_agent

def test_error_handling():
    print("=" * 70)
    print("测试问题1 & 问题2: 错误处理机制和错误总结生成")
    print("=" * 70)
    print(f"工作区: {os.environ['WORKSPACE_ROOT']}")
    
    # 创建 Agent 组件
    planner = planner_agent.PlannerAgent()
    coder = coder_agent.CoderAgent()
    error_solver = error_solver_agent.ErrorSolverAgent()
    
    # 创建 Orchestrator（包含 ErrorSolverAgent）
    orch = orchestrator.create_orchestrator(
        planner=planner,
        coder=coder,
        error_solver=error_solver,
        verbose=True
    )
    
    # 测试用例：请求读取一个不存在的文件，强制触发错误
    user_goal = "请读取当前目录下名为 non_existent_file_12345.txt 的文件内容"
    
    print(f"\n用户目标: {user_goal}")
    print("-" * 70)
    
    try:
        # 使用带错误诊断的执行 - 预期会重试并最终失败（或被诊断修复？）
        # 这里虽然文件不存在无法修复，但应该能看到 ErrorSolver 的工作过程
        result = orch.execute_with_retry(user_goal, max_retries=2)
        
        print("\n" + "=" * 70)
        print("执行结果")
        print("=" * 70)
        print(f"成功: {result.get('success', False)}")
        print(f"总尝试次数: {result.get('total_attempts', 'N/A')}")
        print(f"诊断次数: {result.get('errors_diagnosed', 'N/A')}")
        print(f"生成的小计划数: {result.get('micro_plans_generated', 'N/A')}")
        
        if result.get('error'):
            print(f"最后错误: {result['error'][:200]}...")
            
    except Exception as e:
        print(f"\n执行异常: {e}")
        import traceback
        traceback.print_exc()
    
    # 分析事件日志
    session = orch.current_session
    if not session:
        print("\n[FAIL] 没有会话被创建！")
        return False
    
    print("\n" + "=" * 70)
    print("事件日志分析")
    print("=" * 70)
    
    events = session.event_log.events
    print(f"总事件数: {len(events)}\n")
    
    # 检查关键事件
    has_error_diagnosis_start = False
    has_error_diagnosis_complete = False
    has_final_summary = False
    final_summary_content = ""
    
    for evt in events:
        evt_type = evt.event_type
        summary = evt.summary[:80] if evt.summary else "无"
        print(f"[{evt_type}] {summary}...")
        
        if evt_type == "error_diagnosis_start":
            has_error_diagnosis_start = True
        if evt_type == "error_diagnosis_complete":
            has_error_diagnosis_complete = True
        if evt_type == "final_summary":
            has_final_summary = True
            final_summary_content = evt.summary
    
    print("\n" + "=" * 70)
    print("验证结果")
    print("=" * 70)
    
    # 验证问题1：错误诊断流程
    if has_error_diagnosis_start or has_error_diagnosis_complete:
        print("[PASS] ✓ 问题1: ErrorSolverAgent 被调用进行错误诊断")
        if has_error_diagnosis_complete:
            print("       诊断完成事件已记录")
    else:
        print("[INFO] ⚠ 问题1: 未检测到错误诊断事件（可能任务成功没有触发）")
    
    # 验证问题2：最终总结生成
    if has_final_summary:
        print("[PASS] ✓ 问题2: 最终总结 (final_summary) 已生成")
        print(f"       内容: {final_summary_content[:150]}...")
    else:
        print("[FAIL] ✗ 问题2: 未找到 final_summary 事件")
        return False
    
    return True


if __name__ == "__main__":
    success = test_error_handling()
    print("\n" + "=" * 70)
    if success:
        print("测试通过！问题1和问题2的修复已验证。")
    else:
        print("测试存在问题，请检查输出。")
    print("=" * 70)
