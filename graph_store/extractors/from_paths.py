#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from graph_store.schema import PathCfgRecord, PathDfgRecord, PathLinkRecord, PathRecord, PathReverseIndexRecord


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def extract_path_records(
    path_analyses: List[Dict[str, Any]],
    *,
    run_id: str,
    source_project_path: Optional[str],
) -> List[PathRecord]:
    records: List[PathRecord] = []
    for item in path_analyses or []:
        semantics = item.get("semantics") or {}
        chain = [str(part).strip() for part in (item.get("function_chain") or item.get("path") or []) if str(part).strip()]
        records.append(
            PathRecord(
                path_id=str(item.get("path_id") or "unknown").strip(),
                run_id=run_id,
                partition_id=str(item.get("partition_id") or "unknown").strip(),
                leaf_node=str(item.get("leaf_node") or (chain[-1] if chain else "")).strip(),
                function_chain_json=_json_dumps(chain),
                path_name=str(item.get("path_name") or "").strip(),
                path_description=str(item.get("path_description") or semantics.get("description") or "").strip(),
                semantic_label=str(item.get("semantic_label") or semantics.get("semantic_label") or "").strip(),
                keywords_json=_json_dumps(item.get("keywords") or semantics.get("keywords") or []),
                functional_domain=str(item.get("functional_domain") or semantics.get("functional_domain") or "").strip(),
                worthiness_score=float(item.get("worthiness_score") or 0.0),
                deep_analysis_status=str(item.get("deep_analysis_status") or "ready").strip(),
                cfg_dfg_explain_md=str(item.get("cfg_dfg_explain_md") or ""),
                model=(str(item.get("model")) if item.get("model") not in {None, ""} else None),
                duration_ms=int(item.get("duration_ms") or 0),
                source_project_path=source_project_path,
                skip_reason=(str(item.get("skip_reason")) if item.get("skip_reason") not in {None, ""} else None),
                trigger_mode=str(item.get("trigger_mode") or "skip").strip(),
                llm_reasoning=str(item.get("llm_reasoning") or "").strip(),
            )
        )
    return sorted(records, key=lambda item: (item.partition_id, item.path_id))


def extract_path_link_records(
    path_analyses: List[Dict[str, Any]],
    *,
    run_id: str,
    symbol_by_qn: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[PathLinkRecord]:
    symbol_by_qn = symbol_by_qn or {}
    records: List[PathLinkRecord] = []
    for item in path_analyses or []:
        path_id = str(item.get("path_id") or "unknown").strip()
        chain = [str(part).strip() for part in (item.get("function_chain") or item.get("path") or []) if str(part).strip()]
        direct_calls = {
            (str(pair[0]).strip(), str(pair[1]).strip())
            for pair in ((item.get("call_chain_analysis") or {}).get("direct_calls") or [])
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        }
        for index in range(len(chain) - 1):
            caller = chain[index]
            callee = chain[index + 1]
            caller_symbol = symbol_by_qn.get(caller) or {}
            callee_symbol = symbol_by_qn.get(callee) or {}
            records.append(
                PathLinkRecord(
                    link_id=f"{path_id}:link:{index}",
                    run_id=run_id,
                    path_id=path_id,
                    step_index=index,
                    caller=caller,
                    callee=callee,
                    is_direct_call=(caller, callee) in direct_calls if direct_calls else None,
                    caller_file_path=str(caller_symbol.get("file_path") or "").replace("\\", "/"),
                    callee_file_path=str(callee_symbol.get("file_path") or "").replace("\\", "/"),
                )
            )
    return sorted(records, key=lambda item: (item.path_id, item.step_index))


def extract_path_cfg_records(path_analyses: List[Dict[str, Any]], *, run_id: str) -> List[PathCfgRecord]:
    records: List[PathCfgRecord] = []
    for item in path_analyses or []:
        path_id = str(item.get("path_id") or "unknown").strip()
        cfg_payload = item.get("cfg") or {}
        for node_id, node in sorted((cfg_payload.get("nodes") or {}).items()):
            if not isinstance(node, dict):
                continue
            normalized_node_id = str(node.get("id") or node_id).strip()
            records.append(
                PathCfgRecord(
                    cfg_id=f"{path_id}:cfg:{normalized_node_id}",
                    run_id=run_id,
                    path_id=path_id,
                    method_sig=str(node.get("method") or "").strip(),
                    node_id=normalized_node_id,
                    line_number=int(node.get("line_number") or 0),
                    node_type=str(node.get("type") or "").strip(),
                    code_excerpt=str(node.get("code") or "")[:500],
                )
            )
    return sorted(records, key=lambda item: (item.path_id, item.method_sig, item.node_id))


def extract_path_dfg_records(path_analyses: List[Dict[str, Any]], *, run_id: str) -> List[PathDfgRecord]:
    records: List[PathDfgRecord] = []
    for item in path_analyses or []:
        path_id = str(item.get("path_id") or "unknown").strip()
        dfg_payload = item.get("dfg") or {}
        for node_id, node in sorted((dfg_payload.get("nodes") or {}).items()):
            if not isinstance(node, dict):
                continue
            method_sig = str(node.get("method") or "").strip()
            normalized_node_id = str(node.get("id") or node_id).strip()
            records.append(
                PathDfgRecord(
                    dfg_id=f"{path_id}:dfg:{normalized_node_id}",
                    run_id=run_id,
                    path_id=path_id,
                    method_sig=method_sig,
                    variable_name=str(node.get("variable") or "").strip(),
                    node_id=normalized_node_id,
                    line_number=int(node.get("line_number") or 0),
                    node_type=str(node.get("type") or "").strip(),
                    method_node_id=f"method_{method_sig}" if method_sig else "",
                )
            )
    return sorted(records, key=lambda item: (item.path_id, item.method_sig, item.node_id))


def extract_path_reverse_index_records(
    path_analyses: List[Dict[str, Any]],
    *,
    run_id: str,
) -> List[PathReverseIndexRecord]:
    records: List[PathReverseIndexRecord] = []
    for item in path_analyses or []:
        path_id = str(item.get("path_id") or "unknown").strip()
        chain = [str(part).strip() for part in (item.get("function_chain") or item.get("path") or []) if str(part).strip()]
        for method_qn in sorted(dict.fromkeys(chain)):
            records.append(PathReverseIndexRecord(method_qn=method_qn, run_id=run_id, path_id=path_id))
    return sorted(records, key=lambda item: (item.method_qn, item.path_id))
