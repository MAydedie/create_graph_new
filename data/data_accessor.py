#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一数据访问层（Phase 0 / Task 0.1）

目标：
- 将 app.py 中的全局缓存（main_analysis_cache / function_hierarchy_cache / report）统一封装
- 提供线程安全、路径标准化的读写接口
- 后续可在此基础上做持久化（JSON/SQLite/DB）而不影响上层调用
"""

from __future__ import annotations

import copy
import os
import threading
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _norm_project_path(project_path: str) -> str:
    """标准化项目路径（兼容Windows反斜杠等）。"""
    return os.path.normpath(project_path or "")


def _norm_session_id(session_id: str) -> str:
    return str(session_id or "").strip()


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


class DataAccessor:
    """统一数据访问器（线程安全内存缓存）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._main_analysis_cache: Dict[str, Dict[str, Any]] = {}
        self._function_hierarchy_cache: Dict[str, Dict[str, Any]] = {}
        self._function_hierarchy_layer_cache: Dict[str, Dict[str, Any]] = {}
        self._process_shadow_cache: Dict[str, Dict[str, Any]] = {}
        self._community_shadow_cache: Dict[str, Dict[str, Any]] = {}
        self._report_cache: Dict[str, Any] = {}
        self._workbench_session_cache: Dict[str, Dict[str, Any]] = {}
        self._benchmark_session_cache: Dict[str, Dict[str, Any]] = {}
        self._multi_agent_session_cache: Dict[str, Dict[str, Any]] = {}
        self._conversation_session_cache: Dict[str, Dict[str, Any]] = {}
        self._conversation_cache: Dict[str, Dict[str, Any]] = {}
        self._conversation_storage: Optional[Any] = None
        try:
            from data.conversation_storage import ConversationStorage

            self._conversation_storage = ConversationStorage()
        except Exception:
            self._conversation_storage = None

    # -------- Main analysis (graph_data) --------
    def save_main_analysis(self, project_path: str, graph_data: Dict[str, Any]) -> None:
        key = _norm_project_path(project_path)
        with self._lock:
            self._main_analysis_cache[key] = graph_data

    def get_main_analysis(self, project_path: str) -> Optional[Dict[str, Any]]:
        key = _norm_project_path(project_path)
        with self._lock:
            return self._main_analysis_cache.get(key)

    def delete_main_analysis(self, project_path: str) -> bool:
        key = _norm_project_path(project_path)
        with self._lock:
            existed = key in self._main_analysis_cache
            if existed:
                del self._main_analysis_cache[key]
            return existed

    def list_main_analysis_keys(self) -> List[str]:
        with self._lock:
            return list(self._main_analysis_cache.keys())

    # -------- Function hierarchy analysis (result_data) --------
    def save_function_hierarchy(self, project_path: str, result_data: Dict[str, Any]) -> None:
        key = _norm_project_path(project_path)
        with self._lock:
            self._function_hierarchy_cache[key] = result_data

    def get_function_hierarchy(self, project_path: str) -> Optional[Dict[str, Any]]:
        key = _norm_project_path(project_path)
        with self._lock:
            return self._function_hierarchy_cache.get(key)

    def delete_function_hierarchy(self, project_path: str) -> bool:
        key = _norm_project_path(project_path)
        with self._lock:
            existed = key in self._function_hierarchy_cache
            if existed:
                del self._function_hierarchy_cache[key]
            return existed

    def list_function_hierarchy_keys(self) -> List[str]:
        with self._lock:
            return list(self._function_hierarchy_cache.keys())

    def save_function_hierarchy_layer_cache(self, project_path: str, cache_payload: Dict[str, Any]) -> None:
        key = _norm_project_path(project_path)
        with self._lock:
            self._function_hierarchy_layer_cache[key] = cache_payload

    def get_function_hierarchy_layer_cache(self, project_path: str) -> Optional[Dict[str, Any]]:
        key = _norm_project_path(project_path)
        with self._lock:
            return self._function_hierarchy_layer_cache.get(key)

    def delete_function_hierarchy_layer_cache(self, project_path: str) -> bool:
        key = _norm_project_path(project_path)
        with self._lock:
            existed = key in self._function_hierarchy_layer_cache
            if existed:
                del self._function_hierarchy_layer_cache[key]
            return existed

    def list_function_hierarchy_layer_cache_keys(self) -> List[str]:
        with self._lock:
            return list(self._function_hierarchy_layer_cache.keys())

    # -------- Process shadow analysis (Phase 3) --------
    def save_process_shadow(self, project_path: str, process_shadow: Dict[str, Any]) -> None:
        key = _norm_project_path(project_path)
        with self._lock:
            self._process_shadow_cache[key] = process_shadow

    def get_process_shadow(self, project_path: str) -> Optional[Dict[str, Any]]:
        key = _norm_project_path(project_path)
        with self._lock:
            return self._process_shadow_cache.get(key)

    def delete_process_shadow(self, project_path: str) -> bool:
        key = _norm_project_path(project_path)
        with self._lock:
            existed = key in self._process_shadow_cache
            if existed:
                del self._process_shadow_cache[key]
            return existed

    # -------- Community shadow analysis (Phase 5) --------
    def save_community_shadow(self, project_path: str, community_shadow: Dict[str, Any]) -> None:
        key = _norm_project_path(project_path)
        with self._lock:
            self._community_shadow_cache[key] = community_shadow

    def get_community_shadow(self, project_path: str) -> Optional[Dict[str, Any]]:
        key = _norm_project_path(project_path)
        with self._lock:
            return self._community_shadow_cache.get(key)

    def delete_community_shadow(self, project_path: str) -> bool:
        key = _norm_project_path(project_path)
        with self._lock:
            existed = key in self._community_shadow_cache
            if existed:
                del self._community_shadow_cache[key]
            return existed

    # -------- ProjectAnalysisReport --------
    def save_report(self, project_path: str, report: Any) -> None:
        key = _norm_project_path(project_path)
        with self._lock:
            self._report_cache[key] = report

    def get_report(self, project_path: str) -> Optional[Any]:
        key = _norm_project_path(project_path)
        with self._lock:
            return self._report_cache.get(key)

    # -------- Unified workbench sessions (Phase 1) --------
    def save_workbench_session(self, session_id: str, session_payload: Dict[str, Any]) -> None:
        with self._lock:
            self._workbench_session_cache[session_id] = session_payload

    def get_workbench_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._workbench_session_cache.get(session_id)

    def delete_workbench_session(self, session_id: str) -> bool:
        with self._lock:
            existed = session_id in self._workbench_session_cache
            if existed:
                del self._workbench_session_cache[session_id]
            return existed

    def list_workbench_session_ids(self) -> List[str]:
        with self._lock:
            return list(self._workbench_session_cache.keys())

    # -------- Fixed-scenario benchmark sessions --------
    def save_benchmark_session(self, session_id: str, session_payload: Dict[str, Any]) -> None:
        sid = _norm_session_id(session_id)
        if not sid:
            return
        with self._lock:
            self._benchmark_session_cache[sid] = copy.deepcopy(session_payload)

    def get_benchmark_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        sid = _norm_session_id(session_id)
        if not sid:
            return None
        with self._lock:
            payload = self._benchmark_session_cache.get(sid)
            if not isinstance(payload, dict):
                return None
            return copy.deepcopy(payload)

    def delete_benchmark_session(self, session_id: str) -> bool:
        sid = _norm_session_id(session_id)
        if not sid:
            return False
        with self._lock:
            existed = sid in self._benchmark_session_cache
            if existed:
                del self._benchmark_session_cache[sid]
            return existed

    def list_benchmark_session_ids(self) -> List[str]:
        with self._lock:
            return list(self._benchmark_session_cache.keys())

    # -------- Multi-agent orchestration sessions --------
    def save_multi_agent_session(self, session_id: str, session_payload: Dict[str, Any]) -> None:
        with self._lock:
            self._multi_agent_session_cache[session_id] = session_payload

    def get_multi_agent_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._multi_agent_session_cache.get(session_id)

    def delete_multi_agent_session(self, session_id: str) -> bool:
        with self._lock:
            existed = session_id in self._multi_agent_session_cache
            if existed:
                del self._multi_agent_session_cache[session_id]
            return existed

    def list_multi_agent_session_ids(self) -> List[str]:
        with self._lock:
            return list(self._multi_agent_session_cache.keys())

    # -------- Conversation turn sessions --------
    def save_conversation_session(self, session_id: str, session_payload: Dict[str, Any]) -> None:
        sid = _norm_session_id(session_id)
        if not sid:
            return
        with self._lock:
            self._conversation_session_cache[sid] = session_payload

    def get_conversation_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        sid = _norm_session_id(session_id)
        if not sid:
            return None
        with self._lock:
            payload = self._conversation_session_cache.get(sid)
            if not isinstance(payload, dict):
                return None
            return copy.deepcopy(payload)

    def delete_conversation_session(self, session_id: str) -> bool:
        sid = _norm_session_id(session_id)
        if not sid:
            return False
        with self._lock:
            existed = sid in self._conversation_session_cache
            if existed:
                del self._conversation_session_cache[sid]
            return existed

    def list_conversation_session_ids(self) -> List[str]:
        with self._lock:
            return list(self._conversation_session_cache.keys())

    # -------- Conversation sessions (Phase 1 migration) --------
    @staticmethod
    def _create_default_conversation(conversation_id: str, project_path: str = "") -> Dict[str, Any]:
        now = _utcnow_iso()
        return {
            "conversationId": conversation_id,
            "projectPath": _norm_project_path(project_path),
            "status": "active",
            "messages": [],
            "parts": [],
            "pendingQuestion": None,
            "questionReplies": [],
            "summarySnapshot": None,
            "compactionHistory": [],
            "keyFactsMemory": {},
            "eventLog": [],
            "createdAt": now,
            "updatedAt": now,
        }

    def _persist_conversation_unlocked(self, conversation_id: str, conversation_payload: Dict[str, Any]) -> None:
        if not self._conversation_storage:
            return
        try:
            self._conversation_storage.save_conversation(conversation_id, conversation_payload)
        except Exception:
            return

    def _load_conversation_from_storage(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        if not self._conversation_storage:
            return None
        try:
            loaded = self._conversation_storage.load_conversation(conversation_id)
        except Exception:
            return None
        if not isinstance(loaded, dict):
            return None
        loaded.setdefault("conversationId", conversation_id)
        loaded.setdefault("messages", [])
        loaded.setdefault("parts", [])
        loaded.setdefault("pendingQuestion", None)
        loaded.setdefault("questionReplies", [])
        loaded.setdefault("summarySnapshot", None)
        loaded.setdefault("compactionHistory", [])
        loaded.setdefault("keyFactsMemory", {})
        loaded.setdefault("eventLog", [])
        loaded.setdefault("status", "active")
        loaded.setdefault("createdAt", _utcnow_iso())
        loaded.setdefault("updatedAt", _utcnow_iso())
        return loaded

    def save_conversation(self, conversation_id: str, conversation_payload: Dict[str, Any]) -> None:
        cid = _norm_session_id(conversation_id)
        if not cid:
            return
        payload = copy.deepcopy(conversation_payload or {})
        payload.setdefault("conversationId", cid)
        payload.setdefault("messages", [])
        payload.setdefault("parts", [])
        payload.setdefault("pendingQuestion", None)
        payload.setdefault("questionReplies", [])
        payload.setdefault("summarySnapshot", None)
        payload.setdefault("compactionHistory", [])
        payload.setdefault("keyFactsMemory", {})
        payload.setdefault("eventLog", [])
        payload.setdefault("status", "active")
        payload.setdefault("createdAt", _utcnow_iso())
        payload["updatedAt"] = _utcnow_iso()
        payload["projectPath"] = _norm_project_path(str(payload.get("projectPath") or ""))
        with self._lock:
            self._conversation_cache[cid] = payload
            self._persist_conversation_unlocked(cid, payload)

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        cid = _norm_session_id(conversation_id)
        if not cid:
            return None
        with self._lock:
            cached = self._conversation_cache.get(cid)
            if isinstance(cached, dict):
                return copy.deepcopy(cached)
            loaded = self._load_conversation_from_storage(cid)
            if isinstance(loaded, dict):
                self._conversation_cache[cid] = loaded
                return copy.deepcopy(loaded)
            return None

    def delete_conversation(self, conversation_id: str) -> bool:
        cid = _norm_session_id(conversation_id)
        if not cid:
            return False
        with self._lock:
            existed = cid in self._conversation_cache
            if existed:
                del self._conversation_cache[cid]
            deleted_storage = False
            if self._conversation_storage:
                try:
                    deleted_storage = bool(self._conversation_storage.delete_conversation(cid))
                except Exception:
                    deleted_storage = False
            return existed or deleted_storage

    def list_conversation_ids(self) -> List[str]:
        with self._lock:
            ids = set(self._conversation_cache.keys())
            if self._conversation_storage:
                try:
                    persisted = self._conversation_storage.list_conversations() or []
                    for item in persisted:
                        if not isinstance(item, dict):
                            continue
                        cid = _norm_session_id(str(item.get("conversationId") or ""))
                        if cid:
                            ids.add(cid)
                except Exception:
                    pass
            return sorted(ids)

    def ensure_conversation(self, conversation_id: Optional[str], project_path: str = "") -> Dict[str, Any]:
        cid = _norm_session_id(str(conversation_id or "")) or uuid4().hex
        payload = self.get_conversation(cid)
        if isinstance(payload, dict):
            return payload
        created = self._create_default_conversation(cid, project_path)
        self.save_conversation(cid, created)
        return self.get_conversation(cid) or created

    def list_conversation_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        payload = self.get_conversation(conversation_id)
        if not isinstance(payload, dict):
            return []
        messages = payload.get("messages")
        if not isinstance(messages, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for item in messages:
            if isinstance(item, dict):
                normalized.append(copy.deepcopy(item))
        return normalized

    def append_conversation_message(self, conversation_id: str, message_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        cid = _norm_session_id(conversation_id)
        if not cid:
            return []
        payload = self.ensure_conversation(cid)
        messages = payload.get("messages")
        if not isinstance(messages, list):
            messages = []
            payload["messages"] = messages

        item = copy.deepcopy(message_payload or {})
        item.setdefault("messageId", uuid4().hex)
        item.setdefault("createdAt", _utcnow_iso())
        role = str(item.get("role") or "assistant").strip() or "assistant"
        item["role"] = role
        item.setdefault("content", "")

        messages.append(item)
        payload["updatedAt"] = _utcnow_iso()
        self.save_conversation(cid, payload)
        return self.list_conversation_messages(cid)

    def list_conversation_parts(self, conversation_id: str) -> List[Dict[str, Any]]:
        payload = self.get_conversation(conversation_id)
        if not isinstance(payload, dict):
            return []
        parts = payload.get("parts")
        if not isinstance(parts, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for item in parts:
            if isinstance(item, dict):
                normalized.append(copy.deepcopy(item))
        return normalized

    def append_conversation_part(self, conversation_id: str, part_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        cid = _norm_session_id(conversation_id)
        if not cid:
            return []
        payload = self.ensure_conversation(cid)
        parts = payload.get("parts")
        if not isinstance(parts, list):
            parts = []
            payload["parts"] = parts

        item = copy.deepcopy(part_payload or {})
        item.setdefault("partId", uuid4().hex)
        item.setdefault("createdAt", _utcnow_iso())
        item.setdefault("type", "text")
        parts.append(item)

        payload["updatedAt"] = _utcnow_iso()
        self.save_conversation(cid, payload)
        return self.list_conversation_parts(cid)

    def set_conversation_pending_question(self, conversation_id: str, question_payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        cid = _norm_session_id(conversation_id)
        if not cid:
            return None
        payload = self.ensure_conversation(cid)
        if question_payload is None:
            payload["pendingQuestion"] = None
            payload["updatedAt"] = _utcnow_iso()
            self.save_conversation(cid, payload)
            return None

        item = copy.deepcopy(question_payload)
        item.setdefault("questionId", uuid4().hex)
        item.setdefault("createdAt", _utcnow_iso())
        item.setdefault("status", "pending")
        payload["pendingQuestion"] = item
        payload["updatedAt"] = _utcnow_iso()
        self.save_conversation(cid, payload)
        return copy.deepcopy(item)

    def get_conversation_pending_question(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        payload = self.get_conversation(conversation_id)
        if not isinstance(payload, dict):
            return None
        pending = payload.get("pendingQuestion")
        if not isinstance(pending, dict):
            return None
        return copy.deepcopy(pending)

    def save_conversation_reply(self, conversation_id: str, reply_payload: Dict[str, Any]) -> Dict[str, Any]:
        cid = _norm_session_id(conversation_id)
        payload = self.ensure_conversation(cid)
        reply = copy.deepcopy(reply_payload or {})
        reply.setdefault("replyId", uuid4().hex)
        reply.setdefault("createdAt", _utcnow_iso())

        replies = payload.get("questionReplies")
        if not isinstance(replies, list):
            replies = []
            payload["questionReplies"] = replies
        replies.append(reply)

        pending = payload.get("pendingQuestion")
        if isinstance(pending, dict):
            pending_question_id = str(pending.get("questionId") or "").strip()
            reply_question_id = str(reply.get("questionId") or "").strip()
            if not reply_question_id or reply_question_id == pending_question_id:
                pending["status"] = "answered"
                pending["answeredAt"] = _utcnow_iso()
                payload["pendingQuestion"] = None

        payload["updatedAt"] = _utcnow_iso()
        self.save_conversation(cid, payload)
        return reply

    def save_conversation_summary_snapshot(self, conversation_id: str, summary_payload: Dict[str, Any]) -> None:
        cid = _norm_session_id(conversation_id)
        if not cid:
            return
        payload = self.ensure_conversation(cid)
        summary = copy.deepcopy(summary_payload or {})
        summary.setdefault("createdAt", _utcnow_iso())
        payload["summarySnapshot"] = summary
        payload["updatedAt"] = _utcnow_iso()
        self.save_conversation(cid, payload)

    def get_conversation_summary_snapshot(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        payload = self.get_conversation(conversation_id)
        if not isinstance(payload, dict):
            return None
        summary = payload.get("summarySnapshot")
        if not isinstance(summary, dict):
            return None
        return copy.deepcopy(summary)

    def list_conversation_compaction_snapshots(self, conversation_id: str) -> List[Dict[str, Any]]:
        payload = self.get_conversation(conversation_id)
        if not isinstance(payload, dict):
            return []
        history = payload.get("compactionHistory")
        if not isinstance(history, list):
            return []
        snapshots: List[Dict[str, Any]] = []
        for item in history:
            if isinstance(item, dict):
                snapshots.append(copy.deepcopy(item))
        return snapshots

    def append_conversation_compaction_snapshot(self, conversation_id: str, snapshot_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        cid = _norm_session_id(conversation_id)
        if not cid:
            return []
        payload = self.ensure_conversation(cid)
        history = payload.get("compactionHistory")
        if not isinstance(history, list):
            history = []
            payload["compactionHistory"] = history
        snapshot = copy.deepcopy(snapshot_payload or {})
        snapshot.setdefault("snapshotId", uuid4().hex)
        snapshot.setdefault("createdAt", _utcnow_iso())
        history.append(snapshot)
        payload["updatedAt"] = _utcnow_iso()
        self.save_conversation(cid, payload)
        return self.list_conversation_compaction_snapshots(cid)

    def save_conversation_key_facts_memory(self, conversation_id: str, key_facts_payload: Dict[str, Any], merge: bool = True) -> Dict[str, Any]:
        cid = _norm_session_id(conversation_id)
        payload = self.ensure_conversation(cid)
        existing_raw = payload.get("keyFactsMemory")
        existing: Dict[str, Any] = copy.deepcopy(existing_raw) if isinstance(existing_raw, dict) else {}
        incoming_raw: Dict[str, Any] = key_facts_payload if isinstance(key_facts_payload, dict) else {}
        incoming: Dict[str, Any] = copy.deepcopy(incoming_raw)
        if merge:
            merged: Dict[str, Any] = {}
            for key, value in existing.items():
                merged[str(key)] = value
            for key, value in incoming.items():
                key_text = str(key)
                if isinstance(value, list) and isinstance(merged.get(key_text), list):
                    merged[key_text] = list(merged.get(key_text) or []) + list(value)
                else:
                    merged[key_text] = value
            incoming = merged
        incoming.setdefault("updatedAt", _utcnow_iso())
        payload["keyFactsMemory"] = incoming
        payload["updatedAt"] = _utcnow_iso()
        self.save_conversation(cid, payload)
        return copy.deepcopy(incoming)

    def get_conversation_key_facts_memory(self, conversation_id: str) -> Dict[str, Any]:
        payload = self.get_conversation(conversation_id)
        if not isinstance(payload, dict):
            return {}
        facts = payload.get("keyFactsMemory")
        if not isinstance(facts, dict):
            return {}
        return copy.deepcopy(facts)

    def append_conversation_event(self, conversation_id: str, event_type: str, event_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        cid = _norm_session_id(conversation_id)
        if not cid:
            return None
        payload = self.ensure_conversation(cid)
        event_log = payload.get("eventLog")
        if not isinstance(event_log, list):
            event_log = []
            payload["eventLog"] = event_log

        last_seq = 0
        if event_log:
            tail = event_log[-1]
            if isinstance(tail, dict):
                try:
                    last_seq = int(tail.get("seq") or 0)
                except (TypeError, ValueError):
                    last_seq = 0

        event = {
            "seq": last_seq + 1,
            "eventId": uuid4().hex,
            "type": str(event_type or "event").strip() or "event",
            "payload": copy.deepcopy(event_payload or {}),
            "createdAt": _utcnow_iso(),
        }
        event_log.append(event)
        payload["updatedAt"] = _utcnow_iso()
        self.save_conversation(cid, payload)
        return copy.deepcopy(event)

    def list_conversation_events(self, conversation_id: str, since_seq: int = 0, limit: int = 200) -> List[Dict[str, Any]]:
        payload = self.get_conversation(conversation_id)
        if not isinstance(payload, dict):
            return []
        event_log = payload.get("eventLog")
        if not isinstance(event_log, list):
            return []

        normalized_since = max(0, int(since_seq or 0))
        normalized_limit = max(1, min(int(limit or 200), 1000))

        result: List[Dict[str, Any]] = []
        for item in event_log:
            if not isinstance(item, dict):
                continue
            try:
                seq = int(item.get("seq") or 0)
            except (TypeError, ValueError):
                seq = 0
            if seq <= normalized_since:
                continue
            result.append(copy.deepcopy(item))
            if len(result) >= normalized_limit:
                break
        return result

    # -------- Experience paths helpers (Phase 1 / Task 1.2) --------
    def get_all_partitions(self, project_path: str) -> List[Dict[str, Any]]:
        """从功能层级结果中获取所有分区的 partition_analyses 列表。"""
        key = _norm_project_path(project_path)
        with self._lock:
            hierarchy_data = self._function_hierarchy_cache.get(key)
        if not hierarchy_data:
            return []
        partition_analyses = hierarchy_data.get("partition_analyses", {})
        result: List[Dict[str, Any]] = []
        for partition_id, payload in partition_analyses.items():
            if not isinstance(payload, dict):
                continue
            item = dict(payload)
            item.setdefault("partition_id", partition_id)
            result.append(item)
        return result

    def get_partition_analysis(self, project_path: str, partition_id: str) -> Optional[Dict[str, Any]]:
        """获取指定分区的分析结果。"""
        key = _norm_project_path(project_path)
        with self._lock:
            hierarchy_data = self._function_hierarchy_cache.get(key)
        if not hierarchy_data:
            return None
        partition_analyses = hierarchy_data.get("partition_analyses", {})
        payload = partition_analyses.get(partition_id)
        if not isinstance(payload, dict):
            return payload
        item = dict(payload)
        item.setdefault("partition_id", partition_id)
        return item

    def get_path_analyses(self, project_path: str, partition_id: str) -> List[Dict[str, Any]]:
        """获取指定分区的所有路径分析。"""
        partition_data = self.get_partition_analysis(project_path, partition_id)
        if not partition_data:
            return []
        return partition_data.get("path_analyses", []) or []

    def _extract_io_summary(self, io_graph: Dict[str, Any]) -> Dict[str, List[str]]:
        """从 io_graph 中提取简单的 I/O 摘要."""
        inputs: List[str] = []
        outputs: List[str] = []
        if not isinstance(io_graph, dict):
            return {"input": inputs, "output": outputs}
        for node in io_graph.get("nodes", []) or []:
            label = str(node.get("label", "")).strip()
            ntype = node.get("type", "")
            if not label:
                continue
            if "输入" in label or ntype == "input":
                inputs.append(label)
            if "输出" in label or ntype == "output":
                outputs.append(label)
        return {"input": inputs, "output": outputs}

    def _graph_summary(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {"exists": False, "node_count": 0, "edge_count": 0}
        nodes = payload.get("nodes") or []
        edges = payload.get("edges") or []
        node_count = len(nodes) if isinstance(nodes, list) else 0
        edge_count = len(edges) if isinstance(edges, list) else 0
        return {
            "exists": bool(node_count or edge_count),
            "node_count": node_count,
            "edge_count": edge_count,
        }

    def _build_constraints_structured_from_path(self, path_payload: Dict[str, Any], io_summary: Dict[str, List[str]]) -> Dict[str, Any]:
        raw_cfg = path_payload.get("cfg")
        raw_dfg = path_payload.get("dfg")
        raw_io_graph = path_payload.get("io_graph")
        raw_input_info = path_payload.get("input_info")
        raw_output_info = path_payload.get("output_info")
        cfg_payload: Dict[str, Any] = raw_cfg if isinstance(raw_cfg, dict) else {}
        dfg_payload: Dict[str, Any] = raw_dfg if isinstance(raw_dfg, dict) else {}
        io_graph_payload: Dict[str, Any] = raw_io_graph if isinstance(raw_io_graph, dict) else {}
        input_info: Dict[str, Any] = raw_input_info if isinstance(raw_input_info, dict) else {}
        output_info: Dict[str, Any] = raw_output_info if isinstance(raw_output_info, dict) else {}
        explain_markdown = str(path_payload.get("cfg_dfg_explain_md") or "").strip()

        cfg_summary = self._graph_summary(cfg_payload)
        dfg_summary = self._graph_summary(dfg_payload)
        io_graph_summary = self._graph_summary(io_graph_payload)

        types: List[str] = []
        if cfg_summary["exists"]:
            types.append("cfg")
        if dfg_summary["exists"]:
            types.append("dfg")
        if io_graph_summary["exists"]:
            types.append("io_graph")
        if input_info:
            types.append("input_info")
        if output_info:
            types.append("output_info")
        if explain_markdown:
            types.append("constraint_explain")

        return {
            "version": "constraints.v1",
            "types": types,
            "cfg": {
                "summary": cfg_summary,
                "input_info_keys": [str(key) for key in input_info.keys()],
                "output_info_keys": [str(key) for key in output_info.keys()],
            },
            "dfg": {"summary": dfg_summary},
            "io_graph": {
                "summary": io_graph_summary,
                "inputs": io_summary.get("input") or [],
                "outputs": io_summary.get("output") or [],
            },
            "input_info": input_info,
            "output_info": output_info,
            "constraint_explain": {
                "exists": bool(explain_markdown),
                "markdown": explain_markdown,
            },
        }

    def _build_what_how_from_path(self, partition_id: str, path_payload: Dict[str, Any], function_chain: List[str], io_summary: Dict[str, List[str]]) -> Dict[str, str]:
        path_name = str(path_payload.get("path_name") or f"路径 {partition_id}").strip()
        path_description = str(path_payload.get("path_description") or "").strip()
        what = f"功能分区 {partition_id} 的路径“{path_name}”"
        if path_description:
            what = f"{what}，能力描述：{path_description}"

        chain = " -> ".join([str(item).strip() for item in function_chain if str(item).strip()])
        inputs = io_summary.get("input") or []
        outputs = io_summary.get("output") or []
        io_desc = f"输入: {', '.join(inputs) if inputs else '未知'}；输出: {', '.join(outputs) if outputs else '未知'}"
        how = f"调用链: {chain if chain else '未提供'}；{io_desc}"
        return {"what": what, "how": how}

    def _normalize_absolute_file_path(self, project_path: str, raw_file_path: Any) -> str:
        text = str(raw_file_path or '').strip()
        if not text:
            return ''
        normalized = os.path.normpath(text)
        if os.path.isabs(normalized):
            return normalized
        project_root = _norm_project_path(project_path)
        if project_root:
            return os.path.normpath(os.path.abspath(os.path.join(project_root, normalized)))
        return os.path.normpath(os.path.abspath(normalized))

    def _derive_file_path_from_fqn(self, project_path: str, fqn: Any) -> str:
        text = str(fqn or '').strip()
        segments = [segment for segment in text.split('.') if segment]
        if len(segments) < 3:
            return ''

        candidates: List[str] = []
        module_candidate = os.path.join(project_path, *segments[:-2]) + '.py'
        candidates.append(module_candidate)
        package_init_candidate = os.path.join(project_path, *segments[:-2], '__init__.py')
        candidates.append(package_init_candidate)
        function_candidate = os.path.join(project_path, *segments[:-1]) + '.py'
        candidates.append(function_candidate)
        for candidate in candidates:
            absolute_candidate = self._normalize_absolute_file_path(project_path, candidate)
            if absolute_candidate and os.path.isfile(absolute_candidate):
                return absolute_candidate
        return ''

    def _load_project_library_graph_data(self, project_path: str) -> Optional[Dict[str, Any]]:
        try:
            from data.project_library_storage import ProjectLibraryStorage
        except Exception:
            return None
        storage = ProjectLibraryStorage()
        return storage.load_graph_data(project_path)

    def _load_project_library_hierarchy_data(self, project_path: str) -> Optional[Dict[str, Any]]:
        try:
            from data.project_library_storage import ProjectLibraryStorage
        except Exception:
            return None
        storage = ProjectLibraryStorage()
        return storage.load_function_hierarchy(project_path)

    def _search_partition_file_candidate(self, partition_folders: List[str], method_name: str) -> str:
        simple_name = str(method_name or '').strip()
        if not simple_name:
            return ''
        method_pattern = re.compile(rf"^\s*def\s+{re.escape(simple_name)}\s*\(")
        class_pattern = re.compile(rf"^\s*class\s+{re.escape(simple_name)}\b")
        for folder in partition_folders:
            normalized_folder = os.path.normpath(str(folder or '').strip())
            if not normalized_folder or not os.path.isdir(normalized_folder):
                continue
            for root, _, files in os.walk(normalized_folder):
                for filename in files:
                    if not filename.endswith('.py'):
                        continue
                    candidate = os.path.join(root, filename)
                    try:
                        with open(candidate, 'r', encoding='utf-8', errors='replace') as handle:
                            for line in handle:
                                if method_pattern.search(line) or class_pattern.search(line):
                                    return os.path.normpath(os.path.abspath(candidate))
                    except Exception:
                        continue
        return ''

    def _default_partition_absolute_path(self, partition_id: str, resolver: Optional[Dict[str, Any]]) -> str:
        if not isinstance(resolver, dict):
            return ''
        folders = resolver.get('partition_folders', {}).get(partition_id) or []
        for folder in folders:
            normalized_folder = os.path.normpath(str(folder or '').strip())
            if not normalized_folder:
                continue
            if os.path.isfile(normalized_folder):
                return normalized_folder
            if os.path.isdir(normalized_folder):
                for root, _, files in os.walk(normalized_folder):
                    for filename in files:
                        if filename.endswith('.py'):
                            return os.path.normpath(os.path.abspath(os.path.join(root, filename)))
                return normalized_folder
        project_root = os.path.normpath(str(resolver.get('project_path') or '').strip())
        return project_root if project_root else ''

    @staticmethod
    def _build_exact_symbol_metadata(*, symbol_kind: str, absolute_file_path: str, class_name: str = '', callable_name: str = '', owner_expression: str = '', resolved_signature: str = '', line_start: Optional[int] = None, line_end: Optional[int] = None, ownership_resolution: str = 'graph_node') -> Dict[str, Any]:
        return {
            'symbol_kind': symbol_kind,
            'class_name': class_name,
            'callable_name': callable_name,
            'owner_expression': owner_expression,
            'resolved_signature': resolved_signature,
            'absolute_file_path': absolute_file_path,
            'line_start': line_start,
            'line_end': line_end,
            'ownership_resolution': ownership_resolution,
            'ownership_precision': 'exact',
        }

    @staticmethod
    def _build_non_exact_symbol_metadata(method_signature: str, absolute_file_path: str, *, ownership_resolution: str, ownership_precision: str) -> Dict[str, Any]:
        symbol = str(method_signature or '').strip()
        owner_expression = ''
        class_name = ''
        callable_name = symbol
        symbol_kind = 'unresolved_expression'
        if '.' in symbol:
            owner_expression, callable_name = symbol.rsplit('.', 1)
            if owner_expression and owner_expression[:1].isupper():
                class_name = owner_expression
                symbol_kind = 'method_candidate' if ownership_precision == 'heuristic' else 'unresolved_expression'
            else:
                symbol_kind = 'unresolved_expression'
        else:
            callable_name = symbol
            symbol_kind = 'function_candidate' if ownership_precision == 'heuristic' else 'unresolved_expression'
        return {
            'symbol_kind': symbol_kind,
            'class_name': class_name,
            'callable_name': callable_name,
            'owner_expression': owner_expression,
            'resolved_signature': symbol,
            'absolute_file_path': absolute_file_path,
            'line_start': None,
            'line_end': None,
            'ownership_resolution': ownership_resolution,
            'ownership_precision': ownership_precision,
        }

    def _build_method_file_path_resolver(self, project_path: str, hierarchy_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        normalized_project_path = _norm_project_path(project_path)
        hierarchy_payload = hierarchy_data or self.get_function_hierarchy(normalized_project_path) or self._load_project_library_hierarchy_data(normalized_project_path) or {}
        graph_data = self.get_main_analysis(normalized_project_path) or self._load_project_library_graph_data(normalized_project_path) or {}

        exact_map: Dict[str, Dict[str, Any]] = {}
        simple_map: Dict[str, List[Dict[str, Any]]] = {}
        partition_methods: Dict[str, List[str]] = {}
        partition_folders: Dict[str, List[str]] = {}

        hierarchy_functions = ((hierarchy_payload.get('hierarchy') or {}).get('layer1_functions') or []) if isinstance(hierarchy_payload, dict) else []
        for item in hierarchy_functions:
            if not isinstance(item, dict):
                continue
            partition_id = str(item.get('partition_id') or '').strip()
            if not partition_id:
                continue
            methods = [str(method).strip() for method in (item.get('methods') or []) if str(method).strip()]
            if methods:
                partition_methods[partition_id] = methods
            folders = [self._normalize_absolute_file_path(normalized_project_path, folder) for folder in (item.get('folders') or []) if str(folder).strip()]
            folders = [folder for folder in folders if folder]
            if folders:
                partition_folders[partition_id] = folders

        partition_analyses = (hierarchy_payload.get('partition_analyses') or {}) if isinstance(hierarchy_payload, dict) else {}
        for partition_id, payload in partition_analyses.items():
            if not isinstance(payload, dict):
                continue
            methods = partition_methods.setdefault(str(partition_id), [])
            for fqn_info in payload.get('fqns') or []:
                if not isinstance(fqn_info, dict):
                    continue
                method_signature = str(fqn_info.get('method_signature') or '').strip()
                if method_signature and method_signature not in methods:
                    methods.append(method_signature)
                derived_path = self._derive_file_path_from_fqn(normalized_project_path, fqn_info.get('fqn'))
                if method_signature and derived_path:
                    if method_signature not in exact_map:
                        exact_map[method_signature] = self._build_non_exact_symbol_metadata(
                            method_signature,
                            derived_path,
                            ownership_resolution='fqn_derived',
                            ownership_precision='heuristic',
                        )

        for node in graph_data.get('nodes', []) or []:
            node_data = node.get('data') if isinstance(node, dict) and isinstance(node.get('data'), dict) else node if isinstance(node, dict) else {}
            if not isinstance(node_data, dict):
                continue
            raw_type = str(node_data.get('type') or '').strip().lower()
            if raw_type not in {'method', 'function', 'class'}:
                continue
            absolute_path = self._normalize_absolute_file_path(normalized_project_path, node_data.get('file') or node_data.get('file_path'))
            if not absolute_path:
                continue
            line_start_raw = node_data.get('line') or node_data.get('line_start') or node_data.get('startLine')
            line_end_raw = node_data.get('line_end') or node_data.get('endLine') or line_start_raw
            line_start = int(line_start_raw) if isinstance(line_start_raw, (int, float)) else None
            line_end = int(line_end_raw) if isinstance(line_end_raw, (int, float)) else line_start
            signature_candidates = [
                str(node_data.get('signature') or '').strip(),
                str(node_data.get('id') or '').strip(),
            ]
            class_name = str(node_data.get('class_name') or '').strip()
            label = str(node_data.get('label') or node_data.get('name') or '').strip()
            if label:
                signature_candidates.append(label)
            if class_name and label:
                signature_candidates.append(f'{class_name}.{label}')
            simple_name = label or (signature_candidates[0].split('.')[-1] if signature_candidates and signature_candidates[0] else '')
            if raw_type == 'method':
                metadata = self._build_exact_symbol_metadata(
                    symbol_kind='method',
                    absolute_file_path=absolute_path,
                    class_name=class_name,
                    callable_name=label,
                    owner_expression=class_name,
                    resolved_signature=signature_candidates[0] or f'{class_name}.{label}',
                    line_start=line_start,
                    line_end=line_end,
                    ownership_resolution='graph_node',
                )
            elif raw_type == 'function':
                metadata = self._build_exact_symbol_metadata(
                    symbol_kind='function',
                    absolute_file_path=absolute_path,
                    callable_name=label,
                    resolved_signature=signature_candidates[0] or label,
                    line_start=line_start,
                    line_end=line_end,
                    ownership_resolution='graph_node',
                )
            else:
                metadata = self._build_exact_symbol_metadata(
                    symbol_kind='class',
                    absolute_file_path=absolute_path,
                    class_name=label or class_name,
                    callable_name=label or class_name,
                    owner_expression=label or class_name,
                    resolved_signature=signature_candidates[0] or label or class_name,
                    line_start=line_start,
                    line_end=line_end,
                    ownership_resolution='graph_node',
                )
            for signature in signature_candidates:
                if signature:
                    exact_map[signature] = dict(metadata)
            if simple_name:
                entry = dict(metadata)
                entry['signature'] = signature_candidates[0] or simple_name
                simple_map.setdefault(simple_name, []).append(entry)

        return {
            'project_path': normalized_project_path,
            'exact_map': exact_map,
            'simple_map': simple_map,
            'partition_methods': partition_methods,
            'partition_folders': partition_folders,
            'search_cache': {},
        }

    def _resolve_method_ownership(self, method_signature: str, partition_id: str, resolver: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        symbol = str(method_signature or '').strip()
        if not symbol or not isinstance(resolver, dict):
            return self._build_non_exact_symbol_metadata(symbol, '', ownership_resolution='missing_resolver', ownership_precision='fallback')
        exact_map = resolver.get('exact_map') or {}
        if symbol in exact_map:
            return dict(exact_map[symbol] or {})

        simple_name = symbol.split('.')[-1]
        partition_method_candidates = [
            candidate for candidate in (resolver.get('partition_methods', {}).get(partition_id) or [])
            if candidate == symbol or candidate.endswith(f'.{symbol}') or candidate.split('.')[-1] == simple_name
        ]
        for candidate in partition_method_candidates:
            if candidate in exact_map:
                metadata = dict(exact_map[candidate] or {})
                metadata['ownership_resolution'] = 'partition_candidate_exact'
                return metadata

        simple_candidates = resolver.get('simple_map', {}).get(simple_name) or []
        prioritized: List[Dict[str, Any]] = []
        for item in simple_candidates:
            if not isinstance(item, dict):
                continue
            signature = str(item.get('signature') or '').strip()
            absolute_file_path = str(item.get('absolute_file_path') or '').strip()
            if not absolute_file_path:
                continue
            if partition_method_candidates and signature not in partition_method_candidates:
                continue
            candidate_metadata = dict(item)
            if all(str(existing.get('absolute_file_path') or '') != absolute_file_path for existing in prioritized):
                prioritized.append(candidate_metadata)
        if prioritized:
            if len(prioritized) == 1:
                metadata = dict(prioritized[0])
                metadata['ownership_resolution'] = 'simple_name_unique'
                metadata['ownership_precision'] = 'heuristic'
                return metadata
            metadata = dict(prioritized[0])
            metadata['ownership_resolution'] = 'simple_name_ambiguous'
            metadata['ownership_precision'] = 'heuristic'
            return metadata

        raw_search_cache = resolver.get('search_cache')
        search_cache: Dict[Any, Any] = raw_search_cache if isinstance(raw_search_cache, dict) else {}
        cache_key = (partition_id, simple_name)
        if cache_key in search_cache:
            cached_path = str(search_cache[cache_key] or '')
            return self._build_non_exact_symbol_metadata(symbol, cached_path, ownership_resolution='partition_source_scan_cached', ownership_precision='heuristic' if cached_path else 'fallback')
        searched = self._search_partition_file_candidate(resolver.get('partition_folders', {}).get(partition_id) or [], simple_name)
        if not searched:
            searched = self._default_partition_absolute_path(partition_id, resolver)
        search_cache[cache_key] = searched
        resolver['search_cache'] = search_cache
        return self._build_non_exact_symbol_metadata(
            symbol,
            searched,
            ownership_resolution='partition_source_scan' if searched and searched != self._default_partition_absolute_path(partition_id, resolver) else 'partition_anchor_fallback',
            ownership_precision='heuristic' if searched and searched != self._default_partition_absolute_path(partition_id, resolver) else 'fallback',
        )

    @staticmethod
    def _normalize_function_chain(function_chain: Any) -> List[str]:
        normalized: List[str] = []
        for item in function_chain or []:
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized

    @staticmethod
    def _display_method_name(method_signature: str) -> str:
        normalized = str(method_signature or '').strip()
        if not normalized:
            return ''
        return normalized.split('.')[-1]

    def _infer_chain_role(self, method_signature: str, step_index: int, function_chain: List[str], path_payload: Dict[str, Any]) -> str:
        if not function_chain:
            return 'path_node'

        raw_highlight_config = path_payload.get('highlight_config')
        highlight_config: Dict[str, Any] = raw_highlight_config if isinstance(raw_highlight_config, dict) else {}
        main_method = str(highlight_config.get('main_method') or '').strip()
        intermediate_methods = {
            str(item).strip() for item in (highlight_config.get('intermediate_methods') or []) if str(item).strip()
        }
        direct_calls = set()
        raw_call_chain_analysis = path_payload.get('call_chain_analysis')
        call_chain_analysis: Dict[str, Any] = raw_call_chain_analysis if isinstance(raw_call_chain_analysis, dict) else {}
        for pair in call_chain_analysis.get('direct_calls') or []:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                direct_calls.add((str(pair[0]).strip(), str(pair[1]).strip()))

        if main_method and method_signature == main_method:
            return 'main_method'
        if method_signature in intermediate_methods:
            return 'intermediate_method'
        if step_index == 0:
            return 'entry_method'
        if step_index == len(function_chain) - 1:
            return 'leaf_method'

        prev_method = function_chain[step_index - 1] if step_index > 0 else ''
        if prev_method and (prev_method, method_signature) in direct_calls:
            return 'direct_callee'
        return 'path_node'

    def _build_method_path_entries(self, path_payload: Dict[str, Any], function_chain: List[str], project_path: str = '', resolver: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        partition_id = str(path_payload.get('partition_id') or '').strip()
        for idx, method_signature in enumerate(function_chain):
            prev_method = function_chain[idx - 1] if idx > 0 else None
            next_method = function_chain[idx + 1] if idx + 1 < len(function_chain) else None
            ownership = self._resolve_method_ownership(method_signature, partition_id, resolver)
            entries.append(
                {
                    'step_index': idx + 1,
                    'method_signature': method_signature,
                    'display_name': self._display_method_name(method_signature),
                    'chain_role': self._infer_chain_role(method_signature, idx, function_chain, path_payload),
                    'is_entry': idx == 0,
                    'is_leaf': idx == len(function_chain) - 1,
                    'prev_method': prev_method,
                    'next_method': next_method,
                    'path_to_method': ' -> '.join(function_chain[: idx + 1]),
                    'absolute_file_path': str(ownership.get('absolute_file_path') or ''),
                    'symbol_kind': str(ownership.get('symbol_kind') or ''),
                    'class_name': str(ownership.get('class_name') or ''),
                    'callable_name': str(ownership.get('callable_name') or ''),
                    'owner_expression': str(ownership.get('owner_expression') or ''),
                    'resolved_signature': str(ownership.get('resolved_signature') or method_signature),
                    'line_start': ownership.get('line_start'),
                    'line_end': ownership.get('line_end'),
                    'ownership_resolution': str(ownership.get('ownership_resolution') or ''),
                    'ownership_precision': str(ownership.get('ownership_precision') or ''),
                }
            )
        return entries

    def _build_path_ownership_coverage(self, method_path_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(method_path_entries)
        exact = 0
        heuristic = 0
        fallback = 0
        non_empty_absolute = 0
        exact_kinds = {'method', 'function', 'class'}
        for entry in method_path_entries:
            precision = str(entry.get('ownership_precision') or '').strip().lower()
            symbol_kind = str(entry.get('symbol_kind') or '').strip().lower()
            absolute_file_path = str(entry.get('absolute_file_path') or '').strip()
            if absolute_file_path:
                non_empty_absolute += 1
            if precision == 'exact' and symbol_kind in exact_kinds:
                exact += 1
            elif precision == 'heuristic':
                heuristic += 1
            else:
                fallback += 1
        unresolved = max(total - exact - heuristic - fallback, 0)
        return {
            'total_method_entries': total,
            'exact_owner_count': exact,
            'heuristic_owner_count': heuristic,
            'fallback_owner_count': fallback,
            'unresolved_owner_count': unresolved,
            'non_empty_absolute_path_count': non_empty_absolute,
            'exact_owner_percent': round((exact / total) * 100, 2) if total else 0.0,
            'heuristic_owner_percent': round((heuristic / total) * 100, 2) if total else 0.0,
            'fallback_owner_percent': round((fallback / total) * 100, 2) if total else 0.0,
            'non_empty_absolute_path_percent': round((non_empty_absolute / total) * 100, 2) if total else 0.0,
        }

    def _build_chained_call_path(self, path_payload: Dict[str, Any], function_chain: List[str], method_path_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        raw_highlight_config = path_payload.get('highlight_config')
        raw_call_chain_analysis = path_payload.get('call_chain_analysis')
        highlight_config: Dict[str, Any] = raw_highlight_config if isinstance(raw_highlight_config, dict) else {}
        call_chain_analysis: Dict[str, Any] = raw_call_chain_analysis if isinstance(raw_call_chain_analysis, dict) else {}
        direct_calls = set()
        for pair in call_chain_analysis.get('direct_calls') or []:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                direct_calls.add((str(pair[0]).strip(), str(pair[1]).strip()))

        path_links: List[Dict[str, Any]] = []
        for idx in range(len(function_chain) - 1):
            caller = function_chain[idx]
            callee = function_chain[idx + 1]
            caller_path_entry = method_path_entries[idx] if idx < len(method_path_entries) else {}
            callee_path_entry = method_path_entries[idx + 1] if idx + 1 < len(method_path_entries) else {}
            path_links.append(
                {
                    'step_index': idx + 1,
                    'caller': caller,
                    'callee': callee,
                    'caller_path': ' -> '.join(function_chain[: idx + 1]),
                    'callee_path': ' -> '.join(function_chain[: idx + 2]),
                    'caller_absolute_path': str(caller_path_entry.get('absolute_file_path') or ''),
                    'callee_absolute_path': str(callee_path_entry.get('absolute_file_path') or ''),
                    'link_type': 'adjacent_path_step',
                    'is_direct_call': (caller, callee) in direct_calls if direct_calls else None,
                }
            )

        absolute_file_paths: List[str] = []
        for entry in method_path_entries:
            absolute_file_path = str(entry.get('absolute_file_path') or '').strip()
            if absolute_file_path and absolute_file_path not in absolute_file_paths:
                absolute_file_paths.append(absolute_file_path)

        return {
            'chain_version': 'callpath.v1',
            'path_methods': list(function_chain),
            'method_count': len(function_chain),
            'path_links': path_links,
            'main_method': str(highlight_config.get('main_method') or (function_chain[0] if function_chain else '')).strip(),
            'intermediate_methods': [
                str(item).strip() for item in (highlight_config.get('intermediate_methods') or function_chain[1:-1]) if str(item).strip()
            ],
            'leaf_node': function_chain[-1] if function_chain else '',
            'entry_method': function_chain[0] if function_chain else '',
            'chain_text': ' -> '.join(function_chain),
            'absolute_file_paths': absolute_file_paths,
            'primary_absolute_path': absolute_file_paths[0] if absolute_file_paths else '',
            'explanation': str(highlight_config.get('explanation') or '').strip(),
            'method_path_entries': method_path_entries,
        }

    def _enrich_experience_path_payload(self, path_payload: Dict[str, Any], project_path: str = '', resolver: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        enriched = dict(path_payload or {})
        function_chain = self._normalize_function_chain(enriched.get('function_chain') or enriched.get('path') or [])
        enriched['function_chain'] = function_chain
        enriched['path'] = list(function_chain)
        normalized_project_path = _norm_project_path(project_path or enriched.get('project_path') or '')
        partition_id = str(enriched.get('partition_id') or '').strip()

        method_path_entries = enriched.get('method_path_entries')
        if not isinstance(method_path_entries, list) or len(method_path_entries) != len(function_chain):
            method_path_entries = self._build_method_path_entries(enriched, function_chain, project_path=normalized_project_path, resolver=resolver)
        else:
            rebuilt_entries: List[Dict[str, Any]] = []
            for idx, item in enumerate(method_path_entries):
                current = dict(item) if isinstance(item, dict) else {}
                method_signature = function_chain[idx] if idx < len(function_chain) else str(current.get('method_signature') or '')
                current['method_signature'] = method_signature
                ownership = self._resolve_method_ownership(method_signature, partition_id, resolver)
                current['absolute_file_path'] = current.get('absolute_file_path') or str(ownership.get('absolute_file_path') or '')
                current['symbol_kind'] = current.get('symbol_kind') or str(ownership.get('symbol_kind') or '')
                current['class_name'] = current.get('class_name') or str(ownership.get('class_name') or '')
                current['callable_name'] = current.get('callable_name') or str(ownership.get('callable_name') or '')
                current['owner_expression'] = current.get('owner_expression') or str(ownership.get('owner_expression') or '')
                current['resolved_signature'] = current.get('resolved_signature') or str(ownership.get('resolved_signature') or method_signature)
                current['line_start'] = current.get('line_start') if current.get('line_start') is not None else ownership.get('line_start')
                current['line_end'] = current.get('line_end') if current.get('line_end') is not None else ownership.get('line_end')
                current['ownership_resolution'] = current.get('ownership_resolution') or str(ownership.get('ownership_resolution') or '')
                current['ownership_precision'] = current.get('ownership_precision') or str(ownership.get('ownership_precision') or '')
                rebuilt_entries.append(current)
            method_path_entries = rebuilt_entries
        enriched['method_path_entries'] = method_path_entries

        chained_call_path = enriched.get('chained_call_path')
        if not isinstance(chained_call_path, dict):
            chained_call_path = {}
        expected_leaf = function_chain[-1] if function_chain else ''
        existing_methods = chained_call_path.get('path_methods') or []
        existing_links = chained_call_path.get('path_links') or []
        should_rebuild_chain = (
            chained_call_path.get('chain_version') != 'callpath.v1'
            or len(existing_methods) != len(function_chain)
            or len(existing_links) != max(len(function_chain) - 1, 0)
            or chained_call_path.get('leaf_node') != expected_leaf
            or chained_call_path.get('entry_method') != (function_chain[0] if function_chain else '')
            or chained_call_path.get('chain_text') != ' -> '.join(function_chain)
        )
        if should_rebuild_chain:
            chained_call_path = self._build_chained_call_path(enriched, function_chain, method_path_entries)
        enriched['chained_call_path'] = chained_call_path

        fallback_absolute_path = self._default_partition_absolute_path(partition_id, resolver)
        chain_primary_path = str((chained_call_path or {}).get('primary_absolute_path') or '').strip()
        effective_fallback_absolute_path = chain_primary_path or fallback_absolute_path
        if effective_fallback_absolute_path:
            normalized_entries: List[Dict[str, Any]] = []
            for item in method_path_entries:
                current = dict(item) if isinstance(item, dict) else {}
                if not str(current.get('absolute_file_path') or '').strip():
                    current['absolute_file_path'] = effective_fallback_absolute_path
                normalized_entries.append(current)
            method_path_entries = normalized_entries
            enriched['method_path_entries'] = method_path_entries
            chained_call_path = self._build_chained_call_path(enriched, function_chain, method_path_entries)
            enriched['chained_call_path'] = chained_call_path

        absolute_file_paths: List[str] = []
        for entry in method_path_entries:
            absolute_file_path = str(entry.get('absolute_file_path') or '').strip()
            if absolute_file_path and absolute_file_path not in absolute_file_paths:
                absolute_file_paths.append(absolute_file_path)
        enriched['absolute_file_paths'] = absolute_file_paths
        enriched['primary_absolute_path'] = absolute_file_paths[0] if absolute_file_paths else ''
        enriched['ownership_coverage'] = self._build_path_ownership_coverage(method_path_entries)
        enriched['project_path'] = normalized_project_path or enriched.get('project_path') or ''
        return enriched

    def _convert_path_analyses_to_experience_paths(
        self, path_analyses: List[Dict[str, Any]], partition_id: str, project_path: str = '', resolver: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """将路径分析数据转换为经验路径格式（保留 rich constraints 字段）。"""
        experience_paths: List[Dict[str, Any]] = []
        for idx, pa in enumerate(path_analyses or []):
            path_id = f"{partition_id}_path_{idx}"
            leaf_node = pa.get("leaf_node", "")
            path_nodes = self._normalize_function_chain(pa.get("function_chain") or pa.get("path") or [])
            io_summary = self._extract_io_summary(pa.get("io_graph", {}))
            semantics = pa.get("semantics") or {}
            what_how = self._build_what_how_from_path(partition_id, pa, path_nodes, io_summary)
            constraints_structured = self._build_constraints_structured_from_path(pa, io_summary)

            base_payload = {
                    "path_id": path_id,
                    "partition_id": partition_id,
                    "path_index": pa.get("path_index", idx),
                    "path_name": pa.get("path_name") or f"路径{idx + 1}",
                    "path_description": pa.get("path_description") or "",
                    "function_chain": path_nodes,
                    "path": path_nodes,
                    "leaf_node": leaf_node,
                    "io_summary": io_summary,
                    "semantics": semantics,
                    "cfg": pa.get("cfg"),
                    "dfg": pa.get("dfg"),
                    "io_graph": pa.get("io_graph"),
                    "input_info": pa.get("input_info") if isinstance(pa.get("input_info"), dict) else {},
                    "output_info": pa.get("output_info") if isinstance(pa.get("output_info"), dict) else {},
                    "cfg_dfg_explain_md": pa.get("cfg_dfg_explain_md") or "",
                    "what": what_how["what"],
                    "how": what_how["how"],
                    "constraints": constraints_structured.get("types") or [],
                    "constraints_structured": constraints_structured,
                }
            experience_paths.append(self._enrich_experience_path_payload(base_payload, project_path=project_path, resolver=resolver))
        return experience_paths

    def _convert_paths_map_to_experience_paths(
        self,
        paths_map: Dict[str, Any],
        partition_id: str,
        project_path: str = '',
        resolver: Optional[Dict[str, Any]] = None,
        max_paths: int = 12,
    ) -> List[Dict[str, Any]]:
        """把结构路径缓存(paths_map)补齐为经验路径，避免无深分析时经验库为空。"""
        if not isinstance(paths_map, dict) or not paths_map:
            return []

        flattened: List[Dict[str, Any]] = []
        for leaf_node, paths in paths_map.items():
            for path_index, raw_path in enumerate(paths or []):
                normalized_path = [str(item).strip() for item in (raw_path or []) if str(item).strip()]
                if not normalized_path:
                    continue
                flattened.append(
                    {
                        'leaf_node': str(leaf_node or normalized_path[-1]),
                        'path_index': path_index,
                        'path': normalized_path,
                    }
                )

        if not flattened:
            return []

        results: List[Dict[str, Any]] = []
        seen_signatures: set[tuple[str, ...]] = set()
        for idx, candidate in enumerate(flattened[:max(1, max_paths)]):
            candidate_payload: Dict[str, Any] = candidate if isinstance(candidate, dict) else {}
            path_nodes = list(candidate_payload.get('path') or [])
            signature = tuple(path_nodes)
            if not signature or signature in seen_signatures:
                continue
            seen_signatures.add(signature)

            path_name = f"结构路径 {len(results) + 1}"
            path_payload = {
                'path_name': path_name,
                'path_description': '基于分区结构路径缓存导出的调用链（可按需补齐深分析）',
            }
            io_summary = {'input': [], 'output': []}
            what_how = self._build_what_how_from_path(partition_id, path_payload, path_nodes, io_summary)
            constraints_structured = self._build_constraints_structured_from_path({}, io_summary)

            base_payload = {
                    'path_id': f"{partition_id}_structural_{len(results)}",
                    'partition_id': partition_id,
                    'path_index': candidate_payload.get('path_index', idx),
                    'path_name': path_name,
                    'path_description': path_payload['path_description'],
                    'function_chain': path_nodes,
                    'path': path_nodes,
                    'leaf_node': candidate_payload.get('leaf_node') or (path_nodes[-1] if path_nodes else ''),
                    'io_summary': io_summary,
                    'semantics': {},
                    'cfg': None,
                    'dfg': None,
                    'io_graph': None,
                    'input_info': {},
                    'output_info': {},
                    'cfg_dfg_explain_md': '',
                    'what': what_how['what'],
                    'how': what_how['how'],
                    'constraints': constraints_structured.get('types') or [],
                    'constraints_structured': constraints_structured,
                }
            results.append(self._enrich_experience_path_payload(base_payload, project_path=project_path, resolver=resolver))
        return results

    def _build_partition_experience_paths(self, project_path: str, partition_id: str, partition_data: Dict[str, Any], resolver: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        path_analyses = (partition_data or {}).get('path_analyses', []) or []
        converted_paths = self._convert_path_analyses_to_experience_paths(path_analyses, partition_id, project_path=project_path, resolver=resolver)

        max_structural = max(1, int(os.getenv('FH_EXPERIENCE_STRUCTURAL_MAX_PATHS', '12')))
        structural_paths = self._convert_paths_map_to_experience_paths(
            (partition_data or {}).get('paths_map') or {},
            partition_id,
            project_path=project_path,
            resolver=resolver,
            max_paths=max_structural,
        )

        seen_signatures: set[tuple[str, ...]] = set()
        merged: List[Dict[str, Any]] = []
        for item in converted_paths + structural_paths:
            signature = tuple(str(seg).strip() for seg in (item.get('path') or []) if str(seg).strip())
            if signature and signature in seen_signatures:
                continue
            if signature:
                seen_signatures.add(signature)
            merged.append(item)
        return merged


    def get_experience_paths(self, project_path: str, partition_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取经验路径列表（用于匹配 / 持久化）。
        """
        key = _norm_project_path(project_path)
        with self._lock:
            hierarchy_data = self._function_hierarchy_cache.get(key)
        if not hierarchy_data:
            return []

        resolver = self._build_method_file_path_resolver(key, hierarchy_data)

        partition_analyses = hierarchy_data.get("partition_analyses", {})
        if partition_id:
            partition_data = partition_analyses.get(partition_id) or {}
            return self._build_partition_experience_paths(key, partition_id, partition_data, resolver=resolver)

        all_paths: List[Dict[str, Any]] = []
        for pid, pdata in partition_analyses.items():
            all_paths.extend(self._build_partition_experience_paths(key, pid, pdata or {}, resolver=resolver))
        return all_paths


    def load_experience_paths_from_storage(self, project_path: str) -> Optional[List[Dict[str, Any]]]:
        """
        从 JSON 持久化文件加载经验路径（Phase 1 / Task 1.2）。
        """
        try:
            from data.experience_path_storage import ExperiencePathStorage
        except Exception:
            return None
        storage = ExperiencePathStorage()
        data = storage.load_experience_paths(project_path)
        if not data:
            return None
        resolver = self._build_method_file_path_resolver(project_path)
        all_paths: List[Dict[str, Any]] = []
        for p in data.get("partitions", []) or []:
            for path_payload in p.get("paths", []) or []:
                if isinstance(path_payload, dict):
                    all_paths.append(self._enrich_experience_path_payload(path_payload, project_path=project_path, resolver=resolver))
        return all_paths


_global_data_accessor: Optional[DataAccessor] = None
_global_lock = threading.Lock()


def get_data_accessor() -> DataAccessor:
    """获取全局 DataAccessor（单例）。"""
    global _global_data_accessor
    if _global_data_accessor is None:
        with _global_lock:
            if _global_data_accessor is None:
                _global_data_accessor = DataAccessor()
    return _global_data_accessor
