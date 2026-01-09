#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LLM分区优化器 - 使用LangChain agent和tool优化功能分区
基于路径语义和代码线索，通过LLM迭代优化功能分区识别结果
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field, asdict

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# LangChain导入
try:
    from langchain_core.tools import tool
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
    LANGCHAIN_AVAILABLE = True
except ImportError:
    try:
        from langchain_community.chat_models import ChatOpenAI
        LANGCHAIN_AVAILABLE = True
    except ImportError:
        LANGCHAIN_AVAILABLE = False
        logger.warning("LangChain 未安装，将使用直接 API 调用")

from analysis.community_detector import CommunityDetector
from analysis.code_model import ProjectAnalysisReport
from analysis.method_function_profile_builder import MethodFunctionProfileBuilder


@dataclass
class OptimizationHistory:
    """优化历史记录"""
    iteration: int
    action: str  # "merge", "split", "adjust", "final"
    partitions_before: List[Dict[str, Any]]
    partitions_after: List[Dict[str, Any]]
    modularity_before: float
    modularity_after: float
    modularity_improvement: float
    llm_reasoning: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationResult:
    """优化结果"""
    partitions: List[Dict[str, Any]]
    optimization_history: List[OptimizationHistory]
    statistics: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "partitions": self.partitions,
            "optimization_history": [asdict(h) for h in self.optimization_history],
            "statistics": self.statistics
        }


class LLMPartitionOptimizer:
    """LLM分区优化器 - 使用LangChain tool辅助优化"""
    
    def __init__(self, 
                 api_key: str,
                 base_url: str = "https://api.deepseek.com/v1",
                 project_path: Optional[str] = None,
                 report: Optional[ProjectAnalysisReport] = None):
        """
        初始化优化器
        
        Args:
            api_key: DeepSeek API密钥
            base_url: DeepSeek API基础URL
            project_path: 项目路径
            report: 项目分析报告
        """
        self.api_key = api_key
        self.base_url = base_url
        self.project_path = project_path
        self.report = report
        
        # 初始化LLM
        self.llm = None
        self._init_llm()
        
        # 初始化方法功能画像构建器
        self.profile_builder = None
        if project_path and report:
            self.profile_builder = MethodFunctionProfileBuilder(project_path, report)
            self.method_profiles: Dict[str, Any] = {}  # 缓存方法功能画像
        
        # 优化历史
        self.optimization_history: List[OptimizationHistory] = []
        
        logger.info(f"[LLMPartitionOptimizer] 初始化完成，base_url: {base_url}")
    
    def _init_llm(self):
        """初始化LLM客户端"""
        try:
            try:
                from langchain_openai import ChatOpenAI
                self.llm = ChatOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    model="deepseek-chat",
                    temperature=0.3,
                    max_tokens=8000
                )
                logger.info("✓ ChatOpenAI客户端初始化成功 (langchain_openai)")
            except ImportError:
                from langchain_community.chat_models import ChatOpenAI
                self.llm = ChatOpenAI(
                    openai_api_key=self.api_key,
                    openai_api_base=self.base_url,
                    model_name="deepseek-chat",
                    temperature=0.3,
                    max_tokens=8000
                )
                logger.info("✓ ChatOpenAI客户端初始化成功 (langchain_community)")
        except Exception as e:
            logger.error(f"✗ 初始化LLM客户端失败: {e}")
            raise
    
    def optimize_partitions(self,
                           initial_partitions: List[Dict[str, Any]],
                           call_graph: Dict[str, Set[str]],
                           multi_source_info: Optional[Dict[str, Any]] = None,
                           max_iterations: int = 3,
                           modularity_improvement_threshold: float = 0.1) -> OptimizationResult:
        """
        优化功能分区
        
        Args:
            initial_partitions: 初始分区列表（来自社区检测）
            call_graph: 调用图 {caller: Set[callees]}
            multi_source_info: 多源信息（来自MultiSourceInfoCollector）
            max_iterations: 最大迭代次数
            modularity_improvement_threshold: 模块度提升阈值（>此值继续迭代）
        
        Returns:
            优化结果
        """
        logger.info(f"[LLMPartitionOptimizer] 开始优化分区，初始分区数: {len(initial_partitions)}")
        
        # 构建方法功能画像（如果需要）
        if self.profile_builder:
            self._build_method_profiles(initial_partitions)
        
        # 计算初始模块度
        current_partitions = initial_partitions.copy()
        current_modularity = self._calculate_average_modularity(current_partitions)
        
        logger.info(f"[LLMPartitionOptimizer] 初始平均模块度: {current_modularity:.3f}")
        
        # 迭代优化
        for iteration in range(1, max_iterations + 1):
            logger.info(f"\n[LLMPartitionOptimizer] ===== 迭代 {iteration}/{max_iterations} =====")
            
            # 保存迭代前的状态
            partitions_before = [p.copy() for p in current_partitions]
            modularity_before = current_modularity
            
            # 调用LLM进行优化建议
            optimization_suggestions = self._get_optimization_suggestions(
                current_partitions,
                call_graph,
                multi_source_info,
                iteration
            )
            
            # 应用优化建议
            current_partitions, llm_reasoning = self._apply_optimization_suggestions(
                current_partitions,
                optimization_suggestions,
                call_graph
            )
            
            # 计算新的模块度
            current_modularity = self._calculate_average_modularity(current_partitions)
            modularity_improvement = current_modularity - modularity_before
            
            # 记录优化历史
            history = OptimizationHistory(
                iteration=iteration,
                action="optimize",
                partitions_before=partitions_before,
                partitions_after=[p.copy() for p in current_partitions],
                modularity_before=modularity_before,
                modularity_after=current_modularity,
                modularity_improvement=modularity_improvement,
                llm_reasoning=llm_reasoning,
                details={"suggestions": optimization_suggestions}
            )
            self.optimization_history.append(history)
            
            logger.info(f"[LLMPartitionOptimizer] 迭代 {iteration} 完成:")
            logger.info(f"  模块度: {modularity_before:.3f} → {current_modularity:.3f} (提升 {modularity_improvement:+.3f})")
            logger.info(f"  分区数: {len(partitions_before)} → {len(current_partitions)}")
            
            # 判断是否继续迭代
            if modularity_improvement < modularity_improvement_threshold:
                logger.info(f"[LLMPartitionOptimizer] 模块度提升 < {modularity_improvement_threshold}，停止迭代")
                break
        
        # 构建统计信息
        statistics = self._build_statistics(initial_partitions, current_partitions)
        
        # 构建结果
        result = OptimizationResult(
            partitions=current_partitions,
            optimization_history=self.optimization_history,
            statistics=statistics
        )
        
        logger.info(f"[LLMPartitionOptimizer] ✓ 优化完成，最终分区数: {len(current_partitions)}")
        logger.info(f"[LLMPartitionOptimizer]   模块度: {statistics['initial_modularity']:.3f} → {statistics['final_modularity']:.3f}")
        logger.info(f"[LLMPartitionOptimizer]   提升: {statistics['modularity_improvement']:+.3f}")
        
        return result
    
    def _build_method_profiles(self, partitions: List[Dict[str, Any]]):
        """构建方法功能画像"""
        logger.info("[LLMPartitionOptimizer] 构建方法功能画像...")
        
        # 收集所有方法签名
        all_methods = set()
        for partition in partitions:
            all_methods.update(partition.get("methods", []))
        
        # 批量构建功能画像
        if self.profile_builder:
            self.method_profiles = self.profile_builder.build_profiles_batch(list(all_methods))
            logger.info(f"[LLMPartitionOptimizer] ✓ 构建了 {len(self.method_profiles)} 个方法功能画像")
    
    def _get_optimization_suggestions(self,
                                    partitions: List[Dict[str, Any]],
                                    call_graph: Dict[str, Set[str]],
                                    multi_source_info: Optional[Dict[str, Any]],
                                    iteration: int) -> Dict[str, Any]:
        """
        获取LLM的优化建议
        
        Returns:
            优化建议字典（包含合并、拆分、调整建议）
        """
        # 构建prompt
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(partitions, call_graph, multi_source_info, iteration)
        
        # 调用LLM
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            # 解析LLM响应
            suggestions = self._parse_llm_response(response.content)
            return suggestions
        except Exception as e:
            logger.error(f"[LLMPartitionOptimizer] LLM调用失败: {e}")
            return {}
    
    def _build_system_prompt(self) -> str:
        """构建system prompt"""
        return """你是一个代码分析专家。你的任务是优化功能分区，使其更接近真实的项目功能划分。

功能分区的原则：
1. 同一功能分区的方法应该有较强的调用关系
2. 同一功能分区的方法应该实现相关的业务逻辑
3. 允许方法属于多个功能分区（重叠功能）
4. 功能分区应该有明确的入口点
5. 文件路径和组织结构往往反映真实的功能划分
6. 代码中的装饰器、继承、导入等模式也暗示功能归属

请仔细分析文件路径语义和代码线索，给出优化建议。
返回JSON格式，包含以下字段：
{
    "merge_suggestions": [{"partition_ids": ["id1", "id2"], "reason": "..."}],
    "split_suggestions": [{"partition_id": "id", "sub_partitions": [...], "reason": "..."}],
    "adjust_suggestions": [{"method": "...", "from_partition": "id", "to_partitions": ["id1", "id2"], "reason": "..."}]
}"""
    
    def _build_user_prompt(self,
                          partitions: List[Dict[str, Any]],
                          call_graph: Dict[str, Set[str]],
                          multi_source_info: Optional[Dict[str, Any]],
                          iteration: int) -> str:
        """构建user prompt"""
        lines = []
        lines.append(f"当前是第 {iteration} 次迭代优化。")
        lines.append("")
        lines.append("# 当前分区信息")
        lines.append("")
        
        # 格式化分区信息
        for i, partition in enumerate(partitions):
            lines.append(f"## 分区 {partition.get('partition_id', f'partition_{i}')}")
            lines.append(f"- 模块度: {partition.get('modularity', 0):.3f}")
            lines.append(f"- 方法数: {len(partition.get('methods', []))}")
            lines.append(f"- 内部调用: {partition.get('internal_calls', 0)}")
            lines.append(f"- 外部调用: {partition.get('external_calls', 0)}")
            lines.append(f"- 方法列表: {', '.join(list(partition.get('methods', []))[:10])}")
            if len(partition.get('methods', [])) > 10:
                lines.append(f"  ... 还有 {len(partition.get('methods', [])) - 10} 个方法")
            lines.append("")
        
        # 添加方法功能画像（如果可用）
        if self.method_profiles:
            lines.append("# 方法功能画像（关键方法）")
            lines.append("")
            # 选择前20个方法展示
            profile_text = self.profile_builder.format_profiles_for_llm(
                dict(list(self.method_profiles.items())[:20])
            )
            lines.append(profile_text)
            lines.append("")
        
        # 添加多源信息（如果有）
        if multi_source_info:
            lines.append("# 多源信息摘要")
            if multi_source_info.get("readme"):
                lines.append(f"- README关键词: {', '.join(multi_source_info['readme'].get('keywords', [])[:10])}")
            lines.append("")
        
        lines.append("请给出优化建议（JSON格式）。")
        
        return "\n".join(lines)
    
    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """解析LLM响应"""
        try:
            # 尝试提取JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
        except Exception as e:
            logger.warning(f"[LLMPartitionOptimizer] 解析LLM响应失败: {e}")
        
        return {
            "merge_suggestions": [],
            "split_suggestions": [],
            "adjust_suggestions": []
        }
    
    def _apply_optimization_suggestions(self,
                                      partitions: List[Dict[str, Any]],
                                      suggestions: Dict[str, Any],
                                      call_graph: Dict[str, Set[str]]) -> Tuple[List[Dict[str, Any]], str]:
        """
        应用优化建议
        
        Returns:
            (优化后的分区列表, LLM推理说明)
        """
        # 创建分区索引（partition_id -> partition）
        partition_map = {p.get("partition_id", f"partition_{i}"): p for i, p in enumerate(partitions)}
        new_partitions = [p.copy() for p in partitions]
        reasoning_parts = []
        
        # 1. 处理合并建议
        merge_suggestions = suggestions.get("merge_suggestions", [])
        for merge_sugg in merge_suggestions:
            partition_ids = merge_sugg.get("partition_ids", [])
            if len(partition_ids) >= 2:
                # 找到要合并的分区
                partitions_to_merge = []
                for pid in partition_ids:
                    if pid in partition_map:
                        partitions_to_merge.append(partition_map[pid])
                
                if partitions_to_merge:
                    # 合并分区
                    merged_partition = self._merge_partitions(partitions_to_merge, call_graph)
                    # 移除旧分区，添加新分区
                    new_partitions = [p for p in new_partitions if p.get("partition_id") not in partition_ids]
                    new_partitions.append(merged_partition)
                    reasoning_parts.append(f"合并分区 {', '.join(partition_ids)}: {merge_sugg.get('reason', '')}")
        
        # 2. 处理拆分建议
        split_suggestions = suggestions.get("split_suggestions", [])
        for split_sugg in split_suggestions:
            partition_id = split_sugg.get("partition_id")
            sub_partitions = split_sugg.get("sub_partitions", [])
            
            if partition_id in partition_map and sub_partitions:
                # 找到要拆分的分区
                partition_to_split = partition_map.get(partition_id)
                if partition_to_split:
                    # 拆分分区
                    split_results = self._split_partition(partition_to_split, sub_partitions, call_graph)
                    # 移除旧分区，添加新分区
                    new_partitions = [p for p in new_partitions if p.get("partition_id") != partition_id]
                    new_partitions.extend(split_results)
                    reasoning_parts.append(f"拆分分区 {partition_id}: {split_sugg.get('reason', '')}")
        
        # 3. 处理方法归属调整建议
        adjust_suggestions = suggestions.get("adjust_suggestions", [])
        for adjust_sugg in adjust_suggestions:
            method_sig = adjust_sugg.get("method")
            from_partition_id = adjust_sugg.get("from_partition")
            to_partition_ids = adjust_sugg.get("to_partitions", [])
            
            if method_sig and from_partition_id and to_partition_ids:
                # 调整方法归属
                new_partitions = self._adjust_method_belonging(
                    new_partitions, method_sig, from_partition_id, to_partition_ids
                )
                reasoning_parts.append(f"调整方法 {method_sig} 从 {from_partition_id} 到 {', '.join(to_partition_ids)}")
        
        reasoning = "; ".join(reasoning_parts) if reasoning_parts else "无优化建议或优化建议无效"
        return new_partitions, reasoning
    
    def _merge_partitions(self,
                         partitions: List[Dict[str, Any]],
                         call_graph: Dict[str, Set[str]]) -> Dict[str, Any]:
        """合并多个分区"""
        # 合并方法集合
        all_methods = set()
        for p in partitions:
            all_methods.update(p.get("methods", []))
        
        # 计算新的统计信息
        internal_calls = 0
        external_calls = 0
        for method in all_methods:
            if method in call_graph:
                for callee in call_graph[method]:
                    if callee in all_methods:
                        internal_calls += 1
                    else:
                        external_calls += 1
        
        # 计算模块度（简化计算）
        total_calls = internal_calls + external_calls
        modularity = internal_calls / total_calls if total_calls > 0 else 0.0
        
        # 创建新分区
        merged_id = "_".join([p.get("partition_id", "") for p in partitions])
        return {
            "partition_id": f"merged_{merged_id}",
            "methods": list(all_methods),
            "modularity": modularity,
            "internal_calls": internal_calls,
            "external_calls": external_calls,
            "size": len(all_methods),
            "merged_from": [p.get("partition_id") for p in partitions]
        }
    
    def _split_partition(self,
                        partition: Dict[str, Any],
                        sub_partitions: List[List[str]],
                        call_graph: Dict[str, Set[str]]) -> List[Dict[str, Any]]:
        """拆分分区"""
        results = []
        original_id = partition.get("partition_id", "partition")
        
        for i, sub_methods in enumerate(sub_partitions):
            if not sub_methods:
                continue
            
            sub_method_set = set(sub_methods)
            
            # 计算统计信息
            internal_calls = 0
            external_calls = 0
            for method in sub_method_set:
                if method in call_graph:
                    for callee in call_graph[method]:
                        if callee in sub_method_set:
                            internal_calls += 1
                        else:
                            external_calls += 1
            
            # 计算模块度
            total_calls = internal_calls + external_calls
            modularity = internal_calls / total_calls if total_calls > 0 else 0.0
            
            results.append({
                "partition_id": f"{original_id}_split_{i}",
                "methods": list(sub_method_set),
                "modularity": modularity,
                "internal_calls": internal_calls,
                "external_calls": external_calls,
                "size": len(sub_method_set),
                "split_from": original_id
            })
        
        return results
    
    def _adjust_method_belonging(self,
                                partitions: List[Dict[str, Any]],
                                method_sig: str,
                                from_partition_id: str,
                                to_partition_ids: List[str]) -> List[Dict[str, Any]]:
        """调整方法归属（允许方法属于多个分区）"""
        new_partitions = []
        
        for partition in partitions:
            p_id = partition.get("partition_id", "")
            methods = set(partition.get("methods", []))
            
            # 如果是从这个分区移出
            if p_id == from_partition_id:
                methods.discard(method_sig)  # 从原分区移除
            
            # 如果是添加到这个分区
            if p_id in to_partition_ids:
                methods.add(method_sig)  # 添加到新分区
            
            # 更新分区
            new_partition = partition.copy()
            new_partition["methods"] = list(methods)
            new_partition["size"] = len(methods)
            new_partitions.append(new_partition)
        
        return new_partitions
    
    def _calculate_average_modularity(self, partitions: List[Dict[str, Any]]) -> float:
        """计算平均模块度"""
        if not partitions:
            return 0.0
        modularities = [p.get("modularity", 0.0) for p in partitions]
        return sum(modularities) / len(modularities)
    
    def _build_statistics(self,
                         initial_partitions: List[Dict[str, Any]],
                         final_partitions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """构建统计信息"""
        initial_modularity = self._calculate_average_modularity(initial_partitions)
        final_modularity = self._calculate_average_modularity(final_partitions)
        
        return {
            "initial_modularity": initial_modularity,
            "final_modularity": final_modularity,
            "modularity_improvement": final_modularity - initial_modularity,
            "iterations": len(self.optimization_history),
            "initial_partition_count": len(initial_partitions),
            "final_partition_count": len(final_partitions),
            "merged_partitions": 0,  # TODO: 统计合并的分区数
            "split_partitions": 0,   # TODO: 统计拆分的分区数
            "adjusted_methods": 0    # TODO: 统计调整的方法数
        }


def main():
    """测试代码"""
    print("LLMPartitionOptimizer 测试")
    # TODO: 添加测试代码


if __name__ == "__main__":
    main()

