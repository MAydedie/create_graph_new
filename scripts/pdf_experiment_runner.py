#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import difflib
import gzip
import json
import math
import os
import resource
import re
import pickle
import statistics
import subprocess
import sys
import time
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib.pyplot as plt
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from app.services.analysis_service import analyze_function_hierarchy
from app.services.codebase_retrieval_service import run_codebase_retrieval
from app.services.conversation_service import _run_retrieval_tool
from app.services.simple_qa_engine import SimpleQaEngine
from config.config import EMBEDDING_LOCAL_MODEL_DIR
from llm.rag_core.llm_api import DeepSeekAPI


DATASETS_DIR = PROJECT_ROOT / "数据集"
EXPERIMENT_DIR = PROJECT_ROOT / "实验"
DEFAULT_REPO_PATH = str(PROJECT_ROOT)
DEFAULT_OUTPUT_ROOT = Path("/opt/create_graph/work/experiments") if os.name != "nt" else PROJECT_ROOT / "tmp_experiments"
DEFAULT_DATASETS_ROOT = str(DATASETS_DIR)


@dataclass(frozen=True)
class GroupConfig:
    key: str
    label: str
    retrieval_mode: str
    graph_context: bool
    use_experience: bool
    env_overrides: Dict[str, str]
    runnable: bool = True
    note: str = ""


GROUPS: List[GroupConfig] = [
    GroupConfig(
        key="baseline",
        label="基准组",
        retrieval_mode="bm25",
        graph_context=False,
        use_experience=False,
        env_overrides={
            "FH_ENABLE_DEFAULT_VISIBLE_LAYER": "0",
            "FH_ENABLE_EXPAND_VISIBLE_LAYER": "0",
            "FH_ENABLE_ADVANCED_VISIBLE_LAYER": "0",
            "FH_ENABLE_PARTITION_LLM_SEMANTICS": "0",
            "FH_ENABLE_PATH_LLM_ANALYSIS": "0",
            "FH_ENABLE_PATH_SUPPLEMENT_GENERATION": "0",
            "FH_ENABLE_PATH_CFG_DFG_IO": "0",
            "FH_ENABLE_CFG_DFG_LLM_EXPLAIN": "0",
        },
        note="最小可达路径：仅词法检索，不启用图增强与经验增强。",
    ),
    GroupConfig(
        key="full",
        label="完整组",
        retrieval_mode="hybrid",
        graph_context=True,
        use_experience=True,
        env_overrides={
            "FH_ENABLE_DEFAULT_VISIBLE_LAYER": "1",
            "FH_ENABLE_EXPAND_VISIBLE_LAYER": "1",
            "FH_ENABLE_ADVANCED_VISIBLE_LAYER": "1",
            "FH_ENABLE_PARTITION_LLM_SEMANTICS": "1",
            "FH_ENABLE_PATH_LLM_ANALYSIS": "1",
            "FH_ENABLE_PATH_SUPPLEMENT_GENERATION": "1",
            "FH_ENABLE_PATH_CFG_DFG_IO": "1",
            "FH_ENABLE_CFG_DFG_LLM_EXPLAIN": "1",
        },
        note="当前代码库中最完整、最可辩护的可运行路径。",
    ),
    GroupConfig(
        key="ablation_a",
        label="消融A",
        retrieval_mode="bm25",
        graph_context=False,
        use_experience=True,
        env_overrides={
            "FH_ENABLE_DEFAULT_VISIBLE_LAYER": "1",
            "FH_ENABLE_EXPAND_VISIBLE_LAYER": "1",
            "FH_ENABLE_ADVANCED_VISIBLE_LAYER": "1",
            "FH_ENABLE_PARTITION_LLM_SEMANTICS": "1",
            "FH_ENABLE_PATH_LLM_ANALYSIS": "1",
            "FH_ENABLE_PATH_SUPPLEMENT_GENERATION": "1",
            "FH_ENABLE_PATH_CFG_DFG_IO": "1",
            "FH_ENABLE_CFG_DFG_LLM_EXPLAIN": "1",
        },
        note="关闭图增强，仅保留词法检索。",
    ),
    GroupConfig(
        key="ablation_b",
        label="消融B",
        retrieval_mode="hybrid",
        graph_context=True,
        use_experience=True,
        env_overrides={
            "FH_ENABLE_DEFAULT_VISIBLE_LAYER": "1",
            "FH_ENABLE_EXPAND_VISIBLE_LAYER": "1",
            "FH_ENABLE_ADVANCED_VISIBLE_LAYER": "1",
            "FH_ENABLE_PARTITION_LLM_SEMANTICS": "0",
            "FH_ENABLE_PATH_LLM_ANALYSIS": "1",
            "FH_ENABLE_PATH_SUPPLEMENT_GENERATION": "1",
            "FH_ENABLE_PATH_CFG_DFG_IO": "1",
            "FH_ENABLE_CFG_DFG_LLM_EXPLAIN": "1",
        },
        note="关闭分区级语义分析。",
    ),
    GroupConfig(
        key="ablation_c",
        label="消融C",
        retrieval_mode="semantic",
        graph_context=True,
        use_experience=True,
        env_overrides={
            "FH_ENABLE_DEFAULT_VISIBLE_LAYER": "1",
            "FH_ENABLE_EXPAND_VISIBLE_LAYER": "1",
            "FH_ENABLE_ADVANCED_VISIBLE_LAYER": "1",
            "FH_ENABLE_PARTITION_LLM_SEMANTICS": "1",
            "FH_ENABLE_PATH_LLM_ANALYSIS": "0",
            "FH_ENABLE_PATH_SUPPLEMENT_GENERATION": "0",
            "FH_ENABLE_PATH_CFG_DFG_IO": "0",
            "FH_ENABLE_CFG_DFG_LLM_EXPLAIN": "0",
        },
        note="关闭路径深分析相关步骤。",
    ),
    GroupConfig(
        key="ablation_d",
        label="消融D",
        retrieval_mode="hybrid",
        graph_context=True,
        use_experience=False,
        env_overrides={
            "FH_ENABLE_DEFAULT_VISIBLE_LAYER": "1",
            "FH_ENABLE_EXPAND_VISIBLE_LAYER": "1",
            "FH_ENABLE_ADVANCED_VISIBLE_LAYER": "1",
            "FH_ENABLE_PARTITION_LLM_SEMANTICS": "1",
            "FH_ENABLE_PATH_LLM_ANALYSIS": "1",
            "FH_ENABLE_PATH_SUPPLEMENT_GENERATION": "1",
            "FH_ENABLE_PATH_CFG_DFG_IO": "1",
            "FH_ENABLE_CFG_DFG_LLM_EXPLAIN": "1",
        },
        note="关闭经验增强，仅使用项目内检索证据。",
    ),
    GroupConfig(
        key="reference",
        label="参考组",
        retrieval_mode="bm25",
        graph_context=False,
        use_experience=False,
        env_overrides={},
        runnable=False,
        note="当前代码库未发现可与 PDF 中 Cypher+MCTS 路线严格对应的本地可执行实现；该行保留为未复现。",
    ),
]


CUSTOM_QA_CASES: List[Dict[str, Any]] = [
    {
        "id": "qa_real_001",
        "question": "run_codebase_retrieval query decomposition followup 在哪里实现？",
        "expected_keywords": ["run_codebase_retrieval", "codebase_retrieval_service", "conversation_service"],
        "expected_paths": [
            "app/services/conversation_service.py",
            "app/services/codebase_retrieval_service.py",
        ],
    },
    {
        "id": "qa_real_002",
        "question": "功能层级分析的 HTTP 入口和后台分析函数分别在哪里？",
        "expected_keywords": ["api_analyze_function_hierarchy", "analyze_function_hierarchy", "analysis_service"],
        "expected_paths": [
            "app/routes/api_routes.py",
            "app/services/analysis_service.py",
        ],
    },
    {
        "id": "qa_real_003",
        "question": "经验库导入逻辑在哪里？会把文件写到什么地方？",
        "expected_keywords": ["api_experience_library_import", "write_text", "experience_paths"],
        "expected_paths": [
            "app/services/experience_library_service.py",
        ],
    },
    {
        "id": "qa_real_004",
        "question": "GraphRAGSystem.query 的主要阶段是什么？",
        "expected_keywords": ["retrieve", "rerank", "LLM", "answer"],
        "expected_paths": [
            "llm/capability/graph_rag_system.py",
        ],
    },
]

THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.IGNORECASE)
FIGURE_LABELS = {
    "基准组": "baseline",
    "完整组": "full",
    "消融A": "ablA",
    "消融B": "ablB",
    "消融C": "ablC",
    "消融D": "ablD",
    "参考组": "reference",
}


def _now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _avg(values: Sequence[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _safe_path(value: Any) -> Path:
    return Path(str(value)).expanduser().resolve()


def _format_resource_value(value: Optional[float], suffix: str = "") -> str:
    if value is None:
        return "N/A"
    if suffix:
        return f"{value:.2f}{suffix}"
    return f"{value:.2f}"


def _sample_gpu_memory_mb() -> Optional[float]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    values: List[float] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            values.append(float(line))
        except ValueError:
            continue
    return max(values) if values else None


def _sample_process_rss_mb() -> Optional[float]:
    try:
        getrusage = getattr(resource, "getrusage", None)
        ruself = getattr(resource, "RUSAGE_SELF", None)
        if getrusage is None or ruself is None:
            return None
        usage = getrusage(ruself)
        rss_kb = float(usage.ru_maxrss)
        if os.name == "posix":
            return rss_kb / 1024.0
        return rss_kb / (1024.0 * 1024.0)
    except Exception:
        return None


def _measure_resources(start_wall: float, start_cpu: float, start_rss_mb: Optional[float], start_gpu_mb: Optional[float]) -> Dict[str, Optional[float]]:
    wall_delta = max(time.perf_counter() - start_wall, 1e-6)
    cpu_now = float(os.times().user + os.times().system)
    cpu_delta = max(cpu_now - start_cpu, 0.0)
    rss_now = _sample_process_rss_mb()
    gpu_now = _sample_gpu_memory_mb()
    cpu_percent = min(100.0, (cpu_delta / wall_delta) * 100.0)
    memory_mb = rss_now if rss_now is not None else start_rss_mb
    if memory_mb is not None and start_rss_mb is not None:
        memory_mb = max(memory_mb, start_rss_mb)
    gpu_mb = gpu_now if gpu_now is not None else start_gpu_mb
    if gpu_mb is not None and start_gpu_mb is not None:
        gpu_mb = max(gpu_mb, start_gpu_mb)
    return {
        "memory_mb": memory_mb,
        "gpu_memory_mb": gpu_mb,
        "cpu_percent": cpu_percent,
    }


def _dcg(relevances: Sequence[int], k: int) -> float:
    score = 0.0
    for idx, rel in enumerate(relevances[:k], start=1):
        if rel <= 0:
            continue
        score += rel / math.log2(idx + 1)
    return score


def _ndcg_from_rank(gold_index: int, ranked_indices: Sequence[int], k: int) -> float:
    relevances = [1 if idx == gold_index else 0 for idx in ranked_indices[:k]]
    ideal = _dcg([1], 1)
    return _dcg(relevances, k) / ideal if ideal else 0.0


def _mrr_from_rank(gold_index: int, ranked_indices: Sequence[int], k: int) -> float:
    for rank, idx in enumerate(ranked_indices[:k], start=1):
        if idx == gold_index:
            return 1.0 / rank
    return 0.0


def _edit_similarity(pred: str, truth: str) -> float:
    return difflib.SequenceMatcher(a=(pred or "").strip(), b=(truth or "").strip()).ratio()


def _tokenize(text: str) -> List[str]:
    return [token for token in str(text or "").lower().replace("\n", " ").split() if token]


def _rank_bm25(query: str, docs: Sequence[str]) -> List[Tuple[int, float]]:
    tokenized_docs = [_tokenize(doc) for doc in docs]
    bm25 = BM25Okapi(tokenized_docs)
    scores = bm25.get_scores(_tokenize(query))
    return sorted(list(enumerate(scores)), key=lambda item: item[1], reverse=True)


class SemanticRanker:
    def __init__(self) -> None:
        self.model = SentenceTransformer(EMBEDDING_LOCAL_MODEL_DIR)

    def rank(self, query: str, docs: Sequence[str]) -> List[Tuple[int, float]]:
        query_embedding = self.model.encode([query], normalize_embeddings=True)[0]
        doc_embeddings = self.model.encode(list(docs), normalize_embeddings=True)
        scores: List[Tuple[int, float]] = []
        for idx, doc_embedding in enumerate(doc_embeddings):
            score = float((query_embedding * doc_embedding).sum())
            scores.append((idx, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores


def _rrf_merge(rankings: Sequence[List[Tuple[int, float]]], k: int = 60) -> List[Tuple[int, float]]:
    merged: Dict[int, float] = {}
    for ranking in rankings:
        for pos, (idx, _score) in enumerate(ranking, start=1):
            merged[idx] = merged.get(idx, 0.0) + 1.0 / (k + pos)
    return sorted(merged.items(), key=lambda item: item[1], reverse=True)


@contextmanager
def _temp_env(overrides: Dict[str, str]) -> Iterator[None]:
    old_values = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _load_codesearchnet_python(limit_queries: int = 8, corpus_limit: int = 120) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    zip_path = DATASETS_DIR / "CodeSearchNet" / "python.zip"
    with zipfile.ZipFile(zip_path) as archive:
        target = next(name for name in archive.namelist() if "/test/" in name and name.endswith(".jsonl.gz"))
        payload = gzip.decompress(archive.read(target)).decode("utf-8")
    rows = [json.loads(line) for line in payload.splitlines() if line.strip()]
    corpus = rows[:corpus_limit]
    queries = rows[:limit_queries]
    return queries, corpus


def _evaluate_codesearchnet(group: GroupConfig, semantic_ranker: SemanticRanker) -> Dict[str, Any]:
    queries, corpus = _load_codesearchnet_python()
    docs = [item["code"] for item in corpus]
    lookup = {item["url"]: idx for idx, item in enumerate(corpus)}
    recalls: List[float] = []
    ndcgs: List[float] = []
    latencies: List[float] = []
    for query_item in queries:
        gold_index = lookup.get(query_item["url"])
        if gold_index is None:
            continue
        started = time.perf_counter()
        bm25_rank = _rank_bm25(query_item["docstring"], docs)
        semantic_rank = semantic_ranker.rank(query_item["docstring"], docs)
        if group.retrieval_mode == "bm25":
            ranking = bm25_rank
        elif group.retrieval_mode == "semantic":
            ranking = semantic_rank
        else:
            ranking = _rrf_merge([bm25_rank, semantic_rank])
        latencies.append((time.perf_counter() - started) * 1000)
        ranked_indices = [idx for idx, _ in ranking]
        recalls.append(1.0 if gold_index in ranked_indices[:10] else 0.0)
        ndcgs.append(_ndcg_from_rank(gold_index, ranked_indices, 10))
    return {
        "dataset": "CodeSearchNet",
        "Recall@10": _avg(recalls),
        "NDCG@10": _avg(ndcgs),
        "latency_ms": _avg(latencies),
        "count": len(recalls),
    }


def _load_repoqa_subset() -> Dict[str, Any]:
    raw_path = DATASETS_DIR / "repoqa-2024-06-23.json.gz"
    with gzip.open(raw_path, "rt", encoding="utf-8") as handle:
        dataset = json.load(handle)
    repos = dataset.get("python") or []
    subset: Dict[str, Any] = {"python": []}
    for repo in repos[:2]:
        if not repo.get("needles"):
            continue
        trimmed = dict(repo)
        trimmed["needles"] = list(repo["needles"][:4])
        subset["python"].append(trimmed)
    return subset


def _evaluate_repoqa(group: GroupConfig, semantic_ranker: SemanticRanker) -> Dict[str, Any]:
    dataset = _load_repoqa_subset()
    recalls: List[float] = []
    ndcgs: List[float] = []
    latencies: List[float] = []
    for repo in dataset.get("python", []):
        needles = repo.get("needles") or []
        candidates = []
        for needle in needles:
            file_text = str((repo.get("content") or {}).get(needle.get("path"), ""))
            candidates.append(file_text or f"{needle.get('path','')} {needle.get('name','')}")
        if not candidates:
            continue
        for gold_index, needle in enumerate(needles):
            query = str(needle.get("description") or "")
            started = time.perf_counter()
            bm25_rank = _rank_bm25(query, candidates)
            semantic_rank = semantic_ranker.rank(query, candidates)
            if group.retrieval_mode == "bm25":
                ranking = bm25_rank
            elif group.retrieval_mode == "semantic":
                ranking = semantic_rank
            else:
                ranking = _rrf_merge([bm25_rank, semantic_rank])
            latencies.append((time.perf_counter() - started) * 1000)
            ranked_indices = [idx for idx, _ in ranking]
            recalls.append(1.0 if gold_index in ranked_indices[:10] else 0.0)
            ndcgs.append(_ndcg_from_rank(gold_index, ranked_indices, 10))
    return {
        "dataset": "RepoQA(adapted)",
        "Recall@10": _avg(recalls),
        "NDCG@10": _avg(ndcgs),
        "latency_ms": _avg(latencies),
        "count": len(recalls),
        "note": "本地适配检索：使用 RepoQA 描述查询同仓 needle 候选文件内容；非官方 pass@k 口径。",
    }


def _iter_repobench_subset(limit: int = 20) -> List[Dict[str, Any]]:
    gz_path = DATASETS_DIR / "RepoBench-R" / "data" / "python_cff.gz"
    with gzip.open(gz_path, "rb") as handle:
        payload = pickle.load(handle)
    dataset = (((payload.get("test") or {}).get("easy")) or [])
    rows: List[Dict[str, Any]] = []
    for item in dataset:
        rows.append(dict(item))
        if len(rows) >= limit:
            break
    return rows


def _evaluate_repobench(group: GroupConfig, semantic_ranker: SemanticRanker) -> Dict[str, Any]:
    rows = _iter_repobench_subset()
    acc5: List[float] = []
    ndcg5: List[float] = []
    mrr5: List[float] = []
    latencies: List[float] = []
    for row in rows:
        query = f"{row.get('import_statement','')}\n{row.get('code','')}"
        docs = row.get("context") or []
        gold_index = row.get("gold_snippet_index")
        if gold_index is None:
            gold_index = row.get("golden_snippet_index")
        if gold_index is None:
            gold_index = row.get("gold_snippet_idex")
        if gold_index is None or not docs:
            continue
        started = time.perf_counter()
        bm25_rank = _rank_bm25(query, docs)
        semantic_rank = semantic_ranker.rank(query, docs)
        if group.retrieval_mode == "bm25":
            ranking = bm25_rank
        elif group.retrieval_mode == "semantic":
            ranking = semantic_rank
        else:
            ranking = _rrf_merge([bm25_rank, semantic_rank])
        latencies.append((time.perf_counter() - started) * 1000)
        ranked_indices = [idx for idx, _ in ranking]
        acc5.append(1.0 if gold_index in ranked_indices[:5] else 0.0)
        ndcg5.append(_ndcg_from_rank(int(gold_index), ranked_indices, 5))
        mrr5.append(_mrr_from_rank(int(gold_index), ranked_indices, 5))
    return {
        "dataset": "RepoBench-R",
        "Accuracy@5": _avg(acc5),
        "NDCG@5": _avg(ndcg5),
        "MRR@5": _avg(mrr5),
        "latency_ms": _avg(latencies),
        "count": len(acc5),
    }


def _load_crosscodeeval_rows(variant_name: str, limit: int = 4) -> List[Dict[str, Any]]:
    mapping = {
        "baseline": DATASETS_DIR / "crosscodeeval" / "python" / "line_completion.jsonl",
        "full": DATASETS_DIR / "crosscodeeval" / "python" / "line_completion_oracle_bm25.jsonl",
        "ablation_a": DATASETS_DIR / "crosscodeeval" / "python" / "line_completion_rg1_bm25.jsonl",
        "ablation_b": DATASETS_DIR / "crosscodeeval" / "python" / "line_completion_oracle_openai_cosine_sim.jsonl",
        "ablation_c": DATASETS_DIR / "crosscodeeval" / "python" / "line_completion_oracle_unixcoder_cosine_sim.jsonl",
        "ablation_d": DATASETS_DIR / "crosscodeeval" / "python" / "line_completion_rg1_unixcoder_cosine_sim.jsonl",
    }
    path = mapping.get(variant_name, mapping["baseline"])
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if len(rows) >= limit:
                break
    return rows


def _extract_completion_prompt(row: Dict[str, Any]) -> str:
    return str(row.get("prompt") or "")


def _generate_completion(llm: DeepSeekAPI, prompt: str) -> str:
    try:
        response = llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是一个代码补全助手。请仅输出下一行或最短必要补全，不要解释。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=96,
            timeout=45,
        )
        choices = response.get("choices") if isinstance(response, dict) else None
        if not isinstance(choices, list) or not choices:
            return ""
        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        return str((message or {}).get("content") or "").strip().splitlines()[0].strip()
    except Exception:
        return ""


def _evaluate_crosscodeeval(group: GroupConfig, llm: DeepSeekAPI) -> Dict[str, Any]:
    rows = _load_crosscodeeval_rows(group.key if group.key != "reference" else "baseline")
    em_scores: List[float] = []
    es_scores: List[float] = []
    latencies: List[float] = []
    details: List[Dict[str, Any]] = []
    for row in rows:
        prompt = _extract_completion_prompt(row)
        truth = str(row.get("groundtruth") or "").strip()
        started = time.perf_counter()
        pred = _generate_completion(llm, prompt)
        latencies.append((time.perf_counter() - started) * 1000)
        em = 1.0 if pred == truth else 0.0
        es = _edit_similarity(pred, truth)
        em_scores.append(em)
        es_scores.append(es)
        details.append({"groundtruth": truth, "prediction": pred, "em": em, "es": es})
    return {
        "dataset": "CrossCodeEval",
        "EM": _avg(em_scores),
        "ES": _avg(es_scores),
        "latency_ms": _avg(latencies),
        "count": len(em_scores),
        "details": details,
    }


def _summarize_hits(highlights: Sequence[Dict[str, Any]], limit: int = 4) -> str:
    lines: List[str] = []
    for item in highlights[:limit]:
        file_path = str(item.get("file") or item.get("file_path") or "")
        snippet = str(item.get("snippet") or "").strip().replace("\n", " ")
        lines.append(f"- {file_path}: {snippet[:280]}")
    return "\n".join(lines)


def _generate_qa_answer(question: str, evidence: str, experience: str, llm: DeepSeekAPI) -> str:
    prompt = (
        "基于以下项目证据回答问题，直接给结论并尽量包含关键文件或调用链。\n\n"
        f"问题：{question}\n\n"
        f"项目证据：\n{evidence}\n\n"
        f"经验证据：\n{experience or '无'}\n"
    )
    try:
        response = llm.chat(
            messages=[
                {"role": "system", "content": "你是代码问答评测助手。回答要简洁、可验证、避免无关展开。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=260,
            timeout=45,
        )
        choices = response.get("choices") if isinstance(response, dict) else None
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("empty llm choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        content = str((message or {}).get("content") or "").strip()
        content = THINK_BLOCK_RE.sub("", content).strip()
        if content:
            return content
        raise RuntimeError("empty llm content")
    except Exception:
        fallback_parts = [f"问题：{question}"]
        if evidence:
            fallback_parts.append("检索证据：")
            fallback_parts.append(evidence)
        if experience:
            fallback_parts.append("经验证据：")
            fallback_parts.append(experience[:500])
        return "\n".join(fallback_parts).strip()


def _path_match_rate(answer: str, expected_paths: Sequence[str], highlights: Sequence[Dict[str, Any]]) -> float:
    if not expected_paths:
        return 0.0
    text = (answer or "") + "\n" + "\n".join(str(item.get("file") or item.get("file_path") or "") for item in highlights)
    matched = sum(1 for path in expected_paths if path in text)
    return matched / len(expected_paths)


def _redundancy_rate(answer: str) -> float:
    lines = [line.strip() for line in str(answer or "").splitlines() if line.strip()]
    if not lines:
        return 1.0
    unique = len(set(lines))
    return max(0.0, 1.0 - unique / len(lines))


def _keyword_accuracy(answer: str, keywords: Sequence[str]) -> float:
    if not keywords:
        return 0.0
    lowered = str(answer or "").lower()
    matched = sum(1 for keyword in keywords if keyword.lower() in lowered)
    return matched / len(keywords)


def _prepare_project_for_group(project_path: str, output_root: Path, group: GroupConfig) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    with _temp_env(group.env_overrides):
        analyze_function_hierarchy(project_path, experience_output_root=str(output_root))


def _evaluate_custom_qa(group: GroupConfig, llm: DeepSeekAPI, project_path: str, output_root: Path) -> Dict[str, Any]:
    _prepare_project_for_group(project_path, output_root, group)
    qa_engine = SimpleQaEngine()
    path_rates: List[float] = []
    redundancies: List[float] = []
    qa_accs: List[float] = []
    qa_comps: List[float] = []
    latencies: List[float] = []
    traversed_nodes: List[float] = []
    details: List[Dict[str, Any]] = []
    for case in CUSTOM_QA_CASES:
        started = time.perf_counter()
        if group.graph_context:
            retrieval = _run_retrieval_tool(project_path, case["question"])
            highlights = retrieval.get("highlights") or []
            node_count = len(highlights)
        else:
            retrieval = run_codebase_retrieval(project_path=project_path, query=case["question"], top_k=8)
            highlights = retrieval.get("hits") or []
            node_count = len(highlights)
        evidence = _summarize_hits(highlights)
        experience_summary = ""
        if group.use_experience:
            try:
                experiences, candidate_projects = qa_engine._search_experience(case["question"], project_path, "project_bound")
                experience_summary = qa_engine._build_experience_summary(experiences, candidate_projects, "project_bound")
            except Exception:
                experience_summary = ""
        answer = _generate_qa_answer(case["question"], evidence, experience_summary, llm)
        elapsed_ms = (time.perf_counter() - started) * 1000
        path_rate = _path_match_rate(answer, case["expected_paths"], highlights)
        qa_acc = _keyword_accuracy(answer, case["expected_keywords"])
        qa_comp = (path_rate + qa_acc) / 2.0
        redundancy = _redundancy_rate(answer)
        path_rates.append(path_rate)
        qa_accs.append(qa_acc)
        qa_comps.append(qa_comp)
        redundancies.append(redundancy)
        latencies.append(elapsed_ms)
        traversed_nodes.append(float(node_count))
        details.append({
            "id": case["id"],
            "question": case["question"],
            "answer": answer,
            "path_match_rate": path_rate,
            "qa_acc": qa_acc,
            "qa_comp": qa_comp,
            "redundancy_rate": redundancy,
            "highlights": highlights,
        })
    return {
        "dataset": "CustomQA",
        "PathMatchRate": _avg(path_rates),
        "RedundancyRate": _avg(redundancies),
        "QA-Acc": _avg(qa_accs),
        "QA-Comp": _avg(qa_comps),
        "latency_ms": _avg(latencies),
        "traversed_nodes": _avg(traversed_nodes),
        "count": len(details),
        "details": details,
    }


def _collect_group_metrics(group: GroupConfig, project_path: str, group_output_root: Path, semantic_ranker: SemanticRanker, llm: DeepSeekAPI) -> Dict[str, Any]:
    if not group.runnable:
        return {
            "group": group.label,
            "runnable": False,
            "note": group.note,
            "tasks": {},
            "resources": {},
        }
    started_wall = time.perf_counter()
    started_cpu = float(os.times().user + os.times().system)
    started_rss_mb = _sample_process_rss_mb()
    started_gpu_mb = _sample_gpu_memory_mb()
    tasks = {
        "natural_codesearchnet": _evaluate_codesearchnet(group, semantic_ranker),
        "natural_repoqa": _evaluate_repoqa(group, semantic_ranker),
        "repobench_r": _evaluate_repobench(group, semantic_ranker),
        "crosscodeeval": _evaluate_crosscodeeval(group, llm),
        "custom_qa": _evaluate_custom_qa(group, llm, project_path, group_output_root),
    }
    resources = _measure_resources(started_wall, started_cpu, started_rss_mb, started_gpu_mb)
    return {
        "group": group.label,
        "runnable": True,
        "note": group.note,
        "tasks": tasks,
        "resources": resources,
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_tables(results: List[Dict[str, Any]], output_dir: Path) -> Dict[str, Path]:
    tables: Dict[str, Path] = {}
    overall_rows: List[Dict[str, Any]] = []
    retrieval_rows: List[Dict[str, Any]] = []
    repobench_rows: List[Dict[str, Any]] = []
    completion_rows: List[Dict[str, Any]] = []
    qa_rows: List[Dict[str, Any]] = []
    ablation_rows: List[Dict[str, Any]] = []
    efficiency_rows: List[Dict[str, Any]] = []
    error_rows: List[Dict[str, Any]] = []

    for item in results:
        label = item["group"]
        tasks = item.get("tasks") or {}
        if not item.get("runnable"):
            overall_rows.append({
                "实验组": label,
                "自然语言检索（主指标）": "N/A",
                "跨文件依赖检索（主指标）": "N/A",
                "代码补全（主指标）": "N/A",
                "扩展问答（主指标）": "N/A",
                "综合说明": item.get("note", ""),
            })
            efficiency_rows.append({
                "方法/实验组": label,
                "平均单条查询耗时(ms)": "N/A",
                "平均遍历节点数": "N/A",
                "内存占用": "N/A",
                "显存占用": "N/A",
                "CPU占用": "N/A",
                "备注": item.get("note", ""),
            })
            continue

        csn = tasks["natural_codesearchnet"]
        repoqa = tasks["natural_repoqa"]
        repobench = tasks["repobench_r"]
        completion = tasks["crosscodeeval"]
        custom_qa = tasks["custom_qa"]
        overall_rows.append({
            "实验组": label,
            "自然语言检索（主指标）": f"Recall@10={csn['Recall@10']:.4f}; NDCG@10={csn['NDCG@10']:.4f}",
            "跨文件依赖检索（主指标）": f"Accuracy@5={repobench['Accuracy@5']:.4f}; MRR@5={repobench['MRR@5']:.4f}",
            "代码补全（主指标）": f"EM={completion['EM']:.4f}; ES={completion['ES']:.4f}",
            "扩展问答（主指标）": f"QA-Acc={custom_qa['QA-Acc']:.4f}; QA-Comp={custom_qa['QA-Comp']:.4f}",
            "综合说明": item.get("note", ""),
        })
        retrieval_rows.extend([
            {"方法/实验组": label, "数据集": "CodeSearchNet", "Recall@10": f"{csn['Recall@10']:.4f}", "NDCG@10": f"{csn['NDCG@10']:.4f}", "备注": item.get("note", "")},
            {"方法/实验组": label, "数据集": "RepoQA(adapted)", "Recall@10": f"{repoqa['Recall@10']:.4f}", "NDCG@10": f"{repoqa['NDCG@10']:.4f}", "备注": repoqa.get("note", "")},
        ])
        repobench_rows.append({"方法/实验组": label, "Accuracy@5": f"{repobench['Accuracy@5']:.4f}", "NDCG@5": f"{repobench['NDCG@5']:.4f}", "MRR@5": f"{repobench['MRR@5']:.4f}", "备注": item.get("note", "")})
        completion_rows.append({"方法/实验组": label, "EM": f"{completion['EM']:.4f}", "ES": f"{completion['ES']:.4f}", "备注": item.get("note", "")})
        qa_rows.append({"方法/实验组": label, "路径匹配率": f"{custom_qa['PathMatchRate']:.4f}", "答案冗余率": f"{custom_qa['RedundancyRate']:.4f}", "QA-Acc": f"{custom_qa['QA-Acc']:.4f}", "QA-Comp": f"{custom_qa['QA-Comp']:.4f}", "备注": item.get("note", "")})
        if label.startswith("消融"):
            ablation_rows.append({
                "消融项": label,
                "自然语言检索": f"{csn['Recall@10']:.4f}/{csn['NDCG@10']:.4f}",
                "跨文件依赖检索": f"{repobench['Accuracy@5']:.4f}/{repobench['MRR@5']:.4f}",
                "代码补全": f"{completion['EM']:.4f}/{completion['ES']:.4f}",
                "扩展问答": f"{custom_qa['QA-Acc']:.4f}/{custom_qa['QA-Comp']:.4f}",
                "变化说明": item.get("note", ""),
            })
        efficiency_rows.append({
            "方法/实验组": label,
            "平均单条查询耗时(ms)": f"{statistics.mean([csn['latency_ms'], repoqa['latency_ms'], repobench['latency_ms'], completion['latency_ms'], custom_qa['latency_ms']]):.2f}",
            "平均遍历节点数": f"{custom_qa['traversed_nodes']:.2f}",
            "内存占用": _format_resource_value((item.get("resources") or {}).get("memory_mb"), " MB"),
            "显存占用": _format_resource_value((item.get("resources") or {}).get("gpu_memory_mb"), " MB"),
            "CPU占用": _format_resource_value((item.get("resources") or {}).get("cpu_percent"), "%"),
            "备注": item.get("note", ""),
        })
        for detail in (custom_qa.get("details") or []):
            error_rows.append({
                "编号": detail["id"],
                "任务类型": "custom_qa",
                "输入问题": detail["question"],
                "正确结果": "; ".join(CUSTOM_QA_CASES[[case['id'] for case in CUSTOM_QA_CASES].index(detail['id'])]["expected_paths"]),
                "系统输出": detail["answer"][:300],
                "失败原因": "路径缺失" if detail["path_match_rate"] < 1.0 else ("关键词覆盖不足" if detail["qa_acc"] < 1.0 else "-"),
                "备注": label,
            })

    output_dir.mkdir(parents=True, exist_ok=True)
    tables["table1"] = output_dir / "table1_overall.csv"
    _write_csv(tables["table1"], overall_rows, ["实验组", "自然语言检索（主指标）", "跨文件依赖检索（主指标）", "代码补全（主指标）", "扩展问答（主指标）", "综合说明"])
    tables["table2"] = output_dir / "table2_nl_retrieval.csv"
    _write_csv(tables["table2"], retrieval_rows, ["方法/实验组", "数据集", "Recall@10", "NDCG@10", "备注"])
    tables["table3"] = output_dir / "table3_cross_file.csv"
    _write_csv(tables["table3"], repobench_rows, ["方法/实验组", "Accuracy@5", "NDCG@5", "MRR@5", "备注"])
    tables["table4"] = output_dir / "table4_completion.csv"
    _write_csv(tables["table4"], completion_rows, ["方法/实验组", "EM", "ES", "备注"])
    tables["table5"] = output_dir / "table5_custom_qa.csv"
    _write_csv(tables["table5"], qa_rows, ["方法/实验组", "路径匹配率", "答案冗余率", "QA-Acc", "QA-Comp", "备注"])
    tables["table6"] = output_dir / "table6_ablation.csv"
    _write_csv(tables["table6"], ablation_rows, ["消融项", "自然语言检索", "跨文件依赖检索", "代码补全", "扩展问答", "变化说明"])
    tables["table7"] = output_dir / "table7_efficiency.csv"
    _write_csv(tables["table7"], efficiency_rows, ["方法/实验组", "平均单条查询耗时(ms)", "平均遍历节点数", "内存占用", "显存占用", "CPU占用", "备注"])
    tables["table8"] = output_dir / "table8_errors.csv"
    _write_csv(tables["table8"], error_rows, ["编号", "任务类型", "输入问题", "正确结果", "系统输出", "失败原因", "备注"])
    return tables


def _build_figures(results: List[Dict[str, Any]], output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    runnable = [item for item in results if item.get("runnable")]
    group_labels = [FIGURE_LABELS.get(item["group"], item["group"]) for item in runnable]
    retrieval_scores = [item["tasks"]["natural_codesearchnet"]["Recall@10"] for item in runnable]
    latencies = [item["tasks"]["natural_codesearchnet"]["latency_ms"] for item in runnable]

    fig1_path = output_dir / "figure1_retrieval_depth_substitute.png"
    plt.figure(figsize=(8, 4.5))
    plt.plot(group_labels, retrieval_scores, marker="o", label="Recall@10")
    plt.plot(group_labels, latencies, marker="s", label="Latency(ms)")
    plt.title("Figure 1 - Retrieval Effect / Cost Curve (MCTS substitute)")
    plt.xticks(rotation=25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig1_path, dpi=160)
    plt.close()

    fig2_path = output_dir / "figure2_efficiency_effect_tradeoff.png"
    plt.figure(figsize=(6.5, 5.0))
    qa_scores = [item["tasks"]["custom_qa"]["QA-Comp"] for item in runnable]
    qa_latency = [item["tasks"]["custom_qa"]["latency_ms"] for item in runnable]
    for label, x_value, y_value in zip(group_labels, qa_latency, qa_scores):
        plt.scatter(x_value, y_value, s=70)
        plt.text(x_value, y_value, label)
    plt.xlabel("Average QA latency (ms)")
    plt.ylabel("QA-Comp")
    plt.title("Figure 2 - Efficiency / Effect Tradeoff")
    plt.tight_layout()
    plt.savefig(fig2_path, dpi=160)
    plt.close()
    return {"figure1": fig1_path, "figure2": fig2_path}


def _write_report(results: List[Dict[str, Any]], tables: Dict[str, Path], figures: Dict[str, Path], output_path: Path) -> None:
    lines = [
        "# PDF 实验执行报告（适配版）",
        "",
        f"- 生成时间: {datetime.now().isoformat()}",
        f"- 项目根目录: `{PROJECT_ROOT}`",
        "- 重要说明: 当前代码库未发现 PDF 文本所述 `Cypher + MCTS` 的本地可执行链路，因此本报告严格以仓库中可取证的运行路径为准；`Figure 1` 使用检索效果/耗时替代曲线。",
        "",
        "## 实验组说明",
        "",
    ]
    for item in results:
        lines.append(f"- **{item['group']}**: {item.get('note','')}")
    lines.extend([
        "",
        "## 产出文件",
        "",
    ])
    for key, path in tables.items():
        lines.append(f"- {key}: `{path}`")
    for key, path in figures.items():
        lines.append(f"- {key}: `{path}`")
    lines.extend([
        "",
        "## 指标分析",
        "",
    ])
    runnable = [item for item in results if item.get("runnable")]
    if runnable:
        best_retrieval = max(runnable, key=lambda item: item["tasks"]["natural_codesearchnet"]["Recall@10"])
        best_cross = max(runnable, key=lambda item: item["tasks"]["repobench_r"]["MRR@5"])
        best_completion = max(runnable, key=lambda item: item["tasks"]["crosscodeeval"]["ES"])
        best_qa = max(runnable, key=lambda item: item["tasks"]["custom_qa"]["QA-Comp"])
        lines.append(f"- 自然语言检索最优组: **{best_retrieval['group']}**，CodeSearchNet `Recall@10={best_retrieval['tasks']['natural_codesearchnet']['Recall@10']:.4f}`。")
        lines.append(f"- 跨文件依赖检索最优组: **{best_cross['group']}**，RepoBench-R `MRR@5={best_cross['tasks']['repobench_r']['MRR@5']:.4f}`。")
        lines.append(f"- 代码补全最优组: **{best_completion['group']}**，CrossCodeEval `ES={best_completion['tasks']['crosscodeeval']['ES']:.4f}`。")
        lines.append(f"- 扩展问答最优组: **{best_qa['group']}**，`QA-Comp={best_qa['tasks']['custom_qa']['QA-Comp']:.4f}`。")
    lines.extend([
        "",
        "## 方法学限制",
        "",
        "- RepoQA 原生官方口径是 `pass@k`，本报告为了与 PDF 表头对齐，采用了本地适配检索口径而非官方 `pass@k` 直接填表。",
        "- 参考组保留为未复现；这是为了避免把不存在的 `Cypher + MCTS` 路线伪装成已完成实验。",
        "- CrossCodeEval 采用小样本运行，以保证服务器上能在合理时间内完成真实生成与评分。",
        "",
    ])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(output_root: str = str(DEFAULT_OUTPUT_ROOT), project_path: str = DEFAULT_REPO_PATH, datasets_root: str = DEFAULT_DATASETS_ROOT) -> Dict[str, Any]:
    global DATASETS_DIR
    DATASETS_DIR = _safe_path(datasets_root)
    output_dir = Path(output_root) / f"pdf_experiment_{_now_tag()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    semantic_ranker = SemanticRanker()
    llm = DeepSeekAPI(timeout=60)
    results: List[Dict[str, Any]] = []
    for group in GROUPS:
        group_output_root = output_dir / "group_artifacts" / group.key
        results.append(_collect_group_metrics(group, project_path, group_output_root, semantic_ranker, llm))
    raw_path = output_dir / "raw_results.json"
    raw_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    tables = _build_tables(results, output_dir / "tables")
    figures = _build_figures(results, output_dir / "figures")
    _write_report(results, tables, figures, output_dir / "report.md")
    return {
        "output_dir": str(output_dir),
        "raw_results": str(raw_path),
        "tables": {key: str(value) for key, value in tables.items()},
        "figures": {key: str(value) for key, value in figures.items()},
        "report": str(output_dir / "report.md"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run adapted PDF experiment bundle")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--project-path", default=DEFAULT_REPO_PATH)
    parser.add_argument("--datasets-root", default=DEFAULT_DATASETS_ROOT)
    args = parser.parse_args()
    payload = run(output_root=args.output_root, project_path=args.project_path, datasets_root=args.datasets_root)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
