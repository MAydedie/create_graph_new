#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
社区检测器 - 基于调用图进行功能分区识别
使用Louvain/Leiden等社区检测算法
"""

import networkx as nx
from typing import Dict, Set, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

# 尝试导入社区检测库
try:
    import community.community_louvain as community_louvain
    LOUVAIN_AVAILABLE = True
except ImportError:
    LOUVAIN_AVAILABLE = False
    logger.warning("python-louvain 未安装，将使用 networkx 内置算法")

try:
    import leidenalg
    LEIDEN_AVAILABLE = True
except ImportError:
    LEIDEN_AVAILABLE = False
    logger.warning("leidenalg 未安装，将使用 Louvain 算法")


class CommunityDetector:
    """社区检测器 - 用于功能分区识别"""
    
    def __init__(self):
        self.graph = None
        self.partitions = []
    
    def detect_communities(self, 
                          call_graph: Dict[str, Set[str]], 
                          algorithm: str = "louvain",
                          weight_threshold: float = 0.0) -> List[Dict[str, Any]]:
        """
        检测社区（功能分区）
        
        Args:
            call_graph: 调用图 {caller: Set[callees]}
            algorithm: 算法名称 ("louvain", "leiden", "greedy_modularity", "label_propagation")
            weight_threshold: 边权重阈值，低于此值的边将被忽略
        
        Returns:
            分区列表，每个分区包含方法列表和模块度
        """
        logger.info(f"[CommunityDetector] 开始社区检测，算法: {algorithm}")
        logger.info(f"[CommunityDetector] 调用图大小: {len(call_graph)} 个方法")
        
        # 构建NetworkX图
        self.graph = self._build_graph(call_graph, weight_threshold)
        
        if self.graph.number_of_nodes() == 0:
            logger.warning("[CommunityDetector] 图为空，无法进行社区检测")
            return []
        
        # 选择算法
        communities = self._run_algorithm(algorithm)
        
        # 计算每个社区的模块度
        partitions = []
        for i, comm in enumerate(communities):
            partition = {
                "partition_id": f"partition_{i}",
                "methods": list(comm),
                "modularity": self._calculate_modularity(comm),
                "internal_calls": self._count_internal_calls(comm),
                "external_calls": self._count_external_calls(comm),
                "size": len(comm)
            }
            partitions.append(partition)
        
        # 按模块度排序
        partitions.sort(key=lambda x: x["modularity"], reverse=True)
        
        self.partitions = partitions
        
        logger.info(f"[CommunityDetector] ✓ 检测完成，发现 {len(partitions)} 个分区")
        logger.info(f"[CommunityDetector]   平均模块度: {sum(p['modularity'] for p in partitions) / len(partitions) if partitions else 0:.3f}")
        
        return partitions
    
    def _build_graph(self, call_graph: Dict[str, Set[str]], 
                    weight_threshold: float = 0.0) -> nx.DiGraph:
        """构建NetworkX图"""
        G = nx.DiGraph()
        
        total_edges = 0
        for caller, callees in call_graph.items():
            for callee in callees:
                # 计算边权重
                weight = self._calculate_edge_weight(caller, callee, call_graph)
                
                if weight >= weight_threshold:
                    # 如果边已存在，累加权重
                    if G.has_edge(caller, callee):
                        G[caller][callee]['weight'] += weight
                    else:
                        G.add_edge(caller, callee, weight=weight)
                    total_edges += 1
        
        logger.info(f"[CommunityDetector] 构建图完成: {G.number_of_nodes()} 个节点, {total_edges} 条边")
        return G
    
    def _calculate_edge_weight(self, caller: str, callee: str, 
                              call_graph: Dict[str, Set[str]]) -> float:
        """
        计算边权重
        
        权重公式：
        weight = base_count + depth_bonus + uniqueness_bonus
        
        - base_count: 基础调用次数（这里简化为1，实际可以从调用图统计）
        - depth_bonus: 调用深度奖励
        - uniqueness_bonus: 唯一性奖励（如果A只调用B，B只被A调用）
        """
        base_count = 1.0
        
        # 深度奖励：如果callee又调用了其他方法，说明调用链较长
        depth_bonus = 0.0
        if callee in call_graph and len(call_graph[callee]) > 0:
            depth_bonus = 0.2 * min(len(call_graph[callee]), 5)  # 最多奖励1.0
        
        # 唯一性奖励：如果caller只调用callee，或callee只被caller调用
        uniqueness_bonus = 0.0
        caller_out_degree = len(call_graph.get(caller, set()))
        callee_in_degree = sum(1 for c, callees in call_graph.items() 
                              if callee in callees)
        
        if caller_out_degree == 1:
            uniqueness_bonus += 0.3  # caller只调用callee
        if callee_in_degree == 1:
            uniqueness_bonus += 0.3  # callee只被caller调用
        
        weight = base_count + depth_bonus + uniqueness_bonus
        return weight
    
    def _run_algorithm(self, algorithm: str) -> List[Set[str]]:
        """运行社区检测算法"""
        # 转换为无向图（大多数社区检测算法需要无向图）
        G_undirected = self.graph.to_undirected()
        
        if algorithm == "louvain":
            return self._louvain_algorithm(G_undirected)
        elif algorithm == "leiden":
            return self._leiden_algorithm(G_undirected)
        elif algorithm == "greedy_modularity":
            return self._greedy_modularity_algorithm(G_undirected)
        elif algorithm == "label_propagation":
            return self._label_propagation_algorithm(G_undirected)
        else:
            logger.warning(f"未知算法 {algorithm}，使用 louvain")
            return self._louvain_algorithm(G_undirected)
    
    def _louvain_algorithm(self, G: nx.Graph) -> List[Set[str]]:
        """Louvain算法"""
        if LOUVAIN_AVAILABLE:
            partition = community_louvain.best_partition(G, weight='weight')
            # 转换为社区列表
            communities = {}
            for node, comm_id in partition.items():
                if comm_id not in communities:
                    communities[comm_id] = set()
                communities[comm_id].add(node)
            return list(communities.values())
        else:
            # 使用networkx内置的greedy_modularity作为后备
            logger.warning("python-louvain 未安装，使用 greedy_modularity")
            return self._greedy_modularity_algorithm(G)
    
    def _leiden_algorithm(self, G: nx.Graph) -> List[Set[str]]:
        """Leiden算法"""
        if LEIDEN_AVAILABLE:
            # 转换为igraph格式
            import igraph as ig
            edges = [(u, v) for u, v in G.edges()]
            weights = [G[u][v].get('weight', 1.0) for u, v in edges]
            
            g_ig = ig.Graph(edges, directed=False)
            g_ig.es['weight'] = weights
            
            partition = leidenalg.find_partition(g_ig, leidenalg.ModularityVertexPartition)
            
            # 转换为社区列表
            communities = []
            for comm in partition:
                communities.append(set(G.nodes()[i] for i in comm))
            return communities
        else:
            logger.warning("leidenalg 未安装，使用 louvain")
            return self._louvain_algorithm(G)
    
    def _greedy_modularity_algorithm(self, G: nx.Graph) -> List[Set[str]]:
        """Greedy Modularity算法（networkx内置）"""
        from networkx.algorithms import community
        communities_generator = community.greedy_modularity_communities(
            G, weight='weight'
        )
        return [set(comm) for comm in communities_generator]
    
    def _label_propagation_algorithm(self, G: nx.Graph) -> List[Set[str]]:
        """Label Propagation算法（networkx内置）"""
        from networkx.algorithms import community
        communities_generator = community.label_propagation_communities(G)
        return [set(comm) for comm in communities_generator]
    
    def _calculate_modularity(self, community: Set[str]) -> float:
        """计算社区的模块度"""
        if not self.graph or len(community) == 0:
            return 0.0

        # 使用稳定的近似模块度，避免 networkx modularity 对不完整分区报错
        internal = self._count_internal_calls(community)
        total = internal + self._count_external_calls(community)
        return internal / total if total > 0 else 0.0
    
    def _count_internal_calls(self, community: Set[str]) -> int:
        """统计社区内部调用数"""
        if not self.graph:
            return 0
        
        count = 0
        for caller in community:
            if caller in self.graph:
                for callee in self.graph.successors(caller):
                    if callee in community:
                        count += 1
        return count
    
    def _count_external_calls(self, community: Set[str]) -> int:
        """统计跨社区调用数"""
        if not self.graph:
            return 0
        
        count = 0
        for caller in community:
            if caller in self.graph:
                for callee in self.graph.successors(caller):
                    if callee not in community:
                        count += 1
        return count
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取检测统计信息"""
        if not self.partitions:
            return {}
        
        total_methods = sum(p['size'] for p in self.partitions)
        avg_modularity = sum(p['modularity'] for p in self.partitions) / len(self.partitions)
        
        return {
            "total_partitions": len(self.partitions),
            "total_methods": total_methods,
            "avg_modularity": avg_modularity,
            "max_modularity": max(p['modularity'] for p in self.partitions),
            "min_modularity": min(p['modularity'] for p in self.partitions),
            "avg_size": total_methods / len(self.partitions) if self.partitions else 0
        }


























































