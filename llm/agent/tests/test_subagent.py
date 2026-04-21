#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SubAgent 单元测试

测试 Phase 3 SubAgent 机制的核心功能：
1. SubAgent 创建
2. 上下文隔离
3. 工具限制
4. Orchestrator 孵化
"""

import sys
import os
from pathlib import Path

# 确保项目路径
def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "config" / "config.py").exists():
            return current
        current = current.parent
    return Path.cwd()

PROJECT_ROOT = _find_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


import pytest
from llm.agent.core.subagent import SubAgent, create_subagent
from llm.agent.core.task_session import TaskSession
from llm.agent.tools.tool_registry import ToolRegistry


class TestSubAgent:
    """SubAgent 单元测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.tool_registry = ToolRegistry()
    
    def test_subagent_creation(self):
        """测试 SubAgent 创建"""
        subagent = SubAgent(
            agent_type="research",
            prompt="测试任务",
            tool_registry=self.tool_registry,
            verbose=False
        )
        
        assert subagent.agent_type == "research"
        assert subagent.prompt == "测试任务"
        assert subagent.config["max_steps"] == 10
        assert "Read" in subagent.config["tools"]
    
    def test_invalid_agent_type(self):
        """测试无效的 Agent 类型"""
        with pytest.raises(ValueError):
            SubAgent(
                agent_type="invalid_type",
                prompt="测试任务",
                tool_registry=self.tool_registry,
                verbose=False
            )
    
    def test_tool_filtering(self):
        """测试工具过滤"""
        subagent = SubAgent(
            agent_type="search",
            prompt="搜索任务",
            tool_registry=self.tool_registry,
            verbose=False
        )
        
        # search 类型只能使用 Grep 和 Read
        allowed_tools = subagent.config["tools"]
        assert "Grep" in allowed_tools
        assert "Read" in allowed_tools
        assert "Write" not in allowed_tools  # 不应该有 Write
        assert "Edit" not in allowed_tools  # 不应该有 Edit
    
    def test_lightweight_session_creation(self):
        """测试轻量级 Session 创建"""
        # 创建父 Session
        parent_session = TaskSession.create(user_goal="父任务")
        parent_session.set_rag_knowledge({"test_key": "test_value"})
        
        # 创建轻量级 Session
        sub_session = TaskSession.create_lightweight(
            user_goal="子任务",
            parent_session=parent_session
        )
        
        # 验证继承了 RAG 知识
        assert sub_session.rag_knowledge == parent_session.rag_knowledge
        
        # 验证有独立的消息历史
        assert sub_session.messages == []
        assert sub_session.task_id != parent_session.task_id
    
    def test_context_isolation(self):
        """测试上下文隔离"""
        # 创建父 Session
        parent_session = TaskSession.create(user_goal="父任务")
        parent_session.messages.append({"role": "user", "content": "父消息"})
        
        # 创建 SubAgent
        subagent = SubAgent(
            agent_type="diagnostic",
            prompt="诊断任务",
            tool_registry=self.tool_registry,
            parent_session=parent_session,
            verbose=False
        )
        
        # 验证 SubAgent 的 Session 有独立的消息历史
        assert subagent.session.messages == []
        assert len(parent_session.messages) == 1
    
    def test_create_subagent_helper(self):
        """测试便捷创建函数"""
        subagent = create_subagent(
            agent_type="research",
            prompt="测试任务",
            tool_registry=self.tool_registry,
            verbose=False
        )
        
        assert isinstance(subagent, SubAgent)
        assert subagent.agent_type == "research"


class TestToolRegistry:
    """ToolRegistry 增强功能测试"""
    
    def test_filter_method(self):
        """测试 filter 方法"""
        registry = ToolRegistry()
        
        # 过滤只保留 Read 和 Grep
        filtered = registry.filter(["Read", "Grep"])
        
        assert filtered.has_tool("Read")
        assert filtered.has_tool("Grep")
        assert not filtered.has_tool("Write")
        assert not filtered.has_tool("Edit")
    
    def test_list_tool_names(self):
        """测试列出工具名称"""
        registry = ToolRegistry()
        tool_names = registry.list_tool_names()
        
        assert "Read" in tool_names
        assert "Write" in tool_names
        assert "Edit" in tool_names
        assert "Bash" in tool_names
        assert "Grep" in tool_names
    
    def test_has_tool(self):
        """测试 has_tool 方法"""
        registry = ToolRegistry()
        
        assert registry.has_tool("Read")
        assert registry.has_tool("Write")
        assert not registry.has_tool("NonExistentTool")


class TestTaskSession:
    """TaskSession 增强功能测试"""
    
    def test_create_lightweight_without_parent(self):
        """测试无父 Session 的轻量级创建"""
        session = TaskSession.create_lightweight(user_goal="独立子任务")
        
        assert session.user_goal == "独立子任务"
        assert session.messages == []
        assert "subagent_" in session.task_id
    
    def test_create_lightweight_with_parent(self):
        """测试有父 Session 的轻量级创建"""
        parent = TaskSession.create(user_goal="父任务")
        parent.set_rag_knowledge({"key": "value"})
        parent.set_file_structure({"files": ["a.py", "b.py"]})
        
        child = TaskSession.create_lightweight(
            user_goal="子任务",
            parent_session=parent
        )
        
        # 验证继承
        assert child.rag_knowledge == parent.rag_knowledge
        assert child.file_structure == parent.file_structure
        
        # 验证独立性
        assert child.messages == []
        assert child.task_id != parent.task_id


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
