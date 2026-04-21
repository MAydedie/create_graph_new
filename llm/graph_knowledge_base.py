#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图知识库摘要生成器 - 从图数据生成摘要，减少 LLM token 消耗
核心思想：只发送图的结构摘要，而非完整图数据
"""

from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict, Counter
from pathlib import Path
import json


class GraphKnowledgeBase:
    """图知识库摘要生成器"""
    
    def __init__(self, graph_data: Dict[str, Any]):
        """
        初始化图知识库
        
        Args:
            graph_data: 完整的图数据（包含 nodes 和 edges）
        """
        self.graph_data = graph_data
        self.nodes = graph_data.get('nodes', [])
        self.edges = graph_data.get('edges', [])
        self.metadata = graph_data.get('metadata', {})
    
    def generate_summary(self) -> Dict[str, Any]:
        """
        生成图知识库摘要
        
        Returns:
            图摘要字典，包含：
            - node_stats: 节点统计
            - edge_stats: 边统计
            - key_paths: 关键路径（最重要的调用链）
            - module_dependencies: 模块依赖关系
            - entry_points: 入口点
        """
        summary = {
            'node_stats': self._get_node_stats(),
            'edge_stats': self._get_edge_stats(),
            'key_paths': self._get_key_paths(),
            'module_dependencies': self._get_module_dependencies(),
            'entry_points': self._get_entry_points(),
            'call_frequency': self._get_call_frequency()
        }
        
        return summary
    
    def _get_node_stats(self) -> Dict[str, int]:
        """获取节点统计信息"""
        stats = {
            'total': len(self.nodes),
            'classes': 0,
            'methods': 0,
            'functions': 0,
            'fields': 0,
            'files': 0
        }
        
        for node in self.nodes:
            node_type = node.get('data', {}).get('type', '')
            if node_type == 'class':
                stats['classes'] += 1
            elif node_type == 'method':
                stats['methods'] += 1
            elif node_type == 'function':
                stats['functions'] += 1
            elif node_type == 'field':
                stats['fields'] += 1
            elif node_type == 'file':
                stats['files'] += 1
        
        return stats
    
    def _get_edge_stats(self) -> Dict[str, int]:
        """获取边统计信息"""
        stats = {
            'total': len(self.edges),
            'calls': 0,
            'inherits': 0,
            'accesses': 0,
            'contains': 0,
            'cross_file_call': 0,
            'parameter_flow': 0
        }
        
        for edge in self.edges:
            relation = edge.get('data', {}).get('relation') or edge.get('data', {}).get('type', '')
            if relation in stats:
                stats[relation] += 1
        
        return stats
    
    def _get_key_paths(self, max_paths: int = 10) -> List[str]:
        """
        获取关键路径（最重要的调用链）
        
        策略：
        1. 找到被调用次数最多的方法
        2. 从这些方法开始，追踪调用链
        3. 返回前 N 条最重要的路径
        """
        # 统计每个节点的入度（被调用次数）
        in_degree = defaultdict(int)
        call_graph = defaultdict(list)
        
        for edge in self.edges:
            edge_data = edge.get('data', {})
            relation = edge_data.get('relation') or edge_data.get('type', '')
            if relation == 'calls':
                source = edge_data.get('source')
                target = edge_data.get('target')
                if source and target:
                    in_degree[target] += 1
                    call_graph[source].append(target)
        
        # 找到入度最高的节点（被调用最多的）
        top_nodes = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:max_paths]
        
        # 为每个重要节点生成一条关键路径
        key_paths = []
        for node_id, count in top_nodes:
            # 找到调用这个节点的路径
            path = self._trace_path_to_node(node_id, call_graph)
            if path:
                key_paths.append(' → '.join(path[:5]))  # 只显示前5个节点
        
        return key_paths[:max_paths]
    
    def _trace_path_to_node(self, target_node: str, call_graph: Dict[str, List[str]], 
                           max_depth: int = 5) -> List[str]:
        """追踪到目标节点的路径"""
        # 找到所有调用 target_node 的节点
        for source, targets in call_graph.items():
            if target_node in targets:
                if max_depth > 0:
                    # 递归追踪
                    parent_path = self._trace_path_to_node(source, call_graph, max_depth - 1)
                    if parent_path:
                        return parent_path + [source, target_node]
                    else:
                        return [source, target_node]
                else:
                    return [source, target_node]
        
        return [target_node]
    
    def _get_module_dependencies(self) -> Dict[str, List[str]]:
        """获取模块依赖关系（文件夹间的调用关系）"""
        # 从节点中提取文件路径，然后提取文件夹
        file_to_folder = {}
        for node in self.nodes:
            node_data = node.get('data', {})
            file_path = node_data.get('file', '')
            if file_path:
                # 提取文件夹路径（绝对路径）
                folder = str(Path(file_path).parent) if file_path else ''
                file_to_folder[node_data.get('id')] = folder
        
        # 统计文件夹间的调用关系
        folder_calls = defaultdict(set)
        for edge in self.edges:
            edge_data = edge.get('data', {})
            relation = edge_data.get('relation') or edge_data.get('type', '')
            if relation == 'calls':
                source = edge_data.get('source')
                target = edge_data.get('target')
                source_folder = file_to_folder.get(source)
                target_folder = file_to_folder.get(target)
                if source_folder and target_folder and source_folder != target_folder:
                    folder_calls[source_folder].add(target_folder)
        
        # 转换为列表格式
        dependencies = {}
        for source_folder, target_folders in folder_calls.items():
            dependencies[source_folder] = list(target_folders)
        
        return dependencies
    
    def _get_entry_points(self) -> List[str]:
        """获取入口点（main、__main__ 等）"""
        entry_points = []
        
        for node in self.nodes:
            node_data = node.get('data', {})
            node_id = node_data.get('id', '')
            node_label = node_data.get('label', '')
            
            # 检查是否是入口点
            if 'main' in node_id.lower() or 'main' in node_label.lower():
                entry_points.append(node_id)
        
        return entry_points
    
    def _get_call_frequency(self, top_n: int = 20) -> List[Tuple[str, int]]:
        """获取调用频率最高的方法"""
        call_count = Counter()
        
        for edge in self.edges:
            edge_data = edge.get('data', {})
            relation = edge_data.get('relation') or edge_data.get('type', '')
            if relation == 'calls':
                target = edge_data.get('target')
                if target:
                    call_count[target] += 1
        
        return call_count.most_common(top_n)
    
    def to_text_summary(self, max_length: int = 2000) -> str:
        """
        将摘要转换为文本格式（用于 LLM Prompt）
        
        Args:
            max_length: 最大长度（字符数）
            
        Returns:
            文本摘要
        """
        summary = self.generate_summary()
        
        text = f"""图知识库摘要：

节点统计：
- 总节点数: {summary['node_stats']['total']}
- 类: {summary['node_stats']['classes']}
- 方法: {summary['node_stats']['methods']}
- 函数: {summary['node_stats']['functions']}

边统计：
- 总边数: {summary['edge_stats']['total']}
- 调用关系: {summary['edge_stats']['calls']}
- 继承关系: {summary['edge_stats']['inherits']}
- 跨文件调用: {summary['edge_stats']['cross_file_call']}

关键路径（最重要的调用链）：
"""
        for i, path in enumerate(summary['key_paths'][:5], 1):
            text += f"{i}. {path}\n"
        
        text += f"\n模块依赖关系：\n"
        for source, targets in list(summary['module_dependencies'].items())[:10]:
            text += f"- {source} → {', '.join(targets[:3])}\n"
        
        text += f"\n入口点：{', '.join(summary['entry_points'][:5])}\n"
        
        # 截断到最大长度
        if len(text) > max_length:
            text = text[:max_length] + "..."
        
        return text

