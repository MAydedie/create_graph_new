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
        print(f"❌ 项目路径不存在: {project_path}")
        return
    
    print(f"📂 分析项目: {project_path}")
    print(f"🔧 使用语言: {args.language}")
    
    # 选择解析器
    if args.language == 'python':
        code_parser = PythonParser(str(project_path))
    else:
        print("❌ 暂不支持 Java")
        return
    
    # 解析项目
    print("\n🔍 第一步: 解析代码...")
    report = code_parser.parse_project()
    
    print(f"\n✅ 解析完成!")
    print(f"   📊 类的数量: {report.get_class_count()}")
    print(f"   📝 方法总数: {report.get_method_count()}")
    print(f"   📁 文件数量: {report.total_files}")
    print(f"   📄 总行数: {report.total_lines_of_code}")
    
    # 构建调用图
    print("\n🔗 第二步: 构建调用图...")
    call_graph = CallGraph(report)
    stats = call_graph.get_statistics()
    print(f"✅ 调用图构建完成!")
    print(f"   🔀 调用关系总数: {stats['total_call_relations']}")
    print(f"   🔄 循环调用: {stats['cyclic_calls']}")
    
    # 识别执行入口
    print("\n🎯 第三步: 识别执行入口...")
    if args.language == 'python':
        entry_points = code_parser.find_entry_points()
        for entry in entry_points:
            report.entry_points.append(entry)
    print(f"✅ 找到 {len(report.entry_points)} 个执行入口")
    
    # 分析执行流
    print("\n🚀 第四步: 分析执行流...")
    flow_analyzer = ExecutionFlowAnalyzer(call_graph, report)
    execution_paths = flow_analyzer.analyze_execution_flow()
    if execution_paths:
        critical_path = flow_analyzer.find_critical_path(execution_paths)
        report.critical_path = critical_path
        print(f"✅ 找到 {len(execution_paths)} 个执行路径")
        if critical_path:
            print(f"   关键路径深度: {critical_path.total_depth}")
    
    # 生成可视化数据
    print("\n🎨 第五步: 生成可视化数据...")
    converter = GraphDataConverter(report, call_graph)
    converter.export_to_json(str(output_dir / 'graph_data.json'))
    converter.export_summary_report(str(output_dir / 'report_summary.json'))
    
    # 生成 HTML 报告
    print("\n📄 第六步: 生成分析报告...")
    report_gen = ReportGenerator(report, call_graph, execution_paths)
    
    # 生成 Markdown 报告
    markdown_report = report_gen.generate_markdown_report()
    with open(output_dir / 'analysis_report.md', 'w', encoding='utf-8') as f:
        f.write(markdown_report)
    
    # 复制可视化 HTML
    visualization_html = report_gen.generate_visualization_html()
    with open(output_dir / 'visualization.html', 'w', encoding='utf-8') as f:
        f.write(visualization_html)
    
    print(f"\n✅ 分析完成!")
    print(f"📁 输出目录: {output_dir.absolute()}")
    print(f"\n📋 生成的文件:")
    print(f"   📊 graph_data.json - 图表数据（Cytoscape.js 格式）")
    print(f"   📄 analysis_report.md - Markdown 分析报告")
    print(f"   📊 report_summary.json - JSON 汇总报告")
    print(f"   🌐 visualization.html - 交互式可视化（请在浏览器中打开）")
    
    print(f"\n🎉 下一步:")
    print(f"   打开 {output_dir / 'visualization.html'} 查看交互式代码图表")


if __name__ == '__main__':
    main()
