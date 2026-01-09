"""
Python 代码解析器 - 使用 AST 模块进行深度解析
"""

import ast
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple
from .base_parser import BaseParser
from analysis.code_model import (
    ClassInfo, MethodInfo, FieldInfo, SourceLocation, 
    Parameter, CallRelation, ExecutionEntry
)


class PythonASTVisitor(ast.NodeVisitor):
    """Python AST 访问者 - 提取类、方法和调用关系"""
    
    def __init__(self, file_path: Path, symbol_table):
        self.file_path = file_path
        self.symbol_table = symbol_table
        self.current_class = None
        self.current_method = None
        self.source_lines = []
        self.classes: Dict[str, ClassInfo] = {}
        self.methods: List[MethodInfo] = []
        self.call_relations: List[CallRelation] = []
        
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """访问类定义"""
        # 保存前一个类
        prev_class = self.current_class
        
        # 创建类信息
        parent_class = None
        if node.bases:
            # 获取基类名称
            parent_class = self._get_name_from_node(node.bases[0])
        
        class_info = ClassInfo(
            name=node.name,
            full_name=node.name,  # Python 暂时不处理包名
            parent_class=parent_class,
            source_location=SourceLocation(
                file_path=str(self.file_path),
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                column_start=node.col_offset,
                column_end=node.end_col_offset or 0
            ),
            docstring=ast.get_docstring(node)
        )
        
        self.current_class = class_info
        self.classes[node.name] = class_info
        
        # 访问类的子节点
        self.generic_visit(node)
        
        # 恢复前一个类
        self.current_class = prev_class
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """访问函数定义"""
        # 获取参数信息
        parameters = self._extract_parameters(node)
        
        # 确定返回类型
        return_type = "None"
        if node.returns:
            return_type = self._get_annotation_str(node.returns)
        
        # 确定修饰符
        modifiers = self._extract_modifiers(node)
        
        # 提取完整源代码 - Phase 2分析器关键
        source_code = self._extract_source_code(node)
        
        # 创建方法信息
        if self.current_class:
            # 这是一个类方法
            full_name = f"{self.current_class.name}.{node.name}"
            signature = f"{self.current_class.name}.{node.name}({', '.join(str(p) for p in parameters)})"
            
            method_info = MethodInfo(
                name=node.name,
                class_name=self.current_class.name,
                signature=signature,
                return_type=return_type,
                parameters=parameters,
                modifiers=modifiers,
                source_location=SourceLocation(
                    file_path=str(self.file_path),
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    column_start=node.col_offset,
                    column_end=node.end_col_offset or 0
                ),
                docstring=ast.get_docstring(node),
                source_code=source_code
            )
            
            self.current_class.add_method(method_info)
        else:
            # 这是一个全局函数
            signature = f"{node.name}({', '.join(str(p) for p in parameters)})"
            
            method_info = MethodInfo(
                name=node.name,
                class_name="<module>",
                signature=signature,
                return_type=return_type,
                parameters=parameters,
                modifiers=modifiers,
                source_location=SourceLocation(
                    file_path=str(self.file_path),
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    column_start=node.col_offset,
                    column_end=node.end_col_offset or 0
                ),
                docstring=ast.get_docstring(node),
                source_code=source_code
            )
        
        self.methods.append(method_info)
        
        # 保存前一个方法，访问方法体
        prev_method = self.current_method
        self.current_method = method_info
        
        # 访问函数体以找到调用关系
        for stmt in node.body:
            self.visit(stmt)
        
        self.current_method = prev_method
    
    def visit_Call(self, node: ast.Call) -> None:
        """访问函数调用"""
        if not self.current_method:
            self.generic_visit(node)
            return
        
        # 提取被调用的函数名
        called_func_name = self._get_function_name_from_call(node)
        
        if called_func_name:
            # 添加到当前方法的调用集合
            self.current_method.calls.add(called_func_name)
            
            # 记录调用关系
            relation = CallRelation(
                caller_signature=self.current_method.signature,
                callee_signature=called_func_name,
                line_number=node.lineno,
                call_type="method_call" if "." in called_func_name else "function_call"
            )
            self.call_relations.append(relation)
        
        self.generic_visit(node)
    
    def _extract_parameters(self, node: ast.FunctionDef) -> List[Parameter]:
        """提取函数参数"""
        parameters = []
        
        for arg in node.args.args:
            param_type = "Any"
            if arg.annotation:
                param_type = self._get_annotation_str(arg.annotation)
            
            default_value = None
            # 查找默认值
            defaults_offset = len(node.args.args) - len(node.args.defaults)
            if arg in node.args.args[defaults_offset:]:
                default_idx = node.args.args.index(arg) - defaults_offset
                default_node = node.args.defaults[default_idx]
                default_value = ast.unparse(default_node) if hasattr(ast, 'unparse') else None
            
            parameters.append(Parameter(
                name=arg.arg,
                param_type=param_type,
                default_value=default_value
            ))
        
        return parameters
    
    def _extract_modifiers(self, node: ast.FunctionDef) -> List[str]:
        """提取函数修饰符"""
        modifiers = []
        
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                modifiers.append(decorator.id)
            elif isinstance(decorator, ast.Attribute):
                modifiers.append(self._get_name_from_node(decorator))
        
        # 对于 Python，检查是否是特殊方法
        if node.name.startswith('__') and node.name.endswith('__'):
            modifiers.append("dunder")
        elif node.name.startswith('_'):
            modifiers.append("private")
        
        return modifiers
    
    def _get_annotation_str(self, node) -> str:
        """获取注解的字符串表示"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Subscript):
            base = self._get_annotation_str(node.value)
            if isinstance(node.slice, ast.Tuple):
                params = ", ".join(self._get_annotation_str(elt) for elt in node.slice.elts)
            else:
                params = self._get_annotation_str(node.slice)
            return f"{base}[{params}]"
        else:
            try:
                return ast.unparse(node) if hasattr(ast, 'unparse') else str(node)
            except:
                return "Any"
    
    def _get_name_from_node(self, node) -> str:
        """从 AST 节点提取名称"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value = self._get_name_from_node(node.value)
            return f"{value}.{node.attr}"
        elif isinstance(node, ast.Constant):
            return str(node.value)
        return "Unknown"
    
    def _get_function_name_from_call(self, node: ast.Call) -> Optional[str]:
        """从调用节点提取被调用的函数名"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            base = self._get_name_from_node(node.func.value)
            return f"{base}.{node.func.attr}"
        return None
    
    def visit_Assign(self, node: ast.Assign) -> None:
        """访问赋值语句，用于类字段识别"""
        if self.current_class and not self.current_method:
            # 类级别的赋值（字段）
            for target in node.targets:
                if isinstance(target, ast.Name):
                    field_info = FieldInfo(
                        name=target.id,
                        field_type="Any",
                        source_location=SourceLocation(
                            file_path=str(self.file_path),
                            line_start=node.lineno,
                            line_end=node.end_lineno or node.lineno
                        )
                    )
                    self.current_class.add_field(field_info)
        
        self.generic_visit(node)
    
    def _extract_source_code(self, node: ast.FunctionDef) -> Optional[str]:
        """提取完整的函数源代码"""
        try:
            # 优先使用 ast.unparse (Python 3.9+)
            if hasattr(ast, 'unparse'):
                return ast.unparse(node)
            
            # 备用方案：从文件读取
            if not self.source_lines:
                try:
                    with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        self.source_lines = f.readlines()
                except:
                    return None
            
            # 从源文件提取行
            line_start = node.lineno - 1
            line_end = (node.end_lineno or node.lineno)
            
            if 0 <= line_start < len(self.source_lines):
                source_lines = self.source_lines[line_start:line_end]
                return ''.join(source_lines)
        except Exception as e:
            return None
        
        return None


class PythonParser(BaseParser):
    """Python 代码解析器"""
    
    def get_supported_extensions(self) -> List[str]:
        """支持的文件扩展名"""
        return ["py"]
    
    def parse_file(self, file_path, report=None) -> None:
        """解析 Python 文件"""
        # 处理路径
        if isinstance(file_path, str):
            file_path = Path(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                source_code = f.read()
        except Exception as e:
            print(f"  ❌ 读取文件失败 {file_path}: {e}")
            return
        
        try:
            tree = ast.parse(source_code, filename=str(file_path))
        except SyntaxError as e:
            print(f"  ❌ 语法错误 {file_path}: {e}")
            return
        except Exception as e:
            print(f"  ❌ 解析错误 {file_path}: {e}")
            return
        
        # 创建 AST 访问者
        try:
            visitor = PythonASTVisitor(file_path, self.symbol_table)
            visitor.visit(tree)
            
            # 添加到报告
            if report:
                for class_name, class_info in visitor.classes.items():
                    report.add_class(class_info)
                
                for method_info in visitor.methods:
                    report.functions.append(method_info)
                
        except Exception as e:
            print(f"  ❌ AST访问错误 {file_path}: {e}")
