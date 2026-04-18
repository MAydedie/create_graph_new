"""
Phase 6.3: V2 Integration Tests
验证 V2 工具和提示词的集成
"""
import pytest


def test_v2_tools_registry_complete():
    """验证所有 V2 工具已在 ToolRegistry 中注册"""
    from llm.agent.tools.tool_registry import ToolRegistry
    
    registry = ToolRegistry()
    v2_tools = ["Read", "Edit", "Write", "Bash", "Grep", "Ls", "Glob", "Task"]
    
    for tool_name in v2_tools:
        assert registry.has_tool(tool_name), f"V2 tool {tool_name} not registered"


def test_v2_prompts_importable():
    """验证所有 V2 提示词可以导入"""
    from llm.agent.prompts_v2 import (
        SYSTEM_PROMPT_V2,
        PLANNER_PROMPT_V2,
        CODER_PROMPT_V2,
        REVIEWER_PROMPT_V2,
        SUBAGENT_PROMPTS,
        TOOL_EXAMPLES
    )
    
    assert SYSTEM_PROMPT_V2 is not None
    assert PLANNER_PROMPT_V2 is not None
    assert CODER_PROMPT_V2 is not None
    assert REVIEWER_PROMPT_V2 is not None
    assert SUBAGENT_PROMPTS is not None
    assert TOOL_EXAMPLES is not None


def test_tool_schemas_for_llm():
    """验证可以获取所有工具的 schema 用于 LLM API"""
    from llm.agent.tools.tool_registry import ToolRegistry
    
    schemas = ToolRegistry.get_tool_schemas()
    
    assert isinstance(schemas, list)
    assert len(schemas) > 0
    
    # 验证每个 schema 的结构
    for schema in schemas:
        assert "name" in schema
        assert "description" in schema
        assert "input_schema" in schema


def test_v2_tools_execution():
    """验证 V2 工具可以正常执行"""
    import tempfile
    from pathlib import Path
    from llm.agent.tools.grep_tool import GrepTool
    from llm.agent.tools.ls_tool import LsTool
    from llm.agent.tools.glob_tool import GlobTool
    
    # 创建临时测试环境
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # 创建测试文件
        (tmp_path / "test.py").write_text("def test(): pass")
        (tmp_path / "main.py").write_text("def main(): pass")
        
        # 测试 Grep
        grep_result = GrepTool.execute(pattern="def", path=str(tmp_path))
        assert grep_result["success"] is True
        assert grep_result["count"] > 0
        
        # 测试 Ls
        ls_result = LsTool.execute(path=str(tmp_path))
        assert ls_result["success"] is True
        assert ls_result["total_count"] == 2
        
        # 测试 Glob
        glob_result = GlobTool.execute(pattern="*.py", path=str(tmp_path))
        assert glob_result["success"] is True
        assert glob_result["count"] == 2


def test_prompts_contain_all_tools():
    """验证提示词中提到了所有 V2 工具"""
    from llm.agent.prompts_v2 import SYSTEM_PROMPT_V2
    from llm.agent.tools.tool_registry import ToolRegistry
    
    registry = ToolRegistry()
    v2_core_tools = ["Read", "Edit", "Bash", "Grep", "Ls", "Glob"]
    
    for tool_name in v2_core_tools:
        assert tool_name in SYSTEM_PROMPT_V2, \
            f"Tool {tool_name} not mentioned in SYSTEM_PROMPT_V2"


def test_subagent_prompts_complete():
    """验证所有 SubAgent 类型都有对应的提示词"""
    from llm.agent.prompts_v2 import SUBAGENT_PROMPTS
    
    required_types = ["research", "search", "diagnostic"]
    
    for agent_type in required_types:
        assert agent_type in SUBAGENT_PROMPTS, \
            f"SubAgent type {agent_type} missing"
        assert len(SUBAGENT_PROMPTS[agent_type]) > 50, \
            f"SubAgent prompt for {agent_type} too short"


def test_v2_integration_with_llm_api():
    """验证 V2 工具 schema 可以传递给 LLM API"""
    from llm.agent.tools.tool_registry import ToolRegistry
    
    # 获取工具 schemas
    schemas = ToolRegistry.get_tool_schemas()
    
    # 验证 schema 格式符合 LLM API 要求
    for schema in schemas:
        # 必须有 name
        assert isinstance(schema["name"], str)
        
        # 必须有 description
        assert isinstance(schema["description"], str)
        
        # 必须有 input_schema
        assert isinstance(schema["input_schema"], dict)
        assert "type" in schema["input_schema"]
        assert "properties" in schema["input_schema"]


def test_v2_backward_compatibility():
    """验证 V2 不会破坏现有功能"""
    from llm.agent.tools.tool_registry import ToolRegistry
    
    # 验证旧的类方法 API 仍然可用
    tool = ToolRegistry.get_tool("Read")
    assert tool is not None
    
    # 验证可以执行工具
    result = ToolRegistry.execute_tool("Bash", command="echo test")
    assert "stdout" in result or "error" in result
    
    # 验证新的实例方法 API 也可用
    registry = ToolRegistry()
    assert registry.has_tool("Read")
    assert "Read" in registry.list_tool_names()


def test_v2_prompts_philosophy():
    """验证 V2 提示词体现了 Claude Code 哲学"""
    from llm.agent.prompts_v2 import SYSTEM_PROMPT_V2, CODER_PROMPT_V2
    
    # 核心哲学关键词
    philosophy_keywords = {
        "tool": "Tool-Use Centric",
        "explore": "Explore First",
        "exact": "Precise Edits",
        "autonomous": "Model Autonomy"
    }
    
    combined_prompt = (SYSTEM_PROMPT_V2 + CODER_PROMPT_V2).lower()
    
    for keyword, concept in philosophy_keywords.items():
        assert keyword in combined_prompt, \
            f"Philosophy concept '{concept}' (keyword: {keyword}) not found"


def test_v2_integration_complete():
    """综合验证：V2 系统完整性"""
    from llm.agent.tools.tool_registry import ToolRegistry
    from llm.agent.prompts_v2 import (
        SYSTEM_PROMPT_V2,
        PLANNER_PROMPT_V2,
        CODER_PROMPT_V2,
        REVIEWER_PROMPT_V2
    )
    
    # 1. 工具系统完整
    registry = ToolRegistry()
    assert len(registry.list_tool_names()) >= 8
    
    # 2. 提示词系统完整
    assert len(SYSTEM_PROMPT_V2) > 500
    assert len(PLANNER_PROMPT_V2) > 500
    assert len(CODER_PROMPT_V2) > 500
    assert len(REVIEWER_PROMPT_V2) > 500
    
    # 3. 工具和提示词一致
    schemas = ToolRegistry.get_tool_schemas()
    tool_names = [s["name"] for s in schemas]
    
    for tool_name in ["Read", "Edit", "Grep", "Ls", "Glob"]:
        assert tool_name in tool_names
        assert tool_name in SYSTEM_PROMPT_V2
