#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DFG（数据流图）生成器
追踪变量的定义和使用
"""

import ast
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class DFGNode:
    """DFG节点（变量定义或使用）"""
    node_id: str
    node_type: str  # "def" (定义), "use" (使用)
    variable_name: str
    line_number: int = 0
    code: str = ""


@dataclass
class DFGEdge:
    """DFG边（数据流）"""
    source_id: str  # 定义节点
    target_id: str  # 使用节点
    variable_name: str


@dataclass
class DataFlowGraph:
    """数据流图"""
    method_name: str
    nodes: Dict[str, DFGNode] = field(default_factory=dict)
    edges: List[DFGEdge] = field(default_factory=list)
    
    def to_dot(self) -> str:
        """转换为DOT格式"""
        lines = [f'digraph "{self.method_name}_DFG" {{']
        lines.append('  rankdir=LR;')
        lines.append('  node [shape=box];')
        
        # 添加节点
        for node_id, node in self.nodes.items():
            color = "green" if node.node_type == "def" else "blue"
            label = f"{node.variable_name}\n({node.node_type})"
            lines.append(f'  "{node_id}" [label="{label}", color={color}];')
        
        # 添加边
        for edge in self.edges:
            lines.append(f'  "{edge.source_id}" -> "{edge.target_id}" [label="{edge.variable_name}"];')
        
        lines.append('}')
        return '\n'.join(lines)
    
    def to_json(self) -> Dict:
        """转换为JSON格式"""
        return {
            "method_name": self.method_name,
            "nodes": {
                node_id: {
                    "node_type": node.node_type,
                    "variable_name": node.variable_name,
                    "line_number": node.line_number,
                    "code": node.code
                }
                for node_id, node in self.nodes.items()
            },
            "edges": [
                {
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "variable_name": edge.variable_name
                }
                for edge in self.edges
            ]
        }


class DFGGenerator:
    """DFG生成器"""
    
    def __init__(self):
        self.node_counter = 0
        self.definitions: Dict[str, str] = {}  # variable_name -> node_id
    
    def generate_dfg(self, source_code: str, method_name: str = "") -> DataFlowGraph:
        """
        从源代码生成DFG
        
        Args:
            source_code: 方法源代码
            method_name: 方法名称
            
        Returns:
            DataFlowGraph对象
        """
        try:
            tree = ast.parse(source_code)
            dfg = DataFlowGraph(method_name=method_name)
            
            # 遍历AST提取数据流
            visitor = DFGVisitor(dfg, self)
            visitor.visit(tree)
            
            return dfg
            
        except SyntaxError as e:
            # 如果源代码无法解析，返回空DFG
            return DataFlowGraph(method_name=method_name)
    
    def _new_node_id(self) -> str:
        """生成新的节点ID"""
        self.node_counter += 1
        return f"dfg_node_{self.node_counter}"


class DFGVisitor(ast.NodeVisitor):
    """DFG AST访问器"""
    
    def __init__(self, dfg: DataFlowGraph, generator: DFGGenerator):
        self.dfg = dfg
        self.generator = generator
        self.definitions: Dict[str, str] = {}  # variable_name -> node_id
    
    def visit_Assign(self, node: ast.Assign):
        """访问赋值语句（变量定义）"""
        # 处理赋值目标（定义）
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_name = target.id
                def_id = self.generator._new_node_id()
                
                assign_code = ast.unparse(node) if hasattr(ast, 'unparse') else str(node)
                
                self.dfg.nodes[def_id] = DFGNode(
                    node_id=def_id,
                    node_type="def",
                    variable_name=var_name,
                    line_number=node.lineno,
                    code=assign_code
                )
                
                # 如果之前有定义，创建数据流边
                if var_name in self.definitions:
                    self.dfg.edges.append(DFGEdge(
                        source_id=self.definitions[var_name],
                        target_id=def_id,
                        variable_name=var_name
                    ))
                
                self.definitions[var_name] = def_id
        
        # 处理赋值值（使用）
        self._visit_expression(node.value)
    
    def visit_Name(self, node: ast.Name):
        """访问名称（变量使用）"""
        if isinstance(node.ctx, ast.Load):  # 只处理读取
            var_name = node.id
            use_id = self.generator._new_node_id()
            
            self.dfg.nodes[use_id] = DFGNode(
                node_id=use_id,
                node_type="use",
                variable_name=var_name,
                line_number=node.lineno,
                code=var_name
            )
            
            # 如果有定义，创建数据流边
            if var_name in self.definitions:
                self.dfg.edges.append(DFGEdge(
                    source_id=self.definitions[var_name],
                    target_id=use_id,
                    variable_name=var_name
                ))
    
    def _visit_expression(self, node: ast.AST):
        """访问表达式，提取变量使用"""
        if isinstance(node, ast.Name):
            self.visit_Name(node)
        elif isinstance(node, ast.BinOp):
            self._visit_expression(node.left)
            self._visit_expression(node.right)
        elif isinstance(node, ast.Call):
            for arg in node.args:
                self._visit_expression(arg)
            if node.func:
                self._visit_expression(node.func)
        elif isinstance(node, ast.Attribute):
            self._visit_expression(node.value)
        # 可以添加更多表达式类型的处理
























