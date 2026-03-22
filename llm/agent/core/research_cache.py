#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ResearchCache - 调研结果缓存 - Phase 3.2

用于缓存 PlannerAgent 的调研结果，避免重复调研相同项目。

核心功能：
1. 基于项目路径和用户目标的缓存
2. TTL 过期机制
3. 自动清理过期缓存
4. 线程安全
"""

import time
import hashlib
import logging
from typing import Dict, Optional
from threading import Lock


logger = logging.getLogger("ResearchCache")


class ResearchCache:
    """
    调研结果缓存
    
    特点:
    - 基于项目路径 + 用户目标的缓存
    - TTL 过期机制（默认 1 小时）
    - 自动清理过期缓存
    - 线程安全
    
    使用示例:
    ```python
    cache = ResearchCache(ttl=3600)  # 1 小时过期
    
    # 缓存调研结果
    cache.set("/path/to/project", "生成测试", "调研结果...")
    
    # 获取缓存
    result = cache.get("/path/to/project", "生成测试")
    if result:
        print("缓存命中!")
    ```
    """
    
    def __init__(self, ttl: int = 3600, auto_cleanup: bool = True):
        """
        初始化缓存
        
        Args:
            ttl: 缓存过期时间（秒），默认 1 小时
            auto_cleanup: 是否自动清理过期缓存（默认 True）
        """
        self.cache: Dict[str, Dict] = {}
        self.ttl = ttl
        self.auto_cleanup = auto_cleanup
        self._lock = Lock()  # 线程锁
        
        # 统计信息
        self.stats = {
            "hits": 0,      # 缓存命中次数
            "misses": 0,    # 缓存未命中次数
            "sets": 0,      # 缓存设置次数
            "evictions": 0  # 缓存驱逐次数
        }
    
    def get(self, project_path: str, user_goal: str) -> Optional[str]:
        """
        获取缓存的调研结果
        
        Args:
            project_path: 项目路径
            user_goal: 用户目标
        
        Returns:
            缓存的调研结果，如果不存在或过期则返回 None
        """
        cache_key = self._generate_key(project_path, user_goal)
        
        with self._lock:
            if cache_key in self.cache:
                entry = self.cache[cache_key]
                
                # 检查是否过期
                if time.time() - entry["timestamp"] < self.ttl:
                    self.stats["hits"] += 1
                    logger.debug(f"缓存命中: {cache_key[:8]}...")
                    return entry["result"]
                else:
                    # 过期，删除
                    del self.cache[cache_key]
                    self.stats["evictions"] += 1
                    logger.debug(f"缓存过期: {cache_key[:8]}...")
            
            self.stats["misses"] += 1
            logger.debug(f"缓存未命中: {cache_key[:8]}...")
            return None
    
    def set(self, project_path: str, user_goal: str, result: str):
        """
        缓存调研结果
        
        Args:
            project_path: 项目路径
            user_goal: 用户目标
            result: 调研结果
        """
        cache_key = self._generate_key(project_path, user_goal)
        
        with self._lock:
            self.cache[cache_key] = {
                "result": result,
                "timestamp": time.time(),
                "project_path": project_path,
                "user_goal": user_goal[:100]  # 只保存前 100 字符
            }
            self.stats["sets"] += 1
            logger.debug(f"缓存设置: {cache_key[:8]}...")
            
            # 自动清理过期缓存
            if self.auto_cleanup:
                self._cleanup_expired()
    
    def clear(self):
        """清空所有缓存"""
        with self._lock:
            count = len(self.cache)
            self.cache.clear()
            logger.info(f"清空缓存: 删除 {count} 个条目")
    
    def clear_expired(self):
        """清理过期缓存（公开方法）"""
        with self._lock:
            self._cleanup_expired()
    
    def _cleanup_expired(self):
        """清理过期缓存（内部方法，需要持有锁）"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if current_time - entry["timestamp"] >= self.ttl
        ]
        
        for key in expired_keys:
            del self.cache[key]
            self.stats["evictions"] += 1
        
        if expired_keys:
            logger.debug(f"清理过期缓存: 删除 {len(expired_keys)} 个条目")
    
    def _generate_key(self, project_path: str, user_goal: str) -> str:
        """
        生成缓存 key
        
        使用项目路径 + 用户目标的前 100 字符的 MD5 哈希
        
        Args:
            project_path: 项目路径
            user_goal: 用户目标
        
        Returns:
            缓存 key (MD5 哈希)
        """
        # 标准化项目路径（处理不同的路径分隔符）
        normalized_path = project_path.replace("\\", "/").lower()
        
        # 使用项目路径 + 用户目标的前 100 字符
        content = f"{normalized_path}:{user_goal[:100]}"
        
        # MD5 哈希
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            total_requests = self.stats["hits"] + self.stats["misses"]
            hit_rate = (self.stats["hits"] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                **self.stats,
                "total_requests": total_requests,
                "hit_rate": round(hit_rate, 2),
                "cache_size": len(self.cache)
            }
    
    def __len__(self) -> int:
        """返回缓存条目数量"""
        with self._lock:
            return len(self.cache)
    
    def __repr__(self) -> str:
        """字符串表示"""
        stats = self.get_stats()
        return (
            f"ResearchCache(size={stats['cache_size']}, "
            f"hit_rate={stats['hit_rate']}%, "
            f"ttl={self.ttl}s)"
        )


# 全局缓存实例（单例模式）
_global_cache: Optional[ResearchCache] = None


def get_global_cache(ttl: int = 3600) -> ResearchCache:
    """
    获取全局缓存实例（单例）
    
    Args:
        ttl: 缓存过期时间（秒）
    
    Returns:
        全局 ResearchCache 实例
    """
    global _global_cache
    
    if _global_cache is None:
        _global_cache = ResearchCache(ttl=ttl)
        logger.info(f"创建全局 ResearchCache 实例 (TTL={ttl}s)")
    
    return _global_cache


def clear_global_cache():
    """清空全局缓存"""
    global _global_cache
    
    if _global_cache is not None:
        _global_cache.clear()
