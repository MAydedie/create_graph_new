#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
入口点识别器 - 识别功能分区的入口点
入口点是指功能分区中对外提供接口或作为调用起点的关键方法
"""

from typing import Dict, List, Set, Optional, Any, Tuple
import logging
import ast

logger = logging.getLogger(__name__)


class EntryPoint:
    """入口点"""
    
    def __init__(self, method_sig: str, score: float, reasons: List[str]):
        """
        初始化入口点
        
        Args:
            method_sig: 方法签名
            score: 入口点评分（0-1）
            reasons: 识别原因列表
        """
        self.method_sig = method_sig
        self.score = score
        self.reasons = reasons
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "method_sig": self.method_sig,
            "score": self.score,
            "reasons": self.reasons
        }


class EntryPointIdentifier:
    """入口点识别器"""
    
    def __init__(self, call_graph: Dict[str, Set[str]], 
                 analyzer_report=None,
                 method_location: Dict[str, str] = None):
        """
        初始化识别器
        
        Args:
            call_graph: 调用图 {caller: Set[callees]}
            analyzer_report: 代码分析报告（可选，用于获取方法详细信息）
            method_location: 方法位置映射 {method_sig: file_path}（可选）
        """
        self.call_graph = call_graph
        self.analyzer_report = analyzer_report
        self.method_location = method_location or {}
        
        # 构建反向调用图（用于计算入度）
        self.reverse_call_graph: Dict[str, Set[str]] = {}
        for caller, callees in call_graph.items():
            for callee in callees:
                if callee not in self.reverse_call_graph:
                    self.reverse_call_graph[callee] = set()
                self.reverse_call_graph[callee].add(caller)
    
    def identify_entry_points(self, 
                              partition: Dict[str, Any],
                              all_partitions: List[Dict[str, Any]] = None,
                              score_threshold: float = 0.5) -> List[EntryPoint]:
        """
        识别功能分区的入口点
        
        Args:
            partition: 功能分区字典，包含：
                - partition_id: 分区ID
                - methods: 方法签名列表
            all_partitions: 所有分区列表（用于检测跨分区调用）
            score_threshold: 入口点评分阈值（默认0.5）
        
        Returns:
            入口点列表（按评分降序排列）
        """
        partition_id = partition.get("partition_id", "unknown")
        partition_methods = set(partition.get("methods", []))
        
        logger.info(f"[EntryPointIdentifier] 识别分区 {partition_id} 的入口点，方法数: {len(partition_methods)}")
        
        entry_points = []
        
        # 构建其他分区的方法集合（用于检测外部调用）
        other_partition_methods = set()
        if all_partitions:
            for p in all_partitions:
                if p.get("partition_id") != partition_id:
                    other_partition_methods.update(p.get("methods", []))
        
        for method_sig in partition_methods:
            score, reasons = self._calculate_entry_point_score(
                method_sig, 
                partition_methods,
                other_partition_methods
            )
            
            if score >= score_threshold:
                entry_points.append(EntryPoint(method_sig, score, reasons))
        
        # 按评分降序排列
        entry_points.sort(key=lambda ep: ep.score, reverse=True)
        
        logger.info(f"[EntryPointIdentifier] ✓ 识别到 {len(entry_points)} 个入口点")
        
        return entry_points
    
    def _calculate_entry_point_score(self,
                                     method_sig: str,
                                     partition_methods: Set[str],
                                     other_partition_methods: Set[str]) -> Tuple[float, List[str]]:
        """
        计算入口点评分
        
        评分因素：
        1. 入度分析（入度为0或极低） - 权重 0.3
        2. 外部调用检测（被其他分区调用） - 权重 0.3
        3. 特殊标记识别（@app.route、main()、__init__等） - 权重 0.2
        4. 调用链深度（在调用链的起点） - 权重 0.2
        
        Args:
            method_sig: 方法签名
            partition_methods: 分区方法集合
            other_partition_methods: 其他分区方法集合
        
        Returns:
            (评分, 原因列表)
        """
        score = 0.0
        reasons = []
        
        # 1. 入度分析
        in_degree = len(self.reverse_call_graph.get(method_sig, set()))
        in_degree_score = 0.0
        if in_degree == 0:
            in_degree_score = 1.0
            reasons.append("入度为0（未被其他方法调用）")
        elif in_degree <= 2:
            in_degree_score = 0.7
            reasons.append(f"入度较低（{in_degree}）")
        elif in_degree <= 5:
            in_degree_score = 0.4
            reasons.append(f"入度中等（{in_degree}）")
        
        score += in_degree_score * 0.3
        
        # 2. 外部调用检测
        external_callers = set()
        if method_sig in self.reverse_call_graph:
            for caller in self.reverse_call_graph[method_sig]:
                if caller in other_partition_methods:
                    external_callers.add(caller)
        
        external_score = 0.0
        if len(external_callers) > 0:
            external_score = min(1.0, len(external_callers) / 5.0)  # 最多5个外部调用者得满分
            reasons.append(f"被其他分区调用（{len(external_callers)}个调用者）")
        
        score += external_score * 0.3
        
        # 3. 特殊标记识别
        special_score = 0.0
        special_reason = self._check_special_markers(method_sig)
        if special_reason:
            special_score = 1.0
            reasons.append(special_reason)
        
        score += special_score * 0.2
        
        # 4. 调用链深度计算
        depth_score = self._calculate_call_chain_depth(method_sig, partition_methods)
        if depth_score > 0:
            reasons.append(f"调用链深度评分: {depth_score:.2f}")
        score += depth_score * 0.2
        
        return min(1.0, score), reasons
    
    def _check_special_markers(self, method_sig: str) -> Optional[str]:
        """
        检查特殊标记
        
        特殊标记包括：
        - main() 函数
        - __init__ 方法
        - @app.route 装饰器（Flask）
        - @router.get/post 装饰器（FastAPI）
        - test_ 开头（测试入口）
        - run() / execute() / start() 等常见入口方法名
        
        Args:
            method_sig: 方法签名
        
        Returns:
            特殊标记原因（如果有）
        """
        method_name = method_sig.split(".")[-1] if "." in method_sig else method_sig
        
        # 检查方法名
        if method_name == "main" or method_name == "__main__":
            return "main函数"
        
        if method_name == "__init__":
            return "构造函数"
        
        if method_name.startswith("test_"):
            return "测试入口"
        
        if method_name in ["run", "execute", "start", "entry", "entry_point"]:
            return f"常见入口方法名: {method_name}"
        
        # 检查装饰器（需要从源代码中提取）
        if self.analyzer_report:
            decorator_reason = self._check_decorators(method_sig)
            if decorator_reason:
                return decorator_reason
        
        return None
    
    def _check_decorators(self, method_sig: str) -> Optional[str]:
        """检查装饰器"""
        if not self.analyzer_report:
            return None
        
        # 解析方法签名
        if "." in method_sig:
            class_name, method_name = method_sig.rsplit(".", 1)
            if class_name in self.analyzer_report.classes:
                class_info = self.analyzer_report.classes[class_name]
                if method_name in class_info.methods:
                    method_info = class_info.methods[method_name]
                    source_code = method_info.source_code or ""
                    
                    # 检查装饰器
                    if "@app.route" in source_code or "@route" in source_code:
                        return "Flask路由装饰器"
                    if "@router." in source_code or "@app." in source_code:
                        return "FastAPI路由装饰器"
                    if "@api" in source_code.lower():
                        return "API装饰器"
        
        return None
    
    def _calculate_call_chain_depth(self, 
                                    method_sig: str,
                                    partition_methods: Set[str],
                                    max_depth: int = 10) -> float:
        """
        计算调用链深度评分
        
        如果方法在调用链的起点（调用很多其他方法，但很少被调用），
        则更可能是入口点。
        
        Args:
            method_sig: 方法签名
            partition_methods: 分区方法集合
            max_depth: 最大深度
        
        Returns:
            深度评分（0-1）
        """
        if method_sig not in self.call_graph:
            return 0.0
        
        # 计算出度（调用的方法数）
        out_degree = len(self.call_graph[method_sig])
        
        # 计算入度（被调用的次数）
        in_degree = len(self.reverse_call_graph.get(method_sig, set()))
        
        # 如果出度远大于入度，说明是调用链的起点
        if out_degree > 0 and in_degree == 0:
            return 1.0
        elif out_degree > in_degree * 2:
            return 0.8
        elif out_degree > in_degree:
            return 0.5
        else:
            return 0.2
    
    def get_entry_point_statistics(self, entry_points: List[EntryPoint]) -> Dict[str, Any]:
        """获取入口点统计信息"""
        if not entry_points:
            return {
                "total_entry_points": 0,
                "avg_score": 0.0,
                "score_distribution": {}
            }
        
        scores = [ep.score for ep in entry_points]
        
        return {
            "total_entry_points": len(entry_points),
            "avg_score": sum(scores) / len(scores),
            "max_score": max(scores),
            "min_score": min(scores),
            "score_distribution": {
                "high": len([s for s in scores if s >= 0.8]),
                "medium": len([s for s in scores if 0.5 <= s < 0.8]),
                "low": len([s for s in scores if s < 0.5])
            }
        }


class EntryPointIdentifierGenerator:
    """入口点识别器生成器（批量处理）"""
    
    def __init__(self, call_graph: Dict[str, Set[str]], 
                 analyzer_report=None,
                 method_location: Dict[str, str] = None):
        """
        初始化生成器
        
        Args:
            call_graph: 调用图
            analyzer_report: 代码分析报告
            method_location: 方法位置映射
        """
        self.identifier = EntryPointIdentifier(call_graph, analyzer_report, method_location)
    
    def identify_all_partitions_entry_points(self,
                                            partitions: List[Dict[str, Any]],
                                            score_threshold: float = 0.5) -> Dict[str, List[EntryPoint]]:
        """
        为所有功能分区识别入口点
        
        Args:
            partitions: 功能分区列表
            score_threshold: 入口点评分阈值
        
        Returns:
            {partition_id: [EntryPoint]}
        """
        results = {}
        
        for partition in partitions:
            partition_id = partition.get("partition_id", "unknown")
            entry_points = self.identifier.identify_entry_points(
                partition,
                all_partitions=partitions,
                score_threshold=score_threshold
            )
            results[partition_id] = entry_points
        
        logger.info(f"[EntryPointIdentifierGenerator] ✓ 为 {len(results)} 个分区识别了入口点")
        
        return results


def main():
    """测试代码"""
    # 创建测试数据
    call_graph = {
        "ClassA.method1": {"ClassA.method2", "ClassB.method3"},
        "ClassA.method2": {"ClassA.method3"},
        "ClassA.method3": set(),
        "ClassB.method3": {"ClassC.method4"},
        "ClassC.method4": set(),
        "External.method5": {"ClassA.method1"},  # 外部调用
        "External.method6": {"ClassA.method1"},  # 外部调用
    }
    
    partition = {
        "partition_id": "partition_1",
        "methods": ["ClassA.method1", "ClassA.method2", "ClassA.method3", 
                   "ClassB.method3", "ClassC.method4"]
    }
    
    other_partition = {
        "partition_id": "partition_2",
        "methods": ["External.method5", "External.method6"]
    }
    
    identifier = EntryPointIdentifier(call_graph)
    entry_points = identifier.identify_entry_points(
        partition,
        all_partitions=[partition, other_partition],
        score_threshold=0.3
    )
    
    print("=" * 60)
    print("入口点识别测试")
    print("=" * 60)
    print(f"分区ID: {partition['partition_id']}")
    print(f"识别到 {len(entry_points)} 个入口点:\n")
    
    for ep in entry_points:
        print(f"  {ep.method_sig}")
        print(f"    评分: {ep.score:.2f}")
        print(f"    原因: {', '.join(ep.reasons)}")
        print()
    
    stats = identifier.get_entry_point_statistics(entry_points)
    print("统计信息:")
    print(f"  总入口点数: {stats['total_entry_points']}")
    print(f"  平均评分: {stats['avg_score']:.2f}")
    print(f"  评分分布: {stats['score_distribution']}")


if __name__ == "__main__":
    main()




















