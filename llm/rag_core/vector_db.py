"""
FAISS向量数据库模块
功能：使用FAISS创建向量数据库，存储文本向量和元数据
"""
import faiss
import numpy as np
import pickle
import os
import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path


class FAISSVectorDB:
    """FAISS向量数据库类"""
    
    def __init__(self, embedding_dim: int, index_type: str = "flat"):
        """
        初始化FAISS向量数据库
        
        Args:
            embedding_dim: 向量维度
            index_type: 索引类型
                - "flat": IndexFlatL2，精确搜索，适合小规模数据（<100万）
                - "ivf": IndexIVFFlat，近似搜索，适合大规模数据（>100万）
        """
        self.embedding_dim = embedding_dim
        self.index_type = index_type
        
        # 创建索引
        if index_type == "flat":
            # L2距离（欧氏距离）索引，精确搜索
            self.index = faiss.IndexFlatL2(embedding_dim)
            print(f"创建FAISS索引: IndexFlatL2 (维度: {embedding_dim})")
        elif index_type == "ivf":
            # IVF索引，需要训练，适合大规模数据
            # 这里先创建，后续需要训练
            quantizer = faiss.IndexFlatL2(embedding_dim)
            nlist = 100  # 聚类中心数量
            self.index = faiss.IndexIVFFlat(quantizer, embedding_dim, nlist)
            print(f"创建FAISS索引: IndexIVFFlat (维度: {embedding_dim}, 聚类数: {nlist})")
        else:
            raise ValueError(f"不支持的索引类型: {index_type}")
        
        # 存储元数据：id -> 文本和元数据
        self.id_to_text = {}  # id -> 文本
        self.id_to_metadata = {}  # id -> 元数据字典
        self.next_id = 0  # 下一个可用的ID
        
        print("向量数据库初始化完成！")
    
    def add_vectors(self, vectors: np.ndarray, texts: List[str], 
                   metadatas: Optional[List[Dict]] = None):
        """
        添加向量到索引
        
        Args:
            vectors: 向量数组，形状为 (n, embedding_dim)
            texts: 文本列表，长度应与vectors相同
            metadatas: 元数据列表，可选
        """
        if len(vectors) != len(texts):
            raise ValueError(f"向量数量({len(vectors)})与文本数量({len(texts)})不匹配")
        
        if metadatas and len(metadatas) != len(texts):
            raise ValueError(f"元数据数量({len(metadatas)})与文本数量({len(texts)})不匹配")
        
        # 确保向量是float32类型
        if vectors.dtype != np.float32:
            vectors = vectors.astype(np.float32)
        
        # 如果是IVF索引且未训练，需要先训练
        if self.index_type == "ivf" and not self.index.is_trained:
            print("训练IVF索引...")
            self.index.train(vectors)
            print("训练完成！")
        
        # 添加向量到索引
        start_id = self.next_id
        self.index.add(vectors)
        
        # 存储文本和元数据
        for i, text in enumerate(texts):
            current_id = start_id + i
            self.id_to_text[current_id] = text
            if metadatas:
                self.id_to_metadata[current_id] = metadatas[i]
            else:
                self.id_to_metadata[current_id] = {}
        
        self.next_id += len(vectors)
        print(f"成功添加 {len(vectors)} 个向量到索引（ID: {start_id} - {self.next_id - 1}）")
    
    def search(self, query_vector: np.ndarray, k: int = 10) -> Tuple[np.ndarray, np.ndarray]:
        """
        搜索最相似的k个向量
        
        Args:
            query_vector: 查询向量，形状为 (embedding_dim,) 或 (1, embedding_dim)
            k: 返回最相似的k个结果
            
        Returns:
            (distances, indices): 距离数组和索引数组
                - distances: 形状为 (1, k)，距离值（L2距离，越小越相似）
                - indices: 形状为 (1, k)，对应的向量ID
        """
        if self.index.ntotal == 0:
            raise ValueError("索引为空，无法搜索")
        
        # 确保查询向量是float32类型
        if query_vector.dtype != np.float32:
            query_vector = query_vector.astype(np.float32)
        
        # 确保是2D数组
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        
        # 搜索
        distances, indices = self.index.search(query_vector, min(k, self.index.ntotal))
        
        return distances, indices
    
    def get_text_by_id(self, id: int) -> str:
        """根据ID获取文本"""
        return self.id_to_text.get(id, "")
    
    def get_metadata_by_id(self, id: int) -> Dict:
        """根据ID获取元数据"""
        return self.id_to_metadata.get(id, {})
    
    def get_results(self, query_vector: np.ndarray, k: int = 10) -> List[Dict]:
        """
        搜索并返回完整结果（包含文本和元数据）
        
        Args:
            query_vector: 查询向量
            k: 返回结果数量
            
        Returns:
            结果列表，每个结果包含：
            {
                "id": 向量ID,
                "text": 文本,
                "metadata": 元数据,
                "distance": 距离值
            }
        """
        distances, indices = self.search(query_vector, k)
        
        results = []
        for i in range(len(indices[0])):
            idx = indices[0][i]
            if idx == -1:  # FAISS返回-1表示没有结果
                continue
            
            result = {
                "id": int(idx),
                "text": self.get_text_by_id(idx),
                "metadata": self.get_metadata_by_id(idx),
                "distance": float(distances[0][i])
            }
            results.append(result)
        
        return results
    
    def get_total_vectors(self) -> int:
        """获取索引中的向量总数"""
        return self.index.ntotal
    
    def save(self, index_path: str, metadata_path: str):
        """
        保存索引和元数据到文件
        
        Args:
            index_path: FAISS索引保存路径
            metadata_path: 元数据保存路径（JSON格式）
        """
        # 保存FAISS索引（处理中文路径）
        index_path = os.path.abspath(index_path)
        index_dir = os.path.dirname(index_path)
        index_filename = os.path.basename(index_path)
        
        # 切换到目录后使用相对路径（避免FAISS的中文路径问题）
        original_cwd = os.getcwd()
        try:
            os.chdir(index_dir)
            faiss.write_index(self.index, index_filename)
        finally:
            os.chdir(original_cwd)
        print(f"FAISS索引已保存到: {index_path}")
        
        # 保存元数据
        metadata_dict = {
            "id_to_text": self.id_to_text,
            "id_to_metadata": self.id_to_metadata,
            "next_id": self.next_id,
            "embedding_dim": self.embedding_dim,
            "index_type": self.index_type
        }
        
        # 使用pickle保存（因为可能包含复杂对象）
        with open(metadata_path, 'wb') as f:
            pickle.dump(metadata_dict, f)
        
        print(f"元数据已保存到: {metadata_path}")
        print(f"总共保存了 {self.index.ntotal} 个向量")
    
    @classmethod
    def load(cls, index_path: str, metadata_path: str) -> 'FAISSVectorDB':
        """
        从文件加载索引和元数据
        
        Args:
            index_path: FAISS索引文件路径
            metadata_path: 元数据文件路径
            
        Returns:
            FAISSVectorDB实例
        """
        # 加载FAISS索引（处理中文路径）
        index_path = os.path.abspath(index_path)
        index_dir = os.path.dirname(index_path)
        index_filename = os.path.basename(index_path)
        
        # 切换到目录后使用相对路径（避免FAISS的中文路径问题）
        original_cwd = os.getcwd()
        try:
            os.chdir(index_dir)
            index = faiss.read_index(index_filename)
        finally:
            os.chdir(original_cwd)
        print(f"FAISS索引已从 {index_path} 加载")
        
        # 加载元数据
        with open(metadata_path, 'rb') as f:
            metadata_dict = pickle.load(f)
        
        # 创建实例
        db = cls.__new__(cls)
        db.index = index
        db.embedding_dim = metadata_dict["embedding_dim"]
        db.index_type = metadata_dict["index_type"]
        db.id_to_text = metadata_dict["id_to_text"]
        db.id_to_metadata = metadata_dict["id_to_metadata"]
        db.next_id = metadata_dict["next_id"]
        
        print(f"元数据已从 {metadata_path} 加载")
        print(f"总共加载了 {db.index.ntotal} 个向量")
        
        return db


def create_vector_db(embedding_dim: int, index_type: str = "flat") -> FAISSVectorDB:
    """
    便捷函数：创建向量数据库
    
    Args:
        embedding_dim: 向量维度
        index_type: 索引类型
        
    Returns:
        FAISSVectorDB实例
    """
    return FAISSVectorDB(embedding_dim=embedding_dim, index_type=index_type)


if __name__ == "__main__":
    # 测试代码
    from data_loader import load_qa_data
    from text_splitter import split_qa_data
    from embedding_model import EmbeddingModel
    
    file_path = r"资料\喜哥帮AI客服Q&A【知识库】20260119.xlsx"
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    try:
        # 步骤1-3: 加载数据、分片、向量化（使用前100个片段进行测试）
        print("=" * 60)
        print("步骤1-3: 数据准备")
        print("=" * 60)
        qa_pairs = load_qa_data(file_path)
        chunks = split_qa_data(qa_pairs, format_type="qa_pair")
        test_chunks = chunks[:100]  # 测试前100个
        
        print(f"测试数据: {len(test_chunks)} 个片段\n")
        
        # 初始化Embedding模型
        embedding_model = EmbeddingModel()
        embedding_dim = embedding_model.get_embedding_dim()
        
        # 向量化
        print("=" * 60)
        print("步骤4: 向量化")
        print("=" * 60)
        embeddings, texts = embedding_model.encode_chunks(test_chunks, batch_size=32)
        print(f"向量化完成，形状: {embeddings.shape}\n")
        
        # 步骤5: 创建FAISS向量数据库
        print("=" * 60)
        print("步骤5: 创建FAISS向量数据库")
        print("=" * 60)
        vector_db = FAISSVectorDB(embedding_dim=embedding_dim, index_type="flat")
        
        # 提取元数据
        metadatas = [chunk["metadata"] for chunk in test_chunks]
        
        # 添加向量
        vector_db.add_vectors(embeddings, texts, metadatas)
        print(f"索引中的向量总数: {vector_db.get_total_vectors()}\n")
        
        # 步骤6: 测试搜索
        print("=" * 60)
        print("步骤6: 测试搜索")
        print("=" * 60)
        # 使用第一个文本作为查询
        query_text = texts[0]
        query_vector = embedding_model.encode([query_text])[0]
        
        print(f"查询文本: {query_text[:100]}...")
        results = vector_db.get_results(query_vector, k=5)
        
        print(f"\n找到 {len(results)} 个相似结果:")
        for i, result in enumerate(results, 1):
            print(f"\n【结果 {i}】")
            print(f"  ID: {result['id']}")
            print(f"  距离: {result['distance']:.4f}")
            print(f"  文本: {result['text'][:150]}...")
            print(f"  问题: {result['metadata'].get('question', 'N/A')[:50]}...")
        
        # 步骤7: 测试保存和加载
        print("\n" + "=" * 60)
        print("步骤7: 测试保存和加载")
        print("=" * 60)
        index_path = os.path.join(data_dir, "faiss_index.bin")
        metadata_path = os.path.join(data_dir, "metadata.pkl")
        
        # 保存
        vector_db.save(index_path, metadata_path)
        
        # 加载
        print("\n重新加载索引...")
        loaded_db = FAISSVectorDB.load(index_path, metadata_path)
        print(f"加载后向量总数: {loaded_db.get_total_vectors()}")
        
        # 验证加载的索引是否可用
        test_results = loaded_db.get_results(query_vector, k=3)
        print(f"加载后搜索测试: 找到 {len(test_results)} 个结果")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()



