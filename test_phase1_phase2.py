#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试阶段1和阶段2的实现
"""

import os
import sys
import io

# 设置标准输出为UTF-8编码（解决Windows控制台编码问题）
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from analysis.community_detector import CommunityDetector
from analysis.multi_source_info_collector import MultiSourceInfoCollector
from analysis.analyzer import CodeAnalyzer

def test_phase1():
    """测试阶段1：社区检测"""
    print("\n" + "="*60)
    print("测试阶段1：社区检测")
    print("="*60)
    
    # 使用当前项目作为测试
    project_path = os.path.dirname(__file__)
    
    # 1. 先运行代码分析获取调用图
    print("\n[测试] 步骤1: 运行代码分析...")
    analyzer = CodeAnalyzer(project_path)
    graph_data = analyzer.analyze(project_path)
    
    if not hasattr(analyzer, 'call_graph_analyzer'):
        print("❌ 错误：未找到call_graph_analyzer")
        return False
    
    call_graph = analyzer.call_graph_analyzer.call_graph
    print(f"✓ 获取调用图: {len(call_graph)} 个方法")
    
    # 2. 运行社区检测
    print("\n[测试] 步骤2: 运行社区检测...")
    detector = CommunityDetector()
    
    try:
        partitions = detector.detect_communities(call_graph, algorithm="louvain")
        
        print(f"\n✓ 社区检测完成:")
        print(f"  - 发现 {len(partitions)} 个分区")
        
        # 显示前5个分区
        for i, partition in enumerate(partitions[:5]):
            print(f"\n  分区 {i+1} (ID: {partition['partition_id']}):")
            print(f"    - 方法数: {partition['size']}")
            print(f"    - 模块度: {partition['modularity']:.3f}")
            print(f"    - 内部调用: {partition['internal_calls']}")
            print(f"    - 外部调用: {partition['external_calls']}")
            print(f"    - 示例方法: {', '.join(partition['methods'][:3])}")
        
        # 获取统计信息
        stats = detector.get_statistics()
        print(f"\n统计信息:")
        print(f"  - 总分区数: {stats.get('total_partitions', 0)}")
        print(f"  - 总方法数: {stats.get('total_methods', 0)}")
        print(f"  - 平均模块度: {stats.get('avg_modularity', 0):.3f}")
        
        return True
        
    except Exception as e:
        print(f"❌ 社区检测失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_phase2():
    """测试阶段2：多源信息收集"""
    print("\n" + "="*60)
    print("测试阶段2：多源信息收集")
    print("="*60)
    
    # 使用当前项目作为测试
    project_path = os.path.dirname(__file__)
    
    # 1. 先运行代码分析
    print("\n[测试] 步骤1: 运行代码分析...")
    analyzer = CodeAnalyzer(project_path)
    graph_data = analyzer.analyze(project_path)
    
    if not analyzer.report:
        print("❌ 错误：未获取到分析报告")
        return False
    
    print(f"✓ 代码分析完成")
    
    # 2. 运行多源信息收集
    print("\n[测试] 步骤2: 收集多源信息...")
    collector = MultiSourceInfoCollector(project_path, analyzer.report)
    
    try:
        info = collector.collect_all()
        
        print(f"\n✓ 多源信息收集完成:")
        print(f"  - README关键词: {len(info['readme']['keywords'])} 个")
        print(f"  - 代码注释: {len(info['comments'])} 个")
        print(f"  - 路径信息: {len(info['path_info'])} 个方法")
        print(f"  - 命名模式: {len(info['naming_patterns']['method_prefixes'])} 个方法前缀")
        print(f"  - 数据流: {len(info['data_flow']['parameter_flows'])} 个方法")
        print(f"  - 方法相似度: {len(info['method_similarities'])} 个方法对")
        
        # 显示一些示例
        if info['readme']['keywords']:
            print(f"\n  README关键词示例: {', '.join(info['readme']['keywords'][:5])}")
        
        if info['naming_patterns']['method_prefixes']:
            print(f"\n  方法名前缀示例:")
            for prefix, methods in list(info['naming_patterns']['method_prefixes'].items())[:3]:
                print(f"    - {prefix}: {len(methods)} 个方法")
        
        if info['path_info']:
            sample_method = list(info['path_info'].keys())[0]
            print(f"\n  路径信息示例 ({sample_method}):")
            path_info = info['path_info'][sample_method]
            print(f"    - 文件夹: {path_info['folder_path']}")
            print(f"    - 文件: {path_info['file_name']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 多源信息收集失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("="*60)
    print("阶段1和阶段2功能测试")
    print("="*60)
    
    # 测试阶段1
    phase1_ok = test_phase1()
    
    # 测试阶段2
    phase2_ok = test_phase2()
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    print(f"阶段1 (社区检测): {'✓ 通过' if phase1_ok else '❌ 失败'}")
    print(f"阶段2 (多源信息收集): {'✓ 通过' if phase2_ok else '❌ 失败'}")
    
    if phase1_ok and phase2_ok:
        print("\n🎉 所有测试通过！")
        sys.exit(0)
    else:
        print("\n⚠️ 部分测试失败，请检查错误信息")
        sys.exit(1)

