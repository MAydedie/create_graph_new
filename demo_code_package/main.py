"""
代码库分析器主程序
"""

from codebase_analyzer.parser import CodeParser
from codebase_analyzer.analyzer import CodeAnalyzer
from codebase_analyzer.visualizer import ResultVisualizer


def main():
    """主函数"""
    # 创建分析器
    analyzer = CodeAnalyzer()
    
    # 创建解析器
    parser = CodeParser("example.py")
    analyzer.add_parser(parser)
    
    # 分析项目
    file_paths = ["example.py"]
    results = analyzer.analyze_project(file_paths)
    
    # 生成可视化
    visualizer = ResultVisualizer(analyzer)
    graph_data = visualizer.generate_graph()
    
    # 输出统计信息
    stats = analyzer.get_statistics()
    print(f"统计信息: {stats}")
    
    # 渲染HTML
    visualizer.render_html("output.html")
    print("结果已输出到 output.html")


if __name__ == "__main__":
    main()
























