#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
认知层 (Cognitive Layer)

Phase 3.5 增强版 - 语义化上下文记忆系统
Phase 4 新增 - KnowledgeAgent, MemoryAgent

组件：
- ContextUnit: 上下文单元（语义化对话块）
- ContextCompressor: 上下文压缩器（切分 + 摘要）
- SemanticRetriever: 语义检索器（按需加载）
- ConversationMemory: 会话记忆（跨轮对话）
- AgentMemory: Agent 执行记忆（单次任务）
- KnowledgeAgent: 知识代理（封装 RAG）
- MemoryAgent: 记忆代理（封装 Memory）
"""

from .context_unit import ContextUnit
from .context_compressor import ContextCompressor
from .semantic_retriever import SemanticRetriever
from .memory import AgentMemory, ConversationMemory, Memory

# Phase 4 新增
from .knowledge_agent import KnowledgeAgent, create_knowledge_agent
from .memory_agent import MemoryAgent, create_memory_agent

__all__ = [
    "ContextUnit",
    "ContextCompressor", 
    "SemanticRetriever",
    "AgentMemory",
    "ConversationMemory",
    "Memory",  # 向后兼容
    # Phase 4 新增
    "KnowledgeAgent",
    "create_knowledge_agent",
    "MemoryAgent",
    "create_memory_agent",
]


