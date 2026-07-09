#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class PartitionRecord:
    partition_id: str
    name: str
    original_name: Optional[str]
    modularity: float
    cohesion_score: float
    internal_calls: int
    external_calls: int
    size: int
    method_count: int
    source_project_path: Optional[str] = None


@dataclass(frozen=True)
class PartitionMemberRecord:
    partition_id: str
    member_order: int
    symbol_id: str
    symbol_qualified_name: str


@dataclass(frozen=True)
class PartitionTopologyRecord:
    source_partition: str
    target_partition: str
    edge_count: int
    weight: float
    call_examples: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class OptimizedPartitionRecord:
    optimization_run_id: str
    partition_id: str
    name: str
    original_name: Optional[str]
    modularity: float
    cohesion_score: float
    internal_calls: int
    external_calls: int
    size: int
    method_count: int
    methods_json: str
    qualified_methods_json: str
    member_symbols_json: str
    source_project_path: Optional[str]
    trigger_mode: str
    threshold: float
    was_optimized: bool


@dataclass(frozen=True)
class OptimizationHistoryRecord:
    optimization_run_id: str
    history_index: int
    iteration: int
    action: str
    partitions_before_json: str
    partitions_after_json: str
    modularity_before: float
    modularity_after: float
    modularity_improvement: float
    llm_reasoning: str
    details_json: str
    source_project_path: Optional[str]
    trigger_mode: str
    threshold: float
    status: str
    skip_reason: Optional[str]


@dataclass(frozen=True)
class CommunitySummaryRecord:
    community_run_id: str
    partition_id: str
    name: str
    original_name: Optional[str]
    modularity: float
    cohesion_score: float
    internal_calls: int
    external_calls: int
    size: int
    method_count: int
    methods_json: str
    qualified_methods_json: str
    member_symbols_json: str
    semantic_label: str
    description: str
    functional_domain: str
    key_concepts_json: str
    top_files_json: str
    top_dependencies_json: str
    source_project_path: Optional[str]
    trigger_mode: str
    threshold: float
    status: str
    skip_reason: Optional[str]
    model: Optional[str]
    duration_ms: int


@dataclass(frozen=True)
class CommunitySummaryHistoryRecord:
    community_run_id: str
    history_index: int
    partition_id: str
    action: str
    status: str
    llm_reasoning: str
    details_json: str
    source_project_path: Optional[str]
    trigger_mode: str
    threshold: float
    skip_reason: Optional[str]
    model: Optional[str]
    duration_ms: int


@dataclass(frozen=True)
class PathRecord:
    path_id: str
    run_id: str
    partition_id: str
    leaf_node: str
    function_chain_json: str
    path_name: str
    path_description: str
    semantic_label: str
    keywords_json: str
    functional_domain: str
    worthiness_score: float
    deep_analysis_status: str
    cfg_dfg_explain_md: str
    model: Optional[str]
    duration_ms: int
    source_project_path: Optional[str]
    skip_reason: Optional[str]
    trigger_mode: str
    llm_reasoning: str


@dataclass(frozen=True)
class PathLinkRecord:
    link_id: str
    run_id: str
    path_id: str
    step_index: int
    caller: str
    callee: str
    is_direct_call: Optional[bool]
    caller_file_path: str
    callee_file_path: str


@dataclass(frozen=True)
class PathCfgRecord:
    cfg_id: str
    run_id: str
    path_id: str
    method_sig: str
    node_id: str
    line_number: int
    node_type: str
    code_excerpt: str


@dataclass(frozen=True)
class PathDfgRecord:
    dfg_id: str
    run_id: str
    path_id: str
    method_sig: str
    variable_name: str
    node_id: str
    line_number: int
    node_type: str
    method_node_id: str


@dataclass(frozen=True)
class PathReverseIndexRecord:
    method_qn: str
    run_id: str
    path_id: str
