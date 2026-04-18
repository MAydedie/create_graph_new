#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Graph RAG 批量验收测试脚本 (Phase 1-4 成果展示)
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# 设置环境变量
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# 强制使用本地缓存模型，避免 HuggingFace 连接 443 错误
os.environ["HF_HUB_OFFLINE"] = "1" 

# 设置项目路径
sys.path.insert(0, r"D:\代码仓库生图\create_graph")

from llm.capability.graph_rag_system import GraphRAGSystem

# 5个精选测试问题 (用户指定)
# 25个精选测试问题 (5个宏观 + 20个细节)
TEST_QUESTIONS = [
    # === 第一部分：宏观架构与功能路径 (5题) ===
    "1. 请详细描述 partition_10 中关于 '演示分区创建步骤 (Step 2.7)' 的功能路径，包括涉及的函数调用链。",
    "2. 结合 partition_10 的功能路径数据，说明该流程中的输入输出 (IO) 是如何流转的？",
    "3. 请分析当前 create_graph 项目的整体架构设计，核心模块（如解析、分析、图构建）之间是如何协作的？",
    "4. 如果我要为项目扩展一个新的代码解析器（例如 JavaParser），基于当前的代码结构应该如何实现？请给出具体步骤。",
    "5. 基于当前的项目结构和入口点识别机制，对于后续支持更复杂的微服务架构分析，你有什么架构演进建议？",

    # === 第二部分：核心组件细节验证 (迁移自之前测试成功的核心问题) ===
    "6. 本项目使用了哪种向量数据库？",
    "7. 默认的 Embedding 模型是什么？",
    "8. RAG 系统的重排（Reranker）使用了什么模型？",
    "9. PythonParser 类的主要功能是什么？",
    "10. find_entry_points 方法是用来做什么的？",
    "11. analysis_service.py 中的 analyze_function_hierarchy 函数有什么作用？",
    "12. GraphKnowledgeLoader 类是如何加载数据的？",
    "13. _get_name_from_node 方法在调用链中起什么作用？",
    "14. create_demo_partition_step2_7 函数的功能是什么？",
    "15. ExperiencePathStorage 类将经验路径数据保存在哪里？",
    "16. 如果我想增加检索结果的 top_k 数量，应该修改哪个配置？",
    "17. EmbeddingModel 类中的 encode_chunks 方法有什么作用？",

    # === 第三部分：新增代码细节问题 (8题，聚焦核心逻辑) ===
    "18. BaseParser (或 AbstractParser) 类定义了哪些必须实现的基础接口？",
    "19. 在 PythonParser 中，visit_ClassDef 方法是如何处理类定义的？",
    "20. config.py 文件中主要包含哪些类别的配置项？",
    "21. analysis_service.py 是如何与 parser 模块进行交互的？",
    "22. 项目中的 LogManager 或日志配置是如何实现的？",
    "23. PathSemanticAnalyzer (或类似语义分析类) 的主要职责是什么？",
    "24. 在生成代码图谱时，Unknown 类型的节点通常代表什么含义？",
    "25. data_accessor.py (如有) 或数据访问层是如何读取图谱数据的？"
]

def run_batch_test():
    print("=" * 70)
    print("[START] 开始 Phase 1-4 成果验收测试 (20 Questions)")
    print("=" * 70)
    
    # 1. 初始化系统
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 正在初始化 GraphRAGSystem...")
    start_time = time.time()
    try:
        rag = GraphRAGSystem()
        init_time = time.time() - start_time
        print(f"[SUCCESS] 系统初始化完成 (耗时: {init_time:.2f}s)")
        print(f"[INFO] 知识库状态: {rag.get_statistics()}")
    except Exception as e:
        print(f"[ERROR] 初始化失败: {e}")
        return

    results = []
    
    # 2. 执行测试循环
    for i, question in enumerate(TEST_QUESTIONS, 1):
        print(f"\n[{i}/20] 正在测试: {question}")
        
        q_start = time.time()
        success = False
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # 调用 RAG 系统
                response = rag.query(question, return_context=True)
                success = True
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"   [WARNING] 调用失败，正在重试 ({attempt+1}/{max_retries})... 错误: {e}")
                    time.sleep(2)
                else:
                    raise e
        
        try:
            q_time = time.time() - q_start
            
            result_item = {
                "id": i,
                "question": question,
                "answer": response["answer"],
                "retrieval_count": response["retrieval_count"],
                "rerank_count": response["rerank_count"],
                "time_taken": f"{q_time:.2f}s",
                "timestamp": datetime.now().isoformat()
            }
            results.append(result_item)
            
            print(f"   [SUCCESS] 回答生成成功 (耗时: {q_time:.2f}s)")
            print(f"   [PREVIEW] 答案预览: {response['answer'][:60]}...")
            
        except Exception as e:
            print(f"   [ERROR] 测试失败: {e}")
            results.append({
                "id": i,
                "question": question,
                "answer": f"ERROR: {str(e)}",
                "success": False
            })
    
    # 3. 生成报告
    generate_reports(results)

def generate_reports(results):
    output_dir = "test_reports"
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON 报告
    json_path = os.path.join(output_dir, f"phase1_4_acceptance_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[SUCCESS] JSON 报告已保存: {json_path}")
    
    # Markdown 报告
    md_path = os.path.join(output_dir, f"phase1_4_acceptance_{timestamp}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Phase 1-4 成果验收报告\n\n")
        f.write(f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**测试问题数**: {len(results)}\n\n")
        f.write("## 测试详情\n\n")
        
        for item in results:
            f.write(f"### Q{item['id']}: {item['question']}\n\n")
            f.write(f"**回答**: \n\n{item['answer']}\n\n")
            f.write(f"- **检索**: {item.get('retrieval_count')} 条\n")
            f.write(f"- **重排**: {item.get('rerank_count')} 条\n")
            f.write(f"- **耗时**: {item.get('time_taken')}\n")
            f.write("\n---\n\n")
            
    print(f"[SUCCESS] Markdown 报告已保存: {md_path}")

if __name__ == "__main__":
    run_batch_test()
