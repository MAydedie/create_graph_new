#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
项目代码分析器 - 主分析器类
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from .code_model import ProjectAnalysisReport, ClassInfo, MethodInfo, SourceLocation, Parameter
from .symbol_table import SymbolTable
from parsers.python_parser import PythonParser
from .call_graph_analyzer import CallGraphAnalyzer
from .inheritance_analyzer import InheritanceAnalyzer
from .cross_file_analyzer import CrossFileAnalyzer
from .data_flow_analyzer import DataFlowAnalyzer


class CodeAnalyzer:
    """代码分析器 - 分析Python项目结构"""
    
    def __init__(self, project_path: str = None):
        self.project_path = project_path
        self.report: Optional[ProjectAnalysisReport] = None
        self.symbol_table = SymbolTable()
        print(f"[CodeAnalyzer] 初始化分析器，项目路径: {project_path}")
        try:
            self.python_parser = PythonParser(project_path) if project_path else PythonParser(".")
            print(f"[CodeAnalyzer] PythonParser 初始化成功")
            self.python_parser.symbol_table = self.symbol_table
            print(f"[CodeAnalyzer] SymbolTable 绑定成功")
        except Exception as e:
            print(f"[CodeAnalyzer] ERROR: 初始化失败: {e}")
            raise
    
    def analyze(self, project_path: str) -> Dict[str, Any]:
        """
        分析项目
        
        Args:
            project_path: 项目路径
            
        Returns:
            包含节点和边的图数据字典
        """
        print(f"[CodeAnalyzer.analyze] 开始分析项目: {project_path}", flush=True)
        
        if not os.path.isdir(project_path):
            raise ValueError(f"项目路径不存在: {project_path}")
        
        print(f"[CodeAnalyzer.analyze] ✓ 项目路径有效", flush=True)
        
        # 初始化报告
        project_name = os.path.basename(project_path)
        self.report = ProjectAnalysisReport(
            project_name=project_name,
            project_path=project_path,
            analysis_timestamp=str(Path(project_path).stat().st_mtime)
        )
        print(f"[CodeAnalyzer.analyze] ✓ 报告初始化完成", flush=True)
        
        # 收集所有Python文件
        print(f"[CodeAnalyzer.analyze] 正在扫描Python文件...", flush=True)
        python_files = self._find_python_files(project_path)
        self.report.total_files = len(python_files)
        print(f"[CodeAnalyzer.analyze] ✓ 找到 {len(python_files)} 个Python文件", flush=True)
        
        # 解析每个文件
        if python_files:
            print(f"[CodeAnalyzer.analyze] 开始解析文件...", flush=True)
            for idx, file_path in enumerate(python_files, 1):
                try:
                    print(f"[CodeAnalyzer.analyze]   [{idx}/{len(python_files)}] 解析: {os.path.basename(file_path)}", flush=True)
                    self.python_parser.parse_file(file_path, self.report)
                except Exception as e:
                    print(f"[CodeAnalyzer.analyze]   ⚠️  解析失败: {e}", flush=True)
        else:
            print(f"[CodeAnalyzer.analyze] ⚠️  未找到Python文件", flush=True)
        
        print(f"[CodeAnalyzer.analyze] ✓ 所有文件解析完成", flush=True)
        
        # ===== Phase 2: 运行4个增强分析器 =====
        print(f"\n[CodeAnalyzer.analyze] ========== Phase 2: 高级分析 ==========", flush=True)
        
        # 1. 调用图分析
        print(f"[CodeAnalyzer.analyze] 1/4 运行调用图分析器...", flush=True)
        call_graph_analyzer = CallGraphAnalyzer()
        call_graph = call_graph_analyzer.build_call_graph(self.report)
        self.call_graph_analyzer = call_graph_analyzer
        
        # 2. 继承关系分析
        print(f"[CodeAnalyzer.analyze] 2/4 运行继承关系分析器...", flush=True)
        inheritance_analyzer = InheritanceAnalyzer()
        inheritance_analyzer.build_inheritance_graph(self.report)
        self.inheritance_analyzer = inheritance_analyzer
        
        # 3. 跨文件依赖分析
        print(f"[CodeAnalyzer.analyze] 3/4 运行跨文件依赖分析器...", flush=True)
        cross_file_analyzer = CrossFileAnalyzer()
        method_location = cross_file_analyzer.build_method_location_map(self.report, project_path)
        cross_file_analyzer.analyze_cross_file_calls(call_graph, method_location)
        self.cross_file_analyzer = cross_file_analyzer
        
        # 4. 数据流分析
        print(f"[CodeAnalyzer.analyze] 4/4 运行数据流分析器...", flush=True)
        data_flow_analyzer = DataFlowAnalyzer()
        data_flow_analyzer.analyze_field_accesses(self.report)
        if call_graph:
            data_flow_analyzer.analyze_parameter_flow(call_graph, self.report)
        self.data_flow_analyzer = data_flow_analyzer
        
        print(f"[CodeAnalyzer.analyze] ✓ Phase 2 高级分析完成！", flush=True)
        print(f"[CodeAnalyzer.analyze] ==========================================\n", flush=True)
        
        # 生成可视化数据
        print(f"[CodeAnalyzer.analyze] 正在生成增强图表数据...", flush=True)
        graph_data = self._generate_graph_data()
        print(f"[CodeAnalyzer.analyze] ✓ 增强图表数据生成完成", flush=True)
        print(f"[CodeAnalyzer.analyze]   - 类数: {len(self.report.classes)}", flush=True)
        print(f"[CodeAnalyzer.analyze]   - 方法数: {sum(len(c.methods) for c in self.report.classes.values())}", flush=True)
        print(f"[CodeAnalyzer.analyze]   - 函数数: {len(self.report.functions)}", flush=True)
        print(f"[CodeAnalyzer.analyze]   - 调用关系数: {len(call_graph)}", flush=True)
        print(f"[CodeAnalyzer.analyze]   - 跨文件调用数: {len(cross_file_analyzer.cross_file_calls)}", flush=True)
        
        return graph_data
    
    def _find_python_files(self, project_path: str) -> List[str]:
        """找到所有Python文件"""
        python_files = []
        
        for root, dirs, files in os.walk(project_path):
            # 跳过常见的非代码目录
            dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.venv', 'venv', 'node_modules', '.idea']]
            
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))
        
        return python_files
    
    def _generate_graph_data(self) -> Dict[str, Any]:
        """生成Cytoscape.js格式的图数据"""
        nodes = []
        edges = []
        node_ids = set()
        
        if not self.report:
            return {"nodes": [], "edges": [], "metadata": {}}
        
        # 添加类节点
        for class_info in self.report.classes.values():
            node_id = f"class_{class_info.full_name}"
            nodes.append({
                "data": {
                    "id": node_id,
                    "label": class_info.name,
                    "type": "class",
                    "full_name": class_info.full_name,
                    "methods_count": len(class_info.methods),
                    "file": class_info.source_location.file_path if class_info.source_location else "unknown",
                    "line": class_info.source_location.line_start if class_info.source_location else 0,
                    "docstring": class_info.docstring or "No documentation"
                }
            })
            node_ids.add(node_id)
            
            # 添加方法节点
            for method_name, method_info in class_info.methods.items():
                method_id = f"method_{class_info.full_name}_{method_name}"
                nodes.append({
                    "data": {
                        "id": method_id,
                        "label": method_name,
                        "type": "method",
                        "class_name": class_info.name,
                        "return_type": method_info.return_type,
                        "file": method_info.source_location.file_path if method_info.source_location else "unknown",
                        "line": method_info.source_location.line_start if method_info.source_location else 0,
                        "docstring": method_info.docstring or "No documentation"
                    }
                })
                node_ids.add(method_id)
                
                # 添加方法到类的包含边
                edges.append({
                    "data": {
                        "id": f"edge_{node_id}_to_{method_id}",
                        "source": node_id,
                        "target": method_id,
                        "type": "contains",
                        "relation": "contains"
                    }
                })
        
        # 添加函数节点
        for func_info in self.report.functions:
            func_id = f"func_{func_info.name}"
            nodes.append({
                "data": {
                    "id": func_id,
                    "label": func_info.name,
                    "type": "function",
                    "return_type": func_info.return_type,
                    "file": func_info.source_location.file_path if func_info.source_location else "unknown",
                    "line": func_info.source_location.line_start if func_info.source_location else 0,
                    "docstring": func_info.docstring or "No documentation"
                }
            })
            node_ids.add(func_id)
        
        # 添加继承关系边
        for class_info in self.report.classes.values():
            if class_info.parent_class:
                parent_id = f"class_{class_info.parent_class}"
                source_id = f"class_{class_info.full_name}"
                
                # 确保父类节点存在
                if parent_id not in node_ids:
                    nodes.append({
                        "data": {
                            "id": parent_id,
                            "label": class_info.parent_class,
                            "type": "class",
                            "full_name": class_info.parent_class,
                            "methods_count": 0
                        }
                    })
                    node_ids.add(parent_id)
                
                edges.append({
                    "data": {
                        "id": f"edge_{source_id}_inherits_{parent_id}",
                        "source": source_id,
                        "target": parent_id,
                        "type": "inherits",
                        "relation": "inherits"
                    }
                })
        
        # 添加调用关系边 - 从call_graph_analyzer获取方法调用链
        if hasattr(self, 'call_graph_analyzer'):
            # self.call_graph_analyzer.call_graph 是 Dict[方法签名 -> Set[被调用的方法]]
            for caller_sig, called_methods in self.call_graph_analyzer.call_graph.items():
                # 将调用者签名转换为节点ID
                caller_id = self._signature_to_node_id(caller_sig, self.report)
                
                if not caller_id or caller_id not in node_ids:
                    continue
                
                # 为每个被调用的方法添加边
                for called_method in called_methods:
                    # 尝试将被调用方法的名称转换为节点ID
                    callee_id = self._resolve_method_call(called_method, self.report, caller_sig)
                    
                    if callee_id and callee_id in node_ids:
                        edges.append({
                            "data": {
                                "id": f"edge_{caller_id}_calls_{callee_id}",
                                "source": caller_id,
                                "target": callee_id,
                                "type": "calls",
                                "relation": "calls"
                            }
                        })
        
        # 添加跨文件调用边
        if hasattr(self, 'cross_file_analyzer'):
            for cross_file_call in self.cross_file_analyzer.cross_file_calls:
                # cross_file_call = (caller_file, caller, callee_file, callee)
                caller_id = self._get_node_id(cross_file_call[1])
                callee_id = self._get_node_id(cross_file_call[3])
                
                if caller_id and callee_id and caller_id in node_ids and callee_id in node_ids:
                    edges.append({
                        "data": {
                            "id": f"edge_{caller_id}_cross_file_{callee_id}",
                            "source": caller_id,
                            "target": callee_id,
                            "type": "cross_file_call",
                            "relation": "cross_file_call",
                            "caller_file": cross_file_call[0],
                            "callee_file": cross_file_call[2]
                        }
                    })
        
        # 添加字段访问边
        if hasattr(self, 'data_flow_analyzer'):
            for method_sig, accessed_fields in self.data_flow_analyzer.field_accesses.items():
                method_id = self._get_node_id(method_sig)
                if method_id and method_id in node_ids:
                    for field_name in accessed_fields:
                        field_id = f"field_{field_name}"
                        # 添加字段节点
                        if field_id not in node_ids:
                            nodes.append({
                                "data": {
                                    "id": field_id,
                                    "label": field_name,
                                    "type": "field"
                                }
                            })
                            node_ids.add(field_id)
                        
                        # 添加字段访问边
                        edges.append({
                            "data": {
                                "id": f"edge_{method_id}_accesses_{field_id}",
                                "source": method_id,
                                "target": field_id,
                                "type": "accesses",
                                "relation": "accesses"
                            }
                        })
        
        # 添加参数流动边
        if hasattr(self, 'data_flow_analyzer'):
            for caller, param_name, callee in self.data_flow_analyzer.parameter_flows:
                caller_id = self._get_node_id(caller)
                callee_id = self._get_node_id(callee)
                
                if caller_id and callee_id and caller_id in node_ids and callee_id in node_ids:
                    edges.append({
                        "data": {
                            "id": f"edge_{caller_id}_param_{callee_id}",
                            "source": caller_id,
                            "target": callee_id,
                            "type": "parameter_flow",
                            "relation": "parameter_flow",
                            "parameter": param_name
                        }
                    })
        
        # 生成元数据
        metadata = {
            "project_name": self.report.project_name,
            "project_path": self.report.project_path,  # 添加项目路径
            "total_classes": len(self.report.classes),
            "total_methods": sum(len(c.methods) for c in self.report.classes.values()),
            "total_functions": len(self.report.functions),
            "total_files": self.report.total_files,
            "total_lines_of_code": self.report.total_lines_of_code,
            "call_graph_stats": {
                "total_call_relations": len(self.report.call_graph),
                "cyclic_calls": 0  # 简化计算
            }
        }
        
        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": metadata
        }
    
    def _signature_to_node_id(self, signature: str, report) -> Optional[str]:
        """将方法签名转换为节点ID"""
        if '.' in signature:
            parts = signature.rsplit('.', 1)
            class_name = parts[0]
            method_name = parts[1]
            
            if class_name in report.classes:
                return f"method_{class_name}_{method_name}"
        
        return f"func_{signature}"
    
    def _resolve_method_call(self, called_method: str, report, caller_sig: str) -> Optional[str]:
        """
        解析被调用的方法，返回其节点ID
        支持以下调用形式：
        - func() -> func_func
        - obj.method() -> method_ClassName_method
        - self.method() -> method_ClassName_method
        """
        # 情况1：仅有方法名（self.methodB）
        if '.' not in called_method:
            # 从调用者的类推断
            if '.' in caller_sig:
                caller_class = caller_sig.split('.')[0]
                return f"method_{caller_class}_{called_method}"
            return f"func_{called_method}"
        
        # 情况2：完整的类.方法形式
        parts = called_method.rsplit('.', 1)
        class_part = parts[0]  # obj 或 self
        method_name = parts[1]
        
        # 处理self调用
        if class_part in ['self', 'cls']:
            if '.' in caller_sig:
                caller_class = caller_sig.split('.')[0]
                return f"method_{caller_class}_{method_name}"
        
        # 处理对象属性调用（obj.method）
        # 需要查找obj的类型
        for class_name, class_info in report.classes.items():
            if f"{class_name}.{method_name}" in [f"{class_name}.{m}" for m in class_info.methods]:
                return f"method_{class_name}_{method_name}"
        
        # 未找到，返回None
        return None
    
    def _get_node_id(self, signature: str) -> Optional[str]:
        """从方法签名获取节点ID"""
        if '.' in signature:
            parts = signature.rsplit('.', 1)
            class_name = parts[0]
            method_name = parts[1]
            
            # 检查是否是类方法
            if class_name in self.report.classes:
                return f"method_{class_name}_{method_name}"
        
        # 函数
        return f"func_{signature}"
