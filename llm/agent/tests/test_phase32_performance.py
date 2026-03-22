#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3.2 性能测试

对比测试：
1. 串行 vs 并行执行时间
2. 缓存命中率
3. 智能策略准确性
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


import logging
from llm.agent.core.research_cache import ResearchCache, clear_global_cache
from llm.agent.tools.task_tool import TaskTool
from llm.agent.tools.tool_registry import ToolRegistry
from llm.agent.agents.orchestrator import Orchestrator
from llm.agent.agents.planner_agent import PlannerAgent

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Phase3.2Performance")


def test_serial_vs_parallel():
    """
    测试 1: 串行 vs 并行执行时间对比
    """
    print("\n" + "="*60)
    print("测试 1: 串行 vs 并行执行时间对比")
    print("="*60)
    
    tool_registry = ToolRegistry()
    orchestrator = Orchestrator(tool_registry=tool_registry, verbose=False)
    
    # 创建 5 个子任务
    subtasks = [
        {"type": "research", "prompt": f"列出 llm/agent 目录下的文件 {i}"}
        for i in range(5)
    ]
    
    # 串行执行
    print("\n串行执行 5 个子任务...")
    start_serial = time.time()
    result_serial = TaskTool.execute(
        subtasks=subtasks,
        orchestrator=orchestrator,
        parallel=False,
        verbose=False
    )
    time_serial = time.time() - start_serial
    
    print(f"  串行执行时间: {time_serial:.2f} 秒")
    print(f"  成功: {result_serial['subtask_count'] - result_serial['failed_count']}/{result_serial['subtask_count']}")
    
    # 并行执行
    print("\n并行执行 5 个子任务...")
    start_parallel = time.time()
    result_parallel = TaskTool.execute(
        subtasks=subtasks,
        orchestrator=orchestrator,
        parallel=True,
        max_concurrent=5,
        verbose=False
    )
    time_parallel = time.time() - start_parallel
    
    print(f"  并行执行时间: {time_parallel:.2f} 秒")
    print(f"  成功: {result_parallel['subtask_count'] - result_parallel['failed_count']}/{result_parallel['subtask_count']}")
    
    # 计算提升
    if time_parallel > 0:
        speedup = (time_serial / time_parallel - 1) * 100
        print(f"\n性能提升: {speedup:.1f}%")
        
        if speedup > 30:
            print("✅ 并行执行显著提升性能 (>30%)")
        elif speedup > 0:
            print("⚠️ 并行执行有提升，但不明显 (<30%)")
        else:
            print("❌ 并行执行反而更慢（可能是任务太简单）")
    
    print("="*60)
    
    return {
        "time_serial": time_serial,
        "time_parallel": time_parallel,
        "speedup": speedup if time_parallel > 0 else 0
    }


def test_cache_hit_rate():
    """
    测试 2: 缓存命中率测试
    """
    print("\n" + "="*60)
    print("测试 2: 缓存命中率测试")
    print("="*60)
    
    # 清空全局缓存
    clear_global_cache()
    
    cache = ResearchCache(ttl=3600)
    project_path = "/test/project"
    
    # 模拟 10 次调研请求
    requests = [
        ("生成测试", "结果1"),
        ("生成测试", "结果1"),  # 重复
        ("重构代码", "结果2"),
        ("生成测试", "结果1"),  # 重复
        ("添加功能", "结果3"),
        ("重构代码", "结果2"),  # 重复
        ("生成测试", "结果1"),  # 重复
        ("删除文件", "结果4"),
        ("添加功能", "结果3"),  # 重复
        ("生成测试", "结果1"),  # 重复
    ]
    
    hits = 0
    misses = 0
    
    for user_goal, result in requests:
        cached = cache.get(project_path, user_goal)
        
        if cached:
            hits += 1
            print(f"  ✅ 缓存命中: {user_goal}")
        else:
            misses += 1
            cache.set(project_path, user_goal, result)
            print(f"  ❌ 缓存未命中: {user_goal}")
    
    hit_rate = (hits / len(requests)) * 100
    
    print(f"\n缓存统计:")
    print(f"  总请求数: {len(requests)}")
    print(f"  命中数: {hits}")
    print(f"  未命中数: {misses}")
    print(f"  命中率: {hit_rate:.1f}%")
    
    # 验证缓存统计
    stats = cache.get_stats()
    print(f"\n缓存内部统计:")
    print(f"  {stats}")
    
    if hit_rate >= 80:
        print("\n✅ 缓存命中率优秀 (>=80%)")
    elif hit_rate >= 60:
        print("\n⚠️ 缓存命中率良好 (60-80%)")
    else:
        print("\n❌ 缓存命中率较低 (<60%)")
    
    print("="*60)
    
    return {
        "hit_rate": hit_rate,
        "hits": hits,
        "misses": misses
    }


def test_smart_strategy_accuracy():
    """
    测试 3: 智能调研策略准确性
    """
    print("\n" + "="*60)
    print("测试 3: 智能调研策略准确性")
    print("="*60)
    
    planner = PlannerAgent(verbose=False)
    
    # 测试用例：(user_goal, expected_should_research)
    test_cases = [
        # 应该跳过调研的
        ("简单修改一个文件", False),
        ("快速删除函数", False),
        ("重命名变量", False),
        ("小改动", False),
        
        # 应该调研的
        ("复杂的重构任务", True),
        ("大型架构设计", True),
        ("新增模块", True),
        ("重构整个系统", True),
        
        # 默认调研的
        ("为项目生成测试", True),
        ("实现功能 X", True),
        ("优化性能", True),
    ]
    
    correct = 0
    total = len(test_cases)
    
    for user_goal, expected in test_cases:
        actual = planner._should_research(user_goal)
        is_correct = (actual == expected)
        
        if is_correct:
            correct += 1
            print(f"  ✅ {user_goal}: {actual} (预期 {expected})")
        else:
            print(f"  ❌ {user_goal}: {actual} (预期 {expected})")
    
    accuracy = (correct / total) * 100
    
    print(f"\n准确性统计:")
    print(f"  总测试数: {total}")
    print(f"  正确数: {correct}")
    print(f"  准确率: {accuracy:.1f}%")
    
    if accuracy >= 90:
        print("\n✅ 智能策略准确率优秀 (>=90%)")
    elif accuracy >= 70:
        print("\n⚠️ 智能策略准确率良好 (70-90%)")
    else:
        print("\n❌ 智能策略准确率较低 (<70%)")
    
    print("="*60)
    
    return {
        "accuracy": accuracy,
        "correct": correct,
        "total": total
    }


def main():
    """运行所有性能测试"""
    print("\n" + "="*60)
    print("Phase 3.2 性能测试")
    print("="*60)
    
    results = {}
    
    try:
        # 测试 1: 串行 vs 并行
        results['serial_vs_parallel'] = test_serial_vs_parallel()
    except Exception as e:
        logger.error(f"测试 1 失败: {e}", exc_info=True)
        results['serial_vs_parallel'] = {"error": str(e)}
    
    try:
        # 测试 2: 缓存命中率
        results['cache_hit_rate'] = test_cache_hit_rate()
    except Exception as e:
        logger.error(f"测试 2 失败: {e}", exc_info=True)
        results['cache_hit_rate'] = {"error": str(e)}
    
    try:
        # 测试 3: 智能策略准确性
        results['smart_strategy'] = test_smart_strategy_accuracy()
    except Exception as e:
        logger.error(f"测试 3 失败: {e}", exc_info=True)
        results['smart_strategy'] = {"error": str(e)}
    
    # 总结
    print("\n" + "="*60)
    print("性能测试总结")
    print("="*60)
    
    # 串行 vs 并行
    if 'serial_vs_parallel' in results and 'speedup' in results['serial_vs_parallel']:
        speedup = results['serial_vs_parallel']['speedup']
        print(f"\n并行执行性能提升: {speedup:.1f}%")
    
    # 缓存命中率
    if 'cache_hit_rate' in results and 'hit_rate' in results['cache_hit_rate']:
        hit_rate = results['cache_hit_rate']['hit_rate']
        print(f"缓存命中率: {hit_rate:.1f}%")
    
    # 智能策略准确性
    if 'smart_strategy' in results and 'accuracy' in results['smart_strategy']:
        accuracy = results['smart_strategy']['accuracy']
        print(f"智能策略准确率: {accuracy:.1f}%")
    
    print("\n" + "="*60)
    
    return results


if __name__ == "__main__":
    main()
