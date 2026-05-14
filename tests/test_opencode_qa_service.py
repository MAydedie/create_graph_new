import subprocess

from app.services.opencode_qa_service import run_opencode_qa


def test_run_opencode_qa_first_turn_omits_session_and_agent_by_default(monkeypatch, tmp_path):
    recorded = {}

    def _fake_run(command, **kwargs):
        recorded["command"] = command
        recorded["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"sessionID":"conv-session-1","type":"text","part":{"text":"session answer"}}\n',
            stderr='',
        )

    monkeypatch.setenv("FH_OPENCODE_BIN", "opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = run_opencode_qa(
        project_path=str(tmp_path),
        conversation_id="conv-session-1",
        user_query="继续回答",
        system_prompt="你是问答助手",
        history=[{"role": "user", "content": "上一个问题"}],
        context_payload={"mode": "general_chat"},
        enabled=True,
    )

    assert "--session" not in recorded["command"]
    assert "--agent" not in recorded["command"]
    assert recorded["kwargs"]["cwd"] == str(tmp_path)
    assert "上一个问题" in recorded["kwargs"]["input"]
    assert result["status"] == "ready"
    assert result["session_id"] == "conv-session-1"
    assert result["text"] == "session answer"


def test_run_opencode_qa_followup_turn_reuses_stored_session(monkeypatch, tmp_path):
    recorded = {}

    def _fake_run(command, **kwargs):
        recorded["command"] = command
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"sessionID":"oc-session-2","type":"text","part":{"text":"follow-up answer"}}\n',
            stderr="",
        )

    monkeypatch.setenv("FH_OPENCODE_BIN", "opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = run_opencode_qa(
        project_path=str(tmp_path),
        conversation_id="conv-session-1",
        opencode_session_id="oc-session-2",
        user_query="继续回答",
        system_prompt="你是问答助手",
        history=[],
        enabled=True,
    )

    assert recorded["command"].count("--session") == 1
    assert "oc-session-2" in recorded["command"]
    assert result["session_id"] == "oc-session-2"


def test_run_opencode_qa_marks_process_text_as_incomplete(monkeypatch, tmp_path):
    def _fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"sessionID":"conv-session-2","type":"text","part":{"text":"I\'m gathering evidence and waiting for parallel explore-agent results."}}\n',
            stderr='',
        )

    monkeypatch.setenv("FH_OPENCODE_BIN", "opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = run_opencode_qa(
        project_path=str(tmp_path),
        conversation_id="conv-session-2",
        user_query="继续回答",
        system_prompt="你是问答助手",
        history=[],
        enabled=True,
    )

    assert result["status"] == "incomplete"
    assert result["reason"] == "process_text_detected"
