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
        cfg_payload = path_payload.get("cfg") if isinstance(path_payload.get("cfg"), dict) else {}
        dfg_payload = path_payload.get("dfg") if isinstance(path_payload.get("dfg"), dict) else {}
        io_graph_payload = path_payload.get("io_graph") if isinstance(path_payload.get("io_graph"), dict) else {}
        input_info = path_payload.get("input_info") if isinstance(path_payload.get("input_info"), dict) else {}
        output_info = path_payload.get("output_info") if isinstance(path_payload.get("output_info"), dict) else {}
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

    def _convert_path_analyses_to_experience_paths(
        self, path_analyses: List[Dict[str, Any]], partition_id: str
    ) -> List[Dict[str, Any]]:
        """将路径分析数据转换为经验路径格式（保留 rich constraints 字段）。"""
        experience_paths: List[Dict[str, Any]] = []
        for idx, pa in enumerate(path_analyses or []):
            path_id = f"{partition_id}_path_{idx}"
            leaf_node = pa.get("leaf_node", "")
            path_nodes = pa.get("function_chain") or pa.get("path") or []
            io_summary = self._extract_io_summary(pa.get("io_graph", {}))
            semantics = pa.get("semantics") or {}
            what_how = self._build_what_how_from_path(partition_id, pa, path_nodes, io_summary)
            constraints_structured = self._build_constraints_structured_from_path(pa, io_summary)

            experience_paths.append(
                {
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
            )
        return experience_paths

    def _convert_paths_map_to_experience_paths(
        self,
        paths_map: Dict[str, Any],
        partition_id: str,
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
            path_nodes = list(candidate.get('path') or [])
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

            results.append(
                {
                    'path_id': f"{partition_id}_structural_{len(results)}",
                    'partition_id': partition_id,
                    'path_index': candidate.get('path_index', idx),
                    'path_name': path_name,
                    'path_description': path_payload['path_description'],
                    'function_chain': path_nodes,
                    'path': path_nodes,
                    'leaf_node': candidate.get('leaf_node') or (path_nodes[-1] if path_nodes else ''),
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
            )
        return results

    def _build_partition_experience_paths(self, partition_id: str, partition_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        path_analyses = (partition_data or {}).get('path_analyses', []) or []
        converted_paths = self._convert_path_analyses_to_experience_paths(path_analyses, partition_id)

        max_structural = max(1, int(os.getenv('FH_EXPERIENCE_STRUCTURAL_MAX_PATHS', '12')))
        structural_paths = self._convert_paths_map_to_experience_paths(
            (partition_data or {}).get('paths_map') or {},
            partition_id,
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

        partition_analyses = hierarchy_data.get("partition_analyses", {})
        if partition_id:
            partition_data = partition_analyses.get(partition_id) or {}
            return self._build_partition_experience_paths(partition_id, partition_data)

        all_paths: List[Dict[str, Any]] = []
        for pid, pdata in partition_analyses.items():
            all_paths.extend(self._build_partition_experience_paths(pid, pdata or {}))
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
        all_paths: List[Dict[str, Any]] = []
        for p in data.get("partitions", []) or []:
            all_paths.extend(p.get("paths", []) or [])
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
