"""Stable adapters for v2 skill-callchain inputs."""

from .code_reference_adapter import (
    build_code_reference,
    build_code_references_from_methods,
    build_code_references_from_partition,
    build_code_references_from_path,
)
from .hierarchy_adapter import (
    build_path_evidence,
    get_partition_summaries,
    get_partition_summary,
    load_partition_analyses,
    load_partition_analysis,
    load_partition_summaries,
)
from .phase6_contract_adapter import build_phase6_contract, load_phase6_contract, slim_phase6_contract

__all__ = [
    "build_code_reference",
    "build_code_references_from_methods",
    "build_code_references_from_partition",
    "build_code_references_from_path",
    "build_path_evidence",
    "build_phase6_contract",
    "get_partition_summaries",
    "get_partition_summary",
    "load_partition_analyses",
    "load_partition_analysis",
    "load_partition_summaries",
    "load_phase6_contract",
    "slim_phase6_contract",
]
