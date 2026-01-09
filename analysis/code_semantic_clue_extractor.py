#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
代码语义线索提取器 - 从代码中提取语义线索
用于功能分区识别的代码语义分析
包括：装饰器、继承、导入、注释、异常、依赖注入等模式
"""

import ast
import re
from typing import Dict, List, Set, Optional, Any
import logging

from analysis.code_model import MethodInfo, ClassInfo, SourceLocation

logger = logging.getLogger(__name__)


class CodeSemanticClueExtractor:
    """代码语义线索提取器"""
    
    def __init__(self):
        """初始化提取器"""
        pass
    
    def extract_clues(self, 
                     method_info: Optional[MethodInfo] = None,
                     class_info: Optional[ClassInfo] = None,
                     file_content: Optional[str] = None) -> Dict[str, Any]:
        """
        从代码中提取语义线索
        
        Args:
            method_info: 方法信息（可选）
            class_info: 类信息（可选）
            file_content: 文件完整内容（可选，用于提取导入语句）
        
        Returns:
            包含语义线索的字典：
            {
                "decorators": List[str],              # 装饰器列表
                "inheritance": List[str],             # 继承关系列表
                "imports": List[str],                 # 导入语句列表
                "docstring": str,                     # docstring
                "comments": List[str],                # 功能性注释
                "exceptions": List[str],              # 异常类型列表
                "dependencies": List[str],            # 依赖列表（参数类型、返回值类型等）
                "annotations": Dict[str, str],        # 类型注解 {"param_name": "type", "return": "type"}
                "class_modifiers": List[str],         # 类修饰符（如果有class_info）
                "method_modifiers": List[str],        # 方法修饰符
            }
        """
        clues = {
            "decorators": [],
            "inheritance": [],
            "imports": [],
            "docstring": "",
            "comments": [],
            "exceptions": [],
            "dependencies": [],
            "annotations": {},
            "class_modifiers": [],
            "method_modifiers": [],
        }
        
        # 1. 提取装饰器（从方法源代码）
        if method_info and method_info.source_code:
            clues["decorators"] = self._extract_decorators(method_info.source_code)
            clues["method_modifiers"] = method_info.modifiers
        
        # 2. 提取继承关系（从类信息）
        if class_info:
            if class_info.parent_class:
                clues["inheritance"].append(class_info.parent_class)
            clues["inheritance"].extend(class_info.interfaces)
            clues["class_modifiers"] = class_info.modifiers
        
        # 3. 提取导入语句（从文件内容）
        if file_content:
            clues["imports"] = self._extract_imports(file_content)
        
        # 4. 提取docstring（从方法信息）
        if method_info and method_info.docstring:
            clues["docstring"] = method_info.docstring
        
        # 5. 提取功能性注释（从方法源代码）
        if method_info and method_info.source_code:
            clues["comments"] = self._extract_functional_comments(method_info.source_code)
        
        # 6. 提取异常类型（从方法源代码）
        if method_info and method_info.source_code:
            clues["exceptions"] = self._extract_exception_types(method_info.source_code)
        
        # 7. 提取依赖（参数类型、返回值类型等）
        if method_info:
            clues["dependencies"] = self._extract_dependencies(method_info, class_info)
        
        # 8. 提取类型注解（从方法源代码）
        if method_info and method_info.source_code:
            clues["annotations"] = self._extract_type_annotations(method_info.source_code)
        
        return clues
    
    def _extract_decorators(self, source_code: str) -> List[str]:
        """
        提取装饰器
        
        Examples:
            @app.route('/api/parse') -> ["app.route"]
            @cache -> ["cache"]
            @require_auth -> ["require_auth"]
        """
        decorators = []
        
        try:
            tree = ast.parse(source_code)
            if not tree.body:
                return decorators
            
            # 查找函数定义
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    for decorator in node.decorator_list:
                        decorator_str = self._decorator_to_string(decorator)
                        if decorator_str:
                            decorators.append(decorator_str)
                    break  # 只处理第一个函数定义
        except SyntaxError as e:
            logger.debug(f"AST解析失败，使用正则表达式: {e}")
            # 使用正则表达式作为后备
            decorators = self._extract_decorators_regex(source_code)
        except Exception as e:
            logger.warning(f"提取装饰器失败: {e}")
            decorators = self._extract_decorators_regex(source_code)
        
        return decorators
    
    def _decorator_to_string(self, decorator_node: ast.expr) -> str:
        """将AST装饰器节点转换为字符串"""
        if isinstance(decorator_node, ast.Name):
            return decorator_node.id
        elif isinstance(decorator_node, ast.Attribute):
            # 处理 app.route 这种情况
            attr_parts = []
            node = decorator_node
            while isinstance(node, ast.Attribute):
                attr_parts.insert(0, node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                attr_parts.insert(0, node.id)
            return '.'.join(attr_parts)
        elif isinstance(decorator_node, ast.Call):
            # 处理 @app.route('/path') 这种情况
            if isinstance(decorator_node.func, ast.Name):
                return decorator_node.func.id
            elif isinstance(decorator_node.func, ast.Attribute):
                return self._decorator_to_string(decorator_node.func)
        return ""
    
    def _extract_decorators_regex(self, source_code: str) -> List[str]:
        """使用正则表达式提取装饰器（后备方法）"""
        decorators = []
        lines = source_code.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('@'):
                # 提取 @ 后面的内容（直到第一个括号或换行）
                decorator_match = re.match(r'@(\w+(?:\.\w+)*)', line)
                if decorator_match:
                    decorators.append(decorator_match.group(1))
        
        return decorators
    
    def _extract_inheritance(self, class_info: ClassInfo) -> List[str]:
        """提取继承关系（已在上层方法中处理，这里保留作为独立方法）"""
        inheritance = []
        if class_info.parent_class:
            inheritance.append(class_info.parent_class)
        inheritance.extend(class_info.interfaces)
        return inheritance
    
    def _extract_imports(self, file_content: str) -> List[str]:
        """
        提取导入语句
        
        Examples:
            import os -> ["import os"]
            from analysis import Analyzer -> ["from analysis import Analyzer"]
            from .utils import helper -> ["from .utils import helper"]
        """
        imports = []
        
        try:
            tree = ast.parse(file_content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(f"import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imported_names = [alias.name for alias in node.names]
                    if imported_names:
                        imports.append(f"from {module} import {', '.join(imported_names)}")
        except SyntaxError:
            # 使用正则表达式作为后备
            imports = self._extract_imports_regex(file_content)
        except Exception as e:
            logger.warning(f"提取导入语句失败: {e}")
            imports = self._extract_imports_regex(file_content)
        
        return imports
    
    def _extract_imports_regex(self, file_content: str) -> List[str]:
        """使用正则表达式提取导入语句（后备方法）"""
        imports = []
        lines = file_content.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('import '):
                imports.append(line)
            elif line.startswith('from '):
                # 提取到 import 关键字
                import_match = re.match(r'(from\s+\S+\s+import\s+.+)', line)
                if import_match:
                    imports.append(import_match.group(1))
        
        return imports
    
    def _extract_functional_comments(self, source_code: str) -> List[str]:
        """
        提取功能性注释（过滤掉TODO、FIXME等非功能性注释）
        
        Examples:
            # API endpoint -> "API endpoint"
            # 解析Python代码 -> "解析Python代码"
        """
        comments = []
        lines = source_code.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('#'):
                comment = line[1:].strip()
                # 过滤掉TODO、FIXME等非功能性注释
                if not any(marker in comment.upper() 
                          for marker in ['TODO', 'FIXME', 'XXX', 'HACK', 'NOTE:', 'NOTE']):
                    if comment:  # 非空注释
                        comments.append(comment)
        
        return comments
    
    def _extract_exception_types(self, source_code: str) -> List[str]:
        """
        提取异常类型
        
        Examples:
            raise ParseError(...) -> ["ParseError"]
            except ValidationError: -> ["ValidationError"]
        """
        exceptions = []
        
        try:
            tree = ast.parse(source_code)
            for node in ast.walk(tree):
                # 提取 raise 语句
                if isinstance(node, ast.Raise):
                    if node.exc:
                        exc_name = self._exception_to_string(node.exc)
                        if exc_name:
                            exceptions.append(exc_name)
                
                # 提取 except 子句
                if isinstance(node, ast.ExceptHandler):
                    if node.type:
                        exc_name = self._exception_to_string(node.type)
                        if exc_name:
                            exceptions.append(exc_name)
        except SyntaxError:
            # 使用正则表达式作为后备
            exceptions = self._extract_exceptions_regex(source_code)
        except Exception as e:
            logger.warning(f"提取异常类型失败: {e}")
            exceptions = self._extract_exceptions_regex(source_code)
        
        # 去重
        return list(set(exceptions))
    
    def _exception_to_string(self, exc_node: ast.expr) -> str:
        """将AST异常节点转换为字符串"""
        if isinstance(exc_node, ast.Name):
            return exc_node.id
        elif isinstance(exc_node, ast.Call):
            if isinstance(exc_node.func, ast.Name):
                return exc_node.func.id
            elif isinstance(exc_node.func, ast.Attribute):
                return exc_node.func.attr
        elif isinstance(exc_node, ast.Attribute):
            return exc_node.attr
        return ""
    
    def _extract_exceptions_regex(self, source_code: str) -> List[str]:
        """使用正则表达式提取异常类型（后备方法）"""
        exceptions = []
        
        # 提取 raise 语句
        raise_pattern = r'raise\s+(\w+)\s*\('
        for match in re.finditer(raise_pattern, source_code):
            exceptions.append(match.group(1))
        
        # 提取 except 子句
        except_pattern = r'except\s+(\w+)'
        for match in re.finditer(except_pattern, source_code):
            exceptions.append(match.group(1))
        
        return list(set(exceptions))
    
    def _extract_dependencies(self, method_info: MethodInfo, 
                             class_info: Optional[ClassInfo] = None) -> List[str]:
        """
        提取依赖（参数类型、返回值类型等）
        
        Args:
            method_info: 方法信息
            class_info: 类信息（可选）
        
        Returns:
            依赖类型列表
        """
        dependencies = []
        
        # 从参数类型提取
        for param in method_info.parameters:
            if param.param_type:
                dependencies.append(param.param_type)
        
        # 从返回值类型提取
        if method_info.return_type:
            dependencies.append(method_info.return_type)
        
        # 从类依赖提取（如果有类信息）
        if class_info:
            dependencies.extend(class_info.dependencies)
        
        # 去重
        return list(set(dependencies))
    
    def _extract_type_annotations(self, source_code: str) -> Dict[str, str]:
        """
        提取类型注解
        
        Returns:
            {"param_name": "type", "return": "type"}
        """
        annotations = {}
        
        try:
            tree = ast.parse(source_code)
            if not tree.body:
                return annotations
            
            # 查找函数定义
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    func = node
                    # 提取参数类型注解
                    for arg in func.args.args:
                        if arg.annotation:
                            try:
                                # 尝试使用 ast.unparse（Python 3.9+）
                                type_str = ast.unparse(arg.annotation)
                            except AttributeError:
                                # 回退到手动转换
                                type_str = self._annotation_to_string(arg.annotation)
                            annotations[arg.arg] = type_str
                    
                    # 提取返回值类型注解
                    if func.returns:
                        try:
                            return_type_str = ast.unparse(func.returns)
                        except AttributeError:
                            return_type_str = self._annotation_to_string(func.returns)
                        annotations['return'] = return_type_str
                    break  # 只处理第一个函数定义
        except SyntaxError:
            pass
        except Exception as e:
            logger.debug(f"提取类型注解失败: {e}")
        
        return annotations
    
    def _annotation_to_string(self, annotation_node: ast.expr) -> str:
        """将AST类型注解节点转换为字符串（简化版本）"""
        if isinstance(annotation_node, ast.Name):
            return annotation_node.id
        elif isinstance(annotation_node, ast.Constant):
            return str(annotation_node.value)
        elif isinstance(annotation_node, ast.Subscript):
            # 处理 List[str], Dict[str, int] 等情况
            if isinstance(annotation_node.value, ast.Name):
                base = annotation_node.value.id
                # 简化处理，不递归解析
                return base
        return ""


def main():
    """测试代码"""
    from analysis.code_model import MethodInfo, ClassInfo, Parameter
    
    extractor = CodeSemanticClueExtractor()
    
    # 测试用例：创建一个示例方法信息
    method_code = """
    @app.route('/api/parse')
    @cache
    def parse_code(self, code: str, language: str = 'python') -> dict:
        \"\"\"解析代码\"\"\"
        # API endpoint for code parsing
        try:
            result = parse(code)
        except ParseError as e:
            raise ValidationError(f"Parse failed: {e}")
        return result
    """
    
    method_info = MethodInfo(
        name="parse_code",
        class_name="CodeParser",
        signature="CodeParser.parse_code(code: str, language: str = 'python') -> dict",
        return_type="dict",
        parameters=[
            Parameter(name="code", param_type="str"),
            Parameter(name="language", param_type="str", default_value="'python'")
        ],
        source_code=method_code,
        docstring="解析代码"
    )
    
    class_info = ClassInfo(
        name="CodeParser",
        full_name="CodeParser",
        parent_class="BaseParser",
        interfaces=["IParser"]
    )
    
    file_content = """
    import os
    from analysis import Analyzer
    from .utils import helper
    
    class CodeParser(BaseParser):
        pass
    """
    
    clues = extractor.extract_clues(
        method_info=method_info,
        class_info=class_info,
        file_content=file_content
    )
    
    print("=" * 60)
    print("代码语义线索提取测试")
    print("=" * 60)
    print(f"装饰器: {clues['decorators']}")
    print(f"继承关系: {clues['inheritance']}")
    print(f"导入语句: {clues['imports']}")
    print(f"Docstring: {clues['docstring']}")
    print(f"注释: {clues['comments']}")
    print(f"异常类型: {clues['exceptions']}")
    print(f"依赖: {clues['dependencies']}")
    print(f"类型注解: {clues['annotations']}")


if __name__ == "__main__":
    main()




















