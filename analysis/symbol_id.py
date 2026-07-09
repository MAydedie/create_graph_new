#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
稳定 symbol/file/relation id 生成器。

目标：
1. 对同一个符号在同一文件同一位置重复运行时生成稳定 ID
2. 尽量避免依赖运行时顺序
3. 输出适合 JSON / SQLite 存储的短字符串
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional


def _normalize_path(path: Optional[str]) -> str:
    raw = os.path.normpath(str(path or "")).replace("\\", "/")
    return raw.strip()


def _digest(text: str, length: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def make_file_id(file_path: str) -> str:
    normalized = _normalize_path(file_path)
    return f"file:{_digest(normalized, 20)}"


def make_symbol_id(
    *,
    file_path: str,
    line_start: int,
    line_end: int,
    kind: str,
    name: str,
    owner: Optional[str] = None,
) -> str:
    normalized_path = _normalize_path(file_path)
    normalized_kind = str(kind or "unknown").strip().lower()
    normalized_name = str(name or "unknown").strip()
    normalized_owner = str(owner or "").strip()
    payload = "|".join(
        [
            normalized_path,
            str(line_start or 0),
            str(line_end or 0),
            normalized_kind,
            normalized_name,
            normalized_owner,
        ]
    )
    return f"sym:{_digest(payload, 20)}"


def make_relation_id(
    *,
    source_id: str,
    target_id: str,
    relation_type: str,
    file_path: Optional[str] = None,
    line_number: Optional[int] = None,
) -> str:
    payload = "|".join(
        [
            str(source_id or ""),
            str(target_id or ""),
            str(relation_type or "").strip().lower(),
            _normalize_path(file_path),
            str(line_number or 0),
        ]
    )
    return f"rel:{_digest(payload, 20)}"
