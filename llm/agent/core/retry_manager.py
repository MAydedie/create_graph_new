#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重试管理器 - Phase 4 V2

实现带反馈的重试机制和降级策略。

核心功能：
- 指数退避重试
- 反馈式修复（Reflexion）
- 降级策略执行
"""

import time
import logging
from typing import Dict, Any, Optional, Callable, List, TypeVar, Generic
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .error_handler import (
    ErrorHandler, 
    ErrorInfo, 
    ErrorCategory, 
    RecoveryStrategy,
    create_error_handler
)


logger = logging.getLogger("RetryManager")

T = TypeVar('T')


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3           # 最大重试次数
    initial_delay: float = 1.0     # 初始延迟（秒）
    max_delay: float = 30.0        # 最大延迟
    exponential_base: float = 2.0  # 指数基数
    use_feedback: bool = True      # 是否使用反馈
    enable_fallback: bool = True   # 是否启用降级


@dataclass
class RetryAttempt:
    """重试尝试记录"""
    attempt_number: int
    timestamp: datetime
    success: bool
    result: Any = None
    error: Optional[ErrorInfo] = None
    feedback_used: str = ""
    duration: float = 0.0


@dataclass
class RetryResult:
    """重试结果"""
    success: bool
    result: Any = None
    attempts: List[RetryAttempt] = field(default_factory=list)
    final_error: Optional[ErrorInfo] = None
    strategy_used: RecoveryStrategy = RecoveryStrategy.RETRY
    fallback_result: Any = None
    
    @property
    def total_attempts(self) -> int:
        return len(self.attempts)
    
    @property
    def had_retries(self) -> bool:
        return len(self.attempts) > 1


class FallbackLevel(Enum):
    """降级级别"""
    NONE = 0           # 无降级
    SIMPLIFY = 1       # 简化任务
    HUMAN = 2          # 人工介入
    PARTIAL = 3        # 部分完成


class RetryManager:
    """
    重试管理器
    
    核心功能：
    1. 带指数退避的重试
    2. 基于错误反馈的智能重试
    3. 多级降级策略
    """
    
    def __init__(self, config: RetryConfig = None, error_handler: ErrorHandler = None):
        """
        初始化重试管理器
        
        Args:
            config: 重试配置
            error_handler: 错误处理器
        """
        self.config = config or RetryConfig()
        self.error_handler = error_handler or create_error_handler(self.config.max_retries)
        self.logger = logging.getLogger("RetryManager")
        
        # 降级回调
        self._fallback_handlers: Dict[FallbackLevel, Callable] = {}
    
    def retry_with_feedback(
        self,
        action: Callable[[], Any],
        feedback_generator: Callable[[ErrorInfo, List[RetryAttempt]], str] = None,
        context: Dict = None
    ) -> RetryResult:
        """
        带反馈的重试执行
        
        Args:
            action: 要执行的动作（可调用对象）
            feedback_generator: 自定义反馈生成器
            context: 上下文信息
            
        Returns:
            RetryResult 对象
        """
        attempts: List[RetryAttempt] = []
        current_delay = self.config.initial_delay
        feedback = ""
        
        for attempt_num in range(1, self.config.max_retries + 1):
            start_time = time.time()
            
            try:
                # 如果有反馈，可能需要传递给 action（通过 context）
                if context and feedback:
                    context["retry_feedback"] = feedback
                
                result = action()
                duration = time.time() - start_time
                
                # 成功
                attempt = RetryAttempt(
                    attempt_number=attempt_num,
                    timestamp=datetime.now(),
                    success=True,
                    result=result,
                    feedback_used=feedback,
                    duration=duration
                )
                attempts.append(attempt)
                
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=attempts,
                    strategy_used=RecoveryStrategy.RETRY_WITH_FEEDBACK if feedback else RecoveryStrategy.RETRY
                )
                
            except Exception as e:
                duration = time.time() - start_time
                error_info = self.error_handler.create_error_info(e, context)
                
                attempt = RetryAttempt(
                    attempt_number=attempt_num,
                    timestamp=datetime.now(),
                    success=False,
                    error=error_info,
                    feedback_used=feedback,
                    duration=duration
                )
                attempts.append(attempt)
                
                # 检查是否应该重试
                if not self.error_handler.should_retry(error_info, attempt_num):
                    self.logger.warning(f"错误不可重试: {error_info.message[:100]}")
                    break
                
                if attempt_num < self.config.max_retries:
                    # 生成反馈
                    if self.config.use_feedback:
                        if feedback_generator:
                            feedback = feedback_generator(error_info, attempts)
                        else:
                            feedback = self.error_handler.get_feedback_for_retry(
                                error_info, 
                                [{"summary": a.error.message if a.error else "成功"} for a in attempts]
                            )
                    
                    # 等待后重试
                    self.logger.info(f"尝试 {attempt_num} 失败，{current_delay:.1f}s 后重试...")
                    time.sleep(min(current_delay, self.config.max_delay))
                    current_delay *= self.config.exponential_base
        
        # 所有重试都失败
        final_error = attempts[-1].error if attempts else None
        
        # 尝试降级
        if self.config.enable_fallback:
            fallback_result = self._execute_fallback(final_error, attempts, context)
            if fallback_result:
                return fallback_result
        
        return RetryResult(
            success=False,
            attempts=attempts,
            final_error=final_error,
            strategy_used=RecoveryStrategy.RETRY
        )
    
    def register_fallback(self, level: FallbackLevel, handler: Callable):
        """
        注册降级处理器
        
        Args:
            level: 降级级别
            handler: 处理器函数
        """
        self._fallback_handlers[level] = handler
    
    def _execute_fallback(
        self, 
        error: Optional[ErrorInfo], 
        attempts: List[RetryAttempt],
        context: Dict = None
    ) -> Optional[RetryResult]:
        """
        执行降级策略
        
        降级顺序:
        1. 简化任务
        2. 请求人工介入
        3. 返回部分结果
        """
        # 级别 1: 简化任务
        if FallbackLevel.SIMPLIFY in self._fallback_handlers:
            self.logger.info("降级策略: 尝试简化任务...")
            try:
                result = self._fallback_handlers[FallbackLevel.SIMPLIFY](error, context)
                if result:
                    return RetryResult(
                        success=False,  # 降级不算成功
                        result=result,
                        attempts=attempts,
                        strategy_used=RecoveryStrategy.SIMPLIFY,
                        fallback_result={"partial_success": True, "data": result}
                    )
            except Exception as e:
                self.logger.warning(f"简化任务失败: {e}")
        
        # 级别 2: 请求人工介入
        if FallbackLevel.HUMAN in self._fallback_handlers:
            self.logger.info("降级策略: 请求人工介入...")
            try:
                result = self._fallback_handlers[FallbackLevel.HUMAN](error, context)
                return RetryResult(
                    success=False,
                    attempts=attempts,
                    strategy_used=RecoveryStrategy.HUMAN_INTERVENTION,
                    fallback_result={"human_required": True, "context": result}
                )
            except Exception as e:
                self.logger.warning(f"人工介入请求失败: {e}")
        
        # 级别 3: 返回部分结果
        if FallbackLevel.PARTIAL in self._fallback_handlers:
            self.logger.info("降级策略: 返回部分结果...")
            try:
                result = self._fallback_handlers[FallbackLevel.PARTIAL](error, context)
                return RetryResult(
                    success=False,  # 部分完成不算成功
                    result=result,
                    attempts=attempts,
                    strategy_used=RecoveryStrategy.PARTIAL_COMPLETE,
                    fallback_result={"partial_success": True, "data": result}
                )
            except Exception as e:
                self.logger.warning(f"部分完成失败: {e}")
        
        return None
    
    def simple_retry(
        self, 
        action: Callable[[], T], 
        max_retries: int = None
    ) -> T:
        """
        简单重试（不带反馈）
        
        Args:
            action: 要执行的动作
            max_retries: 最大重试次数
            
        Returns:
            执行结果
            
        Raises:
            Exception: 所有重试都失败时抛出最后的异常
        """
        retries = max_retries or self.config.max_retries
        last_exception = None
        
        for i in range(retries):
            try:
                return action()
            except Exception as e:
                last_exception = e
                if i < retries - 1:
                    delay = self.config.initial_delay * (self.config.exponential_base ** i)
                    time.sleep(min(delay, self.config.max_delay))
        
        raise last_exception
    
    def get_retry_summary(self, result: RetryResult) -> str:
        """
        获取重试摘要
        
        Args:
            result: 重试结果
            
        Returns:
            摘要字符串
        """
        lines = []
        
        if result.success:
            lines.append(f"✓ 成功 (尝试 {result.total_attempts} 次)")
        else:
            lines.append(f"✗ 失败 (尝试 {result.total_attempts} 次)")
        
        lines.append(f"策略: {result.strategy_used.name}")
        
        if result.had_retries:
            lines.append("重试历史:")
            for attempt in result.attempts:
                status = "✓" if attempt.success else "✗"
                lines.append(f"  {status} 尝试 {attempt.attempt_number}: {attempt.duration:.2f}s")
        
        if result.fallback_result:
            lines.append(f"降级结果: {str(result.fallback_result)[:50]}")
        
        return "\n".join(lines)


# 便捷函数
def create_retry_manager(
    max_retries: int = 3,
    use_feedback: bool = True
) -> RetryManager:
    """创建重试管理器"""
    config = RetryConfig(
        max_retries=max_retries,
        use_feedback=use_feedback
    )
    return RetryManager(config=config)
