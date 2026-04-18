from __future__ import annotations

import importlib
from typing import Any


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            normalized = _stringify(item)
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result
    return []


def _maybe_code_model(payload: dict[str, Any]) -> Any:
    try:
        module = importlib.import_module("skill_callchain_v2.models")
        model_cls = getattr(module, "CodeEvidence", None)
    except Exception:
        model_cls = None
    if model_cls is None:
        return payload
    try:
        return model_cls(**payload)
    except Exception:
        return payload


def _iter_partition_analyses(contract_payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    hierarchy_result = contract_payload.get("hierarchy_result") or contract_payload
    partition_analyses = hierarchy_result.get("partition_analyses") or {}
    items: list[tuple[str, dict[str, Any]]] = []
    for partition_id, payload in partition_analyses.items():
        if isinstance(payload, dict):
            items.append((_stringify(partition_id), payload))
    items.sort(key=lambda item: item[0])
    return items


def _build_partition_summary_map(contract_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    summaries = ((contract_payload.get("adapters") or {}).get("partition_summaries") or [])
    result: dict[str, dict[str, Any]] = {}
    for item in summaries:
        if not isinstance(item, dict):
            continue
        partition_id = _stringify(item.get("partition_id"))
        if partition_id:
            result[partition_id] = item
    return result


def _best_node_data(node: dict[str, Any]) -> dict[str, Any]:
    data = node.get("data")
    return data if isinstance(data, dict) else node


def _best_symbol(node_data: dict[str, Any]) -> str:
    for key in ("method_signature", "signature", "full_name", "fqmn", "name"):
        value = _stringify(node_data.get(key))
        if value:
            return value

    label = _stringify(node_data.get("label"))
    class_name = _stringify(node_data.get("class_name"))
    if class_name and label:
        return f"{class_name}.{label}"
    if label:
        return label

    raw_id = _stringify(node_data.get("id"))
    if raw_id.startswith("method_"):
        return raw_id[len("method_") :]
    if raw_id.startswith("function_"):
        return raw_id[len("function_") :]
    if raw_id.startswith("func_"):
        return raw_id[len("func_") :]
    return raw_id


def _build_code_ref(
    partition_id: str,
    *,
    symbol: str,
    kind: str,
    source: str,
    file_path: str = "",
    line: int | None = None,
) -> dict[str, Any] | None:
    normalized_symbol = _stringify(symbol)
    normalized_path = _stringify(file_path)
    if not normalized_symbol and not normalized_path:
        return None
    return {
        "partition_id": partition_id,
        "symbol": normalized_symbol,
        "kind": _stringify(kind) or "code_ref",
        "file_path": normalized_path,
        "line": line,
        "source": _stringify(source),
    }


def _extract_entry_point_refs(partition_id: str, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in analysis.get("entry_points") or []:
        if not isinstance(item, dict):
            continue
        ref = _build_code_ref(
            partition_id,
            symbol=_stringify(item.get("method_signature") or item.get("signature")),
            kind="entry_point",
            source="entry_points",
            file_path=_stringify(item.get("file_path") or item.get("file")),
            line=_int_or_none(item.get("line") or item.get("line_start")),
        )
        if ref is not None:
            results.append(ref)
    return results


def _extract_call_graph_refs(partition_id: str, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    call_graph = analysis.get("call_graph") or {}
    for node in call_graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_data = _best_node_data(node)
        ref = _build_code_ref(
            partition_id,
            symbol=_best_symbol(node_data),
            kind=_stringify(node_data.get("type")) or "graph_node",
            source="call_graph",
            file_path=_stringify(node_data.get("file") or node_data.get("file_path")),
            line=_int_or_none(node_data.get("line") or node_data.get("line_start")),
        )
        if ref is not None:
            results.append(ref)
    return results


def _extract_method_refs(partition_id: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for method in _string_list(summary.get("methods")):
        ref = _build_code_ref(
            partition_id,
            symbol=method,
            kind="method_ref",
            source="partition_summary",
        )
        if ref is not None:
            results.append(ref)
    return results


def build_code_evidence(contract_payload: dict[str, Any]) -> list[Any]:
    results: list[Any] = []
    summary_map = _build_partition_summary_map(contract_payload)
    for partition_id, analysis in _iter_partition_analyses(contract_payload):
        refs = []
        refs.extend(_extract_entry_point_refs(partition_id, analysis))
        refs.extend(_extract_call_graph_refs(partition_id, analysis))
        refs.extend(_extract_method_refs(partition_id, summary_map.get(partition_id) or {}))
        for ref in refs:
            results.append(_maybe_code_model(ref))
    return results
