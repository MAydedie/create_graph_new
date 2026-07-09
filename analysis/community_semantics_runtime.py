#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config.config import FH_COMMUNITY_LLM_THRESHOLD, FH_FORCE_COMMUNITY_LLM
from llm.llm_helper import LLMConfig, LLMHelper


def clone_partition(partition: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(partition if isinstance(partition, dict) else {})


def resolve_community_llm_threshold(default: float = FH_COMMUNITY_LLM_THRESHOLD) -> float:
    raw_value = os.getenv("FH_COMMUNITY_LLM_THRESHOLD")
    if raw_value is None:
        return float(default)
    try:
        return float(str(raw_value).strip())
    except (TypeError, ValueError):
        return float(default)


def resolve_force_community_llm(default: bool = FH_FORCE_COMMUNITY_LLM) -> bool:
    raw_value = os.getenv("FH_FORCE_COMMUNITY_LLM")
    if raw_value is None:
        return bool(default)
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def plan_community_semantics(
    partitions: List[Dict[str, Any]],
    *,
    threshold: Optional[float] = None,
    force: Optional[bool] = None,
    skip_llm: bool = False,
) -> Dict[str, Any]:
    resolved_threshold = float(resolve_community_llm_threshold() if threshold is None else threshold)
    resolved_force = resolve_force_community_llm() if force is None else bool(force)
    modularities = [float(partition.get("modularity") or 0.0) for partition in (partitions or [])]
    avg_modularity = (sum(modularities) / len(modularities)) if modularities else 0.0

    if skip_llm:
        return {
            "should_run": False,
            "trigger_mode": "skip",
            "avg_modularity": avg_modularity,
            "threshold": resolved_threshold,
            "reason": "skip_llm flag enabled",
        }

    if resolved_force:
        return {
            "should_run": True,
            "trigger_mode": "force",
            "avg_modularity": avg_modularity,
            "threshold": resolved_threshold,
            "reason": "forced by flag or environment",
        }

    if avg_modularity < resolved_threshold:
        return {
            "should_run": True,
            "trigger_mode": "threshold",
            "avg_modularity": avg_modularity,
            "threshold": resolved_threshold,
            "reason": f"avg_modularity {avg_modularity:.4f} is below threshold {resolved_threshold:.4f}",
        }

    return {
        "should_run": False,
        "trigger_mode": "skip",
        "avg_modularity": avg_modularity,
        "threshold": resolved_threshold,
        "reason": f"avg_modularity {avg_modularity:.4f} is not below threshold {resolved_threshold:.4f}",
    }


def build_stage4_run_id(source: str = "stage4", stable_token: str = "") -> str:
    normalized_source = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(source or "stage4"))
    if stable_token:
        digest = hashlib.md5(str(stable_token).encode("utf-8")).hexdigest()[:16]
        return f"{normalized_source[:48]}_{digest}"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{normalized_source[:48]}_{timestamp}"


def build_placeholder_summary(
    partition: Dict[str, Any],
    *,
    status: str,
    reason: str,
    model: str = "",
    duration_ms: int = 0,
) -> Dict[str, Any]:
    partition_copy = clone_partition(partition)
    label = str(partition_copy.get("name") or partition_copy.get("partition_id") or "Unnamed Community").strip()
    partition_copy.update(
        {
            "label": label[:80],
            "description": reason.strip(),
            "functional_domain": "",
            "key_concepts": [],
            "top_files": partition_copy.get("top_files") or [],
            "top_dependencies": partition_copy.get("top_dependencies") or [],
            "summary_status": status,
            "skip_reason": reason.strip() if status != "completed" else None,
            "model": model or None,
            "duration_ms": int(duration_ms or 0),
        }
    )
    return partition_copy


def build_history_entry(
    partition_id: str,
    *,
    status: str,
    reason: str,
    trigger_mode: str,
    threshold: float,
    model: str = "",
    duration_ms: int = 0,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "partition_id": partition_id,
        "action": "summary",
        "status": status,
        "llm_reasoning": reason,
        "details": details or {"status": status},
        "trigger_mode": trigger_mode,
        "threshold": float(threshold),
        "skip_reason": reason if status != "completed" else None,
        "model": model or None,
        "duration_ms": int(duration_ms or 0),
    }


def parse_summary_json(raw_text: str) -> Dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        raise ValueError("empty summary response")

    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S | re.I)
    candidates = fenced + re.findall(r"(\{.*\})", text, flags=re.S)
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("summary response must be a JSON object")
    return payload


def build_llm_helper(settings: Dict[str, Any]) -> LLMHelper:
    return LLMHelper(
        LLMConfig(
            api_key=str(settings.get("api_key") or "").strip(),
            base_url=str(settings.get("base_url") or "").strip() or "https://api.deepseek.com/v1",
            model=str(settings.get("model") or "deepseek-v4-flash").strip(),
            temperature=0.1,
            max_tokens=1200,
            timeout=20,
            max_retries=2,
            retry_backoff_base=0.5,
        )
    )


def summarize_partition_with_llm(helper: LLMHelper, community_context: Dict[str, Any]) -> Dict[str, Any]:
    system_prompt = (
        "你是代码社区语义分析器。"
        "请只输出 JSON 对象，不要输出 Markdown。"
        "字段必须包含：label, description, functional_domain, key_concepts, top_files, top_dependencies。"
        "label 控制在 1-10 个词；description 用 50-200 字概括社区职责、入口、依赖与主要协作对象。"
    )
    user_prompt = json.dumps(community_context, ensure_ascii=False, sort_keys=True)
    started_at = time.perf_counter()
    raw_text = helper.call(system_prompt=system_prompt, user_prompt=user_prompt, use_cache=False)
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    parsed = parse_summary_json(raw_text)
    parsed["duration_ms"] = duration_ms
    return parsed
