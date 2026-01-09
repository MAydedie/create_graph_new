#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
功能级控制流图生成器 - 为功能分区生成控制流图
合并分区内多个方法的CFG，通过方法调用连接不同方法的CFG
"""

from typing import Dict, List, Set, Optional, Any, Tuple
import logging

from .cfg_generator import CFGGenerator, ControlFlowGraph, CFGNode, CFGEdge

logger = logging.getLogger(__name__)


class PartitionControlFlowGraph:
    """功能级控制流图"""
    
    def __init__(self, partition_id: str):
        """
        初始化控制流图
        
        Args:
            partition_id: 功能分区ID
        """
        self.partition_id = partition_id
        self.method_cfg_map: Dict[str, ControlFlowGraph] = {}  # method_sig -> CFG
        self.merged_nodes: Dict[str, CFGNode] = {}  # 合并后的节点
        self.merged_edges: List[CFGEdge] = []  # 合并后的边
        self.method_call_edges: List[Dict[str, Any]] = []  # 方法调用边（连接不同方法的CFG）
        self.cycles: List[List[str]] = []  # 循环调用列表
    
    def add_method_cfg(self, method_sig: str, cfg: ControlFlowGraph):
        """添加方法的CFG"""
        self.method_cfg_map[method_sig] = cfg
    
    def merge_method_cfg(self, call_graph: Dict[str, Set[str]], 
                        partition_methods: Set[str]):
        """
        合并所有方法的CFG
        
        通过方法调用连接不同方法的CFG节点
        """
        node_id_map: Dict[Tuple[str, str], str] = {}  # (method_sig, original_node_id) -> merged_node_id
        node_counter = 0
        
        # 1. 合并所有方法的节点（添加方法前缀以避免冲突）
        for method_sig, cfg in self.method_cfg_map.items():
            for original_node_id, node in cfg.nodes.items():
                merged_node_id = f"{method_sig}_{original_node_id}"
                node_id_map[(method_sig, original_node_id)] = merged_node_id
                
                # 创建新节点（添加方法信息）
                merged_node = CFGNode(
                    node_id=merged_node_id,
                    node_type=node.node_type,
                    label=f"[{method_sig}] {node.label}",
                    line_number=node.line_number,
                    code=node.code
                )
                merged_node.metadata = {
                    "method_sig": method_sig,
                    "original_node_id": original_node_id
                }
                self.merged_nodes[merged_node_id] = merged_node
        
        # 2. 合并所有方法的边（内部边）
        for method_sig, cfg in self.method_cfg_map.items():
            for edge in cfg.edges:
                source_key = (method_sig, edge.source_id)
                target_key = (method_sig, edge.target_id)
                
                if source_key in node_id_map and target_key in node_id_map:
                    merged_edge = CFGEdge(
                        source_id=node_id_map[source_key],
                        target_id=node_id_map[target_key],
                        edge_type=edge.edge_type
                    )
                    merged_edge.metadata = {
                        "method_sig": method_sig,
                        "edge_type": "internal"
                    }
                    self.merged_edges.append(merged_edge)
        
        # 3. 通过方法调用连接不同方法的CFG
        self._connect_method_calls(call_graph, partition_methods, node_id_map)
        
        # 4. 识别循环
        self.cycles = self._identify_cycles(call_graph, partition_methods)
        
        logger.info(f"[PartitionControlFlowGraph] ✓ 合并完成: {len(self.merged_nodes)}个节点, "
                   f"{len(self.merged_edges)}条边, {len(self.method_call_edges)}条方法调用边, "
                   f"{len(self.cycles)}个循环")
    
    def _connect_method_calls(self,
                              call_graph: Dict[str, Set[str]],
                              partition_methods: Set[str],
                              node_id_map: Dict[Tuple[str, str], str]):
        """
        通过方法调用连接不同方法的CFG
        
        当方法A调用方法B时，在A的CFG中找到调用节点，连接到B的CFG入口节点
        """
        # 为每个方法找到调用节点和入口/出口节点
        method_call_nodes: Dict[str, List[str]] = {}  # method_sig -> [call_node_ids]
        method_entry_nodes: Dict[str, str] = {}  # method_sig -> entry_node_id
        method_exit_nodes: Dict[str, str] = {}  # method_sig -> exit_node_id
        
        for method_sig, cfg in self.method_cfg_map.items():
            # 找到入口节点
            for node_id, node in cfg.nodes.items():
                if node.node_type == "entry":
                    method_entry_nodes[method_sig] = node_id_map.get((method_sig, node_id))
                    break
            
            # 找到出口节点
            for node_id, node in cfg.nodes.items():
                if node.node_type == "exit":
                    method_exit_nodes[method_sig] = node_id_map.get((method_sig, node_id))
                    break
            
            # 找到调用节点（包含Call表达式的节点）
            call_nodes = []
            for node_id, node in cfg.nodes.items():
                if node.code and ("(" in node.code or "call" in node.code.lower()):
                    # 简单检查：如果代码包含函数调用特征
                    call_nodes.append(node_id_map.get((method_sig, node_id)))
            method_call_nodes[method_sig] = [n for n in call_nodes if n]
        
        # 连接方法调用
        for caller in partition_methods:
            if caller not in call_graph:
                continue
            
            caller_entry = method_entry_nodes.get(caller)
            caller_call_nodes = method_call_nodes.get(caller, [])
            
            for callee in call_graph[caller]:
                if callee not in partition_methods:
                    continue
                
                callee_entry = method_entry_nodes.get(callee)
                callee_exit = method_exit_nodes.get(callee)
                
                if caller_entry and callee_entry:
                    # 从调用节点连接到被调用方法的入口
                    for call_node_id in caller_call_nodes:
                        if call_node_id:
                            # 创建方法调用边
                            call_edge = CFGEdge(
                                source_id=call_node_id,
                                target_id=callee_entry,
                                edge_type="method_call"
                            )
                            call_edge.metadata = {
                                "caller": caller,
                                "callee": callee,
                                "edge_type": "method_call"
                            }
                            self.merged_edges.append(call_edge)
                            
                            # 记录方法调用边（用于可视化）
                            self.method_call_edges.append({
                                "source": call_node_id,
                                "target": callee_entry,
                                "caller": caller,
                                "callee": callee
                            })
                            
                            # 从被调用方法的出口返回到调用节点之后
                            if callee_exit:
                                return_edge = CFGEdge(
                                    source_id=callee_exit,
                                    target_id=call_node_id,
                                    edge_type="return"
                                )
                                return_edge.metadata = {
                                    "caller": caller,
                                    "callee": callee,
                                    "edge_type": "return"
                                }
                                self.merged_edges.append(return_edge)
    
    def _identify_cycles(self,
                        call_graph: Dict[str, Set[str]],
                        partition_methods: Set[str]) -> List[List[str]]:
        """识别功能分区内的循环调用"""
        cycles = []
        visited = set()
        
        def dfs(node: str, path: List[str]):
            if node in path:
                # 找到循环
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                if cycle not in cycles:
                    cycles.append(cycle)
                return
            
            if node in visited or node not in partition_methods:
                return
            
            visited.add(node)
            
            if node in call_graph:
                for callee in call_graph[node]:
                    if callee in partition_methods:
                        dfs(callee, path + [node])
        
        for method in partition_methods:
            if method not in visited:
                dfs(method, [])
        
        return cycles
    
    def to_visualization_data(self) -> Dict[str, Any]:
        """生成可视化数据（Cytoscape.js格式）"""
        nodes = []
        edges = []
        
        # 添加节点
        for node_id, node in self.merged_nodes.items():
            nodes.append({
                "data": {
                    "id": node_id,
                    "label": node.label,
                    "type": node.node_type,
                    "line_number": node.line_number,
                    "code": node.code[:100] if node.code else "",  # 截断长代码
                    "method_sig": node.metadata.get("method_sig", "") if hasattr(node, 'metadata') else ""
                }
            })
        
        # 添加边
        for edge in self.merged_edges:
            edge_data = {
                "id": f"{edge.source_id}->{edge.target_id}",
                "source": edge.source_id,
                "target": edge.target_id,
                "label": edge.edge_type,
                "type": edge.edge_type,
                "relation": "control_flow"
            }
            
            # 添加元数据
            if hasattr(edge, 'metadata'):
                edge_data.update(edge.metadata)
            
            edges.append({"data": edge_data})
        
        return {
            "nodes": nodes,
            "edges": edges,
            "method_call_edges": self.method_call_edges,
            "cycles": self.cycles,
            "statistics": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_methods": len(self.method_cfg_map),
                "method_call_edges_count": len(self.method_call_edges),
                "cycles_count": len(self.cycles)
            }
        }
    
    def to_dot(self) -> str:
        """转换为DOT格式"""
        lines = [f'digraph "{self.partition_id}_CFG" {{']
        lines.append('  rankdir=TB;')
        lines.append('  node [shape=box];')
        
        # 添加节点
        for node_id, node in self.merged_nodes.items():
            label = node.label.replace('"', '\\"')
            color = "lightblue" if node.node_type == "entry" else "lightcoral" if node.node_type == "exit" else "white"
            lines.append(f'  "{node_id}" [label="{label}", style=filled, fillcolor={color}];')
        
        # 添加边
        for edge in self.merged_edges:
            edge_attr = ""
            if edge.edge_type == "method_call":
                edge_attr = ' [label="call", color="blue", style="dashed"]'
            elif edge.edge_type == "return":
                edge_attr = ' [label="return", color="green", style="dashed"]'
            elif edge.edge_type == "true":
                edge_attr = ' [label="True", color="green"]'
            elif edge.edge_type == "false":
                edge_attr = ' [label="False", color="red"]'
            elif edge.edge_type == "loop_back":
                edge_attr = ' [label="Loop", color="blue"]'
            
            lines.append(f'  "{edge.source_id}" -> "{edge.target_id}"{edge_attr};')
        
        lines.append('}')
        return '\n'.join(lines)


class PartitionControlFlowGenerator:
    """功能级控制流图生成器"""
    
    def __init__(self, 
                 call_graph: Dict[str, Set[str]],
                 analyzer_report):
        """
        初始化生成器
        
        Args:
            call_graph: 调用图
            analyzer_report: 代码分析报告
        """
        self.call_graph = call_graph
        self.analyzer_report = analyzer_report
        self.cfg_generator = CFGGenerator()
    
    def generate_partition_control_flow(self,
                                        partition: Dict[str, Any]) -> PartitionControlFlowGraph:
        """
        为功能分区生成控制流图
        
        Args:
            partition: 功能分区字典，包含：
                - partition_id: 分区ID
                - methods: 方法签名列表
        
        Returns:
            PartitionControlFlowGraph对象
        """
        partition_id = partition.get("partition_id", "unknown")
        partition_methods = set(partition.get("methods", []))
        
        logger.info(f"[PartitionControlFlowGenerator] 生成分区 {partition_id} 的控制流图，方法数: {len(partition_methods)}")
        
        # 创建控制流图
        partition_cfg = PartitionControlFlowGraph(partition_id)
        
        # 1. 为每个方法生成CFG
        for method_sig in partition_methods:
            method_cfg = self._generate_method_cfg(method_sig)
            if method_cfg:
                partition_cfg.add_method_cfg(method_sig, method_cfg)
        
        # 2. 合并所有方法的CFG
        partition_cfg.merge_method_cfg(self.call_graph, partition_methods)
        
        logger.info(f"[PartitionControlFlowGenerator] ✓ 生成完成: "
                   f"{len(partition_cfg.merged_nodes)}个节点, "
                   f"{len(partition_cfg.merged_edges)}条边, "
                   f"{len(partition_cfg.cycles)}个循环")
        
        return partition_cfg
    
    def _generate_method_cfg(self, method_sig: str) -> Optional[ControlFlowGraph]:
        """为单个方法生成CFG"""
        if not self.analyzer_report:
            return None
        
        # 解析方法签名
        if "." in method_sig:
            class_name, method_name = method_sig.rsplit(".", 1)
            if class_name in self.analyzer_report.classes:
                class_info = self.analyzer_report.classes[class_name]
                if method_name in class_info.methods:
                    method_info = class_info.methods[method_name]
                    source_code = method_info.source_code or ""
                    
                    if source_code:
                        return self.cfg_generator.generate_cfg(source_code, method_sig)
        
        return None
    
    def generate_all_partitions_control_flow(self,
                                            partitions: List[Dict[str, Any]]) -> Dict[str, PartitionControlFlowGraph]:
        """
        为所有功能分区生成控制流图
        
        Args:
            partitions: 功能分区列表
        
        Returns:
            {partition_id: PartitionControlFlowGraph}
        """
        results = {}
        
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            partition_cfg = self.generate_partition_control_flow(partition)
            results[partition_id] = partition_cfg
        
        logger.info(f"[PartitionControlFlowGenerator] ✓ 为 {len(results)} 个分区生成了控制流图")
        
        return results


def main():
    """测试代码"""
    # 这里需要实际的analyzer_report，所以测试代码简化
    print("=" * 60)
    print("功能级控制流图生成器测试")
    print("=" * 60)
    print("注意：完整测试需要提供analyzer_report对象")
    print("请在实际使用中调用generate_partition_control_flow()方法")


if __name__ == "__main__":
    main()




















