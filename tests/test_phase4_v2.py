#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 4 V2 测试文件

测试重试机制、错误处理、降级策略、持久化
"""

import sys
import io
import tempfile
import os

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, r"D:\代码仓库生图\create_graph")


def test_error_handler_import():
    """测试 ErrorHandler 导入"""
    print("\n=== 测试 ErrorHandler 导入 ===")
    
    from llm.agent.core.error_handler import (
        ErrorCategory, RecoveryStrategy, ErrorInfo, ErrorHandler,
        create_error_handler
    )
    
    handler = create_error_handler(max_retries=3)
    
    # 测试错误分类
    class TimeoutError(Exception):
        pass
    
    category = handler.classify_error(TimeoutError("connection timed out"))
    assert category == ErrorCategory.TIMEOUT
    print(f"  超时错误分类正确: {category.name}")
    
    category = handler.classify_error(Exception("file not found"))
    assert category == ErrorCategory.UNRECOVERABLE
    print(f"  不可恢复错误分类正确: {category.name}")
    
    category = handler.classify_error(Exception("random error"))
    assert category == ErrorCategory.RECOVERABLE
    print(f"  默认错误分类正确: {category.name}")
    
    print("[PASS] ErrorHandler 导入测试通过")
    return True


def test_retry_manager_import():
    """测试 RetryManager 导入"""
    print("\n=== 测试 RetryManager 导入 ===")
    
    from llm.agent.core.retry_manager import (
        RetryConfig, RetryManager, RetryResult, FallbackLevel,
        create_retry_manager
    )
    
    manager = create_retry_manager(max_retries=3)
    
    assert manager.config.max_retries == 3
    assert manager.config.use_feedback == True
    
    print("[PASS] RetryManager 导入测试通过")
    return True


def test_retry_success():
    """测试重试成功场景"""
    print("\n=== 测试重试成功场景 ===")
    
    from llm.agent.core.retry_manager import create_retry_manager
    
    manager = create_retry_manager(max_retries=3)
    
    # 模拟第二次成功
    attempt_count = [0]
    def action():
        attempt_count[0] += 1
        if attempt_count[0] < 2:
            raise Exception("模拟失败")
        return {"success": True, "data": "ok"}
    
    result = manager.retry_with_feedback(action)
    
    assert result.success == True
    assert result.total_attempts == 2
    assert result.had_retries == True
    print(f"  成功在第 {result.total_attempts} 次尝试")
    
    print("[PASS] 重试成功场景测试通过")
    return True


def test_retry_failure_with_fallback():
    """测试重试失败后降级"""
    print("\n=== 测试重试失败后降级 ===")
    
    from llm.agent.core.retry_manager import create_retry_manager, FallbackLevel
    
    manager = create_retry_manager(max_retries=2)
    
    # 注册降级处理器
    def fallback_partial(error, context):
        return {"partial": True, "message": "降级成功"}
    
    manager.register_fallback(FallbackLevel.PARTIAL, fallback_partial)
    
    # 永远失败
    def always_fail():
        raise Exception("永远失败")
    
    result = manager.retry_with_feedback(always_fail, context={"test": True})
    
    # 由于降级，应该返回成功
    assert result.success == True
    assert result.fallback_result is not None
    assert result.fallback_result["partial"] == True
    print(f"  降级结果: {result.fallback_result}")
    
    print("[PASS] 重试失败后降级测试通过")
    return True


def test_task_session_persistence():
    """测试 TaskSession 持久化"""
    print("\n=== 测试 TaskSession 持久化 ===")
    
    from llm.agent.core.task_session import TaskSession
    from llm.agent.core.execution_state import StepStatus, TaskStatus
    
    # 创建并设置会话
    session = TaskSession.create(user_goal="测试持久化")
    session.set_plan({
        "plan_id": "test_plan",
        "goal": "测试",
        "steps": [
            {"step_id": 0, "type": "analysis", "action": "read", "target": "test.py", "description": "读取"}
        ]
    })
    session.update_state("coder", "complete_step", {"summary": "完成"})
    session.set_rag_knowledge({"key": "value"})
    
    # 保存到临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
    
    try:
        session.save_checkpoint(temp_path)
        print(f"  保存到: {temp_path}")
        
        # 加载
        loaded = TaskSession.load_checkpoint(temp_path)
        
        assert loaded.task_id == session.task_id
        assert loaded.user_goal == session.user_goal
        assert loaded.rag_knowledge["key"] == "value"
        assert loaded.plan is not None
        print(f"  加载成功: {loaded.task_id}")
        
    finally:
        os.unlink(temp_path)
    
    print("[PASS] TaskSession 持久化测试通过")
    return True


def test_orchestrator_v2():
    """测试 Orchestrator V2"""
    print("\n=== 测试 Orchestrator V2 ===")
    
    from llm.agent.agents.orchestrator import Orchestrator
    
    # Mock Agents
    class MockPlanner:
        def plan(self, goal, ctx):
            return {
                "plan_id": "mock",
                "goal": goal,
                "steps": [
                    {"step_id": 0, "type": "analysis", "action": "read", "target": "test.py", "description": "分析"}
                ]
            }
    
    class MockCoder:
        def execute_step(self, step, ctx):
            return {"success": True, "summary": "执行成功"}
    
    class MockReviewer:
        def review(self, changes, ctx):
            return {"success": True, "approved": True}
    
    orchestrator = Orchestrator(
        planner=MockPlanner(),
        coder=MockCoder(),
        reviewer=MockReviewer(),
        verbose=False
    )
    
    # 测试 V2 执行
    result = orchestrator.execute_with_retry("测试任务", max_retries=2)
    
    assert result["success"] == True
    assert "retry_info" in result
    print(f"  V2 执行成功: {result['retry_info']}")
    
    print("[PASS] Orchestrator V2 测试通过")
    return True


def test_error_recovery_strategy():
    """测试错误恢复策略选择"""
    print("\n=== 测试错误恢复策略 ===")
    
    from llm.agent.core.error_handler import ErrorHandler, ErrorCategory, RecoveryStrategy
    
    handler = ErrorHandler(default_max_retries=3)
    
    # 测试不同重试次数的策略
    strategy0 = handler.get_recovery_strategy(ErrorCategory.RECOVERABLE, retry_count=0)
    assert strategy0 == RecoveryStrategy.RETRY
    print(f"  重试0次后策略: {strategy0.name}")
    
    strategy3 = handler.get_recovery_strategy(ErrorCategory.RECOVERABLE, retry_count=3)
    assert strategy3 == RecoveryStrategy.SIMPLIFY
    print(f"  重试3次后策略: {strategy3.name}")
    
    strategy4 = handler.get_recovery_strategy(ErrorCategory.RECOVERABLE, retry_count=4)
    assert strategy4 == RecoveryStrategy.HUMAN_INTERVENTION
    print(f"  重试4次后策略: {strategy4.name}")
    
    # 验证失败使用反馈重试
    strategy_val = handler.get_recovery_strategy(ErrorCategory.VALIDATION_ERROR, retry_count=0)
    assert strategy_val == RecoveryStrategy.RETRY_WITH_FEEDBACK
    print(f"  验证失败策略: {strategy_val.name}")
    
    print("[PASS] 错误恢复策略测试通过")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Phase 4 V2 - 测试")
    print("=" * 60)
    
    tests = [
        ("ErrorHandler Import", test_error_handler_import),
        ("RetryManager Import", test_retry_manager_import),
        ("Retry Success", test_retry_success),
        ("Retry Failure with Fallback", test_retry_failure_with_fallback),
        ("TaskSession Persistence", test_task_session_persistence),
        ("Orchestrator V2", test_orchestrator_v2),
        ("Error Recovery Strategy", test_error_recovery_strategy),
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
    print(f"V2 测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
