#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 4 阶段3 测试文件

测试 MemoryAgent 与 TaskSession 集成
"""

import sys
import io

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, r"D:\代码仓库生图\create_graph")


def test_memory_agent_import():
    """测试 MemoryAgent 导入"""
    print("\n=== 测试 MemoryAgent 导入 ===")
    
    from llm.agent.cognitive.memory_agent import MemoryAgent, create_memory_agent
    
    agent = MemoryAgent()
    assert agent is not None
    assert agent.conversation_memory is not None
    assert agent.agent_memory is not None
    
    print("[PASS] MemoryAgent 导入测试通过")
    return True


def test_memory_agent_context():
    """测试 MemoryAgent 上下文获取"""
    print("\n=== 测试 MemoryAgent 上下文 ===")
    
    from llm.agent.cognitive.memory_agent import MemoryAgent
    
    agent = MemoryAgent()
    
    # 添加一些对话
    agent.add_conversation("帮我分析 auth.py", "好的，我来分析 auth.py 文件...")
    agent.add_conversation("再看看 user.py", "接下来分析 user.py...")
    
    # 获取上下文
    context = agent.get_conversation_context("auth.py")
    print(f"上下文类型: {type(context)}")
    print(f"上下文键: {list(context.keys())}")
    
    assert "context" in context
    assert "preferences" in context
    assert "recent_files" in context
    
    print("[PASS] MemoryAgent 上下文测试通过")
    return True


def test_memory_agent_preferences():
    """测试 MemoryAgent 偏好"""
    print("\n=== 测试 MemoryAgent 偏好 ===")
    
    from llm.agent.cognitive.memory_agent import MemoryAgent
    
    agent = MemoryAgent()
    
    # 设置偏好
    agent.update_preference("output_dir", "dist/")
    agent.update_preference("use_typescript", True)
    
    # 获取偏好
    assert agent.get_preference("output_dir") == "dist/"
    assert agent.get_preference("use_typescript") == True
    assert agent.get_preference("unknown", "default") == "default"
    
    print("[PASS] MemoryAgent 偏好测试通过")
    return True


def test_memory_agent_files():
    """测试 MemoryAgent 文件记录"""
    print("\n=== 测试 MemoryAgent 文件记录 ===")
    
    from llm.agent.cognitive.memory_agent import MemoryAgent
    
    agent = MemoryAgent()
    
    # 记录文件
    agent.add_recent_file("auth.py")
    agent.add_recent_file("user.py")
    agent.add_recent_file("config.py")
    
    # 获取当前文件
    current = agent.get_current_file()
    assert current == "config.py"
    
    # 获取上下文
    ctx = agent.get_conversation_context()
    assert len(ctx["recent_files"]) >= 3
    
    print("[PASS] MemoryAgent 文件记录测试通过")
    return True


def test_memory_agent_stats():
    """测试 MemoryAgent 统计"""
    print("\n=== 测试 MemoryAgent 统计 ===")
    
    from llm.agent.cognitive.memory_agent import MemoryAgent
    
    agent = MemoryAgent()
    
    # 添加一些操作
    agent.record_action("ReadFile", {"path": "test.py"}, {"success": True})
    agent.record_action("WriteFile", {"path": "out.py"}, {"success": True})
    
    stats = agent.get_stats()
    print(f"统计信息: {stats}")
    
    assert "conversation" in stats
    assert "agent" in stats
    assert stats["agent"]["action_count"] == 2
    
    print("[PASS] MemoryAgent 统计测试通过")
    return True


def test_memory_agent_with_task_session():
    """测试 MemoryAgent 与 TaskSession 集成"""
    print("\n=== 测试 MemoryAgent 与 TaskSession 集成 ===")
    
    from llm.agent.core.task_session import TaskSession
    from llm.agent.cognitive.memory_agent import MemoryAgent
    
    # 创建 MemoryAgent
    memory_agent = MemoryAgent()
    memory_agent.add_conversation("帮我添加日志功能", "好的，我来帮你添加日志功能...")
    memory_agent.update_preference("log_level", "DEBUG")
    
    # 创建 TaskSession
    session = TaskSession.create(user_goal="添加日志功能")
    
    # 获取对话上下文并设置到 session
    context = memory_agent.get_conversation_context("日志功能")
    session.set_conversation_context(context)
    
    # 验证上下文已设置
    assert session.conversation_context is not None
    assert "preferences" in session.conversation_context
    
    # 获取 Planner 上下文
    planner_ctx = session.get_context_for_agent("planner")
    assert "conversation_context" in planner_ctx
    
    print("[PASS] MemoryAgent 与 TaskSession 集成测试通过")
    return True


def test_orchestrator_with_memory():
    """测试 Orchestrator 与 MemoryAgent 集成"""
    print("\n=== 测试 Orchestrator 与 MemoryAgent 集成 ===")
    
    from llm.agent.agents.orchestrator import Orchestrator
    from llm.agent.cognitive.memory_agent import MemoryAgent
    from llm.agent.agents.planner_agent import PlannerAgent
    
    # 创建带有 MemoryAgent 的 Orchestrator
    memory_agent = MemoryAgent()
    orchestrator = Orchestrator(
        memory_agent=memory_agent,
        planner=PlannerAgent(verbose=False),
        verbose=False
    )
    
    assert orchestrator.memory_agent is not None
    
    print("[PASS] Orchestrator 与 MemoryAgent 集成测试通过")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Phase 4 阶段3 - 测试")
    print("=" * 60)
    
    tests = [
        ("MemoryAgent Import", test_memory_agent_import),
        ("MemoryAgent Context", test_memory_agent_context),
        ("MemoryAgent Preferences", test_memory_agent_preferences),
        ("MemoryAgent Files", test_memory_agent_files),
        ("MemoryAgent Stats", test_memory_agent_stats),
        ("MemoryAgent with TaskSession", test_memory_agent_with_task_session),
        ("Orchestrator with Memory", test_orchestrator_with_memory),
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
