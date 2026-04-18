#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速测试脚本 - 验证迁移模块功能
用于验证 Phase 0-2 创建的新模块
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_graph_types():
    """测试图类型定义"""
    print("\n" + "="*60)
    print("测试 1: graph_types 图类型定义")
    print("="*60)
    
    from src.analysis.graph_types import (
        NodeLabel, RelationshipType, KnowledgeGraph,
        GraphNode, NodeProperties, create_node_id
    )
    
    # 创建测试节点
    props = NodeProperties(
        name="UserService",
        filePath="src/services/user.py",
        startLine=10,
        endLine=50,
        language="python"
    )
    
    node = GraphNode(
        id="Class:src/services/user.py:UserService",
        label=NodeLabel.CLASS,
        properties=props
    )
    
    print(f"✓ 创建节点: {node.id}")
    print(f"  类型: {node.label.value}")
    print(f"  属性: {node.properties.name}")
    print(f"  文件: {node.properties.filePath}")
    
    # 创建知识图谱
    kg = KnowledgeGraph()
    kg.add_node(node)
    
    print(f"✓ 知识图谱节点数: {kg.node_count}")
    print(f"✓ 图数据输出: {len(kg.to_dict()['nodes'])} 个节点")
    
    return True


def test_import_processor():
    """测试 Import 处理器"""
    print("\n" + "="*60)
    print("测试 2: import_processor Import 关系提取")
    print("="*60)
    
    from src.analysis.import_processor import ImportProcessor
    
    test_code = """
import os
import sys
from pathlib import Path
from collections import defaultdict
from myapp.utils import helper
from . import local_module
from ..Parent import ParentClass
"""
    
    processor = ImportProcessor('.')
    imports = processor._extract_imports_regex(test_code)
    
    print(f"✓ 提取到 {len(imports)} 个导入:")
    for imp in imports:
        print(f"  - {imp.name} (from={imp.is_from}, relative={imp.is_relative})")
    
    return True


def test_relationship_enhancer():
    """测试关系增强器"""
    print("\n" + "="*60)
    print("测试 3: relationship_enhancer 关系置信度")
    print("="*60)
    
    from src.analysis.relationship_enhancer import RelationshipEnhancer
    
    enhancer = RelationshipEnhancer()
    
    test_rels = [
        {'type': 'calls', 'source': 'UserService.login', 'target': 'auth_helper', 'reason': 'import-resolved'},
        {'type': 'calls', 'source': 'UserService.login', 'target': 'os.path.join', 'reason': 'import-resolved'},
        {'type': 'inherits', 'source': 'ChildClass', 'target': 'ParentClass', 'parent': True},
    ]
    
    enhanced = enhancer.enhance_relationships(test_rels)
    
    print(f"✓ 增强 {len(enhanced)} 个关系:")
    for rel in enhanced:
        print(f"  - {rel.source} --[{rel.type}]--> {rel.target}")
        print(f"    置信度: {rel.confidence:.2f} ({rel.reason})")
    
    return True


def test_bm25_index():
    """测试 BM25 索引"""
    print("\n" + "="*60)
    print("测试 4: bm25_index BM25 索引")
    print("="*60)
    
    from src.search.bm25_index import CodeBM25Index
    
    documents = [
        {'id': '1', 'text': 'Python is a high-level programming language for data science'},
        {'id': '2', 'text': 'Java is a class-based object oriented programming language'},
        {'id': '3', 'text': 'Machine learning is a subset of artificial intelligence'},
        {'id': '4', 'text': 'Deep learning uses neural networks for pattern recognition'},
        {'id': '5', 'text': 'Natural language processing is part of AI and machine learning'},
    ]
    
    index = CodeBM25Index()
    index.build(documents)
    
    print(f"✓ 语料库统计: {index.get_corpus_stats()}")
    
    # 搜索
    results = index.search('Python machine learning', top_k=3)
    
    print(f"\n✓ 搜索 'Python machine learning' 结果:")
    for r in results:
        print(f"  [{r['rank']}] {r['id']}: score={r['bm25_score']:.2f}")
    
    return True


def test_hybrid_search():
    """测试混合搜索"""
    print("\n" + "="*60)
    print("测试 5: hybrid_search RRF 混合搜索")
    print("="*60)
    
    from src.search.hybrid_search import merge_with_rrf, format_hybrid_results
    
    bm25_results = [
        {'id': 'doc1', 'text': 'Python programming', 'bm25_score': 10.5},
        {'id': 'doc2', 'text': 'Java inheritance', 'bm25_score': 8.2},
        {'id': 'doc3', 'text': 'Machine learning', 'bm25_score': 6.1},
    ]
    
    semantic_results = [
        {'id': 'doc1', 'text': 'Python programming', 'semantic_score': 0.95},
        {'id': 'doc4', 'text': 'Neural networks', 'semantic_score': 0.88},
    ]
    
    results = merge_with_rrf(bm25_results, semantic_results, limit=5)
    
    print("✓ RRF 融合结果:")
    for r in results:
        sources = '+'.join(r.sources)
        print(f"  [{r.rank}] {r.id}: score={r.score:.4f} (来源: {sources})")
    
    return True


def main():
    """运行所有测试"""
    print("\n" + "#"*60)
    print("# 迁移模块验证测试")
    print("#"*60)
    
    tests = [
        ("graph_types", test_graph_types),
        ("import_processor", test_import_processor),
        ("relationship_enhancer", test_relationship_enhancer),
        ("bm25_index", test_bm25_index),
        ("hybrid_search", test_hybrid_search),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            success = test_fn()
            results.append((name, success, None))
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False, str(e)))
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for name, success, error in results:
        status = "✓ PASS" if success else f"✗ FAIL: {error}"
        print(f"  {name}: {status}")
    
    print(f"\n通过: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 所有测试通过！迁移模块工作正常。")
    else:
        print("\n⚠️ 部分测试失败，请检查错误信息。")


if __name__ == "__main__":
    main()
