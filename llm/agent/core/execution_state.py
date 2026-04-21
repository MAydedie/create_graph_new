#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
执行状态管理模块 (Execution State) - Phase 4

实现动态状态管理：
- ExecutionState: 实时追踪当前执行状态
- ExecutionEvent: 单个执行事件
- EventLog: 事件日志，支持筛选和摘要生成

核心思想：不传递完整历史，只传递"当前状态 + 相关事件"
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Any
from datetime import datetime
import uuid


class StepStatus(Enum):
    """步骤状态枚举"""
    PENDING = "pending"           # 待执行
    IN_PROGRESS = "in_progress"   # 执行中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败
    RETRYING = "retrying"         # 重试中
    THINKING = "thinking"         # 思考中
    SKIPPED = "skipped"           # 已跳过


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"           # 待开始
    PLANNING = "planning"         # 规划中
    EXECUTING = "executing"       # 执行中
    REVIEWING = "reviewing"       # 审查中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败
    PAUSED = "paused"             # 已暂停


@dataclass
class ExecutionEvent:
    """
    单个执行事件
    
    记录任务执行过程中的重要事件
    """
    event_id: str                           # 事件 ID
    timestamp: datetime                     # 时间戳
    event_type: str                         # 事件类型: step_start | step_complete | step_fail | retry | feedback
    agent: str                              # 触发事件的 Agent
    step_id: int                            # 步骤 ID
    summary: str                            # 事件摘要
    details: Optional[Dict[str, Any]] = None  # 详细信息
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "agent": self.agent,
            "step_id": self.step_id,
            "summary": self.summary,
            "details": self.details
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionEvent":
        """从字典创建"""
        return cls(
            event_id=data["event_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_type=data["event_type"],
            agent=data["agent"],
            step_id=data["step_id"],
            summary=data["summary"],
            details=data.get("details")
        )


@dataclass
class ExecutionState:
    """
    实时执行状态 - TaskSession 的核心组件
    
    设计目标：
    1. 实时追踪当前正在发生什么
    2. 提供给任意 Agent 查询当前状态
    3. 支持增量式更新
    """
    
    # 当前执行位置
    current_step_id: int = 0
    current_step_status: StepStatus = StepStatus.PENDING
    current_agent: Optional[str] = None  # "planner" | "coder" | "reviewer" | "orchestrator"
    
    # 步骤状态摘要（不是完整结果，只是状态）
    step_statuses: Dict[int, StepStatus] = field(default_factory=dict)
    
    # 最近一次操作的简要描述（用于告知其他 Agent）
    last_action_summary: str = ""
    
    # 重试信息
    retry_count: int = 0
    retry_reason: Optional[str] = None
    
    # 总步骤数
    total_steps: int = 0
    
    SKIPPED = "skipped"           # 已跳过
    
    def get_status_summary(self) -> str:
        """
        生成状态摘要（用于传递给其他 Agent）
        
        关键：这是一个**压缩的**状态描述，不是完整历史
        
        Returns:
            格式化的状态摘要字符串
        """
        # 统计各状态步骤数
        completed = sum(1 for s in self.step_statuses.values() if s == StepStatus.COMPLETED)
        failed = sum(1 for s in self.step_statuses.values() if s == StepStatus.FAILED)
        skipped = sum(1 for s in self.step_statuses.values() if s == StepStatus.SKIPPED)
        
        summary = f"""【当前执行状态】
- 当前步骤: Step {self.current_step_id} / {self.total_steps}
- 状态: {self.current_step_status.value}
- 执行者: {self.current_agent or '未分配'}
- 最近操作: {self.last_action_summary or '无'}
- 已完成: {completed} 步, 失败: {failed} 步, 跳过: {skipped} 步
- 重试次数: {self.retry_count}"""
        
        if self.retry_reason:
            summary += f"\n- 重试原因: {self.retry_reason}"
        
        return summary.strip()
    
    def update_step_status(self, step_id: int, status: StepStatus):
        """更新某个步骤的状态"""
        self.step_statuses[step_id] = status
    
    def get_progress_percentage(self) -> float:
        """获取进度百分比"""
        if self.total_steps == 0:
            return 0.0
        completed = sum(1 for s in self.step_statuses.values() if s == StepStatus.COMPLETED)
        return (completed / self.total_steps) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "current_step_id": self.current_step_id,
            "current_step_status": self.current_step_status.value,
            "current_agent": self.current_agent,
            "step_statuses": {k: v.value for k, v in self.step_statuses.items()},
            "last_action_summary": self.last_action_summary,
            "retry_count": self.retry_count,
            "retry_reason": self.retry_reason,
            "total_steps": self.total_steps
        }


class EventLog:
    """
    事件日志 - 记录任务执行过程中的所有重要事件
    
    设计目标：
    1. 完整记录执行历史（用于调试和复盘）
    2. 支持按条件筛选事件（用于生成上下文）
    3. 支持生成摘要（用于 Agent 理解）
    """
    
    def __init__(self):
        self.events: List[ExecutionEvent] = []
    
    def log(self, event_type: str, agent: str, step_id: int, summary: str, 
            details: Dict = None) -> ExecutionEvent:
        """
        记录事件
        
        Args:
            event_type: 事件类型 (step_start, step_complete, step_fail, retry, feedback, plan_created)
            agent: 触发事件的 Agent
            step_id: 步骤 ID
            summary: 事件摘要
            details: 详细信息
            
        Returns:
            创建的事件对象
        """
        event = ExecutionEvent(
            event_id=f"evt_{len(self.events)}_{uuid.uuid4().hex[:6]}",
            timestamp=datetime.now(),
            event_type=event_type,
            agent=agent,
            step_id=step_id,
            summary=summary,
            details=details
        )
        self.events.append(event)
        return event
    
    def get_recent_events(self, n: int = 5) -> List[ExecutionEvent]:
        """获取最近 N 个事件"""
        return self.events[-n:]
    
    def get_events_for_step(self, step_id: int) -> List[ExecutionEvent]:
        """获取某个步骤的所有事件"""
        return [e for e in self.events if e.step_id == step_id]
    
    def get_events_by_type(self, event_type: str) -> List[ExecutionEvent]:
        """获取某个类型的所有事件"""
        return [e for e in self.events if e.event_type == event_type]
    
    def get_events_by_agent(self, agent: str) -> List[ExecutionEvent]:
        """获取某个 Agent 的所有事件"""
        return [e for e in self.events if e.agent == agent]
    
    def get_failure_feedback(self, step_id: int) -> Optional[str]:
        """
        获取某个步骤的失败反馈（用于返工）
        
        Args:
            step_id: 步骤 ID
            
        Returns:
            失败原因描述，不存在则返回 None
        """
        fail_events = [e for e in self.events 
                       if e.step_id == step_id and e.event_type == "step_fail"]
        if fail_events:
            return fail_events[-1].summary
        return None
    
    def generate_context_summary(self, for_agent: str, current_step: int) -> str:
        """
        为特定 Agent 生成上下文摘要
        
        关键：这是**筛选和压缩**后的信息，不是完整日志
        
        Args:
            for_agent: 目标 Agent 类型 (planner, coder, reviewer)
            current_step: 当前步骤 ID
            
        Returns:
            格式化的上下文摘要
        """
        relevant_events = []
        
        if for_agent == "coder":
            # Coder 需要知道：之前的分析结果 + 如果是返工，需要知道失败原因
            relevant_events = [
                e for e in self.events 
                if e.event_type in ["step_complete", "step_fail"] 
                and e.step_id < current_step
            ]
            # 如果是返工，添加失败反馈
            fail_feedback = self.get_failure_feedback(current_step)
            if fail_feedback:
                context = "【前序步骤摘要】\n"
                context += "\n".join([f"- [{e.agent}] {e.summary}" for e in relevant_events[-3:]])
                context += f"\n\n【返工原因】{fail_feedback}"
                return context
        
        elif for_agent == "reviewer":
            # Reviewer 需要知道：Coder 做了什么
            relevant_events = [
                e for e in self.events 
                if e.agent == "coder" and e.step_id == current_step
            ]
        
        elif for_agent == "planner":
            # Planner 需要知道：之前的执行历史概要
            relevant_events = [
                e for e in self.events 
                if e.event_type in ["step_complete", "step_fail"]
            ][-5:]  # 最近 5 个
        
        if not relevant_events:
            return ""
        
        return "【相关执行记录】\n" + "\n".join([
            f"- [{e.agent}] {e.summary}" for e in relevant_events[-5:]
        ])
    
    def get_all_events_summary(self) -> str:
        """获取所有事件的摘要"""
        if not self.events:
            return "【暂无执行记录】"
        
        lines = ["【执行记录】"]
        for e in self.events[-10:]:  # 最近 10 个
            lines.append(f"- [{e.timestamp.strftime('%H:%M:%S')}] [{e.agent}] {e.summary}")
        
        if len(self.events) > 10:
            lines.insert(1, f"（共 {len(self.events)} 条记录，仅显示最近 10 条）")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "events": [e.to_dict() for e in self.events]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventLog":
        """从字典创建"""
        log = cls()
        log.events = [ExecutionEvent.from_dict(e) for e in data.get("events", [])]
        return log
    
    def clear(self):
        """清空所有事件"""
        self.events = []
    
    def __len__(self) -> int:
        return len(self.events)
