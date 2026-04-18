#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Codebase-first retrieval helpers.

Design goals:
- Repository code as primary searchable object (graph cache optional).
- Lightweight lexical retrieval with bounded scan cost.
- Return file-level evidence + focused snippet windows for downstream LLM/tooling.
"""

from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.analysis.import_processor import ImportProcessor


CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".kt",
    ".swift",
    ".scala",
    ".sql",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".md",
}

IGNORED_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "output_analysis",
    "汇报",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "target",
    "venv",
    ".venv",
    "__pycache__",
}

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "what",
    "how",
    "why",
    "where",
    "when",
    "please",
    "help",
    "code",
    "project",
    "function",
    "method",
    "请",
    "帮我",
    "如何",
    "怎么",
    "这个",
    "那个",
    "代码",
    "项目",
    "方法",
    "函数",
}

SYMBOL_DEF_PATTERNS = [
    re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\b"),
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\("),
    re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)\b"),
]


def _normalize_project_path(project_path: Optional[str]) -> str:
    if not project_path:
        return ""
    return os.path.normpath(os.path.abspath(str(project_path)))


def _extract_path_hints(text: str) -> List[str]:
    value = str(text or "")
    if not value:
        return []
    hints: List[str] = []
    pattern = r"[A-Za-z]:\\[^\s,;，；]+|[^\s,;，；]+(?:\\|/)[^\s,;，；]+|[^\s,;，；]+\.(?:py|ts|tsx|js|java|go|rs|cpp|c|cs|md)"
    for item in re.findall(pattern, value):
        hint = str(item or "").strip().replace("\\", "/")
        if hint and hint not in hints:
            hints.append(hint)
    return hints


def _extract_query_terms(query: str) -> List[str]:
    value = str(query or "").strip().lower()
    if not value:
        return []

    terms: List[str] = []
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}|[\u4e00-\u9fff]{2,}", value)
    for token in tokens:
        cleaned = token.strip().lower()
        if not cleaned or cleaned in STOPWORDS:
            continue
        if cleaned not in terms:
            terms.append(cleaned)
    return terms[:16]


def _dedupe_terms(items: List[str], limit: int) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for raw in items:
        value = str(raw or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
        if len(deduped) >= limit:
            break
    return deduped


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item)
    return result


def _split_query_segments(query: str) -> List[str]:
    value = str(query or "").strip()
    if not value:
        return []
    pieces = re.split(r"\s*(?:->|=>|;|；|,|，|\band\b|\bthen\b|并且|然后|再|以及)\s*", value, flags=re.IGNORECASE)
    segments: List[str] = []
    for piece in pieces:
        normalized = str(piece or "").strip()
        if not normalized:
            continue
        if normalized not in segments:
            segments.append(normalized)
    return segments


def _build_query_plans(query: str) -> List[Dict[str, Any]]:
    root_query = str(query or "").strip()
    if not root_query:
        return []

    plans: List[Dict[str, Any]] = []
    plans.append(
        {
            "query": root_query,
            "weight": 1.0,
            "kind": "primary",
            "terms": _extract_query_terms(root_query),
            "symbol_terms": _extract_symbol_candidates(root_query),
            "exact_identifiers": _extract_exact_identifiers(root_query),
            "path_hints": _extract_path_hints(root_query),
        }
    )

    segments = _split_query_segments(root_query)
    for segment in segments:
        if segment == root_query:
            continue
        plans.append(
            {
                "query": segment,
                "weight": 0.78,
                "kind": "segment",
                "terms": _extract_query_terms(segment),
                "symbol_terms": _extract_symbol_candidates(segment),
                "exact_identifiers": _extract_exact_identifiers(segment),
                "path_hints": _extract_path_hints(segment),
            }
        )

    if len(segments) >= 2:
        head = segments[0]
        tail = segments[-1]
        bridge_query = f"{head} {tail}"
        plans.append(
            {
                "query": bridge_query,
                "weight": 0.72,
                "kind": "bridge",
                "terms": _extract_query_terms(bridge_query),
                "symbol_terms": _extract_symbol_candidates(bridge_query),
                "exact_identifiers": _extract_exact_identifiers(bridge_query),
                "path_hints": _extract_path_hints(bridge_query),
            }
        )

    deduped_plans: List[Dict[str, Any]] = []
    seen_queries = set()
    for plan in plans:
        query_text = str(plan.get("query") or "").strip()
        if not query_text or query_text in seen_queries:
            continue
        seen_queries.add(query_text)
        deduped_plans.append(plan)
        if len(deduped_plans) >= 6:
            break
    return deduped_plans


def _extract_symbol_candidates(query: str) -> List[str]:
    terms = _extract_query_terms(query)
    query_text = str(query or "")
    raw_identifiers = re.findall(r"[A-Za-z_][A-Za-z0-9_\.]{1,}", query_text)
    for token in raw_identifiers:
        normalized = token.strip().replace(".", " ").replace("_", " ")
        for part in normalized.split():
            candidate = part.strip().lower()
            if not candidate or len(candidate) < 2 or candidate in STOPWORDS:
                continue
            if candidate not in terms:
                terms.append(candidate)
        # camelCase split
        camel_parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", token)
        for part in camel_parts:
            candidate = part.strip().lower()
            if not candidate or len(candidate) < 2 or candidate in STOPWORDS:
                continue
            if candidate not in terms:
                terms.append(candidate)
    return terms[:24]


def _extract_exact_identifiers(query: str) -> List[str]:
    query_text = str(query or "")
    raw_identifiers = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", query_text)
    candidates: List[str] = []
    for token in raw_identifiers:
        text = str(token or "").strip()
        if not text:
            continue
        has_snake = "_" in text
        has_camel = bool(re.search(r"[a-z][A-Z]|[A-Z][a-z]", text))
        if not has_snake and not has_camel and len(text) < 12:
            continue
        normalized = text.lower()
        if normalized in STOPWORDS:
            continue
        if normalized not in candidates:
            candidates.append(normalized)
    return candidates[:16]


def _iter_code_files(project_path: str, *, max_files: int) -> Iterable[str]:
    yielded = 0
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        for file_name in files:
            _, ext = os.path.splitext(file_name)
            if ext.lower() not in CODE_EXTENSIONS:
                continue
            absolute_path = os.path.normpath(os.path.join(root, file_name))
            yield absolute_path
            yielded += 1
            if yielded >= max_files:
                return


def _safe_read_text(file_path: str, *, max_bytes: int) -> str:
    try:
        with open(file_path, "rb") as handle:
            raw = handle.read(max_bytes + 1)
    except Exception:
        return ""

    if not raw:
        return ""
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    return raw.decode("utf-8", errors="replace")


def _score_match(
    *,
    relative_path: str,
    content_lower: str,
    query_lower: str,
    terms: List[str],
    path_hints: List[str],
    exact_identifiers: List[str],
) -> float:
    score = 0.0
    path_lower = relative_path.lower()

    for term in terms:
        if term in path_lower:
            score += 2.2
        hit_count = content_lower.count(term)
        if hit_count > 0:
            score += float(min(hit_count, 8)) * 1.1

    for hint in path_hints:
        hint_lower = hint.lower()
        hint_name = os.path.basename(hint_lower)
        if hint_lower and hint_lower in path_lower:
            score += 3.0
        elif hint_name and hint_name in path_lower:
            score += 2.0

    if query_lower and len(query_lower) >= 6 and query_lower in content_lower:
        score += 2.5

    for identifier in exact_identifiers:
        ident = str(identifier or "").strip().lower()
        if not ident:
            continue
        if ident in path_lower:
            score += 4.5
        ident_hits = content_lower.count(ident)
        if ident_hits > 0:
            score += float(min(ident_hits, 4)) * 1.8
        if f"def {ident}(" in content_lower:
            score += 12.0
        elif f"class {ident}" in content_lower:
            score += 10.0
        elif f"function {ident}(" in content_lower:
            score += 10.0
        elif f"const {ident} =" in content_lower or f"let {ident} =" in content_lower:
            score += 8.0

    if path_lower.endswith((".py", ".ts", ".tsx", ".js", ".java")):
        score += 0.2
    return round(score, 4)


def _build_snippet(content: str, terms: List[str], path_hints: List[str]) -> Tuple[int, int, str]:
    lines = content.splitlines()
    if not lines:
        return 1, 1, ""

    best_index = 0
    best_score = -1
    hints = [item.lower() for item in path_hints if item]

    for index, line in enumerate(lines):
        text = line.lower()
        score = 0
        for term in terms:
            if term and term in text:
                score += text.count(term)
        for hint in hints:
            short = os.path.basename(hint)
            if short and short in text:
                score += 2
        if score > best_score:
            best_score = score
            best_index = index

    start = max(0, best_index - 4)
    end = min(len(lines), best_index + 5)
    snippet = "\n".join(lines[start:end]).strip()
    return start + 1, end, snippet


def _build_line_window(lines: List[str], line_index: int, radius: int = 3) -> Tuple[int, int, str]:
    if not lines:
        return 1, 1, ""
    start = max(0, line_index - radius)
    end = min(len(lines), line_index + radius + 1)
    snippet = "\n".join(lines[start:end]).strip()
    return start + 1, end, snippet


def _collect_symbol_hits(
    *,
    text_candidates: List[Dict[str, Any]],
    symbol_terms: List[str],
    exact_identifiers: List[str],
    path_hints: List[str],
    max_hits: int,
) -> List[Dict[str, Any]]:
    if not text_candidates or not symbol_terms:
        return []

    symbol_hits: List[Dict[str, Any]] = []
    seen_symbols = set()
    normalized_hints = [os.path.basename(str(item).lower()) for item in path_hints if str(item).strip()]

    for file_rank, candidate in enumerate(text_candidates[:60], start=1):
        content = str(candidate.get("_content") or "")
        relative_path = str(candidate.get("file") or candidate.get("file_path") or "").strip()
        if not content or not relative_path:
            continue

        base_score = float(candidate.get("score") or 0.0)
        path_lower = relative_path.lower()
        lines = content.splitlines()
        if not lines:
            continue

        for line_index, line in enumerate(lines):
            for pattern in SYMBOL_DEF_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue

                symbol_name = str(match.group(1) or "").strip()
                symbol_lower = symbol_name.lower()
                if not symbol_name:
                    continue

                term_score = 0.0
                for term in symbol_terms:
                    if term == symbol_lower:
                        term_score += 6.0
                    elif term in symbol_lower:
                        term_score += 2.8

                for identifier in exact_identifiers:
                    ident = str(identifier or "").strip().lower()
                    if not ident:
                        continue
                    if ident == symbol_lower:
                        term_score += 16.0
                    elif ident in symbol_lower:
                        term_score += 4.0

                if term_score <= 0:
                    continue

                hint_bonus = 0.0
                for hint in normalized_hints:
                    if hint and hint in path_lower:
                        hint_bonus += 1.2
                        break

                rank_bonus = max(0.0, 1.4 - file_rank * 0.03)
                total_score = round(term_score + hint_bonus + rank_bonus + base_score * 0.35, 4)
                line_start, line_end, snippet = _build_line_window(lines, line_index, radius=4)
                dedupe_key = (path_lower, symbol_lower)
                if dedupe_key in seen_symbols:
                    continue
                seen_symbols.add(dedupe_key)

                symbol_hits.append(
                    {
                        "id": f"symbol:{relative_path}:{symbol_name}:{line_start}",
                        "label": f"{symbol_name} ({relative_path}:{line_start})",
                        "node_id": symbol_name,
                        "file": relative_path,
                        "file_path": relative_path,
                        "score": total_score,
                        "source": "codebase_symbol_hunt",
                        "sources": ["codebase_symbol_hunt"],
                        "snippet": snippet,
                        "line_start": line_start,
                        "line_end": line_end,
                        "graph_context": [
                            {
                                "type": "symbol_definition",
                                "relation": "defines",
                                "target_id": symbol_name,
                                "target_label": symbol_name,
                            }
                        ],
                    }
                )
                if len(symbol_hits) >= max_hits:
                    return symbol_hits
    return symbol_hits


def _collect_python_ast_hits(
    *,
    text_candidates: List[Dict[str, Any]],
    symbol_terms: List[str],
    exact_identifiers: List[str],
    max_hits: int,
) -> List[Dict[str, Any]]:
    if not text_candidates or not symbol_terms:
        return []

    ast_hits: List[Dict[str, Any]] = []
    seen = set()

    for file_rank, candidate in enumerate(text_candidates[:50], start=1):
        relative_path = str(candidate.get("file") or "").strip()
        if not relative_path.lower().endswith(".py"):
            continue

        content = str(candidate.get("_content") or "")
        if not content:
            continue
        base_score = float(candidate.get("score") or 0.0)

        try:
            tree = ast.parse(content)
        except Exception:
            continue

        lines = content.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue

            symbol_name = str(getattr(node, "name", "") or "").strip()
            symbol_lower = symbol_name.lower()
            if not symbol_name:
                continue

            term_score = 0.0
            for term in symbol_terms:
                if term == symbol_lower:
                    term_score += 6.8
                elif term in symbol_lower:
                    term_score += 3.1
            for identifier in exact_identifiers:
                ident = str(identifier or "").strip().lower()
                if not ident:
                    continue
                if ident == symbol_lower:
                    term_score += 18.0
                elif ident in symbol_lower:
                    term_score += 4.5
            if term_score <= 0:
                continue

            line_start = max(1, int(getattr(node, "lineno", 1) or 1))
            line_end = max(line_start, int(getattr(node, "end_lineno", line_start) or line_start))
            snippet_start, snippet_end, snippet = _build_line_window(lines, line_start - 1, radius=4)
            dedupe_key = (relative_path.lower(), symbol_lower)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            rank_bonus = max(0.0, 1.6 - file_rank * 0.03)
            total_score = round(term_score + base_score * 0.38 + rank_bonus, 4)
            kind = "class" if isinstance(node, ast.ClassDef) else "function"

            ast_hits.append(
                {
                    "id": f"ast:{relative_path}:{symbol_name}:{line_start}",
                    "label": f"{symbol_name} ({relative_path}:{line_start})",
                    "node_id": symbol_name,
                    "file": relative_path,
                    "file_path": relative_path,
                    "score": total_score,
                    "source": "python_ast_hunt",
                    "sources": ["python_ast_hunt"],
                    "snippet": snippet,
                    "line_start": line_start,
                    "line_end": line_end if line_end >= snippet_start else snippet_end,
                    "graph_context": [
                        {
                            "type": "python_ast_definition",
                            "relation": kind,
                            "target_id": symbol_name,
                            "target_label": symbol_name,
                        }
                    ],
                }
            )
            if len(ast_hits) >= max_hits:
                return ast_hits
    return ast_hits


def _collect_import_expansion_hits(
    *,
    project_path: str,
    text_candidates: List[Dict[str, Any]],
    symbol_terms: List[str],
    path_hints: List[str],
    max_hits: int,
) -> List[Dict[str, Any]]:
    if not text_candidates:
        return []

    processor = ImportProcessor(project_path)
    indexed_files: List[str] = []
    for candidate in text_candidates[:120]:
        absolute_path = str(candidate.get("_abs_file_path") or "").strip()
        if absolute_path:
            indexed_files.append(absolute_path)
    if not indexed_files:
        return []
    processor.build_file_index(indexed_files)

    hits: List[Dict[str, Any]] = []
    seen_paths = set()

    for candidate in text_candidates[:45]:
        source_abs_path = str(candidate.get("_abs_file_path") or "").strip()
        source_rel_path = str(candidate.get("file") or "").strip()
        source_content = str(candidate.get("_content") or "")
        if not source_abs_path or not source_rel_path or not source_content:
            continue

        try:
            imports = processor.extract_imports(source_abs_path, source_content)
        except Exception:
            imports = []

        base_score = float(candidate.get("score") or 0.0)
        for imp in imports[:24]:
            try:
                resolved = processor.resolve_import(imp, source_abs_path)
            except Exception:
                resolved = None
            if not resolved or not resolved.resolved_path:
                continue

            resolved_abs_path = os.path.normpath(os.path.abspath(str(resolved.resolved_path)))
            if not os.path.isfile(resolved_abs_path):
                continue

            try:
                resolved_rel_path = os.path.relpath(resolved_abs_path, project_path).replace("\\", "/")
            except Exception:
                continue

            if resolved_rel_path == source_rel_path:
                continue
            if resolved_rel_path.lower() in seen_paths:
                continue

            import_name = str(getattr(imp, "name", "") or "").strip()
            import_path = str(getattr(imp, "path", "") or "").strip()
            text_for_match = f"{import_name} {import_path} {resolved_rel_path}".lower()

            term_score = 0.0
            for term in symbol_terms:
                if term and term in text_for_match:
                    term_score += 1.7
            if term_score <= 0:
                matched_by_hint = False
                for hint in path_hints:
                    hint_text = os.path.basename(str(hint).lower())
                    if hint_text and hint_text in resolved_rel_path.lower():
                        matched_by_hint = True
                        break
                if not matched_by_hint:
                    continue
                term_score += 0.9

            target_content = _safe_read_text(resolved_abs_path, max_bytes=120_000)
            target_terms = symbol_terms if symbol_terms else _extract_query_terms(import_name)
            line_start, line_end, snippet = _build_snippet(target_content, target_terms, path_hints)
            confidence_bonus = max(0.0, float(getattr(resolved, "confidence", 0.0) or 0.0)) * 2.6
            total_score = round(base_score * 0.45 + term_score + confidence_bonus, 4)

            hits.append(
                {
                    "id": f"import:{resolved_rel_path}:{line_start}",
                    "label": f"{import_name or import_path or resolved_rel_path} -> {resolved_rel_path}:{line_start}",
                    "node_id": import_name,
                    "file": resolved_rel_path,
                    "file_path": resolved_rel_path,
                    "score": total_score,
                    "source": "codebase_import_hunt",
                    "sources": ["codebase_import_hunt"],
                    "snippet": snippet,
                    "line_start": line_start,
                    "line_end": line_end,
                    "graph_context": [
                        {
                            "type": "import_expansion",
                            "relation": str(getattr(resolved, "reason", "import-resolved") or "import-resolved"),
                            "target_id": resolved_rel_path,
                            "target_label": resolved_rel_path,
                            "source_file": source_rel_path,
                        }
                    ],
                }
            )
            seen_paths.add(resolved_rel_path.lower())
            if len(hits) >= max_hits:
                return hits
    return hits


def _source_priority(source: str) -> int:
    mapping = {
        "python_ast_hunt": 5,
        "codebase_symbol_hunt": 4,
        "codebase_followup_symbol_hunt": 3,
        "codebase_import_hunt": 2,
        "codebase_followup_import_hunt": 1,
    }
    return mapping.get(str(source or ""), 0)


def _retag_hits_source(hits: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    retagged: List[Dict[str, Any]] = []
    for item in hits:
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        normalized["source"] = source
        normalized["sources"] = [source]
        retagged.append(normalized)
    return retagged


def _derive_followup_terms(base_terms: List[str], hits: List[Dict[str, Any]], limit: int = 24) -> List[str]:
    terms = list(base_terms)
    for item in hits[:12]:
        if not isinstance(item, dict):
            continue
        seeds = [
            str(item.get("node_id") or ""),
            str(item.get("label") or ""),
            str(item.get("file") or item.get("file_path") or ""),
        ]
        for seed in seeds:
            for token in _extract_symbol_candidates(seed):
                terms.append(token)
    return _dedupe_terms(terms, limit=limit)


def run_codebase_retrieval(
    *,
    project_path: str,
    query: str,
    top_k: int = 8,
    max_files: int = 400,
    max_file_bytes: int = 200_000,
) -> Dict[str, Any]:
    normalized_project_path = _normalize_project_path(project_path)
    query_text = str(query or "").strip()
    if not query_text:
        return {
            "ok": False,
            "error": "query 不能为空",
            "hits": [],
            "stats": {"scanned_files": 0, "matched_files": 0},
        }
    if not normalized_project_path or not os.path.isdir(normalized_project_path):
        return {
            "ok": False,
            "error": f"project_path 不存在或不是目录: {project_path}",
            "hits": [],
            "stats": {"scanned_files": 0, "matched_files": 0},
        }

    query_plans = _build_query_plans(query_text)
    if not query_plans:
        return {
            "ok": False,
            "error": "query 不能为空",
            "hits": [],
            "stats": {"scanned_files": 0, "matched_files": 0},
        }

    terms: List[str] = _dedupe_terms(
        [term for plan in query_plans for term in (plan.get("terms") or [])],
        limit=24,
    )
    symbol_terms: List[str] = _dedupe_terms(
        [term for plan in query_plans for term in (plan.get("symbol_terms") or [])],
        limit=30,
    )
    exact_identifiers: List[str] = _dedupe_terms(
        [term for plan in query_plans for term in (plan.get("exact_identifiers") or [])],
        limit=20,
    )
    path_hints: List[str] = _dedupe_terms(
        [hint for plan in query_plans for hint in (plan.get("path_hints") or [])],
        limit=12,
    )

    candidates: List[Dict[str, Any]] = []
    scanned_files = 0
    for absolute_path in _iter_code_files(normalized_project_path, max_files=max_files):
        scanned_files += 1
        relative_path = os.path.relpath(absolute_path, normalized_project_path).replace("\\", "/")
        content = _safe_read_text(absolute_path, max_bytes=max_file_bytes)
        if not content:
            continue

        content_lower = content.lower()
        best_plan: Optional[Dict[str, Any]] = None
        best_score = 0.0
        for plan in query_plans:
            plan_query = str(plan.get("query") or "")
            plan_terms = _as_string_list(plan.get("terms"))
            plan_hints = _as_string_list(plan.get("path_hints"))
            plan_identifiers = _as_string_list(plan.get("exact_identifiers"))
            weighted_score = _score_match(
                relative_path=relative_path,
                content_lower=content_lower,
                query_lower=plan_query.lower(),
                terms=plan_terms,
                path_hints=plan_hints,
                exact_identifiers=plan_identifiers,
            ) * float(plan.get("weight") or 1.0)
            if weighted_score > best_score:
                best_score = weighted_score
                best_plan = plan

        if best_score <= 0:
            continue

        snippet_terms = _as_string_list(best_plan.get("terms")) if isinstance(best_plan, dict) else terms
        snippet_hints = _as_string_list(best_plan.get("path_hints")) if isinstance(best_plan, dict) else path_hints
        if not snippet_terms:
            snippet_terms = terms
        if not snippet_hints:
            snippet_hints = path_hints
        line_start, line_end, snippet = _build_snippet(content, snippet_terms, snippet_hints)
        candidates.append(
            {
                "id": f"file:{relative_path}:{line_start}",
                "label": f"{relative_path}:{line_start}",
                "node_id": "",
                "file": relative_path,
                "file_path": relative_path,
                "score": round(best_score, 4),
                "source": "codebase_scan",
                "sources": ["codebase_scan"],
                "snippet": snippet,
                "line_start": line_start,
                "line_end": line_end,
                "plan_query": str(best_plan.get("query") or query_text) if isinstance(best_plan, dict) else query_text,
                "plan_kind": str(best_plan.get("kind") or "primary") if isinstance(best_plan, dict) else "primary",
                "graph_context": [
                    {
                        "type": "codebase_file",
                        "relation": "text_match",
                        "target_id": relative_path,
                        "target_label": relative_path,
                    }
                ],
                "_content": content,
                "_abs_file_path": absolute_path,
            }
        )

    candidates.sort(key=lambda item: (float(item.get("score") or 0.0), -len(str(item.get("file") or ""))), reverse=True)
    symbol_hits = _collect_symbol_hits(
        text_candidates=candidates,
        symbol_terms=symbol_terms,
        exact_identifiers=exact_identifiers,
        path_hints=path_hints,
        max_hits=max(4, min(int(top_k), 20)),
    )
    ast_hits = _collect_python_ast_hits(
        text_candidates=candidates,
        symbol_terms=symbol_terms,
        exact_identifiers=exact_identifiers,
        max_hits=max(4, min(int(top_k), 20)),
    )
    import_hits = _collect_import_expansion_hits(
        project_path=normalized_project_path,
        text_candidates=candidates,
        symbol_terms=symbol_terms,
        path_hints=path_hints,
        max_hits=max(3, min(int(top_k), 12)),
    )

    seed_hits = [*symbol_hits, *ast_hits, *import_hits]
    followup_terms = _derive_followup_terms(symbol_terms, seed_hits, limit=30)
    followup_symbol_hits = _retag_hits_source(
        _collect_symbol_hits(
            text_candidates=candidates,
            symbol_terms=followup_terms,
            exact_identifiers=exact_identifiers,
            path_hints=path_hints,
            max_hits=max(3, min(int(top_k), 10)),
        ),
        source="codebase_followup_symbol_hunt",
    )
    followup_import_hits = _retag_hits_source(
        _collect_import_expansion_hits(
            project_path=normalized_project_path,
            text_candidates=candidates,
            symbol_terms=followup_terms,
            path_hints=path_hints,
            max_hits=max(2, min(int(top_k), 8)),
        ),
        source="codebase_followup_import_hunt",
    )

    merged_hits = [
        *candidates,
        *symbol_hits,
        *ast_hits,
        *import_hits,
        *followup_symbol_hits,
        *followup_import_hits,
    ]
    merged_hits.sort(
        key=lambda item: (
            float(item.get("score") or 0.0),
            _source_priority(str(item.get("source") or "")),
            -len(str(item.get("file") or "")),
        ),
        reverse=True,
    )

    hits: List[Dict[str, Any]] = []
    seen_hit_keys = set()
    file_hit_counts: Dict[str, int] = {}
    for item in merged_hits:
        if len(hits) >= max(1, min(int(top_k), 20)):
            break
        file_key = str(item.get("file") or item.get("file_path") or "").strip().lower()
        if file_key:
            current_count = int(file_hit_counts.get(file_key) or 0)
            if current_count >= 2:
                continue
        key = (
            str(item.get("file") or "").lower(),
            str(item.get("line_start") or ""),
            str(item.get("source") or "").lower(),
        )
        if key in seen_hit_keys:
            continue
        seen_hit_keys.add(key)
        normalized = dict(item)
        normalized.pop("_content", None)
        normalized.pop("_abs_file_path", None)
        hits.append(normalized)
        if file_key:
            file_hit_counts[file_key] = int(file_hit_counts.get(file_key) or 0) + 1

    return {
        "ok": bool(hits),
        "error": None if hits else "代码库检索未命中明显相关片段",
        "hits": hits,
        "stats": {
            "scanned_files": scanned_files,
            "matched_files": len(candidates),
            "symbol_hits": len(symbol_hits),
            "ast_hits": len(ast_hits),
            "import_hits": len(import_hits),
            "followup_symbol_hits": len(followup_symbol_hits),
            "followup_import_hits": len(followup_import_hits),
            "top_k": max(1, min(int(top_k), 20)),
            "terms": terms,
            "symbol_terms": symbol_terms,
            "exact_identifiers": exact_identifiers,
            "followup_terms": followup_terms,
            "query_plans": [
                {
                    "query": str(plan.get("query") or ""),
                    "kind": str(plan.get("kind") or "primary"),
                    "weight": float(plan.get("weight") or 1.0),
                }
                for plan in query_plans
            ],
            "strategy": [
                "codebase_scan",
                "symbol_hunt",
                "python_ast_hunt",
                "import_hunt",
                "followup_symbol_hunt",
                "followup_import_hunt",
            ],
        },
    }
