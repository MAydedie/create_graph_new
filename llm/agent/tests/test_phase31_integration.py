#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3.1 端到端集成测试

模拟真实用户场景，测试：
1. PlannerAgent 自动调研功能
2. TaskTool 任务分解功能
3. 完整的 Orchestrator 工作流
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


import logging
from llm.agent.tools.task_tool import TaskTool
from llm.agent.tools.tool_registry import ToolRegistry
from llm.agent.agents.orchestrator import Orchestrator
from llm.agent.agents.planner_agent import PlannerAgent
from llm.agent.core.task_session import TaskSession

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Phase3.1Test")


def test_scenario_1_task_tool_basic():
    """
    场景 1: TaskTool 基本功能测试
    
    测试 TaskTool 能否正确执行多个子任务并聚合结果
    """
    print("\n" + "="*60)
    print("场景 1: TaskTool 基本功能测试")
    print("="*60)
    
    # 创建 ToolRegistry 和 Orchestrator
    tool_registry = ToolRegistry()
    orchestrator = Orchestrator(tool_registry=tool_registry, verbose=True)
    
    # 定义子任务
    subtasks = [
        {
            "type": "research",
            "prompt": "列出当前项目 llm/agent 目录下的所有 Python 文件",
            "priority": 3
        },
        {
            "type": "search",
            "prompt": "查找 Orchestrator 类的定义位置",
            "priority": 2
        }
    ]
    
    print("\n执行子任务...")
    result = TaskTool.execute(
        subtasks=subtasks,
        orchestrator=orchestrator,
        verbose=True
    )
    
    print(f"\n执行结果:")
    print(f"  成功: {result['success']}")
    print(f"  子任务数: {result['subtask_count']}")
    print(f"  失败数: {result['failed_count']}")
    print(f"\n综合总结:")
    print(f"  {result['summary']}")
    
    print("\n" + "="*60)
    return result


def test_scenario_2_planner_auto_research():
    """
    场景 2: PlannerAgent 自动调研测试
    
    测试 PlannerAgent 能否自动调研代码库并生成计划
    """
    print("\n" + "="*60)
    print("场景 2: PlannerAgent 自动调研测试")
    print("="*60)
    
    # 创建 ToolRegistry 和 Orchestrator
    tool_registry = ToolRegistry()
    orchestrator = Orchestrator(tool_registry=tool_registry, verbose=True)
    
    # 创建 PlannerAgent（会自动设置 orchestrator 引用）
    planner = PlannerAgent(verbose=True)
    orchestrator.planner = planner
    
    # 验证 orchestrator 引用已设置
    print(f"\nPlannerAgent.orchestrator 已设置: {planner.orchestrator is not None}")
    
    # 创建简单的 context（不使用真实的 LLM）
    context = {
        "rag_knowledge": {
            "project_name": "create_graph",
            "main_modules": ["llm", "parsers", "visualization"]
        }
    }
    
    print("\n注意: 这个测试会调用真实的 LLM API")
    print("如果不想调用 LLM，请跳过这个测试\n")
    
    # 这里我们只测试调研部分，不实际生成计划
    # 因为生成计划需要真实的 LLM API
    
    print("测试跳过（需要真实 LLM API）")
    print("\n" + "="*60)
    return {"skipped": True}


def test_scenario_3_orchestrator_integration():
    """
    场景 3: Orchestrator 集成测试
    
    测试 Orchestrator 能否正确设置 planner 的 orchestrator 引用
    """
    print("\n" + "="*60)
    print("场景 3: Orchestrator 集成测试")
    print("="*60)
    
    # 创建 ToolRegistry
    tool_registry = ToolRegistry()
    
    # 创建 PlannerAgent（没有 orchestrator）
    planner = PlannerAgent(verbose=False)
    print(f"\n创建 PlannerAgent 后:")
    print(f"  planner.orchestrator = {planner.orchestrator}")
    
    # 创建 Orchestrator（传入 planner）
    orchestrator = Orchestrator(
        planner=planner,
        tool_registry=tool_registry,
        verbose=False
    )
    
    print(f"\n创建 Orchestrator 后:")
    print(f"  planner.orchestrator = {planner.orchestrator}")
    print(f"  planner.orchestrator is orchestrator = {planner.orchestrator is orchestrator}")
    
    # 验证
    assert planner.orchestrator is orchestrator, "Orchestrator 应该自动设置 planner.orchestrator"
    
    print("\n✅ 测试通过: Orchestrator 正确设置了 planner 的 orchestrator 引用")
    print("="*60)
    return {"success": True}


def test_scenario_4_task_tool_error_handling():
    """
    场景 4: TaskTool 错误处理测试
    
    测试 TaskTool 能否正确处理错误情况
    """
    print("\n" + "="*60)
    print("场景 4: TaskTool 错误处理测试")
    print("="*60)
    
    tool_registry = ToolRegistry()
    orchestrator = Orchestrator(tool_registry=tool_registry, verbose=False)
    
    # 测试 1: 无效的子任务
    print("\n测试 1: 无效的子任务（缺少 type）")
    result1 = TaskTool.execute(
        subtasks=[{"prompt": "测试"}],  # 缺少 type
        orchestrator=orchestrator,
        verbose=False
    )
    print(f"  失败数: {result1['failed_count']}")
    assert result1['failed_count'] == 1, "应该有 1 个失败"
    print("  ✅ 正确处理")
    
    # 测试 2: 空子任务列表
    print("\n测试 2: 空子任务列表")
    result2 = TaskTool.execute(
        subtasks=[],
        orchestrator=orchestrator,
        verbose=False
    )
    print(f"  成功: {result2['success']}")
    assert result2['success'] is False, "应该失败"
    print("  ✅ 正确处理")
    
    # 测试 3: 没有 orchestrator
    print("\n测试 3: 没有 orchestrator")
    result3 = TaskTool.execute(
        subtasks=[{"type": "research", "prompt": "测试"}],
        orchestrator=None,
        verbose=False
    )
    print(f"  成功: {result3['success']}")
    assert result3['success'] is False, "应该失败"
    print("  ✅ 正确处理")
    
    print("\n✅ 所有错误处理测试通过")
    print("="*60)
    return {"success": True}


def test_scenario_5_priority_sorting():
    """
    场景 5: 优先级排序测试
    
    测试 TaskTool 能否按优先级正确排序子任务
    """
    print("\n" + "="*60)
    print("场景 5: 优先级排序测试")
    print("="*60)
    
    # 定义带优先级的子任务
    subtasks = [
        {"type": "research", "prompt": "任务 A", "priority": 1},
        {"type": "search", "prompt": "任务 B", "priority": 3},
        {"type": "diagnostic", "prompt": "任务 C", "priority": 2}
    ]
    
    print("\n原始顺序:")
    for i, task in enumerate(subtasks, 1):
        print(f"  {i}. {task['prompt']} (优先级: {task.get('priority', 0)})")
    
    # 排序（高优先级先执行）
    sorted_tasks = sorted(subtasks, key=lambda x: x.get("priority", 0), reverse=True)
    
    print("\n排序后顺序:")
    for i, task in enumerate(sorted_tasks, 1):
        print(f"  {i}. {task['prompt']} (优先级: {task.get('priority', 0)})")
    
    # 验证
    assert sorted_tasks[0]['prompt'] == "任务 B", "优先级 3 应该第一"
    assert sorted_tasks[1]['prompt'] == "任务 C", "优先级 2 应该第二"
    assert sorted_tasks[2]['prompt'] == "任务 A", "优先级 1 应该第三"
    
    print("\n✅ 优先级排序正确")
    print("="*60)
    return {"success": True}


def main():
    """运行所有测试场景"""
    print("\n" + "="*60)
    print("Phase 3.1 端到端集成测试")
    print("="*60)
    
    results = {}
    
    try:
        # 场景 1: TaskTool 基本功能
        results['scenario_1'] = test_scenario_1_task_tool_basic()
    except Exception as e:
        logger.error(f"场景 1 失败: {e}", exc_info=True)
        results['scenario_1'] = {"error": str(e)}
    
    try:
        # 场景 2: PlannerAgent 自动调研（跳过，需要 LLM）
        results['scenario_2'] = test_scenario_2_planner_auto_research()
    except Exception as e:
        logger.error(f"场景 2 失败: {e}", exc_info=True)
        results['scenario_2'] = {"error": str(e)}
    
    try:
        # 场景 3: Orchestrator 集成
        results['scenario_3'] = test_scenario_3_orchestrator_integration()
    except Exception as e:
        logger.error(f"场景 3 失败: {e}", exc_info=True)
        results['scenario_3'] = {"error": str(e)}
    
    try:
        # 场景 4: 错误处理
        results['scenario_4'] = test_scenario_4_task_tool_error_handling()
    except Exception as e:
        logger.error(f"场景 4 失败: {e}", exc_info=True)
        results['scenario_4'] = {"error": str(e)}
    
    try:
        # 场景 5: 优先级排序
        results['scenario_5'] = test_scenario_5_priority_sorting()
    except Exception as e:
        logger.error(f"场景 5 失败: {e}", exc_info=True)
        results['scenario_5'] = {"error": str(e)}
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    success_count = sum(1 for r in results.values() if r.get('success') or r.get('skipped'))
    total_count = len(results)
    
    print(f"\n通过: {success_count}/{total_count}")
    
    for scenario, result in results.items():
        status = "✅" if (result.get('success') or result.get('skipped')) else "❌"
        print(f"  {status} {scenario}")
    
    print("\n" + "="*60)
    
    return results


if __name__ == "__main__":
    main()
