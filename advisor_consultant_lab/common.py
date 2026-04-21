from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")
STOP_TOKENS = {
    "python",
    "json",
    "runtime",
    "step",
    "agent",
    "skill",
    "skills",
    "code",
    "需求",
    "生成",
    "输出",
    "输入",
    "阶段",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_runtime(runtime_dir: Path) -> Path:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        normalized = as_str(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def tokenize(text: str) -> list[str]:
    normalized = as_str(text).lower()
    if not normalized:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for token in TOKEN_PATTERN.findall(normalized):
        if token in STOP_TOKENS:
            continue
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result
