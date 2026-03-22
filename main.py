"""
代码分析与可视化系统 - 主程序入口
"""

import argparse
import json
from pathlib import Path
from datetime import datetime

from parsers.python_parser import PythonParser
from analysis.call_graph import CallGraph, ExecutionFlowAnalyzer
from visualization.graph_data import GraphDataConverter
from visualization.report_generator import ReportGenerator


def main():
    """主程序"""
    parser = argparse.ArgumentParser(
        description='代码分析与可视化系统 - 分析代码仓库的结构和调用关系'
    )
    parser.add_argument(
        'project_path',
        help='要分析的项目路径'
    )
    parser.add_argument(
        '-o', '--output',
        default='output',
        help='输出目录'
    )
    parser.add_argument(
        '-l', '--language',
        default='python',
        choices=['python', 'java'],
        help='编程语言（默认: python）'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='详细输出'
    )
    
    args = parser.parse_args()
    
    project_path = Path(args.project_path)
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    if not project_path.exists():
        print(f"[ERROR] Project path does not exist: {project_path}")
        return
    
    print(f"[INFO] Analyzed Project: {project_path}")
    print(f"[INFO] Language: {args.language}")
    
    # 选择解析器
    if args.language == 'python':
        code_parser = PythonParser(str(project_path))
    else:
        print("[ERROR] Java not supported yet")
        return
    
    # 解析项目
    print("\n[STEP 1] Parsing code...")
    report = code_parser.parse_project()
    
    print(f"\n[DONE] Parsing complete!")
    print(f"   [STATS] Class count: {report.get_class_count()}")
    print(f"   [STATS] Method count: {report.get_method_count()}")
    print(f"   [STATS] File count: {report.total_files}")
    print(f"   [STATS] Total LoC: {report.total_lines_of_code}")
    
    # 构建调用图
    print("\n[STEP 2] Building call graph...")
    call_graph = CallGraph(report)
    stats = call_graph.get_statistics()
    print(f"[DONE] Call graph built!")
    print(f"   [STATS] Total call relations: {stats['total_call_relations']}")
    print(f"   [STATS] Cyclic calls: {stats['cyclic_calls']}")
    
    # 识别执行入口
    print("\n[STEP 3] Identifying entry points...")
    if args.language == 'python':
        entry_points = code_parser.find_entry_points()
        for entry in entry_points:
            report.entry_points.append(entry)
    print(f"[DONE] Found {len(report.entry_points)} entry points")
    
    # 分析执行流
    print("\n[STEP 4] Analyzing execution flow...")
    flow_analyzer = ExecutionFlowAnalyzer(call_graph, report)
    execution_paths = flow_analyzer.analyze_execution_flow()
    if execution_paths:
        critical_path = flow_analyzer.find_critical_path(execution_paths)
        report.critical_path = critical_path
        print(f"[DONE] Found {len(execution_paths)} execution paths")
        if critical_path:
            print(f"   [STATS] Critical path depth: {critical_path.total_depth}")
    
    # 生成可视化数据
    print("\n[STEP 5] Generating visualization data...")
    converter = GraphDataConverter(report, call_graph)
    converter.export_to_json(str(output_dir / 'graph_data.json'))
    converter.export_summary_report(str(output_dir / 'report_summary.json'))
    
    # 生成 HTML 报告
    print("\n[STEP 6] Generating analysis report...")
    report_gen = ReportGenerator(report, call_graph, execution_paths)
    
    # 生成 Markdown 报告
    markdown_report = report_gen.generate_markdown_report()
    with open(output_dir / 'analysis_report.md', 'w', encoding='utf-8') as f:
        f.write(markdown_report)
    
    # 复制可视化 HTML
    visualization_html = report_gen.generate_visualization_html()
    with open(output_dir / 'visualization.html', 'w', encoding='utf-8') as f:
        f.write(visualization_html)
    
    print(f"\n[DONE] Analysis Complete!")
    print(f"[INFO] Output Directory: {output_dir.absolute()}")
    print(f"\n[INFO] Generated files:")
    print(f"   [FILE] graph_data.json - Graph data (Cytoscape.js format)")
    print(f"   [FILE] analysis_report.md - Markdown analysis report")
    print(f"   [FILE] report_summary.json - JSON summary report")
    print(f"   [FILE] visualization.html - Interactive visualization (Open in browser)")
    
    print(f"\n[NEXT]:")
    print(f"   Open {output_dir / 'visualization.html'} to view interactive chart")


if __name__ == '__main__':
    main()
