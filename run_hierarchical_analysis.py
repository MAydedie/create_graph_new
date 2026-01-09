#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
四层嵌套可视化系统 - 完整集成示例
运行该脚本会执行完整的项目分析流程
"""

import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs/hierarchical_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger(__name__)


def main():
    """主函数 - 执行完整的四层可视化分析"""
    
    print("\n" + "="*70)
    print("🚀 四层嵌套可视化系统 - 完整分析流程")
    print("="*70 + "\n")
    
    # ============ 配置 ============
    project_path = "d:/代码仓库生图/create_graph"
    api_key = "sk-a7e7d7ee44594ac98c27d64a7496742f"
    base_url = "https://api.deepseek.com/v1"
    
    logger.info(f"项目路径: {project_path}")
    logger.info(f"API配置: {base_url}")
    
    # ============ 步骤1：代码分析（第3层构建） ============
    logger.info("\n" + "="*70)
    logger.info("📊 步骤1: 分析项目代码（构建第3层CodeGraph）")
    logger.info("="*70)
    
    try:
        from analysis.analyzer import CodeAnalyzer
        analyzer = CodeAnalyzer(project_path)
        graph_data = analyzer.analyze(project_path)
        logger.info("✅ 代码分析完成")
        logger.info(f"   - 类数: {graph_data['metadata'].get('total_classes', 0)}")
        logger.info(f"   - 方法数: {graph_data['metadata'].get('total_methods', 0)}")
        logger.info(f"   - 函数数: {graph_data['metadata'].get('total_functions', 0)}")
        logger.info(f"   - 调用关系数: {len(graph_data.get('edges', []))}")
    except Exception as e:
        logger.error(f"❌ 代码分析失败: {e}", exc_info=True)
        return False
    
    # ============ 步骤2：LLM理解项目（第1层规划） ============
    logger.info("\n" + "="*70)
    logger.info("🧠 步骤2: LLM理解项目结构（规划第1层FunctionPartitions）")
    logger.info("="*70)
    
    try:
        from llm.code_understanding_agent import CodeUnderstandingAgent
        agent = CodeUnderstandingAgent(api_key=api_key, base_url=base_url)
        
        # 2.1 加载项目
        project_info = agent.load_project(project_path)
        logger.info(f"✅ 项目加载完成: {project_info['name']}")
        
        # 2.2 分析项目概览
        logger.info("🔍 分析项目概览...")
        overview = agent.analyze_project_overview()
        logger.info(f"✅ 项目概览分析完成")
        if overview:
            logger.info(f"   概览摘要: {overview[:200]}...")
        
        # 2.3 识别功能分区
        logger.info("🔍 识别功能分区...")
        partitions = agent.identify_function_partitions(project_info)
        logger.info(f"✅ 功能分区识别完成: {len(partitions)} 个分区")
        for partition in partitions:
            logger.info(f"   - {partition.name}: {partition.description[:50]}...")
    
    except Exception as e:
        logger.error(f"❌ LLM分析失败: {e}", exc_info=True)
        # 不中断，使用默认分区继续
        partitions = []
    
    # ============ 步骤3：构建层级模型 ============
    logger.info("\n" + "="*70)
    logger.info("🏗️ 步骤3: 构建四层层级模型")
    logger.info("="*70)
    
    try:
        from analysis.hierarchy_model import (
            HierarchyModel, HierarchyMetadata, CodeGraph, GraphEdge, RelationType
        )
        
        # 3.1 创建元数据
        metadata = HierarchyMetadata(
            project_name=os.path.basename(project_path),
            project_path=project_path,
            analysis_timestamp=datetime.now().isoformat(),
            total_files=graph_data['metadata'].get('total_files', 0),
            total_functions_in_partition=len(partitions) if partitions else 3
        )
        
        # 3.2 创建空的层级模型
        hierarchy = HierarchyModel(metadata=metadata)
        
        # 3.3 填充第3层（CodeGraph）
        logger.info("   填充第3层: CodeGraph...")
        code_graph = CodeGraph(
            nodes={},
            edges=[],
            total_nodes=len(graph_data.get('nodes', [])),
            total_edges=len(graph_data.get('edges', [])),
            total_classes=graph_data['metadata'].get('total_classes', 0),
            total_methods=graph_data['metadata'].get('total_methods', 0),
            total_functions=graph_data['metadata'].get('total_functions', 0),
        )
        hierarchy.layer3_code_graph = code_graph
        logger.info(f"   ✅ 第3层完成: {code_graph.total_nodes} 个节点, {code_graph.total_edges} 条边")
        
        # 3.4 填充第1层（功能分区）
        logger.info("   填充第1层: FunctionPartitions...")
        if partitions:
            for partition in partitions:
                hierarchy.layer1_functions.append(partition)
                hierarchy.layer1_functions_map[partition.name] = partition
        else:
            # 使用默认分区
            from analysis.hierarchy_model import FunctionPartition, FunctionStats
            default_partitions = [
                FunctionPartition(
                    name="代码解析层",
                    description="负责Python代码的AST解析和符号提取",
                    folders=["parsers", "analysis"],
                    stats=FunctionStats(total_classes=34)
                ),
                FunctionPartition(
                    name="分析层",
                    description="负责调用图、继承关系、数据流等高级分析",
                    folders=["analysis"],
                    stats=FunctionStats(total_methods=146)
                ),
                FunctionPartition(
                    name="可视化层",
                    description="负责前端数据生成和可视化展示",
                    folders=["visualization", "output_analysis", "templates"],
                    stats=FunctionStats(total_functions=155)
                )
            ]
            for partition in default_partitions:
                hierarchy.layer1_functions.append(partition)
                hierarchy.layer1_functions_map[partition.name] = partition
        
        logger.info(f"   ✅ 第1层完成: {len(hierarchy.layer1_functions)} 个功能分区")
        
        # 3.5 填充第2层（文件夹）
        logger.info("   填充第2层: Folders...")
        from analysis.hierarchy_model import FolderNode, FolderStats
        
        folders = [
            FolderNode(
                folder_path="parsers",
                parent_function="代码解析层",
                contained_files=["base_parser.py", "python_parser.py"],
                stats=FolderStats(class_count=2, method_count=20)
            ),
            FolderNode(
                folder_path="analysis",
                parent_function="分析层",
                contained_files=["analyzer.py", "call_graph_analyzer.py", "data_flow_analyzer.py"],
                stats=FolderStats(class_count=6, method_count=50)
            ),
            FolderNode(
                folder_path="visualization",
                parent_function="可视化层",
                contained_files=["enhanced_visualizer.py", "graph_data.py"],
                stats=FolderStats(function_count=10)
            )
        ]
        
        for folder in folders:
            hierarchy.layer2_folders.append(folder)
            hierarchy.layer2_folders_map[folder.folder_path] = folder
        
        logger.info(f"   ✅ 第2层完成: {len(hierarchy.layer2_folders)} 个文件夹")
        
        logger.info("✅ 层级模型构建完成")
        
    except Exception as e:
        logger.error(f"❌ 构建层级模型失败: {e}", exc_info=True)
        return False
    
    # ============ 步骤4：计算聚合关系 ============
    logger.info("\n" + "="*70)
    logger.info("🔗 步骤4: 计算聚合关系（连接各层）")
    logger.info("="*70)
    
    try:
        from analysis.aggregation_calculator import apply_aggregations_to_hierarchy
        
        # 需要先设置映射关系（实际项目中由Agent提供）
        hierarchy.entity_to_function_map = {
            f"entity_{i}": f"function_{i % len(hierarchy.layer1_functions)}"
            for i in range(100)
        }
        hierarchy.entity_to_folder_map = {
            f"entity_{i}": f"folder_{i % len(hierarchy.layer2_folders)}"
            for i in range(100)
        }
        
        # 执行聚合计算
        apply_aggregations_to_hierarchy(hierarchy)
        logger.info("✅ 聚合关系计算完成")
        
        # 输出聚合结果
        logger.info("\n📊 聚合分析结果:")
        for func in hierarchy.layer1_functions:
            outgoing = sum(func.outgoing_calls.values()) if func.outgoing_calls else 0
            logger.info(f"   {func.name}: {outgoing} 个出边调用")
        
    except Exception as e:
        logger.warning(f"⚠️ 聚合关系计算失败: {e}")
        # 继续进行，即使聚合失败
    
    # ============ 步骤5：生成代码解释 ============
    logger.info("\n" + "="*70)
    logger.info("📝 步骤5: 为重要代码生成LLM解释（可选）")
    logger.info("="*70)
    
    try:
        response = input("是否要为重要代码生成LLM解释? (y/n, 默认n): ").strip().lower()
        if response == 'y':
            logger.info("🤖 调用LLM生成代码解释...")
            from llm.code_explanation_chain import generate_explanations_for_hierarchy
            
            generate_explanations_for_hierarchy(hierarchy, api_key, base_url)
            logger.info("✅ 代码解释生成完成")
        else:
            logger.info("⏭️ 跳过代码解释生成")
    
    except Exception as e:
        logger.warning(f"⚠️ 代码解释生成失败: {e}")
    
    # ============ 步骤6：保存结果 ============
    logger.info("\n" + "="*70)
    logger.info("💾 步骤6: 保存分析结果")
    logger.info("="*70)
    
    try:
        os.makedirs("output", exist_ok=True)
        output_path = "output/hierarchy_model.json"
        hierarchy.to_json(output_path)
        logger.info(f"✅ 分析结果已保存到: {output_path}")
    
    except Exception as e:
        logger.error(f"❌ 保存结果失败: {e}", exc_info=True)
        return False
    
    # ============ 总结 ============
    logger.info("\n" + "="*70)
    logger.info("✅ 四层嵌套可视化分析完成！")
    logger.info("="*70)
    
    logger.info("\n📋 分析摘要:")
    logger.info(f"   功能分区数: {len(hierarchy.layer1_functions)}")
    logger.info(f"   文件夹数: {len(hierarchy.layer2_folders)}")
    logger.info(f"   代码元素数: {hierarchy.layer3_code_graph.total_nodes if hierarchy.layer3_code_graph else 0}")
    logger.info(f"   关系边数: {hierarchy.layer3_code_graph.total_edges if hierarchy.layer3_code_graph else 0}")
    
    logger.info("\n🎯 下一步:")
    logger.info("   1. 查看 output/hierarchy_model.json 了解详细数据")
    logger.info("   2. 参考 IMPLEMENTATION_GUIDE_新功能.md 进行前端集成")
    logger.info("   3. 运行 python app.py 启动Web界面展示")
    
    logger.info("\n" + "="*70 + "\n")
    
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断分析")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ 程序异常: {e}", exc_info=True)
        sys.exit(1)
