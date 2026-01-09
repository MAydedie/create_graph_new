#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Web应用：本地项目代码结构分析和可视化
"""

from flask import Flask, render_template, request, jsonify, send_file
import os
import sys
import json
import threading
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from analysis.analyzer import CodeAnalyzer
from analysis.hierarchy_model import HierarchyModel, HierarchyMetadata, CodeGraph, FunctionPartition, FunctionStats, FolderNode, FolderStats
from analysis.aggregation_calculator import apply_aggregations_to_hierarchy
from llm.code_understanding_agent import CodeUnderstandingAgent
from llm.code_explanation_chain import generate_explanations_for_hierarchy
from analysis.contains_relation_extractor import ContainsRelationExtractor
from analysis.cfg_generator import CFGGenerator
from analysis.dfg_generator import DFGGenerator
from analysis.io_extractor import IOExtractor
from analysis.code_model import RepositoryInfo, PackageInfo, ProjectAnalysisReport
from analysis.community_detector import CommunityDetector
from analysis.function_call_graph_generator import FunctionCallGraphGenerator
from analysis.function_call_hypergraph import FunctionCallHypergraphGenerator
from analysis.entry_point_identifier import EntryPointIdentifierGenerator
from analysis.partition_data_flow_generator import PartitionDataFlowGenerator
from analysis.partition_control_flow_generator import PartitionControlFlowGenerator

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 支持中文

# 全局分析状态（加锁保护，避免多线程读写冲突）
analysis_status = {
    'progress': 0,
    'status': '等待中...',
    'data': None,
    'report': None,  # 保存ProjectAnalysisReport
    'is_analyzing': False,
    'error': None
}
status_lock = threading.Lock()


def update_analysis_status(**kwargs):
    """线程安全地更新全局分析状态"""
    with status_lock:
        analysis_status.update(kwargs)


def generate_folder_nodes(project_path, partitions):
    """
    基于功能分区和项目文件夹生成第2层的文件夹节点（使用绝对路径）
    
    Args:
        project_path: 项目根路径
        partitions: 功能分区列表（每个分区包含 folders 列表，可能是绝对路径或相对路径）
    
    Returns:
        文件夹节点列表（使用绝对路径）
    """
    folders = []
    seen_folders = set()  # 避免重复
    
    try:
        # 为每个功能分区扫描其对应的文件夹
        for partition in partitions:
            for folder_path in partition.folders:
                # 处理绝对路径和相对路径
                if os.path.isabs(folder_path):
                    abs_folder_path = folder_path
                else:
                    abs_folder_path = os.path.join(project_path, folder_path)
                
                # 标准化路径（处理 .. 和 .）
                abs_folder_path = os.path.normpath(abs_folder_path)
                
                if abs_folder_path in seen_folders:
                    continue
                
                if os.path.isdir(abs_folder_path):
                    # 统计该文件夹下的代码统计信息
                    class_count = 0
                    method_count = 0
                    function_count = 0
                    
                    # 扫描文件夹下的 Python 文件
                    for root, dirs, files in os.walk(abs_folder_path):
                        # 跳过常见的非代码目录
                        dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', '.venv', 'venv']]
                        for file in files:
                            if file.endswith('.py'):
                                # 简单统计（可以优化为实际解析）
                                try:
                                    with open(os.path.join(root, file), 'r', encoding='utf-8', errors='ignore') as f:
                                        content = f.read()
                                        # 简单统计类和方法
                                        class_count += content.count('class ')
                                        method_count += content.count('def ')
                                        function_count += content.count('def ') - content.count('    def ')  # 粗略估算
                                except:
                                    pass
                    
                    folder_node = FolderNode(
                        folder_path=abs_folder_path,  # 使用绝对路径
                        parent_function=partition.name,
                        stats=FolderStats(
                            class_count=class_count,
                            method_count=method_count,
                            function_count=function_count
                        )
                    )
                    folders.append(folder_node)
                    seen_folders.add(abs_folder_path)
        
        # 如果没有找到任何文件夹，尝试从项目结构创建
        if not folders and partitions:
            # 扫描项目根目录下的所有文件夹
            for item in os.listdir(project_path):
                item_path = os.path.join(project_path, item)
                if os.path.isdir(item_path) and not item.startswith('.') and not item.startswith('__'):
                    abs_path = os.path.normpath(item_path)
                    if abs_path not in seen_folders:
                        # 尝试匹配到功能分区
                        matched_partition = None
                        for partition in partitions:
                            if item.lower() in [k.lower() for k in partition.keywords]:
                                matched_partition = partition
                                break
                        
                        if not matched_partition and partitions:
                            matched_partition = partitions[0]  # 默认匹配第一个
                        
                        if matched_partition:
                            folder_node = FolderNode(
                                folder_path=abs_path,
                                parent_function=matched_partition.name,
                                stats=FolderStats(class_count=0, method_count=0)
                            )
                            folders.append(folder_node)
                            seen_folders.add(abs_path)
    
    except Exception as e:
        print(f"[app.py] ⚠️ 生成文件夹节点失败: {e}", flush=True)
        import traceback
        traceback.print_exc(file=sys.stdout)
    
    return folders


def deduplicate_and_resolve_name_conflicts(partitions):
    """
    对分区进行去重和名称冲突处理
    
    Args:
        partitions: 分区列表，每个分区包含partition_id、methods、name等
        
    Returns:
        去重后的分区列表
    """
    if not partitions:
        return partitions
    
    print(f"[app.py] 开始去重和名称冲突处理，原始分区数: {len(partitions)}", flush=True)
    
    # 步骤1：按方法集合去重（完全相同的分区）
    seen_method_sets = {}
    unique_partitions = []
    duplicate_count = 0
    
    for partition in partitions:
        methods = partition.get("methods", [])
        method_set = frozenset(methods)
        
        if method_set in seen_method_sets:
            # 发现重复分区，合并信息
            existing = seen_method_sets[method_set]
            duplicate_count += 1
            print(f"[app.py]   发现重复分区: {partition.get('partition_id')} 与 {existing.get('partition_id')} 方法集合相同", flush=True)
            
            # 合并统计信息（如果新分区有更好的信息）
            if partition.get("modularity", 0) > existing.get("modularity", 0):
                existing["modularity"] = partition.get("modularity", 0)
            if partition.get("description") and not existing.get("description"):
                existing["description"] = partition.get("description")
            if partition.get("folders") and not existing.get("folders"):
                existing["folders"] = partition.get("folders")
        else:
            seen_method_sets[method_set] = partition
            unique_partitions.append(partition)
    
    if duplicate_count > 0:
        print(f"[app.py]   合并了 {duplicate_count} 个重复分区", flush=True)
    
    # 步骤2：处理名称冲突（名称相同但方法不同）
    name_count = {}
    name_to_partitions = {}
    
    for partition in unique_partitions:
        name = partition.get("name", "未知分区")
        if name not in name_to_partitions:
            name_to_partitions[name] = []
        name_to_partitions[name].append(partition)
    
    # 为有冲突的名称添加后缀
    conflict_count = 0
    for name, same_name_partitions in name_to_partitions.items():
        if len(same_name_partitions) > 1:
            conflict_count += len(same_name_partitions) - 1
            print(f"[app.py]   发现名称冲突: '{name}' 有 {len(same_name_partitions)} 个分区", flush=True)
            
            # 为除第一个外的所有分区添加后缀
            for idx, partition in enumerate(same_name_partitions[1:], start=1):
                original_name = partition.get("name", "未知分区")
                partition["name"] = f"{original_name}-{idx}"
                partition["original_name"] = original_name  # 保存原始名称
                partition["name_conflict"] = True  # 标记为名称冲突
                print(f"[app.py]     重命名: {partition.get('partition_id')} -> {partition['name']}", flush=True)
    
    if conflict_count > 0:
        print(f"[app.py]   处理了 {conflict_count} 个名称冲突", flush=True)
    
    # 步骤3：更新partition_id以确保唯一性
    for idx, partition in enumerate(unique_partitions):
        if "partition_id" not in partition or not partition["partition_id"]:
            partition["partition_id"] = f"partition_{idx}"
        else:
            # 确保partition_id唯一
            base_id = partition["partition_id"]
            if base_id.startswith("partition_"):
                partition["partition_id"] = base_id
            else:
                partition["partition_id"] = f"partition_{idx}_{base_id}"
    
    print(f"[app.py] ✅ 去重和名称冲突处理完成，最终分区数: {len(unique_partitions)}", flush=True)
    
    return unique_partitions


def _convert_partitions_to_dicts(function_partitions, entity_to_function_map):
    """
    将FunctionPartition列表转换为字典格式（供阶段4使用）
    
    Args:
        function_partitions: FunctionPartition对象列表
        entity_to_function_map: 实体到功能分区的映射 {entity_id: function_name}
    
    Returns:
        分区字典列表，每个字典包含partition_id、methods等
    """
    partition_dicts = []
    
    # 构建功能分区名到实体列表的映射
    function_to_entities = {}
    for entity_id, function_name in entity_to_function_map.items():
        if function_name not in function_to_entities:
            function_to_entities[function_name] = []
        function_to_entities[function_name].append(entity_id)
    
    # 提取方法签名（从method_开头的实体ID中提取）
    for i, func_partition in enumerate(function_partitions):
        function_name = func_partition.name
        entities = function_to_entities.get(function_name, [])
        
        # 提取方法签名（从method_ClassName.methodName格式中提取）
        methods = []
        for entity_id in entities:
            if entity_id.startswith('method_'):
                # 提取方法签名（去掉method_前缀）
                method_sig = entity_id[7:]  # 去掉"method_"前缀
                methods.append(method_sig)
            elif entity_id.startswith('function_'):
                # 提取函数名
                func_name = entity_id[9:]  # 去掉"function_"前缀
                methods.append(func_name)
        
        partition_dict = {
            "partition_id": f"partition_{i}",
            "name": function_name,
            "methods": methods,
            "size": len(methods)
        }
        partition_dicts.append(partition_dict)
    
    return partition_dicts


def generate_default_partitions(project_path):
    """
    基于项目文件结构自动生成功能分区
    扫描项目的文件夹结构，识别主要的功能模块
    """
    partitions = []
    
    # 扫描项目结构
    try:
        folder_names = set()
        for item in os.listdir(project_path):
            item_path = os.path.join(project_path, item)
            if os.path.isdir(item_path) and not item.startswith('.') and not item.startswith('__'):
                folder_names.add(item)
        
        print(f"[app.py]   - 检测到的文件夹: {', '.join(sorted(folder_names))}", flush=True)
        
        # 如果项目有明确的模块名，作为分区
        if folder_names:
            # 为每个主要文件夹创建一个分区
            for folder in sorted(folder_names):
                partition = FunctionPartition(
                    name=folder,
                    description=f"模块: {folder}",
                    folders=[folder],
                    keywords=[folder]
                )
                partitions.append(partition)
        
        # 如果没有明确的文件夹或文件夹太少，使用默认分区
        if len(partitions) < 2:
            print(f"[app.py]   - 文件夹结构不明确，使用智能默认分区", flush=True)
            
            # 基于项目名称和内容推荐分区
            project_name = os.path.basename(project_path)
            partitions = [
                FunctionPartition(
                    name="核心业务层",
                    description=f"{project_name} 的核心业务逻辑和主要功能",
                    folders=[],
                    keywords=['main', 'core', 'business', 'service']
                ),
                FunctionPartition(
                    name="工具辅助层",
                    description="提供工具函数和辅助功能的模块",
                    folders=[],
                    keywords=['util', 'helper', 'common', 'base']
                ),
                FunctionPartition(
                    name="外部接口层",
                    description="与外部系统交互的接口和API",
                    folders=[],
                    keywords=['api', 'interface', 'client', 'gateway']
                )
            ]
    
    except Exception as e:
        print(f"[app.py]   - ⚠️ 自动检测文件夹失败: {e}", flush=True)
        # 返回空列表让主程序使用更完整的默认分区
        partitions = []
    
    return partitions if partitions else []


def analyze_project(project_path):
    """后台分析项目 - 仅第3层代码图"""
    try:
        update_analysis_status(
            is_analyzing=True,
            error=None,
            progress=10,
            status='初始化分析器...'
        )
        
        print(f"\n{'='*60}", flush=True)
        print(f"[app.py] 🚀 开始分析项目: {project_path}", flush=True)
        print(f"{'='*60}", flush=True)
        
        # 初始化分析器
        print(f"[app.py] 初始化分析器...", flush=True)
        sys.stdout.flush()
        analyzer = CodeAnalyzer(project_path)
        print(f"[app.py] ✅ 分析器初始化完成", flush=True)
        sys.stdout.flush()
        
        # 更新进度：初始化完成，准备扫描项目
        update_analysis_status(
            progress=20,
            status='正在扫描项目...'
        )
        print(f"[app.py] 进度: 20% - 扫描项目文件...", flush=True)
        sys.stdout.flush()
        
        # 分析代码
        print(f"[app.py] 开始分析代码...", flush=True)
        sys.stdout.flush()
        graph_data = analyzer.analyze(project_path)
        
        # 保存report供后续API使用
        report = analyzer.report
        
        nodes_count = len(graph_data.get('nodes', []))
        edges_count = len(graph_data.get('edges', []))
        print(f"[app.py] ✅ 代码分析完成", flush=True)
        print(f"[app.py]   - 节点数: {nodes_count}", flush=True)
        print(f"[app.py]   - 边数: {edges_count}", flush=True)
        sys.stdout.flush()
        
        # 更新进度：代码分析完成，开始生成可视化数据
        update_analysis_status(
            progress=90,
            status='正在生成可视化数据...'
        )
        print(f"[app.py] 进度: 90% - 生成可视化数据...", flush=True)
        sys.stdout.flush()
        
        # 生成图形数据并完成分析
        update_analysis_status(
            progress=100,
            status='分析完成！',
            data=graph_data,
            report=report,  # 保存report
            is_analyzing=False
        )
        print(f"[app.py] 进度: 100% - 分析完成！", flush=True)
        print(f"[app.py] {'='*60}", flush=True)
        print(f"[app.py] ✅✅✅ 分析成功完成！", flush=True)
        print(f"[app.py] {'='*60}\n", flush=True)
        sys.stdout.flush()
        
    except Exception as e:
        print(f"\n[app.py] {'='*60}", flush=True)
        print(f"[app.py] ❌ 分析出错", flush=True)
        print(f"[app.py] 错误类型: {type(e).__name__}", flush=True)
        print(f"[app.py] 错误信息: {e}", flush=True)
        print(f"[app.py] {'='*60}", flush=True)
        import traceback
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        update_analysis_status(
            error=str(e),
            is_analyzing=False,
            progress=0,
            status='分析失败'
        )
        print(f"[app.py] {'='*60}\n", flush=True)
        sys.stdout.flush()


def analyze_hierarchy(project_path, use_llm=False):
    """后台分析项目四层层级结构"""
    try:
        update_analysis_status(
            is_analyzing=True,
            error=None,
            progress=5,
            status='初始化分析...'
        )
        
        print(f"\n{'='*60}", flush=True)
        print(f"[app.py] 🚀 开始构建四层嵌套可视化: {project_path}", flush=True)
        print(f"{'='*60}", flush=True)
        
        # ===== 步骤1：代码分析（第3层） =====
        update_analysis_status(progress=10, status='步骤1/5: 分析代码...')
        print(f"[app.py] 步骤1: 分析代码（构建第3层CodeGraph）...", flush=True)
        sys.stdout.flush()
        
        analyzer = CodeAnalyzer(project_path)
        graph_data = analyzer.analyze(project_path)
        print(f"[app.py] ✅ 代码分析完成", flush=True)
        sys.stdout.flush()
        
        # ===== 步骤2：提取代码注释和 README =====
        update_analysis_status(progress=20, status='步骤2/5: 提取代码注释和README...')
        print(f"[app.py] 步骤2: 提取代码注释和 README...", flush=True)
        sys.stdout.flush()
        
        # 提取代码注释
        from parsers.comment_extractor import CommentExtractor
        comments_summary = {}
        try:
            # 为每个 Python 文件提取注释
            python_files = []
            for root, dirs, files in os.walk(project_path):
                dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.venv', 'venv', 'node_modules']]
                for file in files:
                    if file.endswith('.py'):
                        python_files.append(os.path.join(root, file))
            
            print(f"[app.py]   提取 {len(python_files)} 个文件的注释...", flush=True)
            for file_path in python_files[:50]:  # 限制前50个文件，避免太慢
                try:
                    extractor = CommentExtractor(file_path)
                    comments = extractor.extract_all_comments()
                    # 保存关键注释（docstring）
                    for entity_id, docstring in comments.get('docstrings', {}).items():
                        comments_summary[entity_id] = {
                            'comments': [docstring],
                            'file': file_path
                        }
                except Exception as e:
                    pass  # 忽略单个文件的错误
            
            print(f"[app.py] ✅ 提取了 {len(comments_summary)} 个代码元素的注释", flush=True)
        except Exception as e:
            print(f"[app.py] ⚠️ 注释提取失败: {e}", flush=True)
            comments_summary = {}
        
        # ===== 步骤3：LLM理解项目（第1层） =====
        partitions = []
        # 现在默认使用 LLM（除非明确禁用）
        try:
            update_analysis_status(progress=30, status='步骤3/5: 🤖 LLM分析项目结构...')
            print(f"\n[app.py] 步骤3: 🤖 调用LLM分析项目结构（使用图知识库）...", flush=True)
            sys.stdout.flush()
            
            api_key = os.getenv('DEEPSEEK_API_KEY', 'sk-a7e7d7ee44594ac98c27d64a7496742f')
            base_url = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
            
            print(f"[app.py]   - API密钥: {api_key[:10]}...", flush=True)
            print(f"[app.py]   - 初始化LLM Agent...", flush=True)
            agent = CodeUnderstandingAgent(api_key=api_key, base_url=base_url)
            
            print(f"[app.py]   - 加载项目信息...", flush=True)
            project_info = agent.load_project(project_path)
            print(f"[app.py]   - ✓ 项目加载完成: {project_info['name']} ({project_info['files_count']} 个Python文件)", flush=True)
            
            print(f"[app.py]   - 🤖 开始调用LLM API（使用图知识库摘要）...", flush=True)
            sys.stdout.flush()
            
            # 传递图数据和注释摘要给 LLM
            partitions = agent.identify_function_partitions(
                project_info=project_info,
                graph_data=graph_data,  # 传递图数据用于生成图知识库摘要
                comments_summary=comments_summary  # 传递注释摘要
            )
            
            if partitions:
                print(f"[app.py] ✅ LLM分析成功！识别了 {len(partitions)} 个功能分区:", flush=True)
                for p in partitions:
                    print(f"[app.py]    ✓ {p.name}: {p.description[:40]}...", flush=True)
                    print(f"[app.py]       文件夹: {p.folders}", flush=True)
            else:
                print(f"[app.py] ⚠️ LLM返回了空的功能分区列表", flush=True)
            sys.stdout.flush()
                
        except Exception as e:
            print(f"[app.py] ❌ LLM分析失败!", flush=True)
            print(f"[app.py]    错误类型: {type(e).__name__}", flush=True)
            print(f"[app.py]    错误信息: {str(e)}", flush=True)
            import traceback
            print(f"[app.py]    完整堆栈:", flush=True)
            traceback.print_exc(file=sys.stdout)
            sys.stdout.flush()
            partitions = []
        
        # 如果LLM失败，使用启发式规则（不再使用写死的默认分区）
        if not partitions:
            print(f"\n[app.py] 🔄 LLM失败，使用启发式规则识别功能分区...", flush=True)
            try:
                # 使用 Agent 的启发式方法
                agent = CodeUnderstandingAgent(api_key='', base_url='')
                agent.project_path = project_path
                agent.readme_content = agent._load_readme()
                partitions = agent._identify_partitions_heuristic()
                if partitions:
                    print(f"[app.py] ✅ 启发式规则识别了 {len(partitions)} 个功能分区", flush=True)
            except Exception as e:
                print(f"[app.py] ⚠️ 启发式规则也失败: {e}", flush=True)
                partitions = []
        
        # 最后的 fallback：基于文件夹结构
        if not partitions:
            print(f"[app.py] 🔄 使用文件夹结构生成功能分区...", flush=True)
            partitions = generate_default_partitions(project_path)
            if partitions:
                print(f"[app.py] ✅ 生成了 {len(partitions)} 个功能分区", flush=True)
            sys.stdout.flush()
        
        # ===== 步骤4：构建层级模型 =====
        update_analysis_status(progress=50, status='步骤4/5: 构建层级模型...')
        print(f"[app.py] 步骤3: 构建四层层级模型...", flush=True)
        sys.stdout.flush()
        
        from datetime import datetime
        metadata = HierarchyMetadata(
            project_name=os.path.basename(project_path),
            project_path=project_path,
            analysis_timestamp=datetime.now().isoformat(),
            total_files=graph_data['metadata'].get('total_files', 0),
            total_functions_in_partition=len(partitions)
        )
        hierarchy = HierarchyModel(metadata=metadata)
        
        # 填充第3层：将 graph_data 转换为 CodeGraph
        from analysis.hierarchy_model import GraphEdge, RelationType
        
        # 转换节点：从 Cytoscape.js 格式转换为字典
        nodes_dict = {}
        for node in graph_data.get('nodes', []):
            node_data = node.get('data', {})
            node_id = node_data.get('id')
            if node_id:
                nodes_dict[node_id] = node_data
        
        # 转换边：从 Cytoscape.js 格式转换为 GraphEdge 对象
        edges_list = []
        relation_type_map = {
            'calls': RelationType.CALLS,
            'inherits': RelationType.INHERITS,
            'accesses': RelationType.ACCESSES,
            'contains': RelationType.CONTAINS,
            'cross_file_call': RelationType.CROSS_FILE_CALL,
            'parameter_flow': RelationType.PARAMETER_FLOW,
        }
        
        for edge in graph_data.get('edges', []):
            edge_data = edge.get('data', {})
            source_id = edge_data.get('source')
            target_id = edge_data.get('target')
            relation_str = edge_data.get('relation') or edge_data.get('type', 'calls')
            
            # 将字符串关系类型转换为 RelationType 枚举
            relation_type = relation_type_map.get(relation_str, RelationType.CALLS)
            
            graph_edge = GraphEdge(
                source_id=source_id,
                target_id=target_id,
                relation=relation_type,
                weight=edge_data.get('weight', 1),
                source_file=edge_data.get('caller_file', ''),
                target_file=edge_data.get('callee_file', ''),
                metadata=edge_data
            )
            edges_list.append(graph_edge)
        
        hierarchy.layer3_code_graph = CodeGraph(
            nodes=nodes_dict,
            edges=edges_list,
            total_nodes=len(graph_data.get('nodes', [])),
            total_edges=len(graph_data.get('edges', [])),
            total_classes=graph_data['metadata'].get('total_classes', 0),
            total_methods=graph_data['metadata'].get('total_methods', 0),
            total_functions=graph_data['metadata'].get('total_functions', 0),
        )
        
        # 填充第1层
        for partition in partitions:
            hierarchy.layer1_functions.append(partition)
            hierarchy.layer1_functions_map[partition.name] = partition
        
        # 填充第2层：基于功能分区和项目文件夹自动映射（使用绝对路径）
        print(f"[app.py] 构建第2层：文件夹层（使用绝对路径）...", flush=True)
        folders = generate_folder_nodes(project_path, partitions)
        
        # 如果功能分区指定了文件夹（绝对路径），使用指定的
        # 否则扫描项目文件夹
        if not folders:
            # 从功能分区的 folders 列表创建文件夹节点
            for partition in partitions:
                for folder_path in partition.folders:
                    # folder_path 可能是绝对路径或相对路径
                    if os.path.isabs(folder_path):
                        abs_folder_path = folder_path
                    else:
                        abs_folder_path = os.path.join(project_path, folder_path)
                    
                    if os.path.isdir(abs_folder_path):
                        # 统计该文件夹下的代码
                        class_count = 0
                        method_count = 0
                        for root, dirs, files in os.walk(abs_folder_path):
                            for file in files:
                                if file.endswith('.py'):
                                    # 简单统计（可以优化）
                                    class_count += 1
                        
                        folder_node = FolderNode(
                            folder_path=abs_folder_path,  # 使用绝对路径
                            parent_function=partition.name,
                            stats=FolderStats(class_count=class_count, method_count=method_count)
                        )
                        folders.append(folder_node)
        
        for folder in folders:
            hierarchy.layer2_folders.append(folder)
            hierarchy.layer2_folders_map[folder.folder_path] = folder
        print(f"[app.py] ✅ 生成了 {len(folders)} 个文件夹节点（绝对路径）", flush=True)
        for f in folders:
            print(f"[app.py]    - {f.folder_path}", flush=True)
        sys.stdout.flush()
        
        print(f"[app.py] ✅ 层级模型构建完成", flush=True)
        sys.stdout.flush()
        
        # ===== 步骤5：计算真实的聚合关系 =====
        update_analysis_status(progress=70, status='步骤5/5: 计算聚合关系...')
        print(f"[app.py] 步骤5: 从第3层计算真实的聚合关系...", flush=True)
        sys.stdout.flush()
        
        # 建立代码元素到各层的映射
        hierarchy.entity_to_function_map = {}
        hierarchy.entity_to_folder_map = {}
        hierarchy.layer1_entity_pairs = {}  # 保存第1层的实体对信息
        hierarchy.layer2_entity_pairs = {}  # 保存第2层的实体对信息
        
        # 根据节点的文件位置映射到功能分区和文件夹（使用绝对路径匹配）
        for node_id, node_data in nodes_dict.items():
            file_path = node_data.get('file', '')
            if file_path:
                # 转换为绝对路径
                if not os.path.isabs(file_path):
                    file_path = os.path.join(project_path, file_path)
                file_path = os.path.normpath(file_path)
                
                # 映射到功能分区（检查文件夹路径是否在文件路径中）
                for partition in partitions:
                    for partition_folder in partition.folders:
                        # 处理绝对路径和相对路径
                        if os.path.isabs(partition_folder):
                            abs_partition_folder = os.path.normpath(partition_folder)
                        else:
                            abs_partition_folder = os.path.normpath(os.path.join(project_path, partition_folder))
                        
                        if abs_partition_folder in file_path or file_path.startswith(abs_partition_folder):
                            hierarchy.entity_to_function_map[node_id] = partition.name
                            break
                    if node_id in hierarchy.entity_to_function_map:
                        break
                
                # 映射到文件夹（使用绝对路径）
                for folder in folders:
                    folder_abs_path = os.path.normpath(folder.folder_path)
                    if folder_abs_path in file_path or file_path.startswith(folder_abs_path):
                        hierarchy.entity_to_folder_map[node_id] = folder.folder_path
                        break
        
        # 计算第1层的聚合边：功能分区之间的调用关系（保存实体对信息）
        layer1_relations = {}  # {(source_partition, target_partition): {'count': int, 'entity_pairs': List}}
        for edge in edges_list:
            source_partition = hierarchy.entity_to_function_map.get(edge.source_id)
            target_partition = hierarchy.entity_to_function_map.get(edge.target_id)
            
            if source_partition and target_partition and source_partition != target_partition:
                key = (source_partition, target_partition)
                if key not in layer1_relations:
                    layer1_relations[key] = {'count': 0, 'entity_pairs': []}
                layer1_relations[key]['count'] += 1
                # 保存实体对（最多保存前20对，避免数据过大）
                if len(layer1_relations[key]['entity_pairs']) < 20:
                    layer1_relations[key]['entity_pairs'].append((edge.source_id, edge.target_id))
        
        # 计算第2层的聚合边：文件夹之间的调用关系（保存实体对信息）
        layer2_relations = {}  # {(source_folder, target_folder): {'count': int, 'entity_pairs': List}}
        for edge in edges_list:
            source_folder = hierarchy.entity_to_folder_map.get(edge.source_id)
            target_folder = hierarchy.entity_to_folder_map.get(edge.target_id)
            
            if source_folder and target_folder and source_folder != target_folder:
                key = (source_folder, target_folder)
                if key not in layer2_relations:
                    layer2_relations[key] = {'count': 0, 'entity_pairs': []}
                layer2_relations[key]['count'] += 1
                # 保存实体对（最多保存前20对）
                if len(layer2_relations[key]['entity_pairs']) < 20:
                    layer2_relations[key]['entity_pairs'].append((edge.source_id, edge.target_id))
        
        # 设置功能分区的出度/入度
        for partition in hierarchy.layer1_functions:
            partition.outgoing_calls = {}
            partition.incoming_calls = {}
        
        for (src, dst), relation_data in layer1_relations.items():
            count = relation_data['count']
            entity_pairs = relation_data.get('entity_pairs', [])
            
            src_partition = next((p for p in hierarchy.layer1_functions if p.name == src), None)
            dst_partition = next((p for p in hierarchy.layer1_functions if p.name == dst), None)
            if src_partition and dst_partition:
                if dst not in src_partition.outgoing_calls:
                    src_partition.outgoing_calls[dst] = 0
                src_partition.outgoing_calls[dst] += count
                
                if src not in dst_partition.incoming_calls:
                    dst_partition.incoming_calls[src] = 0
                dst_partition.incoming_calls[src] += count
                
                # 保存实体对信息到 function_relations（用于展开时重建边）
                from analysis.hierarchy_model import FunctionRelation
                func_relation = FunctionRelation(
                    source_function=src,
                    target_function=dst,
                    call_count=count,
                    call_density=count / max(src_partition.stats.total_methods, 1),
                    critical_path_count=0
                )
                # FunctionRelation 没有 metadata 字段，但我们可以通过其他方式保存
                # 暂时先保存到 function_relations，后续可以通过 call_count 和 source/target 重建
                src_partition.function_relations.append(func_relation)
                
                # 将 entity_pairs 保存到 hierarchy 的映射中（用于展开时重建）
                key = f"{src}->{dst}"
                if key not in hierarchy.layer1_entity_pairs:
                    hierarchy.layer1_entity_pairs[key] = []
                hierarchy.layer1_entity_pairs[key].extend(entity_pairs[:20])  # 最多保存20对
        
        # 设置文件夹的出度/入度
        for folder in hierarchy.layer2_folders:
            folder.outgoing_calls = {}
            folder.incoming_calls = {}
        
        for (src, dst), relation_data in layer2_relations.items():
            count = relation_data['count']
            entity_pairs = relation_data.get('entity_pairs', [])
            
            src_folder = next((f for f in hierarchy.layer2_folders if f.folder_path == src), None)
            dst_folder = next((f for f in hierarchy.layer2_folders if f.folder_path == dst), None)
            if src_folder and dst_folder:
                if dst not in src_folder.outgoing_calls:
                    src_folder.outgoing_calls[dst] = 0
                src_folder.outgoing_calls[dst] += count
                
                if src not in dst_folder.incoming_calls:
                    dst_folder.incoming_calls[src] = 0
                dst_folder.incoming_calls[src] += count
                
                # 保存实体对信息到 folder_relations（用于展开时重建边）
                from analysis.hierarchy_model import FolderRelation
                folder_relation = FolderRelation(
                    source_folder=src,
                    target_folder=dst,
                    call_count=count,
                    entity_pairs=entity_pairs[:20]  # 最多保存20对
                )
                src_folder.folder_relations.append(folder_relation)
                
                # 同时保存到 hierarchy 的映射中
                key = f"{src}->{dst}"
                if key not in hierarchy.layer2_entity_pairs:
                    hierarchy.layer2_entity_pairs[key] = []
                hierarchy.layer2_entity_pairs[key].extend(entity_pairs[:20])
        
        print(f"[app.py] ✅ 聚合关系计算完成:", flush=True)
        print(f"[app.py]   - 第1层关系数: {len(layer1_relations)}", flush=True)
        print(f"[app.py]   - 第2层关系数: {len(layer2_relations)}", flush=True)
        sys.stdout.flush()
        
        apply_aggregations_to_hierarchy(hierarchy)
        print(f"[app.py] ✅ 聚合计算完成", flush=True)
        sys.stdout.flush()
        
        # ===== 步骤6：阶段4分析 - 功能级分析生成 =====
        update_analysis_status(progress=75, status='步骤6/7: 生成功能级分析...')
        print(f"[app.py] 步骤6: 生成功能级分析（调用图、超图、入口点、数据流图、控制流图）...", flush=True)
        sys.stdout.flush()
        
        # 保存阶段4分析结果
        partition_analyses = {}
        
        try:
            # 获取调用图
            call_graph = analyzer.call_graph_analyzer.call_graph
            
            # 将FunctionPartition转换为字典格式（供阶段4使用）
            partition_dicts = _convert_partitions_to_dicts(hierarchy.layer1_functions, hierarchy.entity_to_function_map)
            
            if partition_dicts and call_graph:
                # 阶段4.1: 函数调用图生成
                print(f"[app.py]   阶段4.1: 生成函数调用图...", flush=True)
                call_graph_generator = FunctionCallGraphGenerator(call_graph)
                for partition_dict in partition_dicts:
                    try:
                        partition_call_graph = call_graph_generator.generate_partition_call_graph(partition_dict)
                        partition_id = partition_dict.get("partition_id", "unknown")
                        if partition_id not in partition_analyses:
                            partition_analyses[partition_id] = {}
                        partition_analyses[partition_id]['call_graph'] = partition_call_graph
                    except Exception as e:
                        print(f"[app.py]     ⚠️ 分区 {partition_dict.get('partition_id')} 调用图生成失败: {e}", flush=True)
                
                # 阶段4.2: 函数调用超图生成
                print(f"[app.py]   阶段4.2: 生成函数调用超图...", flush=True)
                hypergraph_generator = FunctionCallHypergraphGenerator(call_graph)
                for partition_dict in partition_dicts:
                    try:
                        partition_hypergraph = hypergraph_generator.generate_partition_hypergraph(partition_dict)
                        partition_id = partition_dict.get("partition_id", "unknown")
                        if partition_id not in partition_analyses:
                            partition_analyses[partition_id] = {}
                        partition_analyses[partition_id]['hypergraph'] = partition_hypergraph.to_dict()
                    except Exception as e:
                        print(f"[app.py]     ⚠️ 分区 {partition_dict.get('partition_id')} 超图生成失败: {e}", flush=True)
                
                # 阶段4.3: 入口点识别
                print(f"[app.py]   阶段4.3: 识别入口点...", flush=True)
                entry_point_generator = EntryPointIdentifierGenerator(call_graph, analyzer.report)
                entry_points_dict = entry_point_generator.identify_all_partitions_entry_points(partition_dicts)
                for partition_id, entry_points in entry_points_dict.items():
                    if partition_id not in partition_analyses:
                        partition_analyses[partition_id] = {}
                    partition_analyses[partition_id]['entry_points'] = [
                        {
                            'method_signature': ep.method_signature,
                            'score': ep.score,
                            'reasons': ep.reasons
                        }
                        for ep in entry_points
                    ]
                
                # 阶段4.4: 功能级数据流图生成
                print(f"[app.py]   阶段4.4: 生成数据流图...", flush=True)
                dataflow_generator = PartitionDataFlowGenerator(
                    call_graph, 
                    analyzer.report,
                    analyzer.data_flow_analyzer if hasattr(analyzer, 'data_flow_analyzer') else None
                )
                for partition_dict in partition_dicts:
                    try:
                        partition_dataflow = dataflow_generator.generate_partition_data_flow(partition_dict)
                        partition_id = partition_dict.get("partition_id", "unknown")
                        if partition_id not in partition_analyses:
                            partition_analyses[partition_id] = {}
                        partition_analyses[partition_id]['dataflow'] = {
                            'nodes': partition_dataflow.nodes,
                            'edges': partition_dataflow.edges,
                            'parameter_flows': partition_dataflow.parameter_flows,
                            'return_flows': partition_dataflow.return_flows,
                            'shared_states': partition_dataflow.shared_states
                        }
                    except Exception as e:
                        print(f"[app.py]     ⚠️ 分区 {partition_dict.get('partition_id')} 数据流图生成失败: {e}", flush=True)
                
                # 阶段4.5: 功能级控制流图生成
                print(f"[app.py]   阶段4.5: 生成控制流图...", flush=True)
                controlflow_generator = PartitionControlFlowGenerator(call_graph, analyzer.report)
                for partition_dict in partition_dicts:
                    try:
                        partition_controlflow = controlflow_generator.generate_partition_control_flow(partition_dict)
                        partition_id = partition_dict.get("partition_id", "unknown")
                        if partition_id not in partition_analyses:
                            partition_analyses[partition_id] = {}
                        partition_analyses[partition_id]['controlflow'] = {
                            'nodes': partition_controlflow.nodes,
                            'edges': partition_controlflow.edges,
                            'method_call_edges': partition_controlflow.method_call_edges,
                            'cycles': partition_controlflow.cycles,
                            'dot': partition_controlflow.to_dot()
                        }
                    except Exception as e:
                        print(f"[app.py]     ⚠️ 分区 {partition_dict.get('partition_id')} 控制流图生成失败: {e}", flush=True)
            
            print(f"[app.py] ✅ 阶段4分析完成，为 {len(partition_analyses)} 个分区生成了分析结果", flush=True)
        except Exception as e:
            print(f"[app.py] ⚠️ 阶段4分析失败: {e}", flush=True)
            import traceback
            traceback.print_exc(file=sys.stdout)
            partition_analyses = {}
        
        sys.stdout.flush()
        
        # ===== 步骤7：保存并返回 =====
        update_analysis_status(progress=90, status='步骤7/7: 准备返回数据...')
        print(f"[app.py] 步骤5: 准备返回数据...", flush=True)
        sys.stdout.flush()
        
        hierarchy_data = hierarchy.to_dict()
        
        # 构建前端需要的数据格式
        result_data = {
            'hierarchy': {
                'layer1_functions': [],
                'layer2_folders': [],
                'metadata': hierarchy_data.get('metadata', {}),
                'entity_pairs': {
                    'layer1': hierarchy.layer1_entity_pairs if hasattr(hierarchy, 'layer1_entity_pairs') else {},
                    'layer2': hierarchy.layer2_entity_pairs if hasattr(hierarchy, 'layer2_entity_pairs') else {}
                }
            },
            'original_graph': graph_data,
            'partition_analyses': partition_analyses  # 阶段4分析结果
        }
        
        # 填充第1层：功能分区
        print(f"[app.py] 填充第1层数据...", flush=True)
        print(f"[app.py] 功能分区总数: {len(hierarchy.layer1_functions)}", flush=True)
        for i, func in enumerate(hierarchy.layer1_functions):
            # 确保 stats 属性存在
            if not hasattr(func, 'stats') or func.stats is None:
                from analysis.hierarchy_model import FunctionStats
                func.stats = FunctionStats()
            
            func_data = {
                'name': func.name,
                'description': func.description,
                'folders': func.folders,
                'partition_id': f"partition_{i}",  # 添加partition_id用于前端查询
                'outgoing_calls': func.outgoing_calls if hasattr(func, 'outgoing_calls') else {},
                'incoming_calls': func.incoming_calls if hasattr(func, 'incoming_calls') else {},
                'stats': {
                    'total_classes': func.stats.total_classes if hasattr(func.stats, 'total_classes') else 0
                },
                'function_relations': [
                    {
                        'source': fr.source_function,
                        'target': fr.target_function,
                        'call_count': fr.call_count,
                        'call_density': fr.call_density
                    }
                    for fr in func.function_relations
                ]
            }
            print(f"[app.py]   - 添加功能分区: {func.name}, outgoing_calls: {func_data['outgoing_calls']}", flush=True)
            result_data['hierarchy']['layer1_functions'].append(func_data)
        
        # 填充第2层：文件夹
        print(f"[app.py] 填充第2层数据...", flush=True)
        print(f"[app.py] 文件夹总数: {len(hierarchy.layer2_folders)}", flush=True)
        for folder in hierarchy.layer2_folders:
            folder_data = {
                'folder_path': folder.folder_path,  # 绝对路径
                'parent_function': folder.parent_function,
                'outgoing_calls': folder.outgoing_calls if hasattr(folder, 'outgoing_calls') else {},
                'stats': {
                    'total_code_elements': 0,
                    'class_count': folder.stats.class_count if hasattr(folder.stats, 'class_count') else 0,
                    'method_count': folder.stats.method_count if hasattr(folder.stats, 'method_count') else 0
                },
                'folder_relations': [
                    {
                        'source': fr.source_folder,
                        'target': fr.target_folder,
                        'call_count': fr.call_count,
                        'entity_pairs': fr.entity_pairs  # 保存实体对，用于展开时重建边
                    }
                    for fr in folder.folder_relations
                ]
            }
            print(f"[app.py]   - 添加文件夹: {folder.folder_path}, outgoing_calls: {folder_data['outgoing_calls']}", flush=True)
            result_data['hierarchy']['layer2_folders'].append(folder_data)
        
        update_analysis_status(
            progress=100,
            status='四层分析完成！',
            data=result_data,
            is_analyzing=False
        )
        
        print(f"[app.py] {'='*60}", flush=True)
        print(f"[app.py] ✅✅✅ 四层嵌套可视化分析完成！", flush=True)
        print(f"[app.py] {'='*60}\n", flush=True)
        sys.stdout.flush()
        
    except Exception as e:
        print(f"\n[app.py] {'='*60}", flush=True)
        print(f"[app.py] ❌ 四层分析出错: {e}", flush=True)
        print(f"[app.py] {'='*60}", flush=True)
        import traceback
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        update_analysis_status(
            error=str(e),
            is_analyzing=False,
            progress=0,
            status='分析失败'
        )
        print(f"[app.py] {'='*60}\n", flush=True)
        sys.stdout.flush()


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/hierarchy')
def hierarchy_view():
    """四层嵌套可视化分析页面"""
    return render_template('index_hierarchy.html')


@app.route('/function_hierarchy')
def function_hierarchy_view():
    """功能层级分析页面"""
    return render_template('function_hierarchy.html')




@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """开始分析API"""
    data = request.json
    project_path = data.get('project_path')
    
    # 如果是临时路径或无效路径，使用当前项目目录作为示例
    if not project_path or not os.path.isdir(project_path) or 'tmp' in project_path:
        project_path = os.path.dirname(os.path.abspath(__file__))
    
    # 重置状态（线程安全）
    update_analysis_status(
        progress=0,
        status='分析中...',
        data=None,
        error=None
    )
    
    # 后台分析
    thread = threading.Thread(target=analyze_project, args=(project_path,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': '分析已开始'})


def convert_sets_to_lists(obj):
    """递归地将所有set类型转换为list，以便JSON序列化"""
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {key: convert_sets_to_lists(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_sets_to_lists(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        # 处理dataclass对象
        return {key: convert_sets_to_lists(value) for key, value in obj.__dict__.items()}
    else:
        return obj


@app.route('/api/status', methods=['GET'])
def api_status():
    """获取分析状态"""
    # 使用锁读取，避免读取到中间状态
    with status_lock:
        status_copy = dict(analysis_status)
        # 转换set为list以便JSON序列化
        # 注意：report对象可能包含set，但我们只序列化基本状态信息
        serializable_status = {
            'progress': status_copy.get('progress', 0),
            'status': status_copy.get('status', '等待中...'),
            'is_analyzing': status_copy.get('is_analyzing', False),
            'error': status_copy.get('error'),
            'data': status_copy.get('data')  # data已经是字典格式，应该可以序列化
        }
    return jsonify(serializable_status)


@app.route('/api/analyze_hierarchy', methods=['POST'])
def api_analyze_hierarchy():
    """开始四层嵌套可视化分析API"""
    data = request.json or {}
    project_path = data.get('project_path')
    use_llm = data.get('use_llm', False)
    
    # 如果是临时路径或无效路径，使用当前项目目录
    if not project_path or not os.path.isdir(project_path) or 'tmp' in project_path:
        project_path = os.path.dirname(os.path.abspath(__file__))
    
    # 重置状态
    update_analysis_status(
        progress=0,
        status='分析中...',
        data=None,
        error=None
    )
    
    # 后台分析
    thread = threading.Thread(target=analyze_hierarchy, args=(project_path, use_llm))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': '四层分析已开始'})


def analyze_function_hierarchy(project_path):
    """后台分析项目功能层级（使用社区检测）"""
    try:
        update_analysis_status(
            is_analyzing=True,
            error=None,
            progress=5,
            status='初始化分析...'
        )
        
        print(f"\n{'='*60}", flush=True)
        print(f"[app.py] 🚀 开始功能层级分析: {project_path}", flush=True)
        print(f"{'='*60}", flush=True)
        
        # ===== 步骤1：代码分析获取调用图 =====
        update_analysis_status(progress=10, status='步骤1/6: 分析代码获取调用图...')
        print(f"[app.py] 步骤1: 分析代码获取调用图...", flush=True)
        sys.stdout.flush()
        
        analyzer = CodeAnalyzer(project_path)
        graph_data = analyzer.analyze(project_path)
        
        if not hasattr(analyzer, 'call_graph_analyzer'):
            raise Exception('未找到call_graph_analyzer')
        
        call_graph = analyzer.call_graph_analyzer.call_graph
        print(f"[app.py] ✅ 获取调用图: {len(call_graph)} 个方法", flush=True)
        sys.stdout.flush()
        
        # ===== 步骤2：社区检测获取功能分区 =====
        update_analysis_status(progress=30, status='步骤2/7: 社区检测获取功能分区...')
        print(f"[app.py] 步骤2: 社区检测获取功能分区...", flush=True)
        sys.stdout.flush()
        
        detector = CommunityDetector()
        partitions = detector.detect_communities(call_graph, algorithm="louvain")
        print(f"[app.py] ✅ 检测到 {len(partitions)} 个功能分区", flush=True)
        sys.stdout.flush()
        
        # 按方法数量排序
        partitions.sort(key=lambda p: len(p.get("methods", [])), reverse=True)
        
        # ===== 步骤2.5：使用LLM增强分区信息 =====
        update_analysis_status(progress=35, status='步骤2.5/7: 使用LLM增强分区信息...')
        print(f"[app.py] 步骤2.5: 使用LLM为分区生成有意义的名字、描述和关键文件夹...", flush=True)
        sys.stdout.flush()
        
        try:
            api_key = os.getenv('DEEPSEEK_API_KEY', 'sk-a7e7d7ee44594ac98c27d64a7496742f')
            base_url = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
            agent = CodeUnderstandingAgent(api_key=api_key, base_url=base_url)
            agent.project_path = project_path
            
            enhanced_partitions = []
            for partition in partitions:
                enhanced_partition = agent.enhance_partition_with_llm(
                    partition.copy(),
                    analyzer.report,
                    project_path
                )
                enhanced_partitions.append(enhanced_partition)
            
            partitions = enhanced_partitions
            print(f"[app.py] ✅ LLM增强完成，为 {len(partitions)} 个分区生成了有意义的名字和描述", flush=True)
            for p in partitions:
                print(f"[app.py]   - {p.get('name', 'unknown')}: {p.get('description', '')[:50]}...", flush=True)
        except Exception as e:
            print(f"[app.py] ⚠️ LLM增强失败: {e}，使用默认分区信息", flush=True)
            import traceback
            traceback.print_exc(file=sys.stdout)
            # 继续使用原始分区
        
        # ===== 步骤2.6：去重和名称冲突处理 =====
        update_analysis_status(progress=37, status='步骤2.6/7: 去重和名称冲突处理...')
        print(f"[app.py] 步骤2.6: 去重和名称冲突处理...", flush=True)
        sys.stdout.flush()
        
        partitions = deduplicate_and_resolve_name_conflicts(partitions)
        
        # ===== 步骤3：生成调用图 =====
        update_analysis_status(progress=40, status='步骤3/7: 生成调用图...')
        print(f"[app.py] 步骤3: 生成调用图...", flush=True)
        sys.stdout.flush()
        
        call_graph_generator = FunctionCallGraphGenerator(call_graph)
        partition_analyses = {}
        
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            try:
                call_graph_result = call_graph_generator.generate_partition_call_graph(partition)
                if partition_id not in partition_analyses:
                    partition_analyses[partition_id] = {}
                partition_analyses[partition_id]['call_graph'] = call_graph_result
                print(f"[app.py]   ✓ 分区 {partition_id} 调用图生成成功", flush=True)
            except Exception as e:
                print(f"[app.py]   ⚠️ 分区 {partition_id} 调用图生成失败: {e}", flush=True)
                import traceback
                traceback.print_exc(file=sys.stdout)
        
        print(f"[app.py] ✅ 调用图生成完成，共 {len(partition_analyses)} 个分区", flush=True)
        sys.stdout.flush()
        
        # ===== 步骤4：生成超图 =====
        update_analysis_status(progress=50, status='步骤4/7: 生成超图...')
        print(f"[app.py] 步骤4: 生成超图...", flush=True)
        sys.stdout.flush()
        
        hypergraph_generator = FunctionCallHypergraphGenerator(call_graph)
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            try:
                hypergraph = hypergraph_generator.generate_partition_hypergraph(partition)
                if partition_id not in partition_analyses:
                    partition_analyses[partition_id] = {}
                # 保存超图的完整信息
                hypergraph_dict = hypergraph.to_dict()
                partition_analyses[partition_id]['hypergraph'] = hypergraph_dict
                # 同时保存可视化数据
                partition_analyses[partition_id]['hypergraph_viz'] = hypergraph.to_visualization_data()
                print(f"[app.py]   ✓ 分区 {partition_id} 超图生成成功: {len(hypergraph.hyperedges)} 条超边", flush=True)
            except Exception as e:
                print(f"[app.py]   ⚠️ 分区 {partition_id} 超图生成失败: {e}", flush=True)
                import traceback
                traceback.print_exc(file=sys.stdout)
        
        print(f"[app.py] ✅ 超图生成完成", flush=True)
        sys.stdout.flush()
        
        # ===== 步骤5：识别入口点 =====
        update_analysis_status(progress=60, status='步骤5/7: 识别入口点...')
        print(f"[app.py] 步骤5: 识别入口点...", flush=True)
        sys.stdout.flush()
        
        entry_point_generator = EntryPointIdentifierGenerator(call_graph, analyzer.report, None)
        entry_points_map = entry_point_generator.identify_all_partitions_entry_points(partitions, score_threshold=0.3)
        
        for partition_id, entry_points in entry_points_map.items():
            if partition_id not in partition_analyses:
                partition_analyses[partition_id] = {}
            partition_analyses[partition_id]['entry_points'] = [
                {
                    'method_signature': ep.method_sig,
                    'score': ep.score,
                    'reasons': ep.reasons
                }
                for ep in entry_points
            ]
        
        print(f"[app.py] ✅ 入口点识别完成", flush=True)
        sys.stdout.flush()
        
        # ===== 步骤6：生成数据流图和控制流图 =====
        update_analysis_status(progress=70, status='步骤6/7: 生成数据流图和控制流图...')
        print(f"[app.py] 步骤6: 生成数据流图和控制流图...", flush=True)
        sys.stdout.flush()
        
        dataflow_generator = PartitionDataFlowGenerator(
            call_graph,
            analyzer.report,
            analyzer.data_flow_analyzer if hasattr(analyzer, 'data_flow_analyzer') else None
        )
        controlflow_generator = PartitionControlFlowGenerator(call_graph, analyzer.report)
        
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            try:
                # 数据流图
                entry_points = entry_points_map.get(partition_id, [])
                partition_dataflow = dataflow_generator.generate_partition_data_flow(partition, entry_points)
                if partition_id not in partition_analyses:
                    partition_analyses[partition_id] = {}
                # 保存数据流图的完整信息
                partition_analyses[partition_id]['dataflow'] = {
                    'nodes': partition_dataflow.merged_nodes,  # 字典格式
                    'edges': partition_dataflow.merged_edges,  # 列表格式
                    'parameter_flows': partition_dataflow.parameter_flows,
                    'return_flows': partition_dataflow.return_value_flows,
                    'shared_states': list(partition_dataflow.shared_states),
                    'viz_data': partition_dataflow.to_visualization_data()  # 可视化数据
                }
                print(f"[app.py]   ✓ 分区 {partition_id} 数据流图生成成功: {len(partition_dataflow.merged_nodes)} 个节点, {len(partition_dataflow.merged_edges)} 条边", flush=True)
                
                # 控制流图
                partition_controlflow = controlflow_generator.generate_partition_control_flow(partition)
                # 转换节点为字典格式
                nodes_dict = {}
                for node_id, node in partition_controlflow.merged_nodes.items():
                    nodes_dict[node_id] = {
                        'id': node.node_id,
                        'label': node.label,
                        'type': node.node_type,
                        'line_number': node.line_number,
                        'code': node.code[:200] if node.code else "",
                        'metadata': node.metadata if hasattr(node, 'metadata') else {}
                    }
                # 转换边为字典格式
                edges_list = []
                for edge in partition_controlflow.merged_edges:
                    edge_dict = {
                        'source': edge.source_id,
                        'target': edge.target_id,
                        'type': edge.edge_type
                    }
                    if hasattr(edge, 'metadata') and edge.metadata:
                        edge_dict['metadata'] = edge.metadata
                    edges_list.append(edge_dict)
                
                partition_analyses[partition_id]['controlflow'] = {
                    'nodes': nodes_dict,
                    'edges': edges_list,
                    'method_call_edges': partition_controlflow.method_call_edges,
                    'cycles': partition_controlflow.cycles,
                    'dot': partition_controlflow.to_dot(),
                    'viz_data': partition_controlflow.to_visualization_data()  # 可视化数据
                }
                print(f"[app.py]   ✓ 分区 {partition_id} 控制流图生成成功: {len(nodes_dict)} 个节点, {len(edges_list)} 条边", flush=True)
            except Exception as e:
                print(f"[app.py]   ⚠️ 分区 {partition_id} 数据流/控制流图生成失败: {e}", flush=True)
                import traceback
                traceback.print_exc(file=sys.stdout)
        
        print(f"[app.py] ✅ 数据流图和控制流图生成完成", flush=True)
        sys.stdout.flush()
        
        # ===== 构建返回数据 =====
        update_analysis_status(progress=90, status='准备返回数据...')
        print(f"[app.py] 准备返回数据...", flush=True)
        sys.stdout.flush()
        
        # 构建功能分区列表
        function_partitions = []
        for i, partition in enumerate(partitions):
            partition_id = partition.get("partition_id", f"partition_{i}")
            methods = partition.get("methods", [])
            
            # 计算出度和入度
            outgoing_calls = {}
            incoming_calls = {}
            
            # 从调用图统计出度和入度
            for method_sig in methods:
                if method_sig in call_graph:
                    # 统计出度（调用其他分区的方法）
                    # call_graph[method_sig] 是一个 Set[str]，直接遍历
                    for callee in call_graph[method_sig]:
                        # 找到callee所属的分区
                        for other_partition in partitions:
                            if callee in other_partition.get("methods", []):
                                other_id = other_partition.get("partition_id", "unknown")
                                if other_id != partition_id:
                                    if other_id not in outgoing_calls:
                                        outgoing_calls[other_id] = 0
                                    outgoing_calls[other_id] += 1
                                break
                    
                    # 统计入度（被其他分区的方法调用）
                    # 需要遍历所有调用图找到调用当前方法的
                    for caller_sig, callees_set in call_graph.items():
                        if caller_sig not in methods:
                            if method_sig in callees_set:
                                # 找到caller所属的分区
                                for other_partition in partitions:
                                    if caller_sig in other_partition.get("methods", []):
                                        other_id = other_partition.get("partition_id", "unknown")
                                        if other_id != partition_id:
                                            if other_id not in incoming_calls:
                                                incoming_calls[other_id] = 0
                                            incoming_calls[other_id] += 1
                                        break
            
            # 统计类数量（从analyzer.report获取）
            class_names = set()
            for method_sig in methods:
                if "." in method_sig:
                    class_name = method_sig.rsplit(".", 1)[0]
                    if analyzer.report and class_name in analyzer.report.classes:
                        class_names.add(class_name)
            
            # 使用LLM增强后的信息
            partition_name = partition.get("name", partition_id)
            partition_description = partition.get("description", f"功能分区，包含 {len(methods)} 个方法")
            partition_folders = partition.get("folders", [])
            partition_keywords = partition.get("keywords", [])
            
            # 构建详细描述，包含统计信息
            detailed_description = partition_description
            if partition.get("name_conflict"):
                detailed_description += f" (注意：此分区与其他分区名称相同但内容不同)"
            
            function_partitions.append({
                'name': partition_name,
                'description': detailed_description,
                'partition_id': partition_id,
                'methods': methods,
                'method_count': len(methods),
                'modularity': partition.get("modularity", 0.0),
                'outgoing_calls': outgoing_calls,
                'incoming_calls': incoming_calls,
                'folders': partition_folders,
                'keywords': partition_keywords,
                'name_conflict': partition.get("name_conflict", False),  # 标记是否为名称冲突
                'original_name': partition.get("original_name", partition_name),  # 原始名称
                'stats': {
                    'total_classes': len(class_names),  # 准确统计类数量
                    'total_methods': len(methods),
                    'total_functions': 0  # 可以从analyzer.report进一步统计
                }
            })
        
        result_data = {
            'hierarchy': {
                'layer1_functions': function_partitions,
                'metadata': {
                    'project_path': project_path,
                    'total_partitions': len(partitions),
                    'total_methods': len(call_graph)
                }
            },
            'partition_analyses': partition_analyses
        }
        
        update_analysis_status(
            progress=100,
            status='功能层级分析完成！',
            data=result_data,
            is_analyzing=False
        )
        
        print(f"[app.py] {'='*60}", flush=True)
        print(f"[app.py] ✅✅✅ 功能层级分析完成！", flush=True)
        print(f"[app.py] {'='*60}\n", flush=True)
        sys.stdout.flush()
        
    except Exception as e:
        print(f"\n[app.py] {'='*60}", flush=True)
        print(f"[app.py] ❌ 功能层级分析出错: {e}", flush=True)
        print(f"[app.py] {'='*60}", flush=True)
        import traceback
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        update_analysis_status(
            error=str(e),
            is_analyzing=False,
            progress=0,
            status='分析失败'
        )
        print(f"[app.py] {'='*60}\n", flush=True)
        sys.stdout.flush()


@app.route('/api/analyze_function_hierarchy', methods=['POST'])
def api_analyze_function_hierarchy():
    """开始功能层级分析API（使用社区检测）"""
    data = request.json or {}
    project_path = data.get('project_path')
    
    # 验证路径：如果路径无效或不存在，使用当前项目目录
    if not project_path or not os.path.isdir(project_path):
        project_path = os.path.dirname(os.path.abspath(__file__))
        print(f"[api_analyze_function_hierarchy] ⚠️ 路径无效，使用默认路径: {project_path}", flush=True)
    else:
        print(f"[api_analyze_function_hierarchy] ✅ 使用指定路径: {project_path}", flush=True)
    
    # 重置状态
    update_analysis_status(
        progress=0,
        status='分析中...',
        data=None,
        error=None
    )
    
    # 后台分析（使用新的analyze_function_hierarchy函数）
    thread = threading.Thread(target=analyze_function_hierarchy, args=(project_path,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': '功能层级分析已开始'})


@app.route('/api/result', methods=['GET'])
def api_result():
    """获取分析结果"""
    if analysis_status['data']:
        return jsonify(analysis_status['data'])
    return jsonify({'error': '暂无结果'}), 400


@app.route('/api/knowledge_graph', methods=['GET'])
def api_knowledge_graph():
    """获取知识图谱数据"""
    try:
        # 获取最新的分析结果
        if not analysis_status['data']:
            return jsonify({'error': '请先运行分析'}), 400
        
        # 从分析结果构建知识图谱数据
        report = analysis_status.get('report')  # 需要保存report
        
        if not report:
            # 如果没有report，尝试从data构建
            return jsonify({'error': '分析数据不完整'}), 400
        
        knowledge_data = build_knowledge_graph_data(report)
        return jsonify(knowledge_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cfg_dfg/<entity_id>', methods=['GET'])
def api_cfg_dfg(entity_id):
    """获取指定实体的CFG和DFG"""
    try:
        report = analysis_status.get('report')
        if not report:
            return jsonify({'error': '请先运行分析'}), 400
        
        # 查找对应的方法和函数
        method_info = None
        for class_info in report.classes.values():
            for method in class_info.methods.values():
                method_id = f"method_{method.get_full_name()}"
                if method_id == entity_id or method.name == entity_id:
                    method_info = method
                    break
            if method_info:
                break
        
        if not method_info:
            for func in report.functions:
                func_id = f"function_{func.name}"
                if func_id == entity_id or func.name == entity_id:
                    method_info = func
                    break
        
        if not method_info or not method_info.source_code:
            return jsonify({'cfg': None, 'dfg': None})
        
        # 生成CFG
        cfg_generator = CFGGenerator()
        cfg = cfg_generator.generate_cfg(method_info.source_code, method_info.name)
        cfg_dot = cfg.to_dot()
        cfg_json = cfg.to_json()
        
        # 生成DFG
        dfg_generator = DFGGenerator()
        dfg = dfg_generator.generate_dfg(method_info.source_code, method_info.name)
        dfg_dot = dfg.to_dot()
        dfg_json = dfg.to_json()
        
        # 提取IO
        io_extractor = IOExtractor()
        io_info = io_extractor.extract_io(
            method_info.source_code,
            method_info.name,
            method_info.parameters
        )
        
        return jsonify({
            'cfg': cfg_dot,  # 返回DOT格式，前端可以用viz.js渲染
            'cfg_json': cfg_json,
            'dfg': dfg_dot,
            'dfg_json': dfg_json,
            'io': {
                'inputs': io_info.inputs,
                'outputs': io_info.outputs,
                'global_reads': io_info.global_reads,
                'global_writes': io_info.global_writes
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/partition/<partition_id>/analysis', methods=['GET'])
def api_partition_analysis(partition_id):
    """获取功能分区的阶段4分析结果（调用图、超图、入口点、数据流图、控制流图）"""
    try:
        data = analysis_status.get('data')
        if not data:
            return jsonify({'error': '请先运行四层分析'}), 400
        
        partition_analyses = data.get('partition_analyses', {})
        if partition_id not in partition_analyses:
            return jsonify({'error': f'分区 {partition_id} 的分析结果不存在'}), 404
        
        return jsonify(partition_analyses[partition_id])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/partition/<partition_id>/call_graph', methods=['GET'])
def api_partition_call_graph(partition_id):
    """获取功能分区的调用图"""
    try:
        data = analysis_status.get('data')
        if not data:
            return jsonify({'error': '请先运行四层分析'}), 400
        
        partition_analyses = data.get('partition_analyses', {})
        if partition_id not in partition_analyses:
            return jsonify({'error': f'分区 {partition_id} 的分析结果不存在'}), 404
        
        call_graph = partition_analyses[partition_id].get('call_graph')
        if not call_graph:
            return jsonify({'error': '调用图不存在'}), 404
        
        return jsonify(call_graph)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/partition/<partition_id>/hypergraph', methods=['GET'])
def api_partition_hypergraph(partition_id):
    """获取功能分区的超图"""
    try:
        data = analysis_status.get('data')
        if not data:
            return jsonify({'error': '请先运行四层分析'}), 400
        
        partition_analyses = data.get('partition_analyses', {})
        if partition_id not in partition_analyses:
            return jsonify({'error': f'分区 {partition_id} 的分析结果不存在'}), 404
        
        hypergraph = partition_analyses[partition_id].get('hypergraph')
        if not hypergraph:
            return jsonify({'error': '超图不存在'}), 404
        
        return jsonify(hypergraph)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/partition/<partition_id>/entry_points', methods=['GET'])
def api_partition_entry_points(partition_id):
    """获取功能分区的入口点"""
    try:
        data = analysis_status.get('data')
        if not data:
            return jsonify({'error': '请先运行四层分析'}), 400
        
        partition_analyses = data.get('partition_analyses', {})
        if partition_id not in partition_analyses:
            return jsonify({'error': f'分区 {partition_id} 的分析结果不存在'}), 404
        
        entry_points = partition_analyses[partition_id].get('entry_points', [])
        return jsonify({'entry_points': entry_points})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/partition/<partition_id>/dataflow', methods=['GET'])
def api_partition_dataflow(partition_id):
    """获取功能分区的数据流图"""
    try:
        data = analysis_status.get('data')
        if not data:
            return jsonify({'error': '请先运行四层分析'}), 400
        
        partition_analyses = data.get('partition_analyses', {})
        if partition_id not in partition_analyses:
            return jsonify({'error': f'分区 {partition_id} 的分析结果不存在'}), 404
        
        dataflow = partition_analyses[partition_id].get('dataflow')
        if not dataflow:
            return jsonify({'error': '数据流图不存在'}), 404
        
        return jsonify(dataflow)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/partition/<partition_id>/controlflow', methods=['GET'])
def api_partition_controlflow(partition_id):
    """获取功能分区的控制流图"""
    try:
        data = analysis_status.get('data')
        if not data:
            return jsonify({'error': '请先运行四层分析'}), 400
        
        partition_analyses = data.get('partition_analyses', {})
        if partition_id not in partition_analyses:
            return jsonify({'error': f'分区 {partition_id} 的分析结果不存在'}), 404
        
        controlflow = partition_analyses[partition_id].get('controlflow')
        if not controlflow:
            return jsonify({'error': '控制流图不存在'}), 404
        
        return jsonify(controlflow)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def build_knowledge_graph_data(report: ProjectAnalysisReport) -> dict:
    """从ProjectAnalysisReport构建知识图谱数据（增强版：包含CFG、DFG、参数、返回值等实体）"""
    knowledge_data = {
        'repository': None,
        'packages': [],
        'classes': [],
        'methods': [],
        'functions': [],
        'parameters': [],  # 新增：参数实体列表
        'return_values': [],  # 新增：返回值实体列表
        'cfgs': [],  # 新增：CFG实体列表
        'dfgs': [],  # 新增：DFG实体列表
        'edges': []  # 新增：关系边列表
    }
    
    # 初始化CFG和DFG生成器
    cfg_generator = CFGGenerator()
    dfg_generator = DFGGenerator()
    io_extractor = IOExtractor()
    
    # 构建仓库信息
    if report.repository:
        knowledge_data['repository'] = {
            'id': f"repository_{report.repository.name}",
            'name': report.repository.name,
            'path': report.repository.path,
            'description': report.repository.description,
            'type': 'repository'
        }
    else:
        # 如果没有repository，从project_name创建
        knowledge_data['repository'] = {
            'id': f"repository_{report.project_name}",
            'name': report.project_name,
            'path': report.project_path,
            'description': f"代码仓库: {report.project_name}",
            'type': 'repository'
        }
    
    # 构建包信息（从文件路径推断）
    packages_map = {}
    for class_info in report.classes.values():
        if class_info.source_location:
            file_path = class_info.source_location.file_path
            # 提取包路径（去掉文件名）
            package_path = os.path.dirname(file_path)
            package_name = os.path.basename(package_path) or 'root'
            
            if package_path not in packages_map:
                packages_map[package_path] = {
                    'id': f"package_{package_name}",
                    'name': package_name,
                    'path': package_path,
                    'type': 'package',
                    'classes': []
                }
                # 添加仓库到包的包含关系边
                knowledge_data['edges'].append({
                    'id': f"edge_repo_{knowledge_data['repository']['id']}_package_{package_name}",
                    'source': knowledge_data['repository']['id'],
                    'target': f"package_{package_name}",
                    'type': 'repository_contains_package',
                    'label': '包含'
                })
    
    # 构建类信息
    for class_info in report.classes.values():
        class_id = f"class_{class_info.full_name}"
        class_data = {
            'id': class_id,
            'name': class_info.name,
            'full_name': class_info.full_name,
            'type': 'class',
            'methods': [],
            'fields': []
        }
        
        # 添加方法
        for method in class_info.methods.values():
            method_id = f"method_{method.get_full_name()}"
            method_data = {
                'id': method_id,
                'name': method.name,
                'signature': method.signature,
                'type': 'method',
                'parameters': [{'name': p.name, 'type': p.param_type} for p in method.parameters],
                'file_path': method.source_location.file_path if method.source_location else '',
                'source_code': method.source_code or ''
            }
            class_data['methods'].append(method_data)
            
            # 添加类包含方法的关系边
            knowledge_data['edges'].append({
                'id': f"edge_{class_id}_contains_{method_id}",
                'source': class_id,
                'target': method_id,
                'type': 'class_contains_method',
                'label': '包含'
            })
            
            # 为每个参数创建独立实体
            for idx, param in enumerate(method.parameters):
                param_id = f"parameter_{method_id}_{param.name}"
                param_entity = {
                    'id': param_id,
                    'name': param.name,
                    'type': param.param_type,
                    'entity_type': 'parameter',
                    'default_value': param.default_value,
                    'position': idx,
                    'owner_method': method_id
                }
                knowledge_data['parameters'].append(param_entity)
                
                # 添加方法包含参数的关系边
                knowledge_data['edges'].append({
                    'id': f"edge_{method_id}_contains_{param_id}",
                    'source': method_id,
                    'target': param_id,
                    'type': 'method_contains_parameter',
                    'label': '包含参数'
                })
            
            # 创建返回值实体
            if method.return_type and method.return_type != 'None':
                return_id = f"return_{method_id}"
                return_entity = {
                    'id': return_id,
                    'return_type': method.return_type,
                    'entity_type': 'return_value',
                    'owner_method': method_id
                }
                knowledge_data['return_values'].append(return_entity)
                
                # 添加方法拥有返回值的关系边
                knowledge_data['edges'].append({
                    'id': f"edge_{method_id}_has_return_{return_id}",
                    'source': method_id,
                    'target': return_id,
                    'type': 'method_has_return',
                    'label': '返回'
                })
            
            # 生成CFG和DFG（如果方法有源代码）
            if method.source_code:
                try:
                    # 生成CFG
                    cfg = cfg_generator.generate_cfg(method.source_code, method.name)
                    if cfg.nodes:
                        cfg_id = f"cfg_{method_id}"
                        cfg_entity = {
                            'id': cfg_id,
                            'method_id': method_id,
                            'method_name': method.name,
                            'entity_type': 'cfg',
                            'node_count': len(cfg.nodes),
                            'edge_count': len(cfg.edges),
                            'dot_format': cfg.to_dot(),
                            'json_format': cfg.to_json()
                        }
                        knowledge_data['cfgs'].append(cfg_entity)
                        
                        # 添加方法拥有CFG的关系边
                        knowledge_data['edges'].append({
                            'id': f"edge_{method_id}_has_cfg_{cfg_id}",
                            'source': method_id,
                            'target': cfg_id,
                            'type': 'method_has_cfg',
                            'label': '拥有CFG'
                        })
                    
                    # 生成DFG
                    dfg = dfg_generator.generate_dfg(method.source_code, method.name)
                    if dfg.nodes:
                        dfg_id = f"dfg_{method_id}"
                        dfg_entity = {
                            'id': dfg_id,
                            'method_id': method_id,
                            'method_name': method.name,
                            'entity_type': 'dfg',
                            'node_count': len(dfg.nodes),
                            'edge_count': len(dfg.edges),
                            'dot_format': dfg.to_dot(),
                            'json_format': dfg.to_json()
                        }
                        knowledge_data['dfgs'].append(dfg_entity)
                        
                        # 添加方法拥有DFG的关系边
                        knowledge_data['edges'].append({
                            'id': f"edge_{method_id}_has_dfg_{dfg_id}",
                            'source': method_id,
                            'target': dfg_id,
                            'type': 'method_has_dfg',
                            'label': '拥有DFG'
                        })
                except Exception as e:
                    print(f"[app.py] ⚠️ 生成 {method_id} 的CFG/DFG失败: {e}", flush=True)
        
        # 添加字段
        for field in class_info.fields.values():
            field_id = f"field_{class_info.full_name}.{field.name}"
            field_data = {
                'id': field_id,
                'name': field.name,
                'type': field.field_type,
                'entity_type': 'field'
            }
            class_data['fields'].append(field_data)
            
            # 添加类包含字段的关系边
            knowledge_data['edges'].append({
                'id': f"edge_{class_id}_contains_{field_id}",
                'source': class_id,
                'target': field_id,
                'type': 'class_contains_field',
                'label': '包含字段'
            })
        
        # 将类添加到对应的包
        if class_info.source_location:
            file_path = class_info.source_location.file_path
            package_path = os.path.dirname(file_path)
            package_id = None
            if package_path in packages_map:
                package_id = packages_map[package_path]['id']
                packages_map[package_path]['classes'].append(class_data)
            else:
                # 如果没有包，添加到根包
                if 'root' not in packages_map:
                    packages_map['root'] = {
                        'id': 'package_root',
                        'name': 'root',
                        'path': '',
                        'type': 'package',
                        'classes': []
                    }
                package_id = 'package_root'
                packages_map['root']['classes'].append(class_data)
            
            # 添加包包含类的关系边
            if package_id:
                knowledge_data['edges'].append({
                    'id': f"edge_{package_id}_contains_{class_id}",
                    'source': package_id,
                    'target': class_id,
                    'type': 'package_contains_class',
                    'label': '包含'
                })
    
    # 构建函数信息
    for func in report.functions:
        func_id = f"function_{func.name}"
        func_data = {
            'id': func_id,
            'name': func.name,
            'signature': func.signature,
            'type': 'function',
            'parameters': [{'name': p.name, 'type': p.param_type} for p in func.parameters],
            'file_path': func.source_location.file_path if func.source_location else '',
            'source_code': func.source_code or ''
        }
        knowledge_data['functions'].append(func_data)
        
        # 为每个参数创建独立实体
        for idx, param in enumerate(func.parameters):
            param_id = f"parameter_{func_id}_{param.name}"
            param_entity = {
                'id': param_id,
                'name': param.name,
                'type': param.param_type,
                'entity_type': 'parameter',
                'default_value': param.default_value,
                'position': idx,
                'owner_method': func_id
            }
            knowledge_data['parameters'].append(param_entity)
            
            # 添加函数包含参数的关系边
            knowledge_data['edges'].append({
                'id': f"edge_{func_id}_contains_{param_id}",
                'source': func_id,
                'target': param_id,
                'type': 'function_contains_parameter',
                'label': '包含参数'
            })
        
        # 创建返回值实体
        if func.return_type and func.return_type != 'None':
            return_id = f"return_{func_id}"
            return_entity = {
                'id': return_id,
                'return_type': func.return_type,
                'entity_type': 'return_value',
                'owner_method': func_id
            }
            knowledge_data['return_values'].append(return_entity)
            
            # 添加函数拥有返回值的关系边
            knowledge_data['edges'].append({
                'id': f"edge_{func_id}_has_return_{return_id}",
                'source': func_id,
                'target': return_id,
                'type': 'function_has_return',
                'label': '返回'
            })
        
        # 生成CFG和DFG（如果函数有源代码）
        if func.source_code:
            try:
                # 生成CFG
                cfg = cfg_generator.generate_cfg(func.source_code, func.name)
                if cfg.nodes:
                    cfg_id = f"cfg_{func_id}"
                    cfg_entity = {
                        'id': cfg_id,
                        'method_id': func_id,
                        'method_name': func.name,
                        'entity_type': 'cfg',
                        'node_count': len(cfg.nodes),
                        'edge_count': len(cfg.edges),
                        'dot_format': cfg.to_dot(),
                        'json_format': cfg.to_json()
                    }
                    knowledge_data['cfgs'].append(cfg_entity)
                    
                    # 添加函数拥有CFG的关系边
                    knowledge_data['edges'].append({
                        'id': f"edge_{func_id}_has_cfg_{cfg_id}",
                        'source': func_id,
                        'target': cfg_id,
                        'type': 'function_has_cfg',
                        'label': '拥有CFG'
                    })
                
                # 生成DFG
                dfg = dfg_generator.generate_dfg(func.source_code, func.name)
                if dfg.nodes:
                    dfg_id = f"dfg_{func_id}"
                    dfg_entity = {
                        'id': dfg_id,
                        'method_id': func_id,
                        'method_name': func.name,
                        'entity_type': 'dfg',
                        'node_count': len(dfg.nodes),
                        'edge_count': len(dfg.edges),
                        'dot_format': dfg.to_dot(),
                        'json_format': dfg.to_json()
                    }
                    knowledge_data['dfgs'].append(dfg_entity)
                    
                    # 添加函数拥有DFG的关系边
                    knowledge_data['edges'].append({
                        'id': f"edge_{func_id}_has_dfg_{dfg_id}",
                        'source': func_id,
                        'target': dfg_id,
                        'type': 'function_has_dfg',
                        'label': '拥有DFG'
                    })
            except Exception as e:
                print(f"[app.py] ⚠️ 生成 {func_id} 的CFG/DFG失败: {e}", flush=True)
    
    knowledge_data['packages'] = list(packages_map.values())
    
    return knowledge_data


if __name__ == '__main__':
    # 手动运行 python app.py 时直接启动 Flask
    # 禁用调试模式以避免进程中断和日志刷新问题
    print("=" * 60)
    print("🚀 Flask 应用正在启动...")
    print("=" * 60)
    print("访问地址: http://127.0.0.1:5000")
    print("按 Ctrl+C 停止服务器")
    print("=" * 60)
    app.run(debug=False, host='127.0.0.1', port=5000, use_reloader=False, threaded=True)
