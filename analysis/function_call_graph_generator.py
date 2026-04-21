#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
函数调用图生成器 - 为功能分区生成调用图
提取分区内部的方法子集，构建调用关系子图，识别跨分区调用
"""

from typing import Dict, List, Set, Optional, Any
import logging

logger = logging.getLogger(__name__)


class FunctionCallGraphGenerator:
    """函数调用图生成器"""
    
    def __init__(self, call_graph: Dict[str, Set[str]]):
        """
        初始化生成器
        
        Args:
            call_graph: 完整的调用图 {caller: Set[callees]}
        """
        self.call_graph = call_graph
    
    def generate_partition_call_graph(self, 
                                     partition: Dict[str, Any]) -> Dict[str, Any]:
        """
        为功能分区生成调用图
        
        Args:
            partition: 功能分区字典，包含：
                - partition_id: 分区ID
                - methods: 方法签名列表
        
        Returns:
            调用图字典：
            {
                "partition_id": str,
                "internal_edges": List[Dict],  # 分区内部调用边
                "external_edges": List[Dict],  # 跨分区调用边
                "nodes": List[Dict],  # 节点列表
                "statistics": Dict  # 统计信息
            }
        """
        partition_id = partition.get("partition_id", "unknown")
        partition_methods = set(partition.get("methods", []))
        
        logger.info(f"[FunctionCallGraphGenerator] 生成分区 {partition_id} 的调用图，方法数: {len(partition_methods)}")
        
        # 提取内部边和外部边
        internal_edges = []
        external_edges = []
        all_nodes = set(partition_methods)
        
        for caller in partition_methods:
            if caller not in self.call_graph:
                continue
            
            for callee in self.call_graph[caller]:
                edge = {
                    "source": caller,
                    "target": callee,
                    "type": "calls"
                }
                
                if callee in partition_methods:
                    # 内部调用
                    internal_edges.append(edge)
                    all_nodes.add(callee)
                else:
                    # 跨分区调用
                    external_edges.append(edge)
                    all_nodes.add(callee)  # 外部节点也包含在图中（用于显示跨分区调用）
        
        # 构建节点列表
        nodes = []
        for method_sig in all_nodes:
            node = {
                "id": method_sig,
                "label": method_sig,
                "type": "method",
                "is_internal": method_sig in partition_methods
            }
            nodes.append(node)
        
        # 计算统计信息
        statistics = {
            "total_nodes": len(nodes),
            "internal_nodes": len(partition_methods),
            "external_nodes": len(all_nodes - partition_methods),
            "internal_edges": len(internal_edges),
            "external_edges": len(external_edges),
            "total_edges": len(internal_edges) + len(external_edges)
        }
        
        result = {
            "partition_id": partition_id,
            "internal_edges": internal_edges,
            "external_edges": external_edges,
            "nodes": nodes,
            "statistics": statistics
        }
        
        logger.info(f"[FunctionCallGraphGenerator] ✓ 生成完成: {statistics['internal_nodes']}个内部节点, "
                   f"{statistics['internal_edges']}条内部边, {statistics['external_edges']}条外部边")
        
        return result
    
    def generate_all_partitions_call_graphs(self,
                                           partitions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        为所有功能分区生成调用图
        
        Args:
            partitions: 功能分区列表
        
        Returns:
            {partition_id: call_graph_dict}
        """
        results = {}
        
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            call_graph = self.generate_partition_call_graph(partition)
            results[partition_id] = call_graph
        
        logger.info(f"[FunctionCallGraphGenerator] ✓ 为 {len(results)} 个分区生成了调用图")
        
        return results
    
    def generate_visualization_data(self,
                                   partition_call_graph: Dict[str, Any],
                                   include_external: bool = True) -> Dict[str, Any]:
        """
        生成可视化数据（用于前端展示）
        
        Args:
            partition_call_graph: 分区调用图（generate_partition_call_graph的返回结果）
            include_external: 是否包含跨分区调用边
        
        Returns:
            可视化数据字典（Cytoscape.js格式）：
            {
                "nodes": List[Dict],
                "edges": List[Dict]
            }
        """
        nodes = partition_call_graph["nodes"]
        edges = []
        
        # 添加内部边
        for edge in partition_call_graph["internal_edges"]:
            edges.append({
                "data": {
                    "id": f"{edge['source']}->{edge['target']}",
                    "source": edge["source"],
                    "target": edge["target"],
                    "label": "calls",
                    "type": "internal"
                }
            })
        
        # 可选：添加外部边
        if include_external:
            for edge in partition_call_graph["external_edges"]:
                edges.append({
                    "data": {
                        "id": f"{edge['source']}->{edge['target']}",
                        "source": edge["source"],
                        "target": edge["target"],
                        "label": "calls",
                        "type": "external"
                    }
                })
        
        # 格式化节点
        formatted_nodes = []
        for node in nodes:
            formatted_nodes.append({
                "data": {
                    "id": node["id"],
                    "label": node["label"],
                    "type": node["type"],
                    "is_internal": node.get("is_internal", False)
                }
            })
        
        return {
            "nodes": formatted_nodes,
            "edges": edges
        }


def main():
    """测试代码"""
    # 创建测试数据
    call_graph = {
        "ClassA.method1": {"ClassA.method2", "ClassB.method3"},
        "ClassA.method2": {"ClassA.method3"},
        "ClassB.method3": {"ClassC.method4"},
        "ClassC.method4": set()
    }
    
    partition = {
        "partition_id": "partition_1",
        "methods": ["ClassA.method1", "ClassA.method2", "ClassB.method3"]
    }
    
    generator = FunctionCallGraphGenerator(call_graph)
    result = generator.generate_partition_call_graph(partition)
    
    print("=" * 60)
    print("函数调用图生成测试")
    print("=" * 60)
    print(f"分区ID: {result['partition_id']}")
    print(f"内部边数: {len(result['internal_edges'])}")
    print(f"外部边数: {len(result['external_edges'])}")
    print(f"节点数: {len(result['nodes'])}")
    print("\n内部边:")
    for edge in result['internal_edges']:
        print(f"  {edge['source']} -> {edge['target']}")
    print("\n外部边:")
    for edge in result['external_edges']:
        print(f"  {edge['source']} -> {edge['target']}")


if __name__ == "__main__":
    main()
























































