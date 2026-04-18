#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CAT-Net 项目 - RAG 实验测试脚本
包含多种配置对比、评估指标、图表生成
"""

import os
import sys
import json
import math
from datetime import datetime
from typing import List, Dict

# 设置编码
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
os.environ["PYTHONIOENCODING"] = "utf-8"

# 设置环境变量
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 设置项目路径
PROJECT_ROOT = r"D:\代码仓库生图\create_graph"
sys.path.insert(0, PROJECT_ROOT)

from llm.capability.graph_rag_system import GraphRAGSystem
from llm.rag_core.retriever import Retriever
from llm.rag_core.reranker import Reranker


# ===== 测试问题集 =====
TEST_QUESTIONS = [
    # ===== 类别一：代码知识查询 =====
    {"category": "代码知识查询", "question": "CAT-Net的网络架构是怎样的？",
     "expected_keywords": ["CAT-Net", "HRNet", "DCT", "网络"]},
    {"category": "代码知识查询", "question": "DCT stream和Full stream有什么区别？",
     "expected_keywords": ["DCT", "Full", "双流", "融合"]},
    {"category": "代码知识查询", "question": "如何训练CAT-Net模型？",
     "expected_keywords": ["train", "训练", "数据集"]},
    {"category": "代码知识查询", "question": "如何使用CAT-Net进行推理？",
     "expected_keywords": ["infer", "推理", "预测"]},
    {"category": "代码知识查询", "question": "CASIA数据集是如何加载的？",
     "expected_keywords": ["CASIA", "dataset", "数据"]},

    # ===== 类别二：知识迁移 =====
    {"category": "知识迁移", "question": "我想检测视频中的篡改，有什么建议？",
     "expected_keywords": ["视频", "篡改", "检测"]},
    {"category": "知识迁移", "question": "如何检测GAN生成的假图像？",
     "expected_keywords": ["GAN", "假图像", "深度伪造"]},
    {"category": "知识迁移", "question": "帮我写一个提取JPEG DCT系数的代码",
     "expected_keywords": ["DCT", "系数", "JPEG"]},

    # ===== 类别三：项目自身修改 =====
    {"category": "项目自身修改", "question": "如何提高模型的推理速度？",
     "expected_keywords": ["推理", "速度", "优化"]},
    {"category": "项目自身修改", "question": "如何添加对视频输入的支持？",
     "expected_keywords": ["视频", "扩展", "支持"]},
    {"category": "项目自身修改", "question": "如何提高分割精度？",
     "expected_keywords": ["分割", "精度", "提高"]},

    # ===== 类别四：全局理解 =====
    {"category": "全局理解", "question": "CAT-Net的核心创新点是什么？",
     "expected_keywords": ["创新", "压缩伪影", "DCT"]},
    {"category": "全局理解", "question": "这个项目解决了什么痛点？",
     "expected_keywords": ["篡改", "检测", "拼接"]},
    {"category": "全局理解", "question": "CAT-Net v1和v2有什么区别？",
     "expected_keywords": ["v1", "v2", "版本"]},

    # ===== 类别五：对比分析 =====
    {"category": "对比分析", "question": "CAT-Net和U-Net相比有什么优势？",
     "expected_keywords": ["U-Net", "优势", "对比"]},
    {"category": "对比分析", "question": "双流结构和单流结构哪个好？",
     "expected_keywords": ["双流", "单流", "比较"]},
]


# ===== 实验配置 =====
EXPERIMENTS = [
    {
        "name": "Naive RAG (模拟)",
        "description": "只使用向量检索，不使用重排",
        "top_k": 10,
        "use_rerank": False,
    },
    {
        "name": "GraphRAG (当前系统)",
        "description": "向量检索 + 重排",
        "top_k": 10,
        "use_rerank": True,
    },
    {
        "name": "扩大召回",
        "description": "扩大召回范围",
        "top_k": 20,
        "use_rerank": True,
    },
    {
        "name": "精简召回",
        "description": "减少召回数量",
        "top_k": 5,
        "use_rerank": True,
    },
]


def evaluate_answer(answer: str, expected_keywords: list) -> dict:
    """评估答案质量"""
    answer_lower = answer.lower()
    found_keywords = [kw for kw in expected_keywords if kw.lower() in answer_lower]
    keyword_score = len(found_keywords) / len(expected_keywords) if expected_keywords else 0
    answer_length = len(answer)
    length_score = 1.0 if 50 < answer_length < 2000 else 0.5 if answer_length > 0 else 0
    综合评分 = keyword_score * 0.7 + length_score * 0.3
    return {
        "keyword_score": keyword_score,
        "length_score": length_score,
        "综合评分": 综合评分,
        "found_keywords": found_keywords,
        "answer_length": answer_length
    }


class ExperimentRunner:
    """实验运行器"""

    def __init__(self):
        print("=" * 80)
        print("初始化 GraphRAG System...")
        print("=" * 80)
        self.rag = GraphRAGSystem()
        self.stats = self.rag.get_statistics()
        print(f"向量数量: {self.stats['total_vectors']}")
        print()

    def run_single_experiment(self, exp_config: dict) -> List[dict]:
        """运行单个实验"""
        print(f"\n{'='*60}")
        print(f"实验: {exp_config['name']}")
        print(f"配置: top_k={exp_config['top_k']}, rerank={exp_config['use_rerank']}")
        print(f"{'='*60}")

        results = []
        for i, tc in enumerate(TEST_QUESTIONS, 1):
            print(f"[{i}/{len(TEST_QUESTIONS)}] {tc['question'][:30]}...", end=" ")

            try:
                # 调用RAG系统
                result = self.rag.query(
                    tc["question"],
                    retrieval_top_k=exp_config["top_k"],
                    rerank_top_k=min(5, exp_config["top_k"]),
                    return_context=True
                )

                # 如果不使用重排，手动模拟
                if not exp_config["use_rerank"]:
                    # 只取前5个结果，不重排
                    result["answer"] = result.get("answer", "")[:500]
                    result["rerank_count"] = result["retrieval_count"]

                # 评估答案
                evaluation = evaluate_answer(
                    result["answer"],
                    tc["expected_keywords"]
                )

                print(f"✓ 关键词:{evaluation['keyword_score']*100:.0f}%")

                results.append({
                    "category": tc["category"],
                    "question": tc["question"],
                    "success": True,
                    "answer": result["answer"],
                    "keyword_score": evaluation["keyword_score"],
                    "综合评分": evaluation["综合评分"],
                    "retrieval_count": result["retrieval_count"],
                    "rerank_count": result.get("rerank_count", 0),
                })

            except Exception as e:
                print(f"✗ 错误: {str(e)[:50]}")
                results.append({
                    "category": tc["category"],
                    "question": tc["question"],
                    "success": False,
                    "error": str(e)
                })

        return results

    def run_all_experiments(self) -> Dict:
        """运行所有实验"""
        all_results = {}
        for exp in EXPERIMENTS:
            results = self.run_single_experiment(exp)
            all_results[exp["name"]] = results
        return all_results


def calculate_metrics(results: List[dict]) -> Dict:
    """计算评估指标"""
    # 按类别统计
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "success": 0, "scores": [], "retrieval": []}
        categories[cat]["total"] += 1
        if r["success"]:
            categories[cat]["success"] += 1
            categories[cat]["scores"].append(r["keyword_score"])
            categories[cat]["retrieval"].append(r["retrieval_count"])

    # 总体统计
    success_results = [r for r in results if r["success"]]
    total_scores = [r["keyword_score"] for r in success_results]
    avg_keyword = sum(total_scores) / len(total_scores) if total_scores else 0

    # 召回率统计
    retrieval_counts = [r["retrieval_count"] for r in success_results]
    avg_retrieval = sum(retrieval_counts) / len(retrieval_counts) if retrieval_counts else 0

    return {
        "categories": categories,
        "total": len(results),
        "success": len(success_results),
        "success_rate": len(success_results) / len(results) * 100 if results else 0,
        "avg_keyword_score": avg_keyword * 100,
        "avg_retrieval": avg_retrieval,
    }


def generate_charts(all_results: Dict, all_metrics: Dict) -> str:
    """生成HTML图表"""
    chart_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>CAT-Net RAG 实验结果</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
        h1 { color: #333; text-align: center; }
        h2 { color: #666; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }
        .chart-container { margin: 30px 0; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: center; }
        th { background-color: #4CAF50; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        .metric-box { display: inline-block; padding: 15px 25px; margin: 10px; background: #e3f2fd; border-radius: 8px; }
        .metric-value { font-size: 24px; font-weight: bold; color: #1976D2; }
        .metric-label { font-size: 12px; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 CAT-Net RAG 实验报告</h1>
        <p style="text-align:center;color:#666;">测试时间: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
"""

    # ===== 1. 总体指标 =====
    chart_html += """
        <h2>1. 总体评估指标</h2>
        <div style="text-align:center;">
"""

    exp_names = list(all_metrics.keys())
    for exp_name in exp_names:
        m = all_metrics[exp_name]
        chart_html += f"""
            <div class="metric-box">
                <div class="metric-value">{m['avg_keyword_score']:.1f}%</div>
                <div class="metric-label">{exp_name}<br>关键词得分</div>
            </div>
        """

    chart_html += "</div>"

    # ===== 2. 柱状图：各实验关键词得分 =====
    chart_html += """
        <h2>2. 关键词得分对比</h2>
        <div class="chart-container">
            <canvas id="barChart" height="100"></canvas>
        </div>
        <script>
            new Chart(document.getElementById('barChart'), {
                type: 'bar',
                data: {
                    labels: """ + json.dumps(exp_names) + """,
                    datasets: [{
                        label: '关键词得分 (%)',
                        data: """ + json.dumps([all_metrics[n]['avg_keyword_score'] for n in exp_names]) + """,
                        backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0']
                    }]
                },
                options: {
                    scales: { y: { beginAtZero: true, max: 100 } }
                }
            });
        </script>
    """

    # ===== 3. 折线图：不同top_k的影响 =====
    chart_html += """
        <h2>3. 召回数量对比</h2>
        <div class="chart-container">
            <canvas id="lineChart" height="80"></canvas>
        </div>
        <script>
            new Chart(document.getElementById('lineChart'), {
                type: 'line',
                data: {
                    labels: """ + json.dumps(exp_names) + """,
                    datasets: [{
                        label: '平均召回数量',
                        data: """ + json.dumps([round(all_metrics[n]['avg_retrieval'], 1) for n in exp_names]) + """,
                        borderColor: '#36A2EB',
                        fill: false
                    }]
                }
            });
        </script>
    """

    # ===== 4. 表格：按类别对比 =====
    chart_html += """
        <h2>4. 按类别详细对比</h2>
        <table>
            <tr>
                <th>类别</th>
"""

    for exp_name in exp_names:
        chart_html += f"<th>{exp_name}</th>"
    chart_html += "</tr>"

    categories = list(all_metrics[exp_names[0]]['categories'].keys())
    for cat in categories:
        chart_html += f"<tr><td><b>{cat}</b></td>"
        for exp_name in exp_names:
            m = all_metrics[exp_name]
            cat_m = m['categories'][cat]
            score = sum(cat_m['scores']) / len(cat_m['scores']) * 100 if cat_m['scores'] else 0
            rate = cat_m['success'] / cat_m['total'] * 100 if cat_m['total'] else 0
            chart_html += f"<td>得分: {score:.0f}%<br>通过: {rate:.0f}%</td>"
        chart_html += "</tr>"

    chart_html += "</table>"

    # ===== 5. 雷达图：多维度对比 =====
    chart_html += """
        <h2>5. 多维度能力对比</h2>
        <div class="chart-container">
            <canvas id="radarChart" height="100"></canvas>
        </div>
        <script>
            new Chart(document.getElementById('radarChart'), {
                type: 'radar',
                data: {
                    labels: """ + json.dumps(categories) + """,
                    datasets: [
"""

    colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0']
    for idx, exp_name in enumerate(exp_names):
        m = all_metrics[exp_name]
        scores = []
        for cat in categories:
            cat_m = m['categories'][cat]
            score = sum(cat_m['scores']) / len(cat_m['scores']) * 100 if cat_m['scores'] else 0
            scores.append(score)
        chart_html += f"""
                        {{
                            label: '{exp_name}',
                            data: {json.dumps(scores)},
                            borderColor: '{colors[idx]}',
                            backgroundColor: '{colors[idx]}20'
                        }},
"""

    chart_html += """
                    ]
                },
                options: { scales: { r: { beginAtZero: true, max: 100 } } }
            });
        </script>
    """

    chart_html += """
    </div>
</body>
</html>
"""
    return chart_html


def generate_report(all_results: Dict, all_metrics: Dict) -> str:
    """生成完整报告"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(PROJECT_ROOT, "test_reports")
    os.makedirs(output_dir, exist_ok=True)

    # ===== 1. Markdown报告 =====
    md_file = os.path.join(output_dir, f"catnet_experiment_{timestamp}.md")
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(f"# CAT-Net RAG 实验报告\n\n")
        f.write(f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")

        # 实验配置
        f.write("## 1. 实验配置\n\n")
        f.write("| 实验名称 | 描述 | top_k | 重排 |\n")
        f.write("|----------|------|-------|------|\n")
        for exp in EXPERIMENTS:
            f.write(f"| {exp['name']} | {exp['description']} | {exp['top_k']} | {'是' if exp['use_rerank'] else '否'} |\n")
        f.write("\n---\n\n")

        # 总体指标
        f.write("## 2. 总体评估指标\n\n")
        f.write("| 实验 | 成功率 | 平均关键词得分 | 平均召回数 |\n")
        f.write("|------|--------|---------------|-----------|\n")
        for exp_name, m in all_metrics.items():
            f.write(f"| {exp_name} | {m['success_rate']:.1f}% | {m['avg_keyword_score']:.1f}% | {m['avg_retrieval']:.1f} |\n")
        f.write("\n---\n\n")

        # 按类别详细对比
        f.write("## 3. 按类别详细对比\n\n")
        categories = list(all_metrics[list(all_metrics.keys())[0]]['categories'].keys())
        for cat in categories:
            f.write(f"### {cat}\n\n")
            f.write("| 实验 | 通过/总数 | 得分 |\n")
            f.write("|------|----------|------|\n")
            for exp_name, m in all_metrics.items():
                cat_m = m['categories'][cat]
                score = sum(cat_m['scores']) / len(cat_m['scores']) * 100 if cat_m['scores'] else 0
                f.write(f"| {exp_name} | {cat_m['success']}/{cat_m['total']} | {score:.1f}% |\n")
            f.write("\n")

    print(f"\n[保存] Markdown报告: {md_file}")

    # ===== 2. HTML图表报告 =====
    html_file = os.path.join(output_dir, f"catnet_experiment_{timestamp}.html")
    chart_html = generate_charts(all_results, all_metrics)
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(chart_html)
    print(f"[保存] HTML图表: {html_file}")

    # ===== 3. JSON数据 =====
    json_file = os.path.join(output_dir, f"catnet_experiment_{timestamp}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump({
            "experiments": EXPERIMENTS,
            "metrics": all_metrics,
            "results": {k: [{"category": r["category"], "question": r["question"],
                           "keyword_score": r.get("keyword_score", 0)} for r in v]
                       for k, v in all_results.items()}
        }, f, ensure_ascii=False, indent=2)
    print(f"[保存] JSON数据: {json_file}")

    return md_file, html_file


def main():
    """主函数"""
    print("=" * 80)
    print("CAT-Net RAG 实验测试")
    print("=" * 80)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试问题数: {len(TEST_QUESTIONS)}")
    print(f"实验数量: {len(EXPERIMENTS)}")
    print("=" * 80)

    # 初始化
    runner = ExperimentRunner()

    # 运行所有实验
    all_results = runner.run_all_experiments()

    # 计算指标
    all_metrics = {}
    for exp_name, results in all_results.items():
        all_metrics[exp_name] = calculate_metrics(results)

    # 打印摘要
    print("\n" + "=" * 80)
    print("实验结果摘要")
    print("=" * 80)
    for exp_name, m in all_metrics.items():
        print(f"\n{exp_name}:")
        print(f"  成功率: {m['success_rate']:.1f}%")
        print(f"  平均关键词得分: {m['avg_keyword_score']:.1f}%")
        print(f"  平均召回数: {m['avg_retrieval']:.1f}")

    # 生成报告
    md_file, html_file = generate_report(all_results, all_metrics)

    print("\n" + "=" * 80)
    print("实验完成!")
    print("=" * 80)
    print(f"\n产出文件:")
    print(f"  1. Markdown报告: {md_file}")
    print(f"  2. HTML图表: {html_file}")
    print(f"\n请在浏览器中打开HTML文件查看可视化图表")


if __name__ == "__main__":
    main()
