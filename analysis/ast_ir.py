#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 1 AST IR 标准化。

把 CodeAnalyzer.report + CallGraphAnalyzer.call_graph 转成可独立保存、
可作为后续阶段输入文件的稳定 JSON 结构。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set
import os

from analysis.symbol_id import make_file_id, make_relation_id, make_symbol_id


def _norm_path(path: Optional[str]) -> str:
    return os.path.normpath(str(path or "")).replace("\\", "/")


@dataclass
class LocationIR:
    file_path: str
    file_id: str
    line_start: int
    line_end: int
    column_start: int = 0
    column_end: int = 0


@dataclass
class SymbolIR:
    id: str
    kind: str
    name: str
    qualified_name: str
    file_id: str
    file_path: str
    line_start: int
    line_end: int
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    parent_class: Optional[str] = None
    interfaces: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    source_code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RelationIR:
    id: str
    source_id: str
    source_qn: str
    target_id: str
    target_qn: str
    relation_type: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _location_to_ir(source_location: Any) -> Optional[LocationIR]:
    if not source_location:
        return None
    file_path = _norm_path(getattr(source_location, "file_path", ""))
    if not file_path:
        return None
    return LocationIR(
        file_path=file_path,
        file_id=make_file_id(file_path),
        line_start=int(getattr(source_location, "line_start", 0) or 0),
        line_end=int(getattr(source_location, "line_end", 0) or 0),
        column_start=int(getattr(source_location, "column_start", 0) or 0),
        column_end=int(getattr(source_location, "column_end", 0) or 0),
    )


def _method_qualified_name(class_name: Optional[str], method_name: str) -> str:
    if class_name and class_name not in {"<module>", "module", ""}:
        return f"{class_name}.{method_name}"
    return method_name


def _module_name_from_file(project_path: str, file_path: str) -> str:
    normalized_project = _norm_path(project_path)
    normalized_file = _norm_path(file_path)
    try:
        rel_path = os.path.relpath(normalized_file, normalized_project)
    except Exception:
        rel_path = normalized_file
    rel_no_ext, _ = os.path.splitext(rel_path)
    module_name = rel_no_ext.replace("\\", ".").replace("/", ".").strip(".")
    return module_name or "module"


def _discover_python_files(project_path: str) -> List[str]:
    discovered: List[str] = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = sorted(
            [d for d in dirs if d not in ['.git', '__pycache__', '.venv', 'venv', 'node_modules', '.idea']]
        )
        for file_name in sorted(files):
            if file_name.endswith('.py'):
                discovered.append(_norm_path(os.path.join(root, file_name)))
    return discovered


def _build_resolution_indexes(symbols: List[SymbolIR]) -> tuple[Dict[str, List[SymbolIR]], Dict[str, Dict[str, List[SymbolIR]]]]:
    simple_name_index: Dict[str, List[SymbolIR]] = {}
    file_local_simple_index: Dict[str, Dict[str, List[SymbolIR]]] = {}
    for symbol in symbols:
        simple_name = symbol.qualified_name.split('.')[-1]
        simple_name_index.setdefault(simple_name, []).append(symbol)
        file_local_simple_index.setdefault(symbol.file_path, {}).setdefault(simple_name, []).append(symbol)
    return simple_name_index, file_local_simple_index


def _resolve_call_target(
    caller_symbol: SymbolIR,
    callee_qn: str,
    qn_to_symbol: Dict[str, SymbolIR],
    simple_name_index: Dict[str, List[SymbolIR]],
    file_local_simple_index: Dict[str, Dict[str, List[SymbolIR]]],
) -> tuple[Optional[SymbolIR], str]:
    direct = qn_to_symbol.get(callee_qn)
    if direct:
        return direct, "exact_qn"

    simple_name = str(callee_qn or "").split('.')[-1]
    if not simple_name:
        return None, "unresolved"

    same_file_candidates = file_local_simple_index.get(caller_symbol.file_path, {}).get(simple_name, [])
    if len(same_file_candidates) == 1:
        return same_file_candidates[0], "same_file_simple_name"

    unique_candidates = simple_name_index.get(simple_name, [])
    if len(unique_candidates) == 1:
        return unique_candidates[0], "global_unique_simple_name"

    return None, "unresolved"


def build_stage1_ir(project_path: str, analyzer_report: Any, call_graph: Dict[str, Set[str]]) -> Dict[str, Any]:
    project_path = _norm_path(project_path)
    files_index: Dict[str, Dict[str, Any]] = {}
    symbols: List[SymbolIR] = []
    relations: List[RelationIR] = []
    qn_to_symbol: Dict[str, SymbolIR] = {}
    call_graph_key_to_symbol: Dict[str, Optional[SymbolIR]] = {}

    def ensure_file(file_path: str) -> Dict[str, Any]:
        normalized = _norm_path(file_path)
        if normalized not in files_index:
            files_index[normalized] = {
                "id": make_file_id(normalized),
                "path": normalized,
            }
        return files_index[normalized]

    for discovered_file in _discover_python_files(project_path):
        ensure_file(discovered_file)

    # Classes + methods + fields
    for class_name, class_info in sorted((analyzer_report.classes or {}).items(), key=lambda item: item[0]):
        location = _location_to_ir(getattr(class_info, "source_location", None))
        if not location:
            continue
        file_info = ensure_file(location.file_path)
        class_qn = getattr(class_info, "full_name", None) or class_name
        class_id = make_symbol_id(
            file_path=location.file_path,
            line_start=location.line_start,
            line_end=location.line_end,
            kind="class",
            name=class_name,
        )
        class_symbol = SymbolIR(
            id=class_id,
            kind="class",
            name=class_name,
            qualified_name=class_qn,
            file_id=file_info["id"],
            file_path=location.file_path,
            line_start=location.line_start,
            line_end=location.line_end,
            parent_class=getattr(class_info, "parent_class", None),
            interfaces=list(getattr(class_info, "interfaces", []) or []),
            decorators=list(getattr(class_info, "decorators", []) or []),
            docstring=getattr(class_info, "docstring", None),
        )
        symbols.append(class_symbol)
        qn_to_symbol[class_qn] = class_symbol
        relations.append(
            RelationIR(
                id=make_relation_id(source_id=file_info["id"], target_id=class_id, relation_type="file_contains_class", file_path=location.file_path, line_number=location.line_start),
                source_id=file_info["id"],
                source_qn=file_info["path"],
                target_id=class_id,
                target_qn=class_qn,
                relation_type="file_contains_class",
                file_path=location.file_path,
                line_number=location.line_start,
            )
        )

        for field_name, field_info in sorted((getattr(class_info, "fields", {}) or {}).items(), key=lambda item: item[0]):
            field_loc = _location_to_ir(getattr(field_info, "source_location", None)) or location
            field_qn = f"{class_qn}.{field_name}"
            field_id = make_symbol_id(
                file_path=field_loc.file_path,
                line_start=field_loc.line_start,
                line_end=field_loc.line_end,
                kind="field",
                name=field_name,
                owner=class_qn,
            )
            field_symbol = SymbolIR(
                id=field_id,
                kind="field",
                name=field_name,
                qualified_name=field_qn,
                file_id=file_info["id"],
                file_path=field_loc.file_path,
                line_start=field_loc.line_start,
                line_end=field_loc.line_end,
                owner_id=class_id,
                owner_name=class_qn,
                docstring=getattr(field_info, "docstring", None),
                metadata={
                    "field_type": getattr(field_info, "field_type", None),
                    "default_value": getattr(field_info, "default_value", None),
                },
            )
            symbols.append(field_symbol)
            qn_to_symbol[field_qn] = field_symbol
            relations.append(
                RelationIR(
                    id=make_relation_id(source_id=class_id, target_id=field_id, relation_type="class_contains_field", file_path=field_loc.file_path, line_number=field_loc.line_start),
                    source_id=class_id,
                    source_qn=class_qn,
                    target_id=field_id,
                    target_qn=field_qn,
                    relation_type="class_contains_field",
                    file_path=field_loc.file_path,
                    line_number=field_loc.line_start,
                )
            )

        for method_name, method_info in sorted((getattr(class_info, "methods", {}) or {}).items(), key=lambda item: item[0]):
            method_loc = _location_to_ir(getattr(method_info, "source_location", None)) or location
            method_qn = _method_qualified_name(class_name, method_name)
            method_id = make_symbol_id(
                file_path=method_loc.file_path,
                line_start=method_loc.line_start,
                line_end=method_loc.line_end,
                kind="method",
                name=method_name,
                owner=class_qn,
            )
            method_symbol = SymbolIR(
                id=method_id,
                kind="method",
                name=method_name,
                qualified_name=method_qn,
                file_id=file_info["id"],
                file_path=method_loc.file_path,
                line_start=method_loc.line_start,
                line_end=method_loc.line_end,
                owner_id=class_id,
                owner_name=class_qn,
                parent_class=class_qn,
                decorators=list(getattr(method_info, "decorators", []) or []),
                parameters=[
                    {
                        "name": getattr(param, "name", ""),
                        "type": getattr(param, "param_type", None) or getattr(param, "type", None) or "Any",
                        "default_value": getattr(param, "default_value", None),
                        "position": idx,
                    }
                    for idx, param in enumerate(getattr(method_info, "parameters", []) or [])
                ],
                return_type=getattr(method_info, "return_type", None),
                docstring=getattr(method_info, "docstring", None),
                source_code=getattr(method_info, "source_code", None),
                metadata={
                    "modifiers": list(getattr(method_info, "modifiers", []) or []),
                    "cyclomatic_complexity": getattr(method_info, "cyclomatic_complexity", None),
                    "lines_of_code": getattr(method_info, "lines_of_code", None),
                },
            )
            symbols.append(method_symbol)
            qn_to_symbol[method_qn] = method_symbol
            call_graph_key_to_symbol[method_qn] = method_symbol
            relations.append(
                RelationIR(
                    id=make_relation_id(source_id=file_info["id"], target_id=method_id, relation_type="file_contains_method", file_path=method_loc.file_path, line_number=method_loc.line_start),
                    source_id=file_info["id"],
                    source_qn=file_info["path"],
                    target_id=method_id,
                    target_qn=method_qn,
                    relation_type="file_contains_method",
                    file_path=method_loc.file_path,
                    line_number=method_loc.line_start,
                )
            )
            relations.append(
                RelationIR(
                    id=make_relation_id(source_id=class_id, target_id=method_id, relation_type="class_contains_method", file_path=method_loc.file_path, line_number=method_loc.line_start),
                    source_id=class_id,
                    source_qn=class_qn,
                    target_id=method_id,
                    target_qn=method_qn,
                    relation_type="class_contains_method",
                    file_path=method_loc.file_path,
                    line_number=method_loc.line_start,
                )
            )

    # Global functions
    for func_info in sorted((getattr(analyzer_report, "functions", []) or []), key=lambda item: getattr(item, "signature", None) or getattr(item, "name", "")):
        func_name = getattr(func_info, "name", None) or "unknown"
        if getattr(func_info, "class_name", None) not in {None, "<module>", "module", ""}:
            # Already represented as class method above.
            continue
        location = _location_to_ir(getattr(func_info, "source_location", None))
        if not location:
            continue
        file_info = ensure_file(location.file_path)
        module_name = _module_name_from_file(project_path, location.file_path)
        func_qn = f"{module_name}.module.{func_name}"
        func_id = make_symbol_id(
            file_path=location.file_path,
            line_start=location.line_start,
            line_end=location.line_end,
            kind="function",
            name=func_name,
        )
        if func_qn in qn_to_symbol:
            continue
        func_symbol = SymbolIR(
            id=func_id,
            kind="function",
            name=func_name,
            qualified_name=func_qn,
            file_id=file_info["id"],
            file_path=location.file_path,
            line_start=location.line_start,
            line_end=location.line_end,
            decorators=list(getattr(func_info, "decorators", []) or []),
            parameters=[
                {
                    "name": getattr(param, "name", ""),
                    "type": getattr(param, "param_type", None) or getattr(param, "type", None) or "Any",
                    "default_value": getattr(param, "default_value", None),
                    "position": idx,
                }
                for idx, param in enumerate(getattr(func_info, "parameters", []) or [])
            ],
            return_type=getattr(func_info, "return_type", None),
            docstring=getattr(func_info, "docstring", None),
            source_code=getattr(func_info, "source_code", None),
            metadata={
                "modifiers": list(getattr(func_info, "modifiers", []) or []),
                "cyclomatic_complexity": getattr(func_info, "cyclomatic_complexity", None),
                "lines_of_code": getattr(func_info, "lines_of_code", None),
            },
        )
        symbols.append(func_symbol)
        qn_to_symbol[func_qn] = func_symbol
        existing_alias = call_graph_key_to_symbol.get(func_name)
        if existing_alias is None and func_name not in call_graph_key_to_symbol:
            call_graph_key_to_symbol[func_name] = func_symbol
        else:
            call_graph_key_to_symbol[func_name] = None
        relations.append(
            RelationIR(
                id=make_relation_id(source_id=file_info["id"], target_id=func_id, relation_type="file_contains_function", file_path=location.file_path, line_number=location.line_start),
                source_id=file_info["id"],
                source_qn=file_info["path"],
                target_id=func_id,
                target_qn=func_qn,
                relation_type="file_contains_function",
                file_path=location.file_path,
                line_number=location.line_start,
            )
        )

    simple_name_index, file_local_simple_index = _build_resolution_indexes(symbols)

    # Inheritance / implements
    for symbol in list(symbols):
        if symbol.kind != "class":
            continue
        if symbol.parent_class and symbol.parent_class in qn_to_symbol:
            target = qn_to_symbol[symbol.parent_class]
            relations.append(
                RelationIR(
                    id=make_relation_id(source_id=symbol.id, target_id=target.id, relation_type="inherits", file_path=symbol.file_path, line_number=symbol.line_start),
                    source_id=symbol.id,
                    source_qn=symbol.qualified_name,
                    target_id=target.id,
                    target_qn=target.qualified_name,
                    relation_type="inherits",
                    file_path=symbol.file_path,
                    line_number=symbol.line_start,
                )
            )
        for interface_name in symbol.interfaces:
            target_qn = interface_name
            target = qn_to_symbol.get(target_qn)
            if target:
                relations.append(
                    RelationIR(
                        id=make_relation_id(source_id=symbol.id, target_id=target.id, relation_type="implements", file_path=symbol.file_path, line_number=symbol.line_start),
                        source_id=symbol.id,
                        source_qn=symbol.qualified_name,
                        target_id=target.id,
                        target_qn=target.qualified_name,
                        relation_type="implements",
                        file_path=symbol.file_path,
                        line_number=symbol.line_start,
                    )
                )

    # Calls from adjacency map
    unresolved_targets: Set[str] = set()
    call_edge_count = 0
    for caller_qn in sorted((call_graph or {}).keys()):
        caller_symbol = qn_to_symbol.get(caller_qn) or call_graph_key_to_symbol.get(caller_qn)
        if not caller_symbol:
            continue
        callees = sorted(call_graph.get(caller_qn) or [])
        for callee_qn in callees:
            target_symbol, resolution_strategy = _resolve_call_target(
                caller_symbol,
                callee_qn,
                qn_to_symbol,
                simple_name_index,
                file_local_simple_index,
            )
            if not target_symbol:
                unresolved_targets.add(callee_qn)
                continue
            call_edge_count += 1
            relations.append(
                RelationIR(
                    id=make_relation_id(source_id=caller_symbol.id, target_id=target_symbol.id, relation_type="calls", file_path=caller_symbol.file_path, line_number=caller_symbol.line_start),
                    source_id=caller_symbol.id,
                    source_qn=caller_symbol.qualified_name,
                    target_id=target_symbol.id,
                    target_qn=target_symbol.qualified_name,
                    relation_type="calls",
                    file_path=caller_symbol.file_path,
                    line_number=caller_symbol.line_start,
                    metadata={
                        "raw_callee": callee_qn,
                        "resolution_strategy": resolution_strategy,
                    },
                )
            )

    # Deterministic ordering
    symbols_sorted = sorted(symbols, key=lambda item: (item.kind, item.qualified_name, item.file_path, item.line_start, item.id))
    relations_sorted = sorted(relations, key=lambda item: (item.relation_type, item.source_qn, item.target_qn, item.file_path or "", item.line_number or 0, item.id))
    files_sorted = sorted(files_index.values(), key=lambda item: item["path"])

    file_count = len(files_sorted)
    symbol_counts: Dict[str, int] = {}
    for item in symbols_sorted:
        symbol_counts[item.kind] = symbol_counts.get(item.kind, 0) + 1

    return {
        "schema_version": "stage1.v1",
        "project": {
            "name": getattr(analyzer_report, "project_name", "unknown_project"),
            "path": project_path,
            "total_files": int(getattr(analyzer_report, "total_files", 0) or 0),
            "total_lines_of_code": int(getattr(analyzer_report, "total_lines_of_code", 0) or 0),
        },
        "summary": {
            "file_count": file_count,
            "symbol_count": len(symbols_sorted),
            "relation_count": len(relations_sorted),
            "call_edge_count": call_edge_count,
            "unresolved_call_target_count": len(unresolved_targets),
            "symbol_counts_by_kind": symbol_counts,
        },
        "files": files_sorted,
        "symbols": [asdict(item) for item in symbols_sorted],
        "relations": [asdict(item) for item in relations_sorted],
        "call_graph": {
            "adjacency": {caller: sorted(list(callees)) for caller, callees in sorted((call_graph or {}).items(), key=lambda item: item[0])},
            "unresolved_targets": sorted(unresolved_targets),
        },
    }
