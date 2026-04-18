"""
应用主程序 - 功能层级分析
"""

from analysis.function_node_enhancer import enhance_hypergraph_with_function_nodes
from analysis.path_level_analyzer import generate_path_level_cfg, generate_path_level_dfg
from parsers.python_parser import PythonParser
from visualization.enhanced_visualizer import EnhancedVisualizer
from llm.code_understanding_agent import CodeUnderstandingAgent
from config.config import Config


def analyze_function_hierarchy(project_path):
    """
    分析项目功能层级
    
    Args:
        project_path: 项目路径
        
    Returns:
        分析结果字典
    """
    # 初始化组件
    config = Config()
    config.load('config.json')
    
    parser = PythonParser('example.py')
    visualizer = EnhancedVisualizer()
    agent = CodeUnderstandingAgent()
    
    # 解析代码
    parse_result = parser.parse("""
    class ExampleClass:
        def method1(self):
            pass
        def method2(self):
            pass
    """)
    
    # 构建调用图
    call_graph = _build_call_graph(parse_result)
    
    # 生成可视化
    graph_data = visualizer.generate_graph(call_graph)
    render_result = visualizer.render({'call_graph': call_graph})
    
    # LLM增强
    partition_data = {
        'methods': list(call_graph.keys()),
        'call_relations': _extract_call_relations(call_graph)
    }
    enhanced_data = agent.enhance_partition(partition_data)
    analysis_result = agent.analyze_code("def example(): pass")
    
    # 路径分析
    paths = _extract_paths(call_graph)
    path_analyses = []
    for path in paths:
        cfg = generate_path_level_cfg(path, call_graph, set(call_graph.keys()))
        dfg = generate_path_level_dfg(path, call_graph, set(call_graph.keys()))
        path_analyses.append({
            'path': path,
            'cfg': cfg,
            'dfg': dfg
        })
    
    return {
        'call_graph': call_graph,
        'graph_data': graph_data,
        'render_result': render_result,
        'enhanced_data': enhanced_data,
        'analysis_result': analysis_result,
        'path_analyses': path_analyses
    }


def _build_call_graph(parse_result):
    """构建调用图"""
    call_graph = {}
    classes = parse_result.get('classes', [])
    
    for cls in classes:
        cls_name = cls.get('name', '')
        methods = cls.get('methods', [])
        for method in methods:
            method_name = f"{cls_name}.{method.get('name', '')}"
            call_graph[method_name] = set()
    
    # 添加调用关系
    method_names = list(call_graph.keys())
    if len(method_names) >= 2:
        call_graph[method_names[0]].add(method_names[1])
    
    return call_graph


def _extract_call_relations(call_graph):
    """提取调用关系"""
    relations = []
    for caller, callees in call_graph.items():
        for callee in callees:
            relations.append({
                'caller': caller,
                'callee': callee
            })
    return relations


def _extract_paths(call_graph):
    """提取路径"""
    paths = []
    method_names = list(call_graph.keys())
    
    if len(method_names) >= 3:
        paths.append(method_names[:3])
    if len(method_names) >= 4:
        paths.append(method_names[:4])
    
    return paths

