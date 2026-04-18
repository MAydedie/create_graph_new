#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
获取每个RAG系统对每个问题的详细答案
"""

import os
import sys
import json

# 设置编码
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
os.environ["PYTHONIOENCODING"] = "utf-8"

PROJECT_ROOT = r"D:\代码仓库生图\create_graph"
sys.path.insert(0, PROJECT_ROOT)

from llm.capability.graph_rag_system import GraphRAGSystem

# 测试问题（完整版）
TEST_QUESTIONS = [
    # ===== 类别一：代码知识查询 =====
    {"category": "代码知识查询", "question": "CAT-Net的网络架构是怎样的？"},
    {"category": "代码知识查询", "question": "DCT stream和Full stream有什么区别？"},
    {"category": "代码知识查询", "question": "如何训练CAT-Net模型？"},
    {"category": "代码知识查询", "question": "如何使用CAT-Net进行推理？"},
    {"category": "代码知识查询", "question": "CASIA数据集是如何加载的？"},

    # ===== 类别二：知识迁移 =====
    {"category": "知识迁移", "question": "我想检测视频中的篡改，有什么建议？"},
    {"category": "知识迁移", "question": "如何检测GAN生成的假图像？"},
    {"category": "知识迁移", "question": "帮我写一个提取JPEG DCT系数的代码"},

    # ===== 类别三：项目自身修改 =====
    {"category": "项目自身修改", "question": "如何提高模型的推理速度？"},
    {"category": "项目自身修改", "question": "如何添加对视频输入的支持？"},
    {"category": "项目自身修改", "question": "如何提高分割精度？"},

    # ===== 类别四：全局理解 =====
    {"category": "全局理解", "question": "CAT-Net的核心创新点是什么？"},
    {"category": "全局理解", "question": "这个项目解决了什么痛点？"},
    {"category": "全局理解", "question": "CAT-Net v1和v2有什么区别？"},

    # ===== 类别五：对比分析 =====
    {"category": "对比分析", "question": "CAT-Net和U-Net相比有什么优势？"},
    {"category": "对比分析", "question": "双流结构和单流结构哪个好？"},
]

# 实验配置
EXPERIMENTS = [
    {"name": "Naive RAG", "top_k": 10, "use_rerank": False},
    {"name": "GraphRAG", "top_k": 10, "use_rerank": True},
    {"name": "扩大召回", "top_k": 20, "use_rerank": True},
    {"name": "精简召回", "top_k": 5, "use_rerank": True},
]


def run_question(rag, question, top_k, use_rerank):
    """运行单个问题"""
    try:
        result = rag.query(
            question,
            retrieval_top_k=top_k,
            rerank_top_k=min(5, top_k),
            return_context=True
        )
        return result["answer"]
    except Exception as e:
        return f"错误: {str(e)}"


def main():
    print("初始化 GraphRAG System...")
    rag = GraphRAGSystem()
    print(f"向量数量: {rag.get_statistics()['total_vectors']}")
    print()

    all_results = {}

    for exp in EXPERIMENTS:
        print(f"=== {exp['name']} ===")
        answers = {}
        for i, tc in enumerate(TEST_QUESTIONS, 1):
            print(f"[{i}/{len(TEST_QUESTIONS)}] {tc['question'][:30]}...", end=" ", flush=True)
            answer = run_question(rag, tc["question"], exp["top_k"], exp["use_rerank"])
            answers[tc["question"]] = {
                "category": tc["category"],
                "answer": answer
            }
            print("✓")
        all_results[exp["name"]] = answers
        print()

    # 保存JSON
    output_file = r"D:\代码仓库生图\汇报\3.4\3.4任务完结\详细任务规划\T3_all_answers.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"答案已保存到: {output_file}")


if __name__ == "__main__":
    main()
