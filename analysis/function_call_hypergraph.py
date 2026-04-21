#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
函数调用超图生成器 - 为功能分区生成超图
超图支持超边（一个超边可以连接多个节点），用于表示功能调用模式
"""

from typing import Dict, List, Set, Optional, Any
import logging

logger = logging.getLogger(__name__)


class HyperEdge:
    """超边 - 连接多个节点的边"""
    
    def __init__(self, hyperedge_id: str, nodes: List[str], edge_type: str = "call_pattern"):
        """
        初始化超边
        
        Args:
            hyperedge_id: 超边ID
            nodes: 连接的节点列表
            edge_type: 边类型（call_pattern, data_flow_pattern等）
        """
        self.hyperedge_id = hyperedge_id
        self.nodes = nodes
        self.edge_type = edge_type
        self.metadata: Dict[str, Any] = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.hyperedge_id,
            "nodes": self.nodes,
            "type": self.edge_type,
            "metadata": self.metadata
        }


class FunctionCallHypergraph:
    """函数调用超图"""
    
    def __init__(self, partition_id: str):
        """
        初始化超图
        
        Args:
            partition_id: 功能分区ID
        """
        self.partition_id = partition_id
        self.nodes: Dict[str, Dict[str, Any]] = {}  # node_id -> node_data
        self.hyperedges: List[HyperEdge] = []
        self.call_patterns: Dict[str, List[str]] = {}  # pattern_id -> [method_sigs]
        self.call_graph: Dict[str, Set[str]] = {}  # 保存调用图，用于生成直接调用边
    
    def add_node(self, node_id: str, node_data: Dict[str, Any]):
        """添加节点"""
        self.nodes[node_id] = node_data
    
    def add_hyperedge(self, hyperedge: HyperEdge):
        """添加超边"""
        self.hyperedges.append(hyperedge)
    
    def identify_call_patterns(self, call_graph: Dict[str, Set[str]], 
                               partition_methods: Set[str]) -> Dict[str, List[str]]:
        """
        识别调用模式（超边）
        
        调用模式包括：
        1. 链式调用：A -> B -> C
        2. 扇出调用：A -> B, A -> C, A -> D
        3. 扇入调用：A -> C, B -> C, D -> C
        4. 循环调用：A -> B -> A
        
        Args:
            call_graph: 调用图
            partition_methods: 分区方法集合
            
        Returns:
            调用模式字典 {pattern_id: [method_sigs]}
        """
        patterns = {}
        pattern_counter = 0
        
        # 1. 识别链式调用模式
        chains = self._find_call_chains(call_graph, partition_methods)
        for chain in chains:
            if len(chain) >= 3:  # 至少3个节点的链
                pattern_id = f"chain_{pattern_counter}"
                patterns[pattern_id] = chain
                pattern_counter += 1
        
        # 2. 识别扇出调用模式（一个方法调用多个方法）
        fanouts = self._find_fanout_patterns(call_graph, partition_methods)
        for caller, callees in fanouts.items():
            if len(callees) >= 3:  # 至少调用3个方法
                pattern_id = f"fanout_{pattern_counter}"
                patterns[pattern_id] = [caller] + list(callees)
                pattern_counter += 1
        
        # 3. 识别扇入调用模式（多个方法调用同一个方法）
        fanins = self._find_fanin_patterns(call_graph, partition_methods)
        for callee, callers in fanins.items():
            if len(callers) >= 3:  # 至少被3个方法调用
                pattern_id = f"fanin_{pattern_counter}"
                patterns[pattern_id] = list(callers) + [callee]
                pattern_counter += 1
        
        # 4. 识别循环调用模式
        cycles = self._find_cycles(call_graph, partition_methods)
        for cycle in cycles:
            if len(cycle) >= 2:
                pattern_id = f"cycle_{pattern_counter}"
                patterns[pattern_id] = cycle
                pattern_counter += 1
        
        self.call_patterns = patterns
        return patterns
    
    def _find_call_chains(self, call_graph: Dict[str, Set[str]], 
                         partition_methods: Set[str], 
                         max_depth: int = 5) -> List[List[str]]:
        """查找调用链"""
        chains = []
        visited = set()
        
        def dfs(node: str, path: List[str], depth: int):
            if depth > max_depth or node in path:
                return
            
            if node not in call_graph:
                if len(path) >= 2:
                    chains.append(path + [node])
                return
            
            for callee in call_graph[node]:
                if callee in partition_methods:
                    dfs(callee, path + [node], depth + 1)
                elif len(path) >= 2:
                    chains.append(path + [node])
        
        for method in partition_methods:
            if method not in visited:
                dfs(method, [], 0)
                visited.add(method)
        
        # 去重
        unique_chains = []
        for chain in chains:
            if chain not in unique_chains:
                unique_chains.append(chain)
        
        return unique_chains[:20]  # 限制返回前20个链
    
    def _find_fanout_patterns(self, call_graph: Dict[str, Set[str]], 
                              partition_methods: Set[str]) -> Dict[str, Set[str]]:
        """查找扇出模式"""
        fanouts = {}
        
        for caller in partition_methods:
            if caller in call_graph:
                callees = {c for c in call_graph[caller] if c in partition_methods}
                if len(callees) >= 2:
                    fanouts[caller] = callees
        
        return fanouts
    
    def _find_fanin_patterns(self, call_graph: Dict[str, Set[str]], 
                            partition_methods: Set[str]) -> Dict[str, Set[str]]:
        """查找扇入模式"""
        fanins = {}
        
        # 构建反向调用图
        reverse_graph: Dict[str, Set[str]] = {}
        for caller, callees in call_graph.items():
            for callee in callees:
                if callee in partition_methods and caller in partition_methods:
                    if callee not in reverse_graph:
                        reverse_graph[callee] = set()
                    reverse_graph[callee].add(caller)
        
        for callee, callers in reverse_graph.items():
            if len(callers) >= 2:
                fanins[callee] = callers
        
        return fanins
    
    def _find_cycles(self, call_graph: Dict[str, Set[str]], 
                    partition_methods: Set[str]) -> List[List[str]]:
        """查找循环调用"""
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
    
    def build_hypergraph(self, call_graph: Dict[str, Set[str]], 
                        partition_methods: Set[str]):
        """
        构建超图
        
        Args:
            call_graph: 调用图（完整的调用图，包含整个项目的调用关系）
            partition_methods: 分区方法集合
        """
        # 只保存分区内的调用图，确保不显示跨分区的调用关系
        partition_call_graph = {}
        for caller, callees in call_graph.items():
            if caller in partition_methods:
                # 只保留分区内的被调用者
                partition_callees = {c for c in callees if c in partition_methods}
                if partition_callees:
                    partition_call_graph[caller] = partition_callees
        self.call_graph = partition_call_graph  # ✅ 只保存分区内的调用图
        
        # 添加所有节点
        for method_sig in partition_methods:
            self.add_node(method_sig, {
                "id": method_sig,
                "label": method_sig,
                "type": "method"
            })
        
        # 识别调用模式
        patterns = self.identify_call_patterns(call_graph, partition_methods)
        
        # 为每个模式创建超边
        for pattern_id, method_sigs in patterns.items():
            hyperedge = HyperEdge(
                hyperedge_id=pattern_id,
                nodes=method_sigs,
                edge_type=self._get_pattern_type(pattern_id)
            )
            hyperedge.metadata = {
                "pattern_type": self._get_pattern_type(pattern_id),
                "node_count": len(method_sigs)
            }
            self.add_hyperedge(hyperedge)
        
        logger.info(f"[FunctionCallHypergraph] ✓ 构建完成: {len(self.nodes)}个节点, "
                   f"{len(self.hyperedges)}条超边")
    
    def _get_pattern_type(self, pattern_id: str) -> str:
        """获取模式类型"""
        if pattern_id.startswith("chain_"):
            return "call_chain"
        elif pattern_id.startswith("fanout_"):
            return "fanout"
        elif pattern_id.startswith("fanin_"):
            return "fanin"
        elif pattern_id.startswith("cycle_"):
            return "cycle"
        return "unknown"
    
    def to_visualization_data(self) -> Dict[str, Any]:
        """
        生成可视化数据（Cytoscape.js格式）
        
        注意：超图在标准图可视化库中需要特殊处理
        这里我们将超边转换为多个普通边来表示
        """
        nodes = []
        edges = []
        
        # 先收集所有在调用链中的节点（有边的节点）
        nodes_in_call_chain = set()
        
        # 从超边中收集节点
        for hyperedge in self.hyperedges:
            for node_id in hyperedge.nodes:
                nodes_in_call_chain.add(node_id)
        
        # 从直接调用关系中收集节点
        if self.call_graph:
            for caller, callees in self.call_graph.items():
                nodes_in_call_chain.add(caller)
                nodes_in_call_chain.update(callees)
        
        # 添加节点（只包括方法节点和功能节点）
        # 对于方法节点，只显示在调用链中的节点
        for node_id, node_data in self.nodes.items():
            node_type = node_data.get("type", "method")
            
            # 如果是方法节点且不在调用链中，跳过（不显示）
            if node_type == "method" and node_id not in nodes_in_call_chain:
                continue
            
            node_info = {
                "data": {
                    "id": node_id,
                    "label": node_data.get("label", node_id),
                    "type": node_type
                }
            }
            
            # 如果是功能节点，添加额外属性
            if node_type == "function":
                node_info["data"].update({
                    "function_path": node_data.get("function_path", []),
                    "start_leaf_node": node_data.get("start_leaf_node", ""),
                    "path_length": node_data.get("path_length", 0),
                    "metadata": node_data.get("metadata", {})
                })
            
            nodes.append(node_info)
        
        # 将超边转换为普通边（每个超边内的节点两两连接）
        for hyperedge in self.hyperedges:
            hyperedge_nodes = hyperedge.nodes
            pattern_type = hyperedge.edge_type
            
            # 根据模式类型生成不同的边
            if pattern_type == "call_chain":
                # 链式调用：A -> B -> C
                for i in range(len(hyperedge_nodes) - 1):
                    edges.append({
                        "data": {
                            "id": f"{hyperedge.hyperedge_id}_edge_{i}",
                            "source": hyperedge_nodes[i],
                            "target": hyperedge_nodes[i + 1],
                            "label": "chain",
                            "type": "hyperedge",
                            "hyperedge_id": hyperedge.hyperedge_id,
                            "pattern_type": pattern_type
                        }
                    })
            elif pattern_type == "fanout":
                # 扇出：A -> B, A -> C, A -> D
                caller = hyperedge_nodes[0]
                for callee in hyperedge_nodes[1:]:
                    edges.append({
                        "data": {
                            "id": f"{hyperedge.hyperedge_id}_edge_{callee}",
                            "source": caller,
                            "target": callee,
                            "label": "fanout",
                            "type": "hyperedge",
                            "hyperedge_id": hyperedge.hyperedge_id,
                            "pattern_type": pattern_type
                        }
                    })
            elif pattern_type == "fanin":
                # 扇入：A -> C, B -> C, D -> C
                callee = hyperedge_nodes[-1]
                for caller in hyperedge_nodes[:-1]:
                    edges.append({
                        "data": {
                            "id": f"{hyperedge.hyperedge_id}_edge_{caller}",
                            "source": caller,
                            "target": callee,
                            "label": "fanin",
                            "type": "hyperedge",
                            "hyperedge_id": hyperedge.hyperedge_id,
                            "pattern_type": pattern_type
                        }
                    })
            elif pattern_type == "cycle":
                # 循环：A -> B -> A
                for i in range(len(hyperedge_nodes)):
                    next_idx = (i + 1) % len(hyperedge_nodes)
                    edges.append({
                        "data": {
                            "id": f"{hyperedge.hyperedge_id}_edge_{i}",
                            "source": hyperedge_nodes[i],
                            "target": hyperedge_nodes[next_idx],
                            "label": "cycle",
                            "type": "hyperedge",
                            "hyperedge_id": hyperedge.hyperedge_id,
                            "pattern_type": pattern_type
                        }
                    })
            elif pattern_type == "function_implements":
                # 功能实现边：功能节点 -> 路径上的方法节点
                function_node = hyperedge_nodes[0]  # 第一个节点是功能节点
                implemented_methods = hyperedge_nodes[1:]  # 其余节点是实现方法
                for method in implemented_methods:
                    edges.append({
                        "data": {
                            "id": f"{hyperedge.hyperedge_id}_edge_{method}",
                            "source": function_node,
                            "target": method,
                            "label": "implements",
                            "type": "function_implements",
                            "hyperedge_id": hyperedge.hyperedge_id,
                            "pattern_type": pattern_type
                        }
                    })
        
        # 添加所有直接的调用关系边（从call_graph中）
        # 这样可以确保所有调用关系都能在超图中显示，而不仅仅是模式匹配的边
        direct_edges_added = set()  # 避免重复添加边
        if self.call_graph:
            for caller, callees in self.call_graph.items():
                # 只处理分区内的方法
                if caller in self.nodes:
                    for callee in callees:
                        if callee in self.nodes:
                            # 创建边的唯一标识符
                            edge_id = f"direct_call_{caller}_{callee}"
                            if edge_id not in direct_edges_added:
                                # 检查是否已经通过超边添加了这条边
                                edge_exists = False
                                for existing_edge in edges:
                                    if (existing_edge["data"]["source"] == caller and 
                                        existing_edge["data"]["target"] == callee):
                                        edge_exists = True
                                        break
                                
                                if not edge_exists:
                                    edges.append({
                                        "data": {
                                            "id": edge_id,
                                            "source": caller,
                                            "target": callee,
                                            "label": "call",
                                            "type": "direct_call",
                                            "pattern_type": "direct"
                                        }
                                    })
                                    direct_edges_added.add(edge_id)
        
        logger.info(f"[FunctionCallHypergraph] ✓ 可视化数据生成完成: {len(nodes)}个节点, "
                   f"{len(edges)}条边（其中{len(direct_edges_added)}条直接调用边）")
        
        # 统计功能节点数量
        function_node_count = len([n for n in self.nodes.values() if n.get('type') == 'function'])
        
        return {
            "nodes": nodes,
            "edges": edges,
            "hyperedges": [he.to_dict() for he in self.hyperedges],
            "statistics": {
                "total_nodes": len(nodes),
                "method_nodes": len([n for n in self.nodes.values() if n.get('type') == 'method']),
                "function_nodes": function_node_count,
                "total_hyperedges": len(self.hyperedges),
                "total_edges": len(edges),
                "direct_call_edges": len(direct_edges_added),
                "pattern_counts": {
                    "chains": len([he for he in self.hyperedges if he.edge_type == "call_chain"]),
                    "fanouts": len([he for he in self.hyperedges if he.edge_type == "fanout"]),
                    "fanins": len([he for he in self.hyperedges if he.edge_type == "fanin"]),
                    "cycles": len([he for he in self.hyperedges if he.edge_type == "cycle"]),
                    "function_implements": len([he for he in self.hyperedges if he.edge_type == "function_implements"])
                }
            }
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "partition_id": self.partition_id,
            "nodes": self.nodes,
            "hyperedges": [he.to_dict() for he in self.hyperedges],
            "call_patterns": self.call_patterns
        }


class FunctionCallHypergraphGenerator:
    """函数调用超图生成器"""
    
    def __init__(self, call_graph: Dict[str, Set[str]]):
        """
        初始化生成器
        
        Args:
            call_graph: 完整的调用图 {caller: Set[callees]}
        """
        self.call_graph = call_graph
    
    def generate_partition_hypergraph(self, 
                                     partition: Dict[str, Any]) -> FunctionCallHypergraph:
        """
        为功能分区生成超图
        
        Args:
            partition: 功能分区字典，包含：
                - partition_id: 分区ID
                - methods: 方法签名列表
        
        Returns:
            FunctionCallHypergraph对象
        """
        partition_id = partition.get("partition_id", "unknown")
        partition_methods = set(partition.get("methods", []))
        
        logger.info(f"[FunctionCallHypergraphGenerator] 生成分区 {partition_id} 的超图，方法数: {len(partition_methods)}")
        
        # 创建超图
        hypergraph = FunctionCallHypergraph(partition_id)
        hypergraph.build_hypergraph(self.call_graph, partition_methods)
        
        return hypergraph
    
    def generate_all_partitions_hypergraphs(self,
                                           partitions: List[Dict[str, Any]]) -> Dict[str, FunctionCallHypergraph]:
        """
        为所有功能分区生成超图
        
        Args:
            partitions: 功能分区列表
        
        Returns:
            {partition_id: hypergraph}
        """
        results = {}
        
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            hypergraph = self.generate_partition_hypergraph(partition)
            results[partition_id] = hypergraph
        
        logger.info(f"[FunctionCallHypergraphGenerator] ✓ 为 {len(results)} 个分区生成了超图")
        
        return results


def main():
    """测试代码"""
    # 创建测试数据
    call_graph = {
        "ClassA.method1": {"ClassA.method2", "ClassB.method3"},
        "ClassA.method2": {"ClassA.method3"},
        "ClassA.method3": {"ClassA.method1"},  # 循环
        "ClassB.method3": {"ClassC.method4", "ClassC.method5", "ClassC.method6"},  # 扇出
        "ClassC.method4": set(),
        "ClassC.method5": set(),
        "ClassC.method6": set(),
        "ClassD.method7": {"ClassC.method4"},  # 扇入
        "ClassE.method8": {"ClassC.method4"},  # 扇入
    }
    
    partition = {
        "partition_id": "partition_1",
        "methods": ["ClassA.method1", "ClassA.method2", "ClassA.method3", 
                   "ClassB.method3", "ClassC.method4", "ClassC.method5", "ClassC.method6",
                   "ClassD.method7", "ClassE.method8"]
    }
    
    generator = FunctionCallHypergraphGenerator(call_graph)
    hypergraph = generator.generate_partition_hypergraph(partition)
    
    print("=" * 60)
    print("函数调用超图生成测试")
    print("=" * 60)
    print(f"分区ID: {hypergraph.partition_id}")
    print(f"节点数: {len(hypergraph.nodes)}")
    print(f"超边数: {len(hypergraph.hyperedges)}")
    print(f"调用模式数: {len(hypergraph.call_patterns)}")
    print("\n调用模式:")
    for pattern_id, methods in hypergraph.call_patterns.items():
        print(f"  {pattern_id}: {methods}")
    
    viz_data = hypergraph.to_visualization_data()
    print(f"\n可视化数据:")
    print(f"  节点数: {len(viz_data['nodes'])}")
    print(f"  边数: {len(viz_data['edges'])}")
    print(f"  统计: {viz_data['statistics']}")


if __name__ == "__main__":
    main()





















