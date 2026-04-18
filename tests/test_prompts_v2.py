"""
Test suite for prompts_v2.py
Verify that all V2 prompts are properly defined
"""
import pytest


def test_prompts_v2_module_exists():
    """验证 prompts_v2 模块可以导入"""
    from llm.agent import prompts_v2
    assert prompts_v2 is not None


def test_system_prompt_v2_exists():
    """验证通用系统提示词存在"""
    from llm.agent.prompts_v2 import SYSTEM_PROMPT_V2
    
    assert isinstance(SYSTEM_PROMPT_V2, str)
    assert len(SYSTEM_PROMPT_V2) > 100
    assert "Software Engineer Agent" in SYSTEM_PROMPT_V2
    assert "Tools" in SYSTEM_PROMPT_V2


def test_planner_prompt_v2_exists():
    """验证 Planner 提示词存在"""
    from llm.agent.prompts_v2 import PLANNER_PROMPT_V2
    
    assert isinstance(PLANNER_PROMPT_V2, str)
    assert len(PLANNER_PROMPT_V2) > 100
    assert "Planning Agent" in PLANNER_PROMPT_V2
    assert "JSON" in PLANNER_PROMPT_V2


def test_coder_prompt_v2_exists():
    """验证 Coder 提示词存在"""
    from llm.agent.prompts_v2 import CODER_PROMPT_V2
    
    assert isinstance(CODER_PROMPT_V2, str)
    assert len(CODER_PROMPT_V2) > 100
    assert "Coding Agent" in CODER_PROMPT_V2
    assert "Read" in CODER_PROMPT_V2
    assert "Edit" in CODER_PROMPT_V2


def test_reviewer_prompt_v2_exists():
    """验证 Reviewer 提示词存在"""
    from llm.agent.prompts_v2 import REVIEWER_PROMPT_V2
    
    assert isinstance(REVIEWER_PROMPT_V2, str)
    assert len(REVIEWER_PROMPT_V2) > 100
    assert "Code Review Agent" in REVIEWER_PROMPT_V2
    assert "approved" in REVIEWER_PROMPT_V2


def test_subagent_prompts_exist():
    """验证 SubAgent 提示词存在"""
    from llm.agent.prompts_v2 import SUBAGENT_PROMPTS
    
    assert isinstance(SUBAGENT_PROMPTS, dict)
    assert "research" in SUBAGENT_PROMPTS
    assert "search" in SUBAGENT_PROMPTS
    assert "diagnostic" in SUBAGENT_PROMPTS
    
    for agent_type, prompt in SUBAGENT_PROMPTS.items():
        assert isinstance(prompt, str)
        assert len(prompt) > 50


def test_tool_examples_exist():
    """验证工具使用示例存在"""
    from llm.agent.prompts_v2 import TOOL_EXAMPLES
    
    assert isinstance(TOOL_EXAMPLES, str)
    assert "Glob" in TOOL_EXAMPLES
    assert "Read" in TOOL_EXAMPLES
    assert "Edit" in TOOL_EXAMPLES


def test_prompts_contain_tool_names():
    """验证提示词包含所有 V2 工具名称"""
    from llm.agent.prompts_v2 import SYSTEM_PROMPT_V2
    
    v2_tools = ["Read", "Edit", "Write", "Bash", "Grep", "Ls", "Glob", "Task"]
    
    for tool in v2_tools:
        assert tool in SYSTEM_PROMPT_V2, f"Tool {tool} not mentioned in SYSTEM_PROMPT_V2"


def test_prompts_follow_philosophy():
    """验证提示词遵循 Claude Code 哲学"""
    from llm.agent.prompts_v2 import SYSTEM_PROMPT_V2
    
    # 核心哲学关键词
    philosophy_keywords = [
        "Explore",  # Explore First
        "exact",    # Precise edits
        "tool",     # Tool-first mindset
    ]
    
    for keyword in philosophy_keywords:
        assert keyword.lower() in SYSTEM_PROMPT_V2.lower(), \
            f"Philosophy keyword '{keyword}' not found in prompt"


def test_planner_has_json_schema():
    """验证 Planner 提示词包含 JSON schema"""
    from llm.agent.prompts_v2 import PLANNER_PROMPT_V2
    
    assert "plan_id" in PLANNER_PROMPT_V2
    assert "steps" in PLANNER_PROMPT_V2
    assert "step_id" in PLANNER_PROMPT_V2


def test_coder_has_tool_guidelines():
    """验证 Coder 提示词包含工具使用指南"""
    from llm.agent.prompts_v2 import CODER_PROMPT_V2
    
    assert "Read Tool" in CODER_PROMPT_V2
    assert "Edit Tool" in CODER_PROMPT_V2
    assert "Write Tool" in CODER_PROMPT_V2
    assert "Bash Tool" in CODER_PROMPT_V2
    assert "mock" in CODER_PROMPT_V2.lower()  # 测试文件创建指南


def test_reviewer_has_scoring_guide():
    """验证 Reviewer 提示词包含评分指南"""
    from llm.agent.prompts_v2 import REVIEWER_PROMPT_V2
    
    assert "score" in REVIEWER_PROMPT_V2.lower()
    assert "90-100" in REVIEWER_PROMPT_V2 or "0-100" in REVIEWER_PROMPT_V2
