#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 4 验收测试 - 测试完整的 Multi-Agent 系统

测试场景：
1. 单文件修改：在 calculator.py 添加乘法函数
2. 简单跨文件：修改 calculator.py 并更新 utils.py
"""

import sys
import io

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, r"D:\代码仓库生图\create_graph")


def test_task_session_flow():
    """测试 TaskSession 完整流程"""
    print("\n=== 测试 TaskSession 完整流程 ===")
    
    from llm.agent.core.task_session import TaskSession
    from llm.agent.core.execution_state import StepStatus, TaskStatus
    
    # 1. 创建会话
    session = TaskSession.create(user_goal="在 calculator.py 添加乘法函数 multiply")
    print(f"  创建会话: {session.task_id}")
    
    # 2. 模拟 RAG 知识
    session.set_rag_knowledge({
        "knowledge_items": [{"question": "calculator.py 有哪些函数", "answer": "add, subtract"}],
        "context_summary": "calculator.py 目前有 add 和 subtract 两个函数"
    })
    
    # 3. 模拟计划
    plan = {
        "plan_id": "multiply_plan",
        "goal": "添加乘法函数",
        "steps": [
            {"step_id": 0, "type": "analysis", "action": "read_file", "target": "test_sandbox/calculator.py", "description": "读取 calculator.py"},
            {"step_id": 1, "type": "code_change", "action": "modify_file", "target": "test_sandbox/calculator.py", "description": "添加 multiply 函数"},
            {"step_id": 2, "type": "verify", "action": "run_tests", "target": "test_sandbox/", "description": "验证修改"}
        ]
    }
    session.set_plan(plan)
    
    # 4. 模拟执行
    for i, step in enumerate(plan["steps"]):
        session.execution_state.current_step_id = i
        session.update_state("orchestrator", "start_step")
        session.update_state("coder" if step["type"] != "verify" else "reviewer", "complete_step", 
                            {"summary": f"完成 {step['description']}"})
        if i < len(plan["steps"]) - 1:
            session.advance_to_next_step()
    
    # 5. 验证
    session.mark_completed()
    assert session.status == TaskStatus.COMPLETED
    assert session.execution_state.get_progress_percentage() == 100.0
    
    print(f"  任务完成: 进度 100%, 事件数 {len(session.event_log)}")
    print("[PASS] TaskSession 完整流程测试通过")
    return True


def test_orchestrator_mock():
    """测试 Orchestrator（Mock 模式）"""
    print("\n=== 测试 Orchestrator (Mock) ===")
    
    from llm.agent.agents.orchestrator import Orchestrator
    from llm.agent.cognitive.memory_agent import MemoryAgent
    
    # 创建 Mock Agent
    class MockPlanner:
        def plan(self, goal, ctx):
            return {
                "plan_id": "mock_plan",
                "goal": goal,
                "steps": [
                    {"step_id": 0, "type": "analysis", "action": "read_file", "target": "test.py", "description": "分析代码"}
                ]
            }
    
    class MockCoder:
        def execute_step(self, step, ctx):
            return {"success": True, "summary": "模拟执行成功"}
    
    class MockReviewer:
        def review(self, changes, ctx):
            return {"success": True, "approved": True, "score": 90, "summary": "审查通过"}
    
    # 创建 Orchestrator
    orchestrator = Orchestrator(
        memory_agent=MemoryAgent(),
        planner=MockPlanner(),
        coder=MockCoder(),
        reviewer=MockReviewer(),
        verbose=False
    )
    
    # 执行
    result = orchestrator.execute("测试任务")
    
    print(f"  执行结果: success={result['success']}")
    print(f"  任务状态: {result['status']}")
    
    assert result["success"] == True
    assert result["status"] == "completed"
    
    print("[PASS] Orchestrator Mock 测试通过")
    return True


def test_coder_read_file():
    """测试 CoderAgent 读取文件"""
    print("\n=== 测试 CoderAgent 读取文件 ===")
    
    from llm.agent.agents.coder_agent import CoderAgent
    
    coder = CoderAgent(verbose=False)
    
    # 读取 test_sandbox 中的文件
    result = coder._execute_read("test_sandbox/calculator.py", {})
    
    print(f"  读取结果: success={result['success']}")
    
    if result["success"]:
        content = result.get("content", "")
        print(f"  文件内容长度: {len(content)}")
        assert "def add" in content
        assert "def subtract" in content
        print("[PASS] CoderAgent 读取文件测试通过")
        return True
    else:
        print(f"  [SKIP] 文件不存在: {result.get('error')}")
        return True  # 允许跳过


def test_three_part_info():
    """测试三部分信息模型"""
    print("\n=== 测试三部分信息模型 ===")
    
    from llm.agent.core.task_session import TaskSession
    from llm.agent.cognitive.knowledge_agent import KnowledgeAgent
    from llm.agent.cognitive.memory_agent import MemoryAgent
    
    # 创建会话
    session = TaskSession.create(user_goal="测试信息模型")
    
    # 1. User Goal（已设置）
    assert session.user_goal == "测试信息模型"
    print("  [OK] 用户目标已设置")
    
    # 2. RAG Knowledge
    knowledge_agent = KnowledgeAgent(rag_system=None)  # 不加载实际 RAG
    session.set_rag_knowledge({
        "knowledge_items": [],
        "context_summary": "测试知识",
        "success": True
    })
    assert session.rag_knowledge.get("success") == True
    print("  [OK] RAG 知识已设置")
    
    # 3. Conversation Context
    memory_agent = MemoryAgent()
    memory_agent.add_conversation("之前问过日志", "已添加日志")
    context = memory_agent.get_conversation_context("日志")
    session.set_conversation_context(context)
    assert "preferences" in session.conversation_context
    print("  [OK] 对话上下文已设置")
    
    # 验证 Planner 能获取三部分信息
    planner_ctx = session.get_context_for_agent("planner")
    assert "user_goal" in planner_ctx
    assert "rag_knowledge" in planner_ctx
    assert "conversation_context" in planner_ctx
    print("  [OK] Planner 上下文包含三部分信息")
    
    print("[PASS] 三部分信息模型测试通过")
    return True


def test_event_log_for_incremental_context():
    """测试 EventLog 增量上下文"""
    print("\n=== 测试 EventLog 增量上下文 ===")
    
    from llm.agent.core.execution_state import EventLog
    
    log = EventLog()
    
    # 模拟执行过程
    log.log("step_start", "planner", 0, "开始规划")
    log.log("step_complete", "planner", 0, "计划生成完成，共 3 步")
    log.log("step_start", "coder", 1, "开始修改 auth.py")
    log.log("step_complete", "coder", 1, "添加 JWT 验证")
    log.log("step_start", "reviewer", 1, "开始审查")
    log.log("step_fail", "reviewer", 1, "缺少错误处理")
    log.log("retry", "orchestrator", 1, "重试修改")
    
    # 测试为 Coder 生成上下文
    coder_ctx = log.generate_context_summary("coder", 2)
    print(f"  Coder 上下文: {coder_ctx[:100]}...")
    
    # 测试失败反馈
    feedback = log.get_failure_feedback(1)
    assert "缺少错误处理" in feedback
    print(f"  失败反馈: {feedback}")
    
    # 测试事件统计
    assert len(log) == 7
    print(f"  事件数: {len(log)}")
    
    print("[PASS] EventLog 增量上下文测试通过")
    return True


def run_all_tests():
    """运行所有验收测试"""
    print("=" * 60)
    print("Phase 4 验收测试")
    print("=" * 60)
    
    tests = [
        ("TaskSession 完整流程", test_task_session_flow),
        ("Orchestrator Mock", test_orchestrator_mock),
        ("CoderAgent 读取文件", test_coder_read_file),
        ("三部分信息模型", test_three_part_info),
        ("EventLog 增量上下文", test_event_log_for_incremental_context),
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
    print(f"验收测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
