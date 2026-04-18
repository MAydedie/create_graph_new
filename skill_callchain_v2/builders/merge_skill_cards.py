from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump") and callable(value.model_dump):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dict(dumped)
    if hasattr(value, "dict") and callable(value.dict):
        dumped = value.dict()
        if isinstance(dumped, dict):
            return dict(dumped)
    if is_dataclass(value) and not isinstance(value, type):
        try:
            dumped = asdict(value)
        except TypeError:
            dumped = None
        if isinstance(dumped, dict):
            return dumped
    if hasattr(value, "__dict__"):
        return {
            key: field_value
            for key, field_value in vars(value).items()
            if not key.startswith("_")
        }
    return {}


def _dedupe_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _stringify(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _group_by_partition(items: list[Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        payload = _to_plain_dict(item)
        partition_id = _stringify(payload.get("partition_id"))
        if not partition_id:
            continue
        grouped.setdefault(partition_id, []).append(payload)
    return grouped


def _dedupe_path_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, tuple[str, ...], str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        function_chain = tuple(_dedupe_strings(item.get("function_chain") or []))
        key = (
            _stringify(item.get("path_id")),
            function_chain,
            _stringify(item.get("leaf_node")),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized = dict(item)
        normalized["function_chain"] = list(function_chain)
        result.append(normalized)
    result.sort(key=lambda item: (-float(item.get("worthiness_score") or 0.0), _stringify(item.get("path_id"))))
    return result


def _dedupe_code_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        line_value = item.get("line")
        key = (
            _stringify(item.get("symbol")),
            _stringify(item.get("file_path")),
            _stringify(line_value),
            _stringify(item.get("kind")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(item))
    result.sort(
        key=lambda item: (
            _stringify(item.get("file_path")),
            int(item.get("line") or 0),
            _stringify(item.get("symbol")),
        )
    )
    return result


def _build_method_call_chain(path_items: list[dict[str, Any]], methods: list[str]) -> list[str]:
    best_chain: list[str] = []
    best_score = -1
    for item in path_items:
        raw_chain = _dedupe_strings(item.get("function_chain") or [])
        chain = _normalize_chain(raw_chain)
        if not chain:
            continue
        rich_count = sum(1 for symbol in chain if _is_meaningful_symbol(symbol))
        score = rich_count * 10 + len(chain)
        if score > best_score:
            best_score = score
            best_chain = chain
    if best_chain:
        return best_chain[:6]
    fallback = _normalize_chain(methods)
    return fallback[:6]


def _normalize_chain(symbols: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        value = _stringify(symbol)
        if not value:
            continue
        if not _is_meaningful_symbol(value):
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _is_meaningful_symbol(symbol: str) -> bool:
    lowered = symbol.lower()
    noisy_tokens = (
        "reshape",
        "permute",
        "unsqueeze",
        "squeeze",
        "append",
        "insert",
        "size",
        "len",
        "numpy",
        "cpu",
        "torch._c",
    )
    if any(token in lowered for token in noisy_tokens):
        return False
    return True


def _safe_line(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _build_source_locations(code_items: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in code_items:
        file_path = _stringify(item.get("file_path"))
        symbol = _stringify(item.get("method_signature") or item.get("symbol"))
        line = _safe_line(item.get("line") or item.get("line_start"))
        line_text = str(line) if line is not None else ""
        key = (file_path, symbol, line_text)
        if key in seen:
            continue
        seen.add(key)
        payload: dict[str, Any] = {
            "file_path": file_path,
            "symbol": symbol,
        }
        if line is not None:
            payload["line"] = line
        if file_path or symbol:
            results.append(payload)
        if len(results) >= limit:
            break
    return results


def _build_approach_graph(call_chain: list[str], inputs: list[str], outputs: list[str]) -> list[dict[str, Any]]:
    if not call_chain:
        return []

    nodes: list[dict[str, Any]] = []
    current_input = inputs[0] if inputs else "任务输入"
    final_output = outputs[0] if outputs else "候选技能输出"

    for index, module_name in enumerate(call_chain, start=1):
        is_last = index == len(call_chain)
        output = final_output if is_last else f"step_{index}_output"
        next_module = call_chain[index] if not is_last else ""
        nodes.append(
            {
                "step": index,
                "module": module_name,
                "input": current_input,
                "action": _infer_action(module_name),
                "output": output,
                "next_module": next_module,
            }
        )
        current_input = output
    return nodes


def _infer_action(module_name: str) -> str:
    lowered = module_name.lower()
    if any(token in lowered for token in ("load", "read", "dataset", "dataloader", "open", "get_")):
        return "读取并标准化输入数据"
    if any(token in lowered for token in ("forward", "stage", "layer", "conv", "encoder", "decoder", "net")):
        return "执行核心功能模块计算"
    if any(token in lowered for token in ("loss", "metric", "eval", "test", "accuracy")):
        return "计算评估指标并形成验证信号"
    if any(token in lowered for token in ("save", "write", "export", "dump")):
        return "落盘输出并准备后续检索"
    return "执行当前模块并输出中间结果"


def _build_chain_explanation(approach_graph: list[dict[str, Any]], *, limit: int = 4) -> list[str]:
    lines: list[str] = []
    for node in approach_graph[:max(limit, 0)]:
        step = int(node.get("step") or 0)
        module = _stringify(node.get("module"))
        node_input = _stringify(node.get("input"))
        node_action = _stringify(node.get("action"))
        node_output = _stringify(node.get("output"))
        next_module = _stringify(node.get("next_module")) or "END"
        lines.append(
            f"[{step}] 输入{node_input} -> 进入{module}；{node_action}；得到{node_output}；下一步{next_module}。"
        )
    return lines


def _build_what_text(payload: dict[str, Any]) -> str:
    partition_name = _stringify(payload.get("partition_name") or payload.get("name")) or "目标功能分区"
    description = _stringify(payload.get("description"))
    method_chain = _dedupe_strings(payload.get("method_call_chain") or payload.get("methods") or [])
    if description:
        return f"该经验库对应“{partition_name}”功能分区，{description}"
    if method_chain:
        return f"该经验库对应“{partition_name}”功能分区，主要通过调用链 {', '.join(method_chain[:4])} 承接需求。"
    return f"该经验库对应“{partition_name}”功能分区，用于承接相关需求并提供可执行经验。"


def _build_how_text(payload: dict[str, Any], approach_graph: list[dict[str, Any]]) -> str:
    lines = _build_chain_explanation(approach_graph, limit=4)
    if not lines:
        chain = _dedupe_strings(payload.get("method_call_chain") or payload.get("methods") or [])
        if chain:
            lines = [
                f"[1] 输入需求 -> 进入{chain[0]}；执行模块能力；得到step_1_output；下一步{chain[1] if len(chain) > 1 else 'END'}。"
            ]

    partition_summary = payload.get("partition_summary") or {}
    constraints: list[str] = []
    if bool(partition_summary.get("has_cfg")):
        constraints.append("CFG")
    if bool(partition_summary.get("has_dfg")):
        constraints.append("DFG")
    if bool(partition_summary.get("has_io")):
        constraints.append("输入输出")
    constraints.extend(_dedupe_strings(payload.get("inputs") or []))
    constraints.extend(_dedupe_strings(payload.get("outputs") or []))
    constraint_text = "、".join(_dedupe_strings(constraints)[:6]) if constraints else "基础路径信息"

    if lines:
        return "；".join(lines) + f"；约束依据：{constraint_text}。"
    return f"按调用链分步执行并补全中间输出，约束依据：{constraint_text}。"


def merge_skill_cards(
    skills: list[Any],
    path_evidence: list[Any],
    code_evidence: list[Any],
) -> list[dict[str, Any]]:
    path_map = _group_by_partition(path_evidence)
    code_map = _group_by_partition(code_evidence)

    merged: list[dict[str, Any]] = []
    for skill in skills:
        payload = _to_plain_dict(skill)
        partition_id = _stringify(payload.get("partition_id"))

        normalized_paths = _dedupe_path_evidence(path_map.get(partition_id) or [])
        normalized_code = _dedupe_code_evidence(code_map.get(partition_id) or [])
        file_count = len({_stringify(item.get("file_path")) for item in normalized_code if _stringify(item.get("file_path"))})

        payload["methods"] = _dedupe_strings(payload.get("methods") or [])
        payload["inputs"] = _dedupe_strings(payload.get("inputs") or [])
        payload["outputs"] = _dedupe_strings(payload.get("outputs") or [])
        payload["path_refs"] = _dedupe_strings([item.get("path_id") for item in normalized_paths])
        payload["code_refs"] = _dedupe_strings([item.get("method_signature") or item.get("symbol") for item in normalized_code])
        payload["path_evidence"] = normalized_paths
        payload["code_evidence"] = normalized_code
        payload["evidence_summary"] = {
            "path_count": len(normalized_paths),
            "code_ref_count": len(normalized_code),
            "file_count": file_count,
        }

        method_call_chain = _build_method_call_chain(normalized_paths, payload["methods"])
        source_locations = _build_source_locations(normalized_code)
        payload["method_call_chain"] = method_call_chain
        payload["source_locations"] = source_locations
        approach_graph = _build_approach_graph(method_call_chain, payload["inputs"], payload["outputs"])
        payload["approach_graph"] = approach_graph
        payload["chain_explanation"] = _build_chain_explanation(approach_graph)
        payload["what"] = _build_what_text(payload)
        payload["how"] = _build_how_text(payload, approach_graph)
        payload["retrieval_hints"] = {
            "partition_id": partition_id,
            "preferred_paths": payload["path_refs"][:3],
            "preferred_symbols": payload["code_refs"][:6],
            "preferred_files": _dedupe_strings([item.get("file_path") for item in source_locations])[:6],
            "search_sequence": [
                "先用 preferred_paths 找调用链路径",
                "再用 preferred_symbols 定位函数",
                "若缺文件路径，再按 symbol 在代码库二次检索",
            ],
        }

        if _stringify(payload.get("name")).startswith("未知分区") and len(method_call_chain) < 2:
            payload["usable_for_matching"] = False

        merged.append(payload)

    merged.sort(key=lambda item: (_stringify(item.get("partition_id")), _stringify(item.get("name"))))
    return merged
