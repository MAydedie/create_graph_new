"""
Phase2: Hybrid search shadow adapter.

Design goals:
- Sidecar-only: consumes existing graph_data, does not modify legacy analysis flow.
- Stable API payload: returns bm25 / semantic / hybrid lists with consistent fields.
- Safe fallback: if BM25 dependency/index fails, semantic + hybrid still return.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from src.search.bm25_index import CodeBM25Index
from src.search.hybrid_search import merge_with_rrf


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _build_doc_text(node_data: Dict[str, Any]) -> str:
    text_parts = [
        _normalize_text(node_data.get("label")),
        _normalize_text(node_data.get("full_name")),
        _normalize_text(node_data.get("name")),
        _normalize_text(node_data.get("type")),
        _normalize_text(node_data.get("class_name")),
        _normalize_text(node_data.get("docstring")),
        _normalize_text(node_data.get("file")),
    ]
    return " ".join(part for part in text_parts if part)


def _to_search_documents(graph_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    documents: List[Dict[str, Any]] = []
    for node in graph_data.get("nodes", []):
        node_data = node.get("data", {}) if isinstance(node, dict) else {}
        node_id = _normalize_text(node_data.get("id"))
        if not node_id:
            continue

        text_content = _build_doc_text(node_data)
        if not text_content:
            continue

        documents.append(
            {
                "id": node_id,
                "text": text_content,
                "type": _normalize_text(node_data.get("type")),
                "label": _normalize_text(node_data.get("label")),
                "file": _normalize_text(node_data.get("file")),
                "full_name": _normalize_text(node_data.get("full_name")),
            }
        )
    return documents


def _tokenize_for_semantic(text: str) -> List[str]:
    normalized = _normalize_text(text).lower()
    normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", normalized)
    normalized = re.sub(r"[_\-/\\.]", " ", normalized)
    return re.findall(r"\b[a-z0-9]{2,}\b", normalized)


def _semantic_search(documents: List[Dict[str, Any]], query: str, top_k: int) -> List[Dict[str, Any]]:
    query_tokens = set(_tokenize_for_semantic(query))
    if not query_tokens:
        return []

    scored_results: List[Tuple[float, Dict[str, Any]]] = []
    query_text = _normalize_text(query).lower()

    for document in documents:
        text_value = document.get("text", "")
        document_tokens = set(_tokenize_for_semantic(text_value))
        if not document_tokens:
            continue

        overlap_count = len(query_tokens & document_tokens)
        if overlap_count == 0:
            continue

        denominator = len(query_tokens | document_tokens)
        jaccard_score = overlap_count / denominator if denominator else 0.0

        substring_boost = 0.1 if query_text and query_text in text_value.lower() else 0.0
        semantic_score = min(jaccard_score + substring_boost, 1.0)

        semantic_result = {
            "id": document["id"],
            "semantic_score": semantic_score,
            "type": document.get("type", ""),
            "label": document.get("label", ""),
            "file": document.get("file", ""),
            "full_name": document.get("full_name", ""),
        }
        scored_results.append((semantic_score, semantic_result))

    scored_results.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored_results[:top_k]]


def _normalize_relation_type(value: Any) -> str:
    relation = _normalize_text(value).upper()
    if relation == "":
        return "UNKNOWN"
    return relation


def _parse_edge(edge: Dict[str, Any]) -> Dict[str, Any]:
    edge_data = edge.get("data", {}) if isinstance(edge, dict) and isinstance(edge.get("data"), dict) else edge
    source = _normalize_text(edge_data.get("source") or edge.get("source") if isinstance(edge, dict) else "")
    target = _normalize_text(edge_data.get("target") or edge.get("target") if isinstance(edge, dict) else "")
    relation_type = _normalize_relation_type(
        edge_data.get("type")
        or edge_data.get("relation")
        or edge_data.get("label")
        or edge.get("type") if isinstance(edge, dict) else ""
    )
    step_raw = edge_data.get("step", edge.get("step") if isinstance(edge, dict) else None)
    try:
        step = int(step_raw) if step_raw is not None else None
    except (TypeError, ValueError):
        step = None
    return {
        "source": source,
        "target": target,
        "type": relation_type,
        "step": step,
    }


def _build_node_label_map(graph_data: Dict[str, Any]) -> Dict[str, str]:
    label_map: Dict[str, str] = {}
    for node in graph_data.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_data = node.get("data", {}) if isinstance(node.get("data"), dict) else node
        node_id = _normalize_text(node_data.get("id") or node.get("id"))
        if not node_id:
            continue
        label = _normalize_text(node_data.get("label") or node_data.get("name") or node_id)
        label_map[node_id] = label
    return label_map


def _build_graph_context(graph_data: Dict[str, Any], node_id: str) -> List[Dict[str, Any]]:
    parsed_edges = [_parse_edge(edge) for edge in graph_data.get("edges", []) if isinstance(edge, dict)]
    node_label_map = _build_node_label_map(graph_data)

    member_of_items: List[Dict[str, Any]] = []
    process_items: List[Dict[str, Any]] = []
    neighbor_items: List[Dict[str, Any]] = []

    for edge in parsed_edges:
        if edge["source"] != node_id:
            continue
        target_id = edge["target"]
        relation_type = edge["type"]
        if relation_type == "MEMBER_OF":
            member_of_items.append(
                {
                    "type": "member_of_community",
                    "community_id": target_id,
                    "community_label": node_label_map.get(target_id, target_id),
                    "relation": relation_type,
                }
            )
        elif relation_type == "STEP_IN_PROCESS":
            process_items.append(
                {
                    "type": "step_in_process",
                    "process_id": target_id,
                    "process_label": node_label_map.get(target_id, target_id),
                    "step": edge.get("step"),
                    "relation": relation_type,
                }
            )
        else:
            neighbor_items.append(
                {
                    "type": "neighbor_relation",
                    "relation": relation_type,
                    "target_id": target_id,
                    "target_label": node_label_map.get(target_id, target_id),
                }
            )

    context_items = process_items + member_of_items + neighbor_items[:2]
    if context_items:
        return context_items
    return [
        {
            "type": "neighbor_relation",
            "relation": "no_edge_found",
            "target_id": node_id,
            "target_label": node_label_map.get(node_id, node_id),
        }
    ]


def _build_flat_hits(hybrid_results: List[Dict[str, Any]], graph_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    flat_hits: List[Dict[str, Any]] = []
    for item in hybrid_results:
        node_id = _normalize_text(item.get("id"))
        graph_context = _build_graph_context(graph_data, node_id)
        flat_hits.append(
            {
                "rank": item.get("rank", 0),
                "source": "+".join(item.get("sources", [])) if isinstance(item.get("sources"), list) else "",
                "score": item.get("score", 0.0),
                "node_id": node_id,
                "file_path": _normalize_text(item.get("file")),
                "label": _normalize_text(item.get("label")),
                "graph_context": graph_context,
            }
        )
    return flat_hits


def _build_grouped_by_process(flat_hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for hit in flat_hits:
        process_contexts = [ctx for ctx in hit.get("graph_context", []) if ctx.get("type") == "step_in_process"]
        if not process_contexts:
            process_contexts = [{"process_id": "__ungrouped__", "process_label": "Ungrouped"}]

        for process_context in process_contexts:
            process_id = _normalize_text(process_context.get("process_id") or "__ungrouped__")
            if process_id not in grouped:
                grouped[process_id] = {
                    "process_id": process_id,
                    "process_label": _normalize_text(process_context.get("process_label") or "Ungrouped"),
                    "hits": [],
                }
            grouped[process_id]["hits"].append(hit)

    group_list = list(grouped.values())
    group_list.sort(key=lambda group: len(group.get("hits", [])), reverse=True)
    return group_list


def run_hybrid_shadow(
    graph_data: Dict[str, Any],
    query: str,
    top_k: int = 10,
    enable_graph_context: bool = True,
) -> Dict[str, Any]:
    documents = _to_search_documents(graph_data)
    if not documents:
        return {
            "query": query,
            "top_k": top_k,
            "doc_count": 0,
            "bm25_results": [],
            "semantic_results": [],
            "hybrid_results": [],
            "stats": {"bm25_count": 0, "semantic_count": 0, "hybrid_count": 0},
        }

    bm25_results: List[Dict[str, Any]] = []
    bm25_error = None
    try:
        bm25_index = CodeBM25Index()
        bm25_index.build(documents, text_field="text", id_field="id")
        bm25_results = bm25_index.search(query, top_k=top_k * 2)
    except Exception as exc:
        bm25_error = str(exc)

    semantic_results = _semantic_search(documents, query=query, top_k=top_k * 2)
    hybrid_objects = merge_with_rrf(bm25_results, semantic_results, limit=top_k)
    hybrid_results = [item.to_dict() for item in hybrid_objects]

    bm25_ids = {item.get("id") for item in bm25_results if item.get("id")}
    semantic_ids = {item.get("id") for item in semantic_results if item.get("id")}
    hybrid_ids = {item.get("id") for item in hybrid_results if item.get("id")}
    overlap_ids = bm25_ids & semantic_ids

    explainable_hybrid_count = 0
    for result in hybrid_results:
        sources_value = result.get("sources")
        if isinstance(sources_value, list) and len(sources_value) >= 1:
            explainable_hybrid_count += 1

    response = {
        "query": query,
        "top_k": top_k,
        "doc_count": len(documents),
        "bm25_results": bm25_results[:top_k],
        "semantic_results": semantic_results[:top_k],
        "hybrid_results": hybrid_results,
        "stats": {
            "bm25_count": len(bm25_results),
            "semantic_count": len(semantic_results),
            "hybrid_count": len(hybrid_results),
        },
        "comparison": {
            "bm25_unique": len(bm25_ids - semantic_ids),
            "semantic_unique": len(semantic_ids - bm25_ids),
            "overlap": len(overlap_ids),
            "hybrid_union_coverage": len(hybrid_ids) / max(len(bm25_ids | semantic_ids), 1),
            "hybrid_vs_bm25_coverage": len(hybrid_ids) / max(len(bm25_ids), 1),
            "hybrid_vs_semantic_coverage": len(hybrid_ids) / max(len(semantic_ids), 1),
            "explainable_hybrid_ratio": explainable_hybrid_count / max(len(hybrid_results), 1),
        },
    }

    if enable_graph_context:
        flat_hits = _build_flat_hits(hybrid_results, graph_data)
        grouped_by_process = _build_grouped_by_process(flat_hits)
        linked_hits = sum(
            1
            for hit in flat_hits
            if any(context.get("relation") != "no_edge_found" for context in hit.get("graph_context", []))
        )
        graph_context_coverage = linked_hits / max(len(flat_hits), 1)
        response["flat_hits"] = flat_hits
        response["grouped_by_process"] = grouped_by_process
        response["phase2b"] = {
            "enabled": True,
            "graph_context_coverage": graph_context_coverage,
            "group_count": len(grouped_by_process),
        }

    if bm25_error:
        response["bm25_error"] = bm25_error
    return response
