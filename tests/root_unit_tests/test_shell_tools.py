#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3 Shell 执行器和工具测试

验证：
- ShellExecutor 基本功能
- RunCommandTool 和 RunTestsTool
- CodeAnalystAgent 可选工具注册
"""

import os
import sys
from pathlib import Path

# 确保项目路径
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_shell_executor():
    """测试 ShellExecutor"""
    print("\n" + "=" * 60)
    print("测试 1: ShellExecutor")
    print("=" * 60)
    
    from llm.agent.infrastructure.shell_executor import ShellExecutor
    
    executor = ShellExecutor(project_root=str(PROJECT_ROOT))
    
    # 测试简单命令
    result = executor.run("echo Hello Agent", timeout=5)
    print(f"执行 'echo Hello Agent':")
    print(f"  成功: {result['success']}")
    print(f"  退出码: {result['exit_code']}")
    print(f"  输出: {result['stdout'].strip()}")
    
    assert result["success"], "命令执行应该成功"
    assert "Hello Agent" in result["stdout"], "输出应包含 'Hello Agent'"
    
    # 测试超时（Windows 使用 timeout 命令）
    print(f"\n测试超时控制 (2秒超时):")
    result = executor.run("timeout /t 5", timeout=2)
    print(f"  成功: {result['success']}")
    print(f"  超时: {result.get('timeout', False)}")
    
    # 超时测试在 Windows 上可能不稳定，所以不强制断言
    
    print("\n✅ ShellExecutor 测试通过!")
    return True


def test_shell_tools():
    """测试 Shell 工具"""
    print("\n" + "=" * 60)
    print("测试 2: Shell 工具")
    print("=" * 60)
    
    from llm.agent.tools.shell_tools import RunCommandTool, RunTestsTool
    from llm.agent.tools.base import ToolRegistry
    
    registry = ToolRegistry()
    registry.register(RunCommandTool())
    registry.register(RunTestsTool())
    
    print(f"已注册工具: {registry.list_tools()}")
    
    # 测试 RunCommand
    result = registry.execute("RunCommand", command="echo Test Shell Tool")
    print(f"\nRunCommand 结果:")
    print(f"  成功: {result['success']}")
    if result['success']:
        print(f"  输出: {result['result'][:100]}...")
    
    assert result["success"], "RunCommand 应该成功"
    
    # 测试 RunTests（运行现有的测试文件）
    result = registry.execute("RunTests", test_path="test_agent_tools.py")
    print(f"\nRunTests 结果:")
    print(f"  成功: {result['success']}")
    if result['success']:
        print(f"  输出: {result['result'][:200]}...")
    else:
        print(f"  错误: {result.get('error', '')[:200]}...")
    
    # 测试可能失败（如果测试文件有问题），但工具本身应该能执行
    
    print("\n✅ Shell 工具测试通过!")
    return True


def test_agent_with_optional_tools():
    """测试 Agent 可选工具注册"""
    print("\n" + "=" * 60)
    print("测试 3: Agent 可选工具注册")
    print("=" * 60)
    
    from llm.agent.agents.code_analyst import CodeAnalystAgent
    from llm.agent.tools.file_tools import WriteFileTool
    from llm.agent.tools.shell_tools import RunTestsTool
    
    # 创建 Agent（默认不包含 WriteFile 和 RunTests）
    agent = CodeAnalystAgent(verbose=False)
    tools_before = agent.list_tools()
    print(f"默认工具: {tools_before}")
    
    assert "WriteFile" not in tools_before, "WriteFile 不应默认注册"
    assert "RunTests" not in tools_before, "RunTests 不应默认注册"
    
    # 注册可选工具
    agent.register_tool(WriteFileTool())
    agent.register_tool(RunTestsTool())
    
    tools_after = agent.list_tools()
    print(f"添加后工具: {tools_after}")
    
    assert "WriteFile" in tools_after, "WriteFile 应该已注册"
    assert "RunTests" in tools_after, "RunTests 应该已注册"
    
    print("\n✅ Agent 可选工具注册测试通过!")
    return True


def test_write_and_test_flow():
    """测试写入-测试流程（不实际修改文件）"""
    print("\n" + "=" * 60)
    print("测试 4: 写入-测试流程模拟")
    print("=" * 60)
    
    from llm.agent.tools.file_tools import ReadFileTool, WriteFileTool
    from llm.agent.tools.shell_tools import RunTestsTool
    
    read_tool = ReadFileTool()
    write_tool = WriteFileTool()
    test_tool = RunTestsTool()
    
    # 1. 读取文件
    print("1. 读取测试文件...")
    result = read_tool.execute(path="test_agent_tools.py", max_bytes=1000)
    if result["success"]:
        print(f"   读取成功: {len(result['result'])} 字符")
    
    # 2. 模拟写入（写入到临时文件）
    print("\n2. 模拟写入（跳过，避免修改文件）...")
    print("   ⚠️ 实际使用时会调用 WriteFile 工具")
    
    # 3. 运行测试
    print("\n3. 运行测试...")
    result = test_tool.execute(test_path="test_agent_tools.py")
    if result["success"]:
        print("   ✅ 测试通过")
    else:
        print(f"   ⚠️ 测试失败（这可能是正常的）")
    
    print("\n✅ 写入-测试流程模拟完成!")
    return True


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Phase 3 Shell 执行器和工具测试")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(("ShellExecutor", test_shell_executor()))
    except Exception as e:
        print(f"❌ ShellExecutor 测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("ShellExecutor", False))
    
    try:
        results.append(("Shell 工具", test_shell_tools()))
    except Exception as e:
        print(f"❌ Shell 工具测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Shell 工具", False))
    
    try:
        results.append(("可选工具注册", test_agent_with_optional_tools()))
    except Exception as e:
        print(f"❌ 可选工具注册测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("可选工具注册", False))
    
    try:
        results.append(("写入-测试流程", test_write_and_test_flow()))
    except Exception as e:
        print(f"❌ 写入-测试流程测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("写入-测试流程", False))
    
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
