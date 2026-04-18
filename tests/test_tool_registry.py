import pytest
from llm.agent.tools.tool_registry import ToolRegistry

def test_registry_schemas():
    schemas = ToolRegistry.get_tool_schemas()
    assert len(schemas) == 5
    names = [s["name"] for s in schemas]
    assert "Read" in names
    assert "Edit" in names
    assert "Write" in names
    assert "Bash" in names
    assert "Grep" in names

def test_registry_execute_read(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("hello", encoding="utf-8")
    
    result = ToolRegistry.execute_tool("Read", file_path=str(p))
    assert result.get("content").strip() == "1\thello"

def test_registry_unknown_tool():
    result = ToolRegistry.execute_tool("Unknown")
    assert "error" in result
