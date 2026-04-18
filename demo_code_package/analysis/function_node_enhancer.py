"""
功能节点增强器 - 在功能分区内进行叶子节点的路径追踪
"""


class FunctionNodeEnhancer:
    """功能节点增强器类"""
    
    def __init__(self):
        """初始化增强器"""
        self.hypergraph = None
        self.call_graph = {}
    
    def identify_leaf_nodes(self, partition_methods):
        """
        识别分区内的叶子节点
        
        Args:
            partition_methods: 分区方法集合
            
        Returns:
            叶子节点列表
        """
        leaf_nodes = []
        for node_id in partition_methods:
            if node_id not in self.call_graph or len(self.call_graph[node_id]) == 0:
                leaf_nodes.append(node_id)
            else:
                callees = self.call_graph[node_id]
                callees_in_partition = callees & partition_methods
                if len(callees_in_partition) == 0:
                    leaf_nodes.append(node_id)
        return leaf_nodes
    
    def explore_paths_in_partition(self, leaf_nodes, partition_methods, max_depth=10):
        """
        在分区内从叶子节点探索有向路径
        
        Args:
            leaf_nodes: 叶子节点列表
            partition_methods: 分区方法集合
            max_depth: 最大深度
            
        Returns:
            路径映射字典
        """
        # 调用内部方法
        return self.explore_paths(leaf_nodes, partition_methods, max_depth)
    
    def explore_paths(self, leaf_nodes, partition_methods, max_depth=10):
        """
        在分区内从叶子节点探索有向路径
        
        Args:
            leaf_nodes: 叶子节点列表
            partition_methods: 分区方法集合
            max_depth: 最大深度
            
        Returns:
            路径映射字典
        """
        reverse_call_graph = self._build_reverse_graph(partition_methods)
        paths_map = {}
        
        for leaf_node in leaf_nodes:
            paths = self._backtrack_paths(leaf_node, reverse_call_graph, partition_methods, max_depth)
            paths_map[leaf_node] = paths
        
        return paths_map
    
    def _build_reverse_graph(self, partition_methods):
        """构建反向调用图"""
        reverse_graph = {}
        for caller, callees in self.call_graph.items():
            if caller in partition_methods:
                for callee in callees:
                    if callee in partition_methods:
                        if callee not in reverse_graph:
                            reverse_graph[callee] = set()
                        reverse_graph[callee].add(caller)
        return reverse_graph
    
    def _backtrack_paths(self, leaf_node, reverse_graph, partition_methods, max_depth):
        """回溯查找路径"""
        paths = []
        visited = set()
        
        def backtrack(current, path, depth):
            if depth > max_depth or len(path) > max_depth:
                return
            
            callers = reverse_graph.get(current, set())
            if len(callers) == 0:
                path_tuple = tuple(path)
                if path_tuple not in visited and len(path) >= 2:
                    paths.append(path.copy())
                    visited.add(path_tuple)
            else:
                for caller in callers:
                    if caller not in path:
                        backtrack(caller, [caller] + path, depth + 1)
        
        backtrack(leaf_node, [leaf_node], 0)
        return paths if paths else [[leaf_node]]
    
    def add_function_nodes(self, hypergraph, paths_map):
        """
        添加功能节点到超图
        
        Args:
            hypergraph: 超图对象
            paths_map: 路径映射字典
        """
        for leaf_node, paths in paths_map.items():
            for idx, path in enumerate(paths):
                function_id = f"function_{leaf_node}_{idx}"
                hypergraph.add_node(function_id, {
                    "id": function_id,
                    "label": f"功能路径 {idx + 1}",
                    "type": "function",
                    "function_path": path
                })


def enhance_hypergraph_with_function_nodes(hypergraph, call_graph, partition_methods):
    """
    增强超图：添加基于路径探索的功能节点
    
    Args:
        hypergraph: 超图对象
        call_graph: 调用图
        partition_methods: 分区方法集合
        
    Returns:
        增强后的超图
    """
    enhancer = FunctionNodeEnhancer()
    enhancer.hypergraph = hypergraph
    enhancer.call_graph = call_graph
    
    leaf_nodes = enhancer.identify_leaf_nodes(partition_methods)
    paths_map = enhancer.explore_paths(leaf_nodes, partition_methods)
    enhancer.add_function_nodes(hypergraph, paths_map)
    
    return hypergraph

