#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图谱工具 (Graph Tools)

提供给 Agent 使用的图谱查询工具：
- QueryKnowledgeGraphTool: 完整 RAG 问答
- RetrieveContextTool: 仅检索相关上下文
"""

from typing import Dict, Any, Optional
from .base import Tool, ToolInputSchema
from ..infrastructure.graph_client import GraphClient


class QueryKnowledgeGraphTool(Tool):
    """查询知识图谱工具（完整 RAG 问答）"""
    
    def __init__(self, graph_client: Optional[GraphClient] = None):
        self._graph_client = graph_client or GraphClient(lazy_init=True)
    
    @property
    def name(self) -> str:
        return "QueryKnowledgeGraph"
    
    @property
    def description(self) -> str:
        return "查询代码知识图谱，获取代码相关问题的答案。系统会自动检索相关上下文并生成答案。"
    
    @property
    def input_schema(self) -> ToolInputSchema:
        return ToolInputSchema(
            properties={
                "query": {
                    "type": "string",
                    "description": "查询问题（自然语言）"
                },
                "top_k": {
                    "type": "integer",
                    "description": "召回数量（可选，默认 10）"
                }
            },
            required=["query"]
        )
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query")
        if not query:
            return {"success": False, "error": "缺少必填参数: query"}
        
        top_k = kwargs.get("top_k", 10)
        result = self._graph_client.query_knowledge_graph(
            query=query,
            retrieval_top_k=top_k,
            return_context=True
        )
        
        if result["success"]:
            return {
                "success": True,
                "result": result["answer"],
                "retrieval_count": result.get("retrieval_count", 0),
                "rerank_count": result.get("rerank_count", 0)
            }
        else:
            return result


class RetrieveContextTool(Tool):
    """仅检索相关上下文工具"""
    
    def __init__(self, graph_client: Optional[GraphClient] = None):
        self._graph_client = graph_client or GraphClient(lazy_init=True)
    
    @property
    def name(self) -> str:
        return "RetrieveContext"
    
    @property
    def description(self) -> str:
        return "从代码知识图谱中检索与问题相关的上下文片段，不生成答案。适用于需要自己分析上下文的场景。"
    
    @property
    def input_schema(self) -> ToolInputSchema:
        return ToolInputSchema(
            properties={
                "query": {
                    "type": "string",
                    "description": "查询问题（自然语言）"
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回数量（可选，默认 10）"
                }
            },
            required=["query"]
        )
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query")
        if not query:
            return {"success": False, "error": "缺少必填参数: query"}
        
        top_k = kwargs.get("top_k", 10)
        result = self._graph_client.retrieve_only(query=query, top_k=top_k)
        
        if result["success"]:
            # 格式化输出
            formatted = []
            for i, r in enumerate(result["results"], 1):
                formatted.append(f"【上下文 {i}】({r['type']})")
                formatted.append(r["text"][:500] + "..." if len(r["text"]) > 500 else r["text"])
                formatted.append("")
            
            return {
                "success": True,
                "result": "\n".join(formatted),
                "count": result["count"]
            }
        else:
            return result


class GetGraphStatsTool(Tool):
    """获取图谱统计信息工具"""
    
    def __init__(self, graph_client: Optional[GraphClient] = None):
        self._graph_client = graph_client or GraphClient(lazy_init=True)
    
    @property
    def name(self) -> str:
        return "GetGraphStats"
    
    @property
    def description(self) -> str:
        return "获取代码知识图谱的统计信息，包括向量数量、索引路径等。"
    
    @property
    def input_schema(self) -> ToolInputSchema:
        return ToolInputSchema(
            properties={},
            required=[]
        )
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        result = self._graph_client.get_statistics()
        
        if result["success"]:
            # 格式化输出
            stats = []
            for key, value in result.items():
                if key != "success":
                    stats.append(f"{key}: {value}")
            
            return {
                "success": True,
                "result": "\n".join(stats)
            }
        else:
            return result
