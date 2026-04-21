#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Conversation-first 会话服务（Phase 1/2）"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from flask import Response, jsonify, request, stream_with_context

from config.config import get_deepseek_settings, has_deepseek_config
from app.services.codebase_retrieval_service import run_codebase_retrieval
from data.data_accessor import get_data_accessor
from llm.agent.utils.question_detector import QuestionDetector
from llm.rag_core.llm_api import DeepSeekAPI
from src.search.adapters.hybrid_shadow_adapter import run_hybrid_shadow


data_accessor = get_data_accessor()


COMPACTION_KEEP_RECENT_MESSAGES = 10
COMPACTION_MIN_MESSAGES = 24
COMPACTION_MIN_TEXT_CHARS = 12000
DEFAULT_RUNBOOK_REPORT_DIR = r"D:\代码仓库生图\汇报\4.6"

PROJECT_PURPOSE_KEYWORDS = [
    "这个项目是做啥",
    "这个项目做什么",
    "项目是做什么",
    "这个项目能干嘛",
    "能用来干嘛",
    "项目用途",
    "项目介绍",
    "能做什么",
    "what is this project",
    "what does this project do",
    "what can i use this project for",
    "project purpose",
]

PROJECT_SUBJECT_MARKERS = [
    "项目",
    "系统",
    "这套",
    "这玩意",
    "这个东西",
    "this project",
    "this system",
]

PROJECT_PURPOSE_INTENT_MARKERS = [
    "干嘛",
    "做什么",
    "用途",
    "能用来",
    "能解决",
    "适合谁",
    "第一步",
    "核心能力",
    "更像",
    "价值",
    "what for",
    "used for",
    "core capability",
]

SKILL_FOCUS_MARKERS = [
    ("data/skills.json", "技能注册表"),
    ("script/skill_agent.py", "技能匹配代理"),
    ("API/api_skills.py", "技能推荐接口"),
    ("skill_callchain_v2", "技能调用链"),
    (".skill", "技能库目录"),
]


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_slug(value: Any, fallback: str = "item", max_len: int = 48) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    text = re.sub(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", "_", text)
    text = text.strip("_")
    return (text[:max_len] or fallback)


def _normalize_report_dir(raw_value: Any) -> Path:
    text = str(raw_value or "").strip() or DEFAULT_RUNBOOK_REPORT_DIR
    path = Path(text)
    if not path.is_absolute():
        path = Path(os.path.abspath(text))
    return path


def _build_runbook_export_basename(conversation_id: str, stage: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cid = _safe_slug(conversation_id, fallback="conversation", max_len=24)
    stage_slug = _safe_slug(stage or "stage", fallback="stage", max_len=24)
    return f"{cid}_{stage_slug}_{ts}"


def _emit_conversation_event(conversation_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    try:
        data_accessor.append_conversation_event(conversation_id, event_type, payload)
    except Exception:
        return


def _extract_path_hints_from_text(text: str) -> List[str]:
    content = str(text or "")
    if not content:
        return []
    hints: List[str] = []
    matches = re.findall(r"[A-Za-z]:\\[^\s,;，；]+|[^\s,;，；]+\.(?:py|ts|tsx|js|java|md)", content)
    for item in matches:
        hint = str(item or "").strip()
        if hint and hint not in hints:
            hints.append(hint)
    return hints


def _dedupe_keep_order(values: List[str], limit: int = 50) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    if len(result) > limit:
        return result[-limit:]
    return result


def _normalize_query_cache_key(query: str) -> str:
    value = str(query or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def _is_project_purpose_query(user_query: str) -> bool:
    query = str(user_query or "").strip().lower()
    if not query:
        return False
    if any(keyword in query for keyword in PROJECT_PURPOSE_KEYWORDS):
        return True
    has_subject = any(marker in query for marker in PROJECT_SUBJECT_MARKERS)
    has_intent = any(marker in query for marker in PROJECT_PURPOSE_INTENT_MARKERS)
    return has_subject and has_intent


def _build_project_identity_profile(project_path: str) -> Dict[str, Any]:
    normalized_project_path = _normalize_project_path(project_path)
    if not normalized_project_path or not os.path.isdir(normalized_project_path):
        return {
            "projectPath": project_path,
            "isSkillFirst": False,
            "purpose": "当前项目可用于代码分析与问答协作。",
            "evidence": [],
        }

    evidence: List[Dict[str, str]] = []
    for relative_path, label in SKILL_FOCUS_MARKERS:
        absolute_path = os.path.join(normalized_project_path, relative_path)
        if os.path.exists(absolute_path):
            evidence.append({"path": relative_path.replace('\\', '/'), "label": label})

    project_name = os.path.basename(normalized_project_path).lower()
    is_skill_first = len(evidence) >= 2 or "skill" in project_name
    if is_skill_first:
        purpose = "这是一个以 skill 技能库选取/匹配为主轴的系统，RAG 用于提供辅助证据而不是主导回答。"
    else:
        purpose = "这是一个面向代码仓库理解、检索与任务编排的问答系统。"

    return {
        "projectPath": normalized_project_path,
        "isSkillFirst": is_skill_first,
        "purpose": purpose,
        "evidence": evidence,
    }


def _contains_any_phrase(text: str, phrases: List[str]) -> bool:
    content = str(text or "").lower()
    return any(str(phrase or "").lower() in content for phrase in phrases)


def _build_skill_first_fallback_answer(user_query: str, project_path: str, llm_error: str = "") -> str:
    profile = _build_project_identity_profile(project_path)
    evidence_raw = profile.get("evidence")
    evidence: List[Dict[str, Any]] = evidence_raw if isinstance(evidence_raw, list) else []

    evidence_lines: List[str] = []
    for item in evidence:
        if len(evidence_lines) >= 3:
            break
        if not isinstance(item, dict):
            continue
        item_path = str(item.get("path") or "").strip()
        item_label = str(item.get("label") or "").strip()
        if not item_path:
            continue
        if item_label:
            evidence_lines.append(f"- `{item_path}`：{item_label}")
        else:
            evidence_lines.append(f"- `{item_path}`")

    query = str(user_query or "").strip()
    audience_markers = ["适合谁", "谁用", "团队", "小白", "新手"]
    first_step_markers = ["第一步", "从哪下手", "怎么开始", "先做什么"]
    compare_markers = ["更像", "还是", "偏", "聊天助手", "工作流"]
    risk_markers = ["会不会", "答非所问", "看不懂", "检索结果"]
    planning_markers = ["选方案", "给方向", "下一步", "怎么改"]

    if _contains_any_phrase(query, audience_markers):
        body = "它最适合在需求还比较模糊时使用：先帮你从技能库里选对能力，再给下一步行动建议。"
    elif _contains_any_phrase(query, first_step_markers):
        body = "第一步通常是先把你的目标场景归类，再从技能库里挑最匹配的 skill，最后给出可执行的下一步。"
    elif _contains_any_phrase(query, compare_markers):
        body = "它不是纯聊天机器人，更像“技能路由 + 辅助检索”的工作流入口。"
    elif _contains_any_phrase(query, risk_markers):
        body = "默认会尽量先给可执行方向，不会先甩一堆检索片段；只有关键事实缺失时才补检索证据。"
    elif _contains_any_phrase(query, planning_markers):
        body = "可以，它的核心价值就是把模糊需求先路由到合适 skill，再给你更可落地的方案方向。"
    else:
        body = "这是一个以 skill 技能库选取为主轴的问答系统：先选能力，再回答，RAG 只做辅助证据。"

    lines = [
        "### 回答",
        f"- {body}",
        "",
        "### 依据",
        *(evidence_lines or ["- 当前项目证据未命中，请确认 project_path 是否正确。"]),
    ]
    if llm_error:
        lines += [
            "",
            "### 说明",
            "- 当前模型调用失败，已自动切换为规则化回答。",
        ]
    return "\n".join(lines)


def _prefer_project_intro_action(user_query: str, project_path: str) -> Optional[Dict[str, Any]]:
    if not _is_project_purpose_query(user_query):
        return None
    profile = _build_project_identity_profile(project_path)
    reason = "项目定位问答优先走会话直答，避免检索片段主导语义"
    if bool(profile.get("isSkillFirst")):
        reason = "项目定位问答命中 skill-first 特征，优先输出技能库主轴"
    return {
        "action": "general_chat",
        "task_mode": "none",
        "reason": reason,
        "confidence": 0.88,
    }


def _compact_highlights_for_memory(highlights: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    compacted: List[Dict[str, Any]] = []
    for item in highlights[:limit]:
        if not isinstance(item, dict):
            continue
        snippet = str(item.get("snippet") or "").strip()
        compacted.append(
            {
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or item.get("id") or ""),
                "file": str(item.get("file") or item.get("file_path") or ""),
                "score": item.get("score"),
                "sources": item.get("sources") if isinstance(item.get("sources"), list) else [],
                "lineStart": item.get("lineStart") if item.get("lineStart") is not None else item.get("line_start"),
                "lineEnd": item.get("lineEnd") if item.get("lineEnd") is not None else item.get("line_end"),
                "snippet": snippet[:420],
            }
        )
    return compacted


def _find_cached_retrieval(conversation_id: str, user_query: str) -> Optional[Dict[str, Any]]:
    memory = data_accessor.get_conversation_key_facts_memory(conversation_id)
    retrieval_cache_raw = memory.get("retrievalCache")
    cache_items: List[Dict[str, Any]] = []
    if isinstance(retrieval_cache_raw, list):
        for raw_item in retrieval_cache_raw:
            if isinstance(raw_item, dict):
                cache_items.append(raw_item)
    query_key = _normalize_query_cache_key(user_query)
    if not query_key:
        return None
    for item in list(reversed(cache_items)):
        if not isinstance(item, dict):
            continue
        if _normalize_query_cache_key(str(item.get("queryKey") or "")) != query_key:
            continue
        highlights_raw = item.get("highlights")
        highlights: List[Dict[str, Any]] = [hit for hit in highlights_raw if isinstance(hit, dict)] if isinstance(highlights_raw, list) else []
        if not highlights:
            continue
        return {
            "highlights": highlights,
            "searchSummary": item.get("searchSummary") if isinstance(item.get("searchSummary"), dict) else {},
            "updatedAt": str(item.get("updatedAt") or ""),
        }
    return None


def _remember_retrieval_cache(
    conversation_id: str,
    *,
    user_query: str,
    highlights: List[Dict[str, Any]],
    search_summary: Dict[str, Any],
) -> None:
    query_key = _normalize_query_cache_key(user_query)
    if not query_key or not highlights:
        return

    memory = data_accessor.get_conversation_key_facts_memory(conversation_id)
    if not isinstance(memory, dict):
        memory = {}
    retrieval_cache_raw = memory.get("retrievalCache")
    cache_items: List[Dict[str, Any]] = []
    if isinstance(retrieval_cache_raw, list):
        for raw_item in retrieval_cache_raw:
            if isinstance(raw_item, dict):
                cache_items.append(raw_item)

    next_cache: List[Dict[str, Any]] = []
    for item in cache_items:
        if not isinstance(item, dict):
            continue
        if _normalize_query_cache_key(str(item.get("queryKey") or "")) == query_key:
            continue
        next_cache.append(item)

    next_cache.append(
        {
            "queryKey": query_key,
            "query": user_query,
            "highlights": _compact_highlights_for_memory(highlights, limit=8),
            "searchSummary": search_summary if isinstance(search_summary, dict) else {},
            "updatedAt": _utcnow_iso(),
        }
    )
    if len(next_cache) > 12:
        next_cache = next_cache[-12:]

    memory["retrievalCache"] = next_cache
    memory["updatedAt"] = _utcnow_iso()
    data_accessor.save_conversation_key_facts_memory(conversation_id, memory, merge=False)


def _update_key_facts_memory(
    conversation_id: str,
    *,
    user_query: str,
    project_path: str,
    action: str,
    task_mode: Optional[str],
    reason: str,
    clarification_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    existing = data_accessor.get_conversation_key_facts_memory(conversation_id)
    if not isinstance(existing, dict):
        existing = {}

    path_hints = _dedupe_keep_order(
        list(existing.get("pathHints") or []) + _extract_path_hints_from_text(user_query),
        limit=80,
    )
    decisions = list(existing.get("decisions") or [])
    decisions.append(
        {
            "action": action,
            "taskMode": task_mode,
            "reason": reason,
            "at": _utcnow_iso(),
        }
    )
    if len(decisions) > 20:
        decisions = decisions[-20:]

    selected_options: List[str] = []
    if isinstance(clarification_context, dict):
        raw = clarification_context.get("selectedOptionLabels")
        if isinstance(raw, list):
            selected_options = [str(item).strip() for item in raw if str(item).strip()]

    memory = {
        "version": "v2",
        "updatedAt": _utcnow_iso(),
        "projectPath": project_path,
        "recentUserGoal": user_query,
        "taskMode": task_mode,
        "pathHints": path_hints,
        "selectedOptionLabels": _dedupe_keep_order(
            list(existing.get("selectedOptionLabels") or []) + selected_options,
            limit=40,
        ),
        "decisions": decisions,
        "retrievalCache": list(existing.get("retrievalCache") or [])[:12],
    }
    return data_accessor.save_conversation_key_facts_memory(conversation_id, memory, merge=False)


def _should_compact_conversation(messages: List[Dict[str, Any]]) -> bool:
    if len(messages) < COMPACTION_MIN_MESSAGES:
        return False
    total_chars = 0
    for item in messages:
        if not isinstance(item, dict):
            continue
        total_chars += len(str(item.get("content") or ""))
    return total_chars >= COMPACTION_MIN_TEXT_CHARS


def _build_compaction_snapshot(
    conversation_id: str,
    messages_to_compact: List[Dict[str, Any]],
    project_path: str,
) -> Dict[str, Any]:
    digest_lines: List[str] = []
    for item in messages_to_compact[-14:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip() or "unknown"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        digest_lines.append(f"{role}: {content[:140]}")
    summary = "\n".join(digest_lines) if digest_lines else "压缩段无可用文本摘要。"

    first_id = ""
    last_id = ""
    if messages_to_compact:
        first = messages_to_compact[0] if isinstance(messages_to_compact[0], dict) else {}
        last = messages_to_compact[-1] if isinstance(messages_to_compact[-1], dict) else {}
        first_id = str(first.get("messageId") or "")
        last_id = str(last.get("messageId") or "")

    return {
        "snapshotId": uuid4().hex,
        "conversationId": conversation_id,
        "projectPath": project_path,
        "strategy": "layered_compaction_v1",
        "compressedMessageCount": len(messages_to_compact),
        "range": {
            "startMessageId": first_id,
            "endMessageId": last_id,
        },
        "summary": summary,
        "createdAt": _utcnow_iso(),
    }


def _maybe_compact_conversation(conversation_id: str, project_path: str) -> Optional[Dict[str, Any]]:
    payload = data_accessor.get_conversation(conversation_id)
    if not isinstance(payload, dict):
        return None
    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list):
        return None

    messages: List[Dict[str, Any]] = [item for item in raw_messages if isinstance(item, dict)]
    if not _should_compact_conversation(messages):
        return None
    if len(messages) <= COMPACTION_KEEP_RECENT_MESSAGES + 1:
        return None

    to_compact = messages[:-COMPACTION_KEEP_RECENT_MESSAGES]
    recent = messages[-COMPACTION_KEEP_RECENT_MESSAGES:]
    snapshot = _build_compaction_snapshot(conversation_id, to_compact, project_path)

    compaction_message = {
        "messageId": uuid4().hex,
        "role": "system",
        "content": f"[CompactionSnapshot] {snapshot.get('summary')}",
        "createdAt": _utcnow_iso(),
        "meta": {
            "snapshotId": snapshot.get("snapshotId"),
            "compaction": True,
        },
    }

    payload["messages"] = [compaction_message] + recent
    summary_snapshot = {
        "summary": str(snapshot.get("summary") or ""),
        "messageCount": len(payload["messages"]),
        "pendingQuestion": payload.get("pendingQuestion"),
        "keyFacts": data_accessor.get_conversation_key_facts_memory(conversation_id),
        "generatedAt": _utcnow_iso(),
        "strategy": "layered_compaction_v1",
    }
    payload["summarySnapshot"] = summary_snapshot
    raw_history = payload.get("compactionHistory")
    history: List[Dict[str, Any]] = list(raw_history) if isinstance(raw_history, list) else []
    history.append(snapshot)
    payload["compactionHistory"] = history
    payload["updatedAt"] = _utcnow_iso()
    data_accessor.save_conversation(conversation_id, payload)

    data_accessor.append_conversation_part(
        conversation_id,
        {
            "type": "compaction",
            "content": str(snapshot.get("summary") or ""),
            "metadata": snapshot,
        },
    )
    _emit_conversation_event(
        conversation_id,
        "conversation.compacted",
        {
            "snapshotId": snapshot.get("snapshotId"),
            "compressedMessageCount": snapshot.get("compressedMessageCount"),
        },
    )
    return snapshot


def _normalize_project_path(project_path: Optional[str]) -> str:
    if not project_path:
        return ""
    return os.path.normpath(os.path.abspath(str(project_path)))


def _normalize_output_root(raw_output_root: Any) -> Optional[str]:
    text = str(raw_output_root or "").strip()
    if not text:
        return None
    if not os.path.isabs(text):
        return None
    return os.path.normpath(os.path.abspath(text))


def _normalize_reply_payload(raw_payload: Any) -> Dict[str, Any]:
    if not isinstance(raw_payload, dict):
        return {}
    payload = dict(raw_payload)
    payload.setdefault("replyId", uuid4().hex)
    payload.setdefault("createdAt", _utcnow_iso())
    return payload


_RUNTIME_LLM_DEFAULTS: Dict[str, Dict[str, str]] = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "openai/gpt-4o-mini"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "glm": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4.5"},
    "kimi": {"base_url": "https://api.moonshot.ai/v1", "model": "kimi-k2.5"},
    "minimax": {"base_url": "https://api.minimax.io/v1", "model": "MiniMax-M2.5"},
    "doubao": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": "doubao-seed-1-6-250615"},
}


def _parse_runtime_llm_config(raw_value: Any) -> Optional[Dict[str, str]]:
    if not isinstance(raw_value, dict):
        return None

    provider = str(raw_value.get("provider") or "").strip().lower()
    defaults = _RUNTIME_LLM_DEFAULTS.get(provider)

    api_key = str(raw_value.get("api_key") or raw_value.get("apiKey") or "").strip()
    if not api_key:
        return None

    base_url = str(raw_value.get("base_url") or raw_value.get("baseUrl") or "").strip()
    model = str(raw_value.get("model") or "").strip()

    if not base_url and defaults:
        base_url = defaults.get("base_url") or ""
    if not model and defaults:
        model = defaults.get("model") or ""

    if not base_url or not model:
        return None

    normalized_base = base_url.rstrip("/")
    if normalized_base.endswith("/chat/completions"):
        normalized_base = normalized_base[: -len("/chat/completions")]

    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": normalized_base,
        "model": model,
    }


def _create_deepseek_client(llm_config: Optional[Dict[str, str]] = None) -> Optional[DeepSeekAPI]:
    runtime_settings = llm_config if isinstance(llm_config, dict) else None
    if runtime_settings:
        api_key = str(runtime_settings.get("api_key") or "").strip()
        base_url = str(runtime_settings.get("base_url") or "").strip()
        model = str(runtime_settings.get("model") or "").strip()
        if api_key and base_url and model:
            try:
                return DeepSeekAPI(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    timeout=45,
                )
            except Exception:
                return None

    if not has_deepseek_config():
        return None
    settings = get_deepseek_settings()
    api_key = str(settings.get("api_key") or "").strip()
    if not api_key:
        return None
    try:
        return DeepSeekAPI(
            api_key=api_key,
            base_url=str(settings.get("base_url") or "https://api.deepseek.com/v1").strip(),
            model=str(settings.get("model") or "deepseek-chat").strip(),
            timeout=45,
        )
    except Exception:
        return None


def _extract_text_from_response(response: Dict[str, Any]) -> str:
    if not isinstance(response, dict):
        return ""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return str(content or "").strip()


def _parse_json_text(text: str) -> Dict[str, Any]:
    body = str(text or "").strip()
    if not body:
        return {}
    try:
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    start = body.find("{")
    end = body.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    candidate = body[start : end + 1]
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _history_for_prompt(conversation_id: str, limit: int = 8) -> List[Dict[str, str]]:
    messages = data_accessor.list_conversation_messages(conversation_id)
    if not messages:
        return []
    picked = messages[-limit:]
    result: List[Dict[str, str]] = []
    for item in picked:
        role = str(item.get("role") or "user").strip() or "user"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        result.append({"role": role, "content": content})
    return result


def _fallback_clarification_payload(user_query: str, project_path: str, decision: Dict[str, Any]) -> Dict[str, Any]:
    clarification_raw = decision.get("clarification")
    clarification: Dict[str, Any] = dict(clarification_raw) if isinstance(clarification_raw, dict) else {}
    options: List[Dict[str, str]] = []
    raw_options = clarification.get("options") if isinstance(clarification, dict) else []
    if isinstance(raw_options, list):
        for item in raw_options[:4]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            description = str(item.get("description") or "").strip()
            prompt_fragment = str(item.get("promptFragment") or "").strip()
            option_id = str(item.get("id") or "").strip()
            if not label:
                continue
            option_payload = {"label": label, "description": description or label}
            if prompt_fragment:
                option_payload["promptFragment"] = prompt_fragment
            if option_id:
                option_payload["id"] = option_id
            options.append(option_payload)

    if not options:
        raw_missing_slots = decision.get("missing_slots")
        missing_slots: List[Any] = list(raw_missing_slots) if isinstance(raw_missing_slots, list) else []
        for slot in missing_slots[:4]:
            name = str(slot or "").strip()
            if not name:
                continue
            options.append({"label": f"补充{name}", "description": f"请补充{name}相关信息"})

    if not options:
        options = [
            {"label": "补充目标模块", "description": "告诉我你要改哪个文件、模块或函数"},
            {"label": "补充期望结果", "description": "告诉我改完后你期望达到什么效果"},
            {"label": "补充约束条件", "description": "告诉我性能、风格、测试等约束"},
        ]

    question = str(clarification.get("prompt") or "").strip() or "Need more task details before code generation. Please choose a direction below or add the missing details directly."
    round_value = max(1, _safe_int(clarification.get("round"), 1))
    max_rounds = max(round_value, _safe_int(clarification.get("maxRounds"), round_value))
    structured_fields_raw = clarification.get("structuredFields")
    structured_fields = [item for item in structured_fields_raw if isinstance(item, dict)] if isinstance(structured_fields_raw, list) else []
    inferred_intent = str(decision.get("inferred_intent") or clarification.get("inferredIntent") or "").strip()
    allow_freeform = bool(clarification.get("allowFreeform", True))

    return {
        "questionId": uuid4().hex,
        "question": question,
        "header": "需求澄清",
        "options": options,
        "multiple": False,
        "custom": allow_freeform,
        "allowFreeform": allow_freeform,
        "source": "fallback",
        "projectPath": project_path,
        "reason": str(decision.get("reason") or "需要进一步澄清"),
        "round": round_value,
        "maxRounds": max_rounds,
        "clarityLevel": str(clarification.get("clarityLevel") or decision.get("clarity_level") or "ambiguous"),
        "inferredIntent": inferred_intent,
        "structuredFields": structured_fields,
        "terminal": bool(clarification.get("terminal", False)),
        "originalQuery": str(clarification.get("originalQuery") or user_query).strip() or user_query,
        "createdAt": _utcnow_iso(),
    }

def _llm_generate_clarification(
    user_query: str,
    conversation_id: str,
    project_path: str,
    decision: Dict[str, Any],
    llm_config: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    client = _create_deepseek_client(llm_config=llm_config)
    if client is None:
        return None

    history = _history_for_prompt(conversation_id, limit=10)
    system_prompt = (
        "你是需求澄清助手。"
        "请基于用户输入和上下文，生成2-4个候选理解，并指导用户选择或补充。"
        "必须返回JSON对象，且仅返回JSON，不要额外解释。"
    )
    user_prompt = {
        "task": "generate_clarification_candidates",
        "projectPath": project_path,
        "latestUserQuery": user_query,
        "heuristicDecision": {
            "route": decision.get("route"),
            "task_mode": decision.get("task_mode"),
            "reason": decision.get("reason"),
            "missing_slots": decision.get("missing_slots"),
        },
        "history": history,
        "output_schema": {
            "question": "string",
            "header": "string",
            "options": [
                {"label": "string", "description": "string"}
            ],
            "multiple": "boolean",
            "custom": "boolean",
            "reason": "string",
        },
    }
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
    ]

    try:
        response = client.chat(messages=messages, temperature=0.2, max_tokens=700, timeout=35)
        text = _extract_text_from_response(response)
        payload = _parse_json_text(text)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    question = str(payload.get("question") or "").strip()
    options = payload.get("options")
    if not question or not isinstance(options, list) or not options:
        return None

    normalized_options: List[Dict[str, str]] = []
    for item in options[:4]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        description = str(item.get("description") or "").strip()
        prompt_fragment = str(item.get("promptFragment") or "").strip()
        option_id = str(item.get("id") or "").strip()
        if not label:
            continue
        option_payload = {"label": label, "description": description or label}
        if prompt_fragment:
            option_payload["promptFragment"] = prompt_fragment
        if option_id:
            option_payload["id"] = option_id
        normalized_options.append(option_payload)

    if not normalized_options:
        return None

    clarification_raw = decision.get("clarification")
    clarification: Dict[str, Any] = dict(clarification_raw) if isinstance(clarification_raw, dict) else {}
    round_value = max(1, _safe_int(clarification.get("round"), 1))
    max_rounds = max(round_value, _safe_int(clarification.get("maxRounds"), round_value))
    structured_fields_raw = clarification.get("structuredFields")
    structured_fields = [item for item in structured_fields_raw if isinstance(item, dict)] if isinstance(structured_fields_raw, list) else []
    inferred_intent = str(decision.get("inferred_intent") or clarification.get("inferredIntent") or "").strip()
    allow_freeform = bool(payload.get("custom", clarification.get("allowFreeform", True)))

    return {
        "questionId": uuid4().hex,
        "question": question,
        "header": str(payload.get("header") or "需求澄清").strip() or "需求澄清",
        "options": normalized_options,
        "multiple": bool(payload.get("multiple", False)),
        "custom": allow_freeform,
        "allowFreeform": allow_freeform,
        "source": "llm",
        "projectPath": project_path,
        "reason": str(payload.get("reason") or decision.get("reason") or "需要进一步澄清"),
        "round": round_value,
        "maxRounds": max_rounds,
        "clarityLevel": str(clarification.get("clarityLevel") or decision.get("clarity_level") or "ambiguous"),
        "inferredIntent": inferred_intent,
        "structuredFields": structured_fields,
        "terminal": bool(clarification.get("terminal", False)),
        "originalQuery": str(clarification.get("originalQuery") or user_query).strip() or user_query,
        "createdAt": _utcnow_iso(),
    }


def _build_clarification_payload(
    user_query: str,
    conversation_id: str,
    project_path: str,
    decision: Dict[str, Any],
    use_llm: bool = True,
    llm_config: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    llm_payload = _llm_generate_clarification(user_query, conversation_id, project_path, decision, llm_config=llm_config) if use_llm else None
    if isinstance(llm_payload, dict):
        return llm_payload
    return _fallback_clarification_payload(user_query, project_path, decision)


def _generate_chat_answer(user_query: str, conversation_id: str, project_path: str, llm_config: Optional[Dict[str, str]] = None) -> str:
    history = _history_for_prompt(conversation_id, limit=10)
    project_profile = _build_project_identity_profile(project_path)
    client = _create_deepseek_client(llm_config=llm_config)
    if client is None:
        if _is_project_purpose_query(user_query):
            return str(project_profile.get("purpose") or "这是一个代码问答系统。")
        return f"我收到你的问题：{user_query}。当前会话模式已启用，你也可以继续补充上下文，我会基于后续信息持续更新答案。"

    system_prompt = (
        "你是代码项目智能问答助手。"
        "优先结合当前会话历史回答，回答要简洁、可执行。"
        "当信息不足时，明确指出还缺什么。"
    )
    profile_evidence = project_profile.get("evidence") if isinstance(project_profile.get("evidence"), list) else []
    profile_hint = {
        "project_profile": {
            "purpose": str(project_profile.get("purpose") or ""),
            "is_skill_first": bool(project_profile.get("isSkillFirst")),
            "evidence": profile_evidence,
        },
        "policy": {
            "for_project_intro_questions": "优先先说明项目真实用途。若命中 skill-first 特征，明确说明技能库选取是主流程、RAG仅辅助。",
            "avoid": "不要把检索基础设施描述成项目主目标。",
        },
    }
    messages = [{"role": "system", "content": system_prompt}] + history
    messages.append({"role": "system", "content": json.dumps(profile_hint, ensure_ascii=False)})
    messages.append({"role": "user", "content": user_query})

    llm_error = ""
    try:
        response = client.chat(messages=messages, temperature=0.3, max_tokens=700, timeout=35)
        text = _extract_text_from_response(response)
        if text:
            return text
    except Exception as exc:
        llm_error = str(exc)

    if _is_project_purpose_query(user_query):
        return _build_project_intro_answer(project_path, [])

    if bool(project_profile.get("isSkillFirst")):
        return _build_skill_first_fallback_answer(user_query, project_path, llm_error)

    return f"我理解你的问题是：{user_query}。你可以再补充一点背景，我会给出更具体的可执行建议。"


def _llm_decide_next_action(
    user_query: str,
    conversation_id: str,
    project_path: str,
    heuristic_decision: Dict[str, Any],
    llm_config: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    client = _create_deepseek_client(llm_config=llm_config)
    if client is None:
        return None

    history = _history_for_prompt(conversation_id, limit=10)
    system_prompt = (
        "你是会话编排决策器。"
        "你只能返回JSON，不允许返回其他文字。"
        "action 只能是 clarify/general_chat/run_retrieval/start_multi_agent 四选一。"
        "如果用户在问项目定位/用途/能做什么，优先 general_chat，除非用户明确要求代码证据。"
    )
    user_payload = {
        "task": "decide_next_action",
        "projectPath": project_path,
        "latestUserQuery": user_query,
        "history": history,
        "heuristicDecision": heuristic_decision,
        "output_schema": {
            "action": "clarify|general_chat|run_retrieval|start_multi_agent",
            "task_mode": "modify_existing|write_new_code|none",
            "reason": "string",
            "confidence": "0-1 float",
        },
    }
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]
    try:
        response = client.chat(messages=messages, temperature=0.1, max_tokens=320, timeout=25)
        text = _extract_text_from_response(response)
        payload = _parse_json_text(text)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    action = str(payload.get("action") or "").strip()
    if action not in {"clarify", "general_chat", "run_retrieval", "start_multi_agent"}:
        return None
    task_mode = str(payload.get("task_mode") or "modify_existing").strip() or "modify_existing"
    raw_confidence = payload.get("confidence")
    try:
        if raw_confidence is None:
            raise ValueError("missing confidence")
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        fallback_confidence = heuristic_decision.get("confidence")
        try:
            confidence = float(fallback_confidence) if fallback_confidence is not None else 0.6
        except (TypeError, ValueError):
            confidence = 0.6

    return {
        "action": action,
        "task_mode": task_mode,
        "reason": str(payload.get("reason") or heuristic_decision.get("reason") or "模型动作决策"),
        "confidence": max(0.0, min(confidence, 1.0)),
    }


def _normalize_action_decision(
    user_query: str,
    conversation_id: str,
    project_path: str,
    heuristic_decision: Dict[str, Any],
    llm_config: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    intro_action = _prefer_project_intro_action(user_query, project_path)
    if isinstance(intro_action, dict):
        return intro_action

    llm_decision = _llm_decide_next_action(user_query, conversation_id, project_path, heuristic_decision, llm_config=llm_config)
    if isinstance(llm_decision, dict):
        heuristic_task_mode = str(heuristic_decision.get("task_mode") or "").strip()
        llm_task_mode = str(llm_decision.get("task_mode") or "").strip()
        if heuristic_task_mode == "write_new_code" and llm_task_mode == "modify_existing":
            llm_decision = {
                **llm_decision,
                "task_mode": "write_new_code",
            }
        return llm_decision

    route = str(heuristic_decision.get("route") or "modify_existing")
    if route == "clarify":
        action = "clarify"
    elif route == "general_chat":
        action = "general_chat"
    else:
        action = "run_retrieval"
    heuristic_confidence = heuristic_decision.get("confidence")
    try:
        confidence = float(heuristic_confidence) if heuristic_confidence is not None else 0.6
    except (TypeError, ValueError):
        confidence = 0.6

    return {
        "action": action,
        "task_mode": str(heuristic_decision.get("task_mode") or "modify_existing"),
        "reason": str(heuristic_decision.get("reason") or "规则动作决策"),
        "confidence": confidence,
    }


def _build_retrieval_highlights(search_payload: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    results = search_payload.get("hybrid_results")
    if not isinstance(results, list):
        return []
    highlights: List[Dict[str, Any]] = []
    for item in results[:limit]:
        if not isinstance(item, dict):
            continue
        highlights.append(
            {
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or ""),
                "file": str(item.get("file") or ""),
                "score": item.get("score"),
                "sources": item.get("sources") if isinstance(item.get("sources"), list) else [],
            }
        )
    return highlights


def _build_codebase_highlights(code_hits: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    highlights: List[Dict[str, Any]] = []
    for item in code_hits[:limit]:
        if not isinstance(item, dict):
            continue
        highlights.append(
            {
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or item.get("file") or ""),
                "file": str(item.get("file") or item.get("file_path") or ""),
                "score": item.get("score"),
                "sources": item.get("sources") if isinstance(item.get("sources"), list) else ["codebase_scan"],
                "snippet": str(item.get("snippet") or ""),
                "lineStart": item.get("line_start"),
                "lineEnd": item.get("line_end"),
            }
        )
    return highlights


def _merge_highlights(code_highlights: List[Dict[str, Any]], graph_highlights: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen: set = set()
    for group in (code_highlights, graph_highlights):
        for item in group:
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("file") or "").strip().lower(),
                str(item.get("label") or item.get("id") or "").strip().lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


def _safe_read_highlight_snippet(
    project_path: str,
    file_path: str,
    line_start: Optional[int],
    line_end: Optional[int],
    *,
    max_lines: int = 18,
) -> str:
    if not project_path or not file_path:
        return ""
    normalized_project = _normalize_project_path(project_path)
    if not normalized_project:
        return ""

    if os.path.isabs(file_path):
        target_path = os.path.normpath(file_path)
    else:
        target_path = os.path.normpath(os.path.join(normalized_project, file_path))

    try:
        if not target_path.startswith(normalized_project):
            return ""
        with open(target_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except Exception:
        return ""

    if not lines:
        return ""

    start = int(line_start) if isinstance(line_start, int) and line_start > 0 else 1
    end = int(line_end) if isinstance(line_end, int) and line_end >= start else min(start + max_lines - 1, len(lines))
    if end - start + 1 > max_lines:
        end = start + max_lines - 1
    return "".join(lines[start - 1 : end]).strip()


def _hydrate_highlights_with_snippets(project_path: str, highlights: List[Dict[str, Any]], limit: int = 4) -> List[Dict[str, Any]]:
    hydrated: List[Dict[str, Any]] = []
    for index, item in enumerate(highlights):
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        snippet = str(normalized.get("snippet") or "").strip()
        if index < limit and len(snippet) < 24:
            file_path = str(normalized.get("file") or normalized.get("file_path") or "").strip()
            line_start_raw = normalized.get("lineStart") if normalized.get("lineStart") is not None else normalized.get("line_start")
            line_end_raw = normalized.get("lineEnd") if normalized.get("lineEnd") is not None else normalized.get("line_end")
            line_start = int(line_start_raw) if isinstance(line_start_raw, int) else None
            line_end = int(line_end_raw) if isinstance(line_end_raw, int) else None
            enriched = _safe_read_highlight_snippet(project_path, file_path, line_start, line_end)
            if enriched:
                normalized["snippet"] = enriched
        hydrated.append(normalized)
    return hydrated


def _dedupe_commands(commands: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for command in commands:
        value = str(command or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _suggest_validation_commands(project_path: str, highlights: List[Dict[str, Any]]) -> List[str]:
    normalized_project = _normalize_project_path(project_path)
    files = [str(item.get("file") or "").strip() for item in highlights if isinstance(item, dict)]
    extensions = {os.path.splitext(path)[1].lower() for path in files if path}

    commands: List[str] = []
    package_json_path = os.path.join(normalized_project, "package.json")
    if os.path.isfile(package_json_path):
        try:
            with open(package_json_path, "r", encoding="utf-8") as handle:
                package_json = json.load(handle)
        except Exception:
            package_json = {}
        scripts = package_json.get("scripts") if isinstance(package_json, dict) else {}
        if isinstance(scripts, dict):
            if "build" in scripts:
                commands.append("npm run build")
            if "test" in scripts:
                commands.append("npm run test")
            if "lint" in scripts:
                commands.append("npm run lint")

    has_python = ".py" in extensions
    has_frontend = any(ext in {".js", ".ts", ".tsx", ".jsx"} for ext in extensions)

    if has_python:
        if any(
            os.path.isfile(os.path.join(normalized_project, marker))
            for marker in ("pytest.ini", "pyproject.toml", "setup.cfg")
        ):
            commands.append("pytest -q")
        py_targets = [path for path in files if path.endswith(".py")][:2]
        for path in py_targets:
            commands.append(f'python -m py_compile "{path}"')

    if has_frontend and not any(command.startswith("npm run build") for command in commands):
        commands.append("npm run build")

    if not commands and files:
        commands.append(f'python -m py_compile "{files[0]}"')

    return _dedupe_commands(commands)[:4]


def _format_retrieval_evidence_lines(highlights: List[Dict[str, Any]], limit: int = 4) -> List[str]:
    lines: List[str] = []
    for item in highlights[:limit]:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("file") or "").strip() or "(unknown file)"
        line_start = item.get("lineStart") if item.get("lineStart") is not None else item.get("line_start")
        label = str(item.get("label") or item.get("id") or "match").strip()
        score = item.get("score")
        location = f"{file_path}:{line_start}" if line_start else file_path
        score_text = f"，score={score}" if score is not None else ""
        snippet = str(item.get("snippet") or "").strip().replace("\n", " ")
        snippet_text = f"；snippet: {snippet[:120]}" if snippet else ""
        lines.append(f"- `{location}` — {label}{score_text}{snippet_text}")
    return lines


def _build_project_intro_answer(project_path: str, highlights: List[Dict[str, Any]]) -> str:
    profile = _build_project_identity_profile(project_path)
    profile_evidence_raw = profile.get("evidence")
    profile_evidence: List[Dict[str, Any]] = profile_evidence_raw if isinstance(profile_evidence_raw, list) else []

    project_evidence_lines: List[str] = []
    for item in profile_evidence:
        if len(project_evidence_lines) >= 4:
            break
        if not isinstance(item, dict):
            continue
        relative_path = str(item.get("path") or "").strip()
        label = str(item.get("label") or "").strip()
        if not relative_path:
            continue
        if label:
            project_evidence_lines.append(f"- `{relative_path}`：{label}")
        else:
            project_evidence_lines.append(f"- `{relative_path}`")

    if not project_evidence_lines:
        for hit in highlights:
            if len(project_evidence_lines) >= 3:
                break
            if not isinstance(hit, dict):
                continue
            file_path = str(hit.get("file") or "").strip()
            label = str(hit.get("label") or hit.get("id") or "").strip()
            if not file_path:
                continue
            project_evidence_lines.append(f"- `{file_path}`：{label or '相关命中'}")

    usage_text = "你可以用它做 skill 候选筛选、路由决策和后续执行链衔接。"
    if not bool(profile.get("isSkillFirst")):
        usage_text = "你可以用它做代码仓库分析、证据检索和任务编排问答。"

    evidence_block = "\n".join(project_evidence_lines) if project_evidence_lines else "- 暂未提取到稳定证据，请补充项目路径或关键文件。"
    return "\n".join(
        [
            "### 项目定位",
            f"- {str(profile.get('purpose') or '这是一个代码问答系统。')}",
            f"- {usage_text}",
            "",
            "### 依据",
            evidence_block,
        ]
    )


def _build_retrieval_fallback_answer(
    user_query: str,
    highlights: List[Dict[str, Any]],
    validation_commands: List[str],
) -> str:
    evidence_lines = _format_retrieval_evidence_lines(highlights, limit=4)
    first_target = highlights[0] if highlights else {}
    first_label = str(first_target.get("label") or first_target.get("file") or "候选目标").strip()
    command_lines = [f"- `{cmd}`" for cmd in validation_commands] if validation_commands else ["- 暂无可推断命令，请按项目标准流程执行回归。"]
    return "\n".join(
        [
            "### 定位结论",
            f"- 基于代码库检索，当前最相关目标是 `{first_label}`。",
            f"- 用户问题：{user_query}",
            "",
            "### 关键证据",
            *(evidence_lines or ["- 当前仅有弱匹配证据，建议补充模块名或文件路径。"]),
            "",
            "### 建议改动步骤",
            "- 先在首个证据文件定位对应函数/类，确认真实调用链入口。",
            "- 依据证据片段做最小改动，并保持接口/行为兼容。",
            "- 改动后重新检索同关键词，确认调用链与锚点仍可命中。",
            "",
            "### 建议验证命令",
            *command_lines,
        ]
    )


def _generate_retrieval_answer(
    user_query: str,
    conversation_id: str,
    project_path: str,
    highlights: List[Dict[str, Any]],
    validation_commands: List[str],
    llm_config: Optional[Dict[str, str]] = None,
) -> str:
    if not highlights:
        return "当前检索没有命中明显相关证据，你可以补充模块名、文件路径或更明确目标。"
    client = _create_deepseek_client(llm_config=llm_config)
    if client is None:
        return _build_retrieval_fallback_answer(user_query, highlights, validation_commands)

    history = _history_for_prompt(conversation_id, limit=6)
    system_prompt = (
        "你是代码问答助手，采用 opencode 风格输出。"
        "必须只基于提供的检索证据，不得虚构仓库事实。"
        "输出必须使用以下4个Markdown二级标题，且按顺序输出："
        "`### 定位结论`、`### 关键证据`、`### 建议改动步骤`、`### 建议验证命令`。"
        "关键证据必须引用具体文件与行号（若有）。"
        "改动步骤必须是可执行动作，避免空话。"
    )
    user_payload = {
        "query": user_query,
        "retrieval_highlights": highlights,
        "validation_commands": validation_commands,
        "format_constraints": {
            "sections": ["定位结论", "关键证据", "建议改动步骤", "建议验证命令"],
            "bullet_style": "- ...",
            "max_evidence_items": 4,
            "max_steps": 4,
        },
    }
    messages = [{"role": "system", "content": system_prompt}] + history
    messages.append({"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)})
    try:
        response = client.chat(messages=messages, temperature=0.2, max_tokens=700, timeout=35)
        text = _extract_text_from_response(response)
        if text:
            return text
    except Exception:
        pass
    return _build_retrieval_fallback_answer(user_query, highlights, validation_commands)


def _execute_with_timeout(timeout_seconds: float, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn, *args, **kwargs)
        return future.result(timeout=timeout_seconds)


def _run_retrieval_tool(
    project_path: str,
    user_query: str,
    progress_hook: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    if callable(progress_hook):
        progress_hook("codebase_scan", {"message": "开始代码库检索"})
    try:
        code_result = _execute_with_timeout(
            28.0,
            run_codebase_retrieval,
            project_path=project_path,
            query=user_query,
            top_k=8,
        )
    except FuturesTimeoutError:
        code_result = {
            "ok": False,
            "error": "codebase_retrieval_timeout",
            "hits": [],
            "stats": {"timeout": True},
        }
    if callable(progress_hook):
        code_hits_count = len(code_result.get("hits") or []) if isinstance(code_result, dict) else 0
        progress_hook("codebase_scan", {"message": f"代码库检索完成（{code_hits_count} 命中）"})

    code_hits_raw = code_result.get("hits")
    code_hits: List[Dict[str, Any]] = [item for item in code_hits_raw if isinstance(item, dict)] if isinstance(code_hits_raw, list) else []
    code_highlights = _build_codebase_highlights(code_hits, limit=6)

    graph_data: Optional[Dict[str, Any]] = None
    graph_search_payload: Optional[Dict[str, Any]] = None
    graph_error: Optional[str] = None
    try:
        from app.services import analysis_service as analysis_svc

        graph_data = analysis_svc._resolve_graph_data_for_project(project_path, allow_global_fallback=False)
    except Exception:
        graph_data = None

    if not isinstance(graph_data, dict):
        graph_data = data_accessor.get_main_analysis(project_path)

    graph_highlights: List[Dict[str, Any]] = []
    if callable(progress_hook):
        progress_hook("graph_aug", {"message": "开始图谱增强检索"})
    if isinstance(graph_data, dict):
        try:
            graph_search_payload_raw = _execute_with_timeout(
                14.0,
                run_hybrid_shadow,
                graph_data=graph_data,
                query=user_query,
                top_k=8,
                enable_graph_context=True,
            )
            if isinstance(graph_search_payload_raw, dict):
                graph_search_payload = graph_search_payload_raw
                graph_highlights = _build_retrieval_highlights(graph_search_payload_raw, limit=6)
            else:
                graph_search_payload = None
        except FuturesTimeoutError:
            graph_error = "graph_retrieval_timeout"
        except Exception as exc:
            graph_error = str(exc)
    if callable(progress_hook):
        progress_hook("graph_aug", {"message": f"图谱增强完成（{len(graph_highlights)} 命中）"})

    highlights = _merge_highlights(code_highlights, graph_highlights, limit=8)
    errors: List[str] = []
    if code_result.get("error") and not code_result.get("ok"):
        errors.append(str(code_result.get("error")))
    if graph_error:
        errors.append(f"graph_retrieval_failed: {graph_error}")
    if not isinstance(graph_data, dict):
        errors.append("graph_cache_unavailable")

    final_error = None if highlights else ("；".join(errors) if errors else "未命中明显相关代码证据")

    if callable(progress_hook):
        progress_hook(
            "merge",
            {
                "message": f"证据合并完成（{len(highlights)} 命中）",
                "highlightsCount": len(highlights),
            },
        )

    return {
        "ok": bool(highlights),
        "error": final_error,
        "search": {
            "mode": "codebase_first_with_graph_augmentation",
            "code": code_result,
            "graph": graph_search_payload,
        },
        "highlights": highlights,
    }


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_dict_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _build_retrieval_search_summary(retrieval_result: Dict[str, Any]) -> Dict[str, Any]:
    search_payload = _as_dict(retrieval_result.get("search"))
    code_payload = _as_dict(search_payload.get("code"))
    code_stats = _as_dict(code_payload.get("stats"))
    graph_payload = _as_dict(search_payload.get("graph"))
    query_plans = _as_dict_list(code_stats.get("query_plans"))
    strategy = _as_string_list(code_stats.get("strategy"))

    return {
        "mode": str(search_payload.get("mode") or "codebase_first_with_graph_augmentation"),
        "stats": {
            "scannedFiles": code_stats.get("scanned_files"),
            "matchedFiles": code_stats.get("matched_files"),
            "symbolHits": code_stats.get("symbol_hits"),
            "astHits": code_stats.get("ast_hits"),
            "importHits": code_stats.get("import_hits"),
            "followupSymbolHits": code_stats.get("followup_symbol_hits"),
            "followupImportHits": code_stats.get("followup_import_hits"),
            "topK": code_stats.get("top_k"),
            "queryPlanCount": len(query_plans),
            "graphAvailable": bool(graph_payload),
        },
        "strategy": strategy,
        "queryPlans": [
            {
                "query": str(item.get("query") or ""),
                "kind": str(item.get("kind") or "primary"),
                "weight": item.get("weight"),
            }
            for item in query_plans
        ][:6],
    }


def _build_retrieval_decision_trace(
    *,
    action: str,
    decision_reason: str,
    confidence: str,
    cache_hit: bool,
    retrieval_search_summary: Dict[str, Any],
    highlights_count: int,
) -> List[Dict[str, Any]]:
    strategy = _as_string_list(retrieval_search_summary.get("strategy"))
    stats = _as_dict(retrieval_search_summary.get("stats"))
    query_plans = _as_dict_list(retrieval_search_summary.get("queryPlans"))

    return [
        {
            "step": "action_decision",
            "decision": action,
            "reason": decision_reason,
            "confidence": confidence,
        },
        {
            "step": "cache_lookup",
            "decision": "hit" if cache_hit else "miss",
            "reason": "同会话同查询优先复用" if cache_hit else "未命中缓存，执行新检索",
        },
        {
            "step": "query_decomposition",
            "decision": f"plans={len(query_plans)}",
            "reason": "主查询 + 分段 + bridge 子查询聚合",
            "evidence": query_plans[:4],
        },
        {
            "step": "strategy_selection",
            "decision": " -> ".join([str(item) for item in strategy if isinstance(item, str)]),
            "reason": "代码优先，符号/AST/导入与二次补全联合打分",
        },
        {
            "step": "graph_augmentation",
            "decision": "enabled" if bool(stats.get("graphAvailable")) else "disabled",
            "reason": "图谱可用时增强调用链上下文；不可用则保持代码优先",
        },
        {
            "step": "result_assembly",
            "decision": f"highlights={highlights_count}",
            "reason": "输出证据命中并附带建议验证命令",
        },
    ]


def _sync_multi_agent_result_to_conversation(conversation_id: str, multi_agent_session_id: str) -> None:
    max_rounds = 600
    for _ in range(max_rounds):
        payload = data_accessor.get_multi_agent_session(multi_agent_session_id)
        if isinstance(payload, dict):
            status = str(payload.get("status") or "").strip()
            if status == "completed":
                result_raw = payload.get("result")
                result: Dict[str, Any] = dict(result_raw) if isinstance(result_raw, dict) else {}
                output_write_raw = result.get("output_write")
                if not isinstance(output_write_raw, dict):
                    solution_packet_raw = result.get("solution_packet")
                    solution_packet: Dict[str, Any] = solution_packet_raw if isinstance(solution_packet_raw, dict) else {}
                    solution_output_write = solution_packet.get("output_write")
                    output_write_raw = solution_output_write if isinstance(solution_output_write, dict) else {}
                output_write: Dict[str, Any] = output_write_raw if isinstance(output_write_raw, dict) else {}
                written_count = _safe_int(output_write.get("writtenCount"), 0)
                failed_count = _safe_int(output_write.get("failedCount"), 0)
                output_root = str(output_write.get("outputRoot") or "").strip()
                summary = str(
                    result.get("message")
                    or result.get("analysis")
                    or result.get("summary")
                    or "multi-agent 执行已完成，结果已回写。"
                ).strip()
                if written_count or failed_count:
                    summary += f"\n\n输出写入结果：成功 {written_count}，失败 {failed_count}"
                    if output_root:
                        summary += f"\n输出目录：{output_root}"
                data_accessor.append_conversation_message(
                    conversation_id,
                    {
                        "role": "assistant",
                        "content": summary,
                        "createdAt": _utcnow_iso(),
                    },
                )
                data_accessor.append_conversation_part(
                    conversation_id,
                    {
                        "type": "task_result",
                        "content": summary,
                        "metadata": {
                            "multiAgentSessionId": multi_agent_session_id,
                            "resultReady": True,
                            "resultEndpoint": f"/api/multi_agent/session/{multi_agent_session_id}/result",
                            "outputWrite": output_write,
                        },
                    },
                )
                return
            if status == "failed":
                error = str(payload.get("error") or "multi-agent 执行失败")
                data_accessor.append_conversation_message(
                    conversation_id,
                    {
                        "role": "assistant",
                        "content": error,
                        "createdAt": _utcnow_iso(),
                    },
                )
                data_accessor.append_conversation_part(
                    conversation_id,
                    {
                        "type": "task_error",
                        "content": error,
                        "metadata": {
                            "multiAgentSessionId": multi_agent_session_id,
                        },
                    },
                )
                return
        time.sleep(1)


def _confidence_level(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "medium"
    if numeric >= 0.8:
        return "high"
    if numeric >= 0.55:
        return "medium"
    return "low"


def _create_conversation_session(
    project_path: str,
    user_query: str,
    conversation_id: str,
    clarification_context: Optional[Dict[str, Any]] = None,
    output_root: Optional[str] = None,
    auto_apply_output: bool = False,
) -> Dict[str, Any]:
    session_id = uuid4().hex
    payload = {
        "sessionId": session_id,
        "conversationId": conversation_id,
        "projectPath": project_path,
        "query": user_query,
        "status": "starting",
        "stage": "intake",
        "message": "会话回合已创建",
        "clarificationContext": clarification_context or {},
        "outputRoot": output_root,
        "autoApplyOutput": bool(auto_apply_output),
        "result": None,
        "error": None,
        "startedAt": _utcnow_iso(),
        "updatedAt": _utcnow_iso(),
        "completedAt": None,
    }
    data_accessor.save_conversation_session(session_id, payload)
    _emit_conversation_event(
        conversation_id,
        "turn.session_created",
        {
            "sessionId": session_id,
            "stage": payload.get("stage"),
            "status": payload.get("status"),
            "query": user_query,
        },
    )
    return payload


def _update_conversation_session(session_id: str, **changes: Any) -> Optional[Dict[str, Any]]:
    payload = data_accessor.get_conversation_session(session_id)
    if not isinstance(payload, dict):
        return None
    old_stage = str(payload.get("stage") or "")
    old_status = str(payload.get("status") or "")
    payload.update(changes)
    payload["updatedAt"] = _utcnow_iso()
    data_accessor.save_conversation_session(session_id, payload)

    conversation_id = str(payload.get("conversationId") or "").strip()
    if conversation_id:
        new_stage = str(payload.get("stage") or "")
        new_status = str(payload.get("status") or "")
        if new_stage != old_stage or new_status != old_status:
            _emit_conversation_event(
                conversation_id,
                "turn.state_changed",
                {
                    "sessionId": session_id,
                    "stage": new_stage,
                    "status": new_status,
                    "message": payload.get("message"),
                },
            )
    return payload


def _finalize_conversation_session(session_id: str, result: Dict[str, Any]) -> None:
    payload = _update_conversation_session(
        session_id,
        status="completed",
        stage="done",
        message="会话回合完成",
        result=result,
        completedAt=_utcnow_iso(),
    )
    conversation_id = str(payload.get("conversationId") or "").strip() if isinstance(payload, dict) else ""
    if conversation_id:
        _emit_conversation_event(
            conversation_id,
            "turn.completed",
            {
                "sessionId": session_id,
                "nextStep": result.get("nextStep"),
                "hasAnswer": bool(str(result.get("answer") or "").strip()),
            },
        )


def _post_turn_housekeeping(
    conversation_id: str,
    *,
    user_query: str,
    project_path: str,
    action: str,
    task_mode: Optional[str],
    reason: str,
    clarification_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    key_facts = _update_key_facts_memory(
        conversation_id,
        user_query=user_query,
        project_path=project_path,
        action=action,
        task_mode=task_mode,
        reason=reason,
        clarification_context=clarification_context,
    )
    _emit_conversation_event(
        conversation_id,
        "memory.updated",
        {
            "action": action,
            "taskMode": task_mode,
        },
    )

    snapshot = _maybe_compact_conversation(conversation_id, project_path)
    return {
        "keyFacts": key_facts,
        "compaction": snapshot,
    }


def _should_try_inline_codegen(task_mode: str) -> bool:
    return task_mode == "write_new_code"


def _build_inline_codegen_answer(result: Dict[str, Any]) -> str:
    solution_packet = _as_dict(result.get("solution_packet"))
    output_protocol = _as_dict(result.get("output_protocol")) or _as_dict(solution_packet.get("output_protocol"))
    analysis = _as_dict(output_protocol.get("analysis")) or _as_dict(solution_packet.get("analysis"))
    selected_path = _as_dict(analysis.get("selected_path"))
    function_chain = _as_string_list(selected_path.get("function_chain"))

    lines: List[str] = []
    summary = str(
        analysis.get("summary")
        or result.get("message")
        or result.get("summary")
        or ""
    ).strip()
    if summary:
        lines.append(summary)

    if function_chain:
        lines.append(f"主路径: {' -> '.join(function_chain)}")

    selection_mode = str(analysis.get("selection_mode") or "").strip()
    if selection_mode:
        lines.append(f"命中模式: {selection_mode}")

    selection_reason = str(analysis.get("selection_reason") or "").strip()
    if selection_reason:
        lines.append(f"命中原因: {selection_reason}")

    for item in _as_string_list(analysis.get("key_reasoning")):
        if item not in lines:
            lines.append(item)

    output_write = _as_dict(result.get("output_write")) or _as_dict(solution_packet.get("output_write"))
    written_count = _safe_int(output_write.get("writtenCount"), 0)
    failed_count = _safe_int(output_write.get("failedCount"), 0)
    output_root = str(output_write.get("outputRoot") or "").strip()
    if written_count or failed_count:
        lines.append(f"输出写入结果：成功 {written_count}，失败 {failed_count}")
    if output_root:
        lines.append(f"输出目录：{output_root}")

    return "\n".join(lines) or "已完成内联代码生成，可直接查看方案与代码片段。"


def _try_inline_codegen_result(
    *,
    conversation_id: str,
    project_path: str,
    user_query: str,
    task_mode: str,
    partition_id: Optional[str],
    selected_node: Optional[Dict[str, Any]],
    clarification_context: Optional[Dict[str, Any]],
    output_root: Optional[str],
    auto_apply_output: bool,
    opencode_enabled: Optional[bool],
) -> Dict[str, Any]:
    from app.services import multi_agent_service as mas

    session_payload = mas._create_multi_agent_session(
        project_path,
        user_query,
        task_mode,
        clarification_context or {},
        swarm_enabled=True,
        conversation_id=conversation_id,
        output_root=output_root,
        auto_apply_output=bool(auto_apply_output),
        opencode_enabled=opencode_enabled,
    )
    session_id = str(session_payload.get("sessionId") or "").strip()
    if not session_id:
        raise RuntimeError("内联代码生成未创建有效的 multi-agent 会话")

    mas._run_multi_agent_session(
        session_id,
        project_path,
        user_query,
        task_mode,
        partition_id,
        selected_node or {},
        clarification_context or {},
        True,
        output_root,
        bool(auto_apply_output),
    )

    final_payload = data_accessor.get_multi_agent_session(session_id)
    if not isinstance(final_payload, dict):
        raise RuntimeError("内联代码生成未返回会话结果")
    if str(final_payload.get("status") or "").strip() != "completed":
        raise RuntimeError(str(final_payload.get("error") or "内联代码生成失败"))

    result_raw = final_payload.get("result")
    result = dict(result_raw) if isinstance(result_raw, dict) else {}
    return {
        "session": session_payload,
        "result": result,
    }


def _run_conversation_turn(
    session_id: str,
    project_path: str,
    user_query: str,
    conversation_id: str,
    selected_node: Optional[Dict[str, Any]] = None,
    partition_id: Optional[str] = None,
    clarification_context: Optional[Dict[str, Any]] = None,
    reply_payload: Optional[Dict[str, Any]] = None,
    auto_start_multi_agent: bool = False,
    force_action: Optional[str] = None,
    force_fallback_clarification: bool = False,
    output_root: Optional[str] = None,
    auto_apply_output: bool = False,
    opencode_enabled: Optional[bool] = None,
    llm_config: Optional[Dict[str, str]] = None,
) -> None:
    try:
        _update_conversation_session(session_id, status="running", stage="intake", message="正在写入会话消息")
        data_accessor.ensure_conversation(conversation_id, project_path)
        _emit_conversation_event(
            conversation_id,
            "turn.started",
            {
                "sessionId": session_id,
                "query": user_query,
                "projectPath": project_path,
            },
        )

        data_accessor.append_conversation_message(
            conversation_id,
            {
                "role": "user",
                "content": user_query,
                "createdAt": _utcnow_iso(),
            },
        )
        data_accessor.append_conversation_part(
            conversation_id,
            {
                "type": "user_text",
                "content": user_query,
                "metadata": {
                    "sessionId": session_id,
                    "projectPath": project_path,
                },
            },
        )

        if isinstance(reply_payload, dict) and reply_payload:
            normalized_reply = data_accessor.save_conversation_reply(conversation_id, reply_payload)
            data_accessor.append_conversation_part(
                conversation_id,
                {
                    "type": "question_reply",
                    "content": json.dumps(normalized_reply, ensure_ascii=False),
                    "metadata": normalized_reply,
                },
            )

        _update_conversation_session(session_id, stage="decide", message="正在评估本轮动作")
        heuristic_decision = QuestionDetector.assess_clarification_need(
            user_query,
            has_context=bool(partition_id or selected_node),
            clarification_context=clarification_context or {},
        )
        action_decision = _normalize_action_decision(
            user_query=user_query,
            conversation_id=conversation_id,
            project_path=project_path,
            heuristic_decision=heuristic_decision,
            llm_config=llm_config,
        )
        forced = str(force_action or "").strip()
        if forced in {"clarify", "general_chat", "run_retrieval", "start_multi_agent"}:
            action_decision = {
                "action": forced,
                "task_mode": str(action_decision.get("task_mode") or "modify_existing"),
                "reason": f"forced_action={forced}",
                "confidence": action_decision.get("confidence") or 0.7,
            }
        action = str(action_decision.get("action") or "start_multi_agent")
        task_mode = str(action_decision.get("task_mode") or "modify_existing")
        confidence = _confidence_level(action_decision.get("confidence"))
        decision_reason = str(action_decision.get("reason") or "动作决策完成")
        _emit_conversation_event(
            conversation_id,
            "turn.decided",
            {
                "sessionId": session_id,
                "action": action,
                "taskMode": task_mode,
                "reason": decision_reason,
                "confidence": confidence,
            },
        )

        if action == "clarify":
            clarification_payload = _build_clarification_payload(
                user_query,
                conversation_id,
                project_path,
                heuristic_decision,
                use_llm=not force_fallback_clarification,
                llm_config=llm_config,
            )
            pending = data_accessor.set_conversation_pending_question(conversation_id, clarification_payload)

            assistant_text = str(clarification_payload.get("question") or "请先补充需求细节。")
            data_accessor.append_conversation_message(
                conversation_id,
                {
                    "role": "assistant",
                    "content": assistant_text,
                    "createdAt": _utcnow_iso(),
                },
            )
            data_accessor.append_conversation_part(
                conversation_id,
                {
                    "type": "question_request",
                    "content": assistant_text,
                    "metadata": pending or clarification_payload,
                },
            )
            _emit_conversation_event(
                conversation_id,
                "clarification.requested",
                {
                    "sessionId": session_id,
                    "questionId": (pending or clarification_payload).get("questionId"),
                },
            )

            housekeeping = _post_turn_housekeeping(
                conversation_id,
                user_query=user_query,
                project_path=project_path,
                action=action,
                task_mode=task_mode,
                reason=decision_reason,
                clarification_context=clarification_context,
            )

            result = {
                "conversationId": conversation_id,
                "intentGuess": task_mode,
                "nextStep": "ask_clarification",
                "safeToCodegen": False,
                "confidence": confidence,
                "reason": decision_reason,
                "taskMode": task_mode,
                "projectPath": project_path,
                "pendingQuestion": pending,
                "memory": housekeeping.get("keyFacts"),
                "compaction": housekeeping.get("compaction"),
            }
            _finalize_conversation_session(session_id, result)
            return

        if action == "run_retrieval":
            _update_conversation_session(session_id, stage="retrieval", message="正在执行按需检索")

            def _emit_retrieval_progress(phase: str, payload: Dict[str, Any]) -> None:
                event_payload = {
                    "sessionId": session_id,
                    "phase": phase,
                }
                if isinstance(payload, dict):
                    event_payload.update(payload)
                _emit_conversation_event(
                    conversation_id,
                    "retrieval.progress",
                    event_payload,
                )

            tool_call = {
                "tool": "codebase_first_retrieval",
                "query": user_query,
                "createdAt": _utcnow_iso(),
            }
            data_accessor.append_conversation_part(
                conversation_id,
                {
                    "type": "tool_call",
                    "content": json.dumps(tool_call, ensure_ascii=False),
                    "metadata": tool_call,
                },
            )
            cached_retrieval = _find_cached_retrieval(conversation_id, user_query)
            cache_hit = bool(cached_retrieval)
            if cache_hit:
                cached_payload: Dict[str, Any] = cached_retrieval if isinstance(cached_retrieval, dict) else {}
                cached_summary = _as_dict(cached_payload.get("searchSummary"))
                cached_stats = _as_dict(cached_summary.get("stats"))
                cached_strategy = _as_string_list(cached_summary.get("strategy"))
                cached_query_plans = _as_dict_list(cached_summary.get("queryPlans"))
                retrieval_result = {
                    "ok": True,
                    "error": None,
                    "search": {
                        "mode": "conversation_memory_cache",
                        "code": {
                            "ok": True,
                            "stats": {
                                "scanned_files": cached_stats.get("scannedFiles") if cached_stats.get("scannedFiles") is not None else cached_stats.get("scanned_files"),
                                "matched_files": cached_stats.get("matchedFiles") if cached_stats.get("matchedFiles") is not None else cached_stats.get("matched_files"),
                                "symbol_hits": cached_stats.get("symbolHits") if cached_stats.get("symbolHits") is not None else cached_stats.get("symbol_hits"),
                                "ast_hits": cached_stats.get("astHits") if cached_stats.get("astHits") is not None else cached_stats.get("ast_hits"),
                                "import_hits": cached_stats.get("importHits") if cached_stats.get("importHits") is not None else cached_stats.get("import_hits"),
                                "followup_symbol_hits": cached_stats.get("followupSymbolHits") if cached_stats.get("followupSymbolHits") is not None else cached_stats.get("followup_symbol_hits"),
                                "followup_import_hits": cached_stats.get("followupImportHits") if cached_stats.get("followupImportHits") is not None else cached_stats.get("followup_import_hits"),
                                "top_k": cached_stats.get("topK") if cached_stats.get("topK") is not None else cached_stats.get("top_k"),
                                "query_plans": cached_query_plans,
                                "strategy": cached_strategy,
                            },
                        },
                        "graph": None,
                    },
                    "highlights": cached_payload.get("highlights") if isinstance(cached_payload.get("highlights"), list) else [],
                }
                _emit_conversation_event(
                    conversation_id,
                    "tool.codebase_retrieval.cache_hit",
                    {
                        "sessionId": session_id,
                        "cachedAt": cached_payload.get("updatedAt"),
                    },
                )
                _emit_retrieval_progress("cache", {"message": "命中会话缓存，直接复用检索结果"})
            else:
                retrieval_result = _run_retrieval_tool(project_path, user_query, progress_hook=_emit_retrieval_progress)
            raw_highlights = retrieval_result.get("highlights")
            highlights: List[Dict[str, Any]] = []
            if isinstance(raw_highlights, list):
                for item in raw_highlights:
                    if isinstance(item, dict):
                        highlights.append(item)
            highlights = _hydrate_highlights_with_snippets(project_path, highlights, limit=4)
            data_accessor.append_conversation_part(
                conversation_id,
                {
                    "type": "tool_result",
                    "content": json.dumps(
                        {
                            "ok": retrieval_result.get("ok"),
                            "error": retrieval_result.get("error"),
                            "highlights": highlights,
                        },
                        ensure_ascii=False,
                    ),
                    "metadata": {
                        "tool": "codebase_first_retrieval",
                        "ok": retrieval_result.get("ok"),
                        "error": retrieval_result.get("error"),
                        "highlights": highlights,
                    },
                },
            )
            _emit_conversation_event(
                conversation_id,
                "tool.codebase_retrieval.completed",
                {
                    "sessionId": session_id,
                    "ok": retrieval_result.get("ok"),
                    "highlightsCount": len(highlights),
                },
            )
            _emit_conversation_event(
                conversation_id,
                "tool.run_hybrid_shadow.completed",
                {
                    "sessionId": session_id,
                    "ok": retrieval_result.get("ok"),
                    "highlightsCount": len(highlights),
                },
            )
            if retrieval_result.get("ok"):
                validation_commands = _suggest_validation_commands(project_path, highlights)
                _emit_retrieval_progress("answer", {"message": "正在基于证据生成回答"})
                if _is_project_purpose_query(user_query):
                    answer = _build_project_intro_answer(project_path, highlights)
                else:
                    answer = _generate_retrieval_answer(
                        user_query,
                        conversation_id,
                        project_path,
                        highlights,
                        validation_commands,
                        llm_config=llm_config,
                    )
                _emit_retrieval_progress("answer", {"message": "回答生成完成"})
            else:
                validation_commands = []
                answer = str(retrieval_result.get("error") or "检索执行失败")

            retrieval_search_summary = _build_retrieval_search_summary(retrieval_result)
            decision_trace = _build_retrieval_decision_trace(
                action=action,
                decision_reason=decision_reason,
                confidence=confidence,
                cache_hit=cache_hit,
                retrieval_search_summary=retrieval_search_summary,
                highlights_count=len(highlights),
            )
            retrieval_search_summary["decisionTrace"] = decision_trace
            _emit_conversation_event(
                conversation_id,
                "retrieval.orchestration.trace",
                {
                    "sessionId": session_id,
                    "steps": decision_trace,
                },
            )
            if highlights:
                _remember_retrieval_cache(
                    conversation_id,
                    user_query=user_query,
                    highlights=highlights,
                    search_summary=retrieval_search_summary,
                )

            data_accessor.append_conversation_message(
                conversation_id,
                {
                    "role": "assistant",
                    "content": answer,
                    "createdAt": _utcnow_iso(),
                },
            )
            data_accessor.append_conversation_part(
                conversation_id,
                {
                    "type": "assistant_text",
                    "content": answer,
                    "metadata": {
                        "mode": "retrieval",
                        "validationCommands": validation_commands,
                        "search": retrieval_search_summary,
                    },
                },
            )
            housekeeping = _post_turn_housekeeping(
                conversation_id,
                user_query=user_query,
                project_path=project_path,
                action=action,
                task_mode=task_mode,
                reason=decision_reason,
                clarification_context=clarification_context,
            )
            result = {
                "conversationId": conversation_id,
                "intentGuess": task_mode,
                "nextStep": "retrieval_answer",
                "safeToCodegen": False,
                "confidence": confidence,
                "reason": decision_reason,
                "taskMode": task_mode,
                "projectPath": project_path,
                "answer": answer,
                "retrieval": {
                    "ok": retrieval_result.get("ok"),
                    "error": retrieval_result.get("error"),
                    "highlights": highlights,
                    "validationCommands": validation_commands,
                    "search": retrieval_search_summary,
                },
                "memory": housekeeping.get("keyFacts"),
                "compaction": housekeeping.get("compaction"),
            }
            _finalize_conversation_session(session_id, result)
            return

        if action == "general_chat":
            _update_conversation_session(session_id, stage="chat", message="正在生成会话回答")
            answer = _generate_chat_answer(user_query, conversation_id, project_path, llm_config=llm_config)
            data_accessor.append_conversation_message(
                conversation_id,
                {
                    "role": "assistant",
                    "content": answer,
                    "createdAt": _utcnow_iso(),
                },
            )
            data_accessor.append_conversation_part(
                conversation_id,
                {
                    "type": "assistant_text",
                    "content": answer,
                    "metadata": {"mode": "general_chat"},
                },
            )
            housekeeping = _post_turn_housekeeping(
                conversation_id,
                user_query=user_query,
                project_path=project_path,
                action=action,
                task_mode=None,
                reason=decision_reason,
                clarification_context=clarification_context,
            )
            result = {
                "conversationId": conversation_id,
                "intentGuess": "general_chat",
                "nextStep": "send_chat",
                "safeToCodegen": False,
                "confidence": confidence,
                "reason": decision_reason,
                "taskMode": None,
                "projectPath": project_path,
                "answer": answer,
                "memory": housekeeping.get("keyFacts"),
                "compaction": housekeeping.get("compaction"),
            }
            _finalize_conversation_session(session_id, result)
            return

        _update_conversation_session(session_id, stage="handoff", message="已达到代码流门槛，准备进入执行链")
        handoff = {
            "project_path": project_path,
            "query": user_query,
            "task_mode": task_mode,
            "partition_id": partition_id,
            "selected_node": selected_node or {},
            "clarification_context": clarification_context or {},
            "output_root": output_root,
            "auto_apply_output": bool(auto_apply_output),
            "opencode_enabled": bool(opencode_enabled) if opencode_enabled is not None else None,
            "opencodeEnabled": bool(opencode_enabled) if opencode_enabled is not None else None,
        }
        if auto_start_multi_agent and _should_try_inline_codegen(task_mode):
            try:
                _update_conversation_session(session_id, stage="inline_codegen", message="正在执行内联代码生成")
                inline_payload = _try_inline_codegen_result(
                    conversation_id=conversation_id,
                    project_path=project_path,
                    user_query=user_query,
                    task_mode=task_mode,
                    partition_id=partition_id,
                    selected_node=selected_node,
                    clarification_context=clarification_context,
                    output_root=output_root,
                    auto_apply_output=bool(auto_apply_output),
                    opencode_enabled=opencode_enabled,
                )
                inline_session = _as_dict(inline_payload.get("session"))
                inline_result = _as_dict(inline_payload.get("result"))
                solution_packet = _as_dict(inline_result.get("solution_packet"))
                output_protocol = _as_dict(inline_result.get("output_protocol")) or _as_dict(solution_packet.get("output_protocol"))
                evidence_verdict = _as_dict(inline_result.get("evidence_verdict"))
                opencode_kernel = _as_dict(inline_result.get("opencode_kernel")) or _as_dict(solution_packet.get("opencode_kernel"))
                swarm_packet = _as_dict(inline_result.get("swarm_packet"))
                output_write = _as_dict(inline_result.get("output_write")) or _as_dict(solution_packet.get("output_write"))
                if not output_write:
                    output_write = _as_dict(output_protocol.get("output_write"))

                requires_materialized_output = bool(output_root and auto_apply_output)
                has_materialized_output = bool(
                    str(output_write.get("outputRoot") or "").strip()
                    or int(output_write.get("writtenCount") or 0) > 0
                ) if isinstance(output_write, dict) else False
                if requires_materialized_output and not has_materialized_output:
                    raise RuntimeError("INLINE_MISSING_OUTPUT_WRITE")

                answer = _build_inline_codegen_answer(inline_result)
                generation = {
                    "mode": "conversation_inline_multi_agent",
                    "used_llm": bool(opencode_kernel) or bool(swarm_packet.get("llm_enabled")),
                    "error": None,
                    "fallback": False,
                    "multiAgentSessionId": inline_session.get("sessionId"),
                }

                data_accessor.append_conversation_message(
                    conversation_id,
                    {
                        "role": "assistant",
                        "content": answer,
                        "createdAt": _utcnow_iso(),
                    },
                )
                data_accessor.append_conversation_part(
                    conversation_id,
                    {
                        "type": "assistant_text",
                        "content": answer,
                        "metadata": {
                            "mode": "inline_codegen",
                            "multiAgentSessionId": inline_session.get("sessionId"),
                            "outputWrite": output_write,
                            "hasSolution": bool(solution_packet),
                        },
                    },
                )
                _emit_conversation_event(
                    conversation_id,
                    "task.handoff.inline_completed",
                    {
                        "sessionId": session_id,
                        "multiAgentSessionId": inline_session.get("sessionId"),
                    },
                )

                housekeeping = _post_turn_housekeeping(
                    conversation_id,
                    user_query=user_query,
                    project_path=project_path,
                    action=action,
                    task_mode=task_mode,
                    reason=decision_reason,
                    clarification_context=clarification_context,
                )
                result = {
                    "conversationId": conversation_id,
                    "intentGuess": task_mode,
                    "nextStep": "send_chat",
                    "safeToCodegen": True,
                    "confidence": confidence,
                    "reason": decision_reason,
                    "taskMode": task_mode,
                    "projectPath": project_path,
                    "answer": answer,
                    "solution_packet": solution_packet,
                    "output_protocol": output_protocol,
                    "evidence_verdict": evidence_verdict,
                    "generation": generation,
                    "opencode_kernel": opencode_kernel,
                    "swarm_packet": swarm_packet,
                    "memory": housekeeping.get("keyFacts"),
                    "compaction": housekeeping.get("compaction"),
                }
                _finalize_conversation_session(session_id, result)
                return
            except Exception as exc:
                handoff["inlineAttempted"] = True
                handoff["inlineError"] = str(exc)
                _emit_conversation_event(
                    conversation_id,
                    "task.handoff.inline_failed",
                    {
                        "sessionId": session_id,
                        "error": str(exc),
                    },
                )
                _update_conversation_session(session_id, stage="handoff", message="内联代码生成失败，回退到执行链")
        if auto_start_multi_agent:
            try:
                from app.services import multi_agent_service as mas

                ma_payload = mas._create_multi_agent_session(
                    project_path,
                    user_query,
                    task_mode,
                    clarification_context or {},
                    swarm_enabled=True,
                    conversation_id=conversation_id,
                    output_root=output_root,
                    auto_apply_output=bool(auto_apply_output),
                    opencode_enabled=opencode_enabled,
                )
                ma_thread = threading.Thread(
                    target=mas._run_multi_agent_session,
                    args=(
                        ma_payload["sessionId"],
                        project_path,
                        user_query,
                        task_mode,
                        partition_id,
                        selected_node or {},
                        clarification_context or {},
                        True,
                        output_root,
                        bool(auto_apply_output),
                    ),
                    daemon=True,
                )
                ma_thread.start()
                handoff["autoStarted"] = True
                handoff["multiAgentSessionId"] = ma_payload.get("sessionId")
                handoff["opencodeEnabled"] = ma_payload.get("opencodeEnabled")
                _emit_conversation_event(
                    conversation_id,
                    "task.handoff.auto_started",
                    {
                        "sessionId": session_id,
                        "multiAgentSessionId": ma_payload.get("sessionId"),
                    },
                )
                if handoff.get("multiAgentSessionId"):
                    sync_thread = threading.Thread(
                        target=_sync_multi_agent_result_to_conversation,
                        args=(conversation_id, str(handoff.get("multiAgentSessionId"))),
                        daemon=True,
                    )
                    sync_thread.start()
            except Exception as exc:
                handoff["autoStarted"] = False
                handoff["autoStartError"] = str(exc)

        assistant_text = "需求已达到进入代码流条件。你可以继续调用 multi_agent 会话执行。"
        data_accessor.append_conversation_message(
            conversation_id,
            {
                "role": "assistant",
                "content": assistant_text,
                "createdAt": _utcnow_iso(),
            },
        )
        data_accessor.append_conversation_part(
            conversation_id,
            {
                "type": "task_handoff",
                "content": assistant_text,
                "metadata": handoff,
            },
        )
        housekeeping = _post_turn_housekeeping(
            conversation_id,
            user_query=user_query,
            project_path=project_path,
            action=action,
            task_mode=task_mode,
            reason=decision_reason,
            clarification_context=clarification_context,
        )
        result = {
            "conversationId": conversation_id,
            "intentGuess": task_mode,
            "nextStep": "start_multi_agent",
            "safeToCodegen": True,
            "confidence": confidence,
            "reason": decision_reason,
            "taskMode": task_mode,
            "projectPath": project_path,
            "handoff": handoff,
            "memory": housekeeping.get("keyFacts"),
            "compaction": housekeeping.get("compaction"),
        }
        _finalize_conversation_session(session_id, result)
    except Exception as exc:
        _emit_conversation_event(
            conversation_id,
            "turn.failed",
            {
                "sessionId": session_id,
                "error": str(exc),
            },
        )
        _update_conversation_session(
            session_id,
            status="failed",
            stage="failed",
            message="会话回合失败",
            error=str(exc),
            completedAt=_utcnow_iso(),
        )


def api_conversation_session_start():
    data = request.json or {}
    project_path = _normalize_project_path(data.get("project_path"))
    user_query = str(data.get("query") or "").strip()
    conversation_id = str(data.get("conversation_id") or "").strip() or uuid4().hex
    selected_node = data.get("selected_node") if isinstance(data.get("selected_node"), dict) else {}
    partition_id = str(data.get("partition_id") or "").strip() or None
    clarification_context = data.get("clarification_context") if isinstance(data.get("clarification_context"), dict) else {}
    reply_payload = _normalize_reply_payload(data.get("reply_payload"))
    auto_start_multi_agent = bool(data.get("auto_start_multi_agent", False))
    force_action = str(data.get("force_action") or "").strip() or None
    force_fallback_clarification = bool(data.get("force_fallback_clarification", False))
    raw_output_root = data.get("output_root")
    output_root = _normalize_output_root(raw_output_root)
    auto_apply_output = bool(data.get("auto_apply_output", False))
    opencode_enabled_raw = data.get("opencode_enabled")
    opencode_enabled = bool(opencode_enabled_raw) if opencode_enabled_raw is not None else None
    llm_config = _parse_runtime_llm_config(data.get("llm_config"))

    if not user_query:
        return jsonify({"error": "query 不能为空"}), 400
    if not os.path.isdir(project_path):
        return jsonify({"error": f"project_path 不存在或不是目录: {project_path}"}), 400
    if raw_output_root is not None and str(raw_output_root).strip() and not output_root:
        return jsonify({"error": "output_root 必须是绝对路径"}), 400
    if auto_apply_output and not output_root:
        return jsonify({"error": "开启 auto_apply_output 时必须提供 output_root"}), 400

    data_accessor.ensure_conversation(conversation_id, project_path)
    payload = _create_conversation_session(
        project_path,
        user_query,
        conversation_id,
        clarification_context,
        output_root=output_root,
        auto_apply_output=auto_apply_output,
    )
    _emit_conversation_event(
        conversation_id,
        "api.turn.requested",
        {
            "sessionId": payload.get("sessionId"),
            "query": user_query,
            "projectPath": project_path,
        },
    )

    thread = threading.Thread(
        target=_run_conversation_turn,
        args=(
            payload["sessionId"],
            project_path,
            user_query,
            conversation_id,
            selected_node,
            partition_id,
            clarification_context,
            reply_payload,
            auto_start_multi_agent,
            force_action,
            force_fallback_clarification,
            output_root,
            auto_apply_output,
            opencode_enabled,
            llm_config,
        ),
        daemon=True,
    )
    thread.start()

    return jsonify(
        {
            "sessionId": payload["sessionId"],
            "conversationId": conversation_id,
            "projectPath": project_path,
            "status": payload["status"],
            "stage": payload["stage"],
            "message": payload["message"],
        }
    )


def api_conversation_session_status(session_id: str):
    payload = data_accessor.get_conversation_session(session_id)
    if not payload:
        return jsonify({"error": "未找到会话回合"}), 404
    return jsonify(
        {
            "sessionId": payload.get("sessionId"),
            "conversationId": payload.get("conversationId"),
            "projectPath": payload.get("projectPath"),
            "status": payload.get("status"),
            "stage": payload.get("stage"),
            "message": payload.get("message"),
            "error": payload.get("error"),
            "startedAt": payload.get("startedAt"),
            "updatedAt": payload.get("updatedAt"),
            "completedAt": payload.get("completedAt"),
        }
    )


def api_conversation_session_result(session_id: str):
    payload = data_accessor.get_conversation_session(session_id)
    if not payload:
        return jsonify({"error": "未找到会话回合"}), 404
    if payload.get("status") == "failed":
        return jsonify({"error": payload.get("error") or "会话回合失败"}), 400
    if payload.get("status") != "completed":
        return jsonify({"error": "结果尚未就绪"}), 409
    return jsonify(payload.get("result") or {})


def api_conversation_get(conversation_id: str):
    payload = data_accessor.get_conversation(conversation_id)
    if not payload:
        return jsonify({"error": "未找到会话"}), 404
    return jsonify(
        {
            "conversationId": payload.get("conversationId"),
            "projectPath": payload.get("projectPath"),
            "status": payload.get("status"),
            "messageCount": len(payload.get("messages") or []),
            "partCount": len(payload.get("parts") or []),
            "pendingQuestion": payload.get("pendingQuestion"),
            "summarySnapshot": payload.get("summarySnapshot"),
            "compactionCount": len(payload.get("compactionHistory") or []),
            "keyFactsMemory": payload.get("keyFactsMemory") or {},
            "createdAt": payload.get("createdAt"),
            "updatedAt": payload.get("updatedAt"),
        }
    )


def _build_summary_snapshot(conversation_id: str) -> Dict[str, Any]:
    messages = data_accessor.list_conversation_messages(conversation_id)
    pending = data_accessor.get_conversation_pending_question(conversation_id)
    recent = messages[-8:]

    highlights: List[str] = []
    for item in recent:
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if not role or not content:
            continue
        snippet = content[:120]
        prefix = "用户" if role == "user" else "助手"
        highlights.append(f"{prefix}: {snippet}")

    summary_text = "\n".join(highlights)
    if not summary_text:
        summary_text = "当前会话暂无可摘要内容。"

    paths: List[str] = []
    for item in recent:
        content = str(item.get("content") or "")
        matches = re.findall(r"[A-Za-z]:\\[^\s,;，；]+|[^\s,;，；]+\.(?:py|ts|tsx|js|java|md)", content)
        for match in matches:
            text = str(match or "").strip()
            if text and text not in paths:
                paths.append(text)

    payload_replies: List[Dict[str, Any]] = []
    conv = data_accessor.get_conversation(conversation_id)
    if isinstance(conv, dict):
        replies_raw = conv.get("questionReplies")
        if isinstance(replies_raw, list):
            payload_replies = [item for item in replies_raw if isinstance(item, dict)]

    memory = data_accessor.get_conversation_key_facts_memory(conversation_id)
    key_facts = {
        "recentUserGoal": next(
            (
                str(item.get("content") or "").strip()
                for item in reversed(recent)
                if str(item.get("role") or "") == "user" and str(item.get("content") or "").strip()
            ),
            "",
        ),
        "pendingQuestion": pending,
        "replyCount": len(payload_replies),
        "pathHints": paths[:8],
        "memory": memory,
    }

    compaction_history = data_accessor.list_conversation_compaction_snapshots(conversation_id)

    return {
        "summary": summary_text,
        "messageCount": len(messages),
        "pendingQuestion": pending,
        "keyFacts": key_facts,
        "compaction": {
            "count": len(compaction_history),
            "latestSnapshotId": compaction_history[-1].get("snapshotId") if compaction_history else None,
        },
        "generatedAt": _utcnow_iso(),
        "strategy": "recent_messages_plus_memory_v2",
    }


def api_conversation_summary(conversation_id: str):
    payload = data_accessor.get_conversation(conversation_id)
    if not payload:
        return jsonify({"error": "未找到会话"}), 404

    force = str(request.args.get("force") or "").strip().lower() in {"1", "true", "yes"}
    summary = payload.get("summarySnapshot") if isinstance(payload.get("summarySnapshot"), dict) else None
    if force or not summary:
        summary = _build_summary_snapshot(conversation_id)
        data_accessor.save_conversation_summary_snapshot(conversation_id, summary)

    return jsonify(
        {
            "conversationId": conversation_id,
            "summarySnapshot": summary,
            "updatedAt": _utcnow_iso(),
        }
    )


def api_conversation_list():
    project_path_filter = _normalize_project_path(request.args.get("project_path") or "")
    ids = data_accessor.list_conversation_ids()
    items: List[Dict[str, Any]] = []
    for cid in ids:
        payload = data_accessor.get_conversation(cid)
        if not isinstance(payload, dict):
            continue
        payload_project_path = _normalize_project_path(payload.get("projectPath") or "")
        if project_path_filter and payload_project_path != project_path_filter:
            continue
        items.append(
            {
                "conversationId": cid,
                "projectPath": payload.get("projectPath"),
                "status": payload.get("status"),
                "messageCount": len(payload.get("messages") or []),
                "hasPendingQuestion": isinstance(payload.get("pendingQuestion"), dict),
                "compactionCount": len(payload.get("compactionHistory") or []),
                "updatedAt": payload.get("updatedAt"),
                "createdAt": payload.get("createdAt"),
            }
        )
    items.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    return jsonify(items)


def api_conversation_compactions(conversation_id: str):
    payload = data_accessor.get_conversation(conversation_id)
    if not payload:
        return jsonify({"error": "未找到会话"}), 404
    history = data_accessor.list_conversation_compaction_snapshots(conversation_id)
    memory = data_accessor.get_conversation_key_facts_memory(conversation_id)
    return jsonify(
        {
            "conversationId": conversation_id,
            "compactionHistory": history,
            "keyFactsMemory": memory,
            "summarySnapshot": payload.get("summarySnapshot") or {},
            "updatedAt": payload.get("updatedAt"),
        }
    )


def api_conversation_events(conversation_id: str):
    payload = data_accessor.get_conversation(conversation_id)
    if not payload:
        return jsonify({"error": "未找到会话"}), 404

    since_seq = _safe_int(request.args.get("since"), 0)
    timeout_seconds = max(10, min(_safe_int(request.args.get("timeout"), 120), 600))
    interval_ms = max(100, min(_safe_int(request.args.get("intervalMs"), 1000), 5000))
    interval_seconds = float(interval_ms) / 1000.0
    target_session_id = str(request.args.get("session_id") or "").strip()

    def _event_stream():
        cursor = since_seq
        deadline = time.time() + timeout_seconds

        bootstrap = {
            "conversationId": conversation_id,
            "status": payload.get("status"),
            "pendingQuestion": payload.get("pendingQuestion"),
            "updatedAt": payload.get("updatedAt"),
            "cursor": cursor,
        }
        yield f"event: bootstrap\ndata: {json.dumps(bootstrap, ensure_ascii=False)}\n\n"

        while time.time() < deadline:
            events = data_accessor.list_conversation_events(conversation_id, since_seq=cursor, limit=200)
            if events:
                for event in events:
                    seq = _safe_int(event.get("seq"), cursor)
                    event_type = str(event.get("type") or "event").strip() or "event"
                    frame = {
                        "seq": seq,
                        "eventId": event.get("eventId"),
                        "type": event_type,
                        "payload": event.get("payload") if isinstance(event.get("payload"), dict) else {},
                        "createdAt": event.get("createdAt"),
                    }
                    yield f"id: {seq}\n"
                    yield f"event: {event_type}\n"
                    yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"
                    cursor = max(cursor, seq)
            else:
                heartbeat = {
                    "ts": _utcnow_iso(),
                    "cursor": cursor,
                }
                yield f"event: heartbeat\ndata: {json.dumps(heartbeat, ensure_ascii=False)}\n\n"

            if target_session_id:
                target_session = data_accessor.get_conversation_session(target_session_id)
                if isinstance(target_session, dict):
                    target_status = str(target_session.get("status") or "").strip()
                    if target_status in {"completed", "failed"}:
                        end_payload = {
                            "cursor": cursor,
                            "reason": "session_terminal",
                            "status": target_status,
                            "sessionId": target_session_id,
                            "ts": _utcnow_iso(),
                        }
                        yield f"event: stream_end\ndata: {json.dumps(end_payload, ensure_ascii=False)}\n\n"
                        return
            time.sleep(interval_seconds)

        end_payload = {
            "cursor": cursor,
            "reason": "timeout",
            "ts": _utcnow_iso(),
        }
        yield f"event: stream_end\ndata: {json.dumps(end_payload, ensure_ascii=False)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return Response(stream_with_context(_event_stream()), mimetype="text/event-stream", headers=headers)


def api_conversation_export_runbook(conversation_id: str):
    payload = data_accessor.get_conversation(conversation_id)
    if not isinstance(payload, dict):
        return jsonify({"error": "未找到会话"}), 404

    data = request.json or {}
    markdown = str(data.get("markdown") or "").strip()
    if not markdown:
        return jsonify({"error": "markdown 不能为空"}), 400

    runbook_text = str(data.get("runbook_text") or "").strip()
    include_messages = bool(data.get("include_messages", True))
    include_events = bool(data.get("include_events", True))
    metadata_raw = data.get("metadata")
    metadata: Dict[str, Any] = metadata_raw if isinstance(metadata_raw, dict) else {}
    stage = str(metadata.get("stage") or payload.get("status") or "stage").strip() or "stage"

    report_dir = _normalize_report_dir(data.get("report_dir"))
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return jsonify({"error": f"report_dir 无法创建: {exc}"}), 400

    base_name = _build_runbook_export_basename(conversation_id, stage)
    markdown_path = report_dir / f"{base_name}.md"
    execution_record_path = report_dir / f"{base_name}.json"

    generated_at = _utcnow_iso()
    execution_record: Dict[str, Any] = {
        "conversationId": conversation_id,
        "projectPath": payload.get("projectPath"),
        "status": payload.get("status"),
        "generatedAt": generated_at,
        "reportDir": str(report_dir),
        "artifacts": {
            "markdownPath": str(markdown_path),
            "executionRecordPath": str(execution_record_path),
        },
        "summarySnapshot": payload.get("summarySnapshot") if isinstance(payload.get("summarySnapshot"), dict) else {},
        "keyFactsMemory": payload.get("keyFactsMemory") if isinstance(payload.get("keyFactsMemory"), dict) else {},
        "compactionHistory": payload.get("compactionHistory") if isinstance(payload.get("compactionHistory"), list) else [],
        "metadata": metadata,
        "runbookText": runbook_text,
    }

    if include_messages:
        messages_raw = payload.get("messages")
        messages = messages_raw if isinstance(messages_raw, list) else []
        execution_record["messages"] = messages
    else:
        execution_record["messages"] = []

    if include_events:
        events_raw = payload.get("eventLog")
        events = events_raw if isinstance(events_raw, list) else []
        execution_record["events"] = events
    else:
        execution_record["events"] = []

    try:
        with markdown_path.open("w", encoding="utf-8") as fp:
            fp.write(markdown)
        with execution_record_path.open("w", encoding="utf-8") as fp:
            json.dump(execution_record, fp, ensure_ascii=False, indent=2)
    except Exception as exc:
        return jsonify({"error": f"写入导出文件失败: {exc}"}), 500

    _emit_conversation_event(
        conversation_id,
        "report.exported",
        {
            "markdownPath": str(markdown_path),
            "executionRecordPath": str(execution_record_path),
            "generatedAt": generated_at,
            "stage": stage,
        },
    )

    return jsonify(
        {
            "conversationId": conversation_id,
            "reportDir": str(report_dir),
            "markdownPath": str(markdown_path),
            "executionRecordPath": str(execution_record_path),
            "generatedAt": generated_at,
        }
    )


def api_conversation_turn():
    return api_conversation_session_start()


def api_conversation_messages(conversation_id: str):
    payload = data_accessor.get_conversation(conversation_id)
    if not payload:
        return jsonify({"error": "未找到会话"}), 404
    return jsonify(
        {
            "conversationId": payload.get("conversationId"),
            "messages": payload.get("messages") or [],
            "parts": payload.get("parts") or [],
            "pendingQuestion": payload.get("pendingQuestion"),
            "questionReplies": payload.get("questionReplies") or [],
            "compactionHistory": payload.get("compactionHistory") or [],
            "keyFactsMemory": payload.get("keyFactsMemory") or {},
            "updatedAt": payload.get("updatedAt"),
        }
    )


def api_conversation_reply(conversation_id: str):
    payload = data_accessor.get_conversation(conversation_id)
    if not payload:
        return jsonify({"error": "未找到会话"}), 404
    pending = payload.get("pendingQuestion")
    if not isinstance(pending, dict):
        return jsonify({"error": "当前没有待回复的问题"}), 409

    data = request.json or {}
    answer = str(data.get("answer") or data.get("query") or "").strip()
    raw_selected_option_labels = data.get("selectedOptionLabels")
    selected_option_labels: List[str] = []
    if isinstance(raw_selected_option_labels, list):
        selected_option_labels = [str(item).strip() for item in raw_selected_option_labels if str(item).strip()]
    if not answer and not selected_option_labels:
        return jsonify({"error": "answer 或 selectedOptionLabels 至少提供一个"}), 400

    project_path = _normalize_project_path(data.get("project_path") or payload.get("projectPath"))
    if not os.path.isdir(project_path):
        return jsonify({"error": f"project_path 不存在或不是目录: {project_path}"}), 400

    user_query = answer or "，".join(str(item) for item in selected_option_labels)
    reply_payload = {
        "questionId": str(pending.get("questionId") or "").strip(),
        "answer": answer,
        "selectedOptionLabels": selected_option_labels,
        "raw": data,
    }

    raw_clarification_context = data.get("clarification_context")
    clarification_context: Dict[str, Any] = dict(raw_clarification_context) if isinstance(raw_clarification_context, dict) else {}
    clarification_context.setdefault("round", int(data.get("round") or 1))
    clarification_context.setdefault("originalQuery", str(data.get("originalQuery") or payload.get("originalQuery") or user_query))
    clarification_context.setdefault("latestUserReply", user_query)
    clarification_context.setdefault("selectedOptionLabels", reply_payload.get("selectedOptionLabels") or [])
    auto_start_multi_agent = bool(data.get("auto_start_multi_agent", False))
    force_action = str(data.get("force_action") or "").strip() or None
    force_fallback_clarification = bool(data.get("force_fallback_clarification", False))
    raw_output_root = data.get("output_root")
    output_root = _normalize_output_root(raw_output_root)
    auto_apply_output = bool(data.get("auto_apply_output", False))
    opencode_enabled_raw = data.get("opencode_enabled")
    opencode_enabled = bool(opencode_enabled_raw) if opencode_enabled_raw is not None else None
    llm_config = _parse_runtime_llm_config(data.get("llm_config"))
    if raw_output_root is not None and str(raw_output_root).strip() and not output_root:
        return jsonify({"error": "output_root 必须是绝对路径"}), 400
    if auto_apply_output and not output_root:
        return jsonify({"error": "开启 auto_apply_output 时必须提供 output_root"}), 400
    _emit_conversation_event(
        conversation_id,
        "api.reply.requested",
        {
            "questionId": str(pending.get("questionId") or "").strip(),
            "answer": answer,
            "selectedOptionLabels": selected_option_labels,
        },
    )

    turn_payload = _create_conversation_session(
        project_path,
        user_query,
        conversation_id,
        clarification_context,
        output_root=output_root,
        auto_apply_output=auto_apply_output,
    )
    thread = threading.Thread(
        target=_run_conversation_turn,
        args=(
            turn_payload["sessionId"],
            project_path,
            user_query,
            conversation_id,
            {},
            None,
            clarification_context,
            reply_payload,
            auto_start_multi_agent,
            force_action,
            force_fallback_clarification,
            output_root,
            auto_apply_output,
            opencode_enabled,
            llm_config,
        ),
        daemon=True,
    )
    thread.start()

    return jsonify(
        {
            "sessionId": turn_payload["sessionId"],
            "conversationId": conversation_id,
            "projectPath": project_path,
            "status": turn_payload["status"],
            "stage": turn_payload["stage"],
            "message": "回复已接收，正在继续会话回合",
        }
    )
