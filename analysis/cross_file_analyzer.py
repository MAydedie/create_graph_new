#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
跨文件依赖分析器 - 检测跨文件的方法调用和类依赖
来自: AuditLuma 的跨文件分析思路
"""

import os
from typing import Dict, Set, List, Tuple
from pathlib import Path


class CrossFileAnalyzer:
    """检测代码中的跨文件依赖"""
    
    def __init__(self):
        self.cross_file_calls: List[Tuple[str, str, str, str]] = []  # (caller_file, caller, callee_file, callee)
        self.cross_file_dependencies: Dict[str, Set[str]] = {}  # 文件 -> 依赖的文件集合
        self.import_graph: Dict[str, Set[str]] = {}  # 文件 -> 导入的模块/类集合
        
    def build_method_location_map(self, analyzer_report, project_path: str) -> Dict[str, str]:
        """
        构建方法签名到文件路径的映射
        
        Args:
            analyzer_report: CodeAnalyzer的report对象
            project_path: 项目路径
            
        Returns:
            方法签名 -> 文件路径的映射
        """
        method_location = {}
        
        for class_name, class_info in analyzer_report.classes.items():
            if class_info.source_location:
                file_path = class_info.source_location.file_path
                
                # 映射类本身
                method_location[class_name] = file_path
                
                # 映射类中的所有方法
                for method_name in class_info.methods.keys():
                    full_method_sig = f"{class_name}.{method_name}"
                    method_location[full_method_sig] = file_path
        
        # 映射全局函数
        for func_info in analyzer_report.functions:
            if func_info.source_location:
                method_location[func_info.name] = func_info.source_location.file_path
        
        return method_location
    
    def analyze_cross_file_calls(self, call_graph: Dict[str, Set[str]], 
                                 method_location: Dict[str, str]) -> List[Tuple]:
        """
        分析调用图中的跨文件调用
        使用真实的call_graph数据（修复：之前数据源为空导致0个跨文件调用）
        
        Args:
            call_graph: 调用图 (方法签名 -> 被调用方法集合)
            method_location: 方法到文件的映射
            
        Returns:
            跨文件调用列表
        """
        print("\n[CrossFileAnalyzer] 分析跨文件调用...")
        
        cross_file_calls = []
        
        # 修复：使用真实的call_graph数据
        if not call_graph:
            print(f"[CrossFileAnalyzer] ⚠ 调用图为空，无法分析跨文件调用")
            print(f"[CrossFileAnalyzer]   - 跨文件调用数: 0")
            print(f"[CrossFileAnalyzer]   - 文件依赖数: 0")
            return cross_file_calls
        
        for caller, callees in call_graph.items():
            if caller not in method_location:
                continue
            
            caller_file = method_location[caller]
            
            # callees 可能是 Set[str] 或其他容器
            for callee in callees:
                if callee not in method_location:
                    continue
                
                callee_file = method_location[callee]
                
                # 检查是否跨文件
                if caller_file != callee_file:
                    cross_file_calls.append((
                        os.path.basename(caller_file),
                        caller,
                        os.path.basename(callee_file),
                        callee
                    ))
                    
                    # 记录文件依赖
                    if caller_file not in self.cross_file_dependencies:
                        self.cross_file_dependencies[caller_file] = set()
                    self.cross_file_dependencies[caller_file].add(callee_file)
        
        self.cross_file_calls = cross_file_calls
        print(f"[CrossFileAnalyzer] ✓ 跨文件调用分析完成")
        print(f"[CrossFileAnalyzer]   - 跨文件调用数: {len(cross_file_calls)}")
        print(f"[CrossFileAnalyzer]   - 文件依赖数: {len(self.cross_file_dependencies)}")
        
        return cross_file_calls
    
    def get_file_dependencies(self, file_path: str) -> Set[str]:
        """
        获取文件依赖的所有其他文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件集合
        """
        dependencies = set()
        visited = {file_path}
        queue = [file_path]
        
        while queue:
            current_file = queue.pop(0)
            if current_file in self.cross_file_dependencies:
                for dep_file in self.cross_file_dependencies[current_file]:
                    if dep_file not in visited:
                        visited.add(dep_file)
                        dependencies.add(dep_file)
                        queue.append(dep_file)
        
        return dependencies
    
    def detect_circular_dependencies(self) -> List[List[str]]:
        """
        检测文件间的循环依赖
        
        Returns:
            循环依赖列表
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
            
            if node in self.cross_file_dependencies:
                for dep in self.cross_file_dependencies[node]:
                    dfs(dep, path[:])
        
        for file_path in self.cross_file_dependencies:
            dfs(file_path, [])
        
        return cycles
    
    def get_file_coupling(self) -> Dict[str, Dict]:
        """
        计算文件间的耦合度
        
        Returns:
            文件耦合度信息
        """
        coupling_info = {}
        
        for file_path, dependencies in self.cross_file_dependencies.items():
            coupling_info[file_path] = {
                "outgoing_dependencies": len(dependencies),
                "incoming_dependencies": sum(
                    1 for deps in self.cross_file_dependencies.values()
                    if file_path in deps
                ),
                "dependency_list": list(dependencies)
            }
        
        return coupling_info
    
    def build_file_dependency_graph(self, analyzer_report, project_path: str) -> Dict:
        """
        构建文件依赖图，返回Cytoscape.js格式
        
        Args:
            analyzer_report: CodeAnalyzer的report对象
            project_path: 项目路径
            
        Returns:
            包含nodes和edges的图数据
        """
        nodes = []
        edges = []
        file_set = set()
        
        # 收集所有文件
        for class_name, class_info in analyzer_report.classes.items():
            if class_info.source_location:
                file_path = class_info.source_location.file_path
                file_name = os.path.basename(file_path)
                file_set.add(file_path)
        
        # 创建文件节点
        for file_path in file_set:
            file_name = os.path.basename(file_path)
            rel_path = os.path.relpath(file_path, project_path)
            
            nodes.append({
                "data": {
                    "id": file_path,
                    "label": file_name,
                    "type": "file",
                    "full_path": file_path,
                    "rel_path": rel_path
                }
            })
        
        # 创建依赖边
        for caller_file, dependencies in self.cross_file_dependencies.items():
            for dep_file in dependencies:
                edges.append({
                    "data": {
                        "id": f"{caller_file}_depends_on_{dep_file}",
                        "source": caller_file,
                        "target": dep_file,
                        "relation": "depends_on"
                    }
                })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "coupling": self.get_file_coupling(),
            "circular_dependencies": self.detect_circular_dependencies()
        }
    
    def get_cross_file_statistics(self) -> Dict:
        """获取跨文件依赖的统计信息"""
        coupling_info = self.get_file_coupling()
        
        max_outgoing = max(
            (info["outgoing_dependencies"] for info in coupling_info.values()),
            default=0
        )
        max_incoming = max(
            (info["incoming_dependencies"] for info in coupling_info.values()),
            default=0
        )
        
        most_depended_on = max(
            coupling_info.items(),
            key=lambda x: x[1]["incoming_dependencies"],
            default=(None, {})
        )[0]
        
        most_dependent = max(
            coupling_info.items(),
            key=lambda x: x[1]["outgoing_dependencies"],
            default=(None, {})
        )[0]
        
        return {
            "total_cross_file_calls": len(self.cross_file_calls),
            "total_files_with_dependencies": len(self.cross_file_dependencies),
            "max_outgoing_dependencies": max_outgoing,
            "max_incoming_dependencies": max_incoming,
            "most_depended_on_file": most_depended_on,
            "most_dependent_file": most_dependent,
            "circular_dependencies": len(self.detect_circular_dependencies())
        }


# 导出用于集成
__all__ = ['CrossFileAnalyzer']
