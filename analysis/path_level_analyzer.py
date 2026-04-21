#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
路径级别分析器 - 为每个叶子节点路径生成CFG、DFG和数据流图
"""

from typing import Dict, List, Set, Optional, Any
import logging
import json

from .cfg_generator import CFGGenerator, ControlFlowGraph
from .dfg_generator import DFGGenerator, DataFlowGraph
from .partition_control_flow_generator import PartitionControlFlowGenerator
from .partition_data_flow_generator import PartitionDataFlowGenerator

logger = logging.getLogger(__name__)


def _mermaid_safe_id(raw: str) -> str:
    return _dot_safe_id(raw)


def _mermaid_safe_label(raw: Any) -> str:
    text = str(raw or '').replace('"', '\\"')
    return text.replace('\n', '<br/>')


def _normalize_type_label(raw: Any, fallback: str) -> str:
    text = str(raw or '').strip()
    if not text or text.lower() in {'none', 'void'}:
        return fallback
    return text


def _resolve_path_method_info(method_sig: str, analyzer_report):
    if not analyzer_report or not method_sig:
        return None
    if '.' in method_sig:
        class_name, method_name = method_sig.rsplit('.', 1)
        if class_name in analyzer_report.classes:
            class_info = analyzer_report.classes[class_name]
            if method_name in class_info.methods:
                return class_info.methods[method_name]
    for func_info in getattr(analyzer_report, 'functions', []) or []:
        if func_info.name == method_sig or getattr(func_info, 'signature', None) == method_sig:
            return func_info
    return None


def _build_path_method_io_list(
    path: List[str],
    analyzer_report,
    inputs: Optional[List[Dict[str, Any]]] = None,
    outputs: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    methods_info: List[Dict[str, Any]] = []
    inputs = inputs or []
    outputs = outputs or []

    for index, method_sig in enumerate(path):
        method_info = _resolve_path_method_info(method_sig, analyzer_report)
        method_inputs = [
            {
                'name': inp.get('parameter_name', 'data'),
                'type': _normalize_type_label(inp.get('parameter_type'), 'Any'),
            }
            for inp in inputs
            if inp.get('method_signature') == method_sig
        ]
        method_outputs = [
            {
                'type': _normalize_type_label(out.get('return_type'), '结果'),
            }
            for out in outputs
            if out.get('method_signature') == method_sig
        ]

        if method_info and not method_inputs:
            for param in getattr(method_info, 'parameters', []) or []:
                param_name = getattr(param, 'name', '') or 'data'
                param_type = _normalize_type_label(getattr(param, 'param_type', None) or getattr(param, 'type', None), 'Any')
                method_inputs.append({'name': param_name, 'type': param_type})

        if method_info and not method_outputs:
            return_type = _normalize_type_label(getattr(method_info, 'return_type', None), '结果')
            if return_type:
                method_outputs.append({'type': return_type})

        if index == 0 and not method_inputs:
            method_inputs.append({'name': 'data', 'type': 'Any'})
        if index < len(path) - 1 and not method_outputs:
            method_outputs.append({'type': 'Any'})
        if index == len(path) - 1 and not method_outputs:
            method_outputs.append({'type': '结果'})

        methods_info.append({
            'signature': method_sig,
            'name': method_sig.split('.')[-1] if '.' in method_sig else method_sig,
            'inputs': method_inputs,
            'outputs': method_outputs,
        })

    return methods_info


def _build_path_dataflow_mermaid(
    path: List[str],
    methods_info: List[Dict[str, Any]],
    path_dfg: Optional[Dict[str, Any]] = None,
) -> str:
    mermaid_lines = ['graph LR']
    seen_nodes: Set[str] = set()
    parameter_flow_map: Dict[tuple, List[str]] = {}
    return_flow_map: Dict[tuple, List[str]] = {}

    for flow in (path_dfg or {}).get('parameter_flows', []) or []:
        if not isinstance(flow, dict):
            continue
        key = (flow.get('source'), flow.get('target'))
        label = str(flow.get('parameter') or '参数').strip() or '参数'
        parameter_flow_map.setdefault(key, []).append(label)

    for flow in (path_dfg or {}).get('return_flows', []) or []:
        if not isinstance(flow, dict):
            continue
        key = (flow.get('source'), flow.get('target'))
        label = str(flow.get('return_value') or '返回值').strip() or '返回值'
        return_flow_map.setdefault(key, []).append(label)

    def add_node(node_id: str, label: str, shape: str = '["{label}"]'):
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        escaped_label = _mermaid_safe_label(label)
        mermaid_lines.append(f'    {node_id}{shape.format(label=escaped_label)}')

    for index, method in enumerate(methods_info):
        method_sig = method.get('signature') or ''
        method_id = f'M{index}'
        add_node(method_id, method.get('name') or method_sig)

        if index == 0:
            for input_index, method_input in enumerate(method.get('inputs') or []):
                input_id = f'I_{index}_{input_index}'
                input_name = method_input.get('name', 'data')
                input_type = _normalize_type_label(method_input.get('type'), 'Any')
                add_node(input_id, f'输入: {input_name} : {input_type}', '(["{label}"])')
                mermaid_lines.append(f'    {input_id} -->|输入| {method_id}')

        if index < len(methods_info) - 1:
            next_method = methods_info[index + 1]
            data_id = f'D_{index}'
            output_types = [
                _normalize_type_label(item.get('type'), 'Any')
                for item in (method.get('outputs') or [])
            ]
            data_label = ' / '.join(dict.fromkeys(output_types)) if output_types else 'Any'
            add_node(data_id, f'中间数据: {data_label}', '(["{label}"])')
            mermaid_lines.append(f'    {method_id} -->|输出| {data_id}')

            flow_key = (method_sig, next_method.get('signature'))
            param_labels = ' / '.join(dict.fromkeys(parameter_flow_map.get(flow_key, [])))
            edge_label = f'输入: {param_labels}' if param_labels else '输入'
            mermaid_lines.append(f'    {data_id} -->|{_mermaid_safe_label(edge_label)}| M{index + 1}')
        else:
            output_types = [
                _normalize_type_label(item.get('type'), '结果')
                for item in (method.get('outputs') or [])
            ]
            output_label = ' / '.join(dict.fromkeys(output_types)) if output_types else '结果'
            output_id = 'O_FINAL'
            add_node(output_id, f'最终输出: {output_label}', '(["{label}"])')
            mermaid_lines.append(f'    {method_id} -->|输出| {output_id}')

    for index in range(len(methods_info) - 1):
        current_method = methods_info[index]
        next_method = methods_info[index + 1]
        return_key = (next_method.get('signature'), current_method.get('signature'))
        return_labels = ' / '.join(dict.fromkeys(return_flow_map.get(return_key, [])))
        if return_labels:
            mermaid_lines.append(f'    M{index + 1} -.->|返回: {_mermaid_safe_label(return_labels)}| M{index}')

    return '\n'.join(mermaid_lines)

def _dot_safe_id(raw: str) -> str:
    """
    将任意字符串转换为 DOT 安全的节点/边 id（保证同一个 raw 产生同一个结果）。
    注意：DOT 中即便使用引号也能包含特殊字符，但本项目里还会做 replace('.')，
    容易导致“节点定义ID”和“边引用ID”不一致，所以统一做一次规范化。
    """
    if raw is None:
        return "null"
    s = str(raw)
    out = []
    for ch in s:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    # 避免出现空字符串
    safe = "".join(out).strip("_")
    return safe or "id"


def generate_path_level_cfg(
    path: List[str],
    call_graph: Dict[str, Set[str]],
    analyzer_report,
    partition_methods: Set[str],
    inputs: Optional[List[Dict]] = None,
    outputs: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """
    为一条路径生成功能层级的CFG（控制流图）
    
    Args:
        path: 路径节点列表（方法签名）
        call_graph: 调用图
        analyzer_report: 代码分析报告
        partition_methods: 分区方法集合
        inputs: 输入参数汇总
        outputs: 返回值汇总
        
    Returns:
        路径级别的CFG数据
    """
    try:
        cfg_generator = CFGGenerator()
        partition_cfg_generator = PartitionControlFlowGenerator(call_graph, analyzer_report)
        
        # 为路径上的每个方法生成CFG
        path_cfgs = {}
        path_nodes = {}
        path_edges = []
        
        for method_sig in path:
            if method_sig not in partition_methods:
                continue
                
            # 获取方法源代码
            method_info = None
            if '.' in method_sig:
                class_name, method_name = method_sig.rsplit('.', 1)
                if analyzer_report and class_name in analyzer_report.classes:
                    class_info = analyzer_report.classes[class_name]
                    if method_name in class_info.methods:
                        method_info = class_info.methods[method_name]
            else:
                # 全局函数
                if analyzer_report:
                    for func_info in analyzer_report.functions:
                        if func_info.name == method_sig or func_info.signature == method_sig:
                            method_info = func_info
                            break
            
            if method_info and hasattr(method_info, 'source_code') and method_info.source_code:
                # 生成方法级别的CFG
                method_cfg = cfg_generator.generate_cfg(method_info.source_code, method_sig)
                if method_cfg and method_cfg.nodes:
                    path_cfgs[method_sig] = method_cfg
                    
                    # 收集节点和边
                    for node_id, node in method_cfg.nodes.items():
                        # 添加路径前缀避免冲突
                        path_node_id = f"{method_sig}_{node_id}"
                        path_nodes[path_node_id] = {
                            'id': path_node_id,
                            'label': f"{method_sig.split('.')[-1]}: {node.label}",
                            'type': node.node_type,
                            'line_number': node.line_number,
                            'code': node.code[:100] if node.code else "",
                            'method': method_sig
                        }
                    
                    for edge in method_cfg.edges:
                        path_edges.append({
                            'source': f"{method_sig}_{edge.source_id}",
                            'target': f"{method_sig}_{edge.target_id}",
                            'type': edge.edge_type,
                            'method': method_sig
                        })
        
        # 添加方法间的调用边
        for i in range(len(path) - 1):
            caller = path[i]
            callee = path[i + 1]
            if caller in path_cfgs and callee in path_cfgs:
                # 更“有联系”的组合方式：
                # 1) 优先把调用边从 caller 内部的“调用点（callsite）”连到 callee.entry
                # 2) 再把 callee.exit 连回 caller 的“调用点后继节点（after_call）”
                # 若找不到调用点，则退化为 caller.exit -> callee.entry

                caller_cfg = path_cfgs[caller]
                callee_cfg = path_cfgs[callee]

                # 找 callee.entry / callee.exit
                callee_entry = None
                callee_exit = None
                for node_id, node in callee_cfg.nodes.items():
                    if node.node_type == 'entry':
                        callee_entry = f"{callee}_{node_id}"
                    elif node.node_type == 'exit':
                        callee_exit = f"{callee}_{node_id}"
                    if callee_entry and callee_exit:
                        break

                if not callee_entry:
                    continue

                # 通过代码片段启发式定位 caller 中的调用点（statement 节点里包含 callee 名称）
                callee_short = callee.split('.')[-1] if '.' in callee else callee
                callsite_node_id = None  # caller_cfg 内部 node_id（不带 method 前缀）
                callsite_line = 10**9
                for node_id, node in caller_cfg.nodes.items():
                    if node.node_type != 'statement':
                        continue
                    code = (node.code or "")
                    # 既支持 foo( 也支持 obj.foo(
                    if f"{callee_short}(" in code or f".{callee_short}(" in code:
                        ln = node.line_number or 0
                        if ln < callsite_line:
                            callsite_line = ln
                            callsite_node_id = node_id

                callsite = f"{caller}_{callsite_node_id}" if callsite_node_id else None

                # 找调用点的后继节点（caller_cfg.edges 中 callsite -> next）
                after_call = None
                if callsite_node_id:
                    for e in caller_cfg.edges:
                        if e.source_id == callsite_node_id:
                            after_call = f"{caller}_{e.target_id}"
                            break

                # fallback：caller.exit
                caller_exit = None
                for node_id, node in caller_cfg.nodes.items():
                    if node.node_type == 'exit':
                        caller_exit = f"{caller}_{node_id}"
                        break

                # 1) 调用边：callsite/exit -> callee.entry
                path_edges.append({
                    'source': callsite or caller_exit or f"{caller}_{list(caller_cfg.nodes.keys())[0]}",
                    'target': callee_entry,
                    'type': 'method_call',
                    'caller': caller,
                    'callee': callee
                })

                # 2) 返回边：callee.exit -> after_call（如果可得）
                if callee_exit and after_call:
                    path_edges.append({
                        'source': callee_exit,
                        'target': after_call,
                        'type': 'return',
                        'caller': caller,
                        'callee': callee
                    })
        
        # 添加输入参数信息到CFG
        input_info = {}
        if inputs:
            for input_item in inputs:
                method_sig = input_item.get('method_signature', '')
                if method_sig in path:
                    if method_sig not in input_info:
                        input_info[method_sig] = []
                    input_info[method_sig].append({
                        'name': input_item.get('parameter_name', ''),
                        'type': input_item.get('parameter_type', '')
                    })
        
        # 添加返回值信息到CFG
        output_info = {}
        if outputs:
            for output_item in outputs:
                method_sig = output_item.get('method_signature', '')
                if method_sig in path:
                    output_info[method_sig] = output_item.get('return_type', '')
        
        # 生成DOT格式（重要：统一使用 safe_id，避免节点与边ID不一致导致图“断开/像拼接”）
        dot_lines = ['digraph PathCFG {', '  rankdir=TB;', '  node [shape=box];']
        id_map: Dict[str, str] = {}  # original_id -> safe_id
        def sid(x: str) -> str:
            if x not in id_map:
                id_map[x] = _dot_safe_id(x)
            return id_map[x]
        
        # 添加输入节点
        if input_info:
            dot_lines.append('  subgraph cluster_inputs {')
            dot_lines.append('    label="输入参数";')
            dot_lines.append('    style=dashed;')
            for method_sig, params in input_info.items():
                for param in params:
                    input_raw = f"input_{method_sig}_{param['name']}"
                    input_id = sid(input_raw)
                    dot_lines.append(f'    "{input_id}" [label="{param["name"]}: {param["type"]}", shape=ellipse, color=blue];')
            dot_lines.append('  }')
        
        # 添加节点
        for node_id, node_data in path_nodes.items():
            safe_node_id = sid(node_id)
            label = node_data['label'].replace('"', '\\"')
            dot_lines.append(f'  "{safe_node_id}" [label="{label}"];')
        
        # 添加边
        for edge in path_edges:
            source = sid(edge['source'])
            target = sid(edge['target'])
            edge_attr = ""
            if edge['type'] == 'method_call':
                edge_attr = ' [label="调用", color=red, style=bold]'
            elif edge['type'] == 'return':
                edge_attr = ' [label="返回", color=purple, style=dashed]'
            elif edge['type'] == 'true':
                edge_attr = ' [label="True", color=green]'
            elif edge['type'] == 'false':
                edge_attr = ' [label="False", color=orange]'
            dot_lines.append(f'  "{source}" -> "{target}"{edge_attr};')
        
        # 添加输出节点
        if output_info:
            dot_lines.append('  subgraph cluster_outputs {')
            dot_lines.append('    label="返回值";')
            dot_lines.append('    style=dashed;')
            for method_sig, return_type in output_info.items():
                output_raw = f"output_{method_sig}"
                output_id = sid(output_raw)
                dot_lines.append(f'    "{output_id}" [label="返回: {return_type}", shape=ellipse, color=green];')
            dot_lines.append('  }')
        
        dot_lines.append('}')
        dot_content = '\n'.join(dot_lines)
        
        return {
            'path': path,
            'nodes': path_nodes,
            'edges': path_edges,
            'input_info': input_info,
            'output_info': output_info,
            'dot': dot_content,
            'method_cfgs': {k: v.to_json() for k, v in path_cfgs.items()}
        }
        
    except Exception as e:
        logger.error(f"[PathLevelAnalyzer] 生成路径CFG失败: {e}", exc_info=True)
        return {
            'path': path,
            'nodes': {},
            'edges': [],
            'input_info': {},
            'output_info': {},
            'dot': f'digraph PathCFG {{ label="生成失败: {str(e)}"; }}',
            'error': str(e)
        }


def generate_path_level_dfg(
    path: List[str],
    call_graph: Dict[str, Set[str]],
    analyzer_report,
    partition_methods: Set[str],
    dataflow_analyzer=None
) -> Dict[str, Any]:
    """
    为一条路径生成功能层级的DFG（数据流图）
    
    Args:
        path: 路径节点列表（方法签名）
        call_graph: 调用图
        analyzer_report: 代码分析报告
        partition_methods: 分区方法集合
        dataflow_analyzer: 数据流分析器
        
    Returns:
        路径级别的DFG数据
    """
    try:
        dfg_generator = DFGGenerator()
        
        # 为路径上的每个方法生成DFG
        path_dfgs = {}
        path_nodes = {}
        path_edges = []

        # 额外：为每个方法加一个“方法汇总节点”，用于承接跨方法的参数/返回值流（更直观，也避免边连不到节点）
        method_summary_nodes: Dict[str, str] = {}  # method_sig -> node_id
        
        for method_sig in path:
            if method_sig not in partition_methods:
                continue

            # 方法汇总节点
            method_node_id = f"method_{method_sig}"
            method_summary_nodes[method_sig] = method_node_id
            short = method_sig.split('.')[-1] if '.' in method_sig else method_sig
            path_nodes[method_node_id] = {
                'id': method_node_id,
                'label': f"【方法】{short}",
                'type': 'method',
                'variable': '',
                'method': method_sig
            }
                
            # 获取方法源代码
            method_info = None
            if '.' in method_sig:
                class_name, method_name = method_sig.rsplit('.', 1)
                if analyzer_report and class_name in analyzer_report.classes:
                    class_info = analyzer_report.classes[class_name]
                    if method_name in class_info.methods:
                        method_info = class_info.methods[method_name]
            else:
                # 全局函数
                if analyzer_report:
                    for func_info in analyzer_report.functions:
                        if func_info.name == method_sig or func_info.signature == method_sig:
                            method_info = func_info
                            break
            
            if method_info and hasattr(method_info, 'source_code') and method_info.source_code:
                # 生成方法级别的DFG
                method_dfg = dfg_generator.generate_dfg(method_info.source_code, method_sig)
                if method_dfg and method_dfg.nodes:
                    path_dfgs[method_sig] = method_dfg
                    
                    # 收集节点和边
                    for node_id, node in method_dfg.nodes.items():
                        path_node_id = f"{method_sig}_{node_id}"
                        # DFGNode使用variable_name而不是label
                        variable_label = f"{node.variable_name} ({node.node_type})" if hasattr(node, 'variable_name') else f"{node.node_type}"
                        method_short_name = method_sig.split('.')[-1] if '.' in method_sig else method_sig
                        path_nodes[path_node_id] = {
                            'id': path_node_id,
                            'label': f"{method_short_name}: {variable_label}",
                            'type': node.node_type,
                            'variable': node.variable_name if hasattr(node, 'variable_name') else '',
                            'method': method_sig
                        }

                        # 把变量节点挂到“方法汇总节点”下，便于读图（虚线，不表示真实数据流）
                        if method_sig in method_summary_nodes:
                            path_edges.append({
                                'source': method_summary_nodes[method_sig],
                                'target': path_node_id,
                                'variable': '',
                                'method': method_sig,
                                'edge_kind': 'contains'
                            })
                    
                    for edge in method_dfg.edges:
                        path_edges.append({
                            'source': f"{method_sig}_{edge.source_id}",
                            'target': f"{method_sig}_{edge.target_id}",
                            'variable': edge.variable_name if hasattr(edge, 'variable_name') else '',
                            'method': method_sig
                        })
        
        # 添加方法间的参数流动（只考虑分区内的调用关系）
        parameter_flows = []
        return_flows = []
        
        if dataflow_analyzer:
            for i in range(len(path) - 1):
                caller = path[i]
                callee = path[i + 1]
                
                # ✅ 确保caller和callee都在分区内（虽然路径本身已经限制在分区内，但为了安全起见，再次检查）
                if caller not in partition_methods or callee not in partition_methods:
                    continue
                
                # 查找参数流动
                if hasattr(dataflow_analyzer, 'parameter_flows'):
                    for flow in dataflow_analyzer.parameter_flows:
                        if flow[0] == caller and flow[2] == callee:
                            parameter_flows.append({
                                'source': caller,
                                'target': callee,
                                'parameter': flow[1] if len(flow) > 1 else ''
                            })
                
                # 查找返回值流动
                if hasattr(dataflow_analyzer, 'return_value_flows'):
                    for flow in dataflow_analyzer.return_value_flows:
                        if flow[0] == callee and flow[2] == caller:
                            return_flows.append({
                                'source': callee,
                                'target': caller,
                                'return_value': flow[1] if len(flow) > 1 else ''
                            })

        # 将“参数/返回值流动”落到具体节点上（尽量连到变量 def/use），否则退化为方法汇总节点之间的连线
        inter_edges: List[Dict[str, Any]] = []

        # 建索引：method_sig -> variable_name -> (last_def_node_id, first_use_node_id)
        def_index: Dict[str, Dict[str, str]] = {}
        use_index: Dict[str, Dict[str, str]] = {}
        for ms, dfg in path_dfgs.items():
            def_index[ms] = {}
            use_index[ms] = {}
            # 依据 line_number：last def / first use
            last_def_line: Dict[str, int] = {}
            first_use_line: Dict[str, int] = {}
            for nid, node in dfg.nodes.items():
                v = getattr(node, 'variable_name', None)
                if not v:
                    continue
                ln = getattr(node, 'line_number', 0) or 0
                if getattr(node, 'node_type', '') == 'def':
                    if v not in last_def_line or ln >= last_def_line[v]:
                        last_def_line[v] = ln
                        def_index[ms][v] = f"{ms}_{nid}"
                elif getattr(node, 'node_type', '') == 'use':
                    if v not in first_use_line or ln <= first_use_line[v]:
                        first_use_line[v] = ln
                        use_index[ms][v] = f"{ms}_{nid}"

        # 参数：caller(var def) -> callee(var use)
        for flow in parameter_flows:
            caller = flow['source']
            callee = flow['target']
            param = (flow.get('parameter') or '').strip()
            if not caller or not callee:
                continue
            src = None
            tgt = None
            if param:
                src = def_index.get(caller, {}).get(param)
                tgt = use_index.get(callee, {}).get(param)
            if not src:
                src = method_summary_nodes.get(caller)
            if not tgt:
                tgt = method_summary_nodes.get(callee)
            if src and tgt:
                inter_edges.append({
                    'source': src,
                    'target': tgt,
                    'label': f"参数: {param}" if param else "参数",
                    'kind': 'param_flow'
                })

        # 返回值：callee(def return?) -> caller(use?)。这里没有显式 return 变量名时，退化为方法节点连线
        for flow in return_flows:
            src_m = flow['source']  # callee
            tgt_m = flow['target']  # caller
            rv = (flow.get('return_value') or '').strip()
            src = method_summary_nodes.get(src_m)
            tgt = method_summary_nodes.get(tgt_m)
            if src and tgt:
                inter_edges.append({
                    'source': src,
                    'target': tgt,
                    'label': f"返回: {rv}" if rv else "返回值",
                    'kind': 'return_flow'
                })
        
        # 生成DOT格式（重要：统一使用 safe_id，避免节点与边ID不一致导致图“断开/像拼接”）
        dot_lines = ['digraph PathDFG {', '  rankdir=LR;', '  node [shape=box];']
        id_map: Dict[str, str] = {}
        def sid(x: str) -> str:
            if x not in id_map:
                id_map[x] = _dot_safe_id(x)
            return id_map[x]
        
        # 添加节点
        for node_id, node_data in path_nodes.items():
            safe_node_id = sid(node_id)
            label = node_data['label'].replace('"', '\\"')
            dot_lines.append(f'  "{safe_node_id}" [label="{label}"];')
        
        # 添加数据流边（方法内 + contains）
        for edge in path_edges:
            source = sid(edge['source'])
            target = sid(edge['target'])
            if edge.get('edge_kind') == 'contains':
                dot_lines.append(f'  "{source}" -> "{target}" [style=dotted, color="#999", label="包含"];')
                continue
            var_label = f' [label="{edge.get("variable", "")}"]' if edge.get('variable') else ''
            dot_lines.append(f'  "{source}" -> "{target}"{var_label};')
        
        # 添加跨方法参数/返回值流动边（优先变量节点，其次方法汇总节点）
        for e in inter_edges:
            source = sid(e['source'])
            target = sid(e['target'])
            label = (e.get('label') or '').replace('"', '\\"')
            if e.get('kind') == 'param_flow':
                dot_lines.append(f'  "{source}" -> "{target}" [label="{label}", color=blue, style=dashed, penwidth=2];')
            else:
                dot_lines.append(f'  "{source}" -> "{target}" [label="{label}", color=green, style=dashed, penwidth=2];')
        
        dot_lines.append('}')
        dot_content = '\n'.join(dot_lines)
        
        return {
            'path': path,
            'nodes': path_nodes,
            'edges': path_edges,
            'parameter_flows': parameter_flows,
            'return_flows': return_flows,
            'dot': dot_content,
            'method_dfgs': {k: v.to_json() for k, v in path_dfgs.items()}
        }
        
    except Exception as e:
        logger.error(f"[PathLevelAnalyzer] 生成路径DFG失败: {e}", exc_info=True)
        return {
            'path': path,
            'nodes': {},
            'edges': [],
            'parameter_flows': [],
            'return_flows': [],
            'dot': f'digraph PathDFG {{ label="生成失败: {str(e)}"; }}',
            'error': str(e)
        }


def generate_path_level_dataflow_mermaid(
    path: List[str],
    call_graph: Dict[str, Set[str]],
    analyzer_report,
    partition_methods: Set[str],
    inputs: Optional[List[Dict]] = None,
    outputs: Optional[List[Dict]] = None,
    llm_agent=None,
    path_dfg: Optional[Dict[str, Any]] = None,
) -> str:
    """
    使用LLM为一条路径生成mermaid格式的数据流图
    
    Args:
        path: 路径节点列表（方法签名）
        call_graph: 调用图
        analyzer_report: 代码分析报告
        partition_methods: 分区方法集合
        inputs: 输入参数汇总
        outputs: 返回值汇总
        llm_agent: LLM代理对象
        
    Returns:
        mermaid格式的数据流图代码
    """
    try:
        methods_info = _build_path_method_io_list(
            path=path,
            analyzer_report=analyzer_report,
            inputs=inputs,
            outputs=outputs,
        )
        return _build_path_dataflow_mermaid(path, methods_info, path_dfg=path_dfg)
        
    except Exception as e:
        logger.error(f"[PathLevelAnalyzer] 生成路径数据流图失败: {e}", exc_info=True)
        methods_info = _build_path_method_io_list(
            path=path,
            analyzer_report=analyzer_report,
            inputs=inputs,
            outputs=outputs,
        )
        return _build_path_dataflow_mermaid(path, methods_info, path_dfg=path_dfg)
