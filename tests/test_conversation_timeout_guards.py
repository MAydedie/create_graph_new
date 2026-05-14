import sys
import time
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services import conversation_service
from app.services import multi_agent_service


def test_execute_with_timeout_returns_result_quickly():
    result = conversation_service._execute_with_timeout(0.2, lambda: "ok")
    assert result == "ok"


def test_execute_with_timeout_raises_without_waiting_for_worker_completion():
    started = time.monotonic()

    with pytest.raises(conversation_service.FuturesTimeoutError):
        conversation_service._execute_with_timeout(0.05, time.sleep, 0.3)

    elapsed = time.monotonic() - started
    assert elapsed < 0.2


def test_execute_with_timeout_respects_global_worker_limit(monkeypatch):
    import threading

    worker_limit = threading.BoundedSemaphore(1)
    monkeypatch.setattr(conversation_service, "_TIMEOUT_WORKER_SEMAPHORE", worker_limit)

    errors = []

    def hold_slot() -> None:
        try:
            conversation_service._execute_with_timeout(0.3, time.sleep, 0.2)
        except Exception as exc:  # pragma: no cover - defensive capture
            errors.append(exc)

    holder = threading.Thread(target=hold_slot)
    holder.start()
    time.sleep(0.03)

    started = time.monotonic()
    with pytest.raises(conversation_service.FuturesTimeoutError):
        conversation_service._execute_with_timeout(0.05, lambda: "second")
    elapsed = time.monotonic() - started

    holder.join(timeout=1)
    assert not errors
    assert elapsed < 0.2


def test_build_weighted_qa_context_returns_none_on_timeout(monkeypatch):
    monkeypatch.setattr(conversation_service, "_get_qa_context_timeout_seconds", lambda: 0.05)

    def slow_build_qa_context_bundle(**kwargs):
        time.sleep(0.2)
        return {"bundle": True, "kwargs": kwargs}

    monkeypatch.setattr(multi_agent_service, "build_qa_context_bundle", slow_build_qa_context_bundle)

    started = time.monotonic()
    result = conversation_service._build_weighted_qa_context(
        project_path="/tmp/project",
        user_query="metric.py 调用链在哪个文件哪一行？",
        action="run_retrieval",
        task_mode="none",
    )
    elapsed = time.monotonic() - started

    assert result is None
    assert elapsed < 0.5


def _install_stale_running_session(monkeypatch, *, session_payload, conversation_payload, events=None):
    session_store = dict(session_payload)

    monkeypatch.setattr(
        conversation_service.data_accessor,
        "get_conversation_session",
        lambda session_id: dict(session_store) if session_id == session_store["sessionId"] else None,
    )
    monkeypatch.setattr(
        conversation_service.data_accessor,
        "save_conversation_session",
        lambda session_id, payload: session_store.update(payload) if session_id == session_store["sessionId"] else None,
    )
    monkeypatch.setattr(
        conversation_service.data_accessor,
        "get_conversation",
        lambda conversation_id: conversation_payload if conversation_id == conversation_payload["conversationId"] else None,
    )
    monkeypatch.setattr(
        conversation_service.data_accessor,
        "list_conversation_events",
        lambda conversation_id, since_seq=0, limit=200: list(events or []),
    )

    return session_store


def _make_running_session(*, conversation_id="conversation-1"):
    return {
        "sessionId": "session-1",
        "conversationId": conversation_id,
        "projectPath": "/tmp/project",
        "status": "running",
        "stage": "chat",
        "message": "still running",
        "error": None,
        "result": None,
        "startedAt": "2026-04-24T00:00:00Z",
        "updatedAt": "2026-04-24T00:00:01Z",
        "completedAt": None,
    }


def _get_json(response):
    return response.get_json()


def _make_test_client():
    from app import create_app

    return create_app().test_client()


def test_stale_running_session_with_pending_question_reconciles_to_completed_result(monkeypatch):
    session_store = _install_stale_running_session(
        monkeypatch,
        session_payload=_make_running_session(),
        conversation_payload={
            "conversationId": "conversation-1",
            "status": "active",
            "pendingQuestion": {"questionId": "q-1", "question": "需要补充哪个模块？"},
            "parts": [],
            "messages": [],
            "updatedAt": "2026-04-24T00:00:02Z",
        },
    )

    client = _make_test_client()

    status_response = client.get("/api/conversations/session/session-1/status")
    result_response = client.get("/api/conversations/session/session-1/result")
    events_response = client.get("/api/conversations/conversation-1/events?session_id=session-1")

    assert status_response.status_code == 200
    assert _get_json(status_response)["status"] == "completed"
    assert _get_json(status_response)["completedAt"]
    assert result_response.status_code == 200
    assert _get_json(result_response)["nextStep"] == "ask_clarification"
    assert _get_json(result_response)["pendingQuestion"]["questionId"] == "q-1"
    assert b'event: stream_end' in events_response.data
    assert b'"reason": "session_terminal"' in events_response.data
    assert session_store["status"] == "completed"


def test_stale_running_session_with_latest_task_handoff_reconciles_to_multi_agent_result(monkeypatch):
    _install_stale_running_session(
        monkeypatch,
        session_payload=_make_running_session(),
        conversation_payload={
            "conversationId": "conversation-1",
            "status": "active",
            "pendingQuestion": None,
            "parts": [
                {"type": "assistant_text", "content": "old"},
                {
                    "type": "task_handoff",
                    "content": "需求已达到进入代码流条件。你可以继续调用 multi_agent 会话执行。",
                    "metadata": {"planId": "handoff-1", "autoStarted": False},
                },
            ],
            "messages": [],
            "updatedAt": "2026-04-24T00:00:02Z",
        },
    )

    client = _make_test_client()

    status_response = client.get("/api/conversations/session/session-1/status")
    result_response = client.get("/api/conversations/session/session-1/result")
    events_response = client.get("/api/conversations/conversation-1/events?session_id=session-1")

    assert status_response.status_code == 200
    assert _get_json(status_response)["status"] == "completed"
    assert result_response.status_code == 200
    assert _get_json(result_response)["nextStep"] == "start_multi_agent"
    assert _get_json(result_response)["handoff"]["planId"] == "handoff-1"
    assert b'event: stream_end' in events_response.data
    assert b'"status": "completed"' in events_response.data


def test_stale_running_session_with_latest_assistant_answer_reconciles_to_completed_chat_result(monkeypatch):
    _install_stale_running_session(
        monkeypatch,
        session_payload=_make_running_session(),
        conversation_payload={
            "conversationId": "conversation-1",
            "status": "active",
            "pendingQuestion": None,
            "parts": [
                {"type": "assistant_text", "content": "最终答复", "metadata": {"mode": "general_chat"}},
            ],
            "messages": [{"role": "assistant", "content": "更早的答复"}],
            "updatedAt": "2026-04-24T00:00:02Z",
        },
    )

    client = _make_test_client()

    status_response = client.get("/api/conversations/session/session-1/status")
    result_response = client.get("/api/conversations/session/session-1/result")

    assert status_response.status_code == 200
    assert _get_json(status_response)["status"] == "completed"
    assert result_response.status_code == 200
    assert _get_json(result_response)["answer"] == "最终答复"


def test_stale_running_session_without_terminal_artifacts_stays_non_terminal(monkeypatch):
    _install_stale_running_session(
        monkeypatch,
        session_payload=_make_running_session(),
        conversation_payload={
            "conversationId": "conversation-1",
            "status": "active",
            "pendingQuestion": None,
            "parts": [{"type": "tool_call", "content": "still working"}],
            "messages": [{"role": "user", "content": "继续"}],
            "updatedAt": "2026-04-24T00:00:02Z",
        },
    )

    client = _make_test_client()

    status_response = client.get("/api/conversations/session/session-1/status")
    result_response = client.get("/api/conversations/session/session-1/result")

    assert status_response.status_code == 200
    assert _get_json(status_response)["status"] == "running"
    assert result_response.status_code == 409
    assert _get_json(result_response)["error"] == "结果尚未就绪"
