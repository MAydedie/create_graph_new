"""
RAG系统主程序
功能：整合所有模块，实现端到端的RAG系统
"""
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional
import logging
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.config import (
    DEEPSEEK_API_KEY, RAG_CONFIG, DATA_CONFIG, 
    VECTOR_DB_CONFIG, EMBEDDING_CONFIG, RERANKER_CONFIG
)

from .data_loader import DataLoader, load_qa_data
from .text_splitter import QATextSplitter, split_qa_data
from .embedding_model import EmbeddingModel, load_embedding_model
from .vector_db import FAISSVectorDB, create_vector_db
from .retriever import Retriever, create_retriever
from .reranker import Reranker, create_reranker
from .llm_api import DeepSeekAPI, create_llm_api


class RAGSystem:
    """RAG系统主类"""
    
    def __init__(self, 
                 index_path: Optional[str] = None,
                 metadata_path: Optional[str] = None,
                 rebuild_index: bool = False):
        """
        初始化RAG系统
        
        Args:
            index_path: FAISS索引文件路径，如果为None则使用配置中的路径
            metadata_path: 元数据文件路径，如果为None则使用配置中的路径
            rebuild_index: 是否重建索引
        """
        self.index_path = index_path or DATA_CONFIG["faiss_index"]
        self.metadata_path = metadata_path or DATA_CONFIG["metadata_file"]
        self.rebuild_index = rebuild_index
        
        # 初始化日志
        self._setup_logging()
        
        # 初始化组件
        self.embedding_model = None
        self.vector_db = None
        self.retriever = None
        self.reranker = None
        self.llm_api = None
        
        # 加载或创建索引
        self._initialize_components()
    
    def _setup_logging(self):
        """设置日志"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"rag_system_{datetime.now().strftime('%Y%m%d')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info("RAG系统初始化开始")
    
    def _initialize_components(self):
        """初始化所有组件"""
        self.logger.info("=" * 60)
        self.logger.info("初始化RAG系统组件")
        self.logger.info("=" * 60)
        
        # 检查索引是否存在
        index_exists = os.path.exists(self.index_path) and os.path.exists(self.metadata_path)
        
        if index_exists and not self.rebuild_index:
            # 加载已有索引
            self.logger.info("加载已有索引...")
            self.vector_db = FAISSVectorDB.load(self.index_path, self.metadata_path)
            self.logger.info(f"加载了 {self.vector_db.get_total_vectors()} 个向量")
        else:
            # 创建新索引
            self.logger.info("创建新索引...")
            self._build_index()
        
        # 初始化Embedding模型
        self.logger.info("初始化Embedding模型...")
        self.embedding_model = EmbeddingModel(
            model_name=EMBEDDING_CONFIG["model_name"]
        )
        
        # 初始化召回器
        self.logger.info("初始化召回器...")
        self.retriever = Retriever(self.vector_db, self.embedding_model)
        
        # 初始化重排器
        self.logger.info("初始化重排器...")
        self.reranker = Reranker(model_name=RERANKER_CONFIG["model_name"])
        
        # 初始化LLM API
        self.logger.info("初始化LLM API...")
        self.llm_api = DeepSeekAPI()
        
        self.logger.info("所有组件初始化完成！")
    
    def _build_index(self):
        """构建索引（准备阶段）"""
        self.logger.info("=" * 60)
        self.logger.info("开始构建索引（准备阶段）")
        self.logger.info("=" * 60)
        
        # 步骤1: 加载数据
        self.logger.info("步骤1: 加载数据")
        excel_file = DATA_CONFIG["excel_file"]
        qa_pairs = load_qa_data(excel_file)
        self.logger.info(f"加载了 {len(qa_pairs)} 条Q&A对")
        
        # 步骤2: 文本分片
        self.logger.info("步骤2: 文本分片")
        chunks = split_qa_data(qa_pairs, format_type="qa_pair")
        self.logger.info(f"生成了 {len(chunks)} 个文本片段")
        
        # 步骤3: 向量化
        self.logger.info("步骤3: 向量化")
        self.embedding_model = EmbeddingModel(
            model_name=EMBEDDING_CONFIG["model_name"]
        )
        embeddings, texts = self.embedding_model.encode_chunks(
            chunks, 
            batch_size=EMBEDDING_CONFIG["batch_size"]
        )
        self.logger.info(f"向量化完成，形状: {embeddings.shape}")
        
        # 步骤4: 创建向量数据库
        self.logger.info("步骤4: 创建向量数据库")
        self.vector_db = FAISSVectorDB(
            embedding_dim=VECTOR_DB_CONFIG["embedding_dim"],
            index_type=VECTOR_DB_CONFIG["index_type"]
        )
        
        # 提取元数据
        metadatas = [chunk["metadata"] for chunk in chunks]
        
        # 添加向量
        self.vector_db.add_vectors(embeddings, texts, metadatas)
        self.logger.info(f"索引创建完成，包含 {self.vector_db.get_total_vectors()} 个向量")
        
        # 步骤5: 保存索引
        self.logger.info("步骤5: 保存索引")
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        self.vector_db.save(self.index_path, self.metadata_path)
        self.logger.info("索引保存完成！")
    
    def query(self, question: str, 
             retrieval_top_k: Optional[int] = None,
             rerank_top_k: Optional[int] = None,
             return_context: bool = False,
             timeout: int = 120) -> Dict:
        """
        查询（回答阶段）
        
        Args:
            question: 用户问题
            retrieval_top_k: 召回数量，如果为None则使用配置中的值
            rerank_top_k: 重排后返回数量，如果为None则使用配置中的值
            return_context: 是否返回上下文信息
            timeout: LLM生成超时时间（秒）
            
        Returns:
            包含答案和可选上下文信息的字典
        """
        self.logger.info("=" * 60)
        self.logger.info(f"用户查询: {question}")
        self.logger.info("=" * 60)
        
        retrieval_top_k = retrieval_top_k or RAG_CONFIG["retrieval_top_k"]
        rerank_top_k = rerank_top_k or RAG_CONFIG["rerank_top_k"]
        
        # 步骤1: 召回
        self.logger.info("步骤1: 召回")
        retrieval_results = self.retriever.retrieve(question, top_k=retrieval_top_k)
        self.logger.info(f"召回了 {len(retrieval_results)} 个结果")
        
        if not retrieval_results:
            return {
                "answer": "抱歉，在知识库中没有找到相关信息。",
                "context": [],
                "retrieval_count": 0,
                "rerank_count": 0
            }
        
        # 步骤2: 重排
        self.logger.info("步骤2: 重排")
        reranked_results = self.reranker.rerank_with_metadata(
            question,
            retrieval_results,
            top_k=rerank_top_k
        )
        self.logger.info(f"重排后返回 {len(reranked_results)} 个结果")
        
        # 步骤3: 生成
        self.logger.info("步骤3: 生成答案")
        try:
            answer = self.llm_api.generate_answer(question, reranked_results, timeout=timeout)
            self.logger.info("答案生成成功")
        except Exception as e:
            self.logger.error(f"生成答案失败: {e}")
            answer = "抱歉，生成答案时出现错误，请稍后重试。"
        
        # 构建返回结果
        result = {
            "answer": answer,
            "retrieval_count": len(retrieval_results),
            "rerank_count": len(reranked_results)
        }
        
        if return_context:
            result["context"] = [
                {
                    "question": r["metadata"].get("question", ""),
                    "answer": r["metadata"].get("answer", ""),
                    "score": r.get("rerank_score", 0.0)
                }
                for r in reranked_results
            ]
        
        return result
    
    def batch_query(self, questions: List[str], 
                   retrieval_top_k: Optional[int] = None,
                   rerank_top_k: Optional[int] = None) -> List[Dict]:
        """
        批量查询
        
        Args:
            questions: 问题列表
            retrieval_top_k: 召回数量
            rerank_top_k: 重排后返回数量
            
        Returns:
            结果列表
        """
        results = []
        for i, question in enumerate(questions, 1):
            self.logger.info(f"处理查询 {i}/{len(questions)}: {question}")
            result = self.query(question, retrieval_top_k, rerank_top_k)
            results.append(result)
        return results
    
    def get_statistics(self) -> Dict:
        """获取系统统计信息"""
        stats = {
            "total_vectors": self.vector_db.get_total_vectors() if self.vector_db else 0,
            "embedding_dim": self.embedding_model.get_embedding_dim() if self.embedding_model else 0,
            "index_path": self.index_path,
            "metadata_path": self.metadata_path
        }
        return stats


def create_rag_system(rebuild_index: bool = False) -> RAGSystem:
    """
    便捷函数：创建RAG系统
    
    Args:
        rebuild_index: 是否重建索引
        
    Returns:
        RAGSystem实例
    """
    return RAGSystem(rebuild_index=rebuild_index)


if __name__ == "__main__":
    # 测试代码
    import argparse
    
    parser = argparse.ArgumentParser(description="RAG系统测试")
    parser.add_argument("--rebuild", action="store_true", help="重建索引")
    parser.add_argument("--query", type=str, help="单个查询")
    args = parser.parse_args()
    
    try:
        # 创建RAG系统
        print("=" * 60)
        print("创建RAG系统")
        print("=" * 60)
        rag = RAGSystem(rebuild_index=args.rebuild)
        
        # 显示统计信息
        stats = rag.get_statistics()
        print("\n系统统计信息:")
        print(f"  向量总数: {stats['total_vectors']}")
        print(f"  向量维度: {stats['embedding_dim']}")
        print(f"  索引路径: {stats['index_path']}")
        
        # 测试查询
        if args.query:
            print("\n" + "=" * 60)
            print("测试查询")
            print("=" * 60)
            result = rag.query(args.query, return_context=True)
            
            print(f"\n问题: {args.query}")
            print(f"\n答案:\n{result['answer']}")
            print(f"\n使用了 {result['rerank_count']} 个上下文片段")
            
            if result.get("context"):
                print("\n上下文片段:")
                for i, ctx in enumerate(result["context"], 1):
                    print(f"\n【片段 {i}】相似度: {ctx['score']:.4f}")
                    print(f"问题: {ctx['question']}")
                    print(f"答案: {ctx['answer'][:100]}...")
        else:
            # 默认测试查询
            test_queries = [
                "怎么添加货单订单？",
                "如何切换业务类型？",
                "怎么修改公司名称？"
            ]
            
            print("\n" + "=" * 60)
            print("测试查询")
            print("=" * 60)
            
            for query in test_queries:
                print(f"\n{'='*60}")
                print(f"问题: {query}")
                print('='*60)
                
                result = rag.query(query, return_context=True)
                
                print(f"\n答案:\n{result['answer']}")
                print(f"\n使用了 {result['rerank_count']} 个上下文片段")
                
                if result.get("context"):
                    print("\n上下文片段:")
                    for i, ctx in enumerate(result["context"][:2], 1):  # 只显示前2个
                        print(f"  {i}. {ctx['question']} (相似度: {ctx['score']:.4f})")
    
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


