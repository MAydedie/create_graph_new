#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 4 阶段2 测试文件

测试 PlannerAgent + CoderAgent + ReviewerAgent
"""

import sys
import io

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, r"D:\代码仓库生图\create_graph")


def test_planner_import():
    """测试 PlannerAgent 导入"""
    print("\n=== 测试 PlannerAgent 导入 ===")
    
    from llm.agent.agents.planner_agent import PlannerAgent, create_planner_agent
    
    planner = PlannerAgent(verbose=False)
    assert planner is not None
    assert planner._llm_api is None  # 延迟加载
    
    # 测试 prompt 构建
    prompt = planner._build_prompt(
        user_goal="添加用户认证功能",
        context={
            "rag_knowledge": {"context_summary": "相关知识"},
            "current_status": "执行中"
        }
    )
    assert "添加用户认证功能" in prompt
    assert "相关知识" in prompt
    
    print("[PASS] PlannerAgent 导入测试通过")
    return True


def test_coder_import():
    """测试 CoderAgent 导入"""
    print("\n=== 测试 CoderAgent 导入 ===")
    
    from llm.agent.agents.coder_agent import CoderAgent, create_coder_agent
    
    coder = CoderAgent(verbose=False)
    assert coder is not None
    assert coder._llm_api is None  # 延迟加载
    
    # 测试读取文件
    result = coder._execute_read("config/config.py", {})
    # 文件可能存在或不存在，但方法应该正常返回
    assert "success" in result
    
    print("[PASS] CoderAgent 导入测试通过")
    return True


def test_reviewer_import():
    """测试 ReviewerAgent 导入"""
    print("\n=== 测试 ReviewerAgent 导入 ===")
    
    from llm.agent.agents.reviewer_agent import ReviewerAgent, create_reviewer_agent
    
    reviewer = ReviewerAgent(verbose=False)
    assert reviewer is not None
    
    # 测试简单审查
    result = reviewer.review({
        "action": "read_file",
        "target": "test.py",
        "success": True,
        "summary": "读取成功"
    })
    
    assert result.get("success") == True
    assert result.get("approved") == True
    
    print("[PASS] ReviewerAgent 导入测试通过")
    return True


def test_orchestrator_integration():
    """测试 Orchestrator 与 Agent 集成"""
    print("\n=== 测试 Orchestrator 集成 ===")
    
    from llm.agent.agents.orchestrator import Orchestrator
    from llm.agent.agents.planner_agent import PlannerAgent
    from llm.agent.agents.coder_agent import CoderAgent
    from llm.agent.agents.reviewer_agent import ReviewerAgent
    
    # 创建不调用 LLM 的简化测试
    orchestrator = Orchestrator(
        planner=PlannerAgent(verbose=False),
        coder=CoderAgent(verbose=False),
        reviewer=ReviewerAgent(verbose=False),
        verbose=False
    )
    
    assert orchestrator.planner is not None
    assert orchestrator.coder is not None
    assert orchestrator.reviewer is not None
    
    print("[PASS] Orchestrator 集成测试通过")
    return True


def test_task_session_with_agents():
    """测试 TaskSession 与 Agent 协同"""
    print("\n=== 测试 TaskSession 与 Agent 协同 ===")
    
    from llm.agent.core.task_session import TaskSession
    from llm.agent.agents.planner_agent import PlannerAgent
    from llm.agent.agents.coder_agent import CoderAgent
    from llm.agent.agents.reviewer_agent import ReviewerAgent
    
    # 创建会话
    session = TaskSession.create(user_goal="测试任务")
    
    # 设置计划
    plan = {
        "plan_id": "test_plan",
        "goal": "测试任务",
        "steps": [
            {"step_id": 0, "type": "analysis", "action": "read_file", "target": "test.py", "description": "读取测试文件"}
        ]
    }
    session.set_plan(plan)
    
    # 获取 Coder 上下文
    coder_ctx = session.get_context_for_agent("coder")
    assert "step" in coder_ctx
    assert coder_ctx["step"]["action"] == "read_file"
    
    # 获取 Reviewer 上下文
    reviewer_ctx = session.get_context_for_agent("reviewer")
    assert "coder_result" in reviewer_ctx
    
    # 更新状态
    session.update_state("coder", "start_step")
    assert session.execution_state.current_agent == "coder"
    
    session.update_state("coder", "complete_step", {"summary": "分析完成"})
    assert session.step_results.get(0) is not None
    
    print("[PASS] TaskSession 与 Agent 协同测试通过")
    return True


def test_full_flow_mock():
    """测试完整流程（Mock 版本，不调用 LLM）"""
    print("\n=== 测试完整流程（Mock）===")
    
    from llm.agent.core.task_session import TaskSession
    from llm.agent.core.execution_state import StepStatus, TaskStatus
    
    # 1. 创建会话
    session = TaskSession.create(user_goal="添加日志功能")
    print(f"  创建会话: {session.task_id}")
    
    # 2. 模拟设置 RAG 知识
    session.set_rag_knowledge({
        "knowledge_items": [{"question": "如何添加日志", "answer": "使用 logging 模块"}],
        "context_summary": "相关知识：使用 Python logging 模块"
    })
    print("  设置 RAG 知识")
    
    # 3. 模拟 Planner 生成计划
    plan = {
        "plan_id": "plan_001",
        "goal": "添加日志功能",
        "analysis": "需要在主模块中添加日志记录",
        "steps": [
            {"step_id": 0, "type": "analysis", "action": "read_file", "target": "main.py", "description": "分析主模块"},
            {"step_id": 1, "type": "code_change", "action": "modify_file", "target": "main.py", "description": "添加日志代码"},
            {"step_id": 2, "type": "verify", "action": "run_tests", "target": "tests/", "description": "运行测试"}
        ]
    }
    session.set_plan(plan)
    print(f"  设置计划: {len(plan['steps'])} 步")
    
    # 4. 模拟执行步骤
    for i, step in enumerate(plan["steps"]):
        session.execution_state.current_step_id = i
        
        # 开始步骤
        session.update_state("orchestrator", "start_step")
        print(f"  执行步骤 {i}: {step['description']}")
        
        # 完成步骤
        session.update_state("coder", "complete_step", {"summary": f"完成 {step['description']}"})
        
        # 前进
        if i < len(plan["steps"]) - 1:
            session.advance_to_next_step()
    
    # 5. 标记完成
    session.mark_completed()
    
    # 验证
    assert session.status == TaskStatus.COMPLETED
    assert session.execution_state.get_progress_percentage() == 100.0
    
    summary = session.get_summary()
    print(f"  任务完成: 进度 {summary['progress']}%")
    print(f"  事件数: {summary['total_events']}")
    
    print("[PASS] 完整流程测试通过")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Phase 4 阶段2 - 测试")
    print("=" * 60)
    
    tests = [
        ("PlannerAgent Import", test_planner_import),
        ("CoderAgent Import", test_coder_import),
        ("ReviewerAgent Import", test_reviewer_import),
        ("Orchestrator Integration", test_orchestrator_integration),
        ("TaskSession with Agents", test_task_session_with_agents),
        ("Full Flow Mock", test_full_flow_mock),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"\n[FAIL] {name} 测试失败: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
