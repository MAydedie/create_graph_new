"""
混合搜索 - RRF (Reciprocal Rank Fusion) 融合算法
移植自 GitNexus hybrid-search.ts

RRF 算法说明：
- 不需要分数归一化
- 通过排名融合多个搜索结果
- RRF_score = Σ 1/(k + rank(i))
- 标准 k=60
"""

from typing import List, Dict, Any, Optional
import math


# RRF 标准常数
RRF_K = 60


class HybridSearchResult:
    """混合搜索结果"""
    
    def __init__(
        self,
        id: str,
        score: float = 0.0,
        rank: int = 0,
        sources: Optional[List[str]] = None,
        **kwargs
    ):
        self.id = id
        self.score = score
        self.rank = rank
        self.sources = sources or []
        self.metadata = kwargs
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'score': self.score,
            'rank': self.rank,
            'sources': self.sources,
            **self.metadata
        }


def merge_with_rrf(
    bm25_results: List[Dict[str, Any]],
    semantic_results: List[Dict[str, Any]],
    limit: int = 10,
    k: int = RRF_K
) -> List[HybridSearchResult]:
    """
    使用 RRF 算法融合搜索结果
    
    Args:
        bm25_results: BM25 搜索结果
        semantic_results: 语义搜索结果
        limit: 返回数量
        k: RRF 常数
        
    Returns:
        融合后的排序结果
    """
    merged: Dict[str, HybridSearchResult] = {}
    
    # 处理 BM25 结果
    for i, r in enumerate(bm25_results):
        doc_id = r.get('id', r.get('file_path', f"bm25_{i}"))
        rrf_score = 1.0 / (k + i + 1)  # i+1 因为排名从 1 开始
        
        merged[doc_id] = HybridSearchResult(
            id=doc_id,
            score=rrf_score,
            rank=0,  # 稍后设置
            sources=['bm25'],
            bm25_score=r.get('bm25_score', 0),
            **{k: v for k, v in r.items() if k not in ['id', 'bm25_score', 'rank', 'score', 'sources']}
        )
    
    # 处理语义结果并融合
    for i, r in enumerate(semantic_results):
        doc_id = r.get('id', r.get('file_path', f"semantic_{i}"))
        rrf_score = 1.0 / (k + i + 1)
        
        if doc_id in merged:
            # 两个搜索都找到了
            existing = merged[doc_id]
            existing.score += rrf_score
            existing.sources.append('semantic')
            existing.metadata['semantic_score'] = r.get('semantic_score', r.get('score', 0))
            
            # 合并元数据
            for key, value in r.items():
                if key not in existing.metadata:
                    existing.metadata[key] = value
        else:
            # 只在语义搜索中找到
            merged[doc_id] = HybridSearchResult(
                id=doc_id,
                score=rrf_score,
                rank=0,
                sources=['semantic'],
                semantic_score=r.get('semantic_score', r.get('score', 0)),
                **{k: v for k, v in r.items() if k not in ['id', 'semantic_score', 'score', 'rank', 'sources']}
            )
    
    # 排序并返回
    sorted_results = sorted(merged.values(), key=lambda x: x.score, reverse=True)
    
    # 设置最终排名
    for i, result in enumerate(sorted_results):
        result.rank = i + 1
    
    return sorted_results[:limit]


def format_hybrid_results(
    results: List[HybridSearchResult],
    include_metadata: bool = True
) -> str:
    """
    格式化混合搜索结果为字符串
    
    Args:
        results: 混合搜索结果
        include_metadata: 是否包含元数据
        
    Returns:
        格式化的字符串
    """
    if not results:
        return 'No results found.'
    
    lines = [f"Found {len(results)} results:\n"]
    
    for i, r in enumerate(results, 1):
        sources = ' + '.join(r.sources)
        
        line = f"[{i}] {r.id}\n"
        line += f"    Score: {r.score:.4f}\n"
        line += f"    Found by: {sources}\n"
        
        if 'bm25_score' in r.metadata:
            line += f"    BM25: {r.metadata['bm25_score']:.4f}\n"
        if 'semantic_score' in r.metadata:
            line += f"    Semantic: {r.metadata['semantic_score']:.4f}\n"
        
        if include_metadata:
            for key, value in r.metadata.items():
                if key not in ['bm25_score', 'semantic_score']:
                    line += f"    {key}: {value}\n"
        
        lines.append(line)
    
    return '\n'.join(lines)


class HybridSearcher:
    """
    混合搜索引擎
    
    组合 BM25 和语义搜索的结果
    """
    
    def __init__(
        self,
        bm25_index=None,
        semantic_index=None,
        k: int = RRF_K
    ):
        """
        Args:
            bm25_index: BM25 索引实例
            semantic_index: 语义搜索索引实例
            k: RRF 常数
        """
        self.bm25_index = bm25_index
        self.semantic_index = semantic_index
        self.k = k
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        use_bm25: bool = True,
        use_semantic: bool = True
    ) -> List[HybridSearchResult]:
        """
        执行混合搜索
        
        Args:
            query: 查询字符串
            top_k: 返回数量
            use_bm25: 是否使用 BM25
            use_semantic: 是否使用语义搜索
            
        Returns:
            融合后的结果
        """
        bm25_results = []
        semantic_results = []
        
        if use_bm25 and self.bm25_index:
            try:
                bm25_results = self.bm25_index.search(query, top_k * 2)
            except Exception as e:
                print(f"BM25 search error: {e}")
        
        if use_semantic and self.semantic_index:
            try:
                semantic_results = self.semantic_index.search(query, top_k * 2)
            except Exception as e:
                print(f"Semantic search error: {e}")
        
        # 如果只有一个搜索有结果，直接返回
        if not bm25_results:
            return [
                HybridSearchResult(
                    id=r.get('id', f"semantic_{i}"),
                    score=1.0 / (self.k + i + 1),
                    rank=i+1,
                    sources=['semantic'],
                    **{k: v for k, v in r.items() if k not in ['id', 'rank', 'score', 'sources']}
                )
                for i, r in enumerate(semantic_results[:top_k])
            ]
        
        if not semantic_results:
            return [
                HybridSearchResult(
                    id=r.get('id', f"bm25_{i}"),
                    score=1.0 / (self.k + i + 1),
                    rank=i+1,
                    sources=['bm25'],
                    **{k: v for k, v in r.items() if k not in ['id', 'rank', 'score', 'sources']}
                )
                for i, r in enumerate(bm25_results[:top_k])
            ]
        
        # 使用 RRF 融合
        return merge_with_rrf(
            bm25_results,
            semantic_results,
            limit=top_k,
            k=self.k
        )


# 测试
if __name__ == '__main__':
    # 测试数据
    bm25_results = [
        {'id': 'doc1', 'text': 'Python programming language', 'bm25_score': 10.5},
        {'id': 'doc2', 'text': 'Java class inheritance', 'bm25_score': 8.2},
        {'id': 'doc3', 'text': 'Machine learning algorithms', 'bm25_score': 6.1},
    ]
    
    semantic_results = [
        {'id': 'doc1', 'text': 'Python programming language', 'semantic_score': 0.95},
        {'id': 'doc4', 'text': 'Neural networks deep learning', 'semantic_score': 0.88},
        {'id': 'doc5', 'text': 'Natural language processing', 'semantic_score': 0.82},
    ]
    
    # 融合
    results = merge_with_rrf(bm25_results, semantic_results, limit=5)
    
    print("混合搜索结果:")
    print(format_hybrid_results(results))
