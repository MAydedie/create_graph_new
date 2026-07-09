#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Tuple
from urllib.error import URLError
from urllib.request import urlopen

SE_TEAM_SERVICE_URL = "http://127.0.0.1:8765/"
_SE_TEAM_HEALTHCHECK_URL = "http://127.0.0.1:8765/api/workflow/steps"

_lock = threading.Lock()
_process: subprocess.Popen | None = None


def _create_graph_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_code_chat_root() -> Path:
    return _create_graph_root().parent / "借鉴项目" / "code_chat"


def is_se_team_service_ready(timeout_seconds: float = 0.6) -> bool:
    try:
        with urlopen(_SE_TEAM_HEALTHCHECK_URL, timeout=timeout_seconds) as response:
            return 200 <= int(getattr(response, "status", 0)) < 500
    except URLError:
        return False
    except Exception:
        return False


def ensure_se_team_service_started() -> Tuple[bool, str]:
    global _process

    with _lock:
        if is_se_team_service_ready():
            return True, "SE-Team service is already running"

        if _process is not None and _process.poll() is None:
            return True, "SE-Team service is starting"

        code_chat_root = resolve_code_chat_root()
        if not code_chat_root.exists():
            return False, f"code_chat not found: {code_chat_root}"

        env = os.environ.copy()
        existing_python_path = env.get("PYTHONPATH", "").strip()
        if existing_python_path:
            env["PYTHONPATH"] = f"{code_chat_root}{os.pathsep}{existing_python_path}"
        else:
            env["PYTHONPATH"] = str(code_chat_root)

        _process = subprocess.Popen(
            [sys.executable, "-m", "ai_team_system.run"],
            cwd=str(code_chat_root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return True, "SE-Team service launch requested"
