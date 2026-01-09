"""
分析模块 - 包含代码分析的核心功能
"""

from .code_model import (
    ClassInfo, MethodInfo, FieldInfo, Parameter,
    ProjectAnalysisReport, CallRelation, ExecutionEntry,
    ExecutionPath, ExecutionStep, ConfigRequirements,
    SourceLocation, RelationType, ElementType
)
from .symbol_table import SymbolTable
from .call_graph import CallGraph, ExecutionFlowAnalyzer

__all__ = [
    'ClassInfo', 'MethodInfo', 'FieldInfo', 'Parameter',
    'ProjectAnalysisReport', 'CallRelation', 'ExecutionEntry',
    'ExecutionPath', 'ExecutionStep', 'ConfigRequirements',
    'SourceLocation', 'RelationType', 'ElementType',
    'SymbolTable', 'CallGraph', 'ExecutionFlowAnalyzer'
]
