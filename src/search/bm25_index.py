"""
BM25 全文搜索索引
移植自 GitNexus hybrid-search.ts
"""

import re
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi


class BM25Index:
    """BM25 全文搜索索引"""
    
    def __init__(self):
        self.corpus: List[str] = []
        self.metadata: List[Dict[str, Any]] = []
        self.bm25: Optional[BM25Okapi] = None
        self._tokenizer = self._default_tokenizer  # Don't call, just assign
    
    @staticmethod
    def _default_tokenizer(text: str) -> List[str]:
        """
        默认分词器
        - 转小写
        - 提取字母数字单词
        - 保留一些编程术语
        """
        # 保留常见的编程符号
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)  # camelCase -> camel Case
        text = re.sub(r'[_\-/]', ' ', text)  # snake_case -> snake case
        
        # 提取词
        tokens = re.findall(r'\b[a-z][a-z0-9]*\b', text.lower())
        
        # 过滤停用词
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
            'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these',
            'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which',
            'who', 'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both',
            'few', 'more', 'most', 'other', 'some', 'such', 'no', 'not', 'only',
            'same', 'so', 'than', 'too', 'very', 'just', 'if', 'else', 'then'
        }
        
        return [t for t in tokens if t not in stop_words and len(t) > 1]
    
    def build(
        self,
        documents: List[Dict[str, Any]],
        text_field: str = 'text',
        id_field: str = 'id'
    ) -> None:
        """
        构建 BM25 索引
        
        Args:
            documents: 文档列表
            text_field: 文本字段名
            id_field: ID 字段名
        """
        self.corpus = [doc.get(text_field, '') for doc in documents]
        self.metadata = documents
        
        # 确保所有文本都是字符串
        self.corpus = [str(t) if t else '' for t in self.corpus]
        
        tokenized_corpus = [self._tokenizer(doc) for doc in self.corpus]
        self.bm25 = BM25Okapi(tokenized_corpus)
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        搜索
        
        Args:
            query: 查询字符串
            top_k: 返回数量
            min_score: 最小分数过滤
            
        Returns:
            排序后的结果列表
        """
        if not self.bm25:
            raise ValueError("Index not built. Call build() first.")
        
        tokenized_query = self._tokenizer(query)
        scores = self.bm25.get_scores(tokenized_query)
        
        # 按分数排序
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        
        results = []
        for idx, score in ranked:
            if score <= min_score:
                continue
            if idx >= len(self.metadata):
                continue
                
            result = self.metadata[idx].copy()
            result['bm25_score'] = float(score)
            result['rank'] = len(results) + 1
            results.append(result)
            
            if len(results) >= top_k:
                break
        
        return results
    
    def get_corpus_stats(self) -> Dict[str, Any]:
        """获取语料库统计信息"""
        if not self.corpus:
            return {'doc_count': 0}
        
        total_tokens = sum(len(self._tokenizer(doc)) for doc in self.corpus)
        avg_tokens = total_tokens / len(self.corpus) if self.corpus else 0
        
        return {
            'doc_count': len(self.corpus),
            'total_tokens': total_tokens,
            'avg_tokens_per_doc': avg_tokens,
        }


class CodeBM25Index(BM25Index):
    """
    代码专用的 BM25 索引
    
    针对代码做了优化：
    - 保留函数名、类名
    - 识别编程术语
    """
    
    @staticmethod
    def _tokenizer(text: str) -> List[str]:
        """代码专用的分词器"""
        if not text:
            return []
        
        # 预处理
        # 1. camelCase -> camel Case
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        # 2. snake_case -> snake case  
        text = re.sub(r'_', ' ', text)
        # 3. 保留点号（用于模块路径）
        # 4. 提取词
        tokens = re.findall(r'\b[a-zA-Z][a-zA-Z0-9]*\b', text)
        
        # 转小写
        tokens = [t.lower() for t in tokens]
        
        # 过滤过短的词
        tokens = [t for t in tokens if len(t) > 1]
        
        return tokens


# 测试
if __name__ == '__main__':
    # 测试 BM25
    documents = [
        {'id': '1', 'text': 'Python is a high-level programming language'},
        {'id': '2', 'text': 'Java is a class-based object oriented language'},
        {'id': '3', 'text': 'Machine learning is a subset of artificial intelligence'},
        {'id': '4', 'text': 'Deep learning uses neural networks'},
        {'id': '5', 'text': 'Natural language processing is part of AI'},
    ]
    
    index = CodeBM25Index()
    index.build(documents)
    
    print("语料库统计:", index.get_corpus_stats())
    print()
    
    # 测试搜索
    results = index.search('Python programming', top_k=3)
    print("搜索 'Python programming':")
    for r in results:
        print(f"  [{r['rank']}] {r['id']}: {r['text'][:50]}... (score: {r['bm25_score']:.2f})")
