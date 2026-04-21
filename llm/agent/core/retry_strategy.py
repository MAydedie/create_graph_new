#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RetryStrategy - 智能重试策略 - Phase 5.2

根据错误类型选择不同的重试策略。

核心功能：
1. 错误类型识别
2. 策略选择
3. 重试判断
4. 延迟计算
"""

import time
import logging
from typing import Dict, Any, Optional
from enum import Enum


logger = logging.getLogger("RetryStrategy")


class RetryType(Enum):
    """重试类型"""
    IMMEDIATE = "immediate"              # 立即重试
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # 指数退避
    NO_RETRY = "no_retry"               # 不重试
    FIX_AND_RETRY = "fix_and_retry"     # 修复后重试


class RetryStrategy:
    """
    智能重试策略
    
    根据错误类型自动选择最佳重试策略。
    
    策略类型：
    1. 立即重试 - 临时性错误（网络波动）
    2. 指数退避 - 资源限制错误（API 速率限制）
    3. 不重试 - 永久性错误（语法错误）
    4. 修复后重试 - 逻辑错误（需要修改代码）
    
    使用示例：
    ```python
    strategy = RetryStrategy()
    
    # 获取策略
    config = strategy.get_strategy(FileNotFoundError())
    
    # 判断是否重试
    should_retry = strategy.should_retry(error, attempt=1)
    
    # 获取延迟
    delay = strategy.get_delay(error, attempt=1)
    time.sleep(delay)
    ```
    """
    
    # 错误类型 -> 策略配置
    STRATEGIES = {
        # 网络相关错误 - 指数退避
        "ConnectionError": {
            "type": RetryType.EXPONENTIAL_BACKOFF,
            "max_retries": 5,
            "base_delay": 1.0,
            "max_delay": 60.0,
            "reason": "网络连接错误，使用指数退避重试"
        },
        "TimeoutError": {
            "type": RetryType.EXPONENTIAL_BACKOFF,
            "max_retries": 3,
            "base_delay": 2.0,
            "max_delay": 30.0,
            "reason": "超时错误，使用指数退避重试"
        },
        
        # 语法错误 - 不重试
        "SyntaxError": {
            "type": RetryType.NO_RETRY,
            "reason": "语法错误，需要修改代码"
        },
        "IndentationError": {
            "type": RetryType.NO_RETRY,
            "reason": "缩进错误，需要修改代码"
        },
        
        # 文件相关错误 - 修复后重试
        "FileNotFoundError": {
            "type": RetryType.FIX_AND_RETRY,
            "max_retries": 2,
            "fix_action": "检查文件路径或创建文件",
            "reason": "文件不存在，需要修复路径或创建文件"
        },
        "PermissionError": {
            "type": RetryType.FIX_AND_RETRY,
            "max_retries": 2,
            "fix_action": "检查文件权限",
            "reason": "权限错误，需要修改文件权限"
        },
        
        # 导入错误 - 修复后重试
        "ImportError": {
            "type": RetryType.FIX_AND_RETRY,
            "max_retries": 1,
            "fix_action": "安装缺失的依赖",
            "reason": "导入错误，需要安装依赖"
        },
        "ModuleNotFoundError": {
            "type": RetryType.FIX_AND_RETRY,
            "max_retries": 1,
            "fix_action": "安装缺失的模块",
            "reason": "模块不存在，需要安装"
        },
        
        # API 限制 - 指数退避
        "RateLimitError": {
            "type": RetryType.EXPONENTIAL_BACKOFF,
            "max_retries": 3,
            "base_delay": 10.0,
            "max_delay": 120.0,
            "reason": "API 速率限制，使用指数退避重试"
        },
        
        # 临时错误 - 立即重试
        "TemporaryError": {
            "type": RetryType.IMMEDIATE,
            "max_retries": 3,
            "reason": "临时错误，立即重试"
        }
    }
    
    # 默认策略
    DEFAULT_STRATEGY = {
        "type": RetryType.EXPONENTIAL_BACKOFF,
        "max_retries": 3,
        "base_delay": 1.0,
        "max_delay": 30.0,
        "reason": "未知错误，使用默认指数退避策略"
    }
    
    def get_strategy(self, error: Exception) -> Dict[str, Any]:
        """
        获取错误的重试策略
        
        Args:
            error: 异常对象
        
        Returns:
            策略配置字典
        """
        error_type = type(error).__name__
        
        strategy = self.STRATEGIES.get(error_type, self.DEFAULT_STRATEGY.copy())
        
        logger.debug(f"错误 {error_type} 使用策略: {strategy['type'].value}")
        
        return strategy
    
    def should_retry(
        self,
        error: Exception,
        attempt: int
    ) -> bool:
        """
        判断是否应该重试
        
        Args:
            error: 异常对象
            attempt: 当前尝试次数（从 1 开始）
        
        Returns:
            是否应该重试
        """
        strategy = self.get_strategy(error)
        retry_type = strategy["type"]
        
        # 不重试类型
        if retry_type == RetryType.NO_RETRY:
            logger.info(f"错误类型 {type(error).__name__} 不支持重试")
            return False
        
        # 检查最大重试次数
        max_retries = strategy.get("max_retries", 3)
        
        if attempt >= max_retries:
            logger.info(f"已达到最大重试次数 {max_retries}")
            return False
        
        logger.debug(f"允许重试，当前尝试 {attempt}/{max_retries}")
        return True
    
    def get_delay(
        self,
        error: Exception,
        attempt: int
    ) -> float:
        """
        获取重试延迟（秒）
        
        Args:
            error: 异常对象
            attempt: 当前尝试次数（从 1 开始）
        
        Returns:
            延迟时间（秒）
        """
        strategy = self.get_strategy(error)
        retry_type = strategy["type"]
        
        # 立即重试
        if retry_type == RetryType.IMMEDIATE:
            return 0.0
        
        # 不重试
        if retry_type == RetryType.NO_RETRY:
            return 0.0
        
        # 指数退避
        if retry_type == RetryType.EXPONENTIAL_BACKOFF:
            base_delay = strategy.get("base_delay", 1.0)
            max_delay = strategy.get("max_delay", 60.0)
            
            # 计算延迟: base_delay * 2^(attempt-1)
            delay = base_delay * (2 ** (attempt - 1))
            
            # 限制最大延迟
            delay = min(delay, max_delay)
            
            logger.debug(f"指数退避延迟: {delay:.2f} 秒")
            return delay
        
        # 修复后重试
        if retry_type == RetryType.FIX_AND_RETRY:
            # 给一点时间让修复生效
            return 0.5
        
        # 默认
        return 1.0
    
    def get_fix_action(self, error: Exception) -> Optional[str]:
        """
        获取修复动作建议
        
        Args:
            error: 异常对象
        
        Returns:
            修复动作描述
        """
        strategy = self.get_strategy(error)
        return strategy.get("fix_action")
    
    def get_reason(self, error: Exception) -> str:
        """
        获取策略原因
        
        Args:
            error: 异常对象
        
        Returns:
            策略原因描述
        """
        strategy = self.get_strategy(error)
        return strategy.get("reason", "未知原因")


# 便捷函数
def should_retry_error(error: Exception, attempt: int) -> bool:
    """
    判断错误是否应该重试（便捷函数）
    
    Args:
        error: 异常对象
        attempt: 当前尝试次数
    
    Returns:
        是否应该重试
    """
    strategy = RetryStrategy()
    return strategy.should_retry(error, attempt)


def get_retry_delay(error: Exception, attempt: int) -> float:
    """
    获取重试延迟（便捷函数）
    
    Args:
        error: 异常对象
        attempt: 当前尝试次数
    
    Returns:
        延迟时间（秒）
    """
    strategy = RetryStrategy()
    return strategy.get_delay(error, attempt)
