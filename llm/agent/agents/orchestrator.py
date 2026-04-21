#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
协调者模块 (Orchestrator) - Phase 4

Multi-Agent 集群的协调者，负责：
- 创建和管理 TaskSession
- 调度各 Agent 执行任务
- 控制执行流程

注意：这是简化版本（V1），不包含重试机制
"""

import copy
import os
import re
import json
import sys
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

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


from llm.agent.core.task_session import TaskSession
from llm.agent.core.execution_state import StepStatus, TaskStatus
from llm.rag_core.llm_api import DeepSeekAPI
from llm.agent.tools.todo_write_tool import TodoWriteTool

# Phase 3.2: ResearchCache
from llm.agent.core.research_cache import get_global_cache


logger = logging.getLogger("Orchestrator")


class Orchestrator:
    """
    协调者 - 管理多 Agent 协同执行
    
    简化版本（V1）特性：
    - 创建和管理 TaskSession
    - 串行执行 Plan 步骤
    - 无重试机制
    - 基础错误处理
    
    后续版本（V2）将添加：
    - 3 次重试机制
    - 降级策略
    - 任务暂停/恢复
    
    Attributes:
        knowledge_agent: 知识代理
        memory_agent: 记忆代理（可选）
        planner: 规划代理
        coder: 编码代理
        reviewer: 审查代理
    """
    
    def __init__(
        self,
        knowledge_agent=None,
        memory_agent=None,
        planner=None,
        coder=None,
        reviewer=None,
        error_solver=None,
        tool_registry=None,
        verbose: bool = True
    ):
        """
        初始化协调者
        
        Args:
            knowledge_agent: 知识代理实例
            memory_agent: 记忆代理实例（可选）
            planner: 规划代理实例
            coder: 编码代理实例
            reviewer: 审查代理实例
            error_solver: 错误解决代理实例（V3新增）
            tool_registry: 工具注册表实例（Phase 3 新增）
            verbose: 是否输出详细日志
        """
        self.knowledge_agent = knowledge_agent
        self.memory_agent = memory_agent
        self.planner = planner
        self.coder = coder
        self.reviewer = reviewer
        self.error_solver = error_solver
        self.tool_registry = tool_registry  # Phase 3 新增
        self.verbose = verbose
        self.logger = logging.getLogger("Orchestrator")
        
        # Phase 3.2: 启用 ResearchCache
        self.research_cache = get_global_cache()
        
        # Phase 3.1: 设置 planner 的 orchestrator 引用（用于自动调研）
        if self.planner and hasattr(self.planner, 'orchestrator'):
            self.planner.orchestrator = self
        
        # 当前任务会话
        self.current_session: Optional[TaskSession] = None
        
        # V3: 任务停止标记
        self._stop_requested = False



    def execute(self, user_goal: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        执行用户请求的主入口
        """
        self._log(f"开始执行任务: {user_goal}")
        
        # 1. 创建或加载 TaskSession
        if session_id:
            session = TaskSession.load(session_id)
            if not session:
                 session = TaskSession.create(user_goal=user_goal)
        else:
            session = TaskSession.create(user_goal=user_goal)
        
        # Add user goal to history
        session.add_message("user", user_goal)

        self.current_session = session
        self._log(f"任务会话 ID: {session.task_id}")
        
        # --- Memory Feature: Load Todos ---
        # 尝试加载之前的 Todo 列表
        try:
            previous_todos = TodoWriteTool.load_todos(session.task_id)
            if previous_todos:
                session.add_message("system", f"**Restored Todo List**:\n{json.dumps(previous_todos, indent=2)}")
                self._log(f"已恢复 {len(previous_todos)} 个待办事项")
        except Exception:
            pass

        try:
            # ... (rest of the existing logic: Knowledge, Memory Agent, Planner, etc.)
            # 2. 从 KnowledgeAgent 获取知识（只调用一次）
            if self.knowledge_agent:
                self._log("获取 RAG 知识...")
                rag_knowledge = self.knowledge_agent.get_context_for_goal(user_goal)
                session.set_rag_knowledge(rag_knowledge)
                self._log(f"RAG 知识获取完成: {len(rag_knowledge.get('knowledge_items', []))} 条")
            
            # 3. 从 MemoryAgent 获取上下文（只调用一次）
            if self.memory_agent:
                self._log("获取对话上下文...")
                try:
                    context = self.memory_agent.get_relevant_context(user_goal)
                    session.set_conversation_context({"context": context})
                    self._log("对话上下文获取完成")
                except Exception as e:
                    self._log(f"获取对话上下文失败: {e}", level="warning")
            
            # 4. Planner 生成计划
            # 4.0 预扫描：从用户目标中提取路径并扫描文件结构（V3 新增）
            file_scan_result = self._scan_files_from_goal(user_goal)
            if file_scan_result.get("scanned"):
                session.set_file_structure(file_scan_result)
                self._log(f"文件结构已注入上下文: {len(file_scan_result.get('paths', []))} 个路径")
            
            if self.planner:
                self._log("Planner 生成计划...")
                session.status = TaskStatus.PLANNING
                
                planner_context = session.get_context_for_agent("planner")
                plan = self.planner.plan(user_goal, planner_context)
                
                if not plan or plan.get("error"):
                    error_msg = plan.get("error", "计划生成失败") if plan else "计划生成失败"
                    session.mark_failed(error_msg)
                    return self._build_result(session, success=False, error=error_msg)
                
                session.set_plan(plan)
                self._log(f"计划生成完成: {len(plan.get('steps', []))} 步")
            else:
                # 如果没有 Planner，创建一个简单的单步计划
                simple_plan = {
                    "plan_id": "simple_plan",
                    "goal": user_goal,
                    "steps": [
                        {
                            "step_id": 0,
                            "type": "code_change",
                            "action": "execute",
                            "target": "user_goal",
                            "description": user_goal
                        }
                    ]
                }
                session.set_plan(simple_plan)
                self._log("使用简单单步计划")
            
            # 5. 逐步执行 Plan
            if session.plan and "steps" in session.plan:
                success = self._execute_plan(session)
                if not success:
                    return self._build_result(session, success=False, error="执行失败")
            
            # 6. 任务完成
            session.mark_completed()
            self._log(f"任务完成: {session.task_id}")
            
            # --- Persistence ---
            session.save()

            return self._build_result(session, success=True)
            
        except Exception as e:
            self.logger.error(f"执行失败: {e}")
            session.mark_failed(str(e))
            session.save() # Save state even on failure
            return self._build_result(session, success=False, error=str(e))
    
    def _execute_plan(self, session: TaskSession) -> bool:
        """
        执行计划中的所有步骤
        
        简化版本：串行执行，无重试
        
        Args:
            session: 任务会话
            
        Returns:
            是否成功
        """
        steps = session.plan.get("steps", [])
        
        for step_id, step in enumerate(steps):
            session.execution_state.current_step_id = step_id
            
            success = self._execute_step(session, step_id, step)
            
            if not success:
                self._log(f"步骤 {step_id} 执行失败", level="error")
                return False
            
            # 前进到下一步
            if step_id < len(steps) - 1:
                session.advance_to_next_step()
        
        return True
    
    def _build_placeholder_map(self, session: TaskSession, step_id: int) -> Dict[str, str]:
        """
        根据之前步骤的执行结果构建占位符替换表。
        例如步骤0读取目录后，可从 content 解析出 .py 文件列表，得到 first_py_file、module_name 等。
        """
        subs: Dict[str, str] = {}
        step_results = getattr(session, "step_results", {}) or {}
        # 步骤0：通常是「读取目录」或「列出 .py 文件」
        step0 = step_results.get(0, {})
        content = step0.get("content") or step0.get("summary") or ""
        target0 = step0.get("target", "")
        if content and ("Directory listing" in content or "listing" in content.lower() or "\n" in content):
            lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
            # 跳过首行标题如 "Directory listing for xxx"
            if lines and ("directory" in lines[0].lower() or "listing" in lines[0].lower()):
                lines = lines[1:]
            py_files: List[str] = [f for f in lines if f.endswith(".py")]
            if py_files:
                # 排除 __init__.py 后的「第一个函数定义文件」更符合 Planner 的语义
                non_init = [f for f in py_files if not f.endswith("__init__.py")]
                first_py = non_init[0] if non_init else py_files[0]
                subs["<first_py_file>"] = first_py
                # Use synonyms
                subs["<first_python_file>"] = first_py
                subs["<source_file_1>"] = first_py
                
                subs["<function_file_1>"] = Path(first_py).stem
                subs["<module_name>"] = Path(first_py).stem
                if len(non_init) > 1:
                    subs["<second_py_file>"] = non_init[1]
                    subs["<function_file_2>"] = Path(non_init[1]).stem
                if len(py_files) > 1:
                    subs["<second_py_file>"] = subs.get("<second_py_file>") or py_files[1]
        return subs
    
    def _resolve_step_placeholders(self, session: TaskSession, step_id: int, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        用之前步骤的结果替换当前 step 的 target、description 中的占位符，
        如 <first_py_file>、<module_name>、<function_file_1>，避免执行时路径字面量报错。
        """
        placeholder_map = self._build_placeholder_map(session, step_id)
        if not placeholder_map:
            return step
        resolved = copy.deepcopy(step)
        for key, val in placeholder_map.items():
            if not val:
                continue
            for field in ("target", "description"):
                if field in resolved and isinstance(resolved[field], str) and key in resolved[field]:
                    resolved[field] = resolved[field].replace(key, val)
                    # Clean up double extensions if any
                    resolved[field] = resolved[field].replace(".py.py", ".py")
        # 若替换后仍有未解析的占位符（如 <first_py_file>），可打日志
        for field in ("target", "description"):
            if field in resolved and isinstance(resolved[field], str):
                remaining = re.findall(r"<[^>]+>", resolved[field])
                if remaining and self.verbose:
                    self._log(f"  占位符未解析（将按字面量执行）: {remaining}", level="warning")
        return resolved
    
    def _execute_step(self, session: TaskSession, step_id: int, step: Dict[str, Any]) -> bool:
        """
        执行单个步骤
        
        简化版本：无重试机制
        
        Args:
            session: 任务会话
            step_id: 步骤 ID
            step: 步骤定义
            
        Returns:
            是否成功
        """
        step_type = step.get("type", "code_change")
        step_desc = step.get("description", f"Step {step_id}")
        
        self._log(f"执行步骤 {step_id}: {step_desc}")
        
        # 用之前步骤的结果解析 target/description 中的占位符（如 <first_py_file>、<module_name>）
        step = self._resolve_step_placeholders(session, step_id, step)
        step_desc = step.get("description", step_desc)
        
        # 更新状态：开始执行
        session.update_state("orchestrator", "start_step", {})
        
        if step_type in ["code_change", "analysis"]:
            # Coder 执行
            if self.coder:
                coder_context = session.get_context_for_agent("coder")
                result = self.coder.execute_step(step, coder_context)
                
                if result.get("success"):
                    session.update_state("coder", "complete_step", {
                        "summary": result.get("summary", "步骤完成")
                    })
                    
                    # Reviewer 验证
                    if self.reviewer:
                        reviewer_context = session.get_context_for_agent("reviewer")
                        review = self.reviewer.review(result, reviewer_context)
                        
                        if review.get("success") or review.get("approved"):
                            session.update_state("reviewer", "complete_step", {
                                "summary": "验证通过"
                            })
                            return True
                        else:
                            session.update_state("reviewer", "fail_step", {
                                "error": review.get("error", review.get("feedback", "验证失败"))
                            })
                            return False
                    else:
                        # 没有 Reviewer，直接通过
                        return True
                else:
                    session.update_state("coder", "fail_step", {
                        "error": result.get("error", "执行失败")
                    })
                    return False
            else:
                # 没有 Coder，标记为完成
                session.update_state("orchestrator", "complete_step", {
                    "summary": f"步骤跳过（无 Coder）: {step_desc}"
                })
                return True
        
        elif step_type == "verify":
            # 直接由 Reviewer 执行
            if self.reviewer:
                reviewer_context = session.get_context_for_agent("reviewer")
                result = self.reviewer.review(step, reviewer_context)
                
                if result.get("success") or result.get("approved"):
                    session.update_state("reviewer", "complete_step", {
                        "summary": "验证通过"
                    })
                    return True
                else:
                    # 针对验证步骤，尽量提供更详细的错误信息，避免后续被归类为 unknown
                    detailed_error = result.get("error") or result.get("feedback") or result.get("summary") or "验证失败"
                    session.update_state("reviewer", "fail_step", {
                        "error": detailed_error
                    })
                    return False
            else:
                # 没有 Reviewer，直接通过
                session.update_state("orchestrator", "complete_step", {
                    "summary": f"步骤跳过（无 Reviewer）: {step_desc}"
                })
                return True
        
        else:
            # 未知步骤类型，标记为完成
            session.update_state("orchestrator", "complete_step", {
                "summary": f"步骤跳过（未知类型 {step_type}）: {step_desc}"
            })
            return True
    
    def _build_result(self, session: TaskSession, success: bool, error: str = None) -> Dict[str, Any]:
        """
        构建执行结果
        
        Args:
            session: 任务会话
            success: 是否成功
            error: 错误信息
            
        Returns:
            结果字典
        """
        result = {
            "success": success,
            "task_id": session.task_id,
            "user_goal": session.user_goal,
            "status": session.status.value,
            "summary": session.get_summary(),
            "events": session.event_log.get_all_events_summary(),
        }
        
        if error:
            result["error"] = error
        
        if session.step_results:
            result["step_results"] = session.step_results
        
        return result
    
    def _log(self, message: str, level: str = "info"):
        """
        输出日志 - 安全处理特殊字符
        
        Args:
            message: 日志消息
            level: 日志级别
        """
        if self.verbose:
            if level == "info":
                self.logger.info(message)
            elif level == "warning":
                self.logger.warning(message)
            elif level == "error":
                self.logger.error(message)
            try:
                print(f"[Orchestrator] {message}")
            except UnicodeEncodeError:
                safe_msg = message.encode('gbk', errors='replace').decode('gbk')
                print(f"[Orchestrator] {safe_msg}")
    
    def get_current_session(self) -> Optional[TaskSession]:
        """获取当前任务会话"""
        return self.current_session
    
    def _scan_files_from_goal(self, user_goal: str) -> Dict[str, Any]:
        """
        从用户目标中提取路径并扫描文件结构（V3 新增，V3.1 优化）
        
        Args:
            user_goal: 用户目标描述
            
        Returns:
            包含文件结构的字典
        """
        import re
        
        # 尝试从用户目标中提取路径（支持 Windows 和 Unix 风格）
        # V3.2: 使用更宽松的匹配，然后逐步截断找到有效路径
        path_patterns = [
            r'([A-Za-z]:[\\\/][^\s"<>|*?]+)',  # Windows (both slashes)
            r'(/[^\s"<>|*?]+)',                 # Unix
        ]
        
        candidate_paths = []
        for pattern in path_patterns:
            matches = re.findall(pattern, user_goal)
            candidate_paths.extend(matches)
        
        if not candidate_paths:
            self._log("未在用户目标中找到目录路径，跳过扫描")
            return {"scanned": False, "paths": [], "file_structure": ""}
        
        # V3.2: 对于每个候选路径，逐步截断直到找到有效路径
        # V3.3: 增加对最后一个路径部分的字符级截断（处理中文后缀）
        found_paths = []
        for candidate in candidate_paths:
            # 标准化路径分隔符
            normalized = candidate.replace("/", "\\")
            parts = normalized.split("\\")
            
            best_path = None
            
            # 从完整路径开始，逐步减少路径部分
            for i in range(len(parts), 1, -1):
                current_parts = parts[:i]
                test_path_str = "\\".join(current_parts)
                test_path = Path(test_path_str)
                
                if test_path.exists() and test_path.is_dir():
                    best_path = str(test_path)
                    break
                
                # 如果整个路径不存在，尝试逐字符截短最后一个部分
                # 这处理类似 "test_sandbox下的所有" 这种情况
                last_part = current_parts[-1]
                for j in range(len(last_part), 0, -1):
                    trimmed_last = last_part[:j]
                    trimmed_parts = current_parts[:-1] + [trimmed_last]
                    test_path_str = "\\".join(trimmed_parts)
                    test_path = Path(test_path_str)
                    if test_path.exists() and test_path.is_dir():
                        best_path = str(test_path)
                        break
                
                if best_path:
                    break
            
            if best_path:
                found_paths.append(best_path)
                self._log(f"找到有效路径: {best_path}")
        
        if not found_paths:
            self._log("未找到有效的目录路径，跳过扫描")
            return {"scanned": False, "paths": [], "file_structure": ""}
        
        scanned_paths = []
        source_files = []  # 源文件（非test_开头的.py）
        test_files = []    # 测试文件（test_开头的.py）
        
        for path_str in found_paths:
            path = Path(path_str)
            if path.exists() and path.is_dir():
                self._log(f"扫描目录: {path}")
                scanned_paths.append(str(path))
                
                # 只扫描 .py 文件
                try:
                    for py_file in sorted(path.rglob("*.py")):
                        if py_file.is_file():
                            rel_path = py_file.relative_to(path)
                            rel_path_str = str(rel_path).replace("\\", "/")  # 统一为正斜杠
                            
                            # 分类：测试文件 vs 源文件
                            if py_file.name.startswith("test_"):
                                test_files.append(rel_path_str)
                            else:
                                source_files.append(rel_path_str)
                except Exception as e:
                    self._log(f"扫描失败: {e}", level="warning")
            elif path.exists() and path.is_file():
                self._log(f"发现文件路径: {path}")
                scanned_paths.append(str(path))
        
        # 构建清晰的文件结构描述
        file_structure_lines = []
        
        if source_files:
            file_structure_lines.append("\n### 源文件（需要生成测试）")
            for f in source_files:
                file_structure_lines.append(f"- {f}")
        
        if test_files:
            file_structure_lines.append("\n### 已存在的测试文件")
            for f in test_files:
                file_structure_lines.append(f"- {f}")
        
        file_structure = "\n".join(file_structure_lines)
        self._log(f"文件扫描完成: {len(source_files)} 个源文件, {len(test_files)} 个测试文件")
        
        return {
            "scanned": True,
            "paths": scanned_paths,
            "file_structure": file_structure,
            "source_files": source_files,  # V3.1 新增：明确列出源文件
            "test_files": test_files,      # V3.1 新增：明确列出测试文件
        }
    
    # ==================== V2 新增功能 ====================
    
    def execute_with_resolution_loop(self, user_goal: str) -> Dict[str, Any]:
        """
        死磕模式执行循环 (V4 Refactored)
        
        核心逻辑：
        1. 建立 Session (一次)
        2. 生成 Plan (一次)
        3. 遍历步骤，对每个失败步骤进行死磕修复
        4. 仅当模型判定无法解决时才跳过
        """
        self._log(f"[V4] 开始执行任务（智能死磕模式）: {user_goal}")
        self._stop_requested = False
        
        # 1. 初始化 Session (原 _execute_internal 的头部逻辑)
        session = TaskSession.create(user_goal=user_goal)
        self.current_session = session
        
        # 准备环境 (RAG, Context, File Scan)
        self._prepare_session_environment(session, user_goal)
        
        # 澄清与思考
        self._run_clarification(session, user_goal)
        
        try:
            # 2. 生成计划
            if self.planner:
                session.status = TaskStatus.PLANNING
                planner_context = session.get_context_for_agent("planner")
                plan = self.planner.plan(user_goal, planner_context)
                
                if not plan or plan.get("error"):
                    raise Exception(plan.get("error", "计划生成失败") if plan else "计划生成失败")
                
                session.set_plan(plan)
                self._save_plan_files(session, plan)
            else:
                # 简单计划回退
                session.set_plan({
                    "plan_id": "simple",
                    "goal": user_goal,
                    "steps": [{"step_id": 0, "type": "code_change", "action": "execute", 
                              "target": "goal", "description": user_goal}]
                })

            # 3. 智能执行循环
            steps = session.plan.get("steps", [])
            all_errors = []        # 全局错误记录
            all_micro_plans = []   # 全局修复计划记录
            
            for step_id, step in enumerate(steps):
                if self._stop_requested:
                    self._log("[V4] 任务已停止，中断执行")
                    break
                    
                session.execution_state.current_step_id = step_id
                
                # 执行单个步骤（带死磕逻辑）
                success = self._execute_step_with_resolution(
                    session, step, step_id, all_errors, all_micro_plans
                )
                
                if not success:
                    # 如果返回 False，说明死磕也失败了（或放弃了），
                    # 检查是否被标记为 skipped，如果是则继续，否则可能需要终止
                    step_status = session.execution_state.step_statuses.get(step_id)
                    if step_status == StepStatus.SKIPPED:
                        self._log(f"[V4] 步骤 {step_id} 已跳过，继续下一步")
                        continue
                    else:
                        # 严重失败且未跳过，可能需要终止整个任务
                        self._log(f"[V4] 步骤 {step_id} 严重失败且未跳过，任务终止", level="error")
                        break
                
                # 成功，继续下一步
                if step_id < len(steps) - 1:
                    session.advance_to_next_step()

            # 4. 完成
            session.mark_completed()
            final_result = self._build_result(session, success=True)
            
            # 添加统计信息
            final_result["resolution_info"] = {
                "total_errors": len(all_errors),
                "micro_plans_executed": len(all_micro_plans)
            }
            
            # 生成最终总结
            self._generate_final_summary(session)
            return final_result
            
        except Exception as e:
            self._log(f"执行异常: {e}", level="error")
            session.mark_failed(str(e))
            self.force_summary_generation() # 即使崩了也要生成总结
            return self._build_result(session, success=False, error=str(e))

    def _execute_step_with_resolution(
        self, 
        session: TaskSession, 
        step: Dict, 
        step_id: int, 
        all_errors: List, 
        all_micro_plans: List
    ) -> bool:
        """
        对单个步骤进行"死磕"执行
        
        V4.1: 增加硬性重试上限防止无限循环
        """
        step_error_history = [] # 当前步骤的错误历史
        MAX_RETRIES = 3  # 硬性重试上限
        
        retry_count = 0
        last_error_type = None
        same_error_count = 0
        
        while retry_count < MAX_RETRIES:
            if self._stop_requested:
                return False
            
            retry_count += 1
            self._log(f"[V4] 尝试执行步骤 {step_id}（第 {retry_count}/{MAX_RETRIES} 次）")
                
            # 1. 尝试执行
            success = self._execute_step(session, step_id, step)
            
            if success:
                return True
            
            # 2. 执行失败，开始诊断
            last_error_details = session.get_last_error()
            error_msg = last_error_details.get("error", "Unknown error") if last_error_details else "Step failed"
            
            # V4.1: 检测是否是相同错误（特别是截断错误）
            current_error_type = self._classify_error_type(error_msg)

            # 特殊规则：对于纯测试验证失败（断言类错误），不进入死磕/修复循环，直接认定为失败或跳过
            if step.get("type") == "verify" and step.get("action") == "run_tests":
                if current_error_type == "assertion_error":
                    # 这是业务逻辑层面的测试未通过，让调用方在最终总结中看到具体失败原因即可
                    self._log(f"[V4] 检测到断言类测试失败（{current_error_type}），不再尝试自动修复", level="warning")
                    # 此时 session 中已经记录了 fail_step 事件和错误，无需再次更新
                    return False
            if current_error_type == last_error_type:
                same_error_count += 1
                if same_error_count >= 2:
                    self._log(f"[V4] 连续 {same_error_count} 次相同错误（{current_error_type}），强制放弃", level="warning")
                    session.update_state("orchestrator", "skip_step", {"reason": f"重复错误: {current_error_type}"})
                    session.event_log.log(
                        event_type="step_skipped",
                        agent="orchestrator",
                        step_id=step_id,
                        summary=f"步骤已跳过: 连续 {same_error_count} 次相同错误",
                        details={"error_type": current_error_type}
                    )
                    return False
            else:
                same_error_count = 1
                last_error_type = current_error_type
            
            # 记录历史
            error_record = {
                "step_id": step_id,
                "attempt": len(step_error_history) + 1,
                "error": error_msg,
                "error_type": current_error_type,
                "timestamp": datetime.now().isoformat()
            }
            step_error_history.append(error_record)
            all_errors.append(error_record)
            
            # 触发前端事件：正在修复
            session.event_log.log(
                event_type="error_resolution",
                agent="orchestrator",
                step_id=step_id,
                summary=f"步骤失败，正在分析并尝试第 {len(step_error_history)} 次修复...",
                details={"error": error_msg}
            )
            
            # 3. 调用 ErrorSolver
            if self.error_solver:
                solve_result = self.error_solver.solve_error(
                    error_log=error_msg,
                    step_info=step,
                    context={"user_goal": session.user_goal},
                    error_history=step_error_history # 传入历史
                )
                
                # 4. 检查是否放弃
                if solve_result.get("give_up"):
                    reason = solve_result.get("give_up_reason", "模型判定无法解决")
                    self._log(f"[V4] 放弃修复步骤 {step_id}: {reason}", level="warning")
                    
                    # 标记跳过
                    session.update_state("orchestrator", "skip_step", {"reason": reason})
                    session.event_log.log(
                        event_type="step_skipped",
                        agent="orchestrator",
                        step_id=step_id,
                        summary=f"步骤已跳过: {reason}",
                        details={"reason": reason}
                    )
                    return False # 返回 False 但状态是 SKIPPED
                
                # 5. 执行修复计划
                micro_plan = solve_result.get("micro_plan")
                if micro_plan:
                    session.event_log.log(
                        event_type="fix_attempt",
                        agent="orchestrator",
                        step_id=step_id,
                        summary=f"执行修复方案: {micro_plan.get('goal')}",
                        details={"plan": micro_plan}
                    )
                    all_micro_plans.append(micro_plan)
                    
                    # 执行 Micro Plan
                    fix_success = self._execute_fix_plan(micro_plan)
                    
                    if not fix_success:
                        self._log("[V4] 修复方案执行失败，继续尝试...", level="warning")
                    else:
                        self._log("[V4] 修复方案执行成功，准备重试原步骤")
                        
                    # 继续 while 循环重试原步骤
                else:
                    self._log("[V4] 未生成修复计划，简单重试", level="warning")
                    import time
                    time.sleep(1)
            else:
                self._log("[V4] 无 ErrorSolver，无法修复", level="error")
                return False
        
        # 超过最大重试次数
        self._log(f"[V4] 步骤 {step_id} 超过最大重试次数 ({MAX_RETRIES})，强制跳过", level="warning")
        session.update_state("orchestrator", "skip_step", {"reason": f"超过最大重试次数 {MAX_RETRIES}"})
        session.event_log.log(
            event_type="step_skipped",
            agent="orchestrator",
            step_id=step_id,
            summary=f"步骤已跳过: 超过最大重试次数 ({MAX_RETRIES})",
            details={"max_retries": MAX_RETRIES}
        )
        return False
    
    def _classify_error_type(self, error_msg: str) -> str:
        """分类错误类型（V4.1 新增）"""
        error_lower = error_msg.lower()
        
        if any(kw in error_lower for kw in ["截断", "truncat", "不完整", "incomplete"]):
            return "truncation"
        elif any(kw in error_lower for kw in ["syntax", "语法"]):
            return "syntax_error"
        elif any(kw in error_lower for kw in ["import", "导入", "module"]):
            return "import_error"
        elif any(kw in error_lower for kw in ["timeout", "超时"]):
            return "timeout"
        elif any(kw in error_lower for kw in ["assert", "assertionerror"]):
            return "assertion_error"
        else:
            return "unknown"

    def _prepare_session_environment(self, session, user_goal):
        """准备会话环境 (RAG, Context, etc)"""
        # 获取知识
        if self.knowledge_agent:
            rag_knowledge = self.knowledge_agent.get_context_for_goal(user_goal)
            session.set_rag_knowledge(rag_knowledge)
        
        # 获取上下文
        if self.memory_agent:
            try:
                context = self.memory_agent.get_relevant_context(user_goal)
                session.set_conversation_context({"context": context})
            except Exception:
                pass
        
        # 扫描文件
        file_scan_result = self._scan_files_from_goal(user_goal)
        if file_scan_result.get("scanned"):
            session.set_file_structure(file_scan_result)

    def _run_clarification(self, session, user_goal):
        """运行澄清逻辑"""
        self._log("生成澄清与简洁思考...")
        session.update_state("orchestrator", "thinking", {})
        
        try:
            clarification = self._generate_clarification(user_goal)
            session.event_log.log(
                event_type="thought",
                agent="orchestrator",
                step_id=-1,
                summary=clarification,
                details={"thought": clarification}
            )
            session.shared_context["clarification"] = clarification
        except Exception as e:
            self._log(f"生成思考失败: {e}", level="warning")

    def force_summary_generation(self):
        """强制生成当前状态的总结（无论成功失败）"""
        if not self.current_session:
            return
            
        try:
            self._log("生成最终总结 (Guaranteed Summary)...")
            
            # 收集所有已发生事件的摘要
            status_summary = self.current_session.execution_state.get_status_summary()
            events_summary = self.current_session.event_log.get_all_events_summary()
            
            summary_prompt = f"""任务汇报请求 (Final Report)

用户目标: {self.current_session.user_goal}

当前状态:
{status_summary}

执行记录摘要:
{events_summary}

请生成一份客观、详细的任务执行总结。
如果任务失败或被停止，请明确指出卡在哪里，以及已经尝试了哪些修复。
如果是死磕模式，请说明尝试了多少轮。

要求：中文回复，重点突出结果和遇到的问题。"""

            api = DeepSeekAPI()
            messages = [{"role": "user", "content": summary_prompt}]
            # 使用较短超时防卡死
            response = api.chat(messages, temperature=0.3, max_tokens=1000, timeout=60)
            
            content = "任务结束。"
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0]["message"]["content"].strip()
            
            # 记录到事件日志
            self.current_session.event_log.log(
                event_type="final_summary",
                agent="orchestrator",
                step_id=-1,
                summary=content,
                details={"summary": content, "forced": True}
            )
            self._log("最终总结已生成并记录")
            
        except Exception as e:
            self._log(f"强制生成总结失败: {e}", level="error")
            # 最后的最后，写死一个总结
            try:
                self.current_session.event_log.log(
                    event_type="final_summary",
                    agent="orchestrator",
                    step_id=-1,
                    summary="系统强制停止，无法生成详细总结。",
                    details={"error": str(e)}
                )
            except:
                pass
    
    def _execute_fix_plan(self, micro_plan: Dict[str, Any]) -> bool:
        """执行修复小计划"""
        try:
            # 创建临时会话用于执行修复
            fix_session = TaskSession.create(
                user_goal=micro_plan.get("goal", "Error Fix"),
                task_id=f"fix_{uuid.uuid4().hex[:6]}"
            )
            # 使用现有会话的上下文
            if self.current_session:
                fix_session.rag_knowledge = self.current_session.rag_knowledge
                fix_session.conversation_context = self.current_session.conversation_context
                fix_session.file_structure = self.current_session.file_structure
            
            fix_session.set_plan(micro_plan)
            
            self._log(f"[V3] 开始执行修复计划: {micro_plan.get('goal')}")
            success = self._execute_plan_v2(fix_session)
            
            # 记录修复日志到当前主会话（如果有）
            if self.current_session:
                self.current_session.event_log.log(
                    event_type="fix_execution",
                    agent="orchestrator",
                    step_id=self.current_session.execution_state.current_step_id,
                    summary=f"执行修复计划: {'成功' if success else '失败'}",
                    details={"plan_id": micro_plan.get("plan_id"), "success": success}
                )
            return success
        except Exception as e:
            self._log(f"修复计划执行异常: {e}", level="error")
            return False
    
    def spawn_subagent(self, agent_type: str, prompt: str) -> str:
        """
        孵化子代理 (Phase 3 新增)
        
        创建一个独立上下文的 SubAgent 来执行特定任务，执行完成后只返回简洁总结。
        
        特点：
        - 独立的消息历史（不污染主 Agent）
        - 受限的工具集（只能使用特定工具）
        - 一次性执行（返回简洁总结）
        - 可以继承父 Session 的 RAG 知识
        
        Args:
            agent_type: SubAgent 类型 (research/search/diagnostic)
            prompt: 任务描述
            
        Returns:
            简洁的总结（不超过 200 字）
            
        Example:
            >>> summary = orchestrator.spawn_subagent(
            ...     agent_type="research",
            ...     prompt="找到项目中所有的 Agent 类定义"
            ... )
            >>> print(summary)
            "找到 5 个 Agent 类: PlannerAgent (line 114), CoderAgent (line 111), ..."
        """
        if not self.tool_registry:
            self._log("未配置 tool_registry，无法孵化 SubAgent", level="warning")
            return "错误: 未配置工具注册表"
        
        try:
            # 导入 SubAgent
            from llm.agent.core.subagent import SubAgent
            
            # 创建 SubAgent
            subagent = SubAgent(
                agent_type=agent_type,
                prompt=prompt,
                tool_registry=self.tool_registry,
                parent_session=self.current_session,
                verbose=self.verbose
            )
            
            self._log(f"[SubAgent] 孵化 {agent_type} 类型的 SubAgent: {prompt[:50]}...")
            
            # 执行
            summary = subagent.run()
            
            # 记录到主 Session（只记录总结）
            if self.current_session:
                self.current_session.event_log.log(
                    event_type="subagent_complete",
                    agent=f"subagent_{agent_type}",
                    summary=f"[{agent_type}] {summary[:100]}",
                    details={
                        "agent_type": agent_type,
                        "prompt": prompt[:100],
                        "summary": summary
                    }
                )
            
            self._log(f"[SubAgent] 执行完成: {summary[:80]}...")
            return summary
        
        except Exception as e:
            self._log(f"[SubAgent] 执行失败: {e}", level="error")
            return f"SubAgent 执行失败: {str(e)}"


    def _execute_internal(self, user_goal: str) -> Dict[str, Any]:
        """
        内部执行方法（可被重试）
        
        与 execute() 类似，但抛出异常而非捕获
        """
        # 1. 创建 TaskSession
        session = TaskSession.create(user_goal=user_goal)
        self.current_session = session
        
        # 2. 获取知识
        if self.knowledge_agent:
            rag_knowledge = self.knowledge_agent.get_context_for_goal(user_goal)
            session.set_rag_knowledge(rag_knowledge)
        
        # 3. 获取上下文
        if self.memory_agent:
            try:
                context = self.memory_agent.get_relevant_context(user_goal)
                session.set_conversation_context({"context": context})
            except Exception:
                pass  # 忽略上下文获取失败
        
        # 3.5 预扫描文件结构（V3.3 新增 - 生产环境路径）
        file_scan_result = self._scan_files_from_goal(user_goal)
        if file_scan_result.get("scanned"):
            session.set_file_structure(file_scan_result)
            self._log(f"[V2] 文件结构已注入: {len(file_scan_result.get('source_files', []))} 个源文件")
        
        # 3.8 生成澄清与简洁思考（新交互核心）
        self._log("生成澄清与简洁思考...")
        session.update_state("orchestrator", "thinking", {}) # 更新状态为思考中
        
        try:
            clarification = self._generate_clarification(user_goal)
            session.event_log.log(
                event_type="thought",
                agent="orchestrator",
                step_id=-1,
                summary=clarification,
                details={"thought": clarification}
            )
            self._log(f"思考内容: {clarification}")
            # 将思考内容注入 Planner 上下文
            session.shared_context["clarification"] = clarification
        except Exception as e:
            self._log(f"生成思考失败: {e}", level="warning")

        # 4. 生成计划
        if self.planner:
            session.status = TaskStatus.PLANNING
            planner_context = session.get_context_for_agent("planner")
            plan = self.planner.plan(user_goal, planner_context)
            
            if not plan or plan.get("error"):
                raise Exception(plan.get("error", "计划生成失败") if plan else "计划生成失败")
            
            session.set_plan(plan)
            
            # 4.1 保存 plan.md 和 workflow.md
            self._save_plan_files(session, plan)

        else:
            # 简单计划
            session.set_plan({
                "plan_id": "simple",
                "goal": user_goal,
                "steps": [{"step_id": 0, "type": "code_change", "action": "execute", 
                          "target": "goal", "description": user_goal}]
            })
        
        # 5. 执行步骤（带重试逻辑）
        success = self._execute_plan_v2(session)
        
        if not success:
            raise Exception(f"执行失败: {session.errors[-1]['error'] if session.errors else '未知'}")
        
        # 6. 生成最终总结
        self._generate_final_summary(session)
        
        # 7. 完成
        session.mark_completed()
        return self._build_result(session, success=True)
    
    def _execute_plan_v2(self, session: TaskSession) -> bool:
        """
        V2 版本的计划执行（支持单步重试）
        """
        steps = session.plan.get("steps", [])
        
        for step_id, step in enumerate(steps):
            session.execution_state.current_step_id = step_id
            
            # 单步最多重试 2 次
            step_success = False
            for attempt in range(3):
                success = self._execute_step(session, step_id, step)
                if success:
                    step_success = True
                    break
                else:
                    if attempt < 2:
                        session.update_state("orchestrator", "retry_step", {
                            "reason": f"步骤失败，第 {attempt + 1} 次重试"
                        })
                        self._log(f"步骤 {step_id} 失败，重试 {attempt + 1}/2")
            
            if not step_success:
                return False
            
            if step_id < len(steps) - 1:
                session.advance_to_next_step()
        
        return True
    
    def _fallback_simplify(self, error, context) -> Optional[Dict]:
        """降级策略1：简化任务"""
        self._log("[降级] 尝试简化任务...")
        
        if context and "user_goal" in context:
            # 尝试只执行第一步
            try:
                session = TaskSession.create(user_goal=f"[简化] {context['user_goal']}")
                session.set_plan({
                    "plan_id": "simplified",
                    "goal": context["user_goal"],
                    "steps": [{"step_id": 0, "type": "analysis", "action": "read_file",
                              "target": ".", "description": "简化分析"}]
                })
                session.mark_completed()
                return {"simplified": True, "summary": "任务已简化执行"}
            except Exception:
                pass
        
        return None
    
    def _fallback_partial(self, error, context) -> Optional[Dict]:
        """降级策略3：返回部分结果"""
        self._log("[降级] 返回部分结果...")
        
        if self.current_session:
            session = self.current_session
            completed = sum(1 for s in session.execution_state.step_statuses.values() 
                           if s == StepStatus.COMPLETED)
            
            if completed > 0:
                return {
                    "partial": True,
                    "completed_steps": completed,
                    "total_steps": session.execution_state.total_steps,
                    "step_results": session.step_results
                }
        
        return None



    def _generate_clarification(self, user_goal: str) -> str:
        """
        生成用户需求的澄清与简洁思考
        """
        prompt = f"""你是一个智能编程助手。用户提出了一个需求：
"{user_goal}"

请你：
1. 用一句话澄清/复述用户的核心意图。
2. 用非常简洁的语言（不超过3句）描述你的思考过程或解决思路。
3. 语调专业、自信、简洁。
4. 只返回文字内容，不要包含 markdown 标题。
"""
        # V4: 优先复用 Planner 的 API 实例，避免重复创建连接
        api = None
        if self.planner and hasattr(self.planner, "_get_llm_api"):
             api = self.planner._get_llm_api()
        elif self.error_solver and hasattr(self.error_solver, "api"):
             api = self.error_solver.api
        else:
             api = DeepSeekAPI()

        messages = [{"role": "user", "content": prompt}]
        try:
            response = api.chat(messages, temperature=0.3, max_tokens=500)
            if "choices" in response and len(response["choices"]) > 0:
                return response["choices"][0]["message"]["content"].strip()
            return "正在思考如何处理您的请求..."
        except Exception as e:
            self._log(f"LLM 调用失败: {e}", level="warning")
            return "收到您的请求，正在准备执行计划..."

    def _save_plan_files(self, session: TaskSession, plan: Dict[str, Any]):
        """
        保存 plan.md 和 workflow.md 到工作区
        """
        import os
        workspace_root = os.environ.get("WORKSPACE_ROOT")
        if not workspace_root:
            self._log("未设置 WORKSPACE_ROOT，跳过文件保存", level="warning")
            return
            
        plans_dir = Path(workspace_root) / ".agent" / "plans"
        try:
            plans_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成 plan.md
            plan_md = f"# 执行计划: {plan.get('goal')}\n\n"
            plan_md += f"**ID:** {plan.get('plan_id')}\n"
            plan_md += f"**Analysis:** {plan.get('analysis', '')}\n\n"
            plan_md += "## 步骤\n"
            for step in plan.get("steps", []):
                plan_md += f"- [ ] **Step {step.get('step_id')}:** {step.get('description')}\n"
                plan_md += f"  - Type: `{step.get('type')}`\n"
                plan_md += f"  - Action: `{step.get('action')}`\n"
                plan_md += f"  - Target: `{step.get('target')}`\n\n"
                
            (plans_dir / "plan.md").write_text(plan_md, encoding="utf-8")
            
            # 生成 workflow.md (简化版主要步骤)
            workflow_md = f"# 工作流: {plan.get('goal')}\n\n"
            workflow_md += "```mermaid\ngraph TD\n"
            workflow_md += "    Start([开始]) --> S0\n"
            steps = plan.get("steps", [])
            for i, step in enumerate(steps):
                safe_desc = step.get('description', '').replace('"', "'").replace('(', '').replace(')', '')[:20]
                workflow_md += f'    S{i}["{i}. {safe_desc}"]\n'
                if i < len(steps) - 1:
                    workflow_md += f"    S{i} --> S{i+1}\n"
            if steps:
                 workflow_md += f"    S{len(steps)-1} --> End([结束])\n"
            else:
                 workflow_md += "    Start --> End([结束])\n"
            workflow_md += "```\n"
            
            (plans_dir / "workflow.md").write_text(workflow_md, encoding="utf-8")
            
            # 记录事件
            session.event_log.log(
                event_type="files_generated",
                agent="orchestrator",
                step_id=-1,
                summary="已生成计划文件",
                details={
                    "files": [
                        {"name": "plan.md", "path": str(plans_dir / "plan.md")},
                        {"name": "workflow.md", "path": str(plans_dir / "workflow.md")}
                    ]
                }
            )
            self._log(f"计划文件已保存到: {plans_dir}")
            
        except Exception as e:
            self._log(f"保存计划文件失败: {e}", level="error")

    def _generate_final_summary(self, session: TaskSession):
        """生成最终总结 - 包含实际执行结果"""
        try:
            # 收集执行日志
            step_results = []
            for evt in session.event_log.events:
                if evt.event_type == "step_complete":
                    step_results.append(f"- [完成] {evt.summary}")
                elif evt.event_type == "step_fail":
                    step_results.append(f"- [失败] {evt.summary}")
                elif evt.event_type == "step_start":
                    # 如果没有对应的 complete/fail，说明卡住了
                    pass
            
            # 检查是否有未完成的步骤
            started_steps = [e for e in session.event_log.events if e.event_type == "step_start"]
            completed_steps = [e for e in session.event_log.events if e.event_type in ["step_complete", "step_fail"]]
            
            if len(started_steps) > len(completed_steps):
                step_results.append(f"- [未完成] 有 {len(started_steps) - len(completed_steps)} 个步骤未能完成执行")
            
            execution_log = "\n".join(step_results) if step_results else "无步骤执行记录"
            
            summary_prompt = f"""用户目标: {session.user_goal}

执行记录:
{execution_log}

请生成一个详细的任务总结，包括：
1. 用户的原始需求是什么
2. 实际完成了哪些步骤
3. 每个步骤的具体结果或输出
4. 如果有失败或未完成的步骤，需要明确指出

请用中文回复，语调专业、实事求是。如果有步骤未完成，不要说任务成功。"""
            
            api = DeepSeekAPI()
            messages = [{"role": "user", "content": summary_prompt}]
            response = api.chat(messages, temperature=0.3, max_tokens=800)
            content = "任务已完成。"
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0]["message"]["content"].strip()
            
            session.event_log.log(
                event_type="final_summary",
                agent="orchestrator",
                step_id=-1,
                summary=content,
                details={"summary": content}
            )
        except Exception as e:
            self._log(f"生成总结失败: {e}", level="warning")
    
    def _generate_error_summary(
        self, 
        all_errors: list, 
        all_micro_plans: list, 
        user_goal: str
    ):
        """
        生成错误总结（任务失败时调用）
        
        Args:
            all_errors: 所有错误记录列表
            all_micro_plans: 所有生成的小计划列表
            user_goal: 用户目标
        """
        try:
            # 构建错误摘要
            error_lines = []
            for i, err in enumerate(all_errors):
                step_desc = ""
                if err.get("step"):
                    step_desc = f" (步骤: {err['step'].get('description', '未知')[:50]})"
                error_lines.append(f"- 尝试 {err['attempt']}: {err['error'][:200]}{step_desc}")
            
            error_log = "\n".join(error_lines) if error_lines else "无错误记录"
            
            # 构建诊断摘要
            diagnosis_lines = []
            for i, mp in enumerate(all_micro_plans):
                if mp.get("original_error"):
                    diagnosis = mp["original_error"].get("quick_diagnosis", "未知")
                    solution = mp.get("solution", "无")[:100]
                    diagnosis_lines.append(f"- 诊断 {i+1}: {diagnosis} | 方案: {solution}")
            
            diagnosis_log = "\n".join(diagnosis_lines) if diagnosis_lines else "无诊断记录"
            
            summary_prompt = f"""用户目标: {user_goal}

任务执行失败。请根据以下错误信息生成一个简洁但有用的失败总结。

错误记录:
{error_log}

诊断与尝试的解决方案:
{diagnosis_log}

请生成一个简洁的任务失败总结，包括：
1. 用户的原始需求是什么
2. 任务失败的主要原因
3. 尝试了哪些修复方案（如果有）
4. 建议用户可以尝试的下一步操作

语调专业、实事求是。不要粉饰失败，直接说明问题所在。"""
            
            api = DeepSeekAPI()
            messages = [{"role": "user", "content": summary_prompt}]
            response = api.chat(messages, temperature=0.3, max_tokens=800)
            content = "任务执行失败，请查看错误日志了解详情。"
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0]["message"]["content"].strip()
            
            if self.current_session:
                self.current_session.event_log.log(
                    event_type="final_summary",
                    agent="orchestrator",
                    step_id=-1,
                    summary=content,
                    details={
                        "summary": content,
                        "status": "failed",
                        "total_errors": len(all_errors),
                        "diagnoses_attempted": len(all_micro_plans)
                    }
                )
                self.current_session.mark_failed("任务执行失败，详见总结")
                
        except Exception as e:
            self._log(f"生成错误总结失败: {e}", level="warning")
            # 即使生成失败，也要记录一个基本总结
            if self.current_session:
                self.current_session.event_log.log(
                    event_type="final_summary",
                    agent="orchestrator",
                    step_id=-1,
                    summary=f"任务失败: 共尝试 {len(all_errors)} 次，最后错误: {all_errors[-1]['error'][:200] if all_errors else '未知'}",
                    details={"status": "failed"}
                )
    
    def _build_result(self, session: TaskSession, success: bool, error: str = None) -> Dict[str, Any]:
        """构建返回结果"""
        result = {
            "success": success,
            "task_id": session.task_id,
            "status": session.status.value,
            "summary": session.get_summary()
        }
        if error:
            result["error"] = error
        return result

    def request_stop(self):
        """请求停止当前任务"""
        self._stop_requested = True
        self._log("[V3] 收到停止请求")


# 便捷函数
def create_orchestrator(
    knowledge_agent=None,
    memory_agent=None,
    planner=None,
    coder=None,
    reviewer=None,
    error_solver=None,
    tool_registry=None,
    verbose: bool = True
) -> Orchestrator:
    """
    创建协调者
    
    Args:
        knowledge_agent: 知识代理
        memory_agent: 记忆代理
        planner: 规划代理
        coder: 编码代理
        reviewer: 审查代理
        error_solver: 错误解决代理（V3新增）
        tool_registry: 工具注册表（Phase 3 新增）
        verbose: 是否详细输出
        
    Returns:
        Orchestrator 实例
    """
    return Orchestrator(
        knowledge_agent=knowledge_agent,
        memory_agent=memory_agent,
        planner=planner,
        coder=coder,
        reviewer=reviewer,
        error_solver=error_solver,
        tool_registry=tool_registry,
        verbose=verbose
    )


    