#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Graph RAG System - 问答效果测试脚本
测试典型代码问答场景
"""

import os
import sys

# 设置环境变量
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 设置项目路径
sys.path.insert(0, r"D:\代码仓库生图\create_graph")

from llm.capability.graph_rag_system import GraphRAGSystem

def run_test_cases():
    print("=" * 70)
    print("Graph RAG System - 问答效果测试")
    print("=" * 70)
    
    # 初始化系统
    print("\n[初始化] 正在加载 GraphRAGSystem...")
    rag = GraphRAGSystem()
    print(f"[初始化] 完成！向量数量: {rag.get_statistics()['total_vectors']}")
    
    # 定义测试用例
    test_cases = [
        {
            "name": "类功能查询",
            "question": "PythonParser 类的主要功能是什么？它在哪个文件中定义？",
            "expected_keywords": ["PythonParser", "解析", "python"]
        },
        {
            "name": "方法查询",
            "question": "find_entry_points 方法是做什么的？",
            "expected_keywords": ["entry", "入口"]
        },
        {
            "name": "调用链查询", 
            "question": "请描述一下代码分析的主要流程，从入口到输出是怎么调用的？",
            "expected_keywords": ["分析", "调用"]
        }
    ]
    
    # 运行测试
    results = []
    for i, tc in enumerate(test_cases, 1):
        print(f"\n{'='*70}")
        print(f"[测试 {i}/{len(test_cases)}] {tc['name']}")
        print(f"问题: {tc['question']}")
        print("-" * 70)
        
        try:
            result = rag.query(tc["question"], return_context=True)
            answer = result["answer"]
            
            print(f"\n答案:")
            print(answer[:500] + "..." if len(answer) > 500 else answer)
            print(f"\n统计: 召回={result['retrieval_count']}, 重排后={result['rerank_count']}")
            
            # 检查关键词
            found_keywords = [kw for kw in tc["expected_keywords"] if kw.lower() in answer.lower()]
            keyword_score = len(found_keywords) / len(tc["expected_keywords"])
            
            print(f"关键词覆盖: {len(found_keywords)}/{len(tc['expected_keywords'])} ({keyword_score*100:.0f}%)")
            
            results.append({
                "name": tc["name"],
                "success": True,
                "keyword_score": keyword_score,
                "retrieval_count": result["retrieval_count"],
                "rerank_count": result["rerank_count"]
            })
            
        except Exception as e:
            print(f"[错误] {e}")
            results.append({
                "name": tc["name"],
                "success": False,
                "error": str(e)
            })
    
    # 汇总结果
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    
    success_count = sum(1 for r in results if r["success"])
    print(f"成功率: {success_count}/{len(results)} ({success_count/len(results)*100:.0f}%)")
    
    for r in results:
        status = "✓" if r["success"] else "✗"
        if r["success"]:
            print(f"  {status} {r['name']}: 关键词覆盖 {r['keyword_score']*100:.0f}%")
        else:
            print(f"  {status} {r['name']}: {r.get('error', 'Unknown error')}")
    
    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)
    
    return results

if __name__ == "__main__":
    run_test_cases()
