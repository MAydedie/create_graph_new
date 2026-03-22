"""
报告生成器 - 生成 Markdown 报告和 HTML 可视化
"""

import json
from typing import List, Dict, Optional
from analysis.code_model import ProjectAnalysisReport, ExecutionPath
from analysis.call_graph import CallGraph


class ReportGenerator:
    """生成各种格式的分析报告"""
    
    def __init__(self, report: ProjectAnalysisReport, call_graph: CallGraph, execution_paths: List[ExecutionPath]):
        self.report = report
        self.call_graph = call_graph
        self.execution_paths = execution_paths
    
    def generate_markdown_report(self) -> str:
        """生成 Markdown 格式的详细报告"""
        report_lines = []
        
        # 标题和摘要
        report_lines.append("# Code Analysis Report\n")
        report_lines.append(f"**项目名称**: {self.report.project_name}\n")
        report_lines.append(f"**分析时间**: {self.report.analysis_timestamp}\n")
        report_lines.append(f"**项目路径**: {self.report.project_path}\n\n")
        
        # 项目概览
        report_lines.append("## Project Overview\n")
        report_lines.append("| 指标 | 数值 |\n")
        report_lines.append("|------|------|\n")
        report_lines.append(f"| 总文件数 | {self.report.total_files} |\n")
        report_lines.append(f"| 总行数 | {self.report.total_lines_of_code} |\n")
        report_lines.append(f"| 类的数量 | {self.report.get_class_count()} |\n")
        report_lines.append(f"| 方法总数 | {self.report.get_method_count()} |\n")
        report_lines.append(f"| 函数总数 | {len(self.report.functions)} |\n\n")
        
        # 代码结构
        report_lines.append("## Code Structure\n")
        report_lines.append("### 类列表\n")
        for class_name, class_info in self.report.classes.items():
            methods_list = ", ".join(list(class_info.methods.keys())[:5])
            if len(class_info.methods) > 5:
                methods_list += f", ... 共{len(class_info.methods)}个方法"
            
            parent_info = f" extends {class_info.parent_class}" if class_info.parent_class else ""
            report_lines.append(f"\n#### {class_info.name}{parent_info}\n")
            report_lines.append(f"**文件**: {class_info.source_location.file_path if class_info.source_location else 'Unknown'}\n")
            report_lines.append(f"**方法**: {methods_list}\n")
            if class_info.docstring:
                report_lines.append(f"**说明**: {class_info.docstring[:100]}\n")
        
        report_lines.append("\n")
        
        # 调用关系分析
        report_lines.append("## Call Graph Analysis\n")
        stats = self.call_graph.get_statistics()
        report_lines.append(f"**总调用关系**: {stats['total_call_relations']}\n")
        report_lines.append(f"**循环调用**: {stats['cyclic_calls']}\n")
        
        if stats['most_called_methods']:
            report_lines.append("\n### 最常被调用的方法\n")
            for method_sig, count in stats['most_called_methods']:
                report_lines.append(f"- {method_sig}: {count} 次\n")
        
        report_lines.append("\n")
        
        # 执行流分析
        report_lines.append("## Execution Flow Analysis\n")
        report_lines.append(f"**总执行入口**: {len(self.report.entry_points)}\n\n")
        
        for entry in self.report.entry_points:
            report_lines.append(f"### 入口: {entry.method.name}\n")
            report_lines.append(f"**类型**: {entry.entry_type}\n")
            report_lines.append(f"**说明**: {entry.description}\n\n")
        
        if self.report.critical_path:
            report_lines.append("### 关键执行路径\n")
            report_lines.append(f"**深度**: {self.report.critical_path.total_depth}\n\n")
            report_lines.append("**执行步骤**:\n")
            
            for i, step in enumerate(self.report.critical_path.steps, 1):
                indent = "  " * step.depth
                report_lines.append(f"{i}. {indent}**{step.method.name}** ({step.method.class_name})\n")
                report_lines.append(f"   {indent}说明: {step.description}\n")
                if step.method.source_location:
                    report_lines.append(f"   {indent}位置: {step.method.source_location.file_path}:{step.method.source_location.line_start}\n")
            
            report_lines.append("\n")
        
        # 统计总结
        report_lines.append("## Statistics Summary\n")
        report_lines.append("```\n")
        report_lines.append(f"代码规模:\n")
        report_lines.append(f"  - 文件数: {self.report.total_files}\n")
        report_lines.append(f"  - 代码行: {self.report.total_lines_of_code}\n")
        report_lines.append(f"  - 平均单文件行数: {self.report.total_lines_of_code // max(1, self.report.total_files)}\n\n")
        report_lines.append(f"对象设计:\n")
        report_lines.append(f"  - 类数: {self.report.get_class_count()}\n")
        report_lines.append(f"  - 方法数: {self.report.get_method_count()}\n")
        report_lines.append(f"  - 平均单类方法数: {self.report.get_method_count() // max(1, self.report.get_class_count())}\n\n")
        report_lines.append(f"复杂度:\n")
        report_lines.append(f"  - 调用关系: {stats['total_call_relations']}\n")
        report_lines.append(f"  - 循环调用: {stats['cyclic_calls']}\n")
        report_lines.append("```\n\n")
        
        # 使用说明
        report_lines.append("## How to use\n")
        report_lines.append("1. 打开 `visualization.html` 查看交互式代码图表\n")
        report_lines.append("2. 鼠标悬停显示详细信息\n")
        report_lines.append("3. 点击节点展开详情\n")
        report_lines.append("4. 使用搜索功能查找特定的类或方法\n\n")
        
        report_lines.append("---\n")
        report_lines.append("*报告由代码分析与可视化系统自动生成*\n")
        
        return "".join(report_lines)
    
    def generate_visualization_html(self) -> str:
        """生成交互式可视化 HTML"""
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>代码结构可视化</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.23.0/cytoscape.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/dagre/0.8.5/dagre.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.4.0/cytoscape-dagre.cjs"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            overflow: hidden;
        }
        
        .container {
            display: flex;
            height: 100vh;
        }
        
        .sidebar {
            width: 300px;
            background: white;
            box-shadow: 2px 0 10px rgba(0,0,0,0.1);
            overflow-y: auto;
            padding: 20px;
            border-right: 1px solid #e0e0e0;
        }
        
        .sidebar h2 {
            color: #667eea;
            margin-bottom: 15px;
            font-size: 18px;
        }
        
        .sidebar h3 {
            color: #333;
            margin-top: 15px;
            margin-bottom: 10px;
            font-size: 14px;
            text-transform: uppercase;
            border-bottom: 2px solid #667eea;
            padding-bottom: 5px;
        }
        
        .search-box {
            width: 100%;
            padding: 10px;
            margin-bottom: 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
        }
        
        .search-box:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 5px rgba(102, 126, 234, 0.3);
        }
        
        .control-buttons {
            display: flex;
            gap: 5px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        
        .btn {
            flex: 1;
            padding: 8px 10px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 12px;
            font-weight: bold;
            transition: all 0.3s;
            min-width: 80px;
        }
        
        .btn-primary {
            background: #667eea;
            color: white;
        }
        
        .btn-primary:hover {
            background: #5568d3;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        .btn-secondary {
            background: #f0f0f0;
            color: #333;
            border: 1px solid #ddd;
        }
        
        .btn-secondary:hover {
            background: #e0e0e0;
        }
        
        .info-panel {
            background: #f9f9f9;
            border: 1px solid #e0e0e0;
            border-radius: 5px;
            padding: 10px;
            margin-bottom: 10px;
            font-size: 12px;
        }
        
        .info-panel h4 {
            color: #667eea;
            margin-bottom: 5px;
        }
        
        .info-panel p {
            color: #666;
            margin: 3px 0;
        }
        
        .main-content {
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        
        .top-bar {
            background: white;
            padding: 15px 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .top-bar h1 {
            color: #333;
            font-size: 20px;
        }
        
        .zoom-controls {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        
        .zoom-level {
            font-size: 14px;
            color: #666;
            min-width: 60px;
            text-align: right;
        }
        
        #cy {
            flex: 1;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        }
        
        .details-panel {
            background: white;
            padding: 15px;
            border-top: 1px solid #e0e0e0;
            max-height: 200px;
            overflow-y: auto;
            font-size: 12px;
        }
        
        .details-panel h4 {
            color: #667eea;
            margin-bottom: 10px;
        }
        
        .details-item {
            margin-bottom: 8px;
            padding: 5px;
            background: #f9f9f9;
            border-radius: 3px;
        }
        
        .details-item strong {
            color: #333;
        }
        
        .legend {
            background: white;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 15px;
            font-size: 12px;
        }
        
        .legend-item {
            display: flex;
            align-items: center;
            margin: 5px 0;
        }
        
        .legend-color {
            width: 20px;
            height: 20px;
            border-radius: 3px;
            margin-right: 8px;
        }
        
        .class-color { background: #3498db; }
        .method-color { background: #2ecc71; }
        .function-color { background: #e74c3c; }
    </style>
</head>
<body>
    <div class="container">
        <!-- 侧边栏 -->
        <div class="sidebar">
            <h2>🔍 代码分析工具</h2>
            
            <input type="text" id="searchBox" class="search-box" placeholder="搜索类或方法...">
            
            <div class="control-buttons">
                <button class="btn btn-primary" onclick="zoomFit()">📊 适应屏幕</button>
                <button class="btn btn-secondary" onclick="resetGraph()">🔄 重置</button>
            </div>
            
            <div class="legend">
                <strong>图例</strong>
                <div class="legend-item">
                    <div class="legend-color class-color"></div>
                    <span>类</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color method-color"></div>
                    <span>方法</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color function-color"></div>
                    <span>函数</span>
                </div>
            </div>
            
            <h3>📊 统计信息</h3>
            <div class="info-panel" id="statsPanel">
                <p>加载中...</p>
            </div>
            
            <h3>🎯 执行入口</h3>
            <div id="entryPointsPanel"></div>
            
            <h3>📌 当前选中</h3>
            <div class="info-panel" id="selectedPanel">
                <p>点击节点查看详情</p>
            </div>
        </div>
        
        <!-- 主内容区 -->
        <div class="main-content">
            <div class="top-bar">
                <h1>📈 代码结构可视化</h1>
                <div class="zoom-controls">
                    <button class="btn btn-secondary" onclick="cy.zoom(cy.zoom() * 1.2)">🔍+</button>
                    <span class="zoom-level" id="zoomLevel">100%</span>
                    <button class="btn btn-secondary" onclick="cy.zoom(cy.zoom() / 1.2)">🔍-</button>
                </div>
            </div>
            
            <div id="cy"></div>
            
            <div class="details-panel" id="detailsPanel">
                <h4>节点详情</h4>
                <p>鼠标悬停或点击节点以显示详情</p>
            </div>
        </div>
    </div>
    
    <script>
        // 全局变量
        let cy;
        let graphData = {
            "nodes": [],
            "edges": [],
            "metadata": {}
        };
        
        // 页面加载完成时初始化
        document.addEventListener('DOMContentLoaded', function() {
            loadGraphData();
            initializeCytoscape();
            setupEventListeners();
            updateStatistics();
        });
        
        // 加载图表数据
        function loadGraphData() {
            // 这里应该从 graph_data.json 加载实际数据
            // 由于这是 HTML 字符串，我们使用占位符
            // 在实际使用中，应该通过 AJAX 加载 graph_data.json
            console.log('Loading graph data...');
            
            // 使用 fetch 加载 graph_data.json
            fetch('graph_data.json')
                .then(response => response.json())
                .then(data => {
                    graphData = data;
                    initializeCytoscape();
                    updateStatistics();
                })
                .catch(error => console.log('Note: graph_data.json not found in same directory'));
        }
        
        // 初始化 Cytoscape
        function initializeCytoscape() {
            if (graphData.nodes.length === 0) {
                console.log('No graph data loaded, using example...');
                graphData = getExampleData();
            }
            
            const style = getCytoscapeStyle();
            
            cy = cytoscape({
                container: document.getElementById('cy'),
                elements: graphData.nodes.concat(graphData.edges),
                style: style,
                layout: {
                    name: 'dagre',
                    directed: true,
                    spacingFactor: 1.5,
                    padding: 10
                }
            });
            
            // 处理节点点击
            cy.on('tap', 'node', function(evt) {
                const node = evt.target;
                displayNodeDetails(node);
            });
            
            // 处理节点悬停
            cy.on('mouseover', 'node', function(evt) {
                const node = evt.target;
                showTooltip(node);
            });
            
            cy.on('mouseout', 'node', function() {
                // 隐藏提示
            });
        }
        
        // 显示节点详情
        function displayNodeDetails(node) {
            const data = node.data();
            let html = `<h4>${data.label}</h4>`;
            
            if (data.type === 'class') {
                html += `<div class="details-item"><strong>类型:</strong> 类</div>`;
                html += `<div class="details-item"><strong>方法数:</strong> ${data.methods_count}</div>`;
            } else if (data.type === 'method') {
                html += `<div class="details-item"><strong>类型:</strong> 方法</div>`;
                html += `<div class="details-item"><strong>返回类型:</strong> ${data.return_type}</div>`;
                html += `<div class="details-item"><strong>所属类:</strong> ${data.class_name}</div>`;
            }
            
            if (data.file) {
                html += `<div class="details-item"><strong>文件:</strong> ${data.file}</div>`;
                if (data.line) {
                    html += `<div class="details-item"><strong>行号:</strong> ${data.line}</div>`;
                }
            }
            
            if (data.docstring) {
                html += `<div class="details-item"><strong>说明:</strong> ${data.docstring.substring(0, 100)}</div>`;
            }
            
            document.getElementById('detailsPanel').innerHTML = html;
        }
        
        // 显示提示信息
        function showTooltip(node) {
            const data = node.data();
            // 可以在这里显示工具提示
        }
        
        // 搜索功能
        document.getElementById('searchBox').addEventListener('keyup', function(e) {
            const query = e.target.value.toLowerCase();
            cy.nodes().forEach(node => {
                const label = node.data('label').toLowerCase();
                if (query === '' || label.includes(query)) {
                    node.style('display', 'element');
                    node.style('opacity', 1);
                } else {
                    node.style('opacity', 0.2);
                }
            });
        });
        
        // 更新统计信息
        function updateStatistics() {
            const metadata = graphData.metadata || {};
            const stats = `
                <p><strong>类数:</strong> ${metadata.total_classes || 0}</p>
                <p><strong>方法数:</strong> ${metadata.total_methods || 0}</p>
                <p><strong>文件数:</strong> ${metadata.total_files || 0}</p>
                <p><strong>总行数:</strong> ${metadata.total_lines_of_code || 0}</p>
            `;
            document.getElementById('statsPanel').innerHTML = stats;
        }
        
        // 获取 Cytoscape 样式
        function getCytoscapeStyle() {
            return [
                {
                    selector: 'node[type="class"]',
                    style: {
                        'background-color': '#3498db',
                        'content': 'data(label)',
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'color': '#fff',
                        'font-size': 12,
                        'width': '120px',
                        'height': '60px',
                        'border-width': 2,
                        'border-color': '#2980b9'
                    }
                },
                {
                    selector: 'node[type="method"]',
                    style: {
                        'background-color': '#2ecc71',
                        'content': 'data(label)',
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'color': '#fff',
                        'font-size': 10,
                        'width': '100px',
                        'height': '40px',
                        'border-width': 1,
                        'border-color': '#27ae60'
                    }
                },
                {
                    selector: 'node[type="function"]',
                    style: {
                        'background-color': '#e74c3c',
                        'content': 'data(label)',
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'color': '#fff',
                        'font-size': 10,
                        'width': '100px',
                        'height': '40px',
                        'border-width': 1,
                        'border-color': '#c0392b'
                    }
                },
                {
                    selector: 'edge[type="inherits"]',
                    style: {
                        'line-color': '#9b59b6',
                        'target-arrow-color': '#9b59b6',
                        'target-arrow-shape': 'triangle',
                        'width': 2,
                        'line-style': 'solid'
                    }
                },
                {
                    selector: 'edge[type="calls"]',
                    style: {
                        'line-color': '#f39c12',
                        'target-arrow-color': '#f39c12',
                        'target-arrow-shape': 'vee',
                        'width': 1.5,
                        'curve-style': 'bezier'
                    }
                },
                {
                    selector: 'edge[type="contains"]',
                    style: {
                        'line-color': '#95a5a6',
                        'line-style': 'dotted',
                        'width': 1,
                        'opacity': 0.5
                    }
                }
            ];
        }
        
        // 获取示例数据（用于演示）
        function getExampleData() {
            return {
                "nodes": [
                    {"data": {"id": "GeneticAlgorithm", "label": "GeneticAlgorithm", "type": "class", "methods_count": 7}},
                    {"data": {"id": "GeneticAlgorithm.run", "label": "run()", "type": "method", "parent": "GeneticAlgorithm", "return_type": "tuple"}},
                    {"data": {"id": "GeneticAlgorithm.fitness", "label": "fitness()", "type": "method", "parent": "GeneticAlgorithm", "return_type": "float"}},
                    {"data": {"id": "GeneticAlgorithm.select_parents", "label": "select_parents()", "type": "method", "parent": "GeneticAlgorithm", "return_type": "list"}}
                ],
                "edges": [
                    {"data": {"id": "contains_1", "source": "GeneticAlgorithm", "target": "GeneticAlgorithm.run", "type": "contains"}},
                    {"data": {"id": "contains_2", "source": "GeneticAlgorithm", "target": "GeneticAlgorithm.fitness", "type": "contains"}},
                    {"data": {"id": "call_1", "source": "GeneticAlgorithm.run", "target": "GeneticAlgorithm.fitness", "type": "calls"}}
                ],
                "metadata": {"total_classes": 1, "total_methods": 3}
            };
        }
        
        // 事件监听器设置
        function setupEventListeners() {
            // 缩放更新
            cy.on('zoom pan', function() {
                const zoom = Math.round(cy.zoom() * 100);
                document.getElementById('zoomLevel').textContent = zoom + '%';
            });
        }
        
        // 缩放到适应屏幕
        function zoomFit() {
            cy.fit(cy.elements(), 50);
        }
        
        // 重置图表
        function resetGraph() {
            cy.layout({
                name: 'dagre',
                directed: true,
                spacingFactor: 1.5,
                padding: 10
            }).run();
        }
    </script>
</body>
</html>
"""
        return html
