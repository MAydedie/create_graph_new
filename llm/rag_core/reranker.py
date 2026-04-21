"""
Cross-encoder重排模块
功能：使用Cross-encoder对召回结果进行精排，选出最相关的片段
"""
from typing import List, Dict, Optional
import numpy as np
import os
from sentence_transformers import CrossEncoder


class Reranker:
    """重排器类"""
    
    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        """
        初始化重排器
        
        Args:
            model_name: Cross-encoder模型名称
                默认使用 cross-encoder/ms-marco-MiniLM-L-6-v2（免费开源）
        """
        self.model_name = model_name
        
        # 确保缓存目录存在
        from config.config import MODEL_CACHE_DIR
        os.environ["HF_HOME"] = str(MODEL_CACHE_DIR)
        os.environ["TRANSFORMERS_CACHE"] = str(MODEL_CACHE_DIR)
        
        print(f"正在加载Reranker模型: {model_name}")
        print(f"缓存目录: {MODEL_CACHE_DIR}")
        
        # 检查模型是否已缓存
        cache_exists = self._check_model_cache(model_name)
        if cache_exists:
            print("✓ 从缓存加载模型...")
        else:
            print("⚠ 首次运行，正在下载模型（约90MB），请耐心等待...")
        
        # 加载Cross-encoder模型（首次运行会自动下载）
        self.model = CrossEncoder(
            model_name,
            cache_folder=str(MODEL_CACHE_DIR)
        )
        
        print("✓ Reranker模型加载成功！")

    def _check_model_cache(self, model_name: str) -> bool:
        """检查模型是否已缓存"""
        from config.config import MODEL_CACHE_DIR
        model_path = MODEL_CACHE_DIR / "models--" / model_name.replace("/", "--")
        return model_path.exists()
    
    def rerank(self, query: str, documents: List[str], top_k: Optional[int] = None) -> List[Dict]:
        """
        对文档列表进行重排
        
        Args:
            query: 查询文本
            documents: 文档列表（召回结果）
            top_k: 返回top-k个结果，None表示返回全部
            
        Returns:
            重排后的结果列表，每个结果包含：
            {
                "text": 文档文本,
                "score": 相关性分数,
                "index": 原始索引
            }
        """
        if not documents:
            return []
        
        # 构建查询-文档对
        pairs = [[query, doc] for doc in documents]
        
        # 使用Cross-encoder进行评分
        print(f"正在对 {len(documents)} 个文档进行重排...")
        scores = self.model.predict(pairs)
        
        # 转换为列表（如果返回的是numpy数组）
        if isinstance(scores, np.ndarray):
            scores = scores.tolist()
        
        # 构建结果列表
        results = []
        for i, (doc, score) in enumerate(zip(documents, scores)):
            results.append({
                "text": doc,
                "score": float(score),
                "index": i
            })
        
        # 按分数降序排序（分数越高越相关）
        results.sort(key=lambda x: x["score"], reverse=True)
        
        # 返回top-k
        if top_k is not None:
            results = results[:top_k]
        
        print(f"重排完成！返回 {len(results)} 个结果")
        
        return results
    
    def rerank_with_metadata(self, query: str, retrieval_results: List[Dict], 
                            top_k: Optional[int] = None) -> List[Dict]:
        """
        对召回结果进行重排（保留元数据）
        
        Args:
            query: 查询文本
            retrieval_results: 召回结果列表，每个结果包含text和metadata
            top_k: 返回top-k个结果
            
        Returns:
            重排后的结果列表，保留原始元数据
        """
        if not retrieval_results:
            return []
        
        # 提取文本
        texts = [result.get("text", "") for result in retrieval_results]
        
        # 重排
        reranked = self.rerank(query, texts, top_k=top_k)
        
        # 将元数据合并回去
        results = []
        for reranked_item in reranked:
            original_index = reranked_item["index"]
            original_result = retrieval_results[original_index]
            
            # 合并结果
            result = {
                "text": reranked_item["text"],
                "score": reranked_item["score"],  # Cross-encoder分数
                "rerank_score": reranked_item["score"],  # 重排分数
                "original_score": original_result.get("score", 0.0),  # 原始召回分数
                "distance": original_result.get("distance", 0.0),  # 原始距离
                "metadata": original_result.get("metadata", {}),
                "id": original_result.get("id", -1),
                "original_index": original_index
            }
            results.append(result)
        
        return results
    
    def rerank_batch(self, queries: List[str], documents_list: List[List[str]], 
                    top_k: Optional[int] = None) -> List[List[Dict]]:
        """
        批量重排（多个查询，每个查询对应一个文档列表）
        
        Args:
            queries: 查询文本列表
            documents_list: 文档列表的列表，每个查询对应一个文档列表
            top_k: 每个查询返回top-k个结果
            
        Returns:
            重排结果的列表，每个查询对应一个结果列表
        """
        all_results = []
        
        for i, (query, documents) in enumerate(zip(queries, documents_list), 1):
            print(f"处理查询 {i}/{len(queries)}: {query[:50]}...")
            results = self.rerank(query, documents, top_k=top_k)
            all_results.append(results)
        
        return all_results
    
    def compare_scores(self, retrieval_results: List[Dict], reranked_results: List[Dict]) -> Dict:
        """
        比较召回和重排的分数差异
        
        Args:
            retrieval_results: 召回结果
            reranked_results: 重排结果
            
        Returns:
            比较统计信息
        """
        if not retrieval_results or not reranked_results:
            return {}
        
        # 计算原始分数的平均值
        original_scores = [r.get("score", 0.0) for r in retrieval_results]
        avg_original = sum(original_scores) / len(original_scores) if original_scores else 0.0
        
        # 计算重排分数的平均值
        rerank_scores = [r.get("rerank_score", 0.0) for r in reranked_results]
        avg_rerank = sum(rerank_scores) / len(rerank_scores) if rerank_scores else 0.0
        
        # 检查top-1是否相同
        top1_original = retrieval_results[0] if retrieval_results else None
        top1_reranked = reranked_results[0] if reranked_results else None
        top1_same = (top1_original and top1_reranked and 
                    top1_original.get("id") == top1_reranked.get("id"))
        
        return {
            "original_count": len(retrieval_results),
            "reranked_count": len(reranked_results),
            "avg_original_score": avg_original,
            "avg_rerank_score": avg_rerank,
            "top1_same": top1_same,
            "score_improvement": avg_rerank - avg_original
        }


def create_reranker(model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> Reranker:
    """
    便捷函数：创建重排器
    
    Args:
        model_name: Cross-encoder模型名称
        
    Returns:
        Reranker实例
    """
    return Reranker(model_name=model_name)


if __name__ == "__main__":
    # 测试代码
    from data_loader import load_qa_data
    from text_splitter import split_qa_data
    from embedding_model import EmbeddingModel
    from vector_db import FAISSVectorDB
    from retriever import Retriever
    import os
    
    file_path = r"资料\喜哥帮AI客服Q&A【知识库】20260119.xlsx"
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    try:
        # 步骤1: 加载索引（如果存在）
        index_path = os.path.join(data_dir, "faiss_index.bin")
        metadata_path = os.path.join(data_dir, "metadata.pkl")
        
        if os.path.exists(index_path) and os.path.exists(metadata_path):
            print("=" * 60)
            print("加载已有索引")
            print("=" * 60)
            vector_db = FAISSVectorDB.load(index_path, metadata_path)
            print(f"加载了 {vector_db.get_total_vectors()} 个向量\n")
        else:
            print("索引不存在，请先运行前面的步骤创建索引")
            exit(1)
        
        # 步骤2: 创建召回器
        print("=" * 60)
        print("步骤2: 创建召回器")
        print("=" * 60)
        embedding_model = EmbeddingModel()
        retriever = Retriever(vector_db, embedding_model)
        
        # 步骤3: 创建重排器
        print("=" * 60)
        print("步骤3: 创建重排器")
        print("=" * 60)
        reranker = Reranker()
        
        # 步骤4: 测试召回+重排流程
        print("=" * 60)
        print("步骤4: 测试召回+重排流程")
        print("=" * 60)
        
        test_queries = [
            "怎么添加货单订单？",
            "如何切换业务类型？"
        ]
        
        for query in test_queries:
            print(f"\n查询: {query}")
            print("-" * 60)
            
            # 召回（top-10）
            print("召回阶段（top-10）:")
            retrieval_results = retriever.retrieve(query, top_k=10)
            
            print(f"召回了 {len(retrieval_results)} 个结果")
            print("前3个召回结果:")
            for i, result in enumerate(retrieval_results[:3], 1):
                print(f"  {i}. 相似度: {result['score']:.4f} - {result['metadata'].get('question', 'N/A')[:50]}...")
            
            # 重排（top-3）
            print("\n重排阶段（top-3）:")
            reranked_results = reranker.rerank_with_metadata(query, retrieval_results, top_k=3)
            
            print(f"重排后返回 {len(reranked_results)} 个结果")
            print("重排后的top-3结果:")
            for i, result in enumerate(reranked_results, 1):
                print(f"  {i}. 重排分数: {result['rerank_score']:.4f} (原始: {result['original_score']:.4f})")
                print(f"     问题: {result['metadata'].get('question', 'N/A')[:50]}...")
            
            # 比较召回和重排
            print("\n比较分析:")
            comparison = reranker.compare_scores(retrieval_results, reranked_results)
            print(f"  召回结果数: {comparison['original_count']}")
            print(f"  重排结果数: {comparison['reranked_count']}")
            print(f"  平均召回分数: {comparison['avg_original_score']:.4f}")
            print(f"  平均重排分数: {comparison['avg_rerank_score']:.4f}")
            print(f"  分数提升: {comparison['score_improvement']:.4f}")
            print(f"  Top-1是否相同: {comparison['top1_same']}")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()



