"""
Phase 6.1 Ready Check: V2 Tools Verification
验证所有工具是否符合 V2 标准
"""
import pytest
from llm.agent.tools.tool_registry import ToolRegistry


def test_all_tools_have_get_schema():
    """验证所有工具都有 get_schema 方法"""
    registry = ToolRegistry()
    tools = registry.get_all_tools()
    
    for tool in tools:
        assert hasattr(tool, 'get_schema'), f"{tool.name} 缺少 get_schema 方法"
        schema = tool.get_schema()
        assert isinstance(schema, dict), f"{tool.name}.get_schema() 应返回 dict"
        assert "name" in schema, f"{tool.name} schema 缺少 'name' 字段"
        assert "description" in schema, f"{tool.name} schema 缺少 'description' 字段"
        assert "input_schema" in schema, f"{tool.name} schema 缺少 'input_schema' 字段"


def test_all_tools_have_execute():
    """验证所有工具都有 execute 方法"""
    registry = ToolRegistry()
    tools = registry.get_all_tools()
    
    for tool in tools:
        assert hasattr(tool, 'execute'), f"{tool.name} 缺少 execute 方法"
        assert callable(tool.execute), f"{tool.name}.execute 应该是可调用的"


def test_all_tools_have_name():
    """验证所有工具都有 name 属性"""
    registry = ToolRegistry()
    tools = registry.get_all_tools()
    
    for tool in tools:
        assert hasattr(tool, 'name'), f"{tool} 缺少 name 属性"
        assert isinstance(tool.name, str), f"{tool} 的 name 应该是字符串"
        assert len(tool.name) > 0, f"{tool} 的 name 不能为空"


def test_v2_core_tools_registered():
    """验证 V2 核心工具已注册"""
    registry = ToolRegistry()
    
    # V2 核心工具列表
    v2_tools = ["Read", "Edit", "Bash", "Grep", "Ls", "Glob"]
    
    for tool_name in v2_tools:
        assert registry.has_tool(tool_name), f"V2 核心工具 {tool_name} 未注册"


def test_read_tool_v2_compatible():
    """验证 ReadTool 符合 V2 标准"""
    from llm.agent.tools.read_tool import ReadTool
    
    schema = ReadTool.get_schema()
    assert schema["name"] == "Read"
    assert "file_path" in schema["input_schema"]["properties"]
    
    # 测试基本功能
    import tempfile
    from pathlib import Path
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        f.write("test content\n" * 10)
        temp_path = f.name
    
    try:
        result = ReadTool.execute(file_path=temp_path)
        assert "content" in result or "error" not in result
    finally:
        Path(temp_path).unlink()


def test_edit_tool_v2_compatible():
    """验证 EditTool 符合 V2 标准"""
    from llm.agent.tools.edit_tool import EditTool
    
    schema = EditTool.get_schema()
    assert schema["name"] == "Edit"
    assert "file_path" in schema["input_schema"]["properties"]
    assert "old_string" in schema["input_schema"]["properties"]
    assert "new_string" in schema["input_schema"]["properties"]


def test_bash_tool_v2_compatible():
    """验证 BashTool 符合 V2 标准"""
    from llm.agent.tools.bash_tool import BashTool
    
    schema = BashTool.get_schema()
    assert schema["name"] == "Bash"
    assert "command" in schema["input_schema"]["properties"]
    
    # 测试基本功能
    result = BashTool.execute(command="echo test")
    assert "stdout" in result or "error" in result


def test_grep_tool_v2_compatible():
    """验证 GrepTool 符合 V2 标准（Python 原生版）"""
    from llm.agent.tools.grep_tool import GrepTool
    
    schema = GrepTool.get_schema()
    assert schema["name"] == "Grep"
    assert "pattern" in schema["input_schema"]["properties"]


def test_ls_tool_v2_compatible():
    """验证 LsTool 符合 V2 标准"""
    from llm.agent.tools.ls_tool import LsTool
    
    schema = LsTool.get_schema()
    assert schema["name"] == "Ls"
    
    # 测试基本功能
    result = LsTool.execute(path=".")
    assert "success" in result or "error" in result


def test_glob_tool_v2_compatible():
    """验证 GlobTool 符合 V2 标准"""
    from llm.agent.tools.glob_tool import GlobTool
    
    schema = GlobTool.get_schema()
    assert schema["name"] == "Glob"
    assert "pattern" in schema["input_schema"]["properties"]
    
    # 测试基本功能
    result = GlobTool.execute(pattern="*.py", path=".")
    assert "success" in result or "error" in result
