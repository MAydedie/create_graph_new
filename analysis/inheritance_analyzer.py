#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
继承关系分析器 - 提取类之间的继承和实现关系
来自: JUnitGenie 的 basic_entities_extraction.py 思路
"""

import ast
from typing import Dict, Set, List, Tuple


class InheritanceAnalyzer:
    """提取代码中的继承关系"""
    
    def __init__(self):
        self.inheritance_graph: Dict[str, str] = {}  # 子类 -> 父类
        self.implementation_graph: Dict[str, Set[str]] = {}  # 类 -> 实现的接口集合
        self.interface_hierarchy: Dict[str, Set[str]] = {}  # 接口 -> 继承的接口
        
    def build_inheritance_graph(self, analyzer_report) -> Dict:
        """
        从分析器报告构建继承关系图
        
        Args:
            analyzer_report: CodeAnalyzer的report对象
            
        Returns:
            包含所有继承关系的字典
        """
        print("\n[InheritanceAnalyzer] 开始构建继承关系图...")
        
        inheritance_count = 0
        
        for class_name, class_info in analyzer_report.classes.items():
            # 处理类继承
            if class_info.parent_class:
                self.inheritance_graph[class_name] = class_info.parent_class
                inheritance_count += 1
                print(f"[InheritanceAnalyzer]   类继承: {class_name} -> {class_info.parent_class}")
        
        print(f"[InheritanceAnalyzer] ✓ 继承关系图构建完成")
        print(f"[InheritanceAnalyzer]   - 继承关系数: {inheritance_count}")
        
        return {
            "inheritance": self.inheritance_graph,
            "implementation": self.implementation_graph,
            "interfaces": self.interface_hierarchy
        }
    
    def get_parent_classes(self, class_name: str) -> List[str]:
        """
        获取类的所有祖先类（递归）
        
        Args:
            class_name: 类名
            
        Returns:
            所有祖先类的列表
        """
        parents = []
        current = class_name
        
        while current in self.inheritance_graph:
            parent = self.inheritance_graph[current]
            parents.append(parent)
            current = parent
        
        return parents
    
    def get_child_classes(self, class_name: str) -> List[str]:
        """
        获取类的所有子类
        
        Args:
            class_name: 父类名
            
        Returns:
            所有子类的列表
        """
        children = []
        for child, parent in self.inheritance_graph.items():
            if parent == class_name:
                children.append(child)
                # 递归获取子类的子类
                children.extend(self.get_child_classes(child))
        
        return children
    
    def get_inheritance_depth(self, class_name: str) -> int:
        """
        获取类在继承树中的深度
        
        Args:
            class_name: 类名
            
        Returns:
            继承深度 (0表示没有父类)
        """
        depth = 0
        current = class_name
        
        while current in self.inheritance_graph:
            depth += 1
            current = self.inheritance_graph[current]
        
        return depth
    
    def detect_inheritance_cycles(self) -> List[List[str]]:
        """
        检测继承关系中的循环
        
        Returns:
            循环继承链列表
        """
        cycles = []
        visited = set()
        
        def dfs(node, path):
            if node in path:
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                if cycle not in cycles:
                    cycles.append(cycle)
                return
            
            if node in visited:
                return
            
            visited.add(node)
            path.append(node)
            
            if node in self.inheritance_graph:
                parent = self.inheritance_graph[node]
                dfs(parent, path[:])
        
        for class_name in self.inheritance_graph:
            dfs(class_name, [])
        
        return cycles
    
    def get_inheritance_statistics(self, analyzer_report) -> Dict:
        """获取继承关系统计信息"""
        # 计算每个类的深度
        depth_distribution = {}
        root_classes = []  # 没有父类的类
        
        for class_name in analyzer_report.classes.keys():
            depth = self.get_inheritance_depth(class_name)
            depth_distribution[depth] = depth_distribution.get(depth, 0) + 1
            
            if depth == 0:
                root_classes.append(class_name)
        
        # 计算每个类的子类数量
        child_counts = {}
        for class_name in analyzer_report.classes.keys():
            children = self.get_child_classes(class_name)
            if children:
                child_counts[class_name] = len(children)
        
        return {
            "total_classes": len(analyzer_report.classes),
            "inheritance_relations": len(self.inheritance_graph),
            "root_classes": len(root_classes),
            "max_inheritance_depth": max(depth_distribution.keys()) if depth_distribution else 0,
            "depth_distribution": depth_distribution,
            "most_specialized_class": max(child_counts.items(), key=lambda x: x[1])[0] if child_counts else None,
            "inheritance_cycles": len(self.detect_inheritance_cycles())
        }
    
    def build_type_hierarchy_graph(self, analyzer_report) -> Dict:
        """
        构建完整的类型层级图，包括类、接口和抽象类
        
        返回格式适合Cytoscape.js可视化
        """
        nodes = []
        edges = []
        
        # 添加所有类作为节点
        for class_name, class_info in analyzer_report.classes.items():
            node_type = "class"
            
            # 判断是否是抽象类或接口 (可以从类名或标记判断)
            if "Abstract" in class_name or "Interface" in class_name:
                node_type = "interface"
            
            nodes.append({
                "data": {
                    "id": class_name,
                    "label": class_name,
                    "type": node_type,
                    "depth": self.get_inheritance_depth(class_name),
                    "child_count": len(self.get_child_classes(class_name))
                }
            })
        
        # 添加继承关系边
        for child, parent in self.inheritance_graph.items():
            edges.append({
                "data": {
                    "id": f"{child}_extends_{parent}",
                    "source": child,
                    "target": parent,
                    "relation": "extends"
                }
            })
        
        # 添加实现关系边
        for class_name, interfaces in self.implementation_graph.items():
            for interface in interfaces:
                edges.append({
                    "data": {
                        "id": f"{class_name}_implements_{interface}",
                        "source": class_name,
                        "target": interface,
                        "relation": "implements"
                    }
                })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "statistics": self.get_inheritance_statistics(analyzer_report)
        }


# 导出用于集成
__all__ = ['InheritanceAnalyzer']
