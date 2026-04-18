from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / "runtime"
INPUT_FILE = BASE_DIR / "requirements_input.txt"
SKILL_LIBRARY_FILE = BASE_DIR / "skills_library.json"

SYNONYM_GROUPS = {
    "skill": ["skill", "技能", "能力"],
    "match": ["匹配", "match", "路由", "选择", "召回"],
    "clarify": ["澄清", "clarify", "结构化", "需求"],
    "loop": ["循环", "闭环", "loop", "回退", "rollback"],
    "code": ["代码", "code", "编写", "实现", "开发"],
    "plan": ["计划", "规划", "plan", "设计", "蓝图", "工图"],
    "test": ["测试", "test", "验证", "验收"],
    "agent": ["agent", "智能体", "代理"],
    "prompt": ["prompt", "提示词", "提示"],
    "project": ["project", "项目"],
}


def ensure_runtime() -> Path:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_DIR


def utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def tokenize(text: str) -> List[str]:
    raw_tokens = re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]{1,8}", text.lower())
    tokens: List[str] = []
    for token in raw_tokens:
        normalized = token.strip("_-")
        if len(normalized) <= 1:
            continue
        tokens.append(normalized)
    return dedupe(tokens)


def expand_tokens(tokens: Iterable[str]) -> List[str]:
    expanded = set(tokens)
    lowered = {token.lower() for token in tokens}
    for canonical, variants in SYNONYM_GROUPS.items():
        variant_set = {item.lower() for item in variants}
        if lowered.intersection(variant_set):
            expanded.add(canonical)
            expanded.update(variant_set)
    return sorted(expanded)


def similarity(left_tokens: Iterable[str], right_tokens: Iterable[str]) -> float:
    left = set(expand_tokens(left_tokens))
    right = set(expand_tokens(right_tokens))
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def dedupe(items: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def print_output(title: str, path: Path) -> None:
    print(f"[v1.0] {title}: {path}")
