#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ErrorMemory - 错误记忆系统 - Phase 5.2

记录和查询错误历史，支持从错误中学习。

核心功能：
1. 记录错误历史
2. 查找相似错误
3. 记录解决方案
4. 持久化存储
"""

import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from threading import Lock


logger = logging.getLogger("ErrorMemory")


@dataclass
class ErrorAttempt:
    """错误尝试记录"""
    attempt_number: int
    error_message: str
    timestamp: float
    action_taken: Optional[str] = None


@dataclass
class ErrorRecord:
    """错误记录"""
    error_id: str
    error_type: str
    error_message: str
    context: Dict[str, Any]
    attempts: List[Dict[str, Any]]
    solution: Optional[str]
    timestamp: float
    resolved: bool = False
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "error_id": self.error_id,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "context": self.context,
            "attempts": self.attempts,
            "solution": self.solution,
            "timestamp": self.timestamp,
            "resolved": self.resolved
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ErrorRecord':
        """从字典创建"""
        return cls(
            error_id=data["error_id"],
            error_type=data["error_type"],
            error_message=data["error_message"],
            context=data["context"],
            attempts=data["attempts"],
            solution=data.get("solution"),
            timestamp=data["timestamp"],
            resolved=data.get("resolved", False)
        )


class ErrorMemory:
    """
    错误记忆系统
    
    功能：
    - 记录错误历史
    - 查找相似错误
    - 记录解决方案
    - 持久化存储
    
    使用示例：
    ```python
    memory = ErrorMemory()
    
    # 记录错误
    error_id = memory.record_error(
        error=FileNotFoundError("file.txt not found"),
        context={"step": "read_file", "file": "file.txt"}
    )
    
    # 记录尝试
    memory.record_attempt(error_id, {
        "attempt": 1,
        "action": "创建文件"
    })
    
    # 记录解决方案
    memory.record_solution(error_id, "使用绝对路径")
    
    # 查找相似错误
    similar = memory.find_similar_errors(
        FileNotFoundError("another.txt not found")
    )
    ```
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        """
        初始化错误记忆
        
        Args:
            storage_path: 存储路径，默认为 .agent/error_memory.json
        """
        self.storage_path = storage_path or Path(".agent/error_memory.json")
        self.records: Dict[str, ErrorRecord] = {}
        self._lock = Lock()
        
        # 确保存储目录存在
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载历史记录
        self._load()
        
        logger.info(f"ErrorMemory 初始化，加载了 {len(self.records)} 条记录")
    
    def record_error(
        self,
        error: Exception,
        context: Dict[str, Any]
    ) -> str:
        """
        记录错误
        
        Args:
            error: 异常对象
            context: 错误上下文
        
        Returns:
            错误 ID
        """
        with self._lock:
            # 生成错误 ID
            error_id = self._generate_error_id(error, context)
            
            # 检查是否已存在
            if error_id in self.records:
                logger.debug(f"错误已存在: {error_id}")
                return error_id
            
            # 创建记录
            record = ErrorRecord(
                error_id=error_id,
                error_type=type(error).__name__,
                error_message=str(error),
                context=context,
                attempts=[],
                solution=None,
                timestamp=time.time(),
                resolved=False
            )
            
            self.records[error_id] = record
            self._save()
            
            logger.info(f"记录错误: {error_id} - {type(error).__name__}")
            
            return error_id
    
    def record_attempt(
        self,
        error_id: str,
        attempt: Dict[str, Any]
    ):
        """
        记录重试尝试
        
        Args:
            error_id: 错误 ID
            attempt: 尝试信息
        """
        with self._lock:
            if error_id not in self.records:
                logger.warning(f"错误不存在: {error_id}")
                return
            
            record = self.records[error_id]
            
            # 添加时间戳
            attempt["timestamp"] = time.time()
            attempt["attempt_number"] = len(record.attempts) + 1
            
            record.attempts.append(attempt)
            self._save()
            
            logger.debug(f"记录尝试 #{attempt['attempt_number']} for {error_id}")
    
    def record_solution(
        self,
        error_id: str,
        solution: str
    ):
        """
        记录解决方案
        
        Args:
            error_id: 错误 ID
            solution: 解决方案描述
        """
        with self._lock:
            if error_id not in self.records:
                logger.warning(f"错误不存在: {error_id}")
                return
            
            record = self.records[error_id]
            record.solution = solution
            record.resolved = True
            self._save()
            
            logger.info(f"记录解决方案 for {error_id}: {solution[:50]}...")
    
    def find_similar_errors(
        self,
        error: Exception,
        limit: int = 5
    ) -> List[ErrorRecord]:
        """
        查找相似错误
        
        Args:
            error: 异常对象
            limit: 返回数量限制
        
        Returns:
            相似错误记录列表（按相似度排序）
        """
        with self._lock:
            error_type = type(error).__name__
            error_message = str(error)
            
            # 过滤相同类型的错误
            candidates = [
                record for record in self.records.values()
                if record.error_type == error_type and record.resolved
            ]
            
            if not candidates:
                return []
            
            # 计算相似度（简单的字符串匹配）
            def similarity(record: ErrorRecord) -> float:
                # 错误消息相似度
                msg_sim = self._string_similarity(
                    error_message.lower(),
                    record.error_message.lower()
                )
                return msg_sim
            
            # 排序
            candidates.sort(key=similarity, reverse=True)
            
            # 返回前 N 个
            result = candidates[:limit]
            
            if result:
                logger.info(f"找到 {len(result)} 个相似错误")
            
            return result
    
    def get_record(self, error_id: str) -> Optional[ErrorRecord]:
        """获取错误记录"""
        with self._lock:
            return self.records.get(error_id)
    
    def get_attempts(self, error_id: str) -> List[Dict]:
        """获取错误的所有尝试"""
        with self._lock:
            record = self.records.get(error_id)
            return record.attempts if record else []
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            total = len(self.records)
            resolved = sum(1 for r in self.records.values() if r.resolved)
            
            # 按错误类型统计
            by_type = {}
            for record in self.records.values():
                error_type = record.error_type
                by_type[error_type] = by_type.get(error_type, 0) + 1
            
            return {
                "total_errors": total,
                "resolved_errors": resolved,
                "unresolved_errors": total - resolved,
                "resolution_rate": (resolved / total * 100) if total > 0 else 0,
                "by_type": by_type,
                "storage_path": str(self.storage_path)
            }
    
    def clear(self):
        """清空所有记录"""
        with self._lock:
            self.records.clear()
            self._save()
            logger.info("清空所有错误记录")
    
    def _generate_error_id(
        self,
        error: Exception,
        context: Dict[str, Any]
    ) -> str:
        """
        生成错误 ID
        
        使用错误类型 + 错误消息 + 上下文的哈希
        """
        content = f"{type(error).__name__}:{str(error)}:{json.dumps(context, sort_keys=True)}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]
    
    def _string_similarity(self, s1: str, s2: str) -> float:
        """
        计算字符串相似度（简单版本）
        
        使用 Jaccard 相似度
        """
        if not s1 or not s2:
            return 0.0
        
        # 分词
        words1 = set(s1.split())
        words2 = set(s2.split())
        
        # Jaccard 相似度
        intersection = words1 & words2
        union = words1 | words2
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    def _load(self):
        """从文件加载记录"""
        if not self.storage_path.exists():
            logger.debug("错误记忆文件不存在，创建新文件")
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.records = {
                error_id: ErrorRecord.from_dict(record_data)
                for error_id, record_data in data.items()
            }
            
            logger.info(f"加载了 {len(self.records)} 条错误记录")
        
        except Exception as e:
            logger.error(f"加载错误记忆失败: {e}")
            self.records = {}
    
    def _save(self):
        """保存记录到文件"""
        try:
            data = {
                error_id: record.to_dict()
                for error_id, record in self.records.items()
            }
            
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"保存了 {len(self.records)} 条错误记录")
        
        except Exception as e:
            logger.error(f"保存错误记忆失败: {e}")
    
    def __len__(self) -> int:
        """返回记录数量"""
        with self._lock:
            return len(self.records)
    
    def __repr__(self) -> str:
        """字符串表示"""
        stats = self.get_statistics()
        return (
            f"ErrorMemory(total={stats['total_errors']}, "
            f"resolved={stats['resolved_errors']}, "
            f"rate={stats['resolution_rate']:.1f}%)"
        )


# 全局错误记忆实例（单例）
_global_error_memory: Optional[ErrorMemory] = None


def get_global_error_memory(storage_path: Optional[Path] = None) -> ErrorMemory:
    """
    获取全局错误记忆实例（单例）
    
    Args:
        storage_path: 存储路径
    
    Returns:
        全局 ErrorMemory 实例
    """
    global _global_error_memory
    
    if _global_error_memory is None:
        _global_error_memory = ErrorMemory(storage_path=storage_path)
        logger.info("创建全局 ErrorMemory 实例")
    
    return _global_error_memory


def clear_global_error_memory():
    """清空全局错误记忆"""
    global _global_error_memory
    
    if _global_error_memory is not None:
        _global_error_memory.clear()
