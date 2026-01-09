#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
聚合计算器 - 从第3层代码图聚合生成第1、2层的关系
这是实现"不丢失联系"的关键：跨层关系通过聚合动态计算
"""

import logging
from typing import Dict, List, Tuple, Set
from collections import defaultdict
from pathlib import Path

from .hierarchy_model import (
    FunctionPartition, FolderNode, FunctionRelation, FolderRelation,
    CodeGraph, GraphEdge, RelationType, FunctionStats, FolderStats,
    HierarchyModel
)

logger = logging.getLogger(__name__)


class AggregationCalculator:
    """聚合计算器"""
    
    def __init__(self, hierarchy_model: HierarchyModel):
        self.hierarchy = hierarchy_model
        self.code_graph = hierarchy_model.layer3_code_graph
        
        # 映射关系（由上层提供）
        self.entity_to_function = hierarchy_model.entity_to_function_map
        self.entity_to_folder = hierarchy_model.entity_to_folder_map
        self.folder_to_function = hierarchy_model.folder_to_function_map
        
        logger.info("初始化AggregationCalculator")
    
    def calculate_all_relations(self) -> None:
        """计算所有层级的聚合关系"""
        logger.info("\n" + "="*50)
        logger.info("📊 开始计算聚合关系")
        logger.info("="*50)
        
        # 第一步：计算第2层（文件夹层）的关系
        logger.info("1/3 计算文件夹层聚合关系...")
        self._calculate_folder_relations()
        logger.info("✓ 文件夹层关系计算完成")
        
        # 第二步：计算统计信息
        logger.info("2/3 计算聚合统计信息...")
        self._calculate_statistics()
        logger.info("✓ 统计信息计算完成")
        
        # 第三步：计算第1层（功能层）的关系
        logger.info("3/3 计算功能层聚合关系...")
        self._calculate_function_relations()
        logger.info("✓ 功能层关系计算完成")
        
        self.hierarchy.relations_calculated = True
        logger.info("✓ 所有聚合关系计算完成！\n")
    
    def _calculate_folder_relations(self) -> None:
        """
        从第3层的调用图聚合出第2层的文件夹间关系
        关键：保留具体的实体对信息以便后续追踪
        """
        # 初始化文件夹的调用计数
        folder_calls: Dict[Tuple[str, str], int] = defaultdict(int)
        folder_entity_pairs: Dict[Tuple[str, str], List[Tuple[str, str]]] = defaultdict(list)
        
        if not self.code_graph:
            logger.warning("⚠️ 第3层代码图为空，无法计算文件夹关系")
            return
        
        # 遍历所有调用边
        for edge in self.code_graph.edges:
            if edge.relation != RelationType.CALLS:
                continue
            
            source_folder = self.entity_to_folder.get(edge.source_id)
            target_folder = self.entity_to_folder.get(edge.target_id)
            
            if source_folder and target_folder and source_folder != target_folder:
                key = (source_folder, target_folder)
                folder_calls[key] += edge.weight
                folder_entity_pairs[key].append((edge.source_id, edge.target_id))
        
        # 更新文件夹的outgoing/incoming调用
        for folder in self.hierarchy.layer2_folders:
            folder_path = folder.folder_path
            
            # 计算outgoing calls
            for (src_folder, tgt_folder), count in folder_calls.items():
                if src_folder == folder_path:
                    folder.outgoing_calls[tgt_folder] = count
                    # 保存具体的实体对
                    relation = FolderRelation(
                        source_folder=src_folder,
                        target_folder=tgt_folder,
                        call_count=count,
                        entity_pairs=folder_entity_pairs[(src_folder, tgt_folder)][:10]  # 只保存前10对
                    )
                    folder.folder_relations.append(relation)
            
            # 计算incoming calls
            for (src_folder, tgt_folder), count in folder_calls.items():
                if tgt_folder == folder_path:
                    folder.incoming_calls[src_folder] = count
        
        logger.info(f"✓ 聚合了 {len(folder_calls)} 个文件夹间调用关系")
    
    def _calculate_function_relations(self) -> None:
        """
        从第3层的调用图聚合出第1层的功能间关系
        这是最重要的聚合，代表不同功能分区之间的依赖
        """
        # 初始化功能的调用计数
        function_calls: Dict[Tuple[str, str], int] = defaultdict(int)
        function_critical_calls: Dict[Tuple[str, str], int] = defaultdict(int)
        
        if not self.code_graph:
            logger.warning("⚠️ 第3层代码图为空，无法计算功能关系")
            return
        
        # 遍历所有调用边
        for edge in self.code_graph.edges:
            if edge.relation != RelationType.CALLS:
                continue
            
            source_func = self.entity_to_function.get(edge.source_id)
            target_func = self.entity_to_function.get(edge.target_id)
            
            if source_func and target_func and source_func != target_func:
                key = (source_func, target_func)
                function_calls[key] += edge.weight
                
                # 追踪"重要-1"代码参与的调用
                source_detail = self.hierarchy.layer4_details.get(edge.source_id)
                if source_detail and "重要-1" in source_detail.importance_mark:
                    function_critical_calls[key] += 1
        
        # 更新功能的outgoing/incoming调用
        for func in self.hierarchy.layer1_functions:
            func_name = func.name
            
            # 计算outgoing calls
            for (src_func, tgt_func), count in function_calls.items():
                if src_func == func_name:
                    func.outgoing_calls[tgt_func] = count
                    
                    # 计算调用密度
                    source_method_count = func.stats.total_methods if func.stats.total_methods > 0 else 1
                    call_density = count / source_method_count
                    
                    critical_count = function_critical_calls.get((src_func, tgt_func), 0)
                    
                    # 创建详细的功能关系
                    relation = FunctionRelation(
                        source_function=src_func,
                        target_function=tgt_func,
                        call_count=count,
                        call_density=call_density,
                        critical_path_count=critical_count
                    )
                    func.function_relations.append(relation)
            
            # 计算incoming calls
            for (src_func, tgt_func), count in function_calls.items():
                if tgt_func == func_name:
                    func.incoming_calls[src_func] = count
        
        logger.info(f"✓ 聚合了 {len(function_calls)} 个功能间调用关系")
    
    def _calculate_statistics(self) -> None:
        """计算各层的聚合统计信息"""
        
        # 第4层：代码细节层（直接来自code_detail）
        # 已经有了，这里不需要计算
        
        # 第3层：代码图统计（已有）
        
        # 第2层：文件夹统计
        logger.info("  计算文件夹统计...")
        for folder in self.hierarchy.layer2_folders:
            folder.stats.class_count = 0
            folder.stats.method_count = 0
            folder.stats.function_count = 0
            folder.stats.field_count = 0
            
            # 遍历该文件夹包含的代码实体
            for entity_id in folder.contained_code_entities:
                node = self.code_graph.nodes.get(entity_id)
                if not node:
                    continue
                
                entity_type = node.get("type", "")
                if entity_type == "class":
                    folder.stats.class_count += 1
                elif entity_type == "method":
                    folder.stats.method_count += 1
                elif entity_type == "function":
                    folder.stats.function_count += 1
                elif entity_type == "field":
                    folder.stats.field_count += 1
            
            folder.stats.total_code_elements = (
                folder.stats.class_count +
                folder.stats.method_count +
                folder.stats.function_count +
                folder.stats.field_count
            )
        
        logger.info("  计算功能统计...")
        # 第1层：功能统计
        for func in self.hierarchy.layer1_functions:
            func.stats.total_classes = 0
            func.stats.total_methods = 0
            func.stats.total_functions = 0
            func.stats.total_critical_codes = 0
            
            # 遍历该功能包含的文件夹
            for folder_path in func.folders:
                folder = self.hierarchy.layer2_folders_map.get(folder_path)
                if folder:
                    func.stats.total_classes += folder.stats.class_count
                    func.stats.total_methods += folder.stats.method_count
                    func.stats.total_functions += folder.stats.function_count
            
            # 统计该功能的重要代码数
            for entity_id in func.contained_code_entities:
                detail = self.hierarchy.layer4_details.get(entity_id)
                if detail and "重要-1" in detail.importance_mark:
                    func.stats.total_critical_codes += 1
        
        logger.info("✓ 统计信息计算完成")
    
    def calculate_node_sizes(self, base_size: int = 10) -> Dict[str, float]:
        """
        计算节点大小（用于可视化）
        节点大小 = base_size + 包含的代码量
        """
        node_sizes = {}
        
        # 计算功能层节点大小
        for func in self.hierarchy.layer1_functions:
            total_entities = (
                func.stats.total_classes +
                func.stats.total_methods +
                func.stats.total_functions
            )
            size = base_size + total_entities * 2
            node_sizes[func.name] = size
        
        # 计算文件夹层节点大小
        for folder in self.hierarchy.layer2_folders:
            total_entities = folder.stats.total_code_elements
            size = base_size + total_entities * 1.5
            node_sizes[folder.folder_path] = size
        
        return node_sizes
    
    def calculate_edge_widths(self, base_width: float = 1.0, max_width: float = 5.0) -> Dict[str, float]:
        """
        计算边的宽度（用于可视化）
        边的宽度 = 调用次数 * 权重系数
        """
        edge_widths = {}
        
        # 查找所有调用边的最大值
        max_call_count = 1
        for edge in self.code_graph.edges:
            if edge.relation == RelationType.CALLS:
                max_call_count = max(max_call_count, edge.weight)
        
        # 功能层边宽度
        for func in self.hierarchy.layer1_functions:
            for relation in func.function_relations:
                edge_id = f"{relation.source_function}_to_{relation.target_function}"
                # 根据调用次数和调用密度计算宽度
                normalized_count = relation.call_count / max_call_count
                width = base_width + normalized_count * (max_width - base_width)
                edge_widths[edge_id] = width
        
        # 文件夹层边宽度
        for folder in self.hierarchy.layer2_folders:
            for relation in folder.folder_relations:
                edge_id = f"{relation.source_folder}_to_{relation.target_folder}"
                normalized_count = relation.call_count / max_call_count
                width = base_width + normalized_count * (max_width - base_width)
                edge_widths[edge_id] = width
        
        return edge_widths
    
    def get_critical_paths(self, max_depth: int = 3) -> List[List[str]]:
        """
        获取关键路径（参与"重要-1"代码的调用链）
        这有助于可视化展示最重要的功能流程
        """
        critical_paths = []
        
        # 从重要-1代码开始，反向追踪调用链
        for entity_id, detail in self.hierarchy.layer4_details.items():
            if "重要-1" not in detail.importance_mark:
                continue
            
            # 找到调用这个实体的所有其他实体
            path = self._trace_incoming_calls(entity_id, max_depth)
            if path:
                critical_paths.append(path)
        
        return critical_paths[:10]  # 返回前10条关键路径
    
    def _trace_incoming_calls(self, entity_id: str, max_depth: int) -> List[str]:
        """追踪调用链"""
        if max_depth <= 0:
            return [entity_id]
        
        path = [entity_id]
        
        # 找到所有调用这个entity的调用边
        for edge in self.code_graph.edges:
            if edge.relation == RelationType.CALLS and edge.target_id == entity_id:
                source_entity = edge.source_id
                
                # 递归追踪
                incoming_paths = self._trace_incoming_calls(source_entity, max_depth - 1)
                if incoming_paths:
                    path = incoming_paths + path
                    break  # 只追踪最主要的路径
        
        return path if len(path) > 1 else []
    
    def generate_summary_report(self) -> Dict:
        """生成聚合分析报告"""
        report = {
            "layer1_summary": {
                "total_functions": len(self.hierarchy.layer1_functions),
                "total_function_calls": sum(
                    sum(f.outgoing_calls.values())
                    for f in self.hierarchy.layer1_functions
                ),
                "functions": []
            },
            "layer2_summary": {
                "total_folders": len(self.hierarchy.layer2_folders),
                "total_folder_calls": sum(
                    sum(f.outgoing_calls.values())
                    for f in self.hierarchy.layer2_folders
                ),
                "folders": []
            },
            "critical_paths": []
        }
        
        # 功能信息
        for func in self.hierarchy.layer1_functions:
            func_info = {
                "name": func.name,
                "description": func.description[:100],
                "code_entities": len(func.contained_code_entities),
                "outgoing_calls": sum(func.outgoing_calls.values()),
                "incoming_calls": sum(func.incoming_calls.values()),
                "critical_codes": func.stats.total_critical_codes
            }
            report["layer1_summary"]["functions"].append(func_info)
        
        # 文件夹信息
        for folder in self.hierarchy.layer2_folders:
            folder_info = {
                "path": folder.folder_path,
                "parent_function": folder.parent_function,
                "code_elements": folder.stats.total_code_elements,
                "outgoing_calls": sum(folder.outgoing_calls.values()),
                "incoming_calls": sum(folder.incoming_calls.values())
            }
            report["layer2_summary"]["folders"].append(folder_info)
        
        # 关键路径
        critical_paths = self.get_critical_paths()
        report["critical_paths"] = [
            " -> ".join(path[:5]) for path in critical_paths
        ]
        
        return report


def apply_aggregations_to_hierarchy(hierarchy: HierarchyModel) -> None:
    """
    应用所有聚合计算到层级模型
    这是连接第3层和第1、2层的关键函数
    """
    calculator = AggregationCalculator(hierarchy)
    calculator.calculate_all_relations()
    
    logger.info("\n📊 聚合分析报告：")
    report = calculator.generate_summary_report()
    logger.info(f"功能分区数: {report['layer1_summary']['total_functions']}")
    logger.info(f"文件夹数: {report['layer2_summary']['total_folders']}")
    logger.info(f"功能间调用数: {report['layer1_summary']['total_function_calls']}")
    logger.info(f"文件夹间调用数: {report['layer2_summary']['total_folder_calls']}")
