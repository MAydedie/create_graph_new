"""
ProjectManagerService — 项目级语义漏斗（阶段一：粗筛）

职责：
- 把所有 output_analysis/experience_paths/*.json 视作"全局经验库候选项目"
- 自动从 experience 文件 + architecture_digest 文件构造每个项目的 summary
- 用本地 embedding (BAAI/bge-small-zh-v1.5) 计算项目级向量并持久化
- 提供 query → top_k 候选项目 的检索能力（可选 LLM 查询扩写、MMR 多样性重排）

设计原则：
- 全本地：embedding 走 sentence-transformers，零 token 消耗
- 懒加载：只有首次 retrieve 才会真正加载 SentenceTransformer
- 持久化：embedding 缓存到 output_analysis/project_library/_global_registry.json
- 增量：summary 不变就不重新算 embedding（用 hash 校验）
- 线程安全：注册/检索全程加锁，可在 Flask 多线程环境下使用

返回的"项目候选"会作为 ExperienceStore.search 的 project_whitelist 输入，
形成"项目级粗筛 → 路径级精排"两段式漏斗。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_APP_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_EXPERIENCE_OUTPUT_ROOT = _APP_ROOT / "output_analysis"
_DEFAULT_REGISTRY_PATH = _DEFAULT_EXPERIENCE_OUTPUT_ROOT / "project_library" / "_global_registry.json"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _normalize_path_key(path_value: str) -> str:
    raw = _safe_str(path_value)
    if not raw:
        return ""
    try:
        return os.path.normpath(os.path.abspath(raw)).lower().replace("\\", "/")
    except Exception:
        return raw.lower().replace("\\", "/")


def _read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_project_summary(experience_payload: dict, digest_payload: Optional[dict]) -> str:
    """
    把一个项目的 experience_paths JSON + architecture_digest JSON 合成一段
    适合 embedding 的"项目摘要"。摘要要长得足以反映项目主题和能力，但又
    不能塞太多噪声路径，否则相似度计算会被稀释。
    """
    parts: List[str] = []

    project_name = _safe_str(experience_payload.get("project_name"))
    if project_name:
        parts.append(f"项目: {project_name}")

    if isinstance(digest_payload, dict):
        overview = digest_payload.get("overview") or {}
        purpose = _safe_str(overview.get("purpose"))
        if purpose:
            parts.append(f"用途: {purpose}")

        tech_stack = overview.get("tech_stack") or []
        if isinstance(tech_stack, list) and tech_stack:
            parts.append("技术栈: " + " / ".join(_safe_str(t) for t in tech_stack if _safe_str(t)))

        frameworks = overview.get("frameworks") or []
        if isinstance(frameworks, list) and frameworks:
            parts.append("框架: " + " / ".join(_safe_str(f) for f in frameworks if _safe_str(f)))

        ctx = _safe_str(digest_payload.get("cross_conversation_context"))
        if ctx:
            parts.append(ctx[:1200])

    partitions = experience_payload.get("partitions") or []
    partition_names: List[str] = []
    sample_descriptions: List[str] = []
    sample_path_names: List[str] = []
    functional_domains: List[str] = []

    for partition in partitions:
        if not isinstance(partition, dict):
            continue
        partition_name = _safe_str(partition.get("partition_name"))
        if partition_name:
            partition_names.append(partition_name)

        for path_item in partition.get("paths") or []:
            if not isinstance(path_item, dict):
                continue
            path_name = _safe_str(path_item.get("path_name"))
            path_desc = _safe_str(path_item.get("path_description"))
            semantics = path_item.get("semantics") or {}
            domain = _safe_str(semantics.get("functional_domain")) if isinstance(semantics, dict) else ""

            if domain and domain not in functional_domains:
                functional_domains.append(domain)
            if path_name and len(sample_path_names) < 24:
                sample_path_names.append(path_name)
            if path_desc and len(path_desc) > 12 and len(sample_descriptions) < 12:
                sample_descriptions.append(path_desc[:160])

    if partition_names:
        parts.append("功能分区: " + " / ".join(partition_names[:24]))
    if functional_domains:
        parts.append("功能域: " + " / ".join(functional_domains[:18]))
    if sample_path_names:
        parts.append("典型路径: " + " | ".join(sample_path_names[:18]))
    if sample_descriptions:
        parts.append("路径描述示例: " + " || ".join(sample_descriptions[:8]))

    return "\n".join(parts).strip()


class _LazyEmbeddingModel:
    """对主项目本地 EmbeddingModel 的懒加载封装，避免启动期昂贵加载。"""

    def __init__(self):
        self._model: Any = None
        self._lock = threading.Lock()
        self._dim: Optional[int] = None
        self._unavailable: bool = False

    def _ensure_loaded(self):
        if self._unavailable:
            raise RuntimeError("embedding model unavailable")
        if self._model is not None:
            return
        with self._lock:
            if self._unavailable:
                raise RuntimeError("embedding model unavailable")
            if self._model is not None:
                return
            from llm.rag_core.embedding_model import EmbeddingModel
            try:
                self._model = EmbeddingModel(allow_remote_download=False)
                self._dim = int(getattr(self._model, "embedding_dim", 0) or 0)
            except Exception:
                self._unavailable = True
                raise

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._ensure_loaded()
        return int(self._dim or 0)

    def encode(self, text: str) -> List[float]:
        self._ensure_loaded()
        vec = self._model.encode([text], show_progress=False, normalize_embeddings=True)
        try:
            return [float(x) for x in vec[0].tolist()]
        except Exception:
            return [float(x) for x in list(vec[0])]


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


class ProjectManagerService:
    """全局经验库的项目级粗筛服务（线程安全单例使用）。"""

    def __init__(
        self,
        experience_root: Path = _DEFAULT_EXPERIENCE_OUTPUT_ROOT,
        registry_path: Path = _DEFAULT_REGISTRY_PATH,
    ):
        self._experience_root = Path(experience_root)
        self._experience_paths_dir = self._experience_root / "experience_paths"
        self._registry_path = Path(registry_path)
        self._registry: Dict[str, Dict[str, Any]] = {}  # key=project_key
        self._lock = threading.RLock()
        self._embedder = _LazyEmbeddingModel()
        self._load_persisted()

    # ------------------------------------------------------------------ persistence

    def _load_persisted(self) -> None:
        payload = _read_json(self._registry_path)
        if not isinstance(payload, dict):
            return
        items = payload.get("items") or {}
        if isinstance(items, dict):
            with self._lock:
                self._registry = {
                    str(key): dict(value)
                    for key, value in items.items()
                    if isinstance(value, dict)
                }

    def _save_persisted(self) -> None:
        try:
            self._registry_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                snapshot = {
                    "version": "1.0",
                    "updated_at": _utcnow_iso(),
                    "embedding_dim": self._embedder.dim if self._registry else None,
                    "items": self._registry,
                }
            self._registry_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ------------------------------------------------------------------ registration

    def _project_key(self, project_name: str, source_file: str) -> str:
        # 文件名+项目名联合去重；同名不同 hash 的两份经验库要分开
        return f"{project_name}::{source_file}"

    def _digest_for_project(self, project_name: str, project_path: str) -> Optional[dict]:
        digest_dir = self._experience_paths_dir
        if not digest_dir.is_dir():
            return None
        # architecture_digest 命名规则：architecture_digest_<safe_name>_<hash>.json
        # 通过 project_path 生成的 hash 与 experience JSON 一致（experience_library_service._project_hash）
        project_hash = ""
        if project_path:
            try:
                project_hash = hashlib.md5(project_path.encode("utf-8")).hexdigest()[:8]
            except Exception:
                project_hash = ""
        candidates: List[Path] = []
        for path in digest_dir.glob("architecture_digest_*.json"):
            stem = path.stem.lower()
            if project_hash and stem.endswith(project_hash):
                candidates.insert(0, path)
            elif project_name and project_name.replace(" ", "_").lower() in stem:
                candidates.append(path)
        for candidate in candidates:
            payload = _read_json(candidate)
            if isinstance(payload, dict):
                return payload
        return None

    def bulk_register_from_experience_paths(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        扫描 experience_paths 目录，给每个未登记或已变更的项目计算 embedding。
        返回汇总信息。
        """
        if not self._experience_paths_dir.is_dir():
            return {"registered": 0, "skipped": 0, "errors": 0, "details": []}

        registered = 0
        skipped = 0
        errors = 0
        details: List[Dict[str, Any]] = []

        for json_file in sorted(self._experience_paths_dir.glob("*.json")):
            if json_file.name.startswith("architecture_digest_"):
                continue
            payload = _read_json(json_file)
            if not isinstance(payload, dict):
                errors += 1
                continue

            project_name = _safe_str(payload.get("project_name")) or json_file.stem
            project_path = _safe_str(payload.get("project_path"))
            digest_payload = self._digest_for_project(project_name, project_path)
            summary = _build_project_summary(payload, digest_payload)
            if not summary:
                skipped += 1
                continue

            summary_hash = _hash_text(summary)
            key = self._project_key(project_name, json_file.name)

            with self._lock:
                existing = self._registry.get(key) or {}
                if (
                    not force_refresh
                    and existing.get("summary_hash") == summary_hash
                    and existing.get("embedding")
                ):
                    skipped += 1
                    details.append({"project": project_name, "status": "skipped", "source": json_file.name})
                    continue

            try:
                embedding = self._embedder.encode(summary)
            except Exception as exc:
                errors += 1
                details.append(
                    {"project": project_name, "status": "error", "error": str(exc), "source": json_file.name}
                )
                continue

            entry = {
                "key": key,
                "project_name": project_name,
                "project_path": project_path,
                "project_path_key": _normalize_path_key(project_path),
                "source_file": json_file.name,
                "summary": summary,
                "summary_hash": summary_hash,
                "embedding": embedding,
                "registered_at": _utcnow_iso(),
                "total_paths": int(payload.get("total_paths") or 0),
                "partition_count": len(payload.get("partitions") or []),
            }
            with self._lock:
                self._registry[key] = entry
            registered += 1
            details.append({"project": project_name, "status": "registered", "source": json_file.name})

        if registered > 0:
            self._save_persisted()

        return {
            "registered": registered,
            "skipped": skipped,
            "errors": errors,
            "total_items": len(self._registry),
            "details": details,
        }

    def list_registry(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "key": item.get("key"),
                    "project_name": item.get("project_name"),
                    "project_path": item.get("project_path"),
                    "source_file": item.get("source_file"),
                    "summary": item.get("summary"),
                    "total_paths": item.get("total_paths", 0),
                    "partition_count": item.get("partition_count", 0),
                    "registered_at": item.get("registered_at"),
                }
                for item in self._registry.values()
            ]

    # ------------------------------------------------------------------ retrieval

    def retrieve_top_projects(
        self,
        query: str,
        top_k: int = 3,
        mmr_lambda: float = 0.7,
        expand_query: bool = False,
        expand_query_fn: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        基于查询语义返回 top_k 个候选项目。

        Args:
            query: 用户原始问题
            top_k: 返回项目数（推荐 3~5，避免后续路径漏斗稀释）
            mmr_lambda: MMR 多样性参数；越接近 1 越偏向相关性，越接近 0 越偏向多样性
            expand_query: 是否做 LLM 查询扩写（消耗 1 次 LLM 调用）
            expand_query_fn: callable(query, summaries) -> str 用于查询扩写
        """
        clean_query = _safe_str(query)
        if not clean_query:
            return []

        with self._lock:
            if not self._registry:
                return []
            items_snapshot = list(self._registry.values())

        used_query = clean_query
        if expand_query and callable(expand_query_fn):
            try:
                summaries_text = "\n".join(
                    f"- {item.get('project_name')}: {(_safe_str(item.get('summary')))[:200]}"
                    for item in items_snapshot[:30]
                )
                expanded = _safe_str(expand_query_fn(clean_query, summaries_text))
                if expanded:
                    used_query = expanded
            except Exception:
                pass

        try:
            query_embedding = self._embedder.encode(used_query)
        except Exception:
            return []

        scored: List[Dict[str, Any]] = []
        for item in items_snapshot:
            embedding = item.get("embedding") or []
            if not isinstance(embedding, list):
                continue
            score = _cosine(query_embedding, embedding)
            if score <= 0:
                continue
            scored.append({"item": item, "score": float(score)})

        scored.sort(key=lambda payload: payload["score"], reverse=True)
        if not scored:
            return []

        # MMR 重排：保证 top_k 项目方向有差异
        if 0.0 <= mmr_lambda < 1.0 and len(scored) > top_k:
            selected: List[Dict[str, Any]] = []
            candidates = list(scored)
            while candidates and len(selected) < max(top_k, 1):
                if not selected:
                    selected.append(candidates.pop(0))
                    continue
                best_score = -1.0
                best_index = 0
                for idx, candidate in enumerate(candidates):
                    diversity_penalty = 0.0
                    for chosen in selected:
                        sim = _cosine(
                            candidate["item"].get("embedding") or [],
                            chosen["item"].get("embedding") or [],
                        )
                        if sim > diversity_penalty:
                            diversity_penalty = sim
                    mmr_value = mmr_lambda * candidate["score"] - (1.0 - mmr_lambda) * diversity_penalty
                    if mmr_value > best_score:
                        best_score = mmr_value
                        best_index = idx
                selected.append(candidates.pop(best_index))
            ranked = selected
        else:
            ranked = scored[:top_k]

        results: List[Dict[str, Any]] = []
        for entry in ranked[:top_k]:
            item = entry["item"]
            results.append(
                {
                    "project_name": item.get("project_name"),
                    "project_path": item.get("project_path"),
                    "source_file": item.get("source_file"),
                    "summary": item.get("summary"),
                    "score": round(float(entry["score"]), 4),
                    "total_paths": item.get("total_paths", 0),
                    "partition_count": item.get("partition_count", 0),
                }
            )
        return results


_service_instance: Optional[ProjectManagerService] = None
_service_lock = threading.Lock()


def get_project_manager_service() -> ProjectManagerService:
    """全局单例。首次调用会从磁盘载入已有 embedding，但不会立即触发模型加载。"""
    global _service_instance
    with _service_lock:
        if _service_instance is None:
            _service_instance = ProjectManagerService()
        return _service_instance


def reset_project_manager_service_for_tests() -> None:
    """仅供测试使用，重置单例。"""
    global _service_instance
    with _service_lock:
        _service_instance = None
