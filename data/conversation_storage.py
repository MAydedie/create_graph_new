#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
会话存储服务 - 负责 conversation 的 JSON 持久化。

Phase 1：
- 按 conversation_id 持久化会话 payload
- 支持保存、加载、删除和列表查询
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import hashlib
import json
import re


class ConversationStorage:
    """会话持久化存储。"""

    def __init__(self, storage_dir: str = "output_analysis/conversations") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_prefix(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return "conversation"
        text = re.sub(r"[^0-9a-zA-Z_-]+", "_", text)
        text = text.strip("_")
        return text[:24] or "conversation"

    def _build_filepath(self, conversation_id: str) -> Path:
        cid = (conversation_id or "").strip()
        digest = hashlib.md5(cid.encode("utf-8")).hexdigest()[:8]
        prefix = self._safe_prefix(cid)
        filename = f"{prefix}_{digest}.json"
        return self.storage_dir / filename

    def save_conversation(self, conversation_id: str, payload: Dict[str, Any]) -> Path:
        filepath = self._build_filepath(conversation_id)
        data = dict(payload or {})
        data.setdefault("conversationId", conversation_id)
        data.setdefault("updatedAt", datetime.utcnow().isoformat() + "Z")
        with filepath.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return filepath

    def load_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        filepath = self._build_filepath(conversation_id)
        if not filepath.exists():
            return None
        try:
            with filepath.open("r", encoding="utf-8") as file:
                data = json.load(file)
            if not isinstance(data, dict):
                return None
            stored_id = str(data.get("conversationId") or "").strip()
            if stored_id and stored_id != str(conversation_id or "").strip():
                return None
            return data
        except Exception:
            return None

    def delete_conversation(self, conversation_id: str) -> bool:
        filepath = self._build_filepath(conversation_id)
        if not filepath.exists():
            return False
        try:
            filepath.unlink()
            return True
        except Exception:
            return False

    def list_conversations(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for filepath in self.storage_dir.glob("*.json"):
            try:
                with filepath.open("r", encoding="utf-8") as file:
                    data = json.load(file)
                if not isinstance(data, dict):
                    continue
                cid = str(data.get("conversationId") or "").strip()
                if not cid:
                    continue
                items.append(
                    {
                        "conversationId": cid,
                        "projectPath": str(data.get("projectPath") or ""),
                        "status": str(data.get("status") or ""),
                        "updatedAt": str(data.get("updatedAt") or ""),
                        "createdAt": str(data.get("createdAt") or ""),
                    }
                )
            except Exception:
                continue
        return items
