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
    inputs: List[Dict] = None,
    outputs: List[Dict] = None
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
    inputs: List[Dict] = None,
    outputs: List[Dict] = None,
    llm_agent=None
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
        if not llm_agent:
            # 如果没有LLM，生成简单的mermaid图
            mermaid_lines = ['graph LR']
            for i, method_sig in enumerate(path):
                method_name = method_sig.split('.')[-1] if '.' in method_sig else method_sig
                node_id = f"M{i}"
                mermaid_lines.append(f'    {node_id}["{method_name}"]')
                if i > 0:
                    mermaid_lines.append(f'    M{i-1} --> M{i}')
            return '\n'.join(mermaid_lines)
        
        # 收集路径上的方法信息
        methods_info = []
        for method_sig in path:
            method_info = None
            if '.' in method_sig:
                class_name, method_name = method_sig.rsplit('.', 1)
                if analyzer_report and class_name in analyzer_report.classes:
                    class_info = analyzer_report.classes[class_name]
                    if method_name in class_info.methods:
                        method_info = class_info.methods[method_name]
            else:
                if analyzer_report:
                    for func_info in analyzer_report.functions:
                        if func_info.name == method_sig or func_info.signature == method_sig:
                            method_info = func_info
                            break
            
            if method_info:
                method_data = {
                    'signature': method_sig,
                    'name': method_sig.split('.')[-1] if '.' in method_sig else method_sig,
                    'source_code': getattr(method_info, 'source_code', '')[:500] if hasattr(method_info, 'source_code') else '',
                    'docstring': getattr(method_info, 'docstring', '') or ''
                }
                
                # 添加参数信息
                if inputs:
                    method_data['inputs'] = [
                        {'name': inp.get('parameter_name'), 'type': inp.get('parameter_type')}
                        for inp in inputs if inp.get('method_signature') == method_sig
                    ]
                
                # 添加返回值信息
                if outputs:
                    method_data['output'] = next(
                        (out.get('return_type') for out in outputs if out.get('method_signature') == method_sig),
                        None
                    )
                
                methods_info.append(method_data)
        
        # 构建LLM提示
        system_prompt = """你是一个代码分析专家，擅长生成数据流图。

请根据给定的方法调用路径，生成一个mermaid格式的数据流图。

要求：
1. 使用graph LR格式（从左到右）
2. 每个方法作为一个节点，节点标签使用简短的方法名
3. 显示方法间的数据流动（参数传递、返回值传递）
4. 如果有输入参数，在节点上标注输入
5. 如果有返回值，在边上标注返回值类型
6. 只返回mermaid代码，不要其他解释

mermaid格式示例：
graph LR
    A["方法A<br/>输入: param1: str"] -->|"返回: int"| B["方法B"]
    B -->|"返回: bool"| C["方法C"]
"""
        
        user_prompt = f"""请为以下方法调用路径生成mermaid数据流图：

路径：{' -> '.join([m['name'] for m in methods_info])}

方法详情：
{json.dumps(methods_info, indent=2, ensure_ascii=False)}

请生成mermaid代码："""
        
        # 调用LLM
        if hasattr(llm_agent, 'llm') and llm_agent.llm:
            from langchain_core.messages import SystemMessage, HumanMessage
            response = llm_agent.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            mermaid_code = response.content.strip()
        elif hasattr(llm_agent, '_call_api_directly'):
            mermaid_code = llm_agent._call_api_directly(system_prompt, user_prompt).strip()
        else:
            # 回退到简单生成
            mermaid_lines = ['graph LR']
            for i, method in enumerate(methods_info):
                method_name = method['name']
                node_id = f"M{i}"
                input_text = ""
                if method.get('inputs'):
                    input_list = []
                    for inp in method['inputs']:
                        inp_name = inp.get('name', '')
                        inp_type = inp.get('type', '')
                        input_list.append(f'{inp_name}: {inp_type}')
                    input_text = "<br/>输入: " + ', '.join(input_list)
                mermaid_lines.append(f'    {node_id}["{method_name}{input_text}"]')
                if i > 0:
                    output_text = ""
                    if methods_info[i-1].get('output'):
                        output_value = methods_info[i-1]["output"]
                        output_text = f'|"返回: {output_value}"|'
                    mermaid_lines.append(f'    M{i-1} {output_text}--> M{i}')
            mermaid_code = '\n'.join(mermaid_lines)
        
        # 验证mermaid代码格式
        if not mermaid_code.startswith('graph'):
            # 如果不是有效的mermaid代码，回退到简单生成
            mermaid_lines = ['graph LR']
            for i, method in enumerate(methods_info):
                method_name = method['name']
                node_id = f"M{i}"
                mermaid_lines.append(f'    {node_id}["{method_name}"]')
                if i > 0:
                    mermaid_lines.append(f'    M{i-1} --> M{i}')
            mermaid_code = '\n'.join(mermaid_lines)
        
        return mermaid_code
        
    except Exception as e:
        logger.error(f"[PathLevelAnalyzer] 生成路径数据流图失败: {e}", exc_info=True)
        # 回退到简单生成
        mermaid_lines = ['graph LR']
        for i, method_sig in enumerate(path):
            method_name = method_sig.split('.')[-1] if '.' in method_sig else method_sig
            node_id = f"M{i}"
            mermaid_lines.append(f'    {node_id}["{method_name}"]')
            if i > 0:
                mermaid_lines.append(f'    M{i-1} --> M{i}')
        return '\n'.join(mermaid_lines)

