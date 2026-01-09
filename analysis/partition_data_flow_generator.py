#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
功能级数据流图生成器 - 为功能分区生成数据流图
合并分区内多个方法的数据流，追踪参数流动、返回值流动和共享状态
"""

from typing import Dict, List, Set, Optional, Any, Tuple
import logging

from .dfg_generator import DFGGenerator, DataFlowGraph
from .data_flow_analyzer import DataFlowAnalyzer

logger = logging.getLogger(__name__)


class PartitionDataFlowGraph:
    """功能级数据流图"""
    
    def __init__(self, partition_id: str):
        """
        初始化数据流图
        
        Args:
            partition_id: 功能分区ID
        """
        self.partition_id = partition_id
        self.method_dfg_map: Dict[str, DataFlowGraph] = {}  # method_sig -> DFG
        self.parameter_flows: List[Dict[str, Any]] = []  # 参数流动列表
        self.return_value_flows: List[Dict[str, Any]] = []  # 返回值流动列表
        self.shared_states: Set[str] = set()  # 共享状态（类字段、全局变量）
        self.merged_nodes: Dict[str, Dict[str, Any]] = {}  # 合并后的节点
        self.merged_edges: List[Dict[str, Any]] = []  # 合并后的边
    
    def add_method_dfg(self, method_sig: str, dfg: DataFlowGraph):
        """添加方法的DFG"""
        self.method_dfg_map[method_sig] = dfg
    
    def merge_method_dfg(self):
        """合并所有方法的DFG"""
        node_id_map: Dict[str, str] = {}  # 原始节点ID -> 合并后节点ID
        node_counter = 0
        
        # 1. 合并节点（去重变量名）
        variable_nodes: Dict[str, Dict[str, Any]] = {}  # variable_name -> node_data
        
        for method_sig, dfg in self.method_dfg_map.items():
            for node_id, node in dfg.nodes.items():
                var_name = node.variable_name
                key = f"{method_sig}:{var_name}"
                
                if key not in variable_nodes:
                    merged_node_id = f"dfg_node_{node_counter}"
                    node_counter += 1
                    
                    variable_nodes[key] = {
                        "id": merged_node_id,
                        "variable_name": var_name,
                        "node_type": node.node_type,
                        "methods": [method_sig],
                        "line_numbers": [node.line_number],
                        "code_snippets": [node.code]
                    }
                    node_id_map[node_id] = merged_node_id
                else:
                    # 合并到已有节点
                    variable_nodes[key]["methods"].append(method_sig)
                    variable_nodes[key]["line_numbers"].append(node.line_number)
                    variable_nodes[key]["code_snippets"].append(node.code)
                    node_id_map[node_id] = variable_nodes[key]["id"]
        
        self.merged_nodes = variable_nodes
        
        # 2. 合并边
        edge_set: Set[Tuple[str, str, str]] = set()  # (source, target, var_name)
        
        for method_sig, dfg in self.method_dfg_map.items():
            for edge in dfg.edges:
                source_id = node_id_map.get(edge.source_id)
                target_id = node_id_map.get(edge.target_id)
                
                if source_id and target_id:
                    edge_key = (source_id, target_id, edge.variable_name)
                    if edge_key not in edge_set:
                        edge_set.add(edge_key)
                        self.merged_edges.append({
                            "source": source_id,
                            "target": target_id,
                            "variable_name": edge.variable_name,
                            "methods": [method_sig]
                        })
                    else:
                        # 更新边的方法列表
                        for merged_edge in self.merged_edges:
                            if (merged_edge["source"] == source_id and 
                                merged_edge["target"] == target_id and
                                merged_edge["variable_name"] == edge.variable_name):
                                if method_sig not in merged_edge["methods"]:
                                    merged_edge["methods"].append(method_sig)
                                break
        
        logger.info(f"[PartitionDataFlowGraph] ✓ 合并完成: {len(self.merged_nodes)}个节点, "
                   f"{len(self.merged_edges)}条边")
    
    def to_visualization_data(self) -> Dict[str, Any]:
        """生成可视化数据（Cytoscape.js格式）"""
        nodes = []
        edges = []
        
        # 添加节点
        for node_id, node_data in self.merged_nodes.items():
            nodes.append({
                "data": {
                    "id": node_id,
                    "label": node_data["variable_name"],
                    "type": node_data["node_type"],
                    "variable_name": node_data["variable_name"],
                    "methods": node_data["methods"],
                    "method_count": len(node_data["methods"])
                }
            })
        
        # 添加边
        for edge in self.merged_edges:
            edges.append({
                "data": {
                    "id": f"{edge['source']}->{edge['target']}",
                    "source": edge["source"],
                    "target": edge["target"],
                    "label": edge["variable_name"],
                    "variable_name": edge["variable_name"],
                    "methods": edge["methods"],
                    "relation": "data_flow"
                }
            })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "parameter_flows": self.parameter_flows,
            "return_value_flows": self.return_value_flows,
            "shared_states": list(self.shared_states),
            "statistics": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_methods": len(self.method_dfg_map),
                "parameter_flows_count": len(self.parameter_flows),
                "return_value_flows_count": len(self.return_value_flows),
                "shared_states_count": len(self.shared_states)
            }
        }


class PartitionDataFlowGenerator:
    """功能级数据流图生成器"""
    
    def __init__(self, 
                 call_graph: Dict[str, Set[str]],
                 analyzer_report,
                 data_flow_analyzer: DataFlowAnalyzer = None):
        """
        初始化生成器
        
        Args:
            call_graph: 调用图
            analyzer_report: 代码分析报告
            data_flow_analyzer: 数据流分析器（可选，如果已存在）
        """
        self.call_graph = call_graph
        self.analyzer_report = analyzer_report
        self.data_flow_analyzer = data_flow_analyzer or DataFlowAnalyzer()
        self.dfg_generator = DFGGenerator()
    
    def generate_partition_data_flow(self,
                                     partition: Dict[str, Any],
                                     entry_points: List[Any] = None) -> PartitionDataFlowGraph:
        """
        为功能分区生成数据流图
        
        Args:
            partition: 功能分区字典，包含：
                - partition_id: 分区ID
                - methods: 方法签名列表
            entry_points: 入口点列表（可选，用于从入口点开始追踪）
        
        Returns:
            PartitionDataFlowGraph对象
        """
        partition_id = partition.get("partition_id", "unknown")
        partition_methods = set(partition.get("methods", []))
        
        logger.info(f"[PartitionDataFlowGenerator] 生成分区 {partition_id} 的数据流图，方法数: {len(partition_methods)}")
        
        # 创建数据流图
        partition_dfg = PartitionDataFlowGraph(partition_id)
        
        # 1. 为每个方法生成DFG
        for method_sig in partition_methods:
            method_dfg = self._generate_method_dfg(method_sig)
            if method_dfg:
                partition_dfg.add_method_dfg(method_sig, method_dfg)
        
        # 2. 合并所有方法的DFG
        partition_dfg.merge_method_dfg()
        
        # 3. 追踪参数流动（从入口点开始）
        if entry_points:
            partition_dfg.parameter_flows = self._trace_parameter_flows(
                partition_dfg, partition_methods, entry_points
            )
        else:
            partition_dfg.parameter_flows = self._trace_parameter_flows(
                partition_dfg, partition_methods
            )
        
        # 4. 追踪返回值流动
        partition_dfg.return_value_flows = self._trace_return_value_flows(
            partition_dfg, partition_methods
        )
        
        # 5. 识别共享状态
        partition_dfg.shared_states = self._identify_shared_states(
            partition_methods
        )
        
        logger.info(f"[PartitionDataFlowGenerator] ✓ 生成完成: "
                   f"{len(partition_dfg.merged_nodes)}个节点, "
                   f"{len(partition_dfg.merged_edges)}条边, "
                   f"{len(partition_dfg.parameter_flows)}个参数流动, "
                   f"{len(partition_dfg.shared_states)}个共享状态")
        
        return partition_dfg
    
    def _generate_method_dfg(self, method_sig: str) -> Optional[DataFlowGraph]:
        """为单个方法生成DFG"""
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
                        return self.dfg_generator.generate_dfg(source_code, method_sig)
        
        return None
    
    def _trace_parameter_flows(self,
                               partition_dfg: PartitionDataFlowGraph,
                               partition_methods: Set[str],
                               entry_points: List[Any] = None) -> List[Dict[str, Any]]:
        """
        追踪参数流动
        
        从入口点开始，追踪参数在方法间的传递
        """
        parameter_flows = []
        
        # 使用data_flow_analyzer的参数流动数据
        if hasattr(self.data_flow_analyzer, 'parameter_flows'):
            for flow in self.data_flow_analyzer.parameter_flows:
                caller, param_name, callee = flow
                if caller in partition_methods and callee in partition_methods:
                    parameter_flows.append({
                        "source_method": caller,
                        "parameter_name": param_name,
                        "target_method": callee,
                        "flow_type": "parameter"
                    })
        
        return parameter_flows
    
    def _trace_return_value_flows(self,
                                 partition_dfg: PartitionDataFlowGraph,
                                 partition_methods: Set[str]) -> List[Dict[str, Any]]:
        """
        追踪返回值流动
        
        追踪方法的返回值如何被其他方法使用
        """
        return_flows = []
        
        # 从调用图中查找返回值流动
        for caller in partition_methods:
            if caller in self.call_graph:
                for callee in self.call_graph[caller]:
                    if callee in partition_methods:
                        # 假设callee的返回值被caller使用
                        return_flows.append({
                            "source_method": callee,
                            "target_method": caller,
                            "flow_type": "return_value"
                        })
        
        return return_flows
    
    def _identify_shared_states(self, partition_methods: Set[str]) -> Set[str]:
        """
        识别共享状态
        
        共享状态包括：
        1. 类字段（被多个方法访问）
        2. 全局变量（被多个方法访问）
        """
        shared_states = set()
        
        if not self.analyzer_report:
            return shared_states
        
        # 1. 识别类字段
        field_access_count: Dict[str, Set[str]] = {}  # field_name -> {method_sigs}
        
        for method_sig in partition_methods:
            if "." in method_sig:
                class_name, method_name = method_sig.rsplit(".", 1)
                if class_name in self.analyzer_report.classes:
                    class_info = self.analyzer_report.classes[class_name]
                    if method_name in class_info.methods:
                        method_info = class_info.methods[method_name]
                        
                        # 获取方法访问的字段
                        if method_sig in self.data_flow_analyzer.field_accesses:
                            accessed_fields = self.data_flow_analyzer.field_accesses[method_sig]
                            for field in accessed_fields:
                                if field not in field_access_count:
                                    field_access_count[field] = set()
                                field_access_count[field].add(method_sig)
        
        # 如果字段被多个方法访问，则认为是共享状态
        for field, methods in field_access_count.items():
            if len(methods) >= 2:
                shared_states.add(f"{class_name}.{field}")
        
        return shared_states
    
    def generate_all_partitions_data_flow(self,
                                         partitions: List[Dict[str, Any]],
                                         entry_points_map: Dict[str, List[Any]] = None) -> Dict[str, PartitionDataFlowGraph]:
        """
        为所有功能分区生成数据流图
        
        Args:
            partitions: 功能分区列表
            entry_points_map: {partition_id: [EntryPoint]}（可选）
        
        Returns:
            {partition_id: PartitionDataFlowGraph}
        """
        results = {}
        
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            entry_points = entry_points_map.get(partition_id, []) if entry_points_map else None
            
            partition_dfg = self.generate_partition_data_flow(partition, entry_points)
            results[partition_id] = partition_dfg
        
        logger.info(f"[PartitionDataFlowGenerator] ✓ 为 {len(results)} 个分区生成了数据流图")
        
        return results


def main():
    """测试代码"""
    # 这里需要实际的analyzer_report，所以测试代码简化
    print("=" * 60)
    print("功能级数据流图生成器测试")
    print("=" * 60)
    print("注意：完整测试需要提供analyzer_report对象")
    print("请在实际使用中调用generate_partition_data_flow()方法")


if __name__ == "__main__":
    main()




















