#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图谱客户端 (GraphClient)

封装现有的 GraphRAGSystem，为 Agent 提供统一的图谱查询接口。
仅调用现有实现，不做修改。
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging


logger = logging.getLogger("GraphClient")


def _find_project_root() -> Path:
    """查找项目根目录"""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "config" / "config.py").exists():
            return current
        current = current.parent
    return Path.cwd()


class GraphClient:
    """
    图谱客户端
    
    封装 GraphRAGSystem，提供简化的接口给 Agent 使用。
    只调用原有实现，不做任何修改。
    """
    
    def __init__(self, lazy_init: bool = True):
        """
        初始化图谱客户端
        
        Args:
            lazy_init: 是否延迟初始化（默认 True）
                      设为 True 时，只有在第一次调用时才初始化 RAG 系统
        """
        self._rag_system = None
        self._lazy_init = lazy_init
        self._initialized = False
        self.logger = logging.getLogger("GraphClient")
        
        # 确保项目路径在 sys.path 中
        project_root = _find_project_root()
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        if not lazy_init:
            self._initialize()
    
    def _initialize(self) -> None:
        """初始化 RAG 系统"""
        if self._initialized:
            return
        
        try:
            self.logger.info("初始化 GraphClient...")
            
            # 设置 HuggingFace 镜像（如果需要）
            if not os.environ.get("HF_ENDPOINT"):
                os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
            
            # 导入并创建 RAG 系统
            from llm.capability.graph_rag_system import create_graph_rag_system
            self._rag_system = create_graph_rag_system()
            self._initialized = True
            self.logger.info("GraphClient 初始化完成")
        except Exception as e:
            self.logger.error(f"GraphClient 初始化失败: {e}")
            raise
    
    def _ensure_initialized(self) -> None:
        """确保系统已初始化"""
        if not self._initialized:
            self._initialize()
    
    def query_knowledge_graph(
        self,
        query: str,
        retrieval_top_k: int = 10,
        rerank_top_k: int = 5,
        return_context: bool = False,
        timeout: int = 120
    ) -> Dict[str, Any]:
        """
        查询知识图谱（完整 RAG 问答）
        
        Args:
            query: 查询问题
            retrieval_top_k: 召回数量
            rerank_top_k: 重排后返回数量
            return_context: 是否返回上下文信息
            timeout: LLM 生成超时时间（秒）
            
        Returns:
            包含以下字段的字典：
            - success: bool
            - answer: str
            - retrieval_count: int
            - rerank_count: int
            - context: List[Dict] (如果 return_context=True)
            - error: str (失败时)
        """
        self._ensure_initialized()
        
        try:
            result = self._rag_system.query(
                question=query,
                retrieval_top_k=retrieval_top_k,
                rerank_top_k=rerank_top_k,
                return_context=return_context,
                timeout=timeout
            )
            
            return {
                "success": True,
                "answer": result.get("answer", ""),
                "retrieval_count": result.get("retrieval_count", 0),
                "rerank_count": result.get("rerank_count", 0),
                "context": result.get("context", []) if return_context else []
            }
        except Exception as e:
            self.logger.error(f"查询失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def retrieve_only(
        self,
        query: str,
        top_k: int = 10
    ) -> Dict[str, Any]:
        """
        仅检索，不生成答案（用于获取相关上下文）
        
        Args:
            query: 查询问题
            top_k: 返回数量
            
        Returns:
            包含以下字段的字典：
            - success: bool
            - results: List[Dict] - 检索结果列表
            - count: int - 结果数量
            - error: str (失败时)
        """
        self._ensure_initialized()
        
        try:
            results = self._rag_system.retrieve_only(
                question=query,
                top_k=top_k
            )
            
            # 格式化结果
            formatted_results = []
            for r in results:
                formatted_results.append({
                    "text": r.get("text", ""),
                    "type": r.get("metadata", {}).get("type", "unknown"),
                    "score": r.get("score", 0.0)
                })
            
            return {
                "success": True,
                "results": formatted_results,
                "count": len(formatted_results)
            }
        except Exception as e:
            self.logger.error(f"检索失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取系统统计信息
        
        Returns:
            统计信息字典
        """
        self._ensure_initialized()
        
        try:
            stats = self._rag_system.get_statistics()
            return {
                "success": True,
                **stats
            }
        except Exception as e:
            self.logger.error(f"获取统计信息失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized
