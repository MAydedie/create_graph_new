"""
Embedding模型模块
功能：加载Embedding模型，将文本转换为向量
"""
from pathlib import Path
from typing import List, Union, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
import os
import pickle


class EmbeddingModel:
    """Embedding模型类"""
    
    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        device: Optional[str] = None,
        allow_remote_download: bool = True,
        local_model_dir: Optional[str] = None,
        prefer_local: bool = True,
    ):
        """
        初始化Embedding模型
        
        Args:
            model_name: 模型名称，默认使用BAAI/bge-small-zh-v1.5（中文优化）
            device: 设备类型，None表示自动选择（优先GPU，否则CPU）
            allow_remote_download: 是否允许联网下载模型，False 时仅使用本地缓存
            local_model_dir: 本地模型目录，存在时优先从目录加载
            prefer_local: 是否优先使用 local_model_dir
        """
        from config.config import EMBEDDING_CONFIG, MODEL_CACHE_DIR

        configured_model_name = str(EMBEDDING_CONFIG.get("model_name") or model_name).strip()
        configured_allow_remote = bool(EMBEDDING_CONFIG.get("allow_remote_download", allow_remote_download))
        configured_prefer_local = bool(EMBEDDING_CONFIG.get("prefer_local", prefer_local))
        configured_local_dir = str(EMBEDDING_CONFIG.get("local_model_dir") or local_model_dir or "").strip()

        self.model_name = str(model_name or configured_model_name).strip() or "BAAI/bge-small-zh-v1.5"
        self.allow_remote_download = bool(allow_remote_download if allow_remote_download is not None else configured_allow_remote)
        self.prefer_local = bool(prefer_local if prefer_local is not None else configured_prefer_local)
        self.local_model_dir = str(local_model_dir or configured_local_dir).strip()

        load_target = self.model_name
        local_dir_exists = False
        if self.local_model_dir:
            local_dir_exists = Path(self.local_model_dir).is_dir()
            if self.prefer_local and local_dir_exists:
                load_target = self.local_model_dir
            elif self.prefer_local and not self.allow_remote_download:
                raise RuntimeError(
                    f"Embedding本地模型目录不存在: {self.local_model_dir}。离线模式已开启，无法联网下载。"
                )
        
        # 确保缓存目录存在
        os.environ["HF_HOME"] = str(MODEL_CACHE_DIR)
        os.environ["TRANSFORMERS_CACHE"] = str(MODEL_CACHE_DIR)
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(MODEL_CACHE_DIR)
        
        print(f"正在加载Embedding模型: {load_target}")
        print(f"缓存目录: {MODEL_CACHE_DIR}")
        
        # 检查模型是否已缓存
        cache_exists = self._check_model_cache(load_target)
        if cache_exists:
            print("✓ 从缓存加载模型...")
        else:
            if self.allow_remote_download:
                print("⚠ 首次运行，正在下载模型（约400MB），请耐心等待...")
            else:
                raise RuntimeError(
                    f"Embedding模型缓存缺失: {load_target}。当前为离线模式，已禁用远程下载。"
                )
        
        try:
             # 加载模型（会自动使用缓存）
             self.model = SentenceTransformer(
                 load_target,
                 device=device,
                 cache_folder=str(MODEL_CACHE_DIR),
                 local_files_only=not self.allow_remote_download,
             )
        except Exception as e:
             print(f"模型加载失败: {e}")
             if not self.allow_remote_download:
                 raise
             print("尝试使用默认配置重试...")
             self.model = SentenceTransformer(load_target, device=device, local_files_only=False)
        
        # 获取向量维度
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        
        print(f"✓ 模型加载成功！")
        print(f"向量维度: {self.embedding_dim}")

    def _check_model_cache(self, model_name: str) -> bool:
        """检查模型是否已缓存"""
        from config.config import MODEL_CACHE_DIR
        maybe_local = Path(str(model_name))
        if maybe_local.is_dir():
            return True
        # HuggingFace 缓存目录格式：models--org--name
        model_dir_name = f"models--{model_name.replace('/', '--')}"
        model_path = MODEL_CACHE_DIR / model_dir_name
        if not model_path.exists():
            return False
        snapshots_dir = model_path / "snapshots"
        if not snapshots_dir.exists():
            return False
        try:
            return any(snapshots_dir.iterdir())
        except Exception:
            return False
    
    def encode(self, texts: Union[str, List[str]], batch_size: int = 32, 
               show_progress: bool = True, normalize_embeddings: bool = True) -> np.ndarray:
        """
        将文本编码为向量
        
        Args:
            texts: 单个文本或文本列表
            batch_size: 批处理大小，默认32
            show_progress: 是否显示进度条
            normalize_embeddings: 是否归一化向量（L2归一化），默认True（推荐）
            
        Returns:
            向量数组，形状为 (n, embedding_dim) 或 (embedding_dim,)
        """
        # 确保输入是列表
        if isinstance(texts, str):
            texts = [texts]
        
        if not texts:
            raise ValueError("文本列表不能为空")
        
        print(f"正在向量化 {len(texts)} 个文本片段...")
        
        # 使用模型编码
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=normalize_embeddings,
            convert_to_numpy=True
        )
        
        print(f"向量化完成！形状: {embeddings.shape}")
        
        return embeddings
    
    def encode_batch(self, texts: List[str], batch_size: int = 32, 
                    max_batch_memory: Optional[int] = None) -> np.ndarray:
        """
        批量编码文本（处理大批量数据，避免内存溢出）
        
        Args:
            texts: 文本列表
            batch_size: 每批处理的文本数量
            max_batch_memory: 最大批处理数量（如果设置，会限制总批次数）
            
        Returns:
            向量数组，形状为 (n, embedding_dim)
        """
        if not texts:
            return np.array([])
        
        total = len(texts)
        print(f"开始批量向量化 {total} 个文本片段...")
        print(f"批处理大小: {batch_size}")
        
        all_embeddings = []
        processed = 0
        
        # 分批处理
        for i in range(0, total, batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size
            
            print(f"处理批次 {batch_num}/{total_batches} ({len(batch_texts)} 个文本)...")
            
            # 编码当前批次
            batch_embeddings = self.encode(
                batch_texts,
                batch_size=min(batch_size, len(batch_texts)),
                show_progress=False,
                normalize_embeddings=True
            )
            
            all_embeddings.append(batch_embeddings)
            processed += len(batch_texts)
            
            # 如果设置了最大批处理数量限制
            if max_batch_memory and batch_num >= max_batch_memory:
                print(f"达到最大批处理数量限制 ({max_batch_memory})，停止处理")
                break
        
        # 合并所有批次的向量
        if all_embeddings:
            result = np.vstack(all_embeddings)
            print(f"批量向量化完成！总共处理 {processed} 个文本，向量形状: {result.shape}")
            return result
        else:
            return np.array([])
    
    def encode_chunks(self, chunks: List[dict], text_key: str = "text",
                     batch_size: int = 32) -> tuple:
        """
        对分片列表进行向量化
        
        Args:
            chunks: 分片列表，每个分片是包含"text"和"metadata"的字典
            text_key: 文本字段的键名，默认为"text"
            batch_size: 批处理大小
            
        Returns:
            (embeddings, chunk_texts): 向量数组和对应的文本列表
        """
        # 提取文本
        chunk_texts = [chunk[text_key] for chunk in chunks if text_key in chunk]
        
        if not chunk_texts:
            raise ValueError("分片列表中没有找到文本内容")
        
        # 向量化
        embeddings = self.encode_batch(chunk_texts, batch_size=batch_size)
        
        return embeddings, chunk_texts
    
    def get_embedding_dim(self) -> int:
        """
        获取向量维度
        
        Returns:
            向量维度
        """
        return self.embedding_dim
    
    def save_model_info(self, file_path: str):
        """
        保存模型信息到文件
        
        Args:
            file_path: 保存路径
        """
        info = {
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim
        }
        
        with open(file_path, 'wb') as f:
            pickle.dump(info, f)
        
        print(f"模型信息已保存到: {file_path}")


def load_embedding_model(model_name: str = "BAAI/bge-small-zh-v1.5") -> EmbeddingModel:
    """
    便捷函数：加载Embedding模型
    
    Args:
        model_name: 模型名称
        
    Returns:
        EmbeddingModel实例
    """
    return EmbeddingModel(model_name=model_name)


if __name__ == "__main__":
    # 测试代码
    from data_loader import load_qa_data
    from text_splitter import split_qa_data
    
    file_path = r"资料\喜哥帮AI客服Q&A【知识库】20260119.xlsx"
    
    try:
        # 步骤1: 加载数据
        print("=" * 60)
        print("步骤1: 加载数据")
        print("=" * 60)
        qa_pairs = load_qa_data(file_path)
        print(f"加载了 {len(qa_pairs)} 条Q&A对\n")
        
        # 步骤2: 文本分片
        print("=" * 60)
        print("步骤2: 文本分片")
        print("=" * 60)
        chunks = split_qa_data(qa_pairs, format_type="qa_pair")
        print(f"生成了 {len(chunks)} 个文本片段\n")
        
        # 步骤3: 初始化Embedding模型
        print("=" * 60)
        print("步骤3: 初始化Embedding模型")
        print("=" * 60)
        embedding_model = EmbeddingModel(model_name="BAAI/bge-small-zh-v1.5")
        print(f"向量维度: {embedding_model.get_embedding_dim()}\n")
        
        # 步骤4: 向量化（测试前10个片段）
        print("=" * 60)
        print("步骤4: 向量化测试（前10个片段）")
        print("=" * 60)
        test_chunks = chunks[:10]
        test_texts = [chunk["text"] for chunk in test_chunks]
        
        embeddings = embedding_model.encode(test_texts, batch_size=8, show_progress=True)
        
        print(f"\n向量化结果:")
        print(f"  输入文本数: {len(test_texts)}")
        print(f"  输出向量形状: {embeddings.shape}")
        print(f"  向量维度: {embeddings.shape[1]}")
        print(f"  向量类型: {type(embeddings)}")
        print(f"  向量数据类型: {embeddings.dtype}")
        
        # 显示第一个向量的部分值
        print(f"\n第一个向量的前10个值:")
        print(embeddings[0][:10])
        
        # 测试向量相似度（第一个和第二个）
        if len(embeddings) >= 2:
            similarity = np.dot(embeddings[0], embeddings[1])
            print(f"\n第一个和第二个文本的向量相似度: {similarity:.4f}")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()



