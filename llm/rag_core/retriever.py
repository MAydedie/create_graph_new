"""
召回模块
功能：从向量数据库中检索最相似的K个片段
"""
from typing import List, Dict, Optional
import numpy as np
from .vector_db import FAISSVectorDB
from .embedding_model import EmbeddingModel


class Retriever:
    """召回器类"""
    
    def __init__(self, vector_db: FAISSVectorDB, embedding_model: EmbeddingModel):
        """
        初始化召回器
        
        Args:
            vector_db: FAISS向量数据库实例
            embedding_model: Embedding模型实例
        """
        self.vector_db = vector_db
        self.embedding_model = embedding_model
        print("召回器初始化完成！")
    
    def retrieve(self, query: str, top_k: int = 10) -> List[Dict]:
        """
        召回最相似的top_k个片段
        
        Args:
            query: 用户查询文本
            top_k: 返回最相似的k个结果，默认10
            
        Returns:
            结果列表，每个结果包含：
            {
                "id": 向量ID,
                "text": 文本,
                "metadata": 元数据,
                "distance": 距离值,
                "score": 相似度分数（0-1，越大越相似）
            }
        """
        # 步骤1: 将查询文本转换为向量
        query_vector = self.embedding_model.encode([query])[0]
        
        # 步骤2: 在FAISS索引中搜索
        results = self.vector_db.get_results(query_vector, k=top_k)
        
        # 步骤3: 计算相似度分数（将距离转换为相似度）
        # L2距离越小越相似，转换为0-1的分数
        for result in results:
            distance = result["distance"]
            # 将距离转换为相似度分数（使用负指数或归一化）
            # 方法1: 使用 1 / (1 + distance)
            result["score"] = 1.0 / (1.0 + distance)
            # 或者使用归一化：score = 1 - (distance / max_distance)
            # 这里使用方法1，因为更稳定
        
        return results
    
    def retrieve_batch(self, queries: List[str], top_k: int = 10) -> List[List[Dict]]:
        """
        批量召回（多个查询）
        
        Args:
            queries: 查询文本列表
            top_k: 每个查询返回的结果数量
            
        Returns:
            结果列表的列表，每个查询对应一个结果列表
        """
        # 批量向量化
        query_vectors = self.embedding_model.encode(queries)
        
        all_results = []
        for query_vector in query_vectors:
            results = self.vector_db.get_results(query_vector, k=top_k)
            
            # 计算相似度分数
            for result in results:
                distance = result["distance"]
                result["score"] = 1.0 / (1.0 + distance)
            
            all_results.append(results)
        
        return all_results
    
    def format_results(self, results: List[Dict], show_metadata: bool = True) -> str:
        """
        格式化搜索结果，便于显示
        
        Args:
            results: 搜索结果列表
            show_metadata: 是否显示元数据
            
        Returns:
            格式化后的字符串
        """
        if not results:
            return "未找到相关结果"
        
        formatted = []
        for i, result in enumerate(results, 1):
            line = f"【结果 {i}】"
            line += f"\n  相似度分数: {result['score']:.4f}"
            line += f"\n  距离: {result['distance']:.4f}"
            line += f"\n  文本: {result['text'][:200]}..."
            
            if show_metadata and result.get('metadata'):
                metadata = result['metadata']
                if metadata.get('question'):
                    line += f"\n  问题: {metadata['question'][:100]}..."
                if metadata.get('row_id'):
                    line += f"\n  行号: {metadata['row_id']}"
            
            formatted.append(line)
        
        return "\n\n".join(formatted)
    
    def get_top_result(self, query: str) -> Optional[Dict]:
        """
        获取最相似的一个结果
        
        Args:
            query: 查询文本
            
        Returns:
            最相似的结果，如果没有则返回None
        """
        results = self.retrieve(query, top_k=1)
        return results[0] if results else None


def create_retriever(vector_db: FAISSVectorDB, embedding_model: EmbeddingModel) -> Retriever:
    """
    便捷函数：创建召回器
    
    Args:
        vector_db: FAISS向量数据库实例
        embedding_model: Embedding模型实例
        
    Returns:
        Retriever实例
    """
    return Retriever(vector_db, embedding_model)


if __name__ == "__main__":
    # 测试代码
    from data_loader import load_qa_data
    from text_splitter import split_qa_data
    from embedding_model import EmbeddingModel
    from vector_db import FAISSVectorDB
    import os
    
    file_path = r"资料\喜哥帮AI客服Q&A【知识库】20260119.xlsx"
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    try:
        # 步骤1-4: 准备数据（如果索引不存在，则创建）
        index_path = os.path.join(data_dir, "faiss_index.bin")
        metadata_path = os.path.join(data_dir, "metadata.pkl")
        
        if os.path.exists(index_path) and os.path.exists(metadata_path):
            print("=" * 60)
            print("加载已有索引")
            print("=" * 60)
            vector_db = FAISSVectorDB.load(index_path, metadata_path)
            print(f"加载了 {vector_db.get_total_vectors()} 个向量\n")
        else:
            print("=" * 60)
            print("创建新索引")
            print("=" * 60)
            # 加载数据
            qa_pairs = load_qa_data(file_path)
            chunks = split_qa_data(qa_pairs, format_type="qa_pair")
            
            # 初始化模型
            embedding_model = EmbeddingModel()
            embedding_dim = embedding_model.get_embedding_dim()
            
            # 向量化
            print("向量化所有片段...")
            embeddings, texts = embedding_model.encode_chunks(chunks, batch_size=32)
            
            # 创建向量数据库
            vector_db = FAISSVectorDB(embedding_dim=embedding_dim, index_type="flat")
            metadatas = [chunk["metadata"] for chunk in chunks]
            vector_db.add_vectors(embeddings, texts, metadatas)
            
            # 保存
            vector_db.save(index_path, metadata_path)
            print(f"索引已保存，包含 {vector_db.get_total_vectors()} 个向量\n")
        
        # 步骤5: 创建召回器
        print("=" * 60)
        print("步骤5: 创建召回器")
        print("=" * 60)
        embedding_model = EmbeddingModel()
        retriever = Retriever(vector_db, embedding_model)
        
        # 步骤6: 测试召回
        print("=" * 60)
        print("步骤6: 测试召回")
        print("=" * 60)
        
        test_queries = [
            "怎么添加货单订单？",
            "如何切换业务类型？",
            "怎么修改公司名称？"
        ]
        
        for query in test_queries:
            print(f"\n查询: {query}")
            print("-" * 60)
            
            results = retriever.retrieve(query, top_k=5)
            
            print(f"找到 {len(results)} 个相关结果:")
            for i, result in enumerate(results, 1):
                print(f"\n  【结果 {i}】")
                print(f"    相似度: {result['score']:.4f} (距离: {result['distance']:.4f})")
                print(f"    问题: {result['metadata'].get('question', 'N/A')}")
                print(f"    文本: {result['text'][:150]}...")
        
        # 步骤7: 测试批量召回
        print("\n" + "=" * 60)
        print("步骤7: 测试批量召回")
        print("=" * 60)
        batch_results = retriever.retrieve_batch(test_queries, top_k=3)
        
        for i, (query, results) in enumerate(zip(test_queries, batch_results), 1):
            print(f"\n查询 {i}: {query}")
            print(f"找到 {len(results)} 个结果")
            if results:
                print(f"最相似结果: {results[0]['metadata'].get('question', 'N/A')}")
                print(f"相似度: {results[0]['score']:.4f}")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()



