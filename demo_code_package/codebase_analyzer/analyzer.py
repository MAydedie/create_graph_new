"""
代码分析器 - 分析代码结构和调用关系
"""

from .parser import CodeParser


class CodeAnalyzer:
    """代码分析器类"""
    
    def __init__(self):
        """初始化分析器"""
        self.parsers = []
        self.call_graph = {}
        self.class_hierarchy = {}
    
    def add_parser(self, parser: CodeParser):
        """
        添加解析器
        
        Args:
            parser: 代码解析器实例
        """
        self.parsers.append(parser)
    
    def analyze_project(self, file_paths: list) -> dict:
        """
        分析整个项目
        
        Args:
            file_paths: 文件路径列表
            
        Returns:
            分析结果字典
        """
        results = []
        for file_path in file_paths:
            parser = CodeParser(file_path)
            result = parser.parse_file()
            results.append(result)
        
        self._build_call_graph(results)
        self._build_class_hierarchy(results)
        
        return {
            'files': results,
            'call_graph': self.call_graph,
            'class_hierarchy': self.class_hierarchy
        }
    
    def _build_call_graph(self, results: list):
        """构建调用图"""
        self.call_graph = {}
        for file_result in results:
            for cls in file_result.get('classes', []):
                for method in cls.get('methods', []):
                    callees = self._find_method_calls(method)
                    method_name = self._get_method_signature(cls, method)
                    self.call_graph[method_name] = callees
    
    def _find_method_calls(self, method_node):
        """查找方法调用"""
        callees = []
        if 'body' in method_node:
            for node in method_node.get('body', []):
                if node.get('type') == 'Call':
                    callees.append(node.get('func', {}).get('id', ''))
        return callees
    
    def _get_method_signature(self, cls_node, method_node):
        """获取方法签名"""
        cls_name = cls_node.get('name', '')
        method_name = method_node.get('name', '')
        return f"{cls_name}.{method_name}"
    
    def _build_class_hierarchy(self, results: list):
        """构建类继承关系"""
        self.class_hierarchy = {}
        for file_result in results:
            for cls in file_result.get('classes', []):
                cls_name = cls.get('name', '')
                parent = cls.get('bases', [{}])[0].get('id', '') if cls.get('bases') else None
                if parent:
                    self.class_hierarchy[cls_name] = parent
    
    def get_statistics(self) -> dict:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        total_methods = sum(len(cls.get('methods', [])) for result in 
                           [r for r in [] if hasattr(self, 'parsers')] 
                           for cls in result.get('classes', []))
        return {
            'total_methods': total_methods,
            'total_classes': len(self.class_hierarchy),
            'call_relations': sum(len(callees) for callees in self.call_graph.values())
        }
























