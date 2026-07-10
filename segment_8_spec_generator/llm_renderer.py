#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from config.config import has_deepseek_config


def _extract_llm_text(response: Dict[str, Any]) -> str:
    choices = response.get("choices") if isinstance(response, dict) else None
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            return str(message.get("content") or "").strip()
    return ""


def maybe_enrich_sections(sections: Dict[str, Any], graph_context: Dict[str, Any], *, skip_llm: bool) -> Tuple[Dict[str, Any], str, str | None]:
    if skip_llm:
        return sections, "skipped_by_flag", None
    if not has_deepseek_config():
        return sections, "skipped_no_llm_configured", None
    try:
        from llm.rag_core.llm_api import DeepSeekAPI

        client = DeepSeekAPI(timeout=20)
        prompt = (
            "你是代码架构说明书编辑器。请仅基于给定 JSON 骨架润色 8 个段落，不要新增未验证的方法名或路径 ID。"
            "返回 JSON 对象，keys 必须保持不变。\n\n"
            + json.dumps({"sections": sections, "graph_queries_used": graph_context.get("graph_queries_used", [])}, ensure_ascii=False, sort_keys=True)[:12000]
        )
        response = client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1800,
            timeout=20,
        )
        text = _extract_llm_text(response)
        if not text:
            return sections, "partial_llm_failed", "LLM returned empty content"
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        parsed = json.loads(cleaned)
        enriched = parsed.get("sections") if isinstance(parsed, dict) else None
        if not isinstance(enriched, dict):
            return sections, "partial_llm_failed", "LLM response did not contain sections object"
        return {**sections, **{key: enriched.get(key, sections.get(key)) for key in sections}}, "completed", None
    except Exception as exc:
        return sections, "partial_llm_failed", str(exc)
