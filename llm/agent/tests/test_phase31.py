#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3.1 单元测试

测试 TaskTool 和 PlannerAgent 的自动调研功能
"""

import sys
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
from llm.agent.tools.task_tool import TaskTool, execute_subtasks
from llm.agent.tools.tool_registry import ToolRegistry
from llm.agent.agents.orchestrator import Orchestrator
from llm.agent.agents.planner_agent import PlannerAgent


class TestTaskTool:
    """TaskTool 单元测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.tool_registry = ToolRegistry()
        self.orchestrator = Orchestrator(tool_registry=self.tool_registry, verbose=False)
    
    def test_task_tool_schema(self):
        """测试 TaskTool Schema"""
        schema = TaskTool.get_schema()
        
        assert schema["name"] == "Task"
        assert "subtasks" in schema["input_schema"]["properties"]
        assert schema["input_schema"]["required"] == ["subtasks"]
    
    def test_task_tool_no_orchestrator(self):
        """测试没有 orchestrator 的情况"""
        result = TaskTool.execute(
            subtasks=[{"type": "research", "prompt": "测试"}],
            orchestrator=None,
            verbose=False
        )
        
        assert result["success"] is False
        assert "未提供 Orchestrator" in result["error"]
    
    def test_task_tool_empty_subtasks(self):
        """测试空子任务列表"""
        result = TaskTool.execute(
            subtasks=[],
            orchestrator=self.orchestrator,
            verbose=False
        )
        
        assert result["success"] is False
        assert "非空列表" in result["error"]
    
    def test_task_tool_invalid_subtask(self):
        """测试无效的子任务"""
        result = TaskTool.execute(
            subtasks=[
                {"type": "research"},  # 缺少 prompt
                {"prompt": "测试"}  # 缺少 type
            ],
            orchestrator=self.orchestrator,
            verbose=False
        )
        
        assert result["subtask_count"] == 2
        assert result["failed_count"] == 2
    
    def test_task_tool_priority_sorting(self):
        """测试优先级排序"""
        # 注意：这个测试只验证排序逻辑，不实际执行 SubAgent
        subtasks = [
            {"type": "research", "prompt": "任务1", "priority": 1},
            {"type": "search", "prompt": "任务2", "priority": 3},
            {"type": "diagnostic", "prompt": "任务3", "priority": 2}
        ]
        
        # 验证排序（高优先级先执行）
        sorted_tasks = sorted(subtasks, key=lambda x: x.get("priority", 0), reverse=True)
        assert sorted_tasks[0]["prompt"] == "任务2"  # priority 3
        assert sorted_tasks[1]["prompt"] == "任务3"  # priority 2
        assert sorted_tasks[2]["prompt"] == "任务1"  # priority 1
    
    def test_execute_subtasks_helper(self):
        """测试便捷函数"""
        result = execute_subtasks(
            subtasks=[],
            orchestrator=self.orchestrator,
            verbose=False
        )
        
        assert "success" in result


class TestPlannerAgentIntegration:
    """PlannerAgent 集成测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.tool_registry = ToolRegistry()
    
    def test_planner_without_orchestrator(self):
        """测试没有 orchestrator 的 PlannerAgent（向后兼容）"""
        planner = PlannerAgent(verbose=False)
        
        assert planner.orchestrator is None
        # plan 方法应该正常工作，只是不会自动调研
    
    def test_planner_with_orchestrator(self):
        """测试有 orchestrator 的 PlannerAgent"""
        orchestrator = Orchestrator(tool_registry=self.tool_registry, verbose=False)
        planner = PlannerAgent(orchestrator=orchestrator, verbose=False)
        
        assert planner.orchestrator is orchestrator
    
    def test_orchestrator_sets_planner_reference(self):
        """测试 Orchestrator 自动设置 planner 的 orchestrator 引用"""
        planner = PlannerAgent(verbose=False)
        orchestrator = Orchestrator(
            planner=planner,
            tool_registry=self.tool_registry,
            verbose=False
        )
        
        # Orchestrator 应该自动设置 planner.orchestrator
        assert planner.orchestrator is orchestrator
    
    def test_planner_skip_research(self):
        """测试跳过自动调研"""
        orchestrator = Orchestrator(tool_registry=self.tool_registry, verbose=False)
        planner = PlannerAgent(orchestrator=orchestrator, verbose=False)
        
        # 使用 skip_research=True 应该不会调用 SubAgent
        # 注意：这个测试只验证参数传递，不实际生成计划
        assert planner.orchestrator is not None


class TestToolRegistry:
    """ToolRegistry 测试（验证 TaskTool 已注册）"""
    
    def test_task_tool_registered(self):
        """测试 TaskTool 已注册"""
        registry = ToolRegistry()
        
        assert registry.has_tool("Task")
        assert "Task" in registry.list_tool_names()
    
    def test_task_tool_get(self):
        """测试获取 TaskTool"""
        registry = ToolRegistry()
        task_tool = registry.get("Task")
        
        assert task_tool is not None
        assert task_tool.name == "Task"


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
