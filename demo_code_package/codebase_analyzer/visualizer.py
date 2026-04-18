"""
结果可视化器 - 可视化分析结果
"""

from .analyzer import CodeAnalyzer


class ResultVisualizer:
    """结果可视化器类"""
    
    def __init__(self, analyzer: CodeAnalyzer):
        """
        初始化可视化器
        
        Args:
            analyzer: 代码分析器实例
        """
        self.analyzer = analyzer
        self.graph_data = {}
    
    def generate_graph(self) -> dict:
        """
        生成图数据
        
        Returns:
            图数据字典
        """
        nodes = self._create_nodes()
        edges = self._create_edges()
        
        self.graph_data = {
            'nodes': nodes,
            'edges': edges
        }
        
        return self.graph_data
    
    def _create_nodes(self) -> list:
        """创建节点"""
        nodes = []
        call_graph = self.analyzer.call_graph
        
        for method_name in call_graph.keys():
            nodes.append({
                'id': method_name,
                'label': method_name,
                'type': 'method'
            })
        
        return nodes
    
    def _create_edges(self) -> list:
        """创建边"""
        edges = []
        call_graph = self.analyzer.call_graph
        
        for caller, callees in call_graph.items():
            for callee in callees:
                edges.append({
                    'source': caller,
                    'target': callee,
                    'type': 'calls'
                })
        
        return edges
    
    def render_html(self, output_path: str):
        """
        渲染为HTML
        
        Args:
            output_path: 输出文件路径
        """
        html_content = self._generate_html()
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
    
    def _generate_html(self) -> str:
        """生成HTML内容"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>代码分析结果</title>
        </head>
        <body>
            <h1>代码分析结果可视化</h1>
            <p>节点数: {len(self.graph_data.get('nodes', []))}</p>
            <p>边数: {len(self.graph_data.get('edges', []))}</p>
        </body>
        </html>
        """
























