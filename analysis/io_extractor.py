#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
输入/输出提取器
提取函数的输入和输出信息
"""

import ast
from typing import List, Dict, Set, Optional
from dataclasses import dataclass, field


@dataclass
class InputOutputInfo:
    """输入/输出信息"""
    function_name: str
    inputs: List[Dict[str, str]] = field(default_factory=list)  # [{"name": "x", "type": "str"}]
    outputs: List[Dict[str, str]] = field(default_factory=list)  # [{"name": "return", "type": "int"}]
    global_reads: List[str] = field(default_factory=list)  # 读取的全局变量
    global_writes: List[str] = field(default_factory=list)  # 写入的全局变量
    file_reads: List[str] = field(default_factory=list)  # 读取的文件
    file_writes: List[str] = field(default_factory=list)  # 写入的文件
    print_outputs: List[str] = field(default_factory=list)  # print输出


class IOExtractor:
    """输入/输出提取器"""
    
    def extract_io(self, source_code: str, function_name: str, parameters: List) -> InputOutputInfo:
        """
        提取函数的输入/输出信息
        
        Args:
            source_code: 函数源代码
            function_name: 函数名称
            parameters: 参数列表（Parameter对象列表）
            
        Returns:
            InputOutputInfo对象
        """
        io_info = InputOutputInfo(function_name=function_name)
        
        # 提取参数作为输入
        for param in parameters:
            io_info.inputs.append({
                "name": param.name,
                "type": param.param_type,
                "default_value": param.default_value
            })
        
        try:
            tree = ast.parse(source_code)
            visitor = IOVisitor(io_info)
            visitor.visit(tree)
        except SyntaxError:
            pass
        
        return io_info


class IOVisitor(ast.NodeVisitor):
    """IO AST访问器"""
    
    def __init__(self, io_info: InputOutputInfo):
        self.io_info = io_info
    
    def visit_Return(self, node: ast.Return):
        """访问return语句（输出）"""
        if node.value:
            return_type = self._infer_type(node.value)
            self.io_info.outputs.append({
                "name": "return",
                "type": return_type,
                "code": ast.unparse(node.value) if hasattr(ast, 'unparse') else str(node.value)
            })
    
    def visit_Global(self, node: ast.Global):
        """访问global语句"""
        self.io_info.global_reads.extend(node.names)
        self.io_info.global_writes.extend(node.names)
    
    def visit_Name(self, node: ast.Name):
        """访问名称（可能是全局变量）"""
        # 这里简化处理，实际需要作用域分析
        pass
    
    def visit_Call(self, node: ast.Call):
        """访问函数调用"""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            # 检查是否是文件操作
            if func_name in ['open', 'read', 'readline', 'readlines']:
                # 简化处理，实际需要更复杂的分析
                pass
            elif func_name == 'print':
                # 提取print输出
                for arg in node.args:
                    output = ast.unparse(arg) if hasattr(ast, 'unparse') else str(arg)
                    self.io_info.print_outputs.append(output)
    
    def _infer_type(self, node: ast.AST) -> str:
        """推断类型（简化版本）"""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, int):
                return "int"
            elif isinstance(node.value, str):
                return "str"
            elif isinstance(node.value, bool):
                return "bool"
            elif isinstance(node.value, float):
                return "float"
        elif isinstance(node, ast.Name):
            return "unknown"
        elif isinstance(node, ast.Call):
            return "unknown"
        return "unknown"




























































