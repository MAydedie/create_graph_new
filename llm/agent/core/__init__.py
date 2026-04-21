#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
核心层 (Core Layer)
ReAct 引擎、Prompt 模板、TaskSession 等通用内核

Phase 4 V1: TaskSession, ExecutionState, EventLog
Phase 4 V2: ErrorHandler, RetryManager
"""

from .prompt import build_system_prompt, build_few_shot_messages, format_observation
from .engine import AgentConfig, ReActEngine, StepRecord, RunResult

# Phase 4 V1
from .execution_state import (
    StepStatus, TaskStatus, ExecutionState, ExecutionEvent, EventLog
)
from .task_session import TaskSession

# Phase 4 V2
from .error_handler import (
    ErrorCategory, RecoveryStrategy, ErrorInfo, ErrorHandler,
    create_error_handler
)
from .retry_manager import (
    RetryConfig, RetryAttempt, RetryResult, FallbackLevel, RetryManager,
    create_retry_manager
)

__all__ = [
    # 原有
    "build_system_prompt",
    "build_few_shot_messages",
    "format_observation",
    "AgentConfig",
    "ReActEngine",
    "StepRecord",
    "RunResult",
    # Phase 4 V1
    "StepStatus",
    "TaskStatus",
    "ExecutionState",
    "ExecutionEvent",
    "EventLog",
    "TaskSession",
    # Phase 4 V2
    "ErrorCategory",
    "RecoveryStrategy", 
    "ErrorInfo",
    "ErrorHandler",
    "create_error_handler",
    "RetryConfig",
    "RetryAttempt",
    "RetryResult",
    "FallbackLevel",
    "RetryManager",
    "create_retry_manager",
]


