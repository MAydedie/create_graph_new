"""
图表数据转换 - 将分析结果转换为可视化格式（Cytoscape.js）
"""

import json
from typing import Dict, List, Any
from analysis.code_model import ProjectAnalysisReport, ClassInfo, MethodInfo
from analysis.call_graph import CallGraph


class GraphDataConverter:
    """将项目分析结果转换为 Cytoscape.js 格式的图表数据"""
    
    def __init__(self, report: ProjectAnalysisReport, call_graph: CallGraph):
        self.report = report
        self.call_graph = call_graph
    
    def convert_to_cytoscape_format(self) -> Dict[str, Any]:
        """转换为 Cytoscape.js 格式"""
        nodes = []
        edges = []
        
        # 添加类节点和方法节点
        nodes, method_nodes = self._create_class_and_method_nodes()
        
        # 添加继承关系边
        edges.extend(self._create_inheritance_edges())
        
        # 添加方法调用边
        edges.extend(self._create_call_edges())
        
        # 添加包含关系边
        edges.extend(self._create_contains_edges(method_nodes))
        
        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": self._generate_metadata()
        }
    
    def _create_class_and_method_nodes(self) -> tuple:
        """创建类和方法节点"""
        nodes = []
        method_nodes = {}
        
        for class_name, class_info in self.report.classes.items():
            # 创建类节点
            class_node = {
                "data": {
                    "id": class_name,
                    "label": class_info.name,
                    "type": "class",
                    "parent": None,
                    "parent_class": class_info.parent_class,
                    "methods_count": len(class_info.methods),
                    "docstring": class_info.docstring or "No documentation",
                    "file": class_info.source_location.file_path if class_info.source_location else "Unknown",
                    "line": class_info.source_location.line_start if class_info.source_location else 0
                }
            }
            nodes.append(class_node)
            
            # 创建方法节点
            for method_name, method_info in class_info.methods.items():
                method_id = f"{class_name}.{method_name}"
                method_node = {
                    "data": {
                        "id": method_id,
                        "label": method_name,
                        "type": "method",
                        "parent": class_name,
                        "class_name": class_name,
                        "signature": method_info.signature,
                        "return_type": method_info.return_type,
                        "modifiers": method_info.modifiers,
                        "docstring": method_info.docstring or "No documentation",
                        "file": method_info.source_location.file_path if method_info.source_location else "Unknown",
                        "line": method_info.source_location.line_start if method_info.source_location else 0,
                        "parameters": [{"name": p.name, "type": p.param_type} for p in method_info.parameters],
                        "calls_count": len(method_info.calls)
                    }
                }
                nodes.append(method_node)
                method_nodes[method_id] = method_info
        
        # 添加模块级函数
        for func_info in self.report.functions:
            func_id = func_info.signature
            func_node = {
                "data": {
                    "id": func_id,
                    "label": func_info.name,
                    "type": "function",
                    "parent": None,
                    "return_type": func_info.return_type,
                    "modifiers": func_info.modifiers,
                    "docstring": func_info.docstring or "No documentation",
                    "file": func_info.source_location.file_path if func_info.source_location else "Unknown",
                    "line": func_info.source_location.line_start if func_info.source_location else 0,
                    "calls_count": len(func_info.calls)
                }
            }
            nodes.append(func_node)
            method_nodes[func_id] = func_info
        
        return nodes, method_nodes
    
    def _create_inheritance_edges(self) -> List[Dict]:
        """创建继承关系边"""
        edges = []
        
        for class_name, class_info in self.report.classes.items():
            if class_info.parent_class:
                edge = {
                    "data": {
                        "id": f"{class_name}_inherits_{class_info.parent_class}",
                        "source": class_info.parent_class,
                        "target": class_name,
                        "type": "inherits",
                        "label": "继承"
                    }
                }
                edges.append(edge)
        
        return edges
    
    def _create_call_edges(self) -> List[Dict]:
        """创建方法调用边"""
        edges = []
        seen = set()
        
        for relation in self.report.call_graph:
            edge_id = f"{relation.caller_signature}_calls_{relation.callee_signature}"
            
            if edge_id not in seen:
                seen.add(edge_id)
                edge = {
                    "data": {
                        "id": edge_id,
                        "source": relation.caller_signature,
                        "target": relation.callee_signature,
                        "type": "calls",
                        "label": "调用",
                        "line_number": relation.line_number
                    }
                }
                edges.append(edge)
        
        return edges
    
    def _create_contains_edges(self, method_nodes: Dict) -> List[Dict]:
        """创建包含关系边（类包含方法）"""
        edges = []
        
        for class_name, class_info in self.report.classes.items():
            for method_name in class_info.methods.keys():
                method_id = f"{class_name}.{method_name}"
                edge = {
                    "data": {
                        "id": f"{class_name}_contains_{method_id}",
                        "source": class_name,
                        "target": method_id,
                        "type": "contains",
                        "label": "包含"
                    }
                }
                edges.append(edge)
        
        return edges
    
    def _generate_metadata(self) -> Dict:
        """生成元数据"""
        return {
            "project_name": self.report.project_name,
            "analysis_timestamp": self.report.analysis_timestamp,
            "total_classes": self.report.get_class_count(),
            "total_methods": self.report.get_method_count(),
            "total_files": self.report.total_files,
            "total_lines_of_code": self.report.total_lines_of_code,
            "call_graph_stats": self.call_graph.get_statistics()
        }
    
    def convert_execution_path_to_cytoscape(self, execution_path) -> Dict[str, Any]:
        """将执行路径转换为 Cytoscape 格式，用于高亮显示"""
        highlight_nodes = []
        highlight_edges = []
        
        for step in execution_path.steps:
            highlight_nodes.append({
                "id": step.method.signature,
                "depth": step.depth,
                "description": step.description
            })
        
        # 添加步骤之间的连接
        for i in range(len(execution_path.steps) - 1):
            source = execution_path.steps[i].method.signature
            target = execution_path.steps[i + 1].method.signature
            
            highlight_edges.append({
                "source": source,
                "target": target,
                "order": i
            })
        
        return {
            "highlighted_nodes": highlight_nodes,
            "highlighted_edges": highlight_edges,
            "entry_point": execution_path.entry_method.signature,
            "total_depth": execution_path.total_depth
        }
    
    def export_to_json(self, output_path: str) -> None:
        """导出为 JSON 文件"""
        data = self.convert_to_cytoscape_format()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 图表数据已导出到: {output_path}")
    
    def export_summary_report(self, output_path: str) -> None:
        """导出汇总报告"""
        report = {
            "project_overview": {
                "name": self.report.project_name,
                "path": self.report.project_path,
                "timestamp": self.report.analysis_timestamp,
                "total_files": self.report.total_files,
                "total_lines_of_code": self.report.total_lines_of_code
            },
            "code_structure": {
                "total_classes": self.report.get_class_count(),
                "total_methods": self.report.get_method_count(),
                "total_functions": len(self.report.functions),
                "classes": [
                    {
                        "name": c.name,
                        "full_name": c.full_name,
                        "parent_class": c.parent_class,
                        "methods": list(c.methods.keys()),
                        "file": c.source_location.file_path if c.source_location else "Unknown"
                    }
                    for c in self.report.classes.values()
                ]
            },
            "call_graph_analysis": self.call_graph.get_statistics(),
            "entry_points": [
                {
                    "method": e.method.name,
                    "type": e.entry_type,
                    "description": e.description
                }
                for e in self.report.entry_points
            ]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 汇总报告已导出到: {output_path}")


def generate_cytoscape_style() -> str:
    """生成 Cytoscape.js 的样式 CSS"""
    return """
    {
        "selector": "node[type='class']",
        "style": {
            "background-color": "#3498db",
            "content": "data(label)",
            "text-valign": "center",
            "text-halign": "center",
            "color": "#fff",
            "font-size": 12,
            "width": "120px",
            "height": "60px",
            "border-width": 2,
            "border-color": "#2980b9"
        }
    },
    {
        "selector": "node[type='method']",
        "style": {
            "background-color": "#2ecc71",
            "content": "data(label)",
            "text-valign": "center",
            "text-halign": "center",
            "color": "#fff",
            "font-size": 10,
            "width": "100px",
            "height": "40px",
            "border-width": 1,
            "border-color": "#27ae60"
        }
    },
    {
        "selector": "node[type='function']",
        "style": {
            "background-color": "#e74c3c",
            "content": "data(label)",
            "text-valign": "center",
            "text-halign": "center",
            "color": "#fff",
            "font-size": 10,
            "width": "100px",
            "height": "40px",
            "border-width": 1,
            "border-color": "#c0392b"
        }
    },
    {
        "selector": "edge[type='inherits']",
        "style": {
            "line-color": "#9b59b6",
            "target-arrow-color": "#9b59b6",
            "target-arrow-shape": "triangle",
            "width": 2,
            "line-style": "solid"
        }
    },
    {
        "selector": "edge[type='calls']",
        "style": {
            "line-color": "#f39c12",
            "target-arrow-color": "#f39c12",
            "target-arrow-shape": "vee",
            "width": 1.5,
            "curve-style": "bezier"
        }
    },
    {
        "selector": "edge[type='contains']",
        "style": {
            "line-color": "#95a5a6",
            "line-style": "dotted",
            "width": 1,
            "opacity": 0.5
        }
    },
    {
        "selector": "node:hover",
        "style": {
            "background-color": "#34495e",
            "box-shadow": "0 0 10px rgba(0,0,0,0.5)"
        }
    },
    {
        "selector": ".highlighted",
        "style": {
            "background-color": "#f39c12",
            "line-color": "#f39c12",
            "z-index": 999
        }
    }
    """
