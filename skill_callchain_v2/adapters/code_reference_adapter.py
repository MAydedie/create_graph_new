from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from app.services import analysis_service

from ..models import CodeEvidence


def _iter_unique_method_signatures(method_signatures: Iterable[Any], *, max_items: Optional[int] = None) -> List[str]:
    seen: Set[str] = set()
    normalized: List[str] = []
    for item in method_signatures:
        method_signature = str(item or "").strip()
        if not method_signature or method_signature in seen:
            continue
        seen.add(method_signature)
        normalized.append(method_signature)
        if max_items is not None and len(normalized) >= max(max_items, 0):
            break
    return normalized


def _split_class_name(method_signature: str) -> str:
    if "." not in method_signature:
        return ""
    return method_signature.rsplit(".", 1)[0].strip()


def _build_snippet_preview(source_code: Any, *, max_lines: int = 8, max_chars: int = 480) -> str:
    text = str(source_code or "").strip("\n")
    if not text:
        return ""

    lines = text.splitlines()[:max_lines]
    preview = "\n".join(lines).rstrip()
    if len(preview) > max_chars:
        preview = preview[: max_chars - 3].rstrip() + "..."
    elif len(text) > len(preview):
        preview = preview.rstrip() + "\n..."
    return preview


def build_code_reference(
    project_path: str,
    method_signature: str,
    *,
    partition_id: str = "",
    path_id: str = "",
    source: str = "partition_method",
    max_snippet_lines: int = 8,
    max_snippet_chars: int = 480,
) -> CodeEvidence:
    normalized_signature = str(method_signature or "").strip()
    report = analysis_service._resolve_report_cached(project_path, allow_global_fallback=False)
    resolved = analysis_service._resolve_method_or_function_from_report(report, normalized_signature) if report else None
    node_data = analysis_service._resolve_graph_node_data(project_path, normalized_signature, allow_global_fallback=False) or {}

    file_path = str(node_data.get("file") or node_data.get("file_path") or "").strip()
    class_name = _split_class_name(normalized_signature)
    symbol_kind = "method" if class_name else "function"
    line_start = None
    line_end = None
    snippet_preview = ""
    language = analysis_service._guess_language(file_path)

    if resolved:
        info = resolved.get("info")
        class_info = resolved.get("class_info")
        symbol_kind = str(resolved.get("kind") or symbol_kind).strip()
        if class_info is not None:
            class_name = str(getattr(class_info, "name", None) or class_name).strip()
        if info is not None and getattr(info, "source_location", None):
            file_path = str(getattr(info.source_location, "file_path", None) or file_path).strip()
            line_start = getattr(info.source_location, "line_start", None)
            line_end = getattr(info.source_location, "line_end", None)
        elif class_info is not None and getattr(class_info, "source_location", None):
            file_path = str(getattr(class_info.source_location, "file_path", None) or file_path).strip()

        snippet_preview = _build_snippet_preview(
            getattr(info, "source_code", None) if info is not None else None,
            max_lines=max_snippet_lines,
            max_chars=max_snippet_chars,
        )
        language = analysis_service._guess_language(file_path)

    return CodeEvidence(
        file_path=file_path,
        class_name=class_name,
        method_signature=normalized_signature,
        snippet_preview=snippet_preview,
        language=language,
        symbol_kind=symbol_kind,
        line_start=line_start,
        line_end=line_end,
        partition_id=str(partition_id or "").strip(),
        path_id=str(path_id or "").strip(),
        source=str(source or "").strip(),
        metadata={
            "resolved_from_report": bool(resolved),
        },
    )


def build_code_references_from_methods(
    project_path: str,
    method_signatures: Sequence[Any],
    *,
    partition_id: str = "",
    path_id: str = "",
    source: str = "partition_method",
    max_items: int = 5,
    max_snippet_lines: int = 8,
    max_snippet_chars: int = 480,
) -> List[CodeEvidence]:
    references: List[CodeEvidence] = []
    for method_signature in _iter_unique_method_signatures(method_signatures, max_items=max_items):
        references.append(
            build_code_reference(
                project_path,
                method_signature,
                partition_id=partition_id,
                path_id=path_id,
                source=source,
                max_snippet_lines=max_snippet_lines,
                max_snippet_chars=max_snippet_chars,
            )
        )
    return references


def build_code_references_from_path(
    project_path: str,
    path_analysis: Optional[Dict[str, Any]],
    *,
    partition_id: str = "",
    max_items: int = 3,
    max_snippet_lines: int = 8,
    max_snippet_chars: int = 480,
) -> List[CodeEvidence]:
    payload = path_analysis if isinstance(path_analysis, dict) else {}
    method_signatures = payload.get("function_chain") or payload.get("path") or []
    return build_code_references_from_methods(
        project_path,
        method_signatures,
        partition_id=partition_id,
        path_id=str(payload.get("path_id") or "").strip(),
        source="path_analysis",
        max_items=max_items,
        max_snippet_lines=max_snippet_lines,
        max_snippet_chars=max_snippet_chars,
    )


def build_code_references_from_partition(
    project_path: str,
    partition_payload: Optional[Dict[str, Any]],
    *,
    max_items: int = 5,
    max_snippet_lines: int = 8,
    max_snippet_chars: int = 480,
) -> List[CodeEvidence]:
    payload = partition_payload if isinstance(partition_payload, dict) else {}
    raw_summary = payload.get("summary")
    summary: Dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    method_signatures = payload.get("methods") or summary.get("methods") or []
    partition_id = str(payload.get("partition_id") or summary.get("partition_id") or "").strip()
    return build_code_references_from_methods(
        project_path,
        method_signatures,
        partition_id=partition_id,
        source="partition_summary",
        max_items=max_items,
        max_snippet_lines=max_snippet_lines,
        max_snippet_chars=max_snippet_chars,
    )
