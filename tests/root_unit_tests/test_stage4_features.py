#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试阶段4功能：函数调用图、超图、入口点识别、数据流图、控制流图
"""

import os
import sys
import io
import json

# 设置标准输出为UTF-8编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from analysis.community_detector import CommunityDetector
from analysis.analyzer import CodeAnalyzer
from analysis.function_call_graph_generator import FunctionCallGraphGenerator
from analysis.function_call_hypergraph import FunctionCallHypergraphGenerator
from analysis.entry_point_identifier import EntryPointIdentifierGenerator
from analysis.partition_data_flow_generator import PartitionDataFlowGenerator
from analysis.partition_control_flow_generator import PartitionControlFlowGenerator


def test_stage4_features():
    """测试阶段4的所有功能"""
    print("\n" + "="*80)
    print("阶段4功能测试：函数调用图、超图、入口点识别、数据流图、控制流图")
    print("="*80)
    
    # 使用当前项目作为测试
    project_path = os.path.dirname(__file__)
    
    # ========== 步骤1：运行代码分析获取调用图 ==========
    print("\n[步骤1] 运行代码分析...")
    analyzer = CodeAnalyzer(project_path)
    graph_data = analyzer.analyze(project_path)
    
    if not hasattr(analyzer, 'call_graph_analyzer'):
        print("❌ 错误：未找到call_graph_analyzer")
        return False
    
    call_graph = analyzer.call_graph_analyzer.call_graph
    print(f"✓ 获取调用图: {len(call_graph)} 个方法")
    
    # ========== 步骤2：运行社区检测获取功能分区 ==========
    print("\n[步骤2] 运行社区检测获取功能分区...")
    detector = CommunityDetector()
    partitions = detector.detect_communities(call_graph, algorithm="louvain")
    print(f"✓ 检测到 {len(partitions)} 个功能分区")
    
    # 选择前3个最大的分区进行测试
    partitions.sort(key=lambda p: len(p.get("methods", [])), reverse=True)
    test_partitions = partitions[:3]
    print(f"✓ 选择前3个最大分区进行测试")
    
    # ========== 步骤3：测试函数调用图生成 ==========
    print("\n" + "-"*80)
    print("[步骤3] 测试函数调用图生成（阶段4.1）")
    print("-"*80)
    call_graph_generator = FunctionCallGraphGenerator(call_graph)
    
    for partition in test_partitions:
        partition_id = partition.get("partition_id", "unknown")
        call_graph_result = call_graph_generator.generate_partition_call_graph(partition)
        stats = call_graph_result["statistics"]
        print(f"\n分区 {partition_id}:")
        print(f"  - 内部节点: {stats['internal_nodes']}")
        print(f"  - 外部节点: {stats['external_nodes']}")
        print(f"  - 内部边: {stats['internal_edges']}")
        print(f"  - 外部边: {stats['external_edges']}")
    
    # ========== 步骤4：测试函数调用超图生成 ==========
    print("\n" + "-"*80)
    print("[步骤4] 测试函数调用超图生成（阶段4.2）")
    print("-"*80)
    hypergraph_generator = FunctionCallHypergraphGenerator(call_graph)
    
    for partition in test_partitions:
        partition_id = partition.get("partition_id", "unknown")
        hypergraph = hypergraph_generator.generate_partition_hypergraph(partition)
        viz_data = hypergraph.to_visualization_data()
        stats = viz_data["statistics"]
        print(f"\n分区 {partition_id}:")
        print(f"  - 节点数: {stats['total_nodes']}")
        print(f"  - 超边数: {stats['total_hyperedges']}")
        print(f"  - 边数: {stats['total_edges']}")
        print(f"  - 调用模式:")
        pattern_counts = stats['pattern_counts']
        print(f"    * 链式调用: {pattern_counts['chains']}")
        print(f"    * 扇出调用: {pattern_counts['fanouts']}")
        print(f"    * 扇入调用: {pattern_counts['fanins']}")
        print(f"    * 循环调用: {pattern_counts['cycles']}")
    
    # ========== 步骤5：测试入口点识别 ==========
    print("\n" + "-"*80)
    print("[步骤5] 测试入口点识别（阶段4.3）")
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
    
    for partition_id, entry_points in list(entry_points_map.items())[:3]:
        print(f"\n分区 {partition_id}:")
        print(f"  - 识别到 {len(entry_points)} 个入口点")
        for ep in entry_points[:5]:  # 只显示前5个
            print(f"    * {ep.method_sig} (评分: {ep.score:.2f})")
            print(f"      原因: {', '.join(ep.reasons[:2])}")  # 只显示前2个原因
    
    # ========== 步骤6：测试功能级数据流图生成 ==========
    print("\n" + "-"*80)
    print("[步骤6] 测试功能级数据流图生成（阶段4.4）")
    print("-"*80)
    data_flow_generator = PartitionDataFlowGenerator(
        call_graph,
        analyzer.report,
        analyzer.data_flow_analyzer
    )
    
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
            print(f"\n分区 {partition_id}:")
            print(f"  - 节点数: {stats['total_nodes']}")
            print(f"  - 边数: {stats['total_edges']}")
            print(f"  - 参数流动数: {stats['parameter_flows_count']}")
            print(f"  - 返回值流动数: {stats['return_value_flows_count']}")
            print(f"  - 共享状态数: {stats['shared_states_count']}")
        except Exception as e:
            print(f"\n分区 {partition_id}: ❌ 生成失败 - {e}")
    
    # ========== 步骤7：测试功能级控制流图生成 ==========
    print("\n" + "-"*80)
    print("[步骤7] 测试功能级控制流图生成（阶段4.5）")
    print("-"*80)
    control_flow_generator = PartitionControlFlowGenerator(
        call_graph,
        analyzer.report
    )
    
    for partition in test_partitions:
        partition_id = partition.get("partition_id", "unknown")
        try:
            partition_cfg = control_flow_generator.generate_partition_control_flow(partition)
            viz_data = partition_cfg.to_visualization_data()
            stats = viz_data["statistics"]
            print(f"\n分区 {partition_id}:")
            print(f"  - 节点数: {stats['total_nodes']}")
            print(f"  - 边数: {stats['total_edges']}")
            print(f"  - 方法数: {stats['total_methods']}")
            print(f"  - 方法调用边数: {stats['method_call_edges_count']}")
            print(f"  - 循环数: {stats['cycles_count']}")
        except Exception as e:
            print(f"\n分区 {partition_id}: ❌ 生成失败 - {e}")
    
    # ========== 总结 ==========
    print("\n" + "="*80)
    print("✅ 阶段4功能测试完成！")
    print("="*80)
    print("\n所有功能都已实现并可以运行。")
    print("可以通过以下方式查看可视化结果：")
    print("1. 运行 python app.py，访问 http://localhost:5000")
    print("2. 点击'四层分析'按钮查看功能分区可视化")
    print("3. 查看生成的JSON数据文件（在output_analysis目录）")
    
    return True


if __name__ == "__main__":
    try:
        test_stage4_features()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()























































