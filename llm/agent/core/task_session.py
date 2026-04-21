#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
任务会话模块 (Task Session) - Phase 4

管理单个复杂任务的完整生命周期：
- 缓存静态信息（RAG 知识、对话上下文）
- 追踪动态状态（ExecutionState）
- 记录执行事件（EventLog）
- 为各 Agent 生成定制化上下文

核心思想：
- 一个用户请求 → 一个 TaskSession
- TaskSession 维护所有状态，Orchestrator 只负责调度
- 减少重复的上下文构建
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

from .execution_state import ExecutionState, EventLog, StepStatus, TaskStatus


@dataclass
class TaskSession:
    """
    任务会话 - 管理单个复杂任务的完整生命周期
    
    核心职责：
    1. 缓存静态信息（RAG 知识）
    2. 追踪动态状态（ExecutionState）
    3. 记录执行事件（EventLog）
    4. 为各 Agent 生成定制化上下文
    
    Attributes:
        task_id: 任务唯一标识
        user_goal: 用户目标描述
        rag_knowledge: 从 KnowledgeAgent 获取的静态知识（缓存）
        conversation_context: 从 MemoryAgent 获取的对话上下文（缓存）
        plan: 由 Planner 生成的执行计划
        execution_state: 实时执行状态
        event_log: 事件日志
        step_results: 各步骤的执行结果
        shared_context: 共享上下文（所有 Agent 可访问）
    """
    
    task_id: str
    user_goal: str
    
    # 静态信息（任务开始时获取，不变）
    rag_knowledge: Dict[str, Any] = field(default_factory=dict)
    conversation_context: Dict[str, Any] = field(default_factory=dict)
    
    # 动态状态
    status: TaskStatus = TaskStatus.PENDING
    plan: Optional[Dict[str, Any]] = None
    execution_state: ExecutionState = field(default_factory=ExecutionState)
    event_log: EventLog = field(default_factory=EventLog)
    
    # 步骤结果缓存（按需查询，不全部传递）
    step_results: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    
    # 共享上下文（所有 Agent 可访问）
    shared_context: Dict[str, Any] = field(default_factory=dict)
    
    # V3 新增：文件结构信息（由 Orchestrator 扫描后注入）
    file_structure: Dict[str, Any] = field(default_factory=dict)
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # 错误记录
    errors: List[Dict[str, Any]] = field(default_factory=list)

    # 聊天历史 (Phase 2 Memory)
    messages: List[Dict[str, str]] = field(default_factory=list)
    
    @classmethod
    def _get_session_dir(cls) -> "Path":
        from pathlib import Path
        path = Path.home() / ".create_graph" / "sessions"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def load(cls, session_id: str) -> Optional["TaskSession"]:
        """
        Load session by ID from default storage
        """
        try:
            path = cls._get_session_dir() / f"{session_id}.json"
            if not path.exists():
                print(f"[TaskSession] File not found: {path}")
                return None
            return cls.load_checkpoint(str(path))
        except Exception as e:
            print(f"[TaskSession] Load failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def save(self):
        """
        Save session to default storage
        """
        path = self._get_session_dir() / f"{self.task_id}.json"
        self.save_checkpoint(str(path))

    def add_message(self, role: str, content: str):
        """Add message to history"""
        self.messages.append({"role": role, "content": content})
        self.updated_at = datetime.now()
    
    @classmethod
    def create(cls, user_goal: str, task_id: str = None) -> "TaskSession":
        """
        创建新的任务会话
        
        Args:
            user_goal: 用户目标描述
            task_id: 任务 ID（可选，自动生成）
            
        Returns:
            TaskSession 实例
        """
        if task_id is None:
            task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        
        return cls(task_id=task_id, user_goal=user_goal)
    
    @classmethod
    def create_lightweight(
        cls,
        user_goal: str,
        parent_session: Optional["TaskSession"] = None,
        task_id: str = None
    ) -> "TaskSession":
        """
        创建轻量级任务会话（用于 SubAgent）
        
        特点：
        - 独立的消息历史（空历史）
        - 可以继承父 Session 的 RAG 知识
        - 不继承对话历史和执行状态
        
        Args:
            user_goal: 用户目标描述
            parent_session: 父 Session（可选）
            task_id: 任务 ID（可选，自动生成）
            
        Returns:
            轻量级 TaskSession 实例
        """
        if task_id is None:
            task_id = f"subagent_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        
        session = cls(task_id=task_id, user_goal=user_goal)
        
        # 继承父 Session 的 RAG 知识（如果有）
        if parent_session:
            session.set_rag_knowledge(parent_session.rag_knowledge)
            # 可选：继承文件结构信息
            if parent_session.file_structure:
                session.set_file_structure(parent_session.file_structure)
        
        return session

    
    def set_rag_knowledge(self, knowledge: Dict[str, Any]):
        """
        设置 RAG 知识（缓存）
        
        Args:
            knowledge: 从 KnowledgeAgent 获取的知识
        """
        self.rag_knowledge = knowledge
        self.updated_at = datetime.now()
    
    def set_conversation_context(self, context: Dict[str, Any]):
        """
        设置对话上下文（缓存）
        
        Args:
            context: 从 MemoryAgent 获取的上下文
        """
        self.conversation_context = context
        self.updated_at = datetime.now()
    
    def set_file_structure(self, file_scan_result: Dict[str, Any]):
        """
        设置文件结构信息（V3 新增）
        
        Args:
            file_scan_result: 由 Orchestrator._scan_files_from_goal 生成的结果
        """
        self.file_structure = file_scan_result
        self.updated_at = datetime.now()
    
    def set_plan(self, plan: Dict[str, Any]):
        """
        设置执行计划
        
        Args:
            plan: 由 Planner 生成的计划
        """
        self.plan = plan
        self.execution_state.total_steps = len(plan.get("steps", []))
        self.status = TaskStatus.EXECUTING
        self.updated_at = datetime.now()
        
        # 记录事件（含计划内容，供前端公屏展示）
        self.event_log.log(
            event_type="plan_created",
            agent="planner",
            step_id=0,
            summary=f"生成计划，共 {self.execution_state.total_steps} 步",
            details={"plan_id": plan.get("plan_id", "unknown"), "plan": plan}
        )
    
    def get_context_for_agent(self, agent_type: str) -> Dict[str, Any]:
        """
        为特定 Agent 生成上下文
        
        关键优化：
        1. 静态信息：直接从缓存读取
        2. 动态状态：只传递压缩的状态摘要
        3. 历史事件：只传递相关的、筛选后的事件
        
        Args:
            agent_type: Agent 类型 (planner, coder, reviewer, orchestrator)
            
        Returns:
            定制化的上下文字典
        """
        current_step = self.execution_state.current_step_id
        
        # 基础上下文（所有 Agent 共享）
        base_context = {
            "task_id": self.task_id,
            "user_goal": self.user_goal,
            "current_status": self.execution_state.get_status_summary(),  # 压缩的状态
            "shared_context": self.shared_context,
        }
        
        if agent_type == "planner":
            return {
                **base_context,
                "rag_knowledge": self.rag_knowledge,
                "conversation_context": self.conversation_context,
                "file_structure": self.file_structure,  # V3 新增
                "execution_history": self.event_log.generate_context_summary("planner", current_step),
            }
        
        elif agent_type == "coder":
            step = {}
            if self.plan and "steps" in self.plan:
                steps = self.plan["steps"]
                if 0 <= current_step < len(steps):
                    step = steps[current_step]
            # 供 Coder 解析占位符：之前步骤的结果（如步骤0的目录列表）
            previous_step_results = {
                i: self.step_results[i]
                for i in range(current_step)
                if i in self.step_results
            }
            return {
                **base_context,
                "step": step,
                "step_results": previous_step_results,
                "rag_knowledge": self._get_relevant_rag(step),  # 只获取相关的 RAG
                "execution_context": self.event_log.generate_context_summary("coder", current_step),
            }
        
        elif agent_type == "reviewer":
            step = {}
            if self.plan and "steps" in self.plan:
                steps = self.plan["steps"]
                if 0 <= current_step < len(steps):
                    step = steps[current_step]
            
            return {
                **base_context,
                "step": step,
                "coder_result": self.step_results.get(current_step, {}),
                "execution_context": self.event_log.generate_context_summary("reviewer", current_step),
            }
        
        elif agent_type == "orchestrator":
            return {
                **base_context,
                "plan": self.plan,
                "progress": self.execution_state.get_progress_percentage(),
                "all_events": self.event_log.get_all_events_summary(),
            }
        
        return base_context
    
    def get_last_error(self) -> Optional[Dict[str, Any]]:
        """获取最近一次错误"""
        if not self.errors:
            return None
        return self.errors[-1]

    def _get_relevant_rag(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取与当前步骤相关的 RAG 知识
        
        Args:
            step: 当前步骤
            
        Returns:
            相关的 RAG 知识
        """
        # 简单实现：返回全部知识
        # TODO: 后续可以根据 step 的 target 筛选相关知识
        return self.rag_knowledge
    
    def update_state(self, agent: str, action: str, result: Dict[str, Any] = None):
        """
        更新执行状态
        
        在每个 Agent 执行后调用
        
        Args:
            agent: 执行的 Agent 类型
            action: 动作类型 (start_step, complete_step, fail_step, retry_step)
            result: 执行结果
        """
        result = result or {}
        step_id = self.execution_state.current_step_id
        step_desc = ""
        if self.plan and "steps" in self.plan:
            steps = self.plan["steps"]
            if 0 <= step_id < len(steps):
                step_desc = steps[step_id].get("description", f"Step {step_id}")
        
        if action == "start_step":
            self.execution_state.current_step_status = StepStatus.IN_PROGRESS
            self.execution_state.current_agent = agent
            self.execution_state.last_action_summary = f"开始执行 {step_desc}"
            self.execution_state.update_step_status(step_id, StepStatus.IN_PROGRESS)
            self.event_log.log(
                event_type="step_start",
                agent=agent,
                step_id=step_id,
                summary=f"开始 {step_desc}"
            )
        
        elif action == "complete_step":
            self.execution_state.current_step_status = StepStatus.COMPLETED
            summary = result.get("summary", "步骤完成")
            self.execution_state.last_action_summary = f"完成 {step_desc}: {summary}"
            self.execution_state.update_step_status(step_id, StepStatus.COMPLETED)
            self.step_results[step_id] = result
            self.event_log.log(
                event_type="step_complete",
                agent=agent,
                step_id=step_id,
                summary=summary,
                details=result
            )
        
        elif action == "fail_step":
            self.execution_state.current_step_status = StepStatus.FAILED
            error = result.get("error", "未知错误")
            self.execution_state.last_action_summary = f"{step_desc} 失败: {error}"
            self.execution_state.update_step_status(step_id, StepStatus.FAILED)
            self.errors.append({
                "step_id": step_id,
                "error": error,
                "timestamp": datetime.now().isoformat()
            })
            self.event_log.log(
                event_type="step_fail",
                agent=agent,
                step_id=step_id,
                summary=error,
                details=result
            )
        
        elif action == "retry_step":
            self.execution_state.current_step_status = StepStatus.RETRYING
            self.execution_state.retry_count += 1
            reason = result.get("reason", "")
            self.execution_state.retry_reason = reason
            self.execution_state.update_step_status(step_id, StepStatus.RETRYING)
            self.event_log.log(
                event_type="retry",
                agent=agent,
                step_id=step_id,
                summary=f"重试 (第 {self.execution_state.retry_count} 次): {reason}"
            )
        
        elif action == "thinking":
            self.execution_state.current_step_status = StepStatus.THINKING
            self.execution_state.current_agent = agent
            self.execution_state.last_action_summary = "正在思考..."
            # Event is logged by Orchestrator
            
        elif action == "skip_step":
            self.execution_state.current_step_status = StepStatus.SKIPPED
            reason = result.get("reason", "未知原因")
            self.execution_state.last_action_summary = f"步骤已跳过: {reason}"
            self.execution_state.update_step_status(step_id, StepStatus.SKIPPED)
            # Event is logged by Orchestrator
        
        self.updated_at = datetime.now()
    
    def advance_to_next_step(self):
        """前进到下一个步骤"""
        self.execution_state.current_step_id += 1
        self.execution_state.current_step_status = StepStatus.PENDING
        self.execution_state.retry_count = 0
        self.execution_state.retry_reason = None
        self.updated_at = datetime.now()
    
    def is_completed(self) -> bool:
        """检查任务是否完成"""
        if not self.plan or "steps" not in self.plan:
            return False
        total_steps = len(self.plan["steps"])
        completed_steps = sum(
            1 for s in self.execution_state.step_statuses.values() 
            if s == StepStatus.COMPLETED or s == StepStatus.SKIPPED
        )
        return completed_steps >= total_steps
    
    def is_failed(self) -> bool:
        """检查任务是否失败"""
        return self.status == TaskStatus.FAILED
    
    def mark_completed(self):
        """标记任务完成"""
        self.status = TaskStatus.COMPLETED
        self.updated_at = datetime.now()
        self.event_log.log(
            event_type="task_complete",
            agent="orchestrator",
            step_id=-1,
            summary=f"任务完成，共 {len(self.event_log)} 个事件"
        )
    
    def mark_failed(self, reason: str):
        """标记任务失败"""
        self.status = TaskStatus.FAILED
        self.updated_at = datetime.now()
        self.event_log.log(
            event_type="task_fail",
            agent="orchestrator",
            step_id=-1,
            summary=f"任务失败: {reason}"
        )
    
    def get_summary(self) -> Dict[str, Any]:
        """获取任务摘要"""
        return {
            "task_id": self.task_id,
            "user_goal": self.user_goal,
            "status": self.status.value,
            "progress": self.execution_state.get_progress_percentage(),
            "total_steps": self.execution_state.total_steps,
            "completed_steps": sum(
                1 for s in self.execution_state.step_statuses.values() 
                if s == StepStatus.COMPLETED
            ),
            "failed_steps": sum(
                1 for s in self.execution_state.step_statuses.values() 
                if s == StepStatus.FAILED
            ),
            "total_events": len(self.event_log),
            "errors": len(self.errors),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于持久化）"""
        return {
            "task_id": self.task_id,
            "user_goal": self.user_goal,
            "status": self.status.value,
            "rag_knowledge": self.rag_knowledge,
            "conversation_context": self.conversation_context,
            "plan": self.plan,
            "execution_state": self.execution_state.to_dict(),
            "event_log": self.event_log.to_dict(),
            "step_results": self.step_results,
            "shared_context": self.shared_context,
            "errors": self.errors,
            "messages": self.messages,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskSession":
        """
        从字典恢复 TaskSession
        
        Args:
            data: 字典数据
            
        Returns:
            TaskSession 实例
        """
        session = cls(
            task_id=data["task_id"],
            user_goal=data["user_goal"]
        )
        
        # 恢复状态
        session.status = TaskStatus(data.get("status", "pending"))
        session.rag_knowledge = data.get("rag_knowledge", {})
        session.conversation_context = data.get("conversation_context", {})
        session.plan = data.get("plan")
        session.step_results = data.get("step_results", {})
        session.shared_context = data.get("shared_context", {})
        session.errors = data.get("errors", [])
        session.messages = data.get("messages", [])
        
        # 恢复执行状态
        if "execution_state" in data:
            es_data = data["execution_state"]
            session.execution_state.current_step_id = es_data.get("current_step_id", 0)
            session.execution_state.current_step_status = StepStatus(
                es_data.get("current_step_status", "pending")
            )
            session.execution_state.current_agent = es_data.get("current_agent")
            session.execution_state.last_action_summary = es_data.get("last_action_summary", "")
            session.execution_state.retry_count = es_data.get("retry_count", 0)
            session.execution_state.retry_reason = es_data.get("retry_reason")
            session.execution_state.total_steps = es_data.get("total_steps", 0)
            # 恢复步骤状态
            for k, v in es_data.get("step_statuses", {}).items():
                session.execution_state.step_statuses[int(k)] = StepStatus(v)
        
        # 恢复事件日志
        if "event_log" in data:
            session.event_log = EventLog.from_dict(data["event_log"])
        
        # 恢复时间戳
        if "created_at" in data:
            session.created_at = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            session.updated_at = datetime.fromisoformat(data["updated_at"])
        
        return session
    
    def save_checkpoint(self, path: str):
        """
        保存检查点到文件
        
        Args:
            path: 保存路径
        """
        import json
        from pathlib import Path
        
        save_path = Path(path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load_checkpoint(cls, path: str) -> "TaskSession":
        """
        从文件加载检查点
        
        Args:
            path: 文件路径
            
        Returns:
            TaskSession 实例
        """
        import json
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return cls.from_dict(data)

