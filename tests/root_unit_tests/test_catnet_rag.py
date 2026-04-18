#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CAT-Net 项目 - RAG 问答测试脚本
自动运行测试问题集并生成报告
"""

import os
import sys
import json
from datetime import datetime

# 设置环境变量
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 设置项目路径
PROJECT_ROOT = r"D:\代码仓库生图\create_graph"
sys.path.insert(0, PROJECT_ROOT)

from llm.capability.graph_rag_system import GraphRAGSystem


# 测试问题集 - 来自 T1_测试问题集_CATNet
TEST_QUESTIONS = [
    # ===== 类别一：代码知识查询 =====
    {
        "category": "代码知识查询",
        "question": "CAT-Net的网络架构是怎样的？",
        "expected_keywords": ["CAT-Net", "HRNet", "DCT", "网络结构"]
    },
    {
        "category": "代码知识查询",
        "question": "DCT stream和Full stream有什么区别？",
        "expected_keywords": ["DCT", "Full", "双流", "融合"]
    },
    {
        "category": "代码知识查询",
        "question": "如何训练CAT-Net模型？",
        "expected_keywords": ["train", "训练", "数据集"]
    },
    {
        "category": "代码知识查询",
        "question": "如何使用CAT-Net进行推理？",
        "expected_keywords": ["infer", "推理", "预测"]
    },
    {
        "category": "代码知识查询",
        "question": "CASIA数据集是如何加载的？",
        "expected_keywords": ["CASIA", "dataset", "数据加载"]
    },

    # ===== 类别二：知识迁移 =====
    {
        "category": "知识迁移",
        "question": "我想检测视频中的篡改，有什么建议？",
        "expected_keywords": ["视频", "篡改", "检测"]
    },
    {
        "category": "知识迁移",
        "question": "如何检测GAN生成的假图像？",
        "expected_keywords": ["GAN", "假图像", "深度伪造"]
    },
    {
        "category": "知识迁移",
        "question": "帮我写一个提取JPEG DCT系数的代码",
        "expected_keywords": ["DCT", "系数", "JPEG"]
    },

    # ===== 类别三：项目自身修改 =====
    {
        "category": "项目自身修改",
        "question": "如何提高模型的推理速度？",
        "expected_keywords": ["推理", "速度", "优化"]
    },
    {
        "category": "项目自身修改",
        "question": "如何添加对视频输入的支持？",
        "expected_keywords": ["视频", "扩展", "支持"]
    },
    {
        "category": "项目自身修改",
        "question": "如何提高分割精度？",
        "expected_keywords": ["分割", "精度", "提高"]
    },

    # ===== 类别四：全局理解 =====
    {
        "category": "全局理解",
        "question": "CAT-Net的核心创新点是什么？",
        "expected_keywords": ["创新", "压缩伪影", "DCT"]
    },
    {
        "category": "全局理解",
        "question": "这个项目解决了什么痛点？",
        "expected_keywords": ["篡改", "检测", "拼接"]
    },
    {
        "category": "全局理解",
        "question": "CAT-Net v1和v2有什么区别？",
        "expected_keywords": ["v1", "v2", "版本"]
    },

    # ===== 类别五：对比分析 =====
    {
        "category": "对比分析",
        "question": "CAT-Net和U-Net相比有什么优势？",
        "expected_keywords": ["U-Net", "优势", "对比"]
    },
    {
        "category": "对比分析",
        "question": "双流结构和单流结构哪个好？",
        "expected_keywords": ["双流", "单流", "比较"]
    },
]


def evaluate_answer(answer: str, expected_keywords: list) -> dict:
    """评估答案质量"""
    answer_lower = answer.lower()

    # 关键词匹配
    found_keywords = [kw for kw in expected_keywords if kw.lower() in answer_lower]
    keyword_score = len(found_keywords) / len(expected_keywords) if expected_keywords else 0

    # 答案长度评估
    answer_length = len(answer)
    length_score = 1.0 if 50 < answer_length < 2000 else 0.5 if answer_length > 0 else 0

    # 综合评分
   综合评分 = (keyword_score * 0.7 + length_score * 0.3)

    return {
        "keyword_score": keyword_score,
        "length_score": length_score,
        "综合评分": 综合评分,
        "found_keywords": found_keywords,
        "answer_length": answer_length
    }


def run_tests():
    """运行所有测试"""
    print("=" * 80)
    print("CAT-Net RAG 问答测试")
    print("=" * 80)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试问题数: {len(TEST_QUESTIONS)}")
    print("=" * 80)

    # 初始化系统
    print("\n[初始化] 正在加载 GraphRAGSystem...")
    try:
        rag = GraphRAGSystem()
        stats = rag.get_statistics()
        print(f"[初始化] 完成！向量数量: {stats['total_vectors']}")
    except Exception as e:
        print(f"[初始化] 失败: {e}")
        return None

    # 运行测试
    results = []
    for i, tc in enumerate(TEST_QUESTIONS, 1):
        print(f"\n[{i}/{len(TEST_QUESTIONS)}] {tc['category']}")
        print(f"问题: {tc['question']}")
        print("-" * 60)

        try:
            # 调用RAG系统
            result = rag.query(tc["question"], return_context=True)
            answer = result["answer"]

            # 评估答案
            evaluation = evaluate_answer(answer, tc["expected_keywords"])

            print(f"答案: {answer[:200]}..." if len(answer) > 200 else f"答案: {answer}")
            print(f"关键词覆盖: {evaluation['keyword_score']*100:.0f}% ({len(evaluation['found_keywords'])}/{len(tc['expected_keywords'])})")
            print(f"召回数: {result['retrieval_count']}, 重排后: {result['rerank_count']}")

            results.append({
                "category": tc["category"],
                "question": tc["question"],
                "success": True,
                "answer": answer,
                "keyword_score": evaluation['keyword_score'],
                "综合评分": evaluation['综合评分'],
                "retrieval_count": result["retrieval_count"],
                "rerank_count": result["rerank_count"],
                "answer_length": evaluation['answer_length']
            })

        except Exception as e:
            print(f"[错误] {e}")
            results.append({
                "category": tc["category"],
                "question": tc["question"],
                "success": False,
                "error": str(e)
            })

    return results


def generate_report(results):
    """生成测试报告"""
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)

    # 按类别统计
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "success": 0, "scores": []}
        categories[cat]["total"] += 1
        if r["success"]:
            categories[cat]["success"] += 1
            categories[cat]["scores"].append(r.get("keyword_score", 0))

    print("\n【按类别统计】")
    print("-" * 60)
    for cat, stats in categories.items():
        avg_score = sum(stats["scores"]) / len(stats["scores"]) * 100 if stats["scores"] else 0
        print(f"{cat}: {stats['success']}/{stats['total']} 通过, 平均关键词得分: {avg_score:.1f}%")

    # 总体统计
    success_count = sum(1 for r in results if r["success"])
    total_scores = [r.get("keyword_score", 0) for r in results if r["success"]]
    avg_score = sum(total_scores) / len(total_scores) * 100 if total_scores else 0

    print("\n【总体统计】")
    print("-" * 60)
    print(f"总问题数: {len(results)}")
    print(f"成功回答: {success_count}")
    print(f"成功率: {success_count/len(results)*100:.1f}%")
    print(f"平均关键词得分: {avg_score:.1f}%")

    # 检索统计
    retrieval_counts = [r.get("retrieval_count", 0) for r in results if r["success"]]
    if retrieval_counts:
        print(f"平均召回数: {sum(retrieval_counts)/len(retrieval_counts):.1f}")

    return {
        "total": len(results),
        "success": success_count,
        "success_rate": success_count/len(results)*100,
        "avg_keyword_score": avg_score,
        "categories": categories
    }


def save_results(results, summary):
    """保存结果到文件"""
    output_dir = os.path.join(PROJECT_ROOT, "test_reports")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"catnet_test_{timestamp}.md"
    filepath = os.path.join(output_dir, filename)

    # 生成Markdown报告
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# CAT-Net RAG 测试报告\n\n")
        f.write(f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**总问题数**: {summary['total']}\n\n")
        f.write(f"**成功率**: {summary['success_rate']:.1f}%\n\n")
        f.write(f"**平均关键词得分**: {summary['avg_keyword_score']:.1f}%\n\n")

        f.write("## 按类别统计\n\n")
        f.write("| 类别 | 通过/总数 | 平均得分 |\n")
        f.write("|------|----------|----------|\n")
        for cat, stats in summary["categories"].items():
            avg_score = sum(stats["scores"]) / len(stats["scores"]) * 100 if stats["scores"] else 0
            f.write(f"| {cat} | {stats['success']}/{stats['total']} | {avg_score:.1f}% |\n")

        f.write("\n## 详细结果\n\n")
        for i, r in enumerate(results, 1):
            f.write(f"### {i}. {r['category']}\n\n")
            f.write(f"**问题**: {r['question']}\n\n")
            if r["success"]:
                f.write(f"**关键词得分**: {r['keyword_score']*100:.0f}%\n\n")
                f.write(f"**召回数**: {r['retrieval_count']}, 重排后: {r['rerank_count']}\n\n")
                f.write(f"**答案**:\n\n{r['answer']}\n\n")
            else:
                f.write(f"**错误**: {r.get('error', 'Unknown')}\n\n")
            f.write("---\n\n")

    print(f"\n[保存] 测试报告已保存到: {filepath}")

    # 同时保存JSON
    json_filename = filepath.replace(".md", ".json")
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)
    print(f"[保存] JSON结果已保存到: {json_filename}")

    return filepath


if __name__ == "__main__":
    results = run_tests()
    if results:
        summary = generate_report(results)
        save_results(results, summary)
    else:
        print("[错误] 测试失败")
