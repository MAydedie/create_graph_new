from __future__ import annotations

import asyncio
import json
import re
import sys
import threading
import time
import uuid
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

from app.services import persona_skill_service as pss
from app.services import multi_agent_service as mas
from llm.agent.utils.question_detector import QuestionDetector


_THINK_BLOCK_PATTERN = re.compile(
    r"<think>[\s\S]*?</think>\s*",
    re.IGNORECASE,
)


def resolve_code_chat_root() -> Path:
    p = Path(__file__).resolve()
    cand1 = p.parents[2].parent.parent / "借鉴项目" / "code_chat"
    if cand1.is_dir():
        return cand1
    cand2 = p.parents[2].parent / "借鉴项目" / "code_chat"
    if cand2.is_dir():
        return cand2
    return cand1


_CODE_REQUEST_HINTS = (
    "写代码",
    "生成代码",
    "改代码",
    "修改",
    "实现",
    "修复",
    "重构",
    "测试",
    "新增",
    "接口",
    "函数",
    "类",
    "组件",
    "脚本",
    "create",
    "generate",
    "implement",
    "write",
    "modify",
    "fix",
    "refactor",
    "api",
    "function",
    "class",
    "component",
)

_ACTION_REQUEST_HINTS = (
    "请帮我",
    "帮我",
    "请你",
    "麻烦你",
    "请实现",
    "请修改",
    "please",
)

_QA_REQUEST_HINTS = (
    "什么",
    "为何",
    "为什么",
    "怎么",
    "如何",
    "是不是",
    "吗",
    "原理",
    "介绍",
    "区别",
    "what",
    "why",
    "how",
    "explain",
)

_CODE_PATH_HINT_PATTERN = re.compile(r"(\.py\b|\.ts\b|\.tsx\b|\.js\b|/|\\\\|::|```)", re.IGNORECASE)
_CODE_ACTION_VERB_PATTERN = re.compile(
    r"(实现|修改|修复|重构|生成|新增|新建|编写|写|开发|添加|优化|改造|add|create|modify|fix|refactor|implement|generate|write|build|develop)",
    re.IGNORECASE,
)
_INFO_QUERY_PATTERN = re.compile(
    r"(介绍|干嘛|做什么|是什么|作用|用途|原理|区别|解释|说明|概述|理解|介绍一下|请问)",
    re.IGNORECASE,
)


def resolve_se_team_html_path() -> Path:
    return resolve_code_chat_root() / "ai_team_app.html"


def _looks_like_code_request(requirement: str) -> bool:
    text = str(requirement or "").strip()
    if not text:
        return False

    lowered = text.lower()
    keyword_hits = sum(1 for keyword in _CODE_REQUEST_HINTS if keyword in lowered)
    if keyword_hits >= 2:
        return True
    return bool(_CODE_PATH_HINT_PATTERN.search(text))


def _looks_like_explicit_action_request(requirement: str) -> bool:
    text = str(requirement or "").strip()
    if not text:
        return False

    lowered = text.lower()
    has_question_signal = bool(re.search(r"(什么|为何|为什么|怎么|如何|是不是|吗|\?|？|what|why|how|介绍|解释|说明)", lowered))
    if has_question_signal and not _CODE_PATH_HINT_PATTERN.search(text):
        if not _CODE_ACTION_VERB_PATTERN.search(text):
            return False

    if _INFO_QUERY_PATTERN.search(text) and not _CODE_ACTION_VERB_PATTERN.search(text):
        return False

    has_action_marker = any(marker in lowered for marker in _ACTION_REQUEST_HINTS)
    has_code_action = bool(_CODE_ACTION_VERB_PATTERN.search(text))
    if has_action_marker and has_code_action:
        return True

    if re.search(
        r"^(请|请你|帮我|麻烦你|please|can you|could you).{0,10}(实现|修改|修复|重构|生成|新增|新建|编写|写|add|create|modify|fix|refactor|implement|generate)",
        lowered,
    ):
        return True
    return bool(_CODE_PATH_HINT_PATTERN.search(text))


def _semantic_intent_scores(requirement: str) -> dict[str, Any]:
    text = str(requirement or "").strip()
    lowered = text.lower()
    code_score = 0
    qa_score = 0
    signals: list[str] = []

    code_keyword_hits = sum(1 for keyword in _CODE_REQUEST_HINTS if keyword in lowered)
    if code_keyword_hits:
        code_score += min(code_keyword_hits, 4)
        signals.append(f"code_keyword_hits={code_keyword_hits}")

    if _CODE_PATH_HINT_PATTERN.search(text):
        code_score += 3
        signals.append("code_path_hint")

    if _looks_like_explicit_action_request(text):
        code_score += 3
        signals.append("explicit_action_request")

    qa_keyword_hits = sum(1 for keyword in _QA_REQUEST_HINTS if keyword in lowered)
    if qa_keyword_hits:
        qa_score += min(qa_keyword_hits, 4)
        signals.append(f"qa_keyword_hits={qa_keyword_hits}")

    if _INFO_QUERY_PATTERN.search(text):
        qa_score += 3
        signals.append("info_query_pattern")

    if re.search(r"(\?|？)", text):
        qa_score += 2
        signals.append("question_mark")

    from llm.agent.utils.question_detector import QuestionDetector

    analysis = QuestionDetector.analyze(text)
    is_question = bool(analysis.get("is_question"))
    if is_question:
        qa_score += 2
        signals.append("question_detector=true")
    else:
        signals.append("question_detector=false")

    return {
        "code_score": code_score,
        "qa_score": qa_score,
        "is_question": is_question,
        "question_detector": analysis,
        "signals": signals,
    }


def semantic_route_judge(requirement: str, preferred_mode: str = "") -> dict[str, Any]:
    normalized_mode = str(preferred_mode or "").strip().lower()
    if normalized_mode in {"1", "code_generation"}:
        normalized_mode = "code_generation"
    elif normalized_mode in {"2", "simple_qa"}:
        normalized_mode = "simple_qa"

    if normalized_mode in {"simple_qa", "code_generation"}:
        route_code = 2 if normalized_mode == "simple_qa" else 1
        return {
            "route_code": route_code,
            "mode": normalized_mode,
            "intent": normalized_mode,
            "reason": "mode manually provided",
            "confidence": 1.0,
            "code_score": 0,
            "qa_score": 0,
            "signals": ["manual_mode"],
        }

    text = str(requirement or "").strip()
    if not text:
        return {
            "route_code": 1,
            "mode": "code_generation",
            "intent": "code_generation",
            "reason": "empty requirement fallback to code generation",
            "confidence": 0.5,
            "code_score": 0,
            "qa_score": 0,
            "signals": ["empty_requirement"],
        }

    score_payload = _semantic_intent_scores(text)
    code_score = int(score_payload.get("code_score") or 0)
    qa_score = int(score_payload.get("qa_score") or 0)
    score_gap = abs(code_score - qa_score)
    confidence = max(0.55, min(0.95, 0.55 + score_gap * 0.08))

    if _looks_like_explicit_action_request(text):
        return {
            "route_code": 1,
            "mode": "code_generation",
            "intent": "code_generation",
            "reason": "explicit action request routed to code generation",
            "confidence": max(confidence, 0.9),
            "code_score": max(code_score, qa_score + 2),
            "qa_score": qa_score,
            "signals": [*list(score_payload.get("signals") or []), "force_code_generation_explicit_action"],
        }

    if qa_score > code_score or (qa_score == code_score and bool(score_payload.get("is_question"))):
        return {
            "route_code": 2,
            "mode": "simple_qa",
            "intent": "simple_qa",
            "reason": "semantic judge routed to simple QA",
            "confidence": confidence,
            "code_score": code_score,
            "qa_score": qa_score,
            "signals": list(score_payload.get("signals") or []),
        }

    return {
        "route_code": 1,
        "mode": "code_generation",
        "intent": "code_generation",
        "reason": "semantic judge routed to code generation",
        "confidence": confidence,
        "code_score": code_score,
        "qa_score": qa_score,
        "signals": list(score_payload.get("signals") or []),
    }


def decide_request_mode(requirement: str, preferred_mode: str = "", use_llm: bool = True) -> dict[str, Any]:
    normalized_mode = str(preferred_mode or "").strip().lower()
    if normalized_mode in {"1", "code_generation"}:
        return {
            "route_code": 1,
            "mode": "code_generation",
            "intent": "code_generation",
            "reason": "manual",
            "confidence": 1.0,
            "code_score": 0,
            "qa_score": 0,
            "signals": ["manual_mode"],
            "model_used": False,
        }
    if normalized_mode in {"2", "simple_qa"}:
        semantic_decision = semantic_route_judge(requirement=requirement, preferred_mode="")
        if int(semantic_decision.get("route_code") or 1) == 1:
            signals = list(semantic_decision.get("signals") or [])
            signals.append("manual_simple_qa_blocked_for_code_task")
            return {
                "route_code": 1,
                "mode": "code_generation",
                "intent": "code_generation",
                "reason": "manual simple_qa override blocked because request looks like a code task",
                "confidence": max(float(semantic_decision.get("confidence") or 0.0), 0.9),
                "code_score": int(semantic_decision.get("code_score") or 0),
                "qa_score": int(semantic_decision.get("qa_score") or 0),
                "signals": signals,
                "model_used": False,
            }
        return {
            "route_code": 2,
            "mode": "simple_qa",
            "intent": "simple_qa",
            "reason": "manual",
            "confidence": 1.0,
            "code_score": 0,
            "qa_score": 0,
            "signals": ["manual_mode"],
            "model_used": False,
        }

    if use_llm:
        try:
            from app.services.se_team_llm_router import llm_semantic_route

            api_key, model_name, base_url = _extract_ai_team_model_config()
            semantic_fallback = semantic_route_judge(requirement=requirement, preferred_mode=preferred_mode)
            llm_result = llm_semantic_route(
                requirement=requirement,
                api_key=api_key,
                model_name=model_name,
                base_url=base_url,
                timeout_seconds=8,
                fallback_router=semantic_route_judge,
            )
            route_code = int(llm_result.get("route_code") or 1)
            if route_code == 2 and int(semantic_fallback.get("route_code") or 1) == 1:
                override_signals = list(semantic_fallback.get("signals") or [])
                override_signals.append("opencode_safety_override")
                return {
                    "route_code": 1,
                    "mode": "code_generation",
                    "intent": "code_generation",
                    "reason": "potential code task forced onto OpenCode safety path",
                    "confidence": max(float(llm_result.get("confidence") or 0.0), float(semantic_fallback.get("confidence") or 0.9)),
                    "code_score": int(semantic_fallback.get("code_score") or 0),
                    "qa_score": int(semantic_fallback.get("qa_score") or 0),
                    "signals": override_signals,
                    "model_used": bool(llm_result.get("model_used", False)),
                }
            mode = "simple_qa" if route_code == 2 else "code_generation"
            return {
                "route_code": route_code,
                "mode": mode,
                "intent": mode,
                "reason": str(llm_result.get("reason") or "llm semantic decision"),
                "confidence": float(llm_result.get("confidence") or 0.9),
                "code_score": int(llm_result.get("code_score") or 0),
                "qa_score": int(llm_result.get("qa_score") or 0),
                "signals": list(llm_result.get("signals") or []),
                "model_used": bool(llm_result.get("model_used", False)),
            }
        except Exception:
            pass

    decision = semantic_route_judge(requirement=requirement, preferred_mode=preferred_mode)
    return {
        "route_code": int(decision.get("route_code") or 1),
        "mode": str(decision.get("mode") or "code_generation"),
        "intent": str(decision.get("intent") or decision.get("mode") or "code_generation"),
        "reason": str(decision.get("reason") or "semantic route decision"),
        "confidence": float(decision.get("confidence") or 0.7),
        "code_score": int(decision.get("code_score") or 0),
        "qa_score": int(decision.get("qa_score") or 0),
        "signals": list(decision.get("signals") or []),
        "model_used": False,
    }


def _extract_ai_team_model_config() -> tuple[str, str, str]:
    try:
        modules = _load_ai_team_modules()
        config = modules["get_config"]()
        model_config = getattr(config, "model", None)
        api_key = str(getattr(model_config, "api_key", "") or "").strip()
        model_name = str(getattr(model_config, "model_name", "") or "").strip()
        base_url = str(getattr(model_config, "base_url", "") or "").strip()
        return api_key, model_name, base_url
    except Exception:
        return "", "", ""


def _simple_qa_fallback_answer(question: str) -> str:
    answer = (
        "这是简答模式，已跳过需求分析/代码生成/代码测试流程。\n"
        f"问题：{question}\n"
        "如果你希望直接生成代码，请补充“目标文件/模块 + 期望改动”。"
    )
    return _apply_persona_voice_prefix(answer)


def _apply_persona_voice_prefix(answer: str) -> str:
    text = str(answer or "").strip()
    if not text:
        return text
    active = pss.get_active_persona_state()
    persona_raw = active.get("persona") if isinstance(active, dict) else None
    if isinstance(persona_raw, dict):
        persona_name = str(persona_raw.get("name") or persona_raw.get("personaId") or "").strip()
        if persona_name:
            prefix = f"[{persona_name}视角] "
            if text.startswith(prefix):
                return text
            return f"{prefix}{text}"
    return text


def _strip_thinking_block(text: str) -> str:
    body = str(text or "")
    if not body:
        return ""
    cleaned = _THINK_BLOCK_PATTERN.sub("", body).strip()
    return cleaned or ""


def _looks_like_internal_draft(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    markers = (
        "<think>",
        "the user wants me to act as",
        "required output structure",
        "input context",
        "let me think about this",
        "carefully parse the requirements",
        "cross-library comparison expert",
        "structured response",
    )
    return any(marker in lowered for marker in markers)


def generate_simple_qa_answer(question: str) -> str:
    question_text = str(question or "").strip()
    if not question_text:
        return "请先输入问题。"

    api_key, model_name, base_url = _extract_ai_team_model_config()
    base_system_prompt = (
        "你是 SE-Team 的简答助手。"
        "对于解释类问题，给 2-5 句直接回答，不要进入代码生成流程。"
    )
    prompt_bundle = pss.compose_system_prompt(base_system_prompt)
    system_prompt = str((prompt_bundle or {}).get("systemPrompt") or base_system_prompt)

    answer_temperature = 0.3
    try:
        raw_temp = (prompt_bundle or {}).get("temperature")
        if raw_temp is not None:
            parsed_temp = float(raw_temp)
            if 0 <= parsed_temp <= 1.5:
                answer_temperature = parsed_temp
    except (TypeError, ValueError):
        pass

    if api_key and model_name and base_url:
        try:
            from llm.rag_core.llm_api import DeepSeekAPI

            client = DeepSeekAPI(
                api_key=api_key,
                base_url=base_url,
                model=model_name,
                timeout=25,
            )
            response = client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {"role": "user", "content": question_text},
                ],
                temperature=answer_temperature,
                max_tokens=280,
                timeout=25,
            )
            choices = response.get("choices") if isinstance(response, dict) else None
            if isinstance(choices, list) and choices:
                first = choices[0] if isinstance(choices[0], dict) else {}
                message = first.get("message") if isinstance(first, dict) else {}
                content = _strip_thinking_block((message or {}).get("content") or "")
                if _looks_like_internal_draft(content):
                    content = ""
                if content:
                    content = _apply_persona_voice_prefix(content)
                    disclaimer = pss.consume_pending_disclaimer()
                    if disclaimer:
                        return f"{disclaimer}\n\n{content}"
                    return content
        except Exception:
            pass

    fallback = _simple_qa_fallback_answer(question_text)
    disclaimer = pss.consume_pending_disclaimer()
    if disclaimer:
        return f"{disclaimer}\n\n{fallback}" if fallback else disclaimer
    return fallback


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def simple_qa_sse_payload(session_id: str, requirement: str, decision: dict[str, Any]) -> list[dict[str, Any]]:
    answer = generate_simple_qa_answer(requirement)
    stages = [
        {
            "step": 1,
            "stage": "requirement_analysis",
            "display_name": "需求分析",
            "content": f"已直接将用户输入作为最终需求：{str(requirement or '').strip()}",
            "icon": "📋",
            "agent_name": "requirement_analysis",
            "agent_type": "standard",
        },
        {
            "step": 2,
            "stage": "experience_retrieval",
            "display_name": "全局经验检索",
            "content": "已进入兼容回退流程：正在根据问题检索全局经验候选。",
            "icon": "🗂️",
            "agent_name": "experience_retrieval",
            "agent_type": "advisor",
        },
        {
            "step": 3,
            "stage": "per_project_extraction",
            "display_name": "逐经验库提取",
            "content": "已进入兼容回退流程：按经验库提取关键路径与描述。",
            "icon": "🧩",
            "agent_name": "per_project_extraction",
            "agent_type": "standard",
        },
        {
            "step": 4,
            "stage": "cross_project_comparison",
            "display_name": "跨经验库对比",
            "content": "已进入兼容回退流程：对候选经验库进行优先级比较。",
            "icon": "⚖️",
            "agent_name": "cross_project_comparison",
            "agent_type": "standard",
        },
        {
            "step": 5,
            "stage": "qa_advisor",
            "display_name": "问答策略规划",
            "content": "已进入兼容回退流程：生成回答结构与引用策略。",
            "icon": "💡",
            "agent_name": "qa_advisor",
            "agent_type": "advisor",
        },
        {
            "step": 6,
            "stage": "qa_evidence_reasoning",
            "display_name": "寻找证据与构思回复",
            "content": "正在基于问题语义组织直接回答。",
            "icon": "🔎",
            "agent_name": "qa_reasoning",
            "agent_type": "standard",
        },
        {
            "step": 7,
            "stage": "qa_reply",
            "display_name": "给出回复",
            "content": answer,
            "icon": "✅",
            "agent_name": "qa_reply",
            "agent_type": "standard",
        },
    ]

    events: list[dict[str, Any]] = [
        {
            "event": "route_decision",
            "type": "route_decision",
            "route_code": int(decision.get("route_code") or 2),
            "mode": "simple_qa",
            "session_id": session_id,
            "reason": str(decision.get("reason") or "simple_qa"),
            "confidence": float(decision.get("confidence") or 0.0),
            "timestamp": _utcnow_iso(),
        },
        {
            "event": "workflow_start",
            "type": "workflow_start",
            "session_id": session_id,
            "requirement": str(requirement or "").strip(),
            "total_steps": 7,
            "mode": "simple_qa",
            "route_code": int(decision.get("route_code") or 2),
            "timestamp": _utcnow_iso(),
        },
    ]

    for stage in stages:
        events.append(
            {
                "event": "stage_start",
                "type": "stage_start",
                "timestamp": _utcnow_iso(),
                "step": stage["step"],
                "stage": stage["stage"],
                "display_name": stage["display_name"],
                "agent_name": stage["agent_name"],
                "agent_type": stage["agent_type"],
                "icon": stage["icon"],
                "mode": "simple_qa",
                "session_id": session_id,
            }
        )
        events.append(
            {
                "event": "workflow_step",
                "type": "workflow_step",
                "mode": "simple_qa",
                "session_id": session_id,
                "stage": stage["display_name"],
                "content": stage["content"],
                "timestamp": _utcnow_iso(),
            }
        )
        events.append(
            {
                "event": "stream_chunk",
                "type": "stream_chunk",
                "timestamp": _utcnow_iso(),
                "step": stage["step"],
                "stage": stage["stage"],
                "content": stage["content"],
                "mode": "simple_qa",
                "session_id": session_id,
            }
        )
        events.append(
            {
                "event": "stage_complete",
                "type": "stage_complete",
                "timestamp": _utcnow_iso(),
                "step": stage["step"],
                "stage": stage["stage"],
                "output": stage["content"],
                "pass_token": "QA_STEP_DONE",
                "mode": "simple_qa",
                "session_id": session_id,
            }
        )

    events.append(
        {
            "event": "simple_qa_answer",
            "type": "simple_qa_answer",
            "role": "assistant",
            "mode": "simple_qa",
            "session_id": session_id,
            "stage": "给出回复",
            "content": answer,
            "done": True,
            "timestamp": _utcnow_iso(),
        }
    )
    events.append(
        {
            "event": "workflow_complete",
            "type": "workflow_complete",
            "status": "completed",
            "mode": "simple_qa",
            "session_id": session_id,
            "timestamp": _utcnow_iso(),
        }
    )
    return events


def _ensure_code_chat_on_path() -> None:
    code_chat_root = resolve_code_chat_root()
    code_chat_root_str = str(code_chat_root)
    if code_chat_root_str not in sys.path:
        sys.path.insert(0, code_chat_root_str)


def _load_ai_team_modules() -> dict[str, Any]:
    _ensure_code_chat_on_path()

    from ai_team_system.agents import AGENTS, WORKFLOW_STEPS
    from ai_team_system.config import get_config, update_config
    from ai_team_system.engine import get_engine
    from ai_team_system.experience import get_experience_store

    return {
        "AGENTS": AGENTS,
        "WORKFLOW_STEPS": WORKFLOW_STEPS,
        "get_config": get_config,
        "update_config": update_config,
        "get_engine": get_engine,
        "get_experience_store": get_experience_store,
    }


_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()
_OPENCODE_STREAM_LOCK = threading.Lock()
_OPENCODE_STREAM_SESSIONS: dict[str, dict[str, Any]] = {}


def _loop_runner(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _ensure_event_loop() -> asyncio.AbstractEventLoop:
    global _loop
    global _loop_thread

    with _loop_lock:
        if _loop is not None and _loop.is_running():
            return _loop

        loop = asyncio.new_event_loop()
        thread = threading.Thread(
            target=_loop_runner,
            args=(loop,),
            name="se-team-embedded-loop",
            daemon=True,
        )
        thread.start()

        for _ in range(100):
            if loop.is_running():
                break
            time.sleep(0.01)

        _loop = loop
        _loop_thread = thread
        return loop


def _save_opencode_stream_session(session_id: str, payload: dict[str, Any]) -> None:
    with _OPENCODE_STREAM_LOCK:
        _OPENCODE_STREAM_SESSIONS[session_id] = dict(payload)


def _get_opencode_stream_session(session_id: str) -> dict[str, Any] | None:
    with _OPENCODE_STREAM_LOCK:
        payload = _OPENCODE_STREAM_SESSIONS.get(session_id)
        return dict(payload) if isinstance(payload, dict) else None


def _update_opencode_stream_session(session_id: str, **changes: Any) -> dict[str, Any] | None:
    with _OPENCODE_STREAM_LOCK:
        existing = _OPENCODE_STREAM_SESSIONS.get(session_id)
        if not isinstance(existing, dict):
            return None
        next_payload = dict(existing)
        next_payload.update(changes)
        _OPENCODE_STREAM_SESSIONS[session_id] = next_payload
        return dict(next_payload)


def _build_se_team_stage_event(
    *,
    event: str,
    session_id: str,
    step: int,
    stage: str,
    display_name: str,
    content: str = "",
    icon: str = "🧩",
    agent_name: str = "opencode_bridge",
    agent_type: str = "standard",
    artifact_files: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": event,
        "type": event,
        "timestamp": _utcnow_iso(),
        "step": step,
        "stage": stage,
        "display_name": display_name,
        "agent_name": agent_name,
        "agent_type": agent_type,
        "icon": icon,
        "mode": "code_generation",
        "session_id": session_id,
    }
    if content:
        if event == "workflow_step" or event == "stream_chunk":
            payload["content"] = content
        elif event == "stage_complete":
            payload["output"] = content
    if artifact_files:
        payload["artifact_files"] = artifact_files
        payload["artifact_paths"] = artifact_files
    return payload


def _task_exploration_event_payload(session_id: str, task_exploration: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": "task_exploration",
        "type": "task_exploration",
        "timestamp": _utcnow_iso(),
        "mode": "code_generation",
        "session_id": session_id,
        "task_exploration": _as_dict(task_exploration),
    }


def _output_write_event_payload(session_id: str, output_write: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": "output_write",
        "type": "output_write",
        "timestamp": _utcnow_iso(),
        "mode": "code_generation",
        "session_id": session_id,
        "output_write": _as_dict(output_write),
    }


def _trim_summary_lines(lines: list[str], limit: int = 5) -> str:
    trimmed: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        trimmed.append(f"- {text}")
        if len(trimmed) >= limit:
            break
    return "\n".join(trimmed)


def _stage_summary_text(stage: str, packets: dict[str, Any], result_payload: dict[str, Any], task_exploration: dict[str, Any], output_write: dict[str, Any]) -> str:
    intent_packet = _as_dict(packets.get("intent_packet"))
    intent_review = _as_dict(intent_packet.get("review"))
    retrieval_bundle = _as_dict(packets.get("retrieval_bundle"))
    evidence_packet = _as_dict(packets.get("evidence_packet"))
    evidence_summary = _as_dict(evidence_packet.get("summary"))
    evidence_review = _as_dict(evidence_packet.get("review"))
    evidence_verdict = _as_dict(packets.get("evidence_verdict"))
    advisor_packet = _as_dict(packets.get("advisor_packet"))
    advisor_analysis = _as_dict(advisor_packet.get("analysis"))
    advisor_constraints = _as_dict(advisor_packet.get("constraints"))
    solution_packet = _as_dict(result_payload.get("solution_packet"))
    solution_analysis = _as_dict(solution_packet.get("analysis"))
    opencode_kernel = _as_dict(solution_packet.get("opencode_kernel"))
    selected_path = _as_dict(retrieval_bundle.get("selected_path"))
    candidate_paths_raw = retrieval_bundle.get("candidate_paths")
    candidate_paths = candidate_paths_raw if isinstance(candidate_paths_raw, list) else []
    impacted_files_raw = solution_analysis.get("impacted_files") or evidence_review.get("impacted_files") or retrieval_bundle.get("impacted_files") or []
    impacted_files = [str(item).strip() for item in impacted_files_raw if str(item).strip()][:3]
    function_chain_raw = selected_path.get("function_chain") or []
    function_chain = [str(item).strip() for item in function_chain_raw if str(item).strip()][:3]
    edit_plan_raw = solution_packet.get("edit_plan")
    edit_plan = edit_plan_raw if isinstance(edit_plan_raw, list) else []
    implementation_targets_raw = opencode_kernel.get("implementation_targets")
    implementation_targets = implementation_targets_raw if isinstance(implementation_targets_raw, list) else []
    validation_commands_raw = solution_packet.get("validation") or opencode_kernel.get("validation_commands") or []
    validation_commands = [str(item).strip() for item in validation_commands_raw if str(item).strip()][:3]

    if stage == "requirement_advisor":
        constraints = [str(item).strip() for item in (intent_review.get("constraints") or []) if str(item).strip()][:3]
        lines = [
            f"目标：{intent_review.get('clarified_target') or intent_review.get('feature_scope') or '待明确'}",
            f"期望结果：{intent_review.get('expected_result') or '生成可直接落地的代码改动'}",
            *[f"约束：{item}" for item in constraints],
        ]
        return _trim_summary_lines(lines)

    if stage == "architecture_advisor":
        source_targets = advisor_packet.get("source_targets") if isinstance(advisor_packet.get("source_targets"), list) else []
        target_reasons = []
        for item in source_targets[:2]:
            if not isinstance(item, dict):
                continue
            advisor_name = str(item.get("advisor_name") or item.get("advisor_id") or "顾问").strip()
            reason = str(item.get("reason") or "").strip()
            if advisor_name or reason:
                target_reasons.append(f"{advisor_name}：{reason}" if reason else advisor_name)
        lines = [
            f"做什么：{advisor_analysis.get('what') or '正在对齐需求与证据'}",
            f"怎么做：{advisor_analysis.get('how') or '围绕主路径与锚点组织方案'}",
            *[f"参考建议：{item}" for item in target_reasons],
            f"约束类型：{','.join([str(item).strip() for item in (advisor_constraints.get('types') or []) if str(item).strip()][:4])}" if advisor_constraints.get("types") else "",
        ]
        return _trim_summary_lines(lines)

    if stage == "architecture_design":
        coverage = _as_dict(evidence_summary.get("coverage"))
        lines = [
            f"主路径：{selected_path.get('path_name') or selected_path.get('path_id') or '未命名路径'}",
            f"候选路径：{len(candidate_paths)} 条",
            f"关键链路：{' -> '.join(function_chain)}" if function_chain else "",
            f"影响文件：{', '.join(impacted_files)}" if impacted_files else "",
            f"证据结论：{evidence_verdict.get('verdict') or 'requery'} / 置信度 {evidence_verdict.get('confidence') or evidence_summary.get('confidence') or retrieval_bundle.get('confidence') or 'low'}",
            f"覆盖情况：text={coverage.get('text', 0)}, graph={coverage.get('graph', 0)}, path={coverage.get('functional_path', 0)}",
        ]
        return _trim_summary_lines(lines)

    if stage == "code_advisor":
        key_reasoning = solution_analysis.get("key_reasoning")
        key_reasoning_lines = [
            f"关键推理：{str(item).strip()}"
            for item in (key_reasoning[:2] if isinstance(key_reasoning, list) else [])
            if str(item).strip()
        ]
        lines = [
            f"OpenCode 状态：{task_exploration.get('status') or 'running'} / {task_exploration.get('phase') or 'queued'}",
            f"实现摘要：{opencode_kernel.get('analysis_summary') or solution_analysis.get('summary') or task_exploration.get('message') or ''}",
            f"关键链路：{' -> '.join(function_chain)}" if function_chain else "",
            *key_reasoning_lines,
        ]
        return _trim_summary_lines(lines)

    if stage == "code_implementation":
        snippet_blocks_raw = solution_packet.get("snippet_blocks")
        snippet_blocks = snippet_blocks_raw if isinstance(snippet_blocks_raw, list) else []
        plan_lines: list[str] = []
        for item in edit_plan[:3]:
            if not isinstance(item, dict):
                continue
            file_path = str(item.get("file_path") or "待定位").strip()
            action = str(item.get("action") or "modify").strip()
            reason = str(item.get("reason") or "").strip()
            plan_lines.append(f"{file_path} · {action}{f' · {reason}' if reason else ''}")
        target_lines = []
        for item in implementation_targets[:2]:
            if not isinstance(item, dict):
                continue
            file_path = str(item.get("file_path") or "").strip()
            purpose = str(item.get("purpose") or "").strip()
            if file_path:
                target_lines.append(f"实现目标：{file_path}{f' · {purpose}' if purpose else ''}")
        lines = [
            f"实现摘要：{solution_analysis.get('summary') or task_exploration.get('message') or output_write.get('reason') or ''}",
            *[f"编辑计划：{item}" for item in plan_lines],
            *target_lines,
            f"预计片段：{opencode_kernel.get('snippet_block_count') or len(snippet_blocks)} 个",
        ]
        return _trim_summary_lines(lines)

    if stage == "code_testing":
        lines = [f"验证：{item}" for item in validation_commands]
        return _trim_summary_lines(lines, limit=3)

    if stage == "requirement_validation":
        written_files_raw = output_write.get("writtenFiles")
        written_files = written_files_raw if isinstance(written_files_raw, list) else []
        lines = [
            f"结果摘要：{solution_analysis.get('summary') or 'OpenCode 已完成执行'}",
            f"写入文件：{len(written_files)} 个",
            f"最终判定：{_as_dict(solution_packet.get('output_protocol')).get('judgment', {}).get('status') or 'ready'}",
        ]
        return _trim_summary_lines(lines, limit=3)

    return ""


async def _sleep_poll(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def start_opencode_workflow_stream(
    session_id: str,
    requirement: str,
    project_path: str,
    support_context: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    normalized_project_path = str(project_path or "").strip()
    task_mode = QuestionDetector.detect_task_mode(requirement)
    total_steps = 8

    _save_opencode_stream_session(
        session_id,
        {
            "session_id": session_id,
            "status": "running",
            "current_step": "requirement_analysis",
            "completed_steps": [],
            "suspended": False,
            "suspend_questions": [],
            "artifacts": {},
            "artifact_files": [],
            "rollback_count": 0,
            "mode": "code_generation",
            "multi_agent_session_id": None,
            "project_path": normalized_project_path,
            "support_context": _as_dict(support_context),
            "task_exploration": {},
            "output_write": {},
        },
    )

    yield {
        "event": "route_decision",
        "type": "route_decision",
        "route_code": 1,
        "mode": "code_generation",
        "session_id": session_id,
        "reason": "code tasks are forced onto OpenCode-backed execution",
        "confidence": 1.0,
        "timestamp": _utcnow_iso(),
    }
    yield {
        "event": "workflow_start",
        "type": "workflow_start",
        "session_id": session_id,
        "requirement": str(requirement or "").strip(),
        "total_steps": total_steps,
        "mode": "code_generation",
        "route_code": 1,
        "timestamp": _utcnow_iso(),
    }

    stage_definitions = [
        (1, "requirement_advisor", "需求顾问指导", "💡", "advisor", "advisor_context", "正在整合项目上下文、经验库和执行约束。"),
        (2, "requirement_analysis", "需求分析", "📋", "standard", "intent_parse", f"已识别为代码任务，执行模式：{task_mode}"),
        (3, "architecture_advisor", "架构顾问指导", "💡", "advisor", "retrieval_context", "正在补充路径证据与架构锚点。"),
        (4, "architecture_design", "架构设计", "🏗️", "standard", "evidence_review", "正在审议证据并生成代码方案骨架。"),
        (5, "code_advisor", "代码顾问指导", "💡", "advisor", "opencode_exploration", "OpenCode 正在勘探项目并规划实现。"),
        (6, "code_implementation", "代码实现", "💻", "standard", "output_materialized", "OpenCode 正在写入修改/生成结果。"),
        (7, "code_testing", "代码测试", "🧪", "standard", "validation", "正在整理验证命令与执行建议。"),
        (8, "requirement_validation", "需求验证", "✅", "standard", "done", "正在汇总最终交付结果。"),
    ]

    for step, stage, display_name, icon, agent_type, _, content in stage_definitions[:2]:
        yield _build_se_team_stage_event(event="stage_start", session_id=session_id, step=step, stage=stage, display_name=display_name, icon=icon, agent_type=agent_type)
        yield _build_se_team_stage_event(event="workflow_step", session_id=session_id, step=step, stage=stage, display_name=display_name, icon=icon, agent_type=agent_type, content=content)
        yield _build_se_team_stage_event(event="stream_chunk", session_id=session_id, step=step, stage=stage, display_name=display_name, icon=icon, agent_type=agent_type, content=content)
        yield _build_se_team_stage_event(event="stage_complete", session_id=session_id, step=step, stage=stage, display_name=display_name, icon=icon, agent_type=agent_type, content=content)

    if not normalized_project_path:
        reason = "代码生成/修改任务必须绑定具体项目路径，当前无法启动 OpenCode。"
        _update_opencode_stream_session(session_id, status="failed")
        yield {
            "event": "workflow_error",
            "type": "workflow_error",
            "status": "failed",
            "mode": "code_generation",
            "session_id": session_id,
            "reason": reason,
            "timestamp": _utcnow_iso(),
        }
        return

    multi_agent_payload = mas._create_multi_agent_session(
        normalized_project_path,
        requirement,
        task_mode,
        {},
        swarm_enabled=True,
        conversation_id=None,
        advisor_enabled=True,
        opencode_enabled=True,
        output_root=None,
        auto_apply_output=True,
        external_context=_as_dict(support_context),
    )
    multi_agent_session_id = str(multi_agent_payload.get("sessionId") or "").strip()
    _update_opencode_stream_session(session_id, multi_agent_session_id=multi_agent_session_id)

    worker = threading.Thread(
        target=mas._run_multi_agent_session,
        args=(
            multi_agent_session_id,
            normalized_project_path,
            requirement,
            task_mode,
            None,
            {},
            {},
            True,
            multi_agent_payload.get("outputRoot"),
            bool(multi_agent_payload.get("autoApplyOutput", True)),
        ),
        daemon=True,
    )
    worker.start()

    emitted_stages: set[str] = set()
    completed_stages: set[str] = {"requirement_advisor", "requirement_analysis"}
    last_progress_message = ""
    last_task_exploration_signature = ""
    last_output_write_signature = ""

    while True:
        status_payload = mas._get_multi_agent_session(multi_agent_session_id) or {}
        current_stage = str(status_payload.get("stage") or "").strip()
        current_status = str(status_payload.get("status") or "running").strip() or "running"
        packets = _as_dict(status_payload.get("packets"))
        task_exploration = _as_dict(packets.get("task_exploration"))
        result_payload = _as_dict(status_payload.get("result"))
        output_write = _as_dict(result_payload.get("output_write"))
        task_exploration_phase = str(task_exploration.get("phase") or "").strip()
        task_exploration_status = str(task_exploration.get("status") or "").strip()

        _update_opencode_stream_session(
            session_id,
            status=current_status,
            current_step=current_stage or "requirement_analysis",
            completed_steps=list(completed_stages),
            task_exploration=task_exploration,
            output_write=output_write,
            artifacts=result_payload,
            artifact_files=[str(item.get("path") or item.get("relativePath") or "").strip() for item in (_as_dict(output_write).get("writtenFiles") or []) if isinstance(item, dict)],
        )

        task_exploration_signature = json.dumps(task_exploration, ensure_ascii=False, sort_keys=True) if task_exploration else ""
        if task_exploration_signature and task_exploration_signature != last_task_exploration_signature:
            last_task_exploration_signature = task_exploration_signature
            yield _task_exploration_event_payload(session_id, task_exploration)

        output_write_signature = json.dumps(output_write, ensure_ascii=False, sort_keys=True) if output_write else ""
        if output_write_signature and output_write_signature != last_output_write_signature:
            last_output_write_signature = output_write_signature
            yield _output_write_event_payload(session_id, output_write)

        for step, stage, display_name, icon, agent_type, trigger_phase, default_message in stage_definitions[2:]:
            should_emit = False
            if trigger_phase == "retrieval_context" and current_stage in {"taizi", "zhongshu", "menxia", "shangshu", "done"}:
                should_emit = True
            elif trigger_phase == "evidence_review" and current_stage in {"zhongshu", "menxia", "shangshu", "done"}:
                should_emit = True
            elif trigger_phase == "opencode_exploration" and task_exploration_phase in {"opencode_exploration", "output_materialized", "validation", "done"}:
                should_emit = True
            elif trigger_phase == "output_materialized" and (current_stage in {"shangshu", "done"} or output_write):
                should_emit = True
            elif trigger_phase == "validation" and current_status == "completed":
                should_emit = True
            elif trigger_phase == "done" and current_status == "completed":
                should_emit = True

            if should_emit and stage not in emitted_stages:
                emitted_stages.add(stage)
                yield _build_se_team_stage_event(event="stage_start", session_id=session_id, step=step, stage=stage, display_name=display_name, icon=icon, agent_type=agent_type)

            if should_emit and stage not in completed_stages:
                if stage in {"architecture_advisor", "architecture_design"}:
                    progress_message = _stage_summary_text(stage, packets, result_payload, task_exploration, output_write) or default_message
                    if progress_message and progress_message != last_progress_message:
                        last_progress_message = progress_message
                        yield _build_se_team_stage_event(event="workflow_step", session_id=session_id, step=step, stage=stage, display_name=display_name, icon=icon, agent_type=agent_type, content=progress_message)
                        yield _build_se_team_stage_event(event="stream_chunk", session_id=session_id, step=step, stage=stage, display_name=display_name, icon=icon, agent_type=agent_type, content=progress_message)
                elif stage == "code_advisor":
                    progress_message = _stage_summary_text(stage, packets, result_payload, task_exploration, output_write) or str(task_exploration.get("message") or default_message)
                    if progress_message and progress_message != last_progress_message:
                        last_progress_message = progress_message
                        yield _build_se_team_stage_event(event="workflow_step", session_id=session_id, step=step, stage=stage, display_name=display_name, icon=icon, agent_type=agent_type, content=progress_message)
                        yield _build_se_team_stage_event(event="stream_chunk", session_id=session_id, step=step, stage=stage, display_name=display_name, icon=icon, agent_type=agent_type, content=progress_message)
                elif stage == "code_implementation":
                    progress_message = _stage_summary_text(stage, packets, result_payload, task_exploration, output_write) or str(task_exploration.get("message") or default_message)
                    if progress_message and progress_message != last_progress_message:
                        last_progress_message = progress_message
                        yield _build_se_team_stage_event(event="workflow_step", session_id=session_id, step=step, stage=stage, display_name=display_name, icon=icon, agent_type=agent_type, content=progress_message)
                        yield _build_se_team_stage_event(event="stream_chunk", session_id=session_id, step=step, stage=stage, display_name=display_name, icon=icon, agent_type=agent_type, content=progress_message)

            should_complete = False
            if stage == "architecture_advisor" and current_stage in {"zhongshu", "menxia", "shangshu", "done"}:
                should_complete = True
            elif stage == "architecture_design" and current_stage in {"menxia", "shangshu", "done"}:
                should_complete = True
            elif stage == "code_advisor" and (task_exploration_phase in {"output_materialized", "validation", "done"} or task_exploration_status == "completed"):
                should_complete = True
            elif stage == "code_implementation" and bool(output_write):
                should_complete = True
            elif stage in {"code_testing", "requirement_validation"} and current_status == "completed":
                should_complete = True

            if should_emit and should_complete and stage not in completed_stages and stage in {"architecture_advisor", "architecture_design", "code_advisor", "code_implementation", "code_testing", "requirement_validation"}:
                artifact_files: list[str] = []
                if stage == "code_implementation":
                    artifact_files = [str(item.get("path") or item.get("relativePath") or "").strip() for item in (output_write.get("writtenFiles") or []) if isinstance(item, dict) and str(item.get("path") or item.get("relativePath") or "").strip()]
                    progress_message = _stage_summary_text(stage, packets, result_payload, task_exploration, output_write) or str(task_exploration.get("message") or output_write.get("reason") or default_message)
                elif stage == "code_testing":
                    progress_message = _stage_summary_text(stage, packets, result_payload, task_exploration, output_write) or "已整理验证命令与执行建议。"
                elif stage == "requirement_validation":
                    progress_message = _stage_summary_text(stage, packets, result_payload, task_exploration, output_write) or "OpenCode 执行完成，结果已回收并可在前端查看。"
                else:
                    progress_message = _stage_summary_text(stage, packets, result_payload, task_exploration, output_write) or default_message
                completed_stages.add(stage)
                yield _build_se_team_stage_event(event="stage_complete", session_id=session_id, step=step, stage=stage, display_name=display_name, icon=icon, agent_type=agent_type, content=progress_message, artifact_files=artifact_files)

        if current_status == "completed":
            solution_packet = _as_dict(result_payload.get("solution_packet"))
            analysis_payload = _as_dict(solution_packet.get("analysis"))
            summary = str(analysis_payload.get("summary") or "OpenCode 已完成执行。")
            yield {
                "event": "workflow_complete",
                "type": "workflow_complete",
                "status": "completed",
                "mode": "code_generation",
                "session_id": session_id,
                "summary": summary,
                "multi_agent_session_id": multi_agent_session_id,
                "timestamp": _utcnow_iso(),
            }
            _update_opencode_stream_session(
                session_id,
                status="completed",
                current_step="done",
                completed_steps=list(completed_stages),
                artifacts=result_payload,
                artifact_files=[str(item.get("path") or item.get("relativePath") or "").strip() for item in (_as_dict(output_write).get("writtenFiles") or []) if isinstance(item, dict)],
                task_exploration=task_exploration,
                output_write=output_write,
            )
            return

        if current_status == "failed":
            reason = str(status_payload.get("error") or "OpenCode 执行失败").strip() or "OpenCode 执行失败"
            _update_opencode_stream_session(session_id, status="failed", current_step="failed", task_exploration=task_exploration, output_write=output_write)
            yield {
                "event": "workflow_error",
                "type": "workflow_error",
                "status": "failed",
                "mode": "code_generation",
                "session_id": session_id,
                "reason": reason,
                "multi_agent_session_id": multi_agent_session_id,
                "timestamp": _utcnow_iso(),
            }
            return

        await _sleep_poll(1.0)


def run_coroutine_sync(coro: Any, timeout_seconds: float | None = None) -> Any:
    loop = _ensure_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError:
        future.cancel()
        raise


def iterate_async_generator(
    async_iter: AsyncIterator[dict[str, Any]],
    first_event_timeout_seconds: float | None = None,
    per_event_timeout_seconds: float | None = None,
) -> Iterator[dict[str, Any]]:
    first_event = True
    while True:
        try:
            timeout_seconds = first_event_timeout_seconds if first_event else per_event_timeout_seconds
            yield run_coroutine_sync(async_iter.__anext__(), timeout_seconds=timeout_seconds)
            first_event = False
        except StopAsyncIteration:
            break


def workflow_steps_payload() -> dict[str, Any]:
    modules = _load_ai_team_modules()
    steps = []
    for step in modules["WORKFLOW_STEPS"]:
        agent = modules["AGENTS"][step["agent"]]
        steps.append(
            {
                "step": step["step"],
                "stage": step["stage"],
                "display_name": step["display"],
                "agent_name": agent.name,
                "agent_type": agent.agent_type.value,
                "icon": agent.icon,
                "pass_token": step["pass_token"],
            }
        )
    return {"steps": steps}


def experiences_payload() -> dict[str, Any]:
    modules = _load_ai_team_modules()
    store = modules["get_experience_store"]()
    return {"experiences": store.get_all_summaries()}


def _normalize_mode(mode: str = "") -> str:
    normalized = str(mode or "").strip().lower()
    if normalized not in {"single_project", "global"}:
        return "single_project"
    return normalized


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def create_session(project_path: str = "", mode: str = "single_project") -> str:
    modules = _load_ai_team_modules()
    engine = modules["get_engine"]()
    session_id = str(uuid.uuid4())[:8]
    engine.create_session(
        session_id,
        selected_project_path=project_path or "",
        mode=_normalize_mode(mode),
    )
    return session_id


def ensure_stream_session(session_id: str, project_path: str = "", mode: str = "single_project") -> str:
    modules = _load_ai_team_modules()
    engine = modules["get_engine"]()
    normalized_mode = _normalize_mode(mode)
    if session_id:
        state = engine.get_session(session_id)
        if not state:
            engine.create_session(
                session_id,
                selected_project_path=project_path or "",
                mode=normalized_mode,
            )
        else:
            if project_path:
                state.selected_project_path = str(project_path).strip()
            if mode:
                state.mode = normalized_mode
        return session_id

    return create_session(project_path=project_path, mode=normalized_mode)


def get_session_scope(session_id: str) -> dict[str, str]:
    modules = _load_ai_team_modules()
    engine = modules["get_engine"]()
    state = engine.get_session(str(session_id or "").strip())
    if not state:
        return {"session_id": str(session_id or "").strip(), "mode": "", "selected_project_path": ""}
    return {
        "session_id": str(getattr(state, "session_id", session_id) or "").strip(),
        "mode": str(getattr(state, "mode", "") or "").strip().lower(),
        "selected_project_path": str(getattr(state, "selected_project_path", "") or "").strip(),
    }


def start_workflow_stream(session_id: str, requirement: str) -> AsyncIterator[dict[str, Any]]:
    modules = _load_ai_team_modules()
    engine = modules["get_engine"]()
    return engine.run_workflow(session_id, requirement)


def resume_workflow_stream(session_id: str, answers: list[str]) -> AsyncIterator[dict[str, Any]]:
    modules = _load_ai_team_modules()
    engine = modules["get_engine"]()
    return engine.resume_workflow(session_id, answers)


def session_payload(session_id: str) -> dict[str, Any] | None:
    opencode_payload = _get_opencode_stream_session(session_id)
    if isinstance(opencode_payload, dict):
        return opencode_payload
    modules = _load_ai_team_modules()
    engine = modules["get_engine"]()
    state = engine.get_session(session_id)
    if not state:
        return None
    return {
        "session_id": state.session_id,
        "status": state.status,
        "current_step": state.current_step,
        "completed_steps": state.completed_steps,
        "suspended": state.suspended,
        "suspend_questions": state.suspend_questions,
        "artifacts": list(state.artifacts.keys()),
        "rollback_count": state.rollback_count,
    }


def artifact_payload(session_id: str, key: str) -> dict[str, Any] | None:
    opencode_payload = _get_opencode_stream_session(session_id)
    if isinstance(opencode_payload, dict):
        artifacts = opencode_payload.get('artifacts') if isinstance(opencode_payload.get('artifacts'), dict) else {}
        if isinstance(artifacts, dict) and key in artifacts:
            return {"key": key, "content": artifacts[key]}
    modules = _load_ai_team_modules()
    engine = modules["get_engine"]()
    state = engine.get_session(session_id)
    if not state:
        return None
    if key not in state.artifacts:
        return None
    return {"key": key, "content": state.artifacts[key]}


def session_files_payload(session_id: str) -> dict[str, Any]:
    opencode_payload = _get_opencode_stream_session(session_id)
    if isinstance(opencode_payload, dict):
        files = [
            {"path": item, "size": 0, "modified": 0}
            for item in (opencode_payload.get('artifact_files') or [])
            if isinstance(item, str) and item.strip()
        ]
        return {"session_id": session_id, "files": files}
    modules = _load_ai_team_modules()
    get_config = modules["get_config"]

    artifact_dir = Path(get_config().artifact_dir) / session_id
    if not artifact_dir.exists():
        return {"session_id": session_id, "files": []}

    files = []
    for item in artifact_dir.rglob("*"):
        if item.is_file():
            rel = item.relative_to(artifact_dir)
            files.append(
                {
                    "path": str(rel),
                    "size": item.stat().st_size,
                    "modified": item.stat().st_mtime,
                }
            )
    return {"session_id": session_id, "files": files}


def resolve_session_file(session_id: str, file_path: str) -> Path:
    modules = _load_ai_team_modules()
    get_config = modules["get_config"]

    artifact_root = (Path(get_config().artifact_dir) / session_id).resolve()
    full_path = (artifact_root / file_path).resolve()
    if artifact_root not in full_path.parents and artifact_root != full_path:
        raise ValueError("Invalid file path")
    return full_path


def update_model_config(api_key: str = "", model_name: str = "", base_url: str = "") -> dict[str, Any]:
    modules = _load_ai_team_modules()
    update_config = modules["update_config"]

    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["model"] = {"api_key": api_key}
    if model_name:
        kwargs.setdefault("model", {})["model_name"] = model_name
    if base_url:
        kwargs.setdefault("model", {})["base_url"] = base_url

    config = update_config(**kwargs)
    return {"status": "updated", "model": config.model.model_name}


def format_sse_event(event: dict[str, Any]) -> str:
    if isinstance(event, dict) and "type" not in event:
        event_type = str(event.get("event") or "").strip()
        if event_type:
            event = {**event, "type": event_type}
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
