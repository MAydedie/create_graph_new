#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
增强可视化模块 - 支持多视图、交互式图表、热点图等
参考AuditLuma的可视化方案进行优化
"""

import json
import os
from typing import Dict, List, Any, Set
from pathlib import Path


class EnhancedVisualizer:
    """增强的代码可视化器 - 支持多种视图"""
    
    def __init__(self):
        self.output_dir = Path("output_analysis")
        self.output_dir.mkdir(exist_ok=True)
    
    def generate_call_graph_view(self, call_graph: Dict[str, Set[str]]) -> Dict:
        """生成方法调用图可视化数据
        
        Args:
            call_graph: 调用图 {caller -> {callees}}
            
        Returns:
            Cytoscape格式的图数据
        """
        nodes = []
        edges = []
        seen_nodes = set()
        
        # 创建节点和边
        for caller, callees in call_graph.items():
            # 添加caller节点
            if caller not in seen_nodes:
                nodes.append({
                    "data": {
                        "id": caller,
                        "label": caller.split(".")[-1],  # 只显示方法名
                        "type": "method",
                        "full_name": caller
                    }
                })
                seen_nodes.add(caller)
            
            # 添加callee节点和边
            for callee in callees:
                if callee not in seen_nodes:
                    nodes.append({
                        "data": {
                            "id": callee,
                            "label": callee.split(".")[-1],
                            "type": "method",
                            "full_name": callee
                        }
                    })
                    seen_nodes.add(callee)
                
                # 添加调用边
                edges.append({
                    "data": {
                        "id": f"{caller}_calls_{callee}",
                        "source": caller,
                        "target": callee,
                        "relation": "calls",
                        "type": "method_call"
                    }
                })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "statistics": {
                "total_methods": len(seen_nodes),
                "total_calls": len(edges)
            }
        }
    
    def generate_field_access_view(self, field_accesses: Dict[str, Set[str]]) -> Dict:
        """生成字段访问可视化数据
        
        Args:
            field_accesses: 字段访问关系 {method -> {fields}}
            
        Returns:
            Cytoscape格式的图数据
        """
        nodes = []
        edges = []
        seen_nodes = set()
        
        for method, fields in field_accesses.items():
            # 添加方法节点
            if method not in seen_nodes:
                nodes.append({
                    "data": {
                        "id": method,
                        "label": method.split(".")[-1],
                        "type": "method",
                        "full_name": method
                    }
                })
                seen_nodes.add(method)
            
            # 添加字段节点和访问边
            for field in fields:
                field_id = f"field_{field}"
                if field_id not in seen_nodes:
                    nodes.append({
                        "data": {
                            "id": field_id,
                            "label": field,
                            "type": "field",
                            "full_name": field
                        }
                    })
                    seen_nodes.add(field_id)
                
                # 添加访问边
                edges.append({
                    "data": {
                        "id": f"{method}_accesses_{field_id}",
                        "source": method,
                        "target": field_id,
                        "relation": "accesses",
                        "type": "field_access"
                    }
                })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "statistics": {
                "total_methods": sum(1 for m in seen_nodes if not m.startswith("field_")),
                "total_fields": sum(1 for f in seen_nodes if f.startswith("field_")),
                "total_accesses": len(edges)
            }
        }
    
    def generate_cross_file_view(self, cross_file_calls: List[tuple], 
                                analyzer_report) -> Dict:
        """生成跨文件依赖可视化数据
        
        Args:
            cross_file_calls: 跨文件调用列表 [(caller_file, caller, callee_file, callee)]
            analyzer_report: 分析报告对象
            
        Returns:
            Cytoscape格式的图数据
        """
        nodes = []
        edges = []
        seen_nodes = set()
        
        for caller_file, caller, callee_file, callee in cross_file_calls:
            # 添加caller文件节点
            if caller_file not in seen_nodes:
                nodes.append({
                    "data": {
                        "id": caller_file,
                        "label": caller_file,
                        "type": "file",
                        "file_type": "caller"
                    }
                })
                seen_nodes.add(caller_file)
            
            # 添加callee文件节点
            if callee_file not in seen_nodes:
                nodes.append({
                    "data": {
                        "id": callee_file,
                        "label": callee_file,
                        "type": "file",
                        "file_type": "callee"
                    }
                })
                seen_nodes.add(callee_file)
            
            # 添加跨文件调用边
            edges.append({
                "data": {
                    "id": f"{caller_file}_to_{callee_file}",
                    "source": caller_file,
                    "target": callee_file,
                    "relation": "cross_file_call",
                    "caller": caller,
                    "callee": callee,
                    "type": "cross_file_dependency"
                }
            })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "statistics": {
                "total_files": len(seen_nodes),
                "total_cross_file_calls": len(edges)
            }
        }
    
    def generate_complete_view(self, analyzer_report) -> Dict:
        """生成完整的综合视图
        
        Args:
            analyzer_report: 分析报告对象
            
        Returns:
            Cytoscape格式的图数据
        """
        nodes = []
        edges = []
        seen_nodes = set()
        
        # 1. 添加类节点
        for class_name, class_info in analyzer_report.classes.items():
            if class_name not in seen_nodes:
                nodes.append({
                    "data": {
                        "id": class_name,
                        "label": class_name,
                        "type": "class",
                        "methods_count": len(class_info.methods)
                    }
                })
                seen_nodes.add(class_name)
            
            # 2. 添加方法节点和包含边
            for method_name, method_info in class_info.methods.items():
                method_id = f"{class_name}.{method_name}"
                if method_id not in seen_nodes:
                    nodes.append({
                        "data": {
                            "id": method_id,
                            "label": method_name,
                            "type": "method",
                            "class": class_name
                        }
                    })
                    seen_nodes.add(method_id)
                
                # 添加包含边（类->方法）
                edges.append({
                    "data": {
                        "id": f"{class_name}_contains_{method_id}",
                        "source": class_name,
                        "target": method_id,
                        "relation": "contains",
                        "type": "containment"
                    }
                })
        
        # 3. 添加继承关系
        for class_name, class_info in analyzer_report.classes.items():
            if class_info.parent_class:
                # 确保父类节点存在
                if class_info.parent_class not in seen_nodes:
                    nodes.append({
                        "data": {
                            "id": class_info.parent_class,
                            "label": class_info.parent_class,
                            "type": "class",
                            "is_external": True
                        }
                    })
                    seen_nodes.add(class_info.parent_class)
                
                # 添加继承边
                edges.append({
                    "data": {
                        "id": f"{class_name}_inherits_{class_info.parent_class}",
                        "source": class_name,
                        "target": class_info.parent_class,
                        "relation": "inherits",
                        "type": "inheritance"
                    }
                })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "statistics": {
                "total_classes": len([n for n in nodes if n["data"]["type"] == "class"]),
                "total_methods": len([n for n in nodes if n["data"]["type"] == "method"]),
                "total_inheritance": len([e for e in edges if e["data"]["relation"] == "inherits"])
            }
        }
    
    def get_cytoscape_style(self, view_type: str = "complete") -> List[Dict]:
        """获取Cytoscape样式配置
        
        Args:
            view_type: 视图类型 (complete, call_graph, field_access, cross_file)
            
        Returns:
            Cytoscape样式列表
        """
        if view_type == "call_graph":
            return self._get_call_graph_style()
        elif view_type == "field_access":
            return self._get_field_access_style()
        elif view_type == "cross_file":
            return self._get_cross_file_style()
        else:
            return self._get_complete_view_style()
    
    def _get_call_graph_style(self) -> List[Dict]:
        """方法调用图样式"""
        return [
            {
                "selector": "node[type='method']",
                "style": {
                    "background-color": "#2ecc71",
                    "label": "data(label)",
                    "text-valign": "center",
                    "text-halign": "center",
                    "color": "#fff",
                    "font-size": 12,
                    "width": "80px",
                    "height": "40px",
                    "border-width": 2,
                    "border-color": "#27ae60"
                }
            },
            {
                "selector": "edge[type='method_call']",
                "style": {
                    "line-color": "#f39c12",
                    "target-arrow-color": "#f39c12",
                    "target-arrow-shape": "vee",
                    "width": 2,
                    "curve-style": "bezier"
                }
            }
        ]
    
    def _get_field_access_style(self) -> List[Dict]:
        """字段访问图样式"""
        return [
            {
                "selector": "node[type='method']",
                "style": {
                    "background-color": "#3498db",
                    "label": "data(label)",
                    "text-valign": "center",
                    "text-halign": "center",
                    "color": "#fff",
                    "font-size": 12,
                    "width": "80px",
                    "height": "40px"
                }
            },
            {
                "selector": "node[type='field']",
                "style": {
                    "background-color": "#e74c3c",
                    "label": "data(label)",
                    "text-valign": "center",
                    "text-halign": "center",
                    "color": "#fff",
                    "font-size": 11,
                    "width": "70px",
                    "height": "35px",
                    "border-width": 2,
                    "border-color": "#c0392b"
                }
            },
            {
                "selector": "edge[type='field_access']",
                "style": {
                    "line-color": "#e74c3c",
                    "target-arrow-color": "#e74c3c",
                    "target-arrow-shape": "vee",
                    "width": 2,
                    "curve-style": "bezier"
                }
            }
        ]
    
    def _get_cross_file_style(self) -> List[Dict]:
        """跨文件依赖样式"""
        return [
            {
                "selector": "node[type='file']",
                "style": {
                    "background-color": "#9b59b6",
                    "label": "data(label)",
                    "text-valign": "center",
                    "text-halign": "center",
                    "color": "#fff",
                    "font-size": 12,
                    "width": "120px",
                    "height": "50px",
                    "border-width": 2,
                    "border-color": "#8e44ad"
                }
            },
            {
                "selector": "edge[type='cross_file_dependency']",
                "style": {
                    "line-color": "#16a085",
                    "target-arrow-color": "#16a085",
                    "target-arrow-shape": "vee",
                    "width": 3,
                    "curve-style": "bezier"
                }
            }
        ]
    
    def _get_complete_view_style(self) -> List[Dict]:
        """完整视图样式"""
        return [
            {
                "selector": "node[type='class']",
                "style": {
                    "background-color": "#3498db",
                    "label": "data(label)",
                    "text-valign": "center",
                    "text-halign": "center",
                    "color": "#fff",
                    "font-size": 13,
                    "width": "100px",
                    "height": "50px",
                    "border-width": 2,
                    "border-color": "#2980b9",
                    "padding": "5px"
                }
            },
            {
                "selector": "node[type='method']",
                "style": {
                    "background-color": "#2ecc71",
                    "label": "data(label)",
                    "text-valign": "center",
                    "text-halign": "center",
                    "color": "#fff",
                    "font-size": 10,
                    "width": "80px",
                    "height": "40px",
                    "border-width": 1,
                    "border-color": "#27ae60"
                }
            },
            {
                "selector": "edge[relation='inherits']",
                "style": {
                    "line-color": "#9b59b6",
                    "target-arrow-color": "#9b59b6",
                    "target-arrow-shape": "triangle",
                    "width": 2.5,
                    "line-style": "solid"
                }
            },
            {
                "selector": "edge[relation='contains']",
                "style": {
                    "line-color": "#95a5a6",
                    "line-style": "dotted",
                    "width": 1,
                    "opacity": 0.5
                }
            }
        ]
    
    def save_view_data(self, view_type: str, data: Dict) -> str:
        """保存视图数据为JSON文件
        
        Args:
            view_type: 视图类型
            data: 视图数据
            
        Returns:
            保存的文件路径
        """
        file_path = self.output_dir / f"graph_{view_type}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return str(file_path)


# 导出
__all__ = ['EnhancedVisualizer']
