#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
阶段3和阶段4综合测试脚本
运行所有阶段3和阶段4的功能，并生成可视化HTML报告
"""

import os
import sys
import io
import json
from datetime import datetime
from pathlib import Path

# 设置标准输出为UTF-8编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from analysis.community_detector import CommunityDetector
from analysis.analyzer import CodeAnalyzer
from analysis.path_semantic_analyzer import PathSemanticAnalyzer
from analysis.code_semantic_clue_extractor import CodeSemanticClueExtractor
from analysis.method_function_profile_builder import MethodFunctionProfileBuilder
from analysis.llm_partition_optimizer import LLMPartitionOptimizer
from analysis.function_call_graph_generator import FunctionCallGraphGenerator
from analysis.function_call_hypergraph import FunctionCallHypergraphGenerator
from analysis.entry_point_identifier import EntryPointIdentifierGenerator
from analysis.partition_data_flow_generator import PartitionDataFlowGenerator
from analysis.partition_control_flow_generator import PartitionControlFlowGenerator


def test_stage3_stage4_comprehensive():
    """综合测试阶段3和阶段4的所有功能"""
    print("\n" + "="*80)
    print("阶段3和阶段4综合测试")
    print("="*80)
    
    # 创建输出目录
    output_dir = Path(r"D:\代码仓库生图\汇报\12.30\阶段3与阶段4 单元测试成果")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 使用当前项目作为测试
    project_path = os.path.dirname(__file__)
    
    # 收集所有结果
    results = {
        "project_path": project_path,
        "timestamp": datetime.now().isoformat(),
        "stage1": {},  # 社区检测
        "stage3_1": {},  # 代码语义线索提取
        "stage3_2": {},  # LLM优化器
        "stage4_1": {},  # 函数调用图
        "stage4_2": {},  # 函数调用超图
        "stage4_3": {},  # 入口点识别
        "stage4_4": {},  # 数据流图
        "stage4_5": {},  # 控制流图
    }
    
    # ========== 步骤1：运行代码分析获取调用图 ==========
    print("\n[步骤1] 运行代码分析...")
    analyzer = CodeAnalyzer(project_path)
    graph_data = analyzer.analyze(project_path)
    
    if not hasattr(analyzer, 'call_graph_analyzer'):
        print("❌ 错误：未找到call_graph_analyzer")
        return False
    
    call_graph = analyzer.call_graph_analyzer.call_graph
    print(f"✓ 获取调用图: {len(call_graph)} 个方法")
    results["call_graph_size"] = len(call_graph)
    
    # ========== 步骤2：运行社区检测获取功能分区 ==========
    print("\n[步骤2] 运行社区检测获取功能分区...")
    detector = CommunityDetector()
    partitions = detector.detect_communities(call_graph, algorithm="louvain")
    print(f"✓ 检测到 {len(partitions)} 个功能分区")
    
    # 选择前5个最大的分区进行测试
    partitions.sort(key=lambda p: len(p.get("methods", [])), reverse=True)
    test_partitions = partitions[:5]
    print(f"✓ 选择前5个最大分区进行测试")
    
    results["stage1"] = {
        "total_partitions": len(partitions),
        "test_partitions": len(test_partitions),
        "partitions": [
            {
                "partition_id": p.get("partition_id", "unknown"),
                "method_count": len(p.get("methods", [])),
                "modularity": p.get("modularity", 0.0),
                "internal_calls": p.get("internal_calls", 0),
                "external_calls": p.get("external_calls", 0)
            }
            for p in test_partitions
        ]
    }
    
    # ========== 步骤3：测试阶段3.1 - 代码语义线索提取 ==========
    print("\n" + "-"*80)
    print("[步骤3] 测试阶段3.1：代码语义线索提取")
    print("-"*80)
    
    path_analyzer = PathSemanticAnalyzer(project_path=project_path)
    clue_extractor = CodeSemanticClueExtractor()
    profile_builder = MethodFunctionProfileBuilder(project_path, analyzer.report)
    
    stage3_1_results = []
    sample_methods = []
    for partition in test_partitions[:2]:  # 只测试前2个分区
        methods = partition.get("methods", [])
        if methods:
            sample_methods.extend(methods[:5])  # 每个分区取前5个方法
    
    for method_sig in sample_methods[:10]:  # 总共测试10个方法
        try:
            profile = profile_builder.build_profile(method_sig)
            if profile:
                stage3_1_results.append({
                    "method_signature": method_sig,
                    "file_path": profile.file_path,
                    "path_semantics": profile.path_semantics,
                    "code_clues": {
                        "decorators": profile.code_clues.get("decorators", []),
                        "inheritance": profile.code_clues.get("inheritance", []),
                        "imports": len(profile.code_clues.get("imports", [])),
                        "has_docstring": bool(profile.code_clues.get("docstring", "")),
                        "functional_comments": len(profile.code_clues.get("functional_comments", [])),
                    }
                })
        except Exception as e:
            print(f"  ⚠️ 方法 {method_sig} 提取失败: {e}")
    
    results["stage3_1"] = {
        "total_profiles": len(stage3_1_results),
        "sample_profiles": stage3_1_results[:5]  # 只保存前5个示例
    }
    print(f"✓ 为 {len(stage3_1_results)} 个方法生成了功能画像")
    
    # ========== 步骤4：测试阶段3.2 - LLM优化器（可选） ==========
    print("\n" + "-"*80)
    print("[步骤4] 测试阶段3.2：LLM优化器（可选）")
    print("-"*80)
    
    # 从环境变量读取API key，移除硬编码默认值
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv('DEEPSEEK_API_KEY')
    base_url = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
    
    if not api_key:
        print("⚠️ 警告: DEEPSEEK_API_KEY 环境变量未设置，跳过LLM优化测试")
        print("   请参考 ENV_SETUP.md 了解如何配置环境变量")
        return True  # 测试跳过但不失败
    
    try:
        optimizer = LLMPartitionOptimizer(
            api_key=api_key,
            base_url=base_url,
            project_path=project_path,
            report=analyzer.report
        )
        
        # 只优化前2个分区（节省时间）
        test_partitions_for_optimization = test_partitions[:2]
        print(f"  优化 {len(test_partitions_for_optimization)} 个分区...")
        
        optimization_result = optimizer.optimize_partitions(
            initial_partitions=test_partitions_for_optimization,
            call_graph=call_graph,
            max_iterations=1,  # 只运行1次迭代以节省时间
            modularity_improvement_threshold=0.1
        )
        
        results["stage3_2"] = {
            "optimized": True,
            "iterations": len(optimization_result.optimization_history),
            "final_modularity": optimization_result.statistics.get("final_modularity", 0.0),
            "modularity_improvement": optimization_result.statistics.get("modularity_improvement", 0.0),
            "optimized_partitions_count": len(optimization_result.partitions)
        }
        print(f"✓ LLM优化完成，模块度提升: {optimization_result.statistics.get('modularity_improvement', 0.0):.2%}")
    except Exception as e:
        print(f"  ⚠️ LLM优化器测试失败: {e}")
        results["stage3_2"] = {
            "optimized": False,
            "error": str(e)
        }
    
    # ========== 步骤5：测试阶段4.1 - 函数调用图生成 ==========
    print("\n" + "-"*80)
    print("[步骤5] 测试阶段4.1：函数调用图生成")
    print("-"*80)
    call_graph_generator = FunctionCallGraphGenerator(call_graph)
    
    stage4_1_results = []
    for partition in test_partitions:
        partition_id = partition.get("partition_id", "unknown")
        call_graph_result = call_graph_generator.generate_partition_call_graph(partition)
        stats = call_graph_result["statistics"]
        stage4_1_results.append({
            "partition_id": partition_id,
            "statistics": stats
        })
        print(f"\n分区 {partition_id}:")
        print(f"  - 内部节点: {stats['internal_nodes']}")
        print(f"  - 外部节点: {stats['external_nodes']}")
        print(f"  - 内部边: {stats['internal_edges']}")
        print(f"  - 外部边: {stats['external_edges']}")
    
    results["stage4_1"] = {
        "partitions": stage4_1_results
    }
    
    # ========== 步骤6：测试阶段4.2 - 函数调用超图生成 ==========
    print("\n" + "-"*80)
    print("[步骤6] 测试阶段4.2：函数调用超图生成")
    print("-"*80)
    hypergraph_generator = FunctionCallHypergraphGenerator(call_graph)
    
    stage4_2_results = []
    for partition in test_partitions:
        partition_id = partition.get("partition_id", "unknown")
        hypergraph = hypergraph_generator.generate_partition_hypergraph(partition)
        viz_data = hypergraph.to_visualization_data()
        stats = viz_data["statistics"]
        stage4_2_results.append({
            "partition_id": partition_id,
            "statistics": stats
        })
        print(f"\n分区 {partition_id}:")
        print(f"  - 节点数: {stats['total_nodes']}")
        print(f"  - 超边数: {stats['total_hyperedges']}")
        print(f"  - 边数: {stats['total_edges']}")
        pattern_counts = stats['pattern_counts']
        print(f"  - 调用模式:")
        print(f"    * 链式调用: {pattern_counts['chains']}")
        print(f"    * 扇出调用: {pattern_counts['fanouts']}")
        print(f"    * 扇入调用: {pattern_counts['fanins']}")
        print(f"    * 循环调用: {pattern_counts['cycles']}")
    
    results["stage4_2"] = {
        "partitions": stage4_2_results
    }
    
    # ========== 步骤7：测试阶段4.3 - 入口点识别 ==========
    print("\n" + "-"*80)
    print("[步骤7] 测试阶段4.3：入口点识别")
    print("-"*80)
    entry_point_generator = EntryPointIdentifierGenerator(
        call_graph, 
        analyzer.report,
        None
    )
    
    entry_points_map = entry_point_generator.identify_all_partitions_entry_points(
        partitions,
        score_threshold=0.3
    )
    
    stage4_3_results = []
    for partition_id, entry_points in list(entry_points_map.items())[:5]:
        stage4_3_results.append({
            "partition_id": partition_id,
            "entry_points_count": len(entry_points),
            "entry_points": [
                {
                    "method_sig": ep.method_sig,
                    "score": ep.score,
                    "reasons": ep.reasons[:3]  # 只保存前3个原因
                }
                for ep in entry_points[:5]  # 只保存前5个入口点
            ]
        })
        print(f"\n分区 {partition_id}:")
        print(f"  - 识别到 {len(entry_points)} 个入口点")
        for ep in entry_points[:5]:
            print(f"    * {ep.method_sig} (评分: {ep.score:.2f})")
            print(f"      原因: {', '.join(ep.reasons[:2])}")
    
    results["stage4_3"] = {
        "partitions": stage4_3_results
    }
    
    # ========== 步骤8：测试阶段4.4 - 功能级数据流图生成 ==========
    print("\n" + "-"*80)
    print("[步骤8] 测试阶段4.4：功能级数据流图生成")
    print("-"*80)
    data_flow_generator = PartitionDataFlowGenerator(
        call_graph,
        analyzer.report,
        analyzer.data_flow_analyzer
    )
    
    stage4_4_results = []
    for partition in test_partitions:
        partition_id = partition.get("partition_id", "unknown")
        entry_points = entry_points_map.get(partition_id, [])
        try:
            partition_dfg = data_flow_generator.generate_partition_data_flow(
                partition,
                entry_points
            )
            viz_data = partition_dfg.to_visualization_data()
            stats = viz_data["statistics"]
            stage4_4_results.append({
                "partition_id": partition_id,
                "statistics": stats
            })
            print(f"\n分区 {partition_id}:")
            print(f"  - 节点数: {stats['total_nodes']}")
            print(f"  - 边数: {stats['total_edges']}")
            print(f"  - 参数流动数: {stats['parameter_flows_count']}")
            print(f"  - 返回值流动数: {stats['return_value_flows_count']}")
            print(f"  - 共享状态数: {stats['shared_states_count']}")
        except Exception as e:
            print(f"\n分区 {partition_id}: ❌ 生成失败 - {e}")
            stage4_4_results.append({
                "partition_id": partition_id,
                "error": str(e)
            })
    
    results["stage4_4"] = {
        "partitions": stage4_4_results
    }
    
    # ========== 步骤9：测试阶段4.5 - 功能级控制流图生成 ==========
    print("\n" + "-"*80)
    print("[步骤9] 测试阶段4.5：功能级控制流图生成")
    print("-"*80)
    control_flow_generator = PartitionControlFlowGenerator(
        call_graph,
        analyzer.report
    )
    
    stage4_5_results = []
    for partition in test_partitions:
        partition_id = partition.get("partition_id", "unknown")
        try:
            partition_cfg = control_flow_generator.generate_partition_control_flow(partition)
            viz_data = partition_cfg.to_visualization_data()
            stats = viz_data["statistics"]
            stage4_5_results.append({
                "partition_id": partition_id,
                "statistics": stats
            })
            print(f"\n分区 {partition_id}:")
            print(f"  - 节点数: {stats['total_nodes']}")
            print(f"  - 边数: {stats['total_edges']}")
            print(f"  - 方法数: {stats['total_methods']}")
            print(f"  - 方法调用边数: {stats['method_call_edges_count']}")
            print(f"  - 循环数: {stats['cycles_count']}")
        except Exception as e:
            print(f"\n分区 {partition_id}: ❌ 生成失败 - {e}")
            stage4_5_results.append({
                "partition_id": partition_id,
                "error": str(e)
            })
    
    results["stage4_5"] = {
        "partitions": stage4_5_results
    }
    
    # ========== 保存JSON结果 ==========
    json_file = output_dir / "test_results.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✓ 结果已保存到: {json_file}")
    
    # ========== 生成可视化HTML ==========
    html_file = output_dir / "阶段3与阶段4测试成果可视化.html"
    generate_visualization_html(results, html_file)
    print(f"✓ 可视化HTML已保存到: {html_file}")
    
    # ========== 总结 ==========
    print("\n" + "="*80)
    print("✅ 阶段3和阶段4综合测试完成！")
    print("="*80)
    print(f"\n结果文件:")
    print(f"  - JSON数据: {json_file}")
    print(f"  - 可视化HTML: {html_file}")
    
    return True


def generate_visualization_html(results: dict, output_file: Path):
    """生成可视化HTML文件"""
    
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>阶段3与阶段4测试成果可视化</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Microsoft YaHei', 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            color: #333;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        .content {{
            padding: 30px;
        }}
        
        .section {{
            margin-bottom: 40px;
            padding: 25px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 5px solid #667eea;
        }}
        
        .section h2 {{
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.8em;
            display: flex;
            align-items: center;
        }}
        
        .section h2::before {{
            content: "📊";
            margin-right: 10px;
            font-size: 1.2em;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }}
        
        .stat-card .number {{
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
        }}
        
        .stat-card .label {{
            color: #666;
            font-size: 1em;
        }}
        
        .partition-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 15px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        .partition-card h3 {{
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.3em;
        }}
        
        .info-row {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }}
        
        .info-row:last-child {{
            border-bottom: none;
        }}
        
        .info-label {{
            font-weight: bold;
            color: #666;
        }}
        
        .info-value {{
            color: #333;
        }}
        
        .entry-point-list {{
            list-style: none;
            padding: 0;
        }}
        
        .entry-point-item {{
            background: #f0f0f0;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 5px;
            border-left: 3px solid #667eea;
        }}
        
        .entry-point-item .method-sig {{
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}
        
        .entry-point-item .score {{
            color: #28a745;
            font-weight: bold;
        }}
        
        .entry-point-item .reasons {{
            color: #666;
            font-size: 0.9em;
            margin-top: 5px;
        }}
        
        .pattern-badge {{
            display: inline-block;
            padding: 5px 12px;
            margin: 5px;
            background: #667eea;
            color: white;
            border-radius: 20px;
            font-size: 0.9em;
        }}
        
        .success {{
            color: #28a745;
            font-weight: bold;
        }}
        
        .error {{
            color: #dc3545;
            font-weight: bold;
        }}
        
        .code-clue-item {{
            background: white;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 5px;
            border-left: 3px solid #28a745;
        }}
        
        .code-clue-item .method-sig {{
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
        }}
        
        .code-clue-item .clue-detail {{
            margin: 5px 0;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>阶段3与阶段4测试成果可视化</h1>
            <p>测试时间: {results.get('timestamp', 'N/A')}</p>
            <p>项目路径: {results.get('project_path', 'N/A')}</p>
        </div>
        
        <div class="content">
            <!-- 总体统计 -->
            <div class="section">
                <h2>总体统计</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="number">{results.get('call_graph_size', 0)}</div>
                        <div class="label">调用图方法数</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">{results.get('stage1', {}).get('total_partitions', 0)}</div>
                        <div class="label">功能分区总数</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">{results.get('stage1', {}).get('test_partitions', 0)}</div>
                        <div class="label">测试分区数</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">{results.get('stage3_1', {}).get('total_profiles', 0)}</div>
                        <div class="label">功能画像数</div>
                    </div>
                </div>
            </div>
            
            <!-- 阶段1：社区检测 -->
            <div class="section">
                <h2>阶段1：社区检测结果</h2>
                {generate_stage1_html(results.get('stage1', {}))}
            </div>
            
            <!-- 阶段3.1：代码语义线索提取 -->
            <div class="section">
                <h2>阶段3.1：代码语义线索提取</h2>
                {generate_stage3_1_html(results.get('stage3_1', {}))}
            </div>
            
            <!-- 阶段3.2：LLM优化器 -->
            <div class="section">
                <h2>阶段3.2：LLM优化器</h2>
                {generate_stage3_2_html(results.get('stage3_2', {}))}
            </div>
            
            <!-- 阶段4.1：函数调用图 -->
            <div class="section">
                <h2>阶段4.1：函数调用图生成</h2>
                {generate_stage4_1_html(results.get('stage4_1', {}))}
            </div>
            
            <!-- 阶段4.2：函数调用超图 -->
            <div class="section">
                <h2>阶段4.2：函数调用超图生成</h2>
                {generate_stage4_2_html(results.get('stage4_2', {}))}
            </div>
            
            <!-- 阶段4.3：入口点识别 -->
            <div class="section">
                <h2>阶段4.3：入口点识别</h2>
                {generate_stage4_3_html(results.get('stage4_3', {}))}
            </div>
            
            <!-- 阶段4.4：数据流图 -->
            <div class="section">
                <h2>阶段4.4：功能级数据流图生成</h2>
                {generate_stage4_4_html(results.get('stage4_4', {}))}
            </div>
            
            <!-- 阶段4.5：控制流图 -->
            <div class="section">
                <h2>阶段4.5：功能级控制流图生成</h2>
                {generate_stage4_5_html(results.get('stage4_5', {}))}
            </div>
        </div>
    </div>
</body>
</html>"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)


def generate_stage1_html(stage1_data):
    """生成阶段1的HTML"""
    if not stage1_data or not stage1_data.get('partitions'):
        return "<p>暂无数据</p>"
    
    html = ""
    for p in stage1_data['partitions']:
        html += f"""
        <div class="partition-card">
            <h3>分区 {p['partition_id']}</h3>
            <div class="info-row">
                <span class="info-label">方法数:</span>
                <span class="info-value">{p['method_count']}</span>
            </div>
            <div class="info-row">
                <span class="info-label">模块度:</span>
                <span class="info-value">{p['modularity']:.3f}</span>
            </div>
            <div class="info-row">
                <span class="info-label">内部调用:</span>
                <span class="info-value">{p['internal_calls']}</span>
            </div>
            <div class="info-row">
                <span class="info-label">外部调用:</span>
                <span class="info-value">{p['external_calls']}</span>
            </div>
        </div>
        """
    return html


def generate_stage3_1_html(stage3_1_data):
    """生成阶段3.1的HTML"""
    if not stage3_1_data or not stage3_1_data.get('sample_profiles'):
        return "<p>暂无数据</p>"
    
    html = f"<p><strong>总功能画像数:</strong> {stage3_1_data.get('total_profiles', 0)}</p>"
    for profile in stage3_1_data['sample_profiles']:
        clues = profile.get('code_clues', {})
        html += f"""
        <div class="code-clue-item">
            <div class="method-sig">{profile.get('method_signature', 'N/A')}</div>
            <div class="clue-detail"><strong>文件路径:</strong> {profile.get('file_path', 'N/A')}</div>
            <div class="clue-detail"><strong>装饰器:</strong> {len(clues.get('decorators', []))} 个</div>
            <div class="clue-detail"><strong>继承关系:</strong> {len(clues.get('inheritance', []))} 个</div>
            <div class="clue-detail"><strong>导入语句:</strong> {clues.get('imports', 0)} 个</div>
            <div class="clue-detail"><strong>有文档字符串:</strong> {'是' if clues.get('has_docstring') else '否'}</div>
            <div class="clue-detail"><strong>功能性注释:</strong> {clues.get('functional_comments', 0)} 个</div>
        </div>
        """
    return html


def generate_stage3_2_html(stage3_2_data):
    """生成阶段3.2的HTML"""
    if not stage3_2_data:
        return "<p>暂无数据</p>"
    
    if stage3_2_data.get('optimized'):
        return f"""
        <div class="partition-card">
            <p class="success">✅ LLM优化成功</p>
            <div class="info-row">
                <span class="info-label">迭代次数:</span>
                <span class="info-value">{stage3_2_data.get('iterations', 0)}</span>
            </div>
            <div class="info-row">
                <span class="info-label">最终模块度:</span>
                <span class="info-value">{stage3_2_data.get('final_modularity', 0.0):.3f}</span>
            </div>
            <div class="info-row">
                <span class="info-label">模块度提升:</span>
                <span class="info-value success">{stage3_2_data.get('modularity_improvement', 0.0):.2%}</span>
            </div>
            <div class="info-row">
                <span class="info-label">优化后分区数:</span>
                <span class="info-value">{stage3_2_data.get('optimized_partitions_count', 0)}</span>
            </div>
        </div>
        """
    else:
        return f"""
        <div class="partition-card">
            <p class="error">❌ LLM优化失败</p>
            <p>错误信息: {stage3_2_data.get('error', '未知错误')}</p>
        </div>
        """


def generate_stage4_1_html(stage4_1_data):
    """生成阶段4.1的HTML"""
    if not stage4_1_data or not stage4_1_data.get('partitions'):
        return "<p>暂无数据</p>"
    
    html = ""
    for p in stage4_1_data['partitions']:
        stats = p.get('statistics', {})
        html += f"""
        <div class="partition-card">
            <h3>分区 {p['partition_id']}</h3>
            <div class="info-row">
                <span class="info-label">内部节点:</span>
                <span class="info-value">{stats.get('internal_nodes', 0)}</span>
            </div>
            <div class="info-row">
                <span class="info-label">外部节点:</span>
                <span class="info-value">{stats.get('external_nodes', 0)}</span>
            </div>
            <div class="info-row">
                <span class="info-label">内部边:</span>
                <span class="info-value">{stats.get('internal_edges', 0)}</span>
            </div>
            <div class="info-row">
                <span class="info-label">外部边:</span>
                <span class="info-value">{stats.get('external_edges', 0)}</span>
            </div>
        </div>
        """
    return html


def generate_stage4_2_html(stage4_2_data):
    """生成阶段4.2的HTML"""
    if not stage4_2_data or not stage4_2_data.get('partitions'):
        return "<p>暂无数据</p>"
    
    html = ""
    for p in stage4_2_data['partitions']:
        stats = p.get('statistics', {})
        patterns = stats.get('pattern_counts', {})
        html += f"""
        <div class="partition-card">
            <h3>分区 {p['partition_id']}</h3>
            <div class="info-row">
                <span class="info-label">节点数:</span>
                <span class="info-value">{stats.get('total_nodes', 0)}</span>
            </div>
            <div class="info-row">
                <span class="info-label">超边数:</span>
                <span class="info-value">{stats.get('total_hyperedges', 0)}</span>
            </div>
            <div class="info-row">
                <span class="info-label">边数:</span>
                <span class="info-value">{stats.get('total_edges', 0)}</span>
            </div>
            <div style="margin-top: 15px;">
                <strong>调用模式:</strong>
                <span class="pattern-badge">链式: {patterns.get('chains', 0)}</span>
                <span class="pattern-badge">扇出: {patterns.get('fanouts', 0)}</span>
                <span class="pattern-badge">扇入: {patterns.get('fanins', 0)}</span>
                <span class="pattern-badge">循环: {patterns.get('cycles', 0)}</span>
            </div>
        </div>
        """
    return html


def generate_stage4_3_html(stage4_3_data):
    """生成阶段4.3的HTML"""
    if not stage4_3_data or not stage4_3_data.get('partitions'):
        return "<p>暂无数据</p>"
    
    html = ""
    for p in stage4_3_data['partitions']:
        html += f"""
        <div class="partition-card">
            <h3>分区 {p['partition_id']} - {p['entry_points_count']} 个入口点</h3>
            <ul class="entry-point-list">
        """
        for ep in p.get('entry_points', []):
            html += f"""
                <li class="entry-point-item">
                    <div class="method-sig">{ep.get('method_sig', 'N/A')}</div>
                    <div class="score">评分: {ep.get('score', 0.0):.2f}</div>
                    <div class="reasons">原因: {', '.join(ep.get('reasons', []))}</div>
                </li>
            """
        html += """
            </ul>
        </div>
        """
    return html


def generate_stage4_4_html(stage4_4_data):
    """生成阶段4.4的HTML"""
    if not stage4_4_data or not stage4_4_data.get('partitions'):
        return "<p>暂无数据</p>"
    
    html = ""
    for p in stage4_4_data['partitions']:
        if 'error' in p:
            html += f"""
            <div class="partition-card">
                <h3>分区 {p['partition_id']}</h3>
                <p class="error">❌ 生成失败: {p['error']}</p>
            </div>
            """
        else:
            stats = p.get('statistics', {})
            html += f"""
            <div class="partition-card">
                <h3>分区 {p['partition_id']}</h3>
                <div class="info-row">
                    <span class="info-label">节点数:</span>
                    <span class="info-value">{stats.get('total_nodes', 0)}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">边数:</span>
                    <span class="info-value">{stats.get('total_edges', 0)}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">参数流动数:</span>
                    <span class="info-value">{stats.get('parameter_flows_count', 0)}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">返回值流动数:</span>
                    <span class="info-value">{stats.get('return_value_flows_count', 0)}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">共享状态数:</span>
                    <span class="info-value">{stats.get('shared_states_count', 0)}</span>
                </div>
            </div>
            """
    return html


def generate_stage4_5_html(stage4_5_data):
    """生成阶段4.5的HTML"""
    if not stage4_5_data or not stage4_5_data.get('partitions'):
        return "<p>暂无数据</p>"
    
    html = ""
    for p in stage4_5_data['partitions']:
        if 'error' in p:
            html += f"""
            <div class="partition-card">
                <h3>分区 {p['partition_id']}</h3>
                <p class="error">❌ 生成失败: {p['error']}</p>
            </div>
            """
        else:
            stats = p.get('statistics', {})
            html += f"""
            <div class="partition-card">
                <h3>分区 {p['partition_id']}</h3>
                <div class="info-row">
                    <span class="info-label">节点数:</span>
                    <span class="info-value">{stats.get('total_nodes', 0)}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">边数:</span>
                    <span class="info-value">{stats.get('total_edges', 0)}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">方法数:</span>
                    <span class="info-value">{stats.get('total_methods', 0)}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">方法调用边数:</span>
                    <span class="info-value">{stats.get('method_call_edges_count', 0)}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">循环数:</span>
                    <span class="info-value">{stats.get('cycles_count', 0)}</span>
                </div>
            </div>
            """
    return html


if __name__ == "__main__":
    try:
        test_stage3_stage4_comprehensive()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()




















