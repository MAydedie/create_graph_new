#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识代理模块 (Knowledge Agent) - Phase 4

封装 RAG 系统，作为 Multi-Agent 集群的一个成员。

职责：
- 从代码仓库知识中检索信息
- 为用户目标获取相关知识
- 缓存检索结果，减少重复调用
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

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


logger = logging.getLogger("KnowledgeAgent")


class KnowledgeAgent:
    """
    知识代理 - 封装 RAG 系统
    
    作为 Multi-Agent 集群的知识检索成员，负责：
    1. 从代码仓库知识中检索信息
    2. 为用户目标获取相关知识
    3. 格式化检索结果供其他 Agent 使用
    
    Attributes:
        rag_system: RAG 系统实例（延迟加载）
        cache: 检索结果缓存
    """
    
    def __init__(self, rag_system=None):
        """
        初始化知识代理
        
        Args:
            rag_system: 可选的 RAG 系统实例，如果不提供则延迟加载
        """
        self._rag_system = rag_system
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger("KnowledgeAgent")
    
    def _get_rag_system(self):
        """
        获取 RAG 系统（延迟加载）
        
        Returns:
            RAGSystem 实例
        """
        if self._rag_system is None:
            try:
                from llm.rag_core.rag_system import RAGSystem
                self._rag_system = RAGSystem()
                self.logger.info("RAG 系统加载成功")
            except Exception as e:
                self.logger.error(f"RAG 系统加载失败: {e}")
                raise
        return self._rag_system
    
    def retrieve(self, query: str, top_k: int = 5, use_cache: bool = True) -> Dict[str, Any]:
        """
        从 RAG 系统检索知识
        
        Args:
            query: 查询字符串
            top_k: 返回的结果数量
            use_cache: 是否使用缓存
            
        Returns:
            包含检索结果的字典：
            {
                "success": bool,
                "query": str,
                "results": List[Dict],  # 检索到的知识片段
                "answer": str,          # RAG 生成的答案
                "context_summary": str  # 格式化的上下文摘要
            }
        """
        # 检查缓存
        cache_key = f"{query}_{top_k}"
        if use_cache and cache_key in self.cache:
            self.logger.info(f"使用缓存的检索结果: {query[:50]}...")
            return self.cache[cache_key]
        
        try:
            rag = self._get_rag_system()
            
            # 调用 RAG 系统查询
            result = rag.query(
                question=query,
                retrieval_top_k=top_k * 2,  # 召回更多，让 reranker 选择
                rerank_top_k=top_k,
                return_context=True,
                timeout=120
            )
            
            # 格式化结果
            formatted_result = {
                "success": True,
                "query": query,
                "results": result.get("context", []),
                "answer": result.get("answer", ""),
                "retrieval_count": result.get("retrieval_count", 0),
                "rerank_count": result.get("rerank_count", 0),
                "context_summary": self._format_context_summary(result.get("context", []))
            }
            
            # 缓存结果
            if use_cache:
                self.cache[cache_key] = formatted_result
            
            self.logger.info(f"检索成功: {query[:50]}... (找到 {len(formatted_result['results'])} 条结果)")
            return formatted_result
            
        except Exception as e:
            self.logger.error(f"检索失败: {e}")
            return {
                "success": False,
                "query": query,
                "results": [],
                "answer": "",
                "error": str(e),
                "context_summary": ""
            }
    
    def get_context_for_goal(self, user_goal: str, top_k: int = 5) -> Dict[str, Any]:
        """
        为用户目标获取相关知识
        
        这是 TaskSession 初始化时调用的主要方法，用于获取与用户目标相关的全部知识。
        
        Args:
            user_goal: 用户目标描述
            top_k: 返回的结果数量
            
        Returns:
            包含相关知识的字典，可直接用于 TaskSession.rag_knowledge
        """
        result = self.retrieve(user_goal, top_k=top_k)
        
        return {
            "query": user_goal,
            "knowledge_items": result.get("results", []),
            "context_summary": result.get("context_summary", ""),
            "rag_answer": result.get("answer", ""),
            "success": result.get("success", False)
        }
    
    def _format_context_summary(self, context_items: List[Dict]) -> str:
        """
        格式化上下文摘要
        
        将检索结果格式化为易读的上下文字符串，供 Agent 使用。
        
        Args:
            context_items: 上下文条目列表
            
        Returns:
            格式化的上下文字符串
        """
        if not context_items:
            return "【暂无相关知识】"
        
        lines = ["【相关知识】"]
        for i, item in enumerate(context_items, 1):
            question = item.get("question", "")
            answer = item.get("answer", "")
            score = item.get("score", 0)
            
            # 截断过长的内容
            if len(answer) > 200:
                answer = answer[:200] + "..."
            
            lines.append(f"\n{i}. [相关度: {score:.2f}]")
            if question:
                lines.append(f"   问题: {question}")
            if answer:
                lines.append(f"   答案: {answer}")
        
        return "\n".join(lines)
    
    def get_related_files(self, query: str) -> List[str]:
        """
        获取与查询相关的文件列表
        
        Args:
            query: 查询字符串
            
        Returns:
            相关文件路径列表
        """
        # TODO: 实现基于知识图谱的文件关联检索
        # 当前返回空列表，后续可以扩展
        return []
    
    def clear_cache(self):
        """清空检索缓存"""
        self.cache.clear()
        self.logger.info("检索缓存已清空")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "cache_size": len(self.cache),
            "cached_queries": list(self.cache.keys())[:10]  # 只返回前 10 个
        }


# 便捷函数
def create_knowledge_agent(rag_system=None) -> KnowledgeAgent:
    """
    创建知识代理
    
    Args:
        rag_system: 可选的 RAG 系统实例
        
    Returns:
        KnowledgeAgent 实例
    """
    return KnowledgeAgent(rag_system=rag_system)
