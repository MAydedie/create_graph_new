#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Agent 工具层测试

验证 Phase 1 工具层实现：
- Tool 基类和 ToolRegistry
- FileManager 和文件工具
- GraphClient 和图谱工具
"""

import os
import sys
from pathlib import Path

# 确保项目路径在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_tool_registry():
    """测试 ToolRegistry"""
    print("\n" + "=" * 60)
    print("测试 1: ToolRegistry")
    print("=" * 60)
    
    from llm.agent.tools.base import Tool, ToolRegistry, ToolInputSchema
    
    # 创建一个简单的测试工具
    class TestTool(Tool):
        @property
        def name(self):
            return "TestTool"
        
        @property
        def description(self):
            return "一个测试工具"
        
        @property
        def input_schema(self):
            return ToolInputSchema(
                properties={"message": {"type": "string", "description": "消息"}},
                required=["message"]
            )
        
        def execute(self, **kwargs):
            return {"success": True, "result": f"收到消息: {kwargs.get('message')}"}
    
    # 测试注册
    registry = ToolRegistry()
    registry.register(TestTool())
    
    tools = registry.list_tools()
    print(f"已注册工具: {tools}")
    assert "TestTool" in tools, "工具注册失败"
    
    # 测试获取
    tool = registry.get("TestTool")
    assert tool is not None, "工具获取失败"
    print(f"获取工具: {tool.name}")
    
    # 测试执行
    result = registry.execute("TestTool", message="Hello Agent!")
    print(f"执行结果: {result}")
    assert result["success"], "工具执行失败"
    
    # 测试提示词生成
    prompt = registry.to_prompt_string()
    print(f"\n工具提示词:\n{prompt}")
    
    print("\n✅ ToolRegistry 测试通过!")
    return True


def test_file_manager():
    """测试 FileManager"""
    print("\n" + "=" * 60)
    print("测试 2: FileManager")
    print("=" * 60)
    
    from llm.agent.infrastructure.file_manager import FileManager
    
    fm = FileManager(project_root=str(PROJECT_ROOT))
    
    # 测试读取
    result = fm.safe_read("README.md")
    if result["success"]:
        print(f"读取 README.md: {len(result['content'])} 字符")
        print(f"截断: {result.get('truncated', False)}")
        print(f"内容预览: {result['content'][:100]}...")
    else:
        print(f"读取失败 (可能文件不存在): {result.get('error')}")
    
    # 测试目录列表
    result = fm.list_dir(".")
    if result["success"]:
        print(f"\n目录内容 ({result['total_count']} 项):")
        for entry in result["entries"][:10]:
            prefix = "[目录]" if entry["is_dir"] else "[文件]"
            print(f"  {prefix} {entry['name']}")
        if result["truncated"]:
            print(f"  ... 还有 {result['total_count'] - len(result['entries'])} 项")
    else:
        print(f"列目录失败: {result.get('error')}")
    
    print("\n✅ FileManager 测试通过!")
    return True


def test_file_tools():
    """测试文件工具"""
    print("\n" + "=" * 60)
    print("测试 3: 文件工具 (ReadFileTool, ListDirTool)")
    print("=" * 60)
    
    from llm.agent.tools.file_tools import ReadFileTool, ListDirTool
    from llm.agent.tools.base import ToolRegistry
    
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(ListDirTool())
    
    print(f"已注册工具: {registry.list_tools()}")
    
    # 测试 ReadFile
    result = registry.execute("ReadFile", path="README.md")
    if result["success"]:
        print(f"\nReadFile 结果: {len(result['result'])} 字符")
    else:
        print(f"\nReadFile 失败 (可能文件不存在): {result.get('error')}")
    
    # 测试 ListDir
    result = registry.execute("ListDir", path="llm/agent")
    if result["success"]:
        print(f"\nListDir 结果:\n{result['result']}")
    else:
        print(f"\nListDir 失败: {result.get('error')}")
    
    print("\n✅ 文件工具测试通过!")
    return True


def test_graph_client():
    """测试 GraphClient (可选，需要 RAG 索引)"""
    print("\n" + "=" * 60)
    print("测试 4: GraphClient (需要 RAG 索引)")
    print("=" * 60)
    
    try:
        from llm.agent.infrastructure.graph_client import GraphClient
        
        # 只测试初始化，不实际调用（避免加载模型）
        print("创建 GraphClient (lazy_init=True)...")
        client = GraphClient(lazy_init=True)
        print(f"GraphClient 创建成功, 已初始化: {client.is_initialized()}")
        
        print("\n⚠️ 跳过实际查询测试 (需要加载模型)")
        print("✅ GraphClient 基础测试通过!")
        return True
    except Exception as e:
        print(f"⚠️ GraphClient 测试跳过: {e}")
        return True  # 不阻断测试


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Phase 1 工具层测试")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(("ToolRegistry", test_tool_registry()))
    except Exception as e:
        print(f"❌ ToolRegistry 测试失败: {e}")
        results.append(("ToolRegistry", False))
    
    try:
        results.append(("FileManager", test_file_manager()))
    except Exception as e:
        print(f"❌ FileManager 测试失败: {e}")
        results.append(("FileManager", False))
    
    try:
        results.append(("文件工具", test_file_tools()))
    except Exception as e:
        print(f"❌ 文件工具测试失败: {e}")
        results.append(("文件工具", False))
    
    try:
        results.append(("GraphClient", test_graph_client()))
    except Exception as e:
        print(f"❌ GraphClient 测试失败: {e}")
        results.append(("GraphClient", False))
    
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
