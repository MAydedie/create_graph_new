from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from scripts.global_se_team_batch_smoke import (
    CODE_GEN_QUESTIONS,
    SIMPLE_QA_QUESTIONS,
    _event_name,
    _extract_session_id,
    _has_complete_event,
    _has_suspend_event,
    _post_stream,
)


def run_case(client, question: str, mode: str, kind: str) -> dict:
    status, events = _post_stream(
        client,
        "/api/session/start-stream",
        {
            "requirement": question,
            "session_mode": "global",
            "mode": mode,
        },
    )
    merged = list(events)
    session_id = _extract_session_id(merged)

    if kind == "code_generation":
        resume_answers = [
            "确认：这是独立代码生成任务，不依赖现有项目私有类型定义；请使用通用字段与标准库直接完成。",
            "确认：可自行做合理默认假设（在注释写明）并继续执行到workflow_complete，不需要再次提问。",
        ]
        resume_round = 0
        while _has_suspend_event(merged) and not _has_complete_event(merged) and session_id and resume_round < 2:
            answer = resume_answers[min(resume_round, len(resume_answers) - 1)]
            _, resume_events = _post_stream(
                client,
                "/api/session/resume-stream",
                {
                    "session_id": session_id,
                    "answers": [answer],
                },
            )
            merged.extend(resume_events)
            resume_round += 1

    answer = ""
    if kind == "simple_qa":
        for event in merged:
            if _event_name(event) == "simple_qa_answer":
                content = str(event.get("content") or "").strip()
                if content:
                    answer = content
    else:
        workflow_fields = ("output", "content", "result", "final_output", "final_answer", "summary")
        for event in merged:
            if _event_name(event) == "workflow_complete":
                for field in workflow_fields:
                    content = str(event.get(field) or "").strip()
                    if content and len(content) > len(answer):
                        answer = content

        stage_priority = ["code_implementation", "code_testing", "requirement_validation"]
        for stage in stage_priority:
            for event in merged:
                if _event_name(event) == "stage_complete" and str(event.get("stage") or "") == stage:
                    content = str(event.get("output") or event.get("content") or "").strip()
                    if content and len(content) > len(answer):
                        answer = content

        if not answer:
            chunks: list[str] = []
            for event in merged:
                if _event_name(event) == "stream_chunk" and str(event.get("stage") or "") in {
                    "code_implementation",
                    "code_testing",
                    "requirement_validation",
                }:
                    content = str(event.get("content") or "").strip()
                    if content:
                        chunks.append(content)
            answer = "\n".join(chunks)

    return {
        "question": question,
        "kind": kind,
        "http_status": status,
        "event_count": len(merged),
        "workflow_complete": _has_complete_event(merged),
        "answer": answer.strip(),
    }


def main() -> int:
    app = create_app()
    client = app.test_client()

    items = []
    for q in SIMPLE_QA_QUESTIONS:
        items.append(run_case(client, q, "simple_qa", "simple_qa"))
    for q in CODE_GEN_QUESTIONS:
        items.append(run_case(client, q, "code_generation", "code_generation"))

    out_path = "scripts/global_se_team_qna_latest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"WROTE {len(items)} items to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
