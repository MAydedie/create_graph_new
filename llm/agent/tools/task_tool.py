#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TaskTool - 任务分解工具 - Phase 3.1

允许 Agent 将复杂任务分解为多个子任务，
并委托给 SubAgent 执行。

核心功能：
1. 接收子任务列表
2. 调度 SubAgent 执行
3. 聚合结果
4. 生成综合总结
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

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


logger = logging.getLogger("TaskTool")


class TaskTool:
    """
    任务分解工具
    
    允许 Agent 将大任务分解为多个子任务，
    并委托给 SubAgent 执行。
    
    特点：
    - 支持多个子任务串行执行
    - 自动聚合结果
    - 生成综合总结
    - 错误处理和降级
    """
    
    name = "Task"
    description = """
将复杂任务分解为多个子任务并执行。

参数:
- subtasks: 子任务列表，每个子任务包含:
  - type: SubAgent 类型 (research/search/diagnostic)
  - prompt: 任务描述
  - priority: 优先级 (可选，默认 0)

返回:
- results: 每个子任务的执行结果
- summary: 综合总结
- subtask_count: 子任务数量

示例:
{
    "subtasks": [
        {"type": "research", "prompt": "分析项目结构"},
        {"type": "search", "prompt": "查找 main 函数"}
    ]
}
"""
    
    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """获取工具的 JSON Schema"""
        return {
            "name": "Task",
            "description": TaskTool.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "subtasks": {
                        "type": "array",
                        "description": "子任务列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["research", "search", "diagnostic"],
                                    "description": "SubAgent 类型"
                                },
                                "prompt": {
                                    "type": "string",
                                    "description": "任务描述"
                                },
                                "priority": {
                                    "type": "number",
                                    "description": "优先级（可选，默认 0）"
                                }
                            },
                            "required": ["type", "prompt"]
                        }
                    }
                },
                "required": ["subtasks"]
            }
        }
    
    @staticmethod
    def execute(
        subtasks: List[Dict[str, Any]],
        orchestrator=None,
        parallel: bool = False,  # Phase 3.2 新增
        max_concurrent: int = 5,  # Phase 3.2 新增
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        执行子任务列表（Phase 3.2 增强版）
        
        Args:
            subtasks: 子任务列表，格式:
                [
                    {"type": "research", "prompt": "调研模块 A"},
                    {"type": "search", "prompt": "查找函数 B"}
                ]
            orchestrator: Orchestrator 实例（必需）
            parallel: 是否并行执行（默认 False，Phase 3.2 新增）
            max_concurrent: 最大并发数（默认 5，Phase 3.2 新增）
            verbose: 是否输出详细日志
            
        Returns:
            {
                "success": True,
                "results": ["总结1", "总结2"],
                "summary": "综合总结",
                "subtask_count": 2,
                "failed_count": 0
            }
        """
        if verbose:
            mode = "并行" if parallel else "串行"
            logger.info(f"[TaskTool] 开始{mode}执行 {len(subtasks)} 个子任务")
        
        # 验证 orchestrator
        if not orchestrator:
            return {
                "success": False,
                "error": "未提供 Orchestrator 实例",
                "results": [],
                "summary": "",
                "subtask_count": 0,
                "failed_count": 0
            }
        
        # 验证 subtasks
        if not subtasks or not isinstance(subtasks, list):
            return {
                "success": False,
                "error": "subtasks 必须是非空列表",
                "results": [],
                "summary": "",
                "subtask_count": 0,
                "failed_count": 0
            }
        
        # 按优先级排序（可选）
        sorted_subtasks = sorted(
            subtasks,
            key=lambda x: x.get("priority", 0),
            reverse=True  # 高优先级先执行
        )
        
        # 选择执行模式
        if parallel:
            return TaskTool._execute_parallel(
                sorted_subtasks, orchestrator, max_concurrent, verbose
            )
        else:
            return TaskTool._execute_serial(
                sorted_subtasks, orchestrator, verbose
            )
    
    @staticmethod
    def _execute_serial(
        subtasks: List[Dict[str, Any]],
        orchestrator,
        verbose: bool
    ) -> Dict[str, Any]:
        """
        串行执行子任务
        
        Args:
            subtasks: 已排序的子任务列表
            orchestrator: Orchestrator 实例
            verbose: 是否输出详细日志
        
        Returns:
            执行结果字典
        """
        results = []
        failed_count = 0
        
        for i, subtask in enumerate(subtasks, 1):
            task_type = subtask.get("type")
            prompt = subtask.get("prompt")
            
            if not task_type or not prompt:
                logger.warning(f"[TaskTool] 子任务 {i} 缺少 type 或 prompt，跳过")
                failed_count += 1
                results.append(f"[错误] 子任务 {i} 格式错误")
                continue
            
            try:
                if verbose:
                    logger.info(f"[TaskTool] 执行子任务 {i}/{len(subtasks)}: {task_type} - {prompt[:50]}...")
                
                # 调用 Orchestrator 的 spawn_subagent
                summary = orchestrator.spawn_subagent(
                    agent_type=task_type,
                    prompt=prompt
                )
                
                results.append(summary)
                
                if verbose:
                    logger.info(f"[TaskTool] 子任务 {i} 完成: {summary[:80]}...")
            
            except Exception as e:
                logger.error(f"[TaskTool] 子任务 {i} 执行失败: {e}")
                failed_count += 1
                results.append(f"[错误] {str(e)}")
        
        # 生成综合总结
        summary = TaskTool._generate_summary(results, failed_count, len(subtasks))
        
        success = failed_count == 0
        
        if verbose:
            logger.info(f"[TaskTool] 所有子任务完成，成功 {len(subtasks) - failed_count}/{len(subtasks)}")
        
        return {
            "success": success,
            "results": results,
            "summary": summary,
            "subtask_count": len(subtasks),
            "failed_count": failed_count
        }
    
    @staticmethod
    def _execute_parallel(
        subtasks: List[Dict[str, Any]],
        orchestrator,
        max_concurrent: int,
        verbose: bool
    ) -> Dict[str, Any]:
        """
        并行执行子任务（Phase 3.2 新增）
        
        Args:
            subtasks: 已排序的子任务列表
            orchestrator: Orchestrator 实例
            max_concurrent: 最大并发数
            verbose: 是否输出详细日志
        
        Returns:
            执行结果字典
        """
        import asyncio
        
        async def spawn_async(subtask: Dict, index: int):
            """异步孵化 SubAgent"""
            task_type = subtask.get("type")
            prompt = subtask.get("prompt")
            
            if not task_type or not prompt:
                logger.warning(f"[TaskTool] 子任务 {index} 缺少 type 或 prompt，跳过")
                return f"[错误] 子任务 {index} 格式错误", True  # (result, is_error)
            
            try:
                if verbose:
                    logger.info(f"[TaskTool] 开始子任务 {index}/{len(subtasks)}: {task_type} - {prompt[:50]}...")
                
                # 在线程中执行（因为 spawn_subagent 是同步的）
                summary = await asyncio.to_thread(
                    orchestrator.spawn_subagent,
                    agent_type=task_type,
                    prompt=prompt
                )
                
                if verbose:
                    logger.info(f"[TaskTool] 子任务 {index} 完成: {summary[:80]}...")
                
                return summary, False  # (result, is_error)
            
            except Exception as e:
                logger.error(f"[TaskTool] 子任务 {index} 执行失败: {e}")
                return f"[错误] {str(e)}", True  # (result, is_error)
        
        async def run_all():
            """并行执行所有子任务（分批）"""
            all_results = []
            
            # 分批执行，避免并发过多
            for i in range(0, len(subtasks), max_concurrent):
                batch = subtasks[i:i + max_concurrent]
                batch_indices = range(i + 1, i + len(batch) + 1)
                
                if verbose:
                    logger.info(f"[TaskTool] 执行批次 {i // max_concurrent + 1}，包含 {len(batch)} 个子任务")
                
                # 并行执行这一批
                batch_tasks = [
                    spawn_async(task, idx)
                    for task, idx in zip(batch, batch_indices)
                ]
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                all_results.extend(batch_results)
            
            return all_results
        
        # 运行异步任务
        try:
            raw_results = asyncio.run(run_all())
        except Exception as e:
            logger.error(f"[TaskTool] 并行执行失败: {e}")
            return {
                "success": False,
                "error": f"并行执行失败: {str(e)}",
                "results": [],
                "summary": "",
                "subtask_count": len(subtasks),
                "failed_count": len(subtasks)
            }
        
        # 处理结果
        results = []
        failed_count = 0
        
        for item in raw_results:
            if isinstance(item, Exception):
                results.append(f"[错误] {str(item)}")
                failed_count += 1
            elif isinstance(item, tuple):
                result, is_error = item
                results.append(result)
                if is_error:
                    failed_count += 1
            else:
                results.append(str(item))
        
        # 生成综合总结
        summary = TaskTool._generate_summary(results, failed_count, len(subtasks))
        
        success = failed_count == 0
        
        if verbose:
            logger.info(f"[TaskTool] 并行执行完成，成功 {len(subtasks) - failed_count}/{len(subtasks)}")
        
        return {
            "success": success,
            "results": results,
            "summary": summary,
            "subtask_count": len(subtasks),
            "failed_count": failed_count
        }
    
    @staticmethod
    def _generate_summary(
        results: List[str],
        failed_count: int,
        total_count: int
    ) -> str:
        """
        生成综合总结
        
        Args:
            results: 子任务结果列表
            failed_count: 失败数量
            total_count: 总数量
            
        Returns:
            综合总结字符串
        """
        if not results:
            return "无子任务结果"
        
        # 过滤掉错误结果
        valid_results = [r for r in results if not r.startswith("[错误]")]
        
        if not valid_results:
            return f"所有 {total_count} 个子任务均失败"
        
        # 生成总结
        summary_parts = []
        
        # 添加成功率
        success_rate = (total_count - failed_count) / total_count * 100
        summary_parts.append(f"完成 {total_count} 个子任务，成功率 {success_rate:.0f}%")
        
        # 添加关键发现（取前 3 个结果的摘要）
        summary_parts.append("\n\n关键发现:")
        for i, result in enumerate(valid_results[:3], 1):
            # 截取每个结果的前 100 字符
            snippet = result[:100] + ("..." if len(result) > 100 else "")
            summary_parts.append(f"{i}. {snippet}")
        
        if len(valid_results) > 3:
            summary_parts.append(f"... 还有 {len(valid_results) - 3} 个结果")
        
        return "\n".join(summary_parts)


# 便捷函数
def execute_subtasks(
    subtasks: List[Dict[str, Any]],
    orchestrator,
    parallel: bool = False,  # Phase 3.2 新增
    max_concurrent: int = 5,  # Phase 3.2 新增
    verbose: bool = True
) -> Dict[str, Any]:
    """
    执行子任务列表（便捷函数）
    
    Args:
        subtasks: 子任务列表
        orchestrator: Orchestrator 实例
        parallel: 是否并行执行（默认 False，Phase 3.2 新增）
        max_concurrent: 最大并发数（默认 5，Phase 3.2 新增）
        verbose: 是否输出详细日志
        
    Returns:
        执行结果字典
    """
    return TaskTool.execute(
        subtasks=subtasks,
        orchestrator=orchestrator,
        parallel=parallel,
        max_concurrent=max_concurrent,
        verbose=verbose
    )
