#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.services.conversation_service import (  # noqa: E402
    _create_conversation_session,
    _run_conversation_turn,
    data_accessor,
)


DEFAULT_PROJECT_PATH = r"D:\代码仓库生图\create_graph"
DEFAULT_REPORT_DIR = r"D:\代码仓库生图\汇报\4.6"


QUESTIONS: List[str] = [
    "conversation session status 和 result 接口分别在哪里，给我定位并说明为什么这样设计。",
    "multi agent evidence extraction 在哪，告诉我关键函数和证据来源策略。",
    "RightPanel 的 Decision Trace 和 Suggested Validation 是怎么来的，定位前后端链路。",
]


def _now_text() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _trim_text(text: str, limit: int = 280) -> str:
    value = str(text or "").strip().replace("\n", " ")
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _extract_event_timeline(conversation_id: str, session_id: str) -> List[Dict[str, Any]]:
    events = data_accessor.list_conversation_events(conversation_id)
    timeline: List[Dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        payload = _as_dict(event.get("payload"))
        payload_session_id = str(payload.get("sessionId") or "").strip()
        if payload_session_id and payload_session_id != session_id:
            continue
        item = {
            "seq": event.get("seq"),
            "type": event.get("type"),
            "createdAt": event.get("createdAt"),
            "summary": _trim_text(
                str(
                    payload.get("message")
                    or payload.get("reason")
                    or payload.get("stage")
                    or payload.get("type")
                    or ""
                )
            ),
            "payload": payload,
        }
        timeline.append(item)
    return timeline


def _run_single_case(project_path: str, question: str) -> Dict[str, Any]:
    conversation_id = f"qa_stage_{uuid4().hex}"
    session = _create_conversation_session(project_path, question, conversation_id)
    session_id = str(session.get("sessionId") or "")

    _run_conversation_turn(
        session_id,
        project_path,
        question,
        conversation_id,
        force_action="run_retrieval",
    )

    session_payload = _as_dict(data_accessor.get_conversation_session(session_id))
    result = _as_dict(session_payload.get("result"))
    retrieval = _as_dict(result.get("retrieval"))
    search = _as_dict(retrieval.get("search"))

    highlights = [item for item in _as_list(retrieval.get("highlights")) if isinstance(item, dict)]
    timeline = _extract_event_timeline(conversation_id, session_id)

    return {
        "conversationId": conversation_id,
        "sessionId": session_id,
        "question": question,
        "stage1_intent": {
            "intentGuess": result.get("intentGuess"),
            "taskMode": result.get("taskMode"),
            "confidence": result.get("confidence"),
            "reason": result.get("reason"),
            "nextStep": result.get("nextStep"),
        },
        "stage2_plan": {
            "mode": search.get("mode"),
            "strategy": search.get("strategy") if isinstance(search.get("strategy"), list) else [],
            "queryPlans": search.get("queryPlans") if isinstance(search.get("queryPlans"), list) else [],
            "decisionTrace": search.get("decisionTrace") if isinstance(search.get("decisionTrace"), list) else [],
            "stats": search.get("stats") if isinstance(search.get("stats"), dict) else {},
        },
        "stage3_execution": {
            "highlights": highlights[:5],
            "highlightsCount": len(highlights),
        },
        "stage4_answer": {
            "answer": str(result.get("answer") or ""),
        },
        "stage5_validation": {
            "validationCommands": retrieval.get("validationCommands")
            if isinstance(retrieval.get("validationCommands"), list)
            else [],
        },
        "timeline": timeline,
    }


def _build_markdown(payload: Dict[str, Any]) -> str:
    cases = [item for item in _as_list(payload.get("cases")) if isinstance(item, dict)]
    lines: List[str] = [
        "# 仿 opencode 智能问答阶段测试（3问答）",
        "",
        f"- 生成时间: {payload.get('generatedAt')}",
        f"- 项目路径: `{payload.get('projectPath')}`",
        f"- 问答数量: {len(cases)}",
        "",
        "说明：每个问答按『意图理解 → 检索计划 → 执行证据 → 最终回答 → 验证建议』展开，并附事件时间线。",
        "",
    ]

    for index, case in enumerate(cases, start=1):
        stage1 = _as_dict(case.get("stage1_intent"))
        stage2 = _as_dict(case.get("stage2_plan"))
        stage3 = _as_dict(case.get("stage3_execution"))
        stage4 = _as_dict(case.get("stage4_answer"))
        stage5 = _as_dict(case.get("stage5_validation"))

        lines.extend(
            [
                f"## 问答 {index}",
                "",
                f"### Q{index}",
                str(case.get("question") or ""),
                "",
                "### 阶段1：理解用户意图",
                f"- intentGuess: `{stage1.get('intentGuess')}`",
                f"- confidence: `{stage1.get('confidence')}`",
                f"- reason: {stage1.get('reason')}",
                f"- nextStep: `{stage1.get('nextStep')}`",
                "",
                "### 阶段2：设计检索计划",
                f"- mode: `{stage2.get('mode')}`",
                f"- strategy: `{', '.join([str(item) for item in _as_list(stage2.get('strategy'))])}`",
                "- queryPlans:",
            ]
        )

        query_plans = [item for item in _as_list(stage2.get("queryPlans")) if isinstance(item, dict)]
        if query_plans:
            for plan in query_plans[:6]:
                lines.append(
                    f"  - `{plan.get('kind')}` ({plan.get('weight')}): {plan.get('query')}"
                )
        else:
            lines.append("  - (none)")

        lines.append("- decisionTrace:")
        trace_items = [item for item in _as_list(stage2.get("decisionTrace")) if isinstance(item, dict)]
        if trace_items:
            for step in trace_items:
                lines.append(
                    f"  - `{step.get('step')}` -> `{step.get('decision')}` | {step.get('reason')}"
                )
        else:
            lines.append("  - (none)")

        lines.extend([
            "",
            "### 阶段3：执行（证据命中）",
        ])
        highlights = [item for item in _as_list(stage3.get("highlights")) if isinstance(item, dict)]
        if highlights:
            for hit in highlights[:5]:
                file_path = str(hit.get("file") or hit.get("file_path") or "")
                line_start = hit.get("lineStart") if hit.get("lineStart") is not None else hit.get("line_start")
                label = hit.get("label") or hit.get("id")
                snippet = _trim_text(str(hit.get("snippet") or ""), limit=160)
                lines.append(
                    f"- `{file_path}:{line_start}` | {label} | snippet: {snippet}"
                )
        else:
            lines.append("- (no highlights)")

        lines.extend(
            [
                "",
                "### 阶段4：模型最终回复",
                str(stage4.get("answer") or ""),
                "",
                "### 阶段5：建议验证命令",
            ]
        )

        commands = [str(item) for item in _as_list(stage5.get("validationCommands")) if str(item).strip()]
        if commands:
            for cmd in commands:
                lines.append(f"- `{cmd}`")
        else:
            lines.append("- (none)")

        lines.extend(
            [
                "",
                "### 事件时间线（按回合）",
            ]
        )
        timeline = [item for item in _as_list(case.get("timeline")) if isinstance(item, dict)]
        for event in timeline[:20]:
            lines.append(
                f"- [{event.get('seq')}] `{event.get('type')}` | {event.get('summary')}"
            )
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def run_report(project_path: str = DEFAULT_PROJECT_PATH, report_dir: str = DEFAULT_REPORT_DIR) -> Dict[str, Any]:
    normalized_project = os.path.normpath(project_path)
    normalized_report_dir = os.path.normpath(report_dir)
    os.makedirs(normalized_report_dir, exist_ok=True)

    cases: List[Dict[str, Any]] = []
    for question in QUESTIONS:
        cases.append(_run_single_case(normalized_project, question))

    payload = {
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "projectPath": normalized_project,
        "cases": cases,
    }

    basename = f"仿opencode_三问答阶段测试_{_now_text()}"
    json_path = Path(normalized_report_dir) / f"{basename}.json"
    md_path = Path(normalized_report_dir) / f"{basename}.md"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    markdown = _build_markdown(payload)
    with md_path.open("w", encoding="utf-8") as handle:
        handle.write(markdown)

    payload["artifacts"] = {
        "jsonPath": str(json_path),
        "markdownPath": str(md_path),
    }
    return payload


if __name__ == "__main__":
    result = run_report()
    print(json.dumps(result.get("artifacts") or {}, ensure_ascii=False, indent=2))
