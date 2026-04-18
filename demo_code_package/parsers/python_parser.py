"""
Python解析器 - 解析Python源代码
"""


class PythonParser:
    """Python解析器类"""
    
    def __init__(self, file_path):
        """
        初始化解析器
        
        Args:
            file_path: 文件路径
        """
        self.file_path = file_path
        self.ast_tree = None
    
    def parse(self, source_code):
        """
        解析源代码
        
        Args:
            source_code: 源代码字符串
            
        Returns:
            解析结果
        """
        self.ast_tree = self._build_ast(source_code)
        classes = self.extract_classes()
        functions = self.extract_functions()
        return {
            'classes': classes,
            'functions': functions,
            'imports': self._extract_imports()
        }
    
    def extract_classes(self):
        """
        提取类定义
        
        Returns:
            类列表
        """
        if not self.ast_tree:
            return []
        
        classes = []
        result = self._traverse_for_classes(self.ast_tree)
        classes.extend(result)
        # 调用内部方法处理结果
        self._process_classes(classes)
        return classes
    
    def _process_classes(self, classes):
        """处理类列表"""
        for cls in classes:
            if 'methods' not in cls:
                cls['methods'] = []
    
    def extract_functions(self):
        """
        提取函数定义
        
        Returns:
            函数列表
        """
        if not self.ast_tree:
            return []
        
        functions = []
        result = self._traverse_for_functions(self.ast_tree)
        functions.extend(result)
        return functions
    
    def _build_ast(self, source_code):
        """构建AST树"""
        # 模拟AST构建
        return {
            'type': 'Module',
            'body': [
                {'type': 'ClassDef', 'name': 'ExampleClass'},
                {'type': 'FunctionDef', 'name': 'example_function'}
            ]
        }
    
    def _traverse_for_classes(self, node):
        """遍历AST查找类定义"""
        classes = []
        if node and isinstance(node, dict):
            if node.get('type') == 'ClassDef':
                classes.append(node)
            if 'body' in node:
                for child in node.get('body', []):
                    classes.extend(self._traverse_for_classes(child))
        return classes
    
    def _traverse_for_functions(self, node):
        """遍历AST查找函数定义"""
        functions = []
        if node and isinstance(node, dict):
            if node.get('type') == 'FunctionDef':
                functions.append(node)
            if 'body' in node:
                for child in node.get('body', []):
                    functions.extend(self._traverse_for_functions(child))
        return functions
    
    def _extract_imports(self):
        """提取导入语句"""
        imports = []
        if self.ast_tree and 'body' in self.ast_tree:
            for node in self.ast_tree.get('body', []):
                if node.get('type') in ['Import', 'ImportFrom']:
                    imports.append(node)
        return imports

