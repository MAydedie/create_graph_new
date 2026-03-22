#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
功能节点增强器 - 在功能分区内进行叶子节点的路径追踪
基于设计文档：基于路径探索的功能识别方法设计文档.md
"""

from typing import Dict, List, Set, Optional, Any
import logging

from .function_call_hypergraph import FunctionCallHypergraph, HyperEdge

logger = logging.getLogger(__name__)


def identify_leaf_nodes_in_partition(
    hypergraph: FunctionCallHypergraph,
    call_graph: Dict[str, Set[str]],
    partition_methods: Set[str]
) -> List[str]:
    """
    识别分区内的叶子节点
    
    定义：分区内的叶子节点 = 不调用分区内其他方法的节点
    
    Args:
        hypergraph: 超图对象（分区级别的）
        call_graph: 完整的调用图 {caller: Set[callees]}
        partition_methods: 分区的methods集合（用于边界约束）
        
    Returns:
        分区内的叶子节点ID列表
    """
    leaf_nodes = []
    
    for node_id in hypergraph.nodes.keys():
        # 确保节点在分区内
        if node_id not in partition_methods:
            continue
        
        # 检查出度：如果不在call_graph中，或者call_graph[node_id]为空，则为叶子节点
        if node_id not in call_graph or len(call_graph[node_id]) == 0:
            leaf_nodes.append(node_id)
        else:
            # 关键：检查是否调用分区内的其他方法
            callees = call_graph[node_id]
            callees_in_partition = callees & partition_methods  # 计算与分区的交集
            
            # 如果不调用分区内的任何方法，则为分区内的叶子节点
            if len(callees_in_partition) == 0:
                leaf_nodes.append(node_id)
    
    return leaf_nodes


def explore_paths_in_partition(
    leaf_nodes: List[str], 
    hypergraph: FunctionCallHypergraph,
    call_graph: Dict[str, Set[str]],
    partition_methods: Set[str],
    max_path_length: int = 10
) -> Dict[str, List[List[str]]]:
    """
    在分区内从叶子节点探索有向路径
    
    关键约束：路径上的所有节点都必须在 partition_methods 中
    
    Args:
        leaf_nodes: 分区内的叶子节点列表
        hypergraph: 超图对象（分区级别的）
        call_graph: 完整的调用图 {caller: Set[callees]}
        partition_methods: 分区的methods集合（用于边界约束）
        max_path_length: 最大路径长度
        
    Returns:
        {leaf_node: [path1, path2, ...]}，每条路径是从叶子节点到分区内入口点的节点序列
    """
    # 构建反向调用图：{callee: Set[callers]}（只考虑分区内的调用关系）
    reverse_call_graph: Dict[str, Set[str]] = {}
    for caller, callees in call_graph.items():
        # 只考虑调用者和被调用者都在分区内的情况
        if caller in partition_methods:
            for callee in callees:
                if callee in partition_methods:  # 关键：只考虑分区内的被调用者
                    if callee not in reverse_call_graph:
                        reverse_call_graph[callee] = set()
                    reverse_call_graph[callee].add(caller)
    
    paths_map: Dict[str, List[List[str]]] = {}
    
    for leaf_node in leaf_nodes:
        # 确保叶子节点在分区内
        if leaf_node not in partition_methods:
            continue
            
        paths = []
        visited_paths = set()  # 用于去重
        
        def backtrack(current_node: str, current_path: List[str], depth: int):
            """
            回溯探索路径（限制在分区内）
            
            关键约束：
            - 路径上的所有节点都必须在 partition_methods 中
            - 回溯时，只考虑分区内的调用者
            """
            # 验证当前节点在分区内（安全措施）
            if current_node not in partition_methods:
                return
            
            # 终止条件：达到最大深度或路径过长
            if depth > max_path_length or len(current_path) > max_path_length:
                # 保存当前路径（从叶子节点到当前节点）
                path_tuple = tuple(current_path)
                if path_tuple not in visited_paths and len(current_path) >= 2:
                    # 验证路径上的所有节点都在分区内
                    if all(node in partition_methods for node in current_path):
                        paths.append(current_path.copy())
                        visited_paths.add(path_tuple)
                return
            
            # 检查是否为分区内的入口点
            # 入口点定义：不被分区内其他节点调用
            callers_in_partition = reverse_call_graph.get(current_node, set()) & partition_methods
            
            if len(callers_in_partition) == 0:
                # 当前节点是分区内的入口点，保存路径
                path_tuple = tuple(current_path)
                if path_tuple not in visited_paths and len(current_path) >= 1:
                    # 验证路径上的所有节点都在分区内
                    if all(node in partition_methods for node in current_path):
                        paths.append(current_path.copy())
                        visited_paths.add(path_tuple)
            else:
                # 继续回溯到分区内的调用者
                for caller in callers_in_partition:
                    # 关键约束：调用者必须在分区内，且不在当前路径中（避免循环）
                    if caller in partition_methods and caller not in current_path:
                        backtrack(caller, current_path + [caller], depth + 1)
                
                # 如果当前路径还未保存，且路径长度>=1，也保存（作为可能的路径终点）
                if len(current_path) >= 1:
                    path_tuple = tuple(current_path)
                    if path_tuple not in visited_paths:
                        if all(node in partition_methods for node in current_path):
                            paths.append(current_path.copy())
                            visited_paths.add(path_tuple)
        
        # 从叶子节点开始回溯
        backtrack(leaf_node, [leaf_node], 0)
        
        # 如果没有任何路径，叶子节点自身也作为一个路径（单独节点作为功能）
        if not paths:
            paths = [[leaf_node]]
        
        paths_map[leaf_node] = paths
    
    return paths_map


def explore_paths_from_entries(
    entry_points: List[str],
    call_graph: Dict[str, Set[str]],
    partition_methods: Set[str],
    max_path_length: int = 15
) -> List[List[str]]:
    """
    新增策略：从入口点前向探索路径（限制在分区内）
    返回若干条从入口点出发的路径（到叶子/或到最大长度）
    """
    results: List[List[str]] = []
    visited: Set[tuple] = set()

    entry_points = [ep for ep in (entry_points or []) if ep in partition_methods]
    if not entry_points:
        return results

    def dfs(node: str, path: List[str]):
        if len(path) >= max_path_length:
            t = tuple(path)
            if t not in visited:
                visited.add(t)
                results.append(path.copy())
            return

        callees = (call_graph.get(node, set()) or set()) & partition_methods
        if not callees:
            t = tuple(path)
            if t not in visited:
                visited.add(t)
                results.append(path.copy())
            return

        extended = False
        for callee in callees:
            if callee in path:
                continue
            extended = True
            dfs(callee, path + [callee])

        if not extended:
            t = tuple(path)
            if t not in visited:
                visited.add(t)
                results.append(path.copy())

    for ep in entry_points:
        dfs(ep, [ep])

    return results


def explore_intermediate_paths(
    call_graph: Dict[str, Set[str]],
    partition_methods: Set[str],
    entry_points: List[str],
    leaf_nodes: List[str],
    max_path_length: int = 15,
    max_seeds: int = 30
) -> List[List[str]]:
    """
    新增策略：中间节点补全
    - 找出既不是入口点、也不是叶子节点的“中间节点”作为种子
    - 从种子向后探索一段短路径，补充覆盖率
    """
    entry_set = set(entry_points or [])
    leaf_set = set(leaf_nodes or [])

    # 挑一些中间节点做种子，避免爆炸
    candidates = [n for n in partition_methods if n not in entry_set and n not in leaf_set]
    candidates = sorted(candidates)  # 关键修复：排序以确保确定性
    candidates = candidates[:max_seeds]

    results: List[List[str]] = []
    visited: Set[tuple] = set()

    def dfs(node: str, path: List[str]):
        if len(path) >= max_path_length:
            t = tuple(path)
            if t not in visited:
                visited.add(t)
                results.append(path.copy())
            return

        callees = (call_graph.get(node, set()) or set()) & partition_methods
        if not callees:
            t = tuple(path)
            if t not in visited:
                visited.add(t)
                results.append(path.copy())
            return

        for callee in callees:
            if callee in path:
                continue
            dfs(callee, path + [callee])

    for seed in candidates:
        dfs(seed, [seed])

    return results


def merge_paths(
    leaf_paths_map: Dict[str, List[List[str]]],
    entry_paths: List[List[str]],
    intermediate_paths: List[List[str]],
    max_per_leaf: int = 20
) -> Dict[str, List[List[str]]]:
    """
    合并并去重路径：
    - 以 leaf_paths_map 为主
    - 入口点与中间路径按“末尾节点”归并到对应 leaf（若末尾是 leaf）
    """
    merged: Dict[str, List[List[str]]] = {k: [p[:] for p in v] for k, v in (leaf_paths_map or {}).items()}

    def add_to_leaf(leaf: str, path: List[str]):
        if not path:
            return
        if leaf not in merged:
            merged[leaf] = []
        # 去重
        t = tuple(path)
        existing = {tuple(p) for p in merged[leaf]}
        if t in existing:
            return
        merged[leaf].append(path)
        if len(merged[leaf]) > max_per_leaf:
            merged[leaf] = merged[leaf][:max_per_leaf]

    for p in entry_paths or []:
        if p and p[-1] in merged:
            add_to_leaf(p[-1], p)

    for p in intermediate_paths or []:
        if p and p[-1] in merged:
            add_to_leaf(p[-1], p)

    return merged


def explore_paths_in_partition_enhanced(
    leaf_nodes: List[str],
    entry_points: List[str],
    hypergraph: FunctionCallHypergraph,
    call_graph: Dict[str, Set[str]],
    partition_methods: Set[str],
    max_path_length: int = 15
) -> Dict[str, List[List[str]]]:
    """
    增强版路径探索：
    1) 叶子回溯（原有策略）
    2) 入口点前向（新增策略）
    3) 中间节点补全（新增策略）
    """
    paths_from_leafs = explore_paths_in_partition(
        leaf_nodes, hypergraph, call_graph, partition_methods, max_path_length
    )

    paths_from_entries = explore_paths_from_entries(
        entry_points, call_graph, partition_methods, max_path_length
    )

    intermediate_paths = explore_intermediate_paths(
        call_graph, partition_methods, entry_points, leaf_nodes, max_path_length
    )

    return merge_paths(paths_from_leafs, paths_from_entries, intermediate_paths)


def generate_function_description_heuristic(
    path: List[str],
    hypergraph: FunctionCallHypergraph
) -> str:
    """
    使用启发式规则生成功能描述
    
    Args:
        path: 路径节点列表
        hypergraph: 超图对象
        
    Returns:
        功能描述文本
    """
    # 从方法名称中提取关键词
    keywords = []
    for method_sig in path:
        method_name = method_sig.split('.')[-1] if '.' in method_sig else method_sig
        # 提取常见动词（get, set, create, delete, update, validate, process等）
        verbs = ["get", "set", "create", "delete", "update", "validate", "process", 
                 "save", "load", "parse", "format", "convert", "generate", "check",
                 "login", "verify", "hash", "encrypt", "decrypt", "send", "receive"]
        for verb in verbs:
            if verb in method_name.lower():
                keywords.append(verb)
                break
    
    # 构建描述
    if keywords:
        unique_keywords = list(dict.fromkeys(keywords))  # 去重并保持顺序
        description = f"通过 {'、'.join(unique_keywords[:3])} 等操作实现功能"
    else:
        # 使用路径长度和节点数
        if len(path) == 1:
            method_name = path[0].split('.')[-1] if '.' in path[0] else path[0]
            description = f"实现 {method_name} 功能"
        else:
            description = f"通过 {len(path)} 个方法的调用链实现功能"
    
    return description


def add_function_nodes_to_hypergraph(
    hypergraph: FunctionCallHypergraph,
    paths_map: Dict[str, List[List[str]]],
    descriptions_map: Dict[str, List[str]]
) -> FunctionCallHypergraph:
    """
    在超图中添加功能节点
    
    Args:
        hypergraph: 超图对象（将被修改）
        paths_map: {leaf_node: [path1, path2, ...]}
        descriptions_map: {leaf_node: [desc1, desc2, ...]}（与paths_map对应）
        
    Returns:
        修改后的超图对象
    """
    function_nodes = []
    
    for leaf_node, paths in paths_map.items():
        descriptions = descriptions_map.get(leaf_node, [])
        
        for path_index, path in enumerate(paths):
            # 生成功能节点ID
            function_node_id = f"function_{leaf_node}_{path_index}".replace('.', '_').replace('/', '_')
            
            # 获取功能描述（如果没有，使用默认描述）
            description = descriptions[path_index] if path_index < len(descriptions) else f"功能路径 {path_index + 1}"
            
            # 创建功能节点
            function_node_data = {
                "id": function_node_id,
                "label": description,
                "type": "function",  # 区别于 "method"
                "function_path": path,  # 功能实现路径
                "start_leaf_node": leaf_node,  # 起始叶子节点
                "path_length": len(path),
                "metadata": {
                    "path_type": "leaf_to_entry",  # 路径类型
                    "methods_in_path": path,  # 路径上的方法列表
                    "leaf_node": leaf_node,
                    "path_index": path_index
                }
            }
            
            # 添加到超图
            hypergraph.add_node(function_node_id, function_node_data)
            function_nodes.append(function_node_id)
            
            # 创建功能实现边（从功能节点到路径上每个方法的超边）
            implement_edge = HyperEdge(
                hyperedge_id=f"function_implements_{leaf_node}_{path_index}",
                nodes=[function_node_id] + path,  # 功能节点 + 路径上的所有方法
                edge_type="function_implements"
            )
            implement_edge.metadata = {
                "function_node": function_node_id,
                "implemented_by": path,
                "path_type": "leaf_to_entry"
            }
            hypergraph.add_hyperedge(implement_edge)
    
    logger.info(f"[FunctionNodeEnhancement] ✓ 添加了 {len(function_nodes)} 个功能节点")
    
    return hypergraph


def enhance_hypergraph_with_function_nodes(
    hypergraph: FunctionCallHypergraph,
    call_graph: Dict[str, Set[str]],
    partition_methods: Set[str],
    analyzer_report=None,
    max_path_length: int = 10,
    use_llm: bool = False,
    llm_agent=None,
    entry_points: Optional[List[str]] = None
) -> tuple[FunctionCallHypergraph, Dict[str, List[List[str]]]]:
    """
    增强超图：添加基于路径探索的功能节点
    
    关键说明：这是在**分区级别**进行的操作，所有路径探索都限制在 partition_methods 内
    
    Args:
        hypergraph: 原始超图对象（分区级别的，只包含该分区的方法）
        call_graph: 完整的调用图 {caller: Set[callees]}（包含整个项目的调用关系）
        partition_methods: 分区的methods集合（用于边界约束，确保路径在分区内）
        analyzer_report: 代码分析报告（用于LLM生成描述）
        max_path_length: 最大路径长度
        use_llm: 是否使用LLM生成功能描述
        llm_agent: LLM代理对象（如果use_llm=True）
        
    Returns:
        增强后的超图对象（包含功能节点）
    """
    logger.info(f"[FunctionNodeEnhancement] 开始增强超图，分区ID: {hypergraph.partition_id}")
    logger.info(f"[FunctionNodeEnhancement] 分区边界: {len(partition_methods)} 个方法")
    
    # 验证：超图中的节点应该在分区内
    hypergraph_nodes = set(hypergraph.nodes.keys())
    if not hypergraph_nodes.issubset(partition_methods):
        logger.warning(f"[FunctionNodeEnhancement] 警告：超图中存在不在分区内的节点，将被忽略")
        # 过滤超图节点，只保留分区内的节点
        for node_id in list(hypergraph.nodes.keys()):
            if node_id not in partition_methods:
                del hypergraph.nodes[node_id]
    
    # 步骤1：锁定分区内的叶子节点
    leaf_nodes = identify_leaf_nodes_in_partition(hypergraph, call_graph, partition_methods)
    logger.info(f"[FunctionNodeEnhancement] 找到 {len(leaf_nodes)} 个分区内的叶子节点: {leaf_nodes[:5]}...")  # 只显示前5个
    
    if not leaf_nodes:
        logger.warning("[FunctionNodeEnhancement] 未找到分区内的叶子节点，跳过功能节点增强")
        return hypergraph, {}
    
    # 步骤2：路径探索（限制在分区内）
    if entry_points:
        paths_map = explore_paths_in_partition_enhanced(
            leaf_nodes,
            entry_points,
            hypergraph,
            call_graph,
            partition_methods,
            max_path_length=max(max_path_length, 15),
        )
    else:
        paths_map = explore_paths_in_partition(
            leaf_nodes,
            hypergraph,
            call_graph,
            partition_methods,  # 关键：传递分区边界
            max_path_length
        )
    total_paths = sum(len(paths) for paths in paths_map.values())
    logger.info(f"[FunctionNodeEnhancement] 探索到 {total_paths} 条路径（全部限制在分区内）")
    
    # 步骤3：生成功能描述（目前只使用启发式方法，LLM支持待后续实现）
    descriptions_map = {}
    for leaf_node, paths in paths_map.items():
        descriptions = []
        for path in paths:
            # 验证路径在分区内（安全措施）
            if not all(node in partition_methods for node in path):
                logger.warning(f"[FunctionNodeEnhancement] 警告：路径包含分区外的节点，跳过: {path}")
                continue
            
            # 目前使用启发式方法生成描述（LLM支持待后续实现）
            if use_llm and llm_agent and analyzer_report:
                # TODO: 实现LLM生成描述的功能
                description = generate_function_description_heuristic(path, hypergraph)
            else:
                description = generate_function_description_heuristic(path, hypergraph)
            descriptions.append(description)
        descriptions_map[leaf_node] = descriptions
    
    # 步骤4：添加功能节点
    enhanced_hypergraph = add_function_nodes_to_hypergraph(hypergraph, paths_map, descriptions_map)
    
    new_function_nodes = len([n for n in enhanced_hypergraph.nodes.values() if n.get('type') == 'function'])
    logger.info(f"[FunctionNodeEnhancement] ✓ 超图增强完成，新增功能节点数: {new_function_nodes}")
    
    return enhanced_hypergraph, paths_map

