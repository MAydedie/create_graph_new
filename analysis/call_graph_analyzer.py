#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调用图分析器 - 提取方法间的调用关系
来自: JUnitGenie 的 context_knowledge_distillation.py 思路
"""

import ast
import sys
from typing import Dict, Set, List, Tuple
from pathlib import Path


# Safe print for background threads
def _safe_print(*args, **kwargs):
    try:
        if sys.stdout and hasattr(sys.stdout, 'closed') and sys.stdout.closed:
            return
        print(*args, **kwargs)
    except Exception:
        pass


class CallGraphAnalyzer:
    """提取代码中的方法调用关系"""
    
    def __init__(self):
        self.call_graph: Dict[str, Set[str]] = {}  # 方法签名 -> 被调用的方法集合
        self.cross_file_calls: List[Tuple[str, str, str]] = []  # (caller_file, caller, callee)
        self.external_calls: Set[str] = set()  # 外部库调用
        
        # Python内置容器类型及其方法（用于过滤）
        self._builtin_container_types = {
            'dict', 'list', 'set', 'tuple', 'str', 'int', 'float', 'bool',
            'bytes', 'bytearray', 'frozenset', 'deque', 'defaultdict',
            'OrderedDict', 'Counter', 'ChainMap'
        }
        self._builtin_container_methods = {
            'values', 'keys', 'items', 'get', 'pop', 'update', 'clear',
            'append', 'extend', 'insert', 'remove', 'pop', 'index', 'count',
            'add', 'discard', 'union', 'intersection', 'difference',
            'split', 'join', 'strip', 'replace', 'find', 'index', 'count',
            'startswith', 'endswith', 'lower', 'upper', 'capitalize',
            'encode', 'decode', 'format', 'isalpha', 'isdigit', 'isspace'
        }
        
    def extract_calls_from_method(self, method_code: str, class_name: str, method_name: str) -> Set[str]:
        """
        从单个方法的源代码提取所有函数调用
        
        Args:
            method_code: 方法的源代码
            class_name: 所属类名
            method_name: 方法名
            
        Returns:
            调用的函数集合
        """
        try:
            tree = ast.parse(method_code)
        except SyntaxError:
            return set()
        
        calls = set()
        
        class CallVisitor(ast.NodeVisitor):
            def visit_Call(self, node):
                # 提取被调用函数的名称
                call_name = self._get_call_name(node)
                if call_name and self._is_valid_method_call(call_name):
                    calls.add(call_name)
                self.generic_visit(node)
            
            def _is_valid_method_call(self, call_name: str) -> bool:
                """
                检查调用是否是有效的方法调用（过滤掉容器方法和属性访问链）
                
                Args:
                    call_name: 调用名称，如 "dict.values", "func.incoming_calls.values"
                
                Returns:
                    True 如果是有效的方法调用，False 如果是容器方法或属性访问链
                """
                # 如果没有点号，可能是全局函数，允许通过
                if '.' not in call_name:
                    return True
                
                parts = call_name.split('.')
                
                # 如果只有两部分，检查是否是内置容器方法
                if len(parts) == 2:
                    base, method = parts
                    # 如果base是内置容器类型，且method是容器方法，则过滤
                    if base in self._builtin_container_types:
                        if method in self._builtin_container_methods:
                            return False
                
                # 如果超过两部分，可能是属性访问链（如 func.incoming_calls.values）
                # 检查中间部分是否是常见的属性名（非类名）
                if len(parts) >= 3:
                    # 常见的属性名模式（非类名）
                    common_attributes = {
                        'incoming_calls', 'outgoing_calls', 'calls', 'called_by',
                        'methods', 'fields', 'attributes', 'properties',
                        'items', 'values', 'keys', 'items', 'entries',
                        'data', 'config', 'settings', 'params', 'args',
                        'kwargs', 'result', 'output', 'input', 'response',
                        'request', 'headers', 'body', 'content', 'text',
                        'json', 'xml', 'html', 'url', 'path', 'file',
                        'dir', 'folder', 'name', 'id', 'type', 'value'
                    }
                    
                    # 检查中间部分是否是属性而非类名
                    for i in range(1, len(parts) - 1):
                        if parts[i] in common_attributes:
                            # 这是属性访问链，不是方法调用
                            return False
                
                return True
            
            def _get_call_name(self, node):
                """从Call节点提取函数名"""
                if isinstance(node.func, ast.Name):
                    # 简单函数调用: func()
                    return node.func.id
                elif isinstance(node.func, ast.Attribute):
                    # 方法调用: obj.method()
                    base = self._get_expr_name(node.func.value)
                    if base:
                        return f"{base}.{node.func.attr}"
                    return node.func.attr
                return None
            
            def _get_expr_name(self, node):
                """递归获取表达式的名称"""
                if isinstance(node, ast.Name):
                    return node.id
                elif isinstance(node, ast.Attribute):
                    base = self._get_expr_name(node.value)
                    if base:
                        return f"{base}.{node.attr}"
                    return node.attr
                elif isinstance(node, ast.Call):
                    # 链式调用: obj.method1().method2()
                    return self._get_call_name(node)
                return None
        
        visitor = CallVisitor()
        # 将内置容器类型和方法传递给visitor
        visitor._builtin_container_types = self._builtin_container_types
        visitor._builtin_container_methods = self._builtin_container_methods
        visitor.visit(tree)
        return calls
    
    def build_call_graph(self, analyzer_report):
        """
        从分析器报告构建完整的调用图
        使用方法的完整源代码进行AST分析（修复：之前使用docstring导致0个关系）
        
        Args:
            analyzer_report: CodeAnalyzer的report对象
        """
        _safe_print("\n[CallGraphAnalyzer] 开始构建调用图...")
        
        # 第1步：收集所有方法签名映射
        method_signatures: Dict[str, Tuple[str, str]] = {}  # 方法名 -> (类名, 完整签名)
        
        for class_name, class_info in analyzer_report.classes.items():
            for method_name, method_info in class_info.methods.items():
                full_sig = f"{class_name}.{method_name}"
                method_signatures[method_name] = (class_name, full_sig)
        
        # 第2步：为每个类方法提取调用（使用source_code而非docstring）
        call_count = 0
        for class_name, class_info in analyzer_report.classes.items():
            for method_name, method_info in class_info.methods.items():
                if not method_info.source_location:
                    continue
                
                caller_sig = f"{class_name}.{method_name}"
                
                # 修复：使用source_code而不是docstring
                source_code = method_info.source_code or ""
                if not source_code:
                    continue
                
                # 提取调用
                called_funcs = self.extract_calls_from_method(
                    source_code,
                    class_name,
                    method_name
                )
                
                if called_funcs:
                    self.call_graph[caller_sig] = called_funcs
                    call_count += len(called_funcs)
        
        # 第3步：函数级别的调用（使用source_code）
        for func_info in analyzer_report.functions:
            source_code = func_info.source_code or ""
            if not source_code:
                continue
            
            called_funcs = self.extract_calls_from_method(
                source_code,
                "<module>",
                func_info.name
            )
            
            if called_funcs:
                self.call_graph[func_info.name] = called_funcs
                call_count += len(called_funcs)
        
        _safe_print(f"[CallGraphAnalyzer] ✓ 调用图构建完成")
        _safe_print(f"[CallGraphAnalyzer]   - 方法数: {len(self.call_graph)}")
        _safe_print(f"[CallGraphAnalyzer]   - 调用关系数: {call_count}")
        
        return self.call_graph
    
    def get_call_chain(self, method_sig: str, max_depth: int = 3) -> List[List[str]]:
        """
        获取方法的调用链 (递归追踪)
        
        参考JUnitGenie的递归约束求解思路
        
        Args:
            method_sig: 方法签名
            max_depth: 最大递归深度 (JUnitGenie使用3层)
            
        Returns:
            调用链列表
        """
        if max_depth <= 0 or method_sig not in self.call_graph:
            return [[method_sig]]
        
        chains = []
        called_methods = self.call_graph[method_sig]
        
        for called_method in called_methods:
            sub_chains = self.get_call_chain(called_method, max_depth - 1)
            for chain in sub_chains:
                chains.append([method_sig] + chain)
        
        return chains if chains else [[method_sig]]
    
    def detect_cyclic_calls(self) -> List[List[str]]:
        """检测循环调用"""
        cycles = []
        
        def dfs(node, path, visited):
            if node in path:
                # 找到循环
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                if cycle not in cycles:
                    cycles.append(cycle)
                return
            
            if node in visited:
                return
            
            visited.add(node)
            path.append(node)
            
            if node in self.call_graph:
                for called in self.call_graph[node]:
                    dfs(called, path[:], visited.copy())
        
        for method_sig in self.call_graph:
            dfs(method_sig, [], set())
        
        return cycles
    
    def get_call_statistics(self) -> Dict:
        """获取调用图统计信息"""
        total_calls = sum(len(calls) for calls in self.call_graph.values())
        cyclic_calls = self.detect_cyclic_calls()
        
        # 计算入度和出度
        in_degree = {}
        for called_set in self.call_graph.values():
            for called in called_set:
                in_degree[called] = in_degree.get(called, 0) + 1
        
        return {
            "total_methods": len(self.call_graph),
            "total_calls": total_calls,
            "cyclic_calls": len(cyclic_calls),
            "avg_calls_per_method": total_calls / len(self.call_graph) if self.call_graph else 0,
            "most_called": max(in_degree.items(), key=lambda x: x[1])[0] if in_degree else None,
            "most_calling": max(self.call_graph.items(), key=lambda x: len(x[1]))[0] if self.call_graph else None
        }


# 导出用于集成
__all__ = ['CallGraphAnalyzer']
