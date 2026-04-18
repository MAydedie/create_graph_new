#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
演示分区管理器
从 app.py 中提取的演示分区创建和管理逻辑
"""

from typing import Dict, List, Set, Any, Optional
from demo_code_package.generate_demo_code import (
    generate_demo_partition_from_call_graph,
    generate_demo_partition_with_methods
)


def create_demo_partition_step2_7(
    call_graph: Dict[str, Set[str]],
    partitions: List[Dict[str, Any]],
    enable_demo: bool = False
) -> tuple[bool, str, str, List[List[str]]]:
    """
    步骤2.7：创建演示分区（如果需要，提前创建以便后续步骤能处理）
    
    Args:
        call_graph: 调用图
        partitions: 分区列表
        enable_demo: 是否启用演示代码生成
        
    Returns:
        (demo_partition_created, demo_partition_id, demo_partition_name, demo_paths)
    """
    demo_partition_created = False
    demo_partition_id = "demo_partition_001"
    demo_partition_name = "代码分析与解析演示分区"
    demo_paths = []
    
    if not enable_demo:
        print(f"[app.py] ℹ️  演示代码生成功能已关闭（ENABLE_DEMO_CODE_GENERATION = False）", flush=True)
        return demo_partition_created, demo_partition_id, demo_partition_name, demo_paths
    
    print(f"\n[app.py] {'='*60}", flush=True)
    print(f"[app.py] 🔍 检查是否需要创建演示分区（提前创建）...", flush=True)
    print(f"[app.py] {'='*60}\n", flush=True)
    
    # 使用外部函数生成演示分区
    demo_partition = generate_demo_partition_from_call_graph(call_graph, min_methods=20)
    
    if demo_partition:
        # 添加必要的字段
        demo_partition["folders"] = ["analysis", "parsers", "visualization", "llm"]
        demo_partition["keywords"] = ["演示", "代码分析", "路径追踪"]
        demo_partition["modularity"] = 0.85
        demo_partition["is_demo"] = True
        
        # 将演示分区添加到列表开头（优先选择）
        partitions.insert(0, demo_partition)
        demo_partition_created = True
        demo_paths = demo_partition.get("paths", [])
        
        print(f"[app.py]   ✓ 演示分区已添加到分区列表（位置0）", flush=True)
        print(f"[app.py]   - 分区ID: {demo_partition_id}", flush=True)
        print(f"[app.py]   - 分区名称: {demo_partition_name}", flush=True)
        print(f"[app.py]   - 方法数量: {len(demo_partition['methods'])}", flush=True)
        print(f"[app.py]   - 路径数量: {len(demo_paths)} 条", flush=True)
        if demo_paths:
            path_lengths = [len(p) for p in demo_paths]
            print(f"[app.py]   - 路径长度分布: {dict((l, path_lengths.count(l)) for l in set(path_lengths))}", flush=True)
        print(f"[app.py]   - 所有路径均基于真实的调用关系", flush=True)
    else:
        print(f"[app.py]   ⚠️ call_graph中方法数量不足或未找到有足够调用关系的连通分量，暂不创建演示分区", flush=True)
        print(f"[app.py]   ℹ️  将在步骤6.5.4中根据实际情况决定是否创建演示分区", flush=True)
    
    print(f"[app.py] ✅ 演示分区检查完成", flush=True)
    
    return demo_partition_created, demo_partition_id, demo_partition_name, demo_paths


def create_demo_partition_step6_5_4(
    partitions: List[Dict[str, Any]],
    partition_paths_map: Dict[str, Dict[str, List[List[str]]]],
    partition_analyses: Dict[str, Dict[str, Any]],
    call_graph: Dict[str, Set[str]],
    analyzer_report: Any,
    enable_demo: bool = False,
    demo_partition_created: bool = False,
    demo_partition_id: str = "demo_partition_001",
    demo_paths: List[List[str]] = None
) -> tuple[bool, str]:
    """
    步骤6.5.4：创建演示分区（如果所有分区都没有符合要求的路径）
    
    Args:
        partitions: 分区列表
        partition_paths_map: 分区路径映射
        partition_analyses: 分区分析结果
        call_graph: 调用图
        analyzer_report: 分析器报告
        enable_demo: 是否启用演示代码生成
        demo_partition_created: 演示分区是否已在步骤2.7创建
        demo_partition_id: 演示分区ID
        demo_paths: 演示路径列表
        
    Returns:
        (demo_partition_created, demo_partition_id)
    """
    if not enable_demo:
        print(f"[app.py] ℹ️  演示代码生成功能已关闭（ENABLE_DEMO_CODE_GENERATION = False）", flush=True)
        return demo_partition_created, demo_partition_id
    
    print(f"\n[app.py] {'='*60}", flush=True)
    print(f"[app.py] 🔍 检查是否需要创建演示分区...", flush=True)
    print(f"[app.py] {'='*60}\n", flush=True)
    
    if demo_partition_created:
        print(f"[app.py]   ℹ️  演示分区已在步骤2.7创建，跳过创建步骤", flush=True)
        print(f"[app.py]   - 分区ID: {demo_partition_id}", flush=True)
        print(f"[app.py]   - 路径数量: {len(demo_paths) if demo_paths else 0} 条", flush=True)
        
        # 补充生成调用图、超图和入口点
        _supplement_demo_partition_analysis(
            partitions, partition_analyses, call_graph, analyzer_report, demo_partition_id
        )
        
        print(f"[app.py] ✅ 演示分区检查完成（已在步骤2.7创建）", flush=True)
        return demo_partition_created, demo_partition_id
    
    # 检查是否有符合要求的分区
    has_valid_partition = False
    for partition in partitions:
        partition_id = partition.get("partition_id", "unknown")
        paths_map = partition_paths_map.get(partition_id, {})
        
        if not paths_map:
            continue
        
        total_paths = sum(len(paths) for paths in paths_map.values())
        if total_paths == 0:
            continue
        
        fqns_list = partition_analyses.get(partition_id, {}).get('fqns', [])
        if not fqns_list:
            continue
        
        fqmn_info_map = {}
        for fqn_info in fqns_list:
            method_sig = fqn_info.get('method_signature')
            if method_sig:
                fqmn_info_map[method_sig] = {
                    'fqn': fqn_info.get('fqn'),
                    'origin': fqn_info.get('origin'),
                    'segment_count': fqn_info.get('segment_count', 0)
                }
        
        valid_path_count = 0
        for leaf_node, paths in paths_map.items():
            for path in paths:
                # User disabled: was len(path) < 3
                if not path or len(path) < 1:
                    continue
                
                # User disabled all strict FQMN checks - treat all paths as valid
                is_valid_path = True
                # for method_sig in path:
                #     if method_sig not in fqmn_info_map:
                #         is_valid_path = False
                #         break
                #     
                #     fqmn_info = fqmn_info_map[method_sig]
                #     if fqmn_info.get('segment_count') != 4 or fqmn_info.get('origin') != 'internal':
                #         is_valid_path = False
                #         break
                
                if is_valid_path:
                    valid_path_count += 1
        
        if valid_path_count > 0:
            has_valid_partition = True
            print(f"[app.py]   ✅ 找到有符合要求路径的分区: {partition_id} ({valid_path_count}条)", flush=True)
            break
    
    if not has_valid_partition:
        print(f"[app.py]   ❌ 所有分区都没有符合要求的路径（四段内部、长度≥3）", flush=True)
        print(f"[app.py] ⚠️ 开始创建演示分区...", flush=True)
        
        # 收集项目中的方法签名 (User disabled strict filters: collect ALL methods)
        available_methods = []
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            fqns_list = partition_analyses.get(partition_id, {}).get('fqns', [])
            for fqn_info in fqns_list:
                method_sig = fqn_info.get('method_signature')
                # origin = fqn_info.get('origin')
                # segment_count = fqn_info.get('segment_count', 0)
                # Disabled: if method_sig and origin == 'internal' and segment_count == 4:
                if method_sig:
                    available_methods.append(method_sig)
        
        # 使用外部函数生成演示分区
        demo_partition = generate_demo_partition_with_methods(available_methods)
        
        # 将演示分区添加到列表开头
        partitions.insert(0, demo_partition)
        demo_partition_created = True
        demo_partition_id = demo_partition["partition_id"]
        
        # 保存演示分区的路径信息
        partition_paths_map[demo_partition_id] = demo_partition.get("paths_map", {})
        
        # 保存FQMN信息
        if demo_partition_id not in partition_analyses:
            partition_analyses[demo_partition_id] = {}
        partition_analyses[demo_partition_id]['fqns'] = demo_partition.get('fqns', [])
        partition_analyses[demo_partition_id]['inputs'] = demo_partition.get('inputs', [])
        partition_analyses[demo_partition_id]['outputs'] = demo_partition.get('outputs', [])
        
        print(f"[app.py]   ✓ 演示分区已添加到分区列表（位置0）", flush=True)
        print(f"[app.py]   ✓ 演示分区路径信息已保存到 partition_paths_map", flush=True)
        print(f"[app.py]   ✓ 演示分区FQMN/IO信息已保存到 partition_analyses", flush=True)
        
        valid_paths = [p for p in demo_partition.get('paths', []) if len(p) >= 1]  # User: was >= 3
        print(f"\n[app.py] ✅ 演示分区创建完成!", flush=True)
        print(f"[app.py]   - 分区ID: {demo_partition_id}", flush=True)
        print(f"[app.py]   - 分区名称: {demo_partition['name']}", flush=True)
        print(f"[app.py]   - 方法数量: {len(demo_partition['methods'])}", flush=True)
        print(f"[app.py]   - 总路径数量: {len(demo_partition.get('paths', []))} 条", flush=True)
        print(f"[app.py]   - 符合要求的路径数: {len(valid_paths)} 条", flush=True)
        print(f"[app.py]   - 所有路径均被接受 (User disabled strict filters)", flush=True)
        
        # 补充生成调用图、超图和入口点
        _supplement_demo_partition_analysis(
            partitions, partition_analyses, call_graph, analyzer_report, demo_partition_id
        )
    else:
        print(f"[app.py] ✅ 找到有路径的分区，无需创建演示分区", flush=True)
    
    print(f"[app.py] {'='*60}\n", flush=True)
    
    return demo_partition_created, demo_partition_id


def _supplement_demo_partition_analysis(
    partitions: List[Dict[str, Any]],
    partition_analyses: Dict[str, Dict[str, Any]],
    call_graph: Dict[str, Set[str]],
    analyzer_report: Any,
    demo_partition_id: str
):
    """
    为演示分区补充生成调用图、超图和入口点
    
    Args:
        partitions: 分区列表
        partition_analyses: 分区分析结果
        call_graph: 调用图
        analyzer_report: 分析器报告
        demo_partition_id: 演示分区ID
    """
    print(f"\n[app.py] {'='*60}", flush=True)
    print(f"[app.py] 🔧 为演示分区补充生成调用图、超图和入口点...", flush=True)
    print(f"[app.py] {'='*60}", flush=True)
    
    # 确保 partition_analyses 中存在演示分区
    if demo_partition_id not in partition_analyses:
        partition_analyses[demo_partition_id] = {}
    
    # 找到演示分区对象
    demo_partition = None
    for partition in partitions:
        if partition.get("partition_id") == demo_partition_id:
            demo_partition = partition
            break
    
    if not demo_partition:
        print(f"[app.py]   ⚠️ 未找到演示分区对象，无法补充生成", flush=True)
        return
    
    # 导入必要的类
    from analysis.function_call_graph_generator import FunctionCallGraphGenerator
    from analysis.function_call_hypergraph import FunctionCallHypergraphGenerator
    from analysis.entry_point_identifier import EntryPointIdentifierGenerator
    
    # 1. 补充生成调用图
    try:
        print(f"[app.py]   [补充] 为演示分区生成调用图...", flush=True)
        call_graph_generator = FunctionCallGraphGenerator(call_graph)
        call_graph_result = call_graph_generator.generate_partition_call_graph(demo_partition)
        partition_analyses[demo_partition_id]['call_graph'] = call_graph_result
        nodes_count = len(call_graph_result.get('nodes', []))
        edges_count = len(call_graph_result.get('edges', []))
        print(f"[app.py]   ✓ [补充] 演示分区调用图生成成功: 节点={nodes_count}, 边={edges_count}", flush=True)
    except Exception as e:
        print(f"[app.py]   ⚠️ [补充] 演示分区调用图生成失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
    
    # 2. 补充生成超图
    try:
        print(f"[app.py]   [补充] 为演示分区生成超图...", flush=True)
        hypergraph_generator = FunctionCallHypergraphGenerator(call_graph)
        hypergraph = hypergraph_generator.generate_partition_hypergraph(demo_partition)
        hypergraph_dict = hypergraph.to_dict()
        partition_analyses[demo_partition_id]['hypergraph'] = hypergraph_dict
        hypergraph_viz = hypergraph.to_visualization_data()
        partition_analyses[demo_partition_id]['hypergraph_viz'] = hypergraph_viz
        method_nodes = len([n for n in hypergraph.nodes.values() if n.get('type') == 'method'])
        function_nodes = len([n for n in hypergraph.nodes.values() if n.get('type') == 'function'])
        total_nodes = len(hypergraph.nodes)
        total_edges = len(hypergraph_viz.get('edges', []))
        print(f"[app.py]   ✓ [补充] 演示分区超图生成成功: 节点={total_nodes} (方法={method_nodes}, 功能={function_nodes}), 边={total_edges}", flush=True)
    except Exception as e:
        print(f"[app.py]   ⚠️ [补充] 演示分区超图生成失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
    
    # 3. 补充识别入口点
    try:
        print(f"[app.py]   [补充] 为演示分区识别入口点...", flush=True)
        entry_point_generator = EntryPointIdentifierGenerator(call_graph, analyzer_report, None)
        entry_points_map = entry_point_generator.identify_all_partitions_entry_points([demo_partition], score_threshold=0.3)
        if demo_partition_id in entry_points_map:
            entry_points = entry_points_map[demo_partition_id]
            partition_analyses[demo_partition_id]['entry_points'] = [
                {
                    'method_signature': ep.method_sig,
                    'score': ep.score,
                    'reasons': ep.reasons
                }
                for ep in entry_points
            ]
            print(f"[app.py]   ✓ [补充] 演示分区入口点识别成功: {len(entry_points)} 个入口点", flush=True)
        else:
            print(f"[app.py]   ⚠️ [补充] 演示分区入口点识别失败: 未在entry_points_map中找到", flush=True)
    except Exception as e:
        print(f"[app.py]   ⚠️ [补充] 演示分区入口点识别失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
    
    print(f"[app.py] ✅ 演示分区补充生成完成", flush=True)
    print(f"[app.py] {'='*60}\n", flush=True)



















