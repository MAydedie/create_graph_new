#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CFG（控制流图）生成器
使用AST生成方法的控制流图
"""

import ast
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class CFGNode:
    """CFG节点"""
    node_id: str
    node_type: str  # "entry", "exit", "statement", "condition", "loop"
    label: str
    line_number: int = 0
    code: str = ""


@dataclass
class CFGEdge:
    """CFG边"""
    source_id: str
    target_id: str
    edge_type: str = "normal"  # "normal", "true", "false", "loop_back"


@dataclass
class ControlFlowGraph:
    """控制流图"""
    method_name: str
    nodes: Dict[str, CFGNode] = field(default_factory=dict)
    edges: List[CFGEdge] = field(default_factory=list)
    
    def to_dot(self) -> str:
        """转换为DOT格式"""
        lines = [f'digraph "{self.method_name}" {{']
        lines.append('  rankdir=TB;')
        lines.append('  node [shape=box];')
        
        # 添加节点
        for node_id, node in self.nodes.items():
            label = node.label.replace('"', '\\"')
            lines.append(f'  "{node_id}" [label="{label}"];')
        
        # 添加边
        for edge in self.edges:
            edge_attr = ""
            if edge.edge_type == "true":
                edge_attr = ' [label="True", color="green"]'
            elif edge.edge_type == "false":
                edge_attr = ' [label="False", color="red"]'
            elif edge.edge_type == "loop_back":
                edge_attr = ' [label="Loop", color="blue"]'
            
            lines.append(f'  "{edge.source_id}" -> "{edge.target_id}"{edge_attr};')
        
        lines.append('}')
        return '\n'.join(lines)
    
    def to_json(self) -> Dict:
        """转换为JSON格式"""
        return {
            "method_name": self.method_name,
            "nodes": {
                node_id: {
                    "node_type": node.node_type,
                    "label": node.label,
                    "line_number": node.line_number,
                    "code": node.code
                }
                for node_id, node in self.nodes.items()
            },
            "edges": [
                {
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "edge_type": edge.edge_type
                }
                for edge in self.edges
            ]
        }


class CFGGenerator:
    """CFG生成器"""
    
    def __init__(self):
        self.node_counter = 0
    
    def generate_cfg(self, source_code: str, method_name: str = "") -> ControlFlowGraph:
        """
        从源代码生成CFG
        
        Args:
            source_code: 方法源代码
            method_name: 方法名称
            
        Returns:
            ControlFlowGraph对象
        """
        try:
            tree = ast.parse(source_code)
            cfg = ControlFlowGraph(method_name=method_name)
            
            # 创建入口节点
            entry_id = self._new_node_id()
            cfg.nodes[entry_id] = CFGNode(
                node_id=entry_id,
                node_type="entry",
                label="Entry"
            )
            
            # 遍历AST生成CFG
            visitor = CFGVisitor(cfg, entry_id, self)
            visitor.visit(tree)
            
            # 创建出口节点
            exit_id = self._new_node_id()
            cfg.nodes[exit_id] = CFGNode(
                node_id=exit_id,
                node_type="exit",
                label="Exit"
            )
            
            # 连接最后一个节点到出口
            if visitor.last_node_id:
                cfg.edges.append(CFGEdge(
                    source_id=visitor.last_node_id,
                    target_id=exit_id,
                    edge_type="normal"
                ))
            
            return cfg
            
        except SyntaxError as e:
            # 如果源代码无法解析，返回空CFG
            return ControlFlowGraph(method_name=method_name)
    
    def _new_node_id(self) -> str:
        """生成新的节点ID"""
        self.node_counter += 1
        return f"node_{self.node_counter}"


class CFGVisitor(ast.NodeVisitor):
    """CFG AST访问器"""
    
    def __init__(self, cfg: ControlFlowGraph, entry_id: str, generator: CFGGenerator):
        self.cfg = cfg
        self.current_node_id = entry_id
        self.last_node_id = entry_id
        self.generator = generator
        self.node_stack: List[str] = []  # 用于处理嵌套结构
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """访问函数定义"""
        # 跳过函数定义本身，直接访问函数体
        for stmt in node.body:
            self.visit(stmt)
    
    def visit_If(self, node: ast.If):
        """访问if语句"""
        # 创建条件节点
        condition_id = self.generator._new_node_id()
        condition_code = ast.unparse(node.test) if hasattr(ast, 'unparse') else str(node.test)
        
        self.cfg.nodes[condition_id] = CFGNode(
            node_id=condition_id,
            node_type="condition",
            label=f"If: {condition_code}",
            line_number=node.lineno,
            code=condition_code
        )
        
        # 连接当前节点到条件节点
        self.cfg.edges.append(CFGEdge(
            source_id=self.current_node_id,
            target_id=condition_id,
            edge_type="normal"
        ))
        
        # 处理then分支
        then_last_id = condition_id
        for stmt in node.body:
            stmt_id = self.generator._new_node_id()
            stmt_code = ast.unparse(stmt) if hasattr(ast, 'unparse') else str(stmt)
            
            self.cfg.nodes[stmt_id] = CFGNode(
                node_id=stmt_id,
                node_type="statement",
                label=stmt_code[:50],  # 截断长代码
                line_number=stmt.lineno,
                code=stmt_code
            )
            
            self.cfg.edges.append(CFGEdge(
                source_id=then_last_id,
                target_id=stmt_id,
                edge_type="true"
            ))
            
            self.visit(stmt)
            then_last_id = stmt_id
        
        # 处理else分支
        if node.orelse:
            else_last_id = condition_id
            for stmt in node.orelse:
                stmt_id = self.generator._new_node_id()
                stmt_code = ast.unparse(stmt) if hasattr(ast, 'unparse') else str(stmt)
                
                self.cfg.nodes[stmt_id] = CFGNode(
                    node_id=stmt_id,
                    node_type="statement",
                    label=stmt_code[:50],
                    line_number=stmt.lineno,
                    code=stmt_code
                )
                
                self.cfg.edges.append(CFGEdge(
                    source_id=else_last_id,
                    target_id=stmt_id,
                    edge_type="false"
                ))
                
                self.visit(stmt)
                else_last_id = stmt_id
            
            # 合并两个分支（简化处理）
            self.last_node_id = else_last_id
        else:
            self.last_node_id = then_last_id
    
    def visit_While(self, node: ast.While):
        """访问while循环"""
        # 创建循环条件节点
        loop_id = self.generator._new_node_id()
        condition_code = ast.unparse(node.test) if hasattr(ast, 'unparse') else str(node.test)
        
        self.cfg.nodes[loop_id] = CFGNode(
            node_id=loop_id,
            node_type="loop",
            label=f"While: {condition_code}",
            line_number=node.lineno,
            code=condition_code
        )
        
        # 连接当前节点到循环节点
        self.cfg.edges.append(CFGEdge(
            source_id=self.current_node_id,
            target_id=loop_id,
            edge_type="normal"
        ))
        
        # 处理循环体
        body_last_id = loop_id
        for stmt in node.body:
            stmt_id = self.generator._new_node_id()
            stmt_code = ast.unparse(stmt) if hasattr(ast, 'unparse') else str(stmt)
            
            self.cfg.nodes[stmt_id] = CFGNode(
                node_id=stmt_id,
                node_type="statement",
                label=stmt_code[:50],
                line_number=stmt.lineno,
                code=stmt_code
            )
            
            self.cfg.edges.append(CFGEdge(
                source_id=body_last_id,
                target_id=stmt_id,
                edge_type="normal"
            ))
            
            self.visit(stmt)
            body_last_id = stmt_id
        
        # 添加回边
        self.cfg.edges.append(CFGEdge(
            source_id=body_last_id,
            target_id=loop_id,
            edge_type="loop_back"
        ))
        
        self.last_node_id = loop_id
    
    def visit_Return(self, node: ast.Return):
        """访问return语句"""
        return_id = self.generator._new_node_id()
        return_code = ast.unparse(node) if hasattr(ast, 'unparse') else "return"
        
        self.cfg.nodes[return_id] = CFGNode(
            node_id=return_id,
            node_type="statement",
            label=return_code,
            line_number=node.lineno,
            code=return_code
        )
        
        self.cfg.edges.append(CFGEdge(
            source_id=self.current_node_id,
            target_id=return_id,
            edge_type="normal"
        ))
        
        self.last_node_id = return_id
    
    def visit_Expr(self, node: ast.Expr):
        """访问表达式语句"""
        expr_id = self.generator._new_node_id()
        expr_code = ast.unparse(node.value) if hasattr(ast, 'unparse') else str(node.value)
        
        self.cfg.nodes[expr_id] = CFGNode(
            node_id=expr_id,
            node_type="statement",
            label=expr_code[:50],
            line_number=node.lineno,
            code=expr_code
        )
        
        self.cfg.edges.append(CFGEdge(
            source_id=self.current_node_id,
            target_id=expr_id,
            edge_type="normal"
        ))
        
        self.current_node_id = expr_id
        self.last_node_id = expr_id
    
    def visit_Assign(self, node: ast.Assign):
        """访问赋值语句"""
        assign_id = self.generator._new_node_id()
        assign_code = ast.unparse(node) if hasattr(ast, 'unparse') else str(node)
        
        self.cfg.nodes[assign_id] = CFGNode(
            node_id=assign_id,
            node_type="statement",
            label=assign_code[:50],
            line_number=node.lineno,
            code=assign_code
        )
        
        self.cfg.edges.append(CFGEdge(
            source_id=self.current_node_id,
            target_id=assign_id,
            edge_type="normal"
        ))
        
        self.current_node_id = assign_id
        self.last_node_id = assign_id
























