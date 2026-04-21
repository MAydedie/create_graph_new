"""
语义检索器模块

负责根据当前问题检索最相关的上下文单元。
支持关键词匹配和语义向量检索两种模式。
"""

import re
from typing import List, Tuple, Optional
from datetime import datetime

from .context_unit import ContextUnit


# 中文停用词（与 context_compressor 保持一致）
CHINESE_STOPWORDS = {
    "的", "了", "在", "是", "我", "你", "他", "她", "它", "这", "那",
    "和", "与", "或", "但", "如果", "因为", "所以", "虽然", "但是",
    "就", "也", "都", "还", "很", "非常", "可以", "能够", "应该",
    "会", "要", "想", "让", "把", "被", "对", "从", "到", "给",
    "吗", "呢", "啊", "吧", "呀", "哦", "哈", "嗯", "好", "不",
    "有", "没有", "什么", "怎么", "为什么", "哪里", "哪个", "谁",
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will"
}


class SemanticRetriever:
    """
    语义检索器
    
    职责：根据当前问题，检索最相关的上下文单元
    
    支持两种检索模式：
    1. 关键词匹配（默认，简单快速）
    2. 语义向量检索（需要 Embedding 模型）
    """
    
    def __init__(self, use_embeddings: bool = False):
        """
        初始化检索器
        
        Args:
            use_embeddings: 是否使用向量检索（默认 False）
        """
        self.use_embeddings = use_embeddings
        # 可选：向量索引（如 FAISS）
        self.vector_index = None
    
    def retrieve_relevant_units(
        self,
        query: str,
        units: List[ContextUnit],
        top_k: int = 3
    ) -> List[ContextUnit]:
        """
        检索最相关的单元
        
        Args:
            query: 查询字符串（当前问题）
            units: 所有可用的上下文单元
            top_k: 返回的最大单元数
            
        Returns:
            按相关性排序的单元列表
        """
        if not units:
            return []
        
        if self.use_embeddings and self.vector_index is not None:
            return self._retrieve_by_embedding(query, units, top_k)
        else:
            return self._retrieve_by_keywords(query, units, top_k)
    
    def _retrieve_by_keywords(
        self,
        query: str,
        units: List[ContextUnit],
        top_k: int
    ) -> List[ContextUnit]:
        """
        基于关键词匹配检索
        
        算法：
        1. 提取查询关键词
        2. 计算每个单元的相关性得分
        3. 结合时间衰减因子
        4. 返回得分最高的 top_k 个单元
        
        Args:
            query: 查询字符串
            units: 所有单元
            top_k: 返回数量
            
        Returns:
            相关单元列表
        """
        query_keywords = set(self._extract_keywords(query))
        
        if not query_keywords:
            # 如果没有提取到关键词，返回最近的单元
            sorted_units = sorted(units, key=lambda u: u.timestamp, reverse=True)
            return sorted_units[:top_k]
        
        # 计算每个单元的相关性得分
        scored_units: List[Tuple[float, ContextUnit]] = []
        
        for unit in units:
            score = self._calculate_relevance_score(query_keywords, unit)
            if score > 0:
                scored_units.append((score, unit))
        
        # 按得分排序
        scored_units.sort(reverse=True, key=lambda x: x[0])
        
        # 返回 top_k
        return [unit for score, unit in scored_units[:top_k]]
    
    def _calculate_relevance_score(
        self,
        query_keywords: set,
        unit: ContextUnit
    ) -> float:
        """
        计算单元与查询的相关性得分
        
        考虑因素：
        1. 关键词重叠度
        2. 主题匹配
        3. 摘要匹配
        4. 时间衰减
        
        Args:
            query_keywords: 查询关键词集合
            unit: 上下文单元
            
        Returns:
            相关性得分
        """
        score = 0.0
        
        # 1. 关键词重叠度（权重：1.0）
        unit_keywords = set(unit.keywords)
        keyword_overlap = len(query_keywords & unit_keywords)
        score += keyword_overlap * 1.0
        
        # 2. 主题匹配（权重：2.0）
        topic_keywords = set(self._extract_keywords(unit.topic))
        topic_overlap = len(query_keywords & topic_keywords)
        score += topic_overlap * 2.0
        
        # 3. 摘要匹配（权重：1.5）
        summary_keywords = set(self._extract_keywords(unit.summary))
        summary_overlap = len(query_keywords & summary_keywords)
        score += summary_overlap * 1.5
        
        # 4. 时间衰减因子（越新越重要）
        # 每天衰减 10%，但最低保留 50%
        days_old = (datetime.now() - unit.timestamp).days
        time_factor = max(0.5, 1.0 - (days_old * 0.1))
        score *= time_factor
        
        return score
    
    def _retrieve_by_embedding(
        self,
        query: str,
        units: List[ContextUnit],
        top_k: int
    ) -> List[ContextUnit]:
        """
        基于语义向量检索（高级版本）
        
        需要：
        1. Embedding 模型
        2. 向量索引（如 FAISS）
        
        Args:
            query: 查询字符串
            units: 所有单元
            top_k: 返回数量
            
        Returns:
            相关单元列表
        """
        # TODO: 实现向量检索
        # 1. 将 query 转换为向量
        # 2. 在 vector_index 中搜索最近邻
        # 3. 返回对应的 units
        
        # 暂时降级到关键词检索
        return self._retrieve_by_keywords(query, units, top_k)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        提取关键词
        
        改进：对中文进行更细粒度的分词处理
        
        Args:
            text: 原始文本
            
        Returns:
            关键词列表
        """
        keywords = []
        
        # 提取英文词语
        english_words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text.lower())
        keywords.extend([w for w in english_words if w not in CHINESE_STOPWORDS and len(w) > 1])
        
        # 提取中文词语（使用多种策略）
        chinese_text = re.findall(r'[\u4e00-\u9fff]+', text)
        
        for segment in chinese_text:
            # 策略1：整个中文片段（如果不是停用词）
            if len(segment) >= 2 and segment not in CHINESE_STOPWORDS:
                keywords.append(segment)
            
            # 策略2：2-gram（双字词）
            if len(segment) >= 2:
                for i in range(len(segment) - 1):
                    bigram = segment[i:i+2]
                    if bigram not in CHINESE_STOPWORDS:
                        keywords.append(bigram)
            
            # 策略3：单个重要字符（常见的名词、动词词根）
            for char in segment:
                if char not in CHINESE_STOPWORDS and char not in "一二三四五六七八九十个":
                    keywords.append(char)
        
        return keywords
    
    def get_context_string(
        self,
        query: str,
        units: List[ContextUnit],
        max_units: int = 3,
        include_full_content: bool = False
    ) -> str:
        """
        获取格式化的上下文字符串（直接用于 Prompt）
        
        Args:
            query: 查询字符串
            units: 所有单元
            max_units: 最大单元数
            include_full_content: 是否包含完整对话内容
            
        Returns:
            格式化的上下文字符串
        """
        relevant_units = self.retrieve_relevant_units(query, units, max_units)
        
        if not relevant_units:
            return ""
        
        lines = ["【相关对话上下文】"]
        
        for unit in relevant_units:
            if include_full_content:
                lines.append(unit.to_full_string())
            else:
                lines.append(unit.to_context_string())
        
        return "\n".join(lines)
    
    def build_vector_index(self, units: List[ContextUnit]) -> None:
        """
        构建向量索引（用于加速向量检索）
        
        Args:
            units: 需要索引的单元列表
        """
        # TODO: 实现向量索引构建
        # 1. 检查所有单元是否有 embedding
        # 2. 使用 FAISS 或其他向量库构建索引
        pass
    
    def update_vector_index(self, unit: ContextUnit) -> None:
        """
        更新向量索引（添加新单元）
        
        Args:
            unit: 新的单元
        """
        # TODO: 实现增量索引更新
        pass
