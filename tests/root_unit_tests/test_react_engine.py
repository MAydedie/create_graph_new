#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 2 ReAct 引擎测试

验证 CodeAnalystAgent 的核心功能：
- Agent 初始化和工具注册
- 简单问答（仅使用文件工具）
- ReAct 循环（多步推理）
"""

import os
import sys
from pathlib import Path

# 确保项目路径
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_agent_initialization():
    """测试 Agent 初始化"""
    print("\n" + "=" * 60)
    print("测试 1: Agent 初始化")
    print("=" * 60)
    
    from llm.agent.agents.code_analyst import CodeAnalystAgent
    
    agent = CodeAnalystAgent(verbose=False)
    tools = agent.list_tools()
    
    print(f"已注册工具: {tools}")
    
    # 验证必要工具已注册
    assert "ReadFile" in tools, "ReadFile 工具未注册"
    assert "ListDir" in tools, "ListDir 工具未注册"
    
    print("✅ Agent 初始化测试通过!")
    return True


def test_prompt_building():
    """测试 Prompt 构建"""
    print("\n" + "=" * 60)
    print("测试 2: Prompt 构建")
    print("=" * 60)
    
    from llm.agent.core.prompt import build_system_prompt, build_few_shot_messages
    
    # 模拟工具信息
    tools = [
        {
            "name": "TestTool",
            "description": "一个测试工具",
            "parameters": {
                "properties": {"query": {"type": "string", "description": "查询"}},
                "required": ["query"]
            }
        }
    ]
    
    system_prompt = build_system_prompt(tools)
    print(f"System Prompt 长度: {len(system_prompt)} 字符")
    print(f"预览: {system_prompt[:200]}...")
    
    assert "ReAct" in system_prompt, "System Prompt 应包含 ReAct"
    assert "TestTool" in system_prompt, "System Prompt 应包含工具名"
    
    few_shot = build_few_shot_messages()
    print(f"\nFew-shot 消息数: {len(few_shot)}")
    
    assert len(few_shot) > 0, "应有 Few-shot 示例"
    
    print("✅ Prompt 构建测试通过!")
    return True


def test_response_parsing():
    """测试响应解析"""
    print("\n" + "=" * 60)
    print("测试 3: 响应解析")
    print("=" * 60)
    
    from llm.agent.core.engine import ReActEngine, AgentConfig
    from llm.agent.tools.base import ToolRegistry
    
    engine = ReActEngine(
        config=AgentConfig(verbose=False),
        tool_registry=ToolRegistry()
    )
    
    # 测试解析带 action 的响应
    response1 = """<thinking>
我需要读取文件来了解内容。
</thinking>

<action>
{"tool": "ReadFile", "args": {"path": "test.py"}}
</action>"""
    
    thinking, action, final = engine._parse_response(response1)
    print(f"解析结果 1:")
    print(f"  Thinking: {thinking[:50]}...")
    print(f"  Action: {action}")
    print(f"  Final: {final}")
    
    assert "读取文件" in thinking, "Thinking 解析错误"
    assert action is not None, "Action 解析失败"
    assert action.get("tool") == "ReadFile", "Tool 名称错误"
    
    # 测试解析带 final_answer 的响应
    response2 = """<thinking>
信息已足够，我来总结答案。
</thinking>

<final_answer>
这是最终答案。
</final_answer>"""
    
    thinking, action, final = engine._parse_response(response2)
    print(f"\n解析结果 2:")
    print(f"  Thinking: {thinking[:50]}...")
    print(f"  Action: {action}")
    print(f"  Final: {final[:30]}...")
    
    assert final == "这是最终答案。", "Final answer 解析错误"
    assert action is None, "不应有 action"
    
    print("✅ 响应解析测试通过!")
    return True


def test_simple_file_query():
    """测试简单文件查询（不涉及 LLM）"""
    print("\n" + "=" * 60)
    print("测试 4: 工具直接执行")
    print("=" * 60)
    
    from llm.agent.agents.code_analyst import CodeAnalystAgent
    
    agent = CodeAnalystAgent(verbose=False)
    
    # 直接调用工具（不通过 LLM）
    result = agent.tool_registry.execute("ListDir", path="llm/agent")
    
    print(f"ListDir 结果: success={result.get('success')}")
    if result.get("success"):
        print(f"  {result.get('result', '')[:200]}...")
    
    assert result.get("success"), f"ListDir 失败: {result.get('error')}"
    
    result = agent.tool_registry.execute("ReadFile", path="README.md", max_bytes=500)
    print(f"\nReadFile 结果: success={result.get('success')}")
    if result.get("success"):
        print(f"  预览: {result.get('result', '')[:100]}...")
    
    print("✅ 工具直接执行测试通过!")
    return True


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Phase 2 ReAct 引擎测试")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(("Agent 初始化", test_agent_initialization()))
    except Exception as e:
        print(f"❌ Agent 初始化测试失败: {e}")
        results.append(("Agent 初始化", False))
    
    try:
        results.append(("Prompt 构建", test_prompt_building()))
    except Exception as e:
        print(f"❌ Prompt 构建测试失败: {e}")
        results.append(("Prompt 构建", False))
    
    try:
        results.append(("响应解析", test_response_parsing()))
    except Exception as e:
        print(f"❌ 响应解析测试失败: {e}")
        results.append(("响应解析", False))
    
    try:
        results.append(("工具执行", test_simple_file_query()))
    except Exception as e:
        print(f"❌ 工具执行测试失败: {e}")
        results.append(("工具执行", False))
    
    # 汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {name}: {status}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
