#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 4 阶段1 测试文件

测试 TaskSession + ExecutionState + EventLog + KnowledgeAgent + Orchestrator
"""

import sys
import io

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, r"D:\代码仓库生图\create_graph")


def test_step_status():
    """测试 StepStatus 枚举"""
    print("\n=== 测试 StepStatus ===")
    
    from llm.agent.core.execution_state import StepStatus, TaskStatus
    
    # 验证枚举值
    assert StepStatus.PENDING.value == "pending"
    assert StepStatus.IN_PROGRESS.value == "in_progress"
    assert StepStatus.COMPLETED.value == "completed"
    assert StepStatus.FAILED.value == "failed"
    assert StepStatus.RETRYING.value == "retrying"
    
    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.COMPLETED.value == "completed"
    
    print("[PASS] StepStatus 和 TaskStatus 枚举正确")
    return True


def test_execution_state():
    """测试 ExecutionState"""
    print("\n=== 测试 ExecutionState ===")
    
    from llm.agent.core.execution_state import ExecutionState, StepStatus
    
    state = ExecutionState()
    
    # 测试初始状态
    assert state.current_step_id == 0
    assert state.current_step_status == StepStatus.PENDING
    assert state.current_agent is None
    
    # 测试状态更新
    state.current_step_id = 1
    state.current_step_status = StepStatus.IN_PROGRESS
    state.current_agent = "coder"
    state.last_action_summary = "正在修改 auth.py"
    state.total_steps = 5
    state.update_step_status(0, StepStatus.COMPLETED)
    state.update_step_status(1, StepStatus.IN_PROGRESS)
    
    # 测试状态摘要
    summary = state.get_status_summary()
    print(f"状态摘要:\n{summary}")
    
    assert "Step 1 / 5" in summary
    assert "in_progress" in summary
    assert "coder" in summary
    
    # 测试进度
    progress = state.get_progress_percentage()
    assert progress == 20.0  # 1/5 = 20%
    
    print("[PASS] ExecutionState 测试通过")
    return True


def test_event_log():
    """测试 EventLog"""
    print("\n=== 测试 EventLog ===")
    
    from llm.agent.core.execution_state import EventLog
    
    log = EventLog()
    
    # 记录事件
    log.log("step_start", "planner", 0, "开始分析需求")
    log.log("step_complete", "planner", 0, "需求分析完成")
    log.log("step_start", "coder", 1, "开始修改 auth.py")
    log.log("step_fail", "coder", 1, "权限不足，无法写入文件")
    log.log("retry", "orchestrator", 1, "重试执行")
    
    # 测试获取事件
    assert len(log) == 5
    
    recent = log.get_recent_events(3)
    assert len(recent) == 3
    
    step_events = log.get_events_for_step(1)
    assert len(step_events) == 3
    
    fail_feedback = log.get_failure_feedback(1)
    assert "权限不足" in fail_feedback
    
    # 测试上下文生成
    coder_context = log.generate_context_summary("coder", 1)
    print(f"Coder 上下文:\n{coder_context}")
    assert "返工原因" in coder_context or "前序" in coder_context
    
    # 测试全部事件摘要
    all_summary = log.get_all_events_summary()
    print(f"全部事件摘要:\n{all_summary}")
    
    print("[PASS] EventLog 测试通过")
    return True


def test_task_session():
    """测试 TaskSession"""
    print("\n=== 测试 TaskSession ===")
    
    from llm.agent.core.task_session import TaskSession
    from llm.agent.core.execution_state import StepStatus, TaskStatus
    
    # 创建会话
    session = TaskSession.create(user_goal="扩展认证模块")
    
    assert session.task_id.startswith("task_")
    assert session.user_goal == "扩展认证模块"
    assert session.status == TaskStatus.PENDING
    
    print(f"创建会话: {session.task_id}")
    
    # 设置知识和上下文
    session.set_rag_knowledge({"items": ["知识1", "知识2"]})
    session.set_conversation_context({"preference": "使用 JWT"})
    
    # 设置计划
    plan = {
        "plan_id": "test_plan",
        "goal": "扩展认证模块",
        "steps": [
            {"step_id": 0, "type": "analysis", "action": "read_file", "target": "auth.py", "description": "分析 auth.py"},
            {"step_id": 1, "type": "code_change", "action": "create_file", "target": "jwt_handler.py", "description": "创建 jwt_handler.py"},
            {"step_id": 2, "type": "verify", "action": "run_tests", "target": "tests/", "description": "运行测试"}
        ]
    }
    session.set_plan(plan)
    
    assert session.execution_state.total_steps == 3
    assert session.status == TaskStatus.EXECUTING
    
    # 测试获取上下文
    planner_ctx = session.get_context_for_agent("planner")
    assert "user_goal" in planner_ctx
    assert "rag_knowledge" in planner_ctx
    print(f"Planner 上下文键: {list(planner_ctx.keys())}")
    
    coder_ctx = session.get_context_for_agent("coder")
    assert "step" in coder_ctx
    print(f"Coder 上下文键: {list(coder_ctx.keys())}")
    
    # 测试状态更新
    session.update_state("orchestrator", "start_step")
    session.update_state("coder", "complete_step", {"summary": "分析完成"})
    
    assert session.execution_state.current_step_status == StepStatus.COMPLETED
    assert 0 in session.step_results
    
    # 前进到下一步
    session.advance_to_next_step()
    assert session.execution_state.current_step_id == 1
    
    # 测试摘要
    summary = session.get_summary()
    print(f"任务摘要: {summary}")
    assert summary["progress"] > 0
    
    print("[PASS] TaskSession 测试通过")
    return True


def test_knowledge_agent_import():
    """测试 KnowledgeAgent 导入"""
    print("\n=== 测试 KnowledgeAgent 导入 ===")
    
    from llm.agent.cognitive.knowledge_agent import KnowledgeAgent, create_knowledge_agent
    
    # 创建 agent（不加载 RAG）
    agent = KnowledgeAgent(rag_system=None)
    
    # 测试缓存功能
    agent.cache["test_query"] = {"success": True, "results": []}
    stats = agent.get_cache_stats()
    assert stats["cache_size"] == 1
    
    agent.clear_cache()
    assert agent.get_cache_stats()["cache_size"] == 0
    
    print("[PASS] KnowledgeAgent 导入测试通过")
    return True


def test_orchestrator_import():
    """测试 Orchestrator 导入"""
    print("\n=== 测试 Orchestrator 导入 ===")
    
    from llm.agent.agents.orchestrator import Orchestrator, create_orchestrator
    from llm.agent.agents.planner_agent import PlannerAgent
    from llm.agent.agents.coder_agent import CoderAgent
    from llm.agent.agents.reviewer_agent import ReviewerAgent
    
    # 创建 orchestrator
    orchestrator = Orchestrator(
        planner=PlannerAgent(),
        coder=CoderAgent(),
        reviewer=ReviewerAgent(),
        verbose=False
    )
    
    assert orchestrator.planner is not None
    assert orchestrator.coder is not None
    assert orchestrator.reviewer is not None
    
    print("[PASS] Orchestrator 导入测试通过")
    return True


def test_all_imports():
    """测试所有模块导入"""
    print("\n=== 测试所有模块导入 ===")
    
    # 测试 core 导入
    from llm.agent.core import (
        TaskSession, ExecutionState, EventLog, StepStatus, TaskStatus,
        ReActEngine, AgentConfig
    )
    
    # 测试 cognitive 导入
    from llm.agent.cognitive import (
        KnowledgeAgent, create_knowledge_agent,
        ConversationMemory, AgentMemory
    )
    
    # 测试 agents 导入
    from llm.agent.agents import (
        Orchestrator, create_orchestrator,
        PlannerAgent, CoderAgent, ReviewerAgent
    )
    
    print("[PASS] 所有模块导入成功")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Phase 4 阶段1 - 测试")
    print("=" * 60)
    
    tests = [
        ("StepStatus", test_step_status),
        ("ExecutionState", test_execution_state),
        ("EventLog", test_event_log),
        ("TaskSession", test_task_session),
        ("KnowledgeAgent Import", test_knowledge_agent_import),
        ("Orchestrator Import", test_orchestrator_import),
        ("All Imports", test_all_imports),
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
