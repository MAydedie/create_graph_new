"""
增强的可视化器 - 支持多种视图
"""


class EnhancedVisualizer:
    """增强的可视化器类"""
    
    def __init__(self):
        """初始化可视化器"""
        self.graph_data = {}
        self.renderer = None
    
    def render(self, graph_data):
        """
        渲染图数据
        
        Args:
            graph_data: 图数据字典
            
        Returns:
            渲染结果
        """
        self.graph_data = graph_data
        nodes = self._create_nodes()
        edges = self._create_edges()
        stats = self._calculate_statistics(nodes, edges)
        
        return {
            'nodes': nodes,
            'edges': edges,
            'statistics': stats
        }
    
    def generate_graph(self, call_graph):
        """
        生成图数据
        
        Args:
            call_graph: 调用图
            
        Returns:
            图数据字典
        """
        nodes = []
        edges = []
        
        for caller, callees in call_graph.items():
            nodes.append({
                'id': caller,
                'label': caller.split('.')[-1],
                'type': 'method'
            })
            
            for callee in callees:
                edges.append({
                    'source': caller,
                    'target': callee,
                    'type': 'calls'
                })
        
        return {
            'nodes': nodes,
            'edges': edges
        }
    
    def _create_nodes(self):
        """创建节点"""
        nodes = []
        if 'call_graph' in self.graph_data:
            call_graph = self.graph_data['call_graph']
            for method_name in call_graph.keys():
                nodes.append({
                    'id': method_name,
                    'label': method_name.split('.')[-1],
                    'type': 'method'
                })
        return nodes
    
    def _create_edges(self):
        """创建边"""
        edges = []
        if 'call_graph' in self.graph_data:
            call_graph = self.graph_data['call_graph']
            for caller, callees in call_graph.items():
                for callee in callees:
                    edges.append({
                        'source': caller,
                        'target': callee,
                        'type': 'calls'
                    })
        return edges
    
    def _calculate_statistics(self, nodes, edges):
        """计算统计信息"""
        return {
            'total_nodes': len(nodes),
            'total_edges': len(edges),
            'average_degree': len(edges) / len(nodes) if nodes else 0
        }

