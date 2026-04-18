#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
端到端测试脚本 - 使用最小化测试问题验证整个 Multi-Agent 系统
"""

import sys
import os
import json
import logging
from pathlib import Path

# 设置 stdout 编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 确保项目路径
PROJECT_ROOT = Path(r"D:\代码仓库生图\create_graph")
sys.path.insert(0, str(PROJECT_ROOT))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)

def safe_print(msg):
    """安全打印"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('gbk', errors='replace').decode('gbk'))

def test_minimal_orchestrator():
    """测试 Orchestrator 使用最小化问题"""
    safe_print("=" * 60)
    safe_print("端到端测试：Orchestrator 执行最小化任务")
    safe_print("=" * 60)
    
    from llm.agent.agents import orchestrator, planner_agent, coder_agent, reviewer_agent
    from llm.agent.cognitive import knowledge_agent, memory_agent
    
    # 最小化问题 - 只为一个文件夹生成测试
    user_goal = r"为D:\代码仓库生图\create_graph\test_sandbox\finance_cli\finance_cli\commands目录下的stock.py文件生成单元测试"
    
    safe_print(f"\n用户目标: {user_goal}")
    safe_print("-" * 60)
    
    # 创建代理
    ka = knowledge_agent.KnowledgeAgent()
    ma = memory_agent.MemoryAgent()
    planner = planner_agent.PlannerAgent(verbose=True)
    coder = coder_agent.CoderAgent(verbose=True)
    reviewer = reviewer_agent.ReviewerAgent(verbose=True)
    
    # 创建 Orchestrator
    orch = orchestrator.create_orchestrator(
        knowledge_agent=ka,
        memory_agent=ma,
        planner=planner,
        coder=coder,
        reviewer=reviewer,
        verbose=True
    )
    
    safe_print("\n开始执行任务...")
    
    # 执行（带重试）
    result = orch.execute_with_retry(user_goal, max_retries=2)
    
    safe_print("\n" + "=" * 60)
    safe_print("执行结果:")
    safe_print("=" * 60)
    
    # 格式化输出关键结果
    safe_print(f"成功: {result.get('success')}")
    safe_print(f"任务 ID: {result.get('task_id')}")
    safe_print(f"状态: {result.get('status')}")
    
    if result.get('error'):
        safe_print(f"错误: {result.get('error')}")
    
    if result.get('retry_info'):
        safe_print(f"\n重试信息:")
        safe_print(f"  - 总尝试次数: {result['retry_info'].get('total_attempts')}")
        safe_print(f"  - 有重试: {result['retry_info'].get('had_retries')}")
        safe_print(f"  - 使用策略: {result['retry_info'].get('strategy_used')}")
    
    # 检查步骤结果
    step_results = result.get('step_results', {})
    if step_results:
        safe_print(f"\n步骤执行结果 ({len(step_results)} 步):")
        for step_id, step_result in step_results.items():
            success = step_result.get('success', 'N/A')
            summary = step_result.get('summary', '')[:50]
            safe_print(f"  [{step_id}] 成功: {success} - {summary}")
    
    safe_print("\n" + "=" * 60)
    
    return result


if __name__ == "__main__":
    safe_print("=" * 60)
    safe_print("Multi-Agent 端到端测试")
    safe_print("=" * 60)
    
    try:
        result = test_minimal_orchestrator()
        
        if result.get('success'):
            safe_print("\n✓ 测试成功完成！")
            exit(0)
        else:
            safe_print(f"\n✗ 测试失败: {result.get('error')}")
            exit(1)
    except Exception as e:
        safe_print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
