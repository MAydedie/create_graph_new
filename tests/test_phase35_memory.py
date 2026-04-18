#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3.5 测试文件

测试语义化上下文记忆系统的核心功能：
1. ContextUnit 创建和序列化
2. ContextCompressor 主题提取和摘要生成
3. SemanticRetriever 关键词检索
4. ConversationMemory 多轮对话记忆
"""

import sys
import io

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, r"D:\代码仓库生图\create_graph")

from datetime import datetime


def test_context_unit():
    """测试 ContextUnit"""
    print("\n=== 测试 ContextUnit ===")
    
    from llm.agent.cognitive.context_unit import ContextUnit
    
    # 创建单元
    messages = [
        {"role": "user", "content": "把文件保存到 output/ 目录"},
        {"role": "assistant", "content": "好的，我会将文件保存到 output/ 目录。"}
    ]
    
    unit = ContextUnit.create(
        topic="文件保存路径",
        summary="用户指定将文件保存到 output/ 目录",
        messages=messages,
        keywords=["文件", "保存", "output", "目录"]
    )
    
    print(f"单元ID: {unit.unit_id}")
    print(f"主题: {unit.topic}")
    print(f"摘要: {unit.summary}")
    print(f"上下文字符串: {unit.to_context_string()}")
    print(f"Token 估算: {unit.get_token_estimate()}")
    
    # 测试序列化
    data = unit.to_dict()
    restored = ContextUnit.from_dict(data)
    assert restored.topic == unit.topic
    assert restored.summary == unit.summary
    print("[PASS] 序列化/反序列化通过")
    
    return True


def test_context_compressor():
    """测试 ContextCompressor"""
    print("\n=== 测试 ContextCompressor ===")
    
    from llm.agent.cognitive.context_compressor import ContextCompressor
    
    compressor = ContextCompressor(llm_api=None)  # 不使用 LLM，用简化方法
    
    # 添加消息
    messages = [
        {"role": "user", "content": "我想分析一下 GraphRAGSystem 的代码结构"},
        {"role": "assistant", "content": "好的，让我来分析 GraphRAGSystem 的代码结构..."},
        {"role": "user", "content": "那它的 query 方法是怎么工作的？"},
        {"role": "assistant", "content": "query 方法的工作流程如下..."},
    ]
    
    for msg in messages:
        unit = compressor.add_message(msg)
        if unit:
            print(f"创建了新单元: {unit.topic}")
    
    # 强制刷新
    final_unit = compressor.flush_current_unit()
    if final_unit:
        print(f"最终单元: {final_unit.topic}")
        print(f"摘要: {final_unit.summary}")
        print(f"关键词: {final_unit.keywords[:5]}")
    
    print("[PASS] ContextCompressor 测试通过")
    return True


def test_semantic_retriever():
    """测试 SemanticRetriever"""
    print("\n=== 测试 SemanticRetriever ===")
    
    from llm.agent.cognitive.context_unit import ContextUnit
    from llm.agent.cognitive.semantic_retriever import SemanticRetriever
    
    retriever = SemanticRetriever()
    
    # 创建测试单元
    units = [
        ContextUnit.create(
            topic="文件保存设置",
            summary="用户指定将文件保存到 output/ 目录",
            messages=[],
            keywords=["文件", "保存", "output", "目录"]
        ),
        ContextUnit.create(
            topic="代码分析需求",
            summary="用户想分析 GraphRAGSystem 的代码结构",
            messages=[],
            keywords=["代码", "分析", "GraphRAGSystem", "结构"]
        ),
        ContextUnit.create(
            topic="测试运行",
            summary="用户运行了 pytest 测试，结果全部通过",
            messages=[],
            keywords=["测试", "pytest", "运行", "通过"]
        ),
    ]
    
    # 测试检索
    query = "再保存一个备份文件"
    results = retriever.retrieve_relevant_units(query, units, top_k=2)
    
    print(f"查询: '{query}'")
    print(f"检索到 {len(results)} 个相关单元:")
    for unit in results:
        print(f"  - {unit.to_context_string()}")
    
    # 验证应该检索到文件保存相关的单元
    assert len(results) > 0
    assert any("文件" in u.topic or "保存" in u.topic for u in results)
    
    print("[PASS] SemanticRetriever 测试通过")
    return True


def test_conversation_memory():
    """测试 ConversationMemory"""
    print("\n=== 测试 ConversationMemory ===")
    
    from llm.agent.cognitive.memory import ConversationMemory
    
    memory = ConversationMemory()
    
    # 添加对话
    memory.add_conversation(
        "把结果文件保存到 data/output 目录",
        "好的，我会将结果保存到 data/output 目录。"
    )
    
    # 更新偏好
    memory.update_preference("target_dir", "data/output")
    memory.add_recent_file("data/output/result.json")
    
    # 添加更多对话
    memory.add_conversation(
        "分析一下 main.py 的代码",
        "main.py 的主要功能是..."
    )
    
    # 测试检索
    context = memory.get_relevant_context("再保存一个备份")
    print("检索到的上下文:")
    print(context)
    
    # 验证偏好被记住
    assert memory.get_preference("target_dir") == "data/output"
    assert memory.get_current_file() == "data/output/result.json"
    
    # 获取统计信息
    stats = memory.get_stats()
    print(f"\n统计信息: {stats}")
    
    print("[PASS] ConversationMemory 测试通过")
    return True


def test_agent_memory():
    """测试 AgentMemory"""
    print("\n=== 测试 AgentMemory ===")
    
    from llm.agent.cognitive.memory import AgentMemory
    
    memory = AgentMemory()
    
    # 设置任务目标
    memory.set_task_goal("分析并修复 bug #123")
    
    # 记录工具调用
    memory.add_action(
        tool_name="ReadFile",
        args={"path": "main.py"},
        result={"success": True, "content": "..."}
    )
    
    memory.add_action(
        tool_name="WriteFile",
        args={"path": "main.py", "content": "..."},
        result={"success": False, "error": "Permission denied"}
    )
    
    # 测试获取结果
    last_result = memory.get_last_result("ReadFile")
    assert last_result["success"] == True
    
    last_error = memory.get_last_error()
    assert "Permission denied" in last_error["error"]
    
    # 测试上下文字符串
    context = memory.to_context_string()
    print("Agent 上下文:")
    print(context)
    
    print("[PASS] AgentMemory 测试通过")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Phase 3.5 语义化上下文记忆系统 - 测试")
    print("=" * 60)
    
    tests = [
        ("ContextUnit", test_context_unit),
        ("ContextCompressor", test_context_compressor),
        ("SemanticRetriever", test_semantic_retriever),
        ("ConversationMemory", test_conversation_memory),
        ("AgentMemory", test_agent_memory),
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
