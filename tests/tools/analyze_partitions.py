#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析功能分区的详细信息
"""

import os
import sys
import io
import json

# 设置标准输出为UTF-8编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))

from analysis.community_detector import CommunityDetector
from analysis.analyzer import CodeAnalyzer
from analysis.code_model import ProjectAnalysisReport

def get_partition_details():
    """获取功能分区的详细信息"""
    project_path = os.path.dirname(__file__)
    
    # 1. 运行代码分析
    print("="*60)
    print("步骤1: 运行代码分析获取调用图...")
    print("="*60)
    analyzer = CodeAnalyzer(project_path)
    graph_data = analyzer.analyze(project_path)
    
    call_graph = analyzer.call_graph_analyzer.call_graph
    print(f"\n✓ 获取调用图: {len(call_graph)} 个方法")
    
    # 2. 运行社区检测
    print("\n" + "="*60)
    print("步骤2: 运行社区检测...")
    print("="*60)
    detector = CommunityDetector()
    partitions = detector.detect_communities(call_graph, algorithm="louvain")
    
    print(f"\n✓ 检测到 {len(partitions)} 个分区")
    
    # 3. 获取每个分区的详细信息
    print("\n" + "="*60)
    print("步骤3: 分析分区详细信息...")
    print("="*60)
    
    detailed_partitions = []
    
    for i, partition in enumerate(partitions):
        methods = partition['methods']
        
        # 分析方法的文件分布
        file_distribution = {}
        class_distribution = {}
        
        for method_sig in methods:
            # 从方法签名提取类名和方法名
            if '.' in method_sig:
                parts = method_sig.split('.')
                if len(parts) >= 2:
                    class_name = parts[0]
                    method_name = '.'.join(parts[1:])
                    
                    # 查找方法在report中的信息
                    if hasattr(analyzer, 'report') and analyzer.report:
                        if class_name in analyzer.report.classes:
                            class_info = analyzer.report.classes[class_name]
                            if method_name in class_info.methods:
                                method_info = class_info.methods[method_name]
                                if method_info.source_location:
                                    file_path = method_info.source_location.file_path
                                    rel_path = os.path.relpath(file_path, project_path)
                                    file_dir = os.path.dirname(rel_path)
                                    
                                    if file_dir not in file_distribution:
                                        file_distribution[file_dir] = []
                                    file_distribution[file_dir].append(method_sig)
                                    
                                    if class_name not in class_distribution:
                                        class_distribution[class_name] = []
                                    class_distribution[class_name].append(method_sig)
        
        detailed_partition = {
            "partition_id": partition['partition_id'],
            "size": partition['size'],
            "modularity": partition['modularity'],
            "internal_calls": partition['internal_calls'],
            "external_calls": partition['external_calls'],
            "methods": methods,
            "file_distribution": file_distribution,
            "class_distribution": class_distribution,
            "top_files": sorted(file_distribution.items(), key=lambda x: len(x[1]), reverse=True)[:3],
            "top_classes": sorted(class_distribution.items(), key=lambda x: len(x[1]), reverse=True)[:3]
        }
        
        detailed_partitions.append(detailed_partition)
    
    # 按大小排序，选择前5个最大的分区
    detailed_partitions.sort(key=lambda x: x['size'], reverse=True)
    
    return detailed_partitions[:5], analyzer.report

def analyze_partition_semantics(partition, report):
    """分析分区的语义含义"""
    methods = partition['methods']
    
    # 提取关键信息
    class_names = set()
    method_names = []
    file_paths = set()
    
    for method_sig in methods:
        if '.' in method_sig:
            parts = method_sig.split('.')
            if len(parts) >= 2:
                class_name = parts[0]
                method_name = '.'.join(parts[1:])
                class_names.add(class_name)
                method_names.append(method_name)
                
                # 查找文件路径
                if class_name in report.classes:
                    class_info = report.classes[class_name]
                    if method_name in class_info.methods:
                        method_info = class_info.methods[method_name]
                        if method_info.source_location:
                            file_paths.add(method_info.source_location.file_path)
    
    # 分析命名模式
    naming_patterns = {}
    for method_name in method_names:
        if '_' in method_name:
            prefix = method_name.split('_')[0] + '_'
            naming_patterns[prefix] = naming_patterns.get(prefix, 0) + 1
    
    # 推断功能
    inferred_function = infer_function_from_names(class_names, method_names, file_paths)
    
    return {
        "class_names": list(class_names),
        "method_names": method_names[:10],  # 前10个
        "file_paths": [os.path.basename(f) for f in list(file_paths)[:5]],
        "naming_patterns": naming_patterns,
        "inferred_function": inferred_function
    }

def infer_function_from_names(class_names, method_names, file_paths):
    """从类名、方法名和文件路径推断功能"""
    keywords = []
    
    # 从类名推断
    for class_name in class_names:
        if 'Parser' in class_name or 'parse' in class_name.lower():
            keywords.append("解析")
        if 'Analyzer' in class_name or 'analyze' in class_name.lower():
            keywords.append("分析")
        if 'Generator' in class_name or 'generate' in class_name.lower():
            keywords.append("生成")
        if 'Extractor' in class_name or 'extract' in class_name.lower():
            keywords.append("提取")
        if 'Visualizer' in class_name or 'visualize' in class_name.lower():
            keywords.append("可视化")
        if 'Graph' in class_name:
            keywords.append("图")
        if 'Flow' in class_name:
            keywords.append("流")
        if 'Call' in class_name:
            keywords.append("调用")
    
    # 从方法名推断
    for method_name in method_names[:20]:  # 只看前20个
        method_lower = method_name.lower()
        if 'parse' in method_lower:
            keywords.append("解析")
        if 'analyze' in method_lower:
            keywords.append("分析")
        if 'generate' in method_lower:
            keywords.append("生成")
        if 'extract' in method_lower:
            keywords.append("提取")
        if 'build' in method_lower:
            keywords.append("构建")
        if 'create' in method_lower:
            keywords.append("创建")
        if 'get' in method_lower:
            keywords.append("获取")
        if 'calculate' in method_lower:
            keywords.append("计算")
    
    # 从文件路径推断
    for file_path in file_paths:
        file_lower = file_path.lower()
        if 'parser' in file_lower:
            keywords.append("解析器")
        if 'analyzer' in file_lower:
            keywords.append("分析器")
        if 'generator' in file_lower:
            keywords.append("生成器")
        if 'extractor' in file_lower:
            keywords.append("提取器")
        if 'graph' in file_lower:
            keywords.append("图")
        if 'flow' in file_lower:
            keywords.append("流")
    
    # 统计关键词频率
    from collections import Counter
    keyword_counts = Counter(keywords)
    
    # 返回前3个最常见的关键词
    top_keywords = [kw for kw, _ in keyword_counts.most_common(3)]
    
    if top_keywords:
        return " + ".join(top_keywords)
    else:
        return "未知功能"

if __name__ == "__main__":
    print("="*60)
    print("功能分区详细分析")
    print("="*60)
    
    detailed_partitions, report = get_partition_details()
    
    print("\n" + "="*60)
    print("前5个最大分区的详细分析")
    print("="*60)
    
    for i, partition in enumerate(detailed_partitions, 1):
        print(f"\n{'='*60}")
        print(f"分区 {i}: {partition['partition_id']}")
        print(f"{'='*60}")
        
        print(f"\n【基本信息】")
        print(f"  - 方法数: {partition['size']}")
        print(f"  - 模块度: {partition['modularity']:.3f}")
        print(f"  - 内部调用: {partition['internal_calls']}")
        print(f"  - 外部调用: {partition['external_calls']}")
        
        print(f"\n【文件分布】")
        for file_dir, methods in partition['top_files']:
            print(f"  - {file_dir}: {len(methods)} 个方法")
        
        print(f"\n【类分布】")
        for class_name, methods in partition['top_classes']:
            print(f"  - {class_name}: {len(methods)} 个方法")
        
        # 语义分析
        semantics = analyze_partition_semantics(partition, report)
        
        print(f"\n【语义分析】")
        print(f"  - 推断功能: {semantics['inferred_function']}")
        print(f"  - 主要类: {', '.join(semantics['class_names'][:5])}")
        print(f"  - 命名模式: {dict(list(semantics['naming_patterns'].items())[:5])}")
        print(f"  - 主要文件: {', '.join(semantics['file_paths'][:3])}")
        
        print(f"\n【方法示例】（前10个）")
        for method in partition['methods'][:10]:
            print(f"  - {method}")
        
        if len(partition['methods']) > 10:
            print(f"  ... 还有 {len(partition['methods']) - 10} 个方法")


























































