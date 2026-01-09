#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据流分析器 - 提取代码中的变量和参数依赖
来自: JUnitGenie 的 obtain_use_relevant_info_relations.py 思路
"""

import ast
from typing import Dict, Set, List, Tuple


class DataFlowAnalyzer:
    """提取代码中的数据流依赖"""
    
    def __init__(self):
        self.variable_dependencies: Dict[str, Set[str]] = {}  # 变量 -> 依赖的变量
        self.parameter_flows: List[Tuple[str, str, str]] = []  # (方法, 参数, 类型)
        self.field_accesses: Dict[str, Set[str]] = {}  # 方法 -> 访问的字段集合
        
    def extract_variable_dependencies(self, method_code: str, class_name: str, 
                                     method_name: str) -> Dict:
        """
        从方法代码提取变量依赖
        
        参考JUnitGenie的approach
        
        Args:
            method_code: 方法源代码
            class_name: 类名
            method_name: 方法名
            
        Returns:
            变量依赖信息
        """
        try:
            tree = ast.parse(method_code)
        except SyntaxError:
            return {}
        
        variables = {}
        assignments = {}  # 变量 -> 被赋值的内容
        
        class DataFlowVisitor(ast.NodeVisitor):
            def visit_Assign(self, node):
                """处理赋值语句"""
                # 获取被赋值的变量
                targets = []
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        targets.append(target.id)
                    elif isinstance(target, ast.Attribute):
                        targets.append(self._get_attr_name(target))
                
                # 获取右侧使用的变量
                if isinstance(node.value, ast.Name):
                    used_var = node.value.id
                    for target in targets:
                        if target not in assignments:
                            assignments[target] = set()
                        assignments[target].add(used_var)
                elif isinstance(node.value, ast.Call):
                    # 函数调用的返回值
                    call_name = self._get_call_name(node.value)
                    for target in targets:
                        if target not in assignments:
                            assignments[target] = set()
                        assignments[target].add(call_name)
                elif isinstance(node.value, ast.BinOp):
                    # 二元操作
                    used_vars = self._extract_names_from_expr(node.value)
                    for target in targets:
                        if target not in assignments:
                            assignments[target] = set()
                        assignments[target].update(used_vars)
                
                self.generic_visit(node)
            
            def visit_Return(self, node):
                """处理return语句"""
                if isinstance(node.value, ast.Name):
                    # 返回的变量
                    variables[f"{class_name}.{method_name}.return"] = node.value.id
                
                self.generic_visit(node)
            
            def _get_call_name(self, node):
                """从Call节点提取函数名"""
                if isinstance(node.func, ast.Name):
                    return node.func.id
                elif isinstance(node.func, ast.Attribute):
                    return node.func.attr
                return None
            
            def _get_attr_name(self, node):
                """从Attribute节点提取属性名"""
                if isinstance(node.value, ast.Name):
                    return f"{node.value.id}.{node.attr}"
                return node.attr
            
            def _extract_names_from_expr(self, node):
                """从表达式提取所有变量名"""
                names = set()
                if isinstance(node, ast.Name):
                    names.add(node.id)
                elif isinstance(node, ast.BinOp):
                    names.update(self._extract_names_from_expr(node.left))
                    names.update(self._extract_names_from_expr(node.right))
                elif isinstance(node, ast.Call):
                    call_name = self._get_call_name(node)
                    if call_name:
                        names.add(call_name)
                return names
        
        visitor = DataFlowVisitor()
        visitor.visit(tree)
        
        return {
            "assignments": assignments,
            "variables": variables
        }
    
    def analyze_field_accesses(self, analyzer_report) -> Dict[str, Set[str]]:
        """
        分析每个方法访问的字段
        使用source_code而不是docstring进行AST分析（修复：之前使用docstring导致0个字段访问）
        
        Args:
            analyzer_report: CodeAnalyzer的report对象
            
        Returns:
            方法 -> 字段集合的映射
        """
        print("\n[DataFlowAnalyzer] 分析字段访问...")
        
        field_access_count = 0
        
        for class_name, class_info in analyzer_report.classes.items():
            for method_name, method_info in class_info.methods.items():
                method_sig = f"{class_name}.{method_name}"
                
                # 修复：使用source_code而不是docstring，并进行AST分析
                source_code = method_info.source_code or ""
                if not source_code:
                    continue
                
                accessed_fields = self._extract_field_accesses_from_ast(
                    source_code, 
                    class_info
                )
                
                if accessed_fields:
                    self.field_accesses[method_sig] = accessed_fields
                    field_access_count += len(accessed_fields)
        
        print(f"[DataFlowAnalyzer] ✓ 字段访问分析完成")
        print(f"[DataFlowAnalyzer]   - 字段访问关系数: {field_access_count}")
        
        return self.field_accesses
    
    def _extract_field_accesses_from_ast(self, code: str, class_info) -> Set[str]:
        """从源代码的AST中提取对类字段的访问"""
        accessed_fields = set()
        
        # 获取类的所有字段名
        field_names = set()
        for field_name, field_info in class_info.fields.items():
            field_names.add(field_name)
        
        if not field_names or not code:
            return accessed_fields
        
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return accessed_fields
        
        class FieldAccessVisitor(ast.NodeVisitor):
            def visit_Attribute(self, node):
                """访问属性访问节点 (如 self.field, obj.field)"""
                # 检查是否是 self.field_name 或 其他对象.field_name
                if isinstance(node.value, ast.Name):
                    # self.field 或 obj.field
                    if node.attr in field_names:
                        accessed_fields.add(node.attr)
                
                self.generic_visit(node)
        
        visitor = FieldAccessVisitor()
        visitor.visit(tree)
        
        return accessed_fields
    
    def _extract_field_accesses(self, code: str, class_info) -> Set[str]:
        """从代码提取对类字段的访问"""
        accessed_fields = set()
        
        # 获取类的所有字段名（处理字段可能是FieldInfo对象或字符串）
        field_names = set()
        for field in class_info.fields:
            if isinstance(field, str):
                field_names.add(field)
            elif hasattr(field, 'name'):
                field_names.add(field.name)
        
        # 检查代码中是否包含字段访问
        for field_name in field_names:
            if f"self.{field_name}" in code or f".{field_name}" in code:
                accessed_fields.add(field_name)
        
        return accessed_fields
    
    def analyze_parameter_flow(self, call_graph: Dict[str, Set[str]], 
                              analyzer_report) -> List[Tuple]:
        """
        分析参数在方法间的流动
        
        Args:
            call_graph: 调用图
            analyzer_report: CodeAnalyzer的report对象
            
        Returns:
            参数流动列表
        """
        print("\n[DataFlowAnalyzer] 分析参数流动...")
        
        parameter_flows = []
        
        for caller, callees in call_graph.items():
            # 获取caller的参数
            if "." in caller:
                class_name, method_name = caller.rsplit(".", 1)
                if class_name in analyzer_report.classes:
                    class_info = analyzer_report.classes[class_name]
                    if method_name in class_info.methods:
                        caller_method = class_info.methods[method_name]
                        
                        if caller_method.parameters:
                            for param in caller_method.parameters:
                                for callee in callees:
                                    # 创建参数流记录
                                    parameter_flows.append((
                                        caller,
                                        param.name,
                                        callee
                                    ))
        
        self.parameter_flows = parameter_flows
        print(f"[DataFlowAnalyzer] ✓ 参数流动分析完成")
        print(f"[DataFlowAnalyzer]   - 参数流动数: {len(parameter_flows)}")
        
        return parameter_flows
    
    def build_data_flow_graph(self, analyzer_report) -> Dict:
        """
        构建数据流图，返回Cytoscape.js格式
        
        Returns:
            包含nodes和edges的图数据
        """
        nodes = []
        edges = []
        node_set = set()
        
        # 创建变量节点
        for var_name in self.variable_dependencies.keys():
            if var_name not in node_set:
                nodes.append({
                    "data": {
                        "id": var_name,
                        "label": var_name,
                        "type": "variable"
                    }
                })
                node_set.add(var_name)
        
        # 创建字段节点
        for method_fields in self.field_accesses.values():
            for field in method_fields:
                if field not in node_set:
                    nodes.append({
                        "data": {
                            "id": field,
                            "label": field,
                            "type": "field"
                        }
                    })
                    node_set.add(field)
        
        # 创建变量依赖边
        for source, targets in self.variable_dependencies.items():
            for target in targets:
                edges.append({
                    "data": {
                        "id": f"{source}_depends_on_{target}",
                        "source": source,
                        "target": target,
                        "relation": "data_depends"
                    }
                })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "statistics": self.get_data_flow_statistics()
        }
    
    def get_data_flow_statistics(self) -> Dict:
        """获取数据流统计信息"""
        return {
            "total_variable_dependencies": len(self.variable_dependencies),
            "total_field_accesses": sum(len(fields) for fields in self.field_accesses.values()),
            "total_parameter_flows": len(self.parameter_flows),
            "methods_with_field_access": len(self.field_accesses)
        }


# 导出用于集成
__all__ = ['DataFlowAnalyzer']
