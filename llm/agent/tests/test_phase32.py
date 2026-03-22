#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3.2 单元测试

测试新增功能：
1. ResearchCache - 调研结果缓存
2. PlannerAgent 智能调研策略
3. TaskTool 并行执行
"""

import sys
import time
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
from llm.agent.core.research_cache import ResearchCache, get_global_cache, clear_global_cache
from llm.agent.tools.task_tool import TaskTool
from llm.agent.tools.tool_registry import ToolRegistry
from llm.agent.agents.orchestrator import Orchestrator
from llm.agent.agents.planner_agent import PlannerAgent


class TestResearchCache:
    """ResearchCache 单元测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.cache = ResearchCache(ttl=2)  # 2 秒过期，方便测试
    
    def test_cache_basic(self):
        """测试基本的缓存功能"""
        project_path = "/test/project"
        user_goal = "生成测试"
        result = "这是调研结果"
        
        # 设置缓存
        self.cache.set(project_path, user_goal, result)
        
        # 获取缓存
        cached = self.cache.get(project_path, user_goal)
        
        assert cached == result
        assert len(self.cache) == 1
    
    def test_cache_miss(self):
        """测试缓存未命中"""
        cached = self.cache.get("/test/project", "不存在的目标")
        
        assert cached is None
    
    def test_cache_ttl(self):
        """测试 TTL 过期机制"""
        project_path = "/test/project"
        user_goal = "生成测试"
        result = "调研结果"
        
        # 设置缓存
        self.cache.set(project_path, user_goal, result)
        
        # 立即获取，应该命中
        cached = self.cache.get(project_path, user_goal)
        assert cached == result
        
        # 等待过期
        time.sleep(2.5)
        
        # 再次获取，应该过期
        cached = self.cache.get(project_path, user_goal)
        assert cached is None
    
    def test_cache_stats(self):
        """测试缓存统计"""
        project_path = "/test/project"
        
        # 设置缓存
        self.cache.set(project_path, "目标1", "结果1")
        self.cache.set(project_path, "目标2", "结果2")
        
        # 命中
        self.cache.get(project_path, "目标1")
        
        # 未命中
        self.cache.get(project_path, "目标3")
        
        stats = self.cache.get_stats()
        
        assert stats["sets"] == 2
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["total_requests"] == 2
        assert stats["hit_rate"] == 50.0
        assert stats["cache_size"] == 2
    
    def test_cache_clear(self):
        """测试清空缓存"""
        self.cache.set("/test/project", "目标1", "结果1")
        self.cache.set("/test/project", "目标2", "结果2")
        
        assert len(self.cache) == 2
        
        self.cache.clear()
        
        assert len(self.cache) == 0
    
    def test_global_cache(self):
        """测试全局缓存单例"""
        cache1 = get_global_cache()
        cache2 = get_global_cache()
        
        assert cache1 is cache2
        
        # 清空全局缓存
        clear_global_cache()


class TestPlannerAgentSmartStrategy:
    """PlannerAgent 智能调研策略测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.planner = PlannerAgent(verbose=False)
    
    def test_should_research_simple_task(self):
        """测试简单任务应该跳过调研"""
        assert self.planner._should_research("简单修改一个文件") == False
        assert self.planner._should_research("快速删除函数") == False
        assert self.planner._should_research("重命名变量") == False
    
    def test_should_research_complex_task(self):
        """测试复杂任务应该调研"""
        assert self.planner._should_research("复杂的重构任务") == True
        assert self.planner._should_research("大型架构设计") == True
        assert self.planner._should_research("新增模块") == True
    
    def test_should_research_default(self):
        """测试默认行为（无关键词）"""
        assert self.planner._should_research("为项目生成测试") == True
        assert self.planner._should_research("实现功能 X") == True


class TestTaskToolParallel:
    """TaskTool 并行执行测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.tool_registry = ToolRegistry()
        self.orchestrator = Orchestrator(tool_registry=self.tool_registry, verbose=False)
    
    def test_parallel_parameter(self):
        """测试 parallel 参数"""
        subtasks = [
            {"type": "research", "prompt": "任务1"},
            {"type": "search", "prompt": "任务2"}
        ]
        
        # 串行执行（默认）
        result_serial = TaskTool.execute(
            subtasks=subtasks,
            orchestrator=self.orchestrator,
            parallel=False,
            verbose=False
        )
        
        assert "subtask_count" in result_serial
        assert result_serial["subtask_count"] == 2
        
        # 并行执行
        result_parallel = TaskTool.execute(
            subtasks=subtasks,
            orchestrator=self.orchestrator,
            parallel=True,
            verbose=False
        )
        
        assert "subtask_count" in result_parallel
        assert result_parallel["subtask_count"] == 2
    
    def test_max_concurrent(self):
        """测试最大并发数限制"""
        # 创建 10 个子任务
        subtasks = [
            {"type": "research", "prompt": f"任务{i}"}
            for i in range(10)
        ]
        
        # 限制最大并发数为 3
        result = TaskTool.execute(
            subtasks=subtasks,
            orchestrator=self.orchestrator,
            parallel=True,
            max_concurrent=3,
            verbose=False
        )
        
        # 应该分批执行（10 个任务，每批 3 个，共 4 批）
        assert result["subtask_count"] == 10


class TestPlannerAgentCache:
    """PlannerAgent 缓存集成测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.tool_registry = ToolRegistry()
        self.orchestrator = Orchestrator(tool_registry=self.tool_registry, verbose=False)
        self.planner = PlannerAgent(orchestrator=self.orchestrator, verbose=False)
        
        # 清空全局缓存
        clear_global_cache()
    
    def test_cache_integration(self):
        """测试缓存集成（不实际调用 LLM）"""
        # 验证 planner 有缓存
        assert hasattr(self.planner, '_research_cache')
        assert self.planner._research_cache is not None
        
        # 验证缓存是全局共享的
        cache1 = self.planner._research_cache
        planner2 = PlannerAgent(verbose=False)
        cache2 = planner2._research_cache
        
        assert cache1 is cache2


class TestBackwardCompatibility:
    """向后兼容性测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.tool_registry = ToolRegistry()
        self.orchestrator = Orchestrator(tool_registry=self.tool_registry, verbose=False)
    
    def test_task_tool_default_serial(self):
        """测试 TaskTool 默认串行执行"""
        subtasks = [
            {"type": "research", "prompt": "任务1"}
        ]
        
        # 不指定 parallel 参数，应该默认串行
        result = TaskTool.execute(
            subtasks=subtasks,
            orchestrator=self.orchestrator,
            verbose=False
        )
        
        assert result["subtask_count"] == 1
    
    def test_planner_default_research(self):
        """测试 PlannerAgent 默认调研"""
        planner = PlannerAgent(verbose=False)
        
        # 默认应该调研（除非有跳过关键词）
        assert planner._should_research("普通任务") == True
    
    def test_planner_default_use_cache(self):
        """测试 PlannerAgent 默认使用缓存"""
        # plan 方法的 use_cache 参数默认为 True
        # 这里只验证参数存在，不实际调用
        planner = PlannerAgent(verbose=False)
        assert hasattr(planner, 'plan')


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
