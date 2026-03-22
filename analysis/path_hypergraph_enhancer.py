#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
功能路径超图增强器 - 分析调用链类型并生成高亮配置
"""

from typing import Dict, List, Set, Optional, Any, Tuple
import logging

logger = logging.getLogger(__name__)


def analyze_path_call_chain_for_highlight(
    path: List[str],
    call_graph: Dict[str, Set[str]],
    call_chain_analysis: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    分析功能路径的调用链类型，生成超图高亮配置
    
    Args:
        path: 路径节点列表（方法签名）
        call_graph: 调用图 {caller: {callee1, callee2, ...}}
        call_chain_analysis: LLM分析的调用链类型结果（如果已有）
        
    Returns:
        高亮配置字典，包含：
        - path_methods: 路径上的方法列表
        - main_method: 总方法（如果有）
        - intermediate_methods: 中间方法列表
        - direct_calls: 直接调用关系列表
        - highlight_config: 高亮配置
            - path_nodes: 路径节点（绿色高亮）
            - main_method_nodes: 总方法节点（蓝色高亮）
            - intermediate_nodes: 中间方法节点（橙色高亮）
            - path_edges: 路径边（绿色粗线）
            - main_method_edges: 总方法到路径方法的边（蓝色粗线）
            - intermediate_edges: 中间方法相关的边（橙色粗线）
    """
    logger.info(f"[PathHypergraphEnhancer] 分析路径调用链: {path}")
    
    # 如果已有LLM分析结果，直接使用
    if call_chain_analysis:
        call_chain_type = call_chain_analysis.get('call_chain_type', '未知类型')
        main_method = call_chain_analysis.get('main_method')
        intermediate_methods = call_chain_analysis.get('intermediate_methods', [])
        direct_calls = call_chain_analysis.get('direct_calls', [])
        explanation = call_chain_analysis.get('explanation', '')
        
        logger.info(f"[PathHypergraphEnhancer]   - 调用链类型: {call_chain_type}")
        logger.info(f"[PathHypergraphEnhancer]   - 总方法: {main_method}")
        logger.info(f"[PathHypergraphEnhancer]   - 中间方法: {intermediate_methods}")
    else:
        # 如果没有LLM分析结果，使用启发式规则
        call_chain_type, main_method, intermediate_methods, direct_calls, explanation = _analyze_call_chain_heuristic(
            path, call_graph
        )
    
    # 分析直接调用关系
    if not direct_calls:
        direct_calls = []
        for i in range(len(path) - 1):
            caller = path[i]
            callee = path[i + 1]
            if caller in call_graph and callee in call_graph[caller]:
                direct_calls.append((caller, callee))
    
    # 查找总方法（如果LLM没有识别到，尝试从调用图中查找）
    if not main_method:
        main_method = _find_main_method(path, call_graph)
    
    # 查找中间方法（如果LLM没有识别到，尝试从调用图中查找）
    if not intermediate_methods:
        intermediate_methods = _find_intermediate_methods(path, call_graph, direct_calls)
    
    # 生成高亮配置
    highlight_config = _generate_highlight_config(
        path=path,
        main_method=main_method,
        intermediate_methods=intermediate_methods,
        direct_calls=direct_calls,
        call_graph=call_graph
    )
    
    return {
        'path_methods': path,
        'main_method': main_method,
        'intermediate_methods': intermediate_methods,
        'direct_calls': direct_calls,
        'call_chain_type': call_chain_type,
        'explanation': explanation,
        'highlight_config': highlight_config
    }


def _analyze_call_chain_heuristic(
    path: List[str],
    call_graph: Dict[str, Set[str]]
) -> Tuple[str, Optional[str], List[str], List[Tuple[str, str]], str]:
    """使用启发式规则分析调用链类型"""
    # 分析直接调用关系
    direct_calls = []
    for i in range(len(path) - 1):
        caller = path[i]
        callee = path[i + 1]
        if caller in call_graph and callee in call_graph[caller]:
            direct_calls.append((caller, callee))
    
    # 如果所有相邻方法都有直接调用关系，判断为直接顺序调用
    if len(direct_calls) == len(path) - 1:
        return (
            '直接顺序调用',
            None,
            [],
            direct_calls,
            f'路径上的方法形成直接顺序调用链：{" -> ".join(path)}。每个方法直接调用下一个方法。'
        )
    
    # 查找总方法
    main_method = _find_main_method(path, call_graph)
    if main_method:
        return (
            '总方法顺序调用',
            main_method,
            [],
            direct_calls,
            f'存在总方法 {main_method}，该总方法按顺序调用路径上的方法：{" -> ".join(path)}。数据流从第一个方法流向最后一个方法。'
        )
    
    # 查找中间方法
    intermediate_methods = _find_intermediate_methods(path, call_graph, direct_calls)
    if intermediate_methods:
        return (
            '中间方法桥接',
            None,
            intermediate_methods,
            direct_calls,
            f'路径上的方法通过中间方法建立调用关系：{" -> ".join(path)}。中间方法包括：{", ".join(intermediate_methods)}。'
        )
    
    # 其他情况
    return (
        '未知类型',
        None,
        [],
        direct_calls,
        f'无法确定调用链类型。路径：{" -> ".join(path)}。'
    )


def _find_main_method(path: List[str], call_graph: Dict[str, Set[str]]) -> Optional[str]:
    """查找总方法（调用路径上多个方法的）"""
    for method_sig in call_graph:
        if method_sig not in path:
            # 检查这个方法是否调用了路径上的多个方法
            called_path_methods = [m for m in path if m in call_graph.get(method_sig, set())]
            if len(called_path_methods) >= 2:
                # 检查是否按顺序调用
                called_indices = [path.index(m) for m in called_path_methods]
                if called_indices == sorted(called_indices):
                    return method_sig
    return None


def _find_intermediate_methods(
    path: List[str],
    call_graph: Dict[str, Set[str]],
    direct_calls: List[Tuple[str, str]]
) -> List[str]:
    """查找中间方法（连接路径上方法的方法）"""
    intermediate_methods = []
    
    # 对于路径上相邻但没有直接调用的方法对，查找中间方法
    for i in range(len(path) - 1):
        caller = path[i]
        callee = path[i + 1]
        
        # 如果已经有直接调用关系，跳过
        if (caller, callee) in direct_calls:
            continue
        
        # 查找中间方法：caller -> intermediate -> callee
        for intermediate in call_graph.get(caller, set()):
            if intermediate not in path and callee in call_graph.get(intermediate, set()):
                if intermediate not in intermediate_methods:
                    intermediate_methods.append(intermediate)
    
    return intermediate_methods


def _generate_highlight_config(
    path: List[str],
    main_method: Optional[str],
    intermediate_methods: List[str],
    direct_calls: List[Tuple[str, str]],
    call_graph: Dict[str, Set[str]]
) -> Dict[str, Any]:
    """生成高亮配置"""
    config = {
        'path_nodes': path,  # 路径节点（绿色高亮）
        'main_method_nodes': [],  # 总方法节点（蓝色高亮）
        'intermediate_nodes': intermediate_methods,  # 中间方法节点（橙色高亮）
        'path_edges': direct_calls,  # 路径边（绿色粗线）
        'main_method_edges': [],  # 总方法到路径方法的边（蓝色粗线）
        'intermediate_edges': []  # 中间方法相关的边（橙色粗线）
    }
    
    # 如果有总方法，添加总方法节点和边
    if main_method:
        config['main_method_nodes'] = [main_method]
        # 查找总方法到路径方法的边
        if main_method in call_graph:
            for path_method in path:
                if path_method in call_graph[main_method]:
                    config['main_method_edges'].append((main_method, path_method))
    
    # 添加中间方法相关的边
    for intermediate in intermediate_methods:
        # 查找路径方法 -> 中间方法的边
        for path_method in path:
            if path_method in call_graph and intermediate in call_graph[path_method]:
                config['intermediate_edges'].append((path_method, intermediate))
        
        # 查找中间方法 -> 路径方法的边
        if intermediate in call_graph:
            for path_method in path:
                if path_method in call_graph[intermediate]:
                    config['intermediate_edges'].append((intermediate, path_method))
    
    return config














