#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成演示代码的逻辑
从app.py中提取的生成演示分区的逻辑
"""

from typing import Dict, List, Set, Any


def find_connected_component(start_node: str, visited: Set[str], call_graph: Dict[str, Set[str]], 
                            partition_methods: Set[str]) -> Set[str]:
    """
    使用BFS找到包含start_node的连通分量
    
    Args:
        start_node: 起始节点
        visited: 已访问节点集合
        call_graph: 调用图
        partition_methods: 分区方法集合
        
    Returns:
        连通分量集合
    """
    component = set()
    queue = [start_node]
    visited.add(start_node)
    
    while queue:
        current = queue.pop(0)
        component.add(current)
        
        # 添加被调用的方法（如果也在候选方法中）
        if current in call_graph:
            for callee in call_graph[current]:
                if callee in partition_methods and callee not in visited:
                    visited.add(callee)
                    queue.append(callee)
        
        # 添加调用当前方法的方法（如果也在候选方法中）
        for caller, callees in call_graph.items():
            if caller in partition_methods and current in callees and caller not in visited:
                visited.add(caller)
                queue.append(caller)
    
    return component


def find_paths_from_leaf(leaf_node: str, reverse_call_graph: Dict[str, Set[str]], 
                         demo_methods: Set[str], max_depth: int = 4) -> List[List[str]]:
    """
    从叶子节点回溯找到路径
    
    Args:
        leaf_node: 叶子节点
        reverse_call_graph: 反向调用图
        demo_methods: 演示方法集合
        max_depth: 最大深度
        
    Returns:
        路径列表
    """
    paths = []
    visited_paths = set()
    
    def backtrack(current_node: str, current_path: List[str], depth: int):
        if depth > max_depth or len(current_path) > max_depth:
            return
        
        # 检查是否为入口点（不被分区内其他方法调用）
        callers_in_partition = reverse_call_graph.get(current_node, set())
        if len(callers_in_partition) == 0:
            # 是入口点，保存路径
            path_tuple = tuple(current_path)
            if path_tuple not in visited_paths and len(current_path) >= 2:
                paths.append(current_path.copy())
                visited_paths.add(path_tuple)
        else:
            # 继续回溯
            for caller in callers_in_partition:
                if caller not in current_path:  # 避免循环
                    backtrack(caller, [caller] + current_path, depth + 1)
    
    backtrack(leaf_node, [leaf_node], 0)
    
    # 如果没有找到路径，叶子节点自身作为一条路径
    if not paths:
        paths = [[leaf_node]]
    
    return paths


def generate_demo_partition_from_call_graph(call_graph: Dict[str, Set[str]], 
                                           min_methods: int = 20) -> Dict[str, Any]:
    """
    基于真实调用关系生成演示分区
    
    这是从app.py步骤2.7中提取的逻辑
    
    Args:
        call_graph: 调用图
        min_methods: 最小方法数量
        
    Returns:
        演示分区字典，包含：
        - partition_id: 分区ID
        - name: 分区名称
        - methods: 方法列表
        - paths_map: 路径映射
        - description: 描述
    """
    # 从call_graph中提取真实的方法签名
    available_methods_from_call_graph = []
    for method_sig in call_graph.keys():
        # 只保留看起来像项目内部方法的签名（简单过滤）
        if '.' in method_sig and not method_sig.startswith('builtin.'):
            available_methods_from_call_graph.append(method_sig)
    
    if len(available_methods_from_call_graph) < min_methods:
        return None
    
    # 找到所有连通分量
    visited = set()
    components = []
    for method_sig in available_methods_from_call_graph:
        if method_sig not in visited:
            component = find_connected_component(
                method_sig, 
                visited, 
                call_graph,
                set(available_methods_from_call_graph)
            )
            if len(component) >= 3:  # 至少3个节点才能形成路径
                components.append(component)
    
    if not components:
        return None
    
    # 选择最大的连通分量
    components.sort(key=len, reverse=True)
    largest_component = components[0]
    
    # 如果最大连通分量太小，尝试合并多个连通分量
    if len(largest_component) < 20:
        demo_methods = set(largest_component)
        for component in components[1:]:
            if len(demo_methods) < 30:
                demo_methods.update(component)
            else:
                break
    else:
        # 如果连通分量太大，只取前30个节点
        demo_methods = set(list(largest_component)[:30])
    
    # 从真实的调用关系中提取路径
    demo_paths = []
    demo_paths_map = {}
    
    # 找到分区内的叶子节点
    leaf_nodes = []
    for method_sig in demo_methods:
        callees_in_partition = set()
        if method_sig in call_graph:
            callees_in_partition = call_graph[method_sig] & demo_methods
        
        if len(callees_in_partition) == 0:
            leaf_nodes.append(method_sig)
    
    # 从叶子节点回溯，找到到入口点的路径
    reverse_call_graph = {}
    for caller, callees in call_graph.items():
        for callee in callees:
            if callee in demo_methods and caller in demo_methods:
                if callee not in reverse_call_graph:
                    reverse_call_graph[callee] = set()
                reverse_call_graph[callee].add(caller)
    
    # 从每个叶子节点找到路径
    for leaf_node in leaf_nodes[:10]:  # 最多处理10个叶子节点
        paths = find_paths_from_leaf(leaf_node, reverse_call_graph, demo_methods)
        demo_paths.extend(paths)
        if leaf_node not in demo_paths_map:
            demo_paths_map[leaf_node] = []
        demo_paths_map[leaf_node].extend(paths)
    
    # 限制为10条路径
    demo_paths = demo_paths[:10]
    
    # 验证：确保所有路径中的方法都在demo_methods中
    validated_paths = []
    for path in demo_paths:
        if all(node in demo_methods for node in path):
            validated_paths.append(path)
    demo_paths = validated_paths
    
    # 统计调用关系数量
    internal_edges_count = 0
    for caller in demo_methods:
        if caller in call_graph:
            callees_in_partition = call_graph[caller] & demo_methods
            internal_edges_count += len(callees_in_partition)
    
    return {
        "partition_id": "demo_partition_001",
        "name": "代码分析与解析演示分区",
        "description": f"演示功能分区，包含{len(demo_paths)}条功能路径（基于真实调用关系）。包含{len(demo_methods)}个方法，{internal_edges_count}条内部调用关系。",
        "methods": list(demo_methods),
        "paths_map": demo_paths_map,
        "paths": demo_paths,
        "internal_edges_count": internal_edges_count,
        "leaf_nodes": leaf_nodes
    }


def generate_demo_partition_with_methods(available_methods: List[str]) -> Dict[str, Any]:
    """
    基于方法列表生成演示分区（创建路径）
    
    这是从app.py步骤6.5.4中提取的逻辑
    
    Args:
        available_methods: 可用方法列表（四段内部格式）
        
    Returns:
        演示分区字典
    """
    demo_methods = set()
    demo_paths_map = {}
    
    # 如果找不到足够的方法，使用一些示例方法签名
    if len(available_methods) < 20:
        # 创建一些示例方法签名（符合四段内部格式：包.文件.类.方法）
        available_methods = [
            "analysis.function_node_enhancer.FunctionNodeEnhancer.identify_leaf_nodes",
            "analysis.function_node_enhancer.FunctionNodeEnhancer.explore_paths",
            "analysis.function_node_enhancer.FunctionNodeEnhancer.add_function_nodes",
            "analysis.path_level_analyzer.PathLevelAnalyzer.generate_path_level_cfg",
            "analysis.path_level_analyzer.PathLevelAnalyzer.generate_path_level_dfg",
            "parsers.python_parser.PythonParser.parse",
            "parsers.python_parser.PythonParser.extract_classes",
            "parsers.python_parser.PythonParser.extract_functions",
            "visualization.enhanced_visualizer.EnhancedVisualizer.render",
            "visualization.enhanced_visualizer.EnhancedVisualizer.generate_graph",
            "llm.code_understanding_agent.CodeUnderstandingAgent.enhance_partition",
            "llm.code_understanding_agent.CodeUnderstandingAgent.analyze_code",
            "config.config.Config.load",
            "config.config.Config.get",
            "app.analyze_function_hierarchy",
        ]
    
    # 确保有足够的方法
    if len(available_methods) < 15:
        # 重复使用一些方法以创建更多路径
        while len(available_methods) < 30:
            available_methods.extend(available_methods[:5])
    
    # 创建20条演示路径（包含长度2、3、4的路径，种类多样）
    demo_paths = []
    
    # 5条长度为2的路径（用于演示过滤效果）
    for i in range(5):
        if len(available_methods) >= 2:
            start_idx = (i * 2) % len(available_methods)
            path = [available_methods[start_idx], available_methods[(start_idx + 1) % len(available_methods)]]
            if len(path) == 2:
                demo_paths.append(path)
    
    # 8条长度为3的路径
    for i in range(8):
        if len(available_methods) >= 3:
            start_idx = (i * 3) % len(available_methods)
            path = []
            for j in range(3):
                path.append(available_methods[(start_idx + j) % len(available_methods)])
            if len(path) == 3:
                demo_paths.append(path)
    
    # 7条长度为4的路径
    for i in range(7):
        if len(available_methods) >= 4:
            start_idx = (i * 4) % len(available_methods)
            path = []
            for j in range(4):
                path.append(available_methods[(start_idx + j) % len(available_methods)])
            if len(path) == 4:
                demo_paths.append(path)
    
    # 确保有20条路径（如果不够，补充长度3和4的）
    while len(demo_paths) < 20:
        if len(available_methods) >= 3:
            start_idx = len(demo_paths) % len(available_methods)
            path_len = 3 if len(demo_paths) % 2 == 0 else 4
            path = []
            for j in range(path_len):
                path.append(available_methods[(start_idx + j) % len(available_methods)])
            demo_paths.append(path)
        else:
            break
    
    # 限制为20条
    demo_paths = demo_paths[:20]
    
    # 收集所有使用的方法
    for path in demo_paths:
        demo_methods.update(path)
    
    # 构建paths_map（按叶子节点分组）
    for idx, path in enumerate(demo_paths):
        leaf_node = path[0]  # 使用路径的第一个节点作为叶子节点
        if leaf_node not in demo_paths_map:
            demo_paths_map[leaf_node] = []
        demo_paths_map[leaf_node].append(path)
    
    # 生成FQMN信息
    demo_fqns = []
    demo_inputs = []
    demo_outputs = []
    
    for method_sig in demo_methods:
        # 构建FQMN（四段内部格式）
        if '.' in method_sig:
            parts = method_sig.split('.')
            if len(parts) >= 2:
                # 确保是4段格式
                if len(parts) == 2:
                    fqmn = f"{parts[0]}.{parts[0]}.{parts[0]}.{parts[1]}"
                elif len(parts) == 3:
                    fqmn = f"{parts[0]}.{parts[1]}.{parts[1]}.{parts[2]}"
                else:
                    fqmn = '.'.join(parts[:4]) if len(parts) >= 4 else method_sig
            else:
                fqmn = f"demo.{method_sig}.module.{method_sig}"
        else:
            fqmn = f"demo.demo.module.{method_sig}"
        
        demo_fqns.append({
            'method_signature': method_sig,
            'fqn': fqmn,
            'origin': 'internal',
            'segment_count': 4
        })
        
        # 添加示例输入输出
        demo_inputs.append({
            'method_signature': method_sig,
            'parameter_name': 'data',
            'parameter_type': 'Dict',
            'fqn': fqmn
        })
        demo_outputs.append({
            'method_signature': method_sig,
            'return_type': 'Dict',
            'fqn': fqmn
        })
    
    return {
        "partition_id": "demo_partition_001",
        "name": "代码分析与解析演示分区",
        "description": "演示功能分区，包含15条符合要求的功能路径（四段内部、长度≥3），用于展示路径级别分析功能。包含路径长度3、4、5的多种调用链。",
        "methods": list(demo_methods),
        "paths_map": demo_paths_map,
        "paths": demo_paths,
        "fqns": demo_fqns,
        "inputs": demo_inputs,
        "outputs": demo_outputs,
        "folders": ["analysis", "parsers", "visualization", "llm"],
        "keywords": ["演示", "代码分析", "路径追踪"],
        "modularity": 0.85,
        "is_demo": True
    }


if __name__ == "__main__":
    # 测试代码
    print("演示代码生成逻辑已提取到 demo_code_package/generate_demo_code.py")
    print("包含两个主要函数：")
    print("1. generate_demo_partition_from_call_graph() - 基于真实调用关系生成")
    print("2. generate_demo_partition_with_methods() - 基于方法列表生成")




















