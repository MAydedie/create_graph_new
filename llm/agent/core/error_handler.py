#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
错误处理模块 - Phase 4 V2

实现错误分类、恢复策略和降级处理。

错误类别：
- RECOVERABLE: 可恢复错误，适合重试
- UNRECOVERABLE: 不可恢复错误，需要降级或终止
- TIMEOUT: 超时错误，可重试但需调整参数
- LLM_ERROR: LLM 相关错误，可重试
- VALIDATION_ERROR: 验证失败，可能需要修改后重试
"""

import re
import logging
from enum import Enum, auto
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from datetime import datetime


logger = logging.getLogger("ErrorHandler")


class ErrorCategory(Enum):
    """错误类别枚举"""
    RECOVERABLE = auto()       # 可恢复：网络波动、临时失败
    UNRECOVERABLE = auto()     # 不可恢复：权限不足、文件不存在
    TIMEOUT = auto()           # 超时：API 调用超时
    LLM_ERROR = auto()         # LLM 错误：生成失败、格式错误
    VALIDATION_ERROR = auto()  # 验证失败：代码审查不通过


class RecoveryStrategy(Enum):
    """恢复策略枚举"""
    RETRY = auto()              # 直接重试
    RETRY_WITH_FEEDBACK = auto() # 带反馈重试
    SIMPLIFY = auto()           # 简化任务
    HUMAN_INTERVENTION = auto() # 请求人工介入
    PARTIAL_COMPLETE = auto()   # 返回部分结果
    ABORT = auto()              # 终止任务


@dataclass
class ErrorInfo:
    """错误信息封装"""
    category: ErrorCategory
    message: str
    original_exception: Optional[Exception] = None
    recoverable: bool = True
    suggested_strategy: RecoveryStrategy = RecoveryStrategy.RETRY
    retry_delay: float = 1.0  # 重试前等待秒数
    context: Dict[str, Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.context is None:
            self.context = {}


class ErrorHandler:
    """
    错误处理器
    
    负责：
    1. 错误分类
    2. 恢复策略建议
    3. 错误转换和标准化
    """
    
    # 错误模式匹配规则
    ERROR_PATTERNS = {
        # 超时错误
        ErrorCategory.TIMEOUT: [
            r"timeout",
            r"timed out",
            r"read timed out",
            r"connection timed out",
            r"deadline exceeded",
        ],
        # LLM 错误
        ErrorCategory.LLM_ERROR: [
            r"api.*error",
            r"invalid.*response",
            r"json.*parse",
            r"rate.*limit",
            r"quota.*exceeded",
            r"model.*not.*found",
        ],
        # 验证错误
        ErrorCategory.VALIDATION_ERROR: [
            r"validation.*failed",
            r"review.*failed",
            r"test.*failed",
            r"assertion.*error",
            r"not.*approved",
        ],
        # 不可恢复错误
        ErrorCategory.UNRECOVERABLE: [
            r"permission.*denied",
            r"access.*denied",
            r"file.*not.*found",
            r"directory.*not.*found",
            r"invalid.*path",
            r"authentication.*failed",
            r"not.*authorized",
        ],
    }
    
    def __init__(self, default_max_retries: int = 3):
        """
        初始化错误处理器
        
        Args:
            default_max_retries: 默认最大重试次数
        """
        self.default_max_retries = default_max_retries
        self.error_history: List[ErrorInfo] = []
        self.logger = logging.getLogger("ErrorHandler")
    
    def classify_error(self, error: Exception) -> ErrorCategory:
        """
        对错误进行分类
        
        Args:
            error: 异常对象
            
        Returns:
            错误类别
        """
        error_str = str(error).lower()
        
        # 按优先级匹配
        for category, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, error_str, re.IGNORECASE):
                    return category
        
        # 默认为可恢复错误
        return ErrorCategory.RECOVERABLE
    
    def create_error_info(self, error: Exception, context: Dict = None) -> ErrorInfo:
        """
        创建标准化的错误信息
        
        Args:
            error: 异常对象
            context: 错误上下文
            
        Returns:
            ErrorInfo 对象
        """
        category = self.classify_error(error)
        strategy = self.get_recovery_strategy(category)
        recoverable = category != ErrorCategory.UNRECOVERABLE
        
        # 根据错误类型设置重试延迟
        retry_delay = self._get_retry_delay(category)
        
        error_info = ErrorInfo(
            category=category,
            message=str(error),
            original_exception=error,
            recoverable=recoverable,
            suggested_strategy=strategy,
            retry_delay=retry_delay,
            context=context or {}
        )
        
        # 记录到历史
        self.error_history.append(error_info)
        
        return error_info
    
    def get_recovery_strategy(self, category: ErrorCategory, 
                               retry_count: int = 0) -> RecoveryStrategy:
        """
        根据错误类别和重试次数决定恢复策略
        
        Args:
            category: 错误类别
            retry_count: 已重试次数
            
        Returns:
            恢复策略
        """
        # 不可恢复错误直接终止
        if category == ErrorCategory.UNRECOVERABLE:
            return RecoveryStrategy.ABORT
        
        # 根据重试次数决定策略
        if retry_count < self.default_max_retries:
            if category == ErrorCategory.VALIDATION_ERROR:
                return RecoveryStrategy.RETRY_WITH_FEEDBACK
            else:
                return RecoveryStrategy.RETRY
        
        # 达到最大重试次数，尝试降级
        if retry_count == self.default_max_retries:
            return RecoveryStrategy.SIMPLIFY
        elif retry_count == self.default_max_retries + 1:
            return RecoveryStrategy.HUMAN_INTERVENTION
        else:
            return RecoveryStrategy.PARTIAL_COMPLETE
    
    def _get_retry_delay(self, category: ErrorCategory) -> float:
        """获取重试延迟（指数退避）"""
        base_delays = {
            ErrorCategory.TIMEOUT: 2.0,
            ErrorCategory.LLM_ERROR: 1.5,
            ErrorCategory.VALIDATION_ERROR: 0.5,
            ErrorCategory.RECOVERABLE: 1.0,
            ErrorCategory.UNRECOVERABLE: 0.0,
        }
        return base_delays.get(category, 1.0)
    
    def should_retry(self, error_info: ErrorInfo, retry_count: int) -> bool:
        """
        判断是否应该重试
        
        Args:
            error_info: 错误信息
            retry_count: 已重试次数
            
        Returns:
            是否应该重试
        """
        if not error_info.recoverable:
            return False
        
        if retry_count >= self.default_max_retries:
            return False
        
        return True
    
    def get_feedback_for_retry(self, error_info: ErrorInfo, 
                                 previous_attempts: List[Dict] = None) -> str:
        """
        为重试生成反馈提示
        
        Args:
            error_info: 错误信息
            previous_attempts: 之前的尝试记录
            
        Returns:
            反馈提示字符串
        """
        lines = ["【重试反馈】"]
        
        # 错误信息
        lines.append(f"上次失败原因: {error_info.message[:200]}")
        
        # 错误类别建议
        category_hints = {
            ErrorCategory.TIMEOUT: "建议：减少处理范围或增加超时时间",
            ErrorCategory.LLM_ERROR: "建议：简化输入或检查 API 配额",
            ErrorCategory.VALIDATION_ERROR: "建议：根据审查反馈修改代码",
            ErrorCategory.RECOVERABLE: "建议：检查输入参数和环境",
        }
        if error_info.category in category_hints:
            lines.append(category_hints[error_info.category])
        
        # 之前尝试的总结
        if previous_attempts:
            lines.append(f"已尝试 {len(previous_attempts)} 次")
            for i, attempt in enumerate(previous_attempts[-2:], 1):
                summary = attempt.get("summary", "无摘要")[:50]
                lines.append(f"  尝试 {i}: {summary}")
        
        return "\n".join(lines)
    
    def get_error_summary(self) -> Dict[str, Any]:
        """获取错误统计摘要"""
        if not self.error_history:
            return {"total": 0, "by_category": {}}
        
        by_category = {}
        for error in self.error_history:
            cat_name = error.category.name
            by_category[cat_name] = by_category.get(cat_name, 0) + 1
        
        return {
            "total": len(self.error_history),
            "by_category": by_category,
            "last_error": self.error_history[-1].message[:100]
        }
    
    def clear_history(self):
        """清空错误历史"""
        self.error_history = []


# 便捷函数
def create_error_handler(max_retries: int = 3) -> ErrorHandler:
    """创建错误处理器"""
    return ErrorHandler(default_max_retries=max_retries)
