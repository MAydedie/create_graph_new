#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Graph RAG System - 基于代码图谱的问答系统
专门用于从代码图谱知识库中检索和回答问题
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any
import logging
from datetime import datetime

# 确定项目根目录
# 尝试多种方式确定根目录，确保路径正确
def _find_project_root() -> Path:
    # 方式1: 从当前文件位置向上查找
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "config" / "config.py").exists():
            return current
        current = current.parent
    
    # 方式2: 从 PYTHONPATH 查找
    for path in sys.path:
        p = Path(path)
        if (p / "config" / "config.py").exists():
            return p
    
    # 方式3: 从当前工作目录
    cwd = Path.cwd()
    if (cwd / "config" / "config.py").exists():
        return cwd
    
    raise RuntimeError("无法确定项目根目录")

PROJECT_ROOT = _find_project_root()
sys.path.insert(0, str(PROJECT_ROOT))

from config.config import (
    EMBEDDING_CONFIG, VECTOR_DB_CONFIG, RAG_CONFIG,
    RERANKER_CONFIG, DEEPSEEK_API_KEY
)
from llm.rag_core.embedding_model import EmbeddingModel
from llm.rag_core.vector_db import FAISSVectorDB
from llm.rag_core.retriever import Retriever
from llm.rag_core.reranker import Reranker
from llm.rag_core.llm_api import DeepSeekAPI



class GraphRAGSystem:
    """基于代码图谱的 RAG 系统"""
    
    def __init__(self, 
                 index_path: str = None,
                 metadata_path: str = None):
        """
        初始化 Graph RAG 系统
        
        Args:
            index_path: FAISS 索引文件路径
            metadata_path: 元数据文件路径
        """
        # 默认使用图谱索引路径
        self.index_path = index_path or str(PROJECT_ROOT / "data" / "graph_index" / "faiss.bin")
        self.metadata_path = metadata_path or str(PROJECT_ROOT / "data" / "graph_index" / "meta.pkl")
        
        self._setup_logging()
        self._initialize_components()
    
    def _setup_logging(self):
        """配置日志"""
        self.logger = logging.getLogger("GraphRAGSystem")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def _initialize_components(self):
        """初始化所有组件"""
        self.logger.info("=" * 60)
        self.logger.info("初始化 Graph RAG 系统")
        self.logger.info("=" * 60)
        
        # 检查索引是否存在
        if not os.path.exists(self.index_path):
            raise FileNotFoundError(f"索引文件不存在: {self.index_path}")
        if not os.path.exists(self.metadata_path):
            raise FileNotFoundError(f"元数据文件不存在: {self.metadata_path}")
        
        # 加载索引
        self.logger.info(f"加载索引: {self.index_path}")
        self.vector_db = FAISSVectorDB.load(self.index_path, self.metadata_path)
        self.logger.info(f"加载了 {self.vector_db.get_total_vectors()} 个向量")
        
        # 初始化 Embedding 模型
        self.logger.info("初始化 Embedding 模型...")
        self.embedding_model = EmbeddingModel(
            model_name=EMBEDDING_CONFIG["model_name"]
        )
        
        # 初始化召回器
        self.logger.info("初始化召回器...")
        self.retriever = Retriever(self.vector_db, self.embedding_model)
        
        # 初始化重排器
        self.logger.info("初始化重排器...")
        self.reranker = Reranker(model_name=RERANKER_CONFIG["model_name"])
        
        # 初始化 LLM API
        self.logger.info("初始化 LLM API...")
        self.llm_api = DeepSeekAPI()
        
        self.logger.info("Graph RAG 系统初始化完成！")
    
    def _build_context(self, results: List[Dict]) -> str:
        """
        构建提供给 LLM 的上下文
        
        Args:
            results: 检索结果列表
            
        Returns:
            格式化的上下文文本
        """
        context_parts = []
        for i, r in enumerate(results, 1):
            text = r.get("text", "")
            metadata = r.get("metadata", {})
            source_type = metadata.get("type", "unknown")
            
            context_parts.append(f"【知识块 {i}】({source_type})")
            context_parts.append(text)
            context_parts.append("-" * 40)
        
        return "\n".join(context_parts)
    
    def _build_prompt(self, question: str, context: str) -> str:
        """
        构建 LLM 提示词
        
        Args:
            question: 用户问题
            context: 检索到的上下文
            
        Returns:
            完整的提示词
        """
        prompt = f"""你是一个专业的代码分析助手。请根据以下代码知识库中的信息来回答用户的问题。

## 代码知识库上下文

{context}

## 用户问题

{question}

## 回答要求

1. 基于上下文中的代码知识来回答问题
2. 如果涉及到具体的类或方法，请说明它们的位置（文件和行号）
3. 如果涉及到功能路径（调用链），请清晰地描述调用流程
4. 如果上下文中没有相关信息，请明确说明
5. 回答要简洁准确，使用中文

请回答："""
        return prompt
    
    def query(self, 
              question: str, 
              retrieval_top_k: int = None,
              rerank_top_k: int = None,
              return_context: bool = False,
              timeout: int = 120) -> Dict[str, Any]:
        """
        查询问答
        
        Args:
            question: 用户问题
            retrieval_top_k: 召回数量
            rerank_top_k: 重排后返回数量
            return_context: 是否返回上下文信息
            timeout: LLM生成超时时间（秒）
            
        Returns:
            包含答案的字典
        """
        self.logger.info("=" * 60)
        self.logger.info(f"用户查询: {question}")
        self.logger.info("=" * 60)
        
        retrieval_top_k = retrieval_top_k or RAG_CONFIG["retrieval_top_k"]
        rerank_top_k = rerank_top_k or RAG_CONFIG["rerank_top_k"]
        
        # 步骤1: 召回
        self.logger.info(f"步骤1: 召回 (top_k={retrieval_top_k})")
        retrieval_results = self.retriever.retrieve(question, top_k=retrieval_top_k)
        self.logger.info(f"召回了 {len(retrieval_results)} 个结果")
        
        if not retrieval_results:
            return {
                "answer": "抱歉，在代码知识库中没有找到相关信息。",
                "retrieval_count": 0,
                "rerank_count": 0
            }
        
        # 步骤2: 重排
        self.logger.info(f"步骤2: 重排 (top_k={rerank_top_k})")
        reranked_results = self.reranker.rerank_with_metadata(
            question,
            retrieval_results,
            top_k=rerank_top_k
        )
        self.logger.info(f"重排后返回 {len(reranked_results)} 个结果")
        
        # 步骤3: 构建上下文
        context = self._build_context(reranked_results)
        
        # 步骤4: 生成答案
        self.logger.info("步骤3: 生成答案")
        try:
            prompt = self._build_prompt(question, context)
            # chat() expects messages list, not a string
            messages = [{"role": "user", "content": prompt}]
            response = self.llm_api.chat(messages, timeout=timeout)
            # Extract answer from response
            if "choices" in response and len(response["choices"]) > 0:
                answer = response["choices"][0].get("message", {}).get("content", "生成答案失败")
            else:
                answer = response.get("content", "生成答案失败")
            self.logger.info("答案生成成功")
        except Exception as e:
            self.logger.error(f"生成答案失败: {e}")
            answer = f"抱歉，生成答案时出现错误: {str(e)}"
        
        # 构建返回结果
        result = {
            "answer": answer,
            "retrieval_count": len(retrieval_results),
            "rerank_count": len(reranked_results)
        }
        
        if return_context:
            result["context"] = [
                {
                    "text": r.get("text", "")[:200] + "...",
                    "type": r.get("metadata", {}).get("type", "unknown"),
                    "score": r.get("rerank_score", 0.0)
                }
                for r in reranked_results
            ]
        
        return result
    
    def retrieve_only(self, 
                      question: str, 
                      top_k: int = 10) -> List[Dict]:
        """
        仅检索，不生成答案（用于调试和测试）
        
        Args:
            question: 查询问题
            top_k: 返回数量
            
        Returns:
            检索结果列表
        """
        results = self.retriever.retrieve(question, top_k=top_k)
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        return {
            "total_vectors": self.vector_db.get_total_vectors(),
            "embedding_model": EMBEDDING_CONFIG["model_name"],
            "index_path": self.index_path,
            "retrieval_top_k": RAG_CONFIG["retrieval_top_k"],
            "rerank_top_k": RAG_CONFIG["rerank_top_k"]
        }


def create_graph_rag_system(project_name: str = None) -> GraphRAGSystem:
    """
    便捷函数：创建 Graph RAG 系统
    
    Args:
        project_name: 项目名称，用于加载对应的索引目录
                      如 'catnet' -> data/catnet_index/
                      默认为 None，使用 data/graph_index/
    """
    if project_name and project_name != 'self':
        index_dir = PROJECT_ROOT / "data" / f"{project_name}_index"
        index_path = str(index_dir / "faiss.bin")
        metadata_path = str(index_dir / "meta.pkl")
        return GraphRAGSystem(index_path=index_path, metadata_path=metadata_path)
    else:
        return GraphRAGSystem()


# 命令行测试入口
if __name__ == "__main__":
    import os
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    
    print("=" * 60)
    print("Graph RAG System 交互式测试")
    print("=" * 60)
    
    try:
        rag = create_graph_rag_system()
        print(f"\n统计信息: {rag.get_statistics()}")
        
        print("\n输入问题进行测试（输入 'quit' 退出）：")
        while True:
            question = input("\n问题: ").strip()
            if question.lower() in ['quit', 'exit', 'q']:
                break
            if not question:
                continue
            
            result = rag.query(question, return_context=True)
            print("\n" + "=" * 40)
            print("答案:")
            print(result["answer"])
            print(f"\n召回: {result['retrieval_count']}, 重排后: {result['rerank_count']}")
            
    except Exception as e:
        print(f"初始化失败: {e}")
        import traceback
        traceback.print_exc()
