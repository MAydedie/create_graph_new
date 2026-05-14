#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OpenCode QA bridge service."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _resolve_opencode_executable() -> str:
    explicit = _as_text(os.getenv("FH_OPENCODE_BIN") or os.getenv("OPENCODE_BIN"))
    if explicit:
        return explicit
    for name in ("opencode", "opencode.cmd", "opencode.exe"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return ""


def _build_opencode_command(executable: str) -> List[str]:
    if not executable:
        return []
    suffix = Path(executable).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        return ["cmd", "/c", executable, "run", "--format", "json"]
    return [executable, "run", "--format", "json"]


def _parse_opencode_stdout(stdout: str) -> Dict[str, str]:
    text_chunks: List[str] = []
    session_id = ""
    for raw_line in (stdout or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if not session_id:
            session_id = _as_text(payload.get("sessionID"))
        if payload.get("type") != "text":
            continue
        part = _as_dict(payload.get("part"))
        text = _as_text(part.get("text"))
        if text:
            text_chunks.append(text)
    return {"session_id": session_id, "text": "\n".join(text_chunks).strip()}


def _looks_like_process_text(text: str) -> bool:
    lowered = _as_text(text).lower()
    if not lowered:
        return False
    process_markers = [
        "i read this as",
        "i'm gathering",
        "i am gathering",
        "waiting for parallel",
        "still checking",
        "still investigating",
        "explore-agent",
        "explore agent",
        "looking into",
        "后台检索",
        "还在查",
        "还在检索",
        "继续梳理",
    ]
    return any(marker in lowered for marker in process_markers)


def _build_message(
    *,
    system_prompt: str,
    user_query: str,
    conversation_id: str,
    history: List[Dict[str, str]],
    context_payload: Optional[Dict[str, Any]] = None,
) -> str:
    payload = {
        "conversation_id": conversation_id,
        "history": [item for item in history if isinstance(item, dict)][-10:],
        "context": _as_dict(context_payload),
        "latest_user_query": user_query,
    }
    return (
        f"SYSTEM:\n{_as_text(system_prompt)}\n\n"
        f"DATA:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        "INSTRUCTIONS:\n"
        "Continue the same QA conversation. Use history when relevant. "
        "If retrieval evidence is provided, stay grounded in it. "
        "Do not output JSON unless explicitly requested."
    )


def run_opencode_qa(
    *,
    project_path: str,
    conversation_id: str,
    opencode_session_id: str = "",
    user_query: str,
    system_prompt: str,
    history: List[Dict[str, str]],
    context_payload: Optional[Dict[str, Any]] = None,
    enabled: bool = True,
    model: str = "",
    agent: str = "",
    timeout_seconds: int = 90,
) -> Dict[str, Any]:
    started_at = time.perf_counter()
    if not enabled:
        return {"type": "OpenCodeQAResult", "status": "disabled", "reason": "feature_disabled", "duration_ms": int((time.perf_counter() - started_at) * 1000)}

    root = Path(project_path)
    if not root.exists() or not root.is_dir():
        return {"type": "OpenCodeQAResult", "status": "error", "reason": f"project_path_invalid: {project_path}", "duration_ms": int((time.perf_counter() - started_at) * 1000)}

    executable = _resolve_opencode_executable()
    if not executable:
        return {"type": "OpenCodeQAResult", "status": "error", "reason": "opencode_cli_not_found", "duration_ms": int((time.perf_counter() - started_at) * 1000)}

    timeout_seconds = max(20, min(int(timeout_seconds or 90), 600))
    command = _build_opencode_command(executable)
    command.extend(["--dir", str(root)])
    normalized_session_id = _as_text(opencode_session_id)
    if normalized_session_id:
        command.extend(["--session", normalized_session_id])
    if model:
        command.extend(["--model", model])
    normalized_agent = _as_text(agent)
    if normalized_agent:
        command.extend(["--agent", normalized_agent])

    completed = None
    message = _build_message(
        system_prompt=system_prompt,
        user_query=user_query,
        conversation_id=conversation_id,
        history=history,
        context_payload=context_payload,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            check=False,
            timeout=timeout_seconds,
            input=message,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return {
            "type": "OpenCodeQAResult",
            "status": "timeout",
            "reason": f"opencode_timeout_{timeout_seconds}s",
            "duration_ms": int((time.perf_counter() - started_at) * 1000),
        }
    except Exception as exc:
        return {
            "type": "OpenCodeQAResult",
            "status": "error",
            "reason": f"opencode_runtime_error: {exc}",
            "duration_ms": int((time.perf_counter() - started_at) * 1000),
        }

    parsed = _parse_opencode_stdout((completed.stdout or "") if completed else "")
    text_output = _as_text(parsed.get("text"))
    if not text_output:
        status = "error" if completed.returncode != 0 else "no_text_output"
    elif completed.returncode != 0:
        status = "error"
    elif _looks_like_process_text(text_output):
        status = "incomplete"
    else:
        status = "ready"

    return {
        "type": "OpenCodeQAResult",
        "status": status,
        "reason": (
            None
            if status == "ready"
            else "process_text_detected"
            if status == "incomplete"
            else f"opencode_exit_{completed.returncode}"
        ),
        "duration_ms": int((time.perf_counter() - started_at) * 1000),
        "returncode": completed.returncode,
        "model": model,
        "agent": normalized_agent,
        "session_id": _as_text(parsed.get("session_id")) or normalized_session_id,
        "text": text_output[:6000],
        "stdout_tail": (completed.stdout or "")[-2000:],
        "stderr_tail": (completed.stderr or "")[-2000:],
    }
