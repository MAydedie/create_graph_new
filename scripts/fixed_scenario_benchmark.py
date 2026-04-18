#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.services.conversation_service import (
    _build_retrieval_decision_trace,
    _build_retrieval_search_summary,
    _find_cached_retrieval,
    _remember_retrieval_cache,
    _run_retrieval_tool,
)


DEFAULT_PROJECT_PATH = r"D:\代码仓库生图\create_graph"
DEFAULT_REPORT_DIR = r"D:\代码仓库生图\汇报\4.6"


@dataclass
class Scenario:
    name: str
    query: str
    expected_files: List[str]


SCENARIOS: List[Scenario] = [
    Scenario(
        name="conversation_status_flow",
        query="conversation session status result 接口在哪里",
        expected_files=["app/services/conversation_service.py", "app/routes/api_routes.py"],
    ),
    Scenario(
        name="multi_agent_evidence",
        query="multi agent evidence extraction 在哪里实现",
        expected_files=["app/services/multi_agent_service.py"],
    ),
    Scenario(
        name="analysis_bridge",
        query="conversation retrieval bridge 到 rag 证据在 analysis_service 的哪里",
        expected_files=["app/services/analysis_service.py"],
    ),
    Scenario(
        name="frontend_rightpanel_strategy",
        query="RightPanel 展示 Retrieval Strategy 的代码",
        expected_files=["frontend_gitnexus/src/components/RightPanel.tsx"],
    ),
    Scenario(
        name="frontend_api_types",
        query="conversation retrieval payload 类型定义在 create-graph-extensions",
        expected_files=["frontend_gitnexus/src/services/create-graph-extensions.ts"],
    ),
    Scenario(
        name="codebase_retrieval_core",
        query="run_codebase_retrieval query decomposition followup 在哪里",
        expected_files=["app/services/codebase_retrieval_service.py"],
    ),
    Scenario(
        name="conversation_storage_cache",
        query="conversation keyFactsMemory retrievalCache 的保存逻辑",
        expected_files=["data/data_accessor.py", "app/services/conversation_service.py"],
    ),
    Scenario(
        name="sse_events",
        query="conversation events sse endpoint 代码",
        expected_files=["app/services/conversation_service.py"],
    ),
]


def _extract_files(highlights: List[Dict[str, Any]], limit: int = 5) -> List[str]:
    result: List[str] = []
    for item in highlights[:limit]:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("file") or item.get("file_path") or "").strip()
        if not file_path:
            continue
        result.append(file_path)
    return result


def _jaccard(items_a: List[str], items_b: List[str]) -> float:
    set_a = {str(item).strip().lower() for item in items_a if str(item).strip()}
    set_b = {str(item).strip().lower() for item in items_b if str(item).strip()}
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return round(len(set_a & set_b) / float(len(set_a | set_b)), 4)


def _scenario_hit(expected_files: List[str], top_files: List[str]) -> bool:
    lowered_top = [item.lower() for item in top_files]
    for expected in expected_files:
        expected_text = str(expected).lower()
        if any(expected_text in item for item in lowered_top):
            return True
    return False


def _now_text() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve_project_path(project_path: str) -> str:
    candidate = str(project_path or "").strip()
    if candidate and os.path.isdir(candidate):
        return os.path.normpath(candidate)
    fallback = os.path.normpath(PROJECT_ROOT)
    return fallback if os.path.isdir(fallback) else candidate


def _resolve_report_dir(report_dir: str) -> str:
    candidate = str(report_dir or "").strip()
    if candidate:
        return os.path.normpath(candidate)
    return os.path.normpath(os.path.join(PROJECT_ROOT, "benchmark_reports"))


def _list_benchmark_json_reports(report_dir: str) -> List[Path]:
    target = Path(report_dir)
    if not target.exists():
        return []
    reports = sorted(target.glob("fixed_scenario_benchmark_*.json"), key=lambda item: item.stat().st_mtime)
    return reports


def _safe_load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _build_latest_comparison(report_dir: str, current_json_path: str) -> Dict[str, Any]:
    reports = _list_benchmark_json_reports(report_dir)
    current_path = Path(current_json_path)
    previous_candidates = [item for item in reports if item.resolve() != current_path.resolve()]
    if not previous_candidates:
        return {"hasPrevious": False}

    previous_path = previous_candidates[-1]
    previous_payload = _safe_load_json(previous_path)
    previous_summary = _as_dict(previous_payload.get("summary"))

    current_payload = _safe_load_json(current_path)
    current_summary = _as_dict(current_payload.get("summary"))

    def _delta(key: str) -> float:
        curr = float(current_summary.get(key) or 0.0)
        prev = float(previous_summary.get(key) or 0.0)
        return round(curr - prev, 4)

    return {
        "hasPrevious": True,
        "previousReport": str(previous_path),
        "delta": {
            "hitRate": _delta("hitRate"),
            "top1StabilityRate": _delta("top1StabilityRate"),
            "top5JaccardAvg": _delta("top5JaccardAvg"),
            "decisionTraceAvailabilityRate": _delta("decisionTraceAvailabilityRate"),
            "cacheReuseHitRate": _delta("cacheReuseHitRate"),
            "cacheTop1ConsistencyRate": _delta("cacheTop1ConsistencyRate"),
            "elapsedMs": int(current_summary.get("elapsedMs") or 0) - int(previous_summary.get("elapsedMs") or 0),
        },
    }


def run_benchmark(project_path: str = DEFAULT_PROJECT_PATH, report_dir: str = DEFAULT_REPORT_DIR) -> Dict[str, Any]:
    project_path = _resolve_project_path(project_path)
    report_dir = _resolve_report_dir(report_dir)

    started = time.perf_counter()
    conversation_id = f"benchmark_{uuid4().hex}"
    scenario_results: List[Dict[str, Any]] = []

    total_hits = 0
    top1_stable = 0
    decision_trace_available = 0
    cache_reuse_hits = 0
    cache_top1_consistent = 0
    jaccard_values: List[float] = []

    for scenario in SCENARIOS:
        first_result = _run_retrieval_tool(project_path, scenario.query)
        second_result = _run_retrieval_tool(project_path, scenario.query)

        first_highlights = [item for item in (first_result.get("highlights") or []) if isinstance(item, dict)]
        second_highlights = [item for item in (second_result.get("highlights") or []) if isinstance(item, dict)]

        first_top_files = _extract_files(first_highlights, limit=5)
        second_top_files = _extract_files(second_highlights, limit=5)

        hit = _scenario_hit(scenario.expected_files, first_top_files)
        if hit:
            total_hits += 1

        first_top1 = first_top_files[0] if first_top_files else ""
        second_top1 = second_top_files[0] if second_top_files else ""
        stable_top1 = bool(first_top1 and first_top1 == second_top1)
        if stable_top1:
            top1_stable += 1

        jaccard_top5 = _jaccard(first_top_files, second_top_files)
        jaccard_values.append(jaccard_top5)

        first_summary = _build_retrieval_search_summary(first_result)
        decision_trace = _build_retrieval_decision_trace(
            action="run_retrieval",
            decision_reason="fixed_scenario_benchmark",
            confidence="high",
            cache_hit=False,
            retrieval_search_summary=first_summary,
            highlights_count=len(first_highlights),
        )
        has_decision_trace = len(decision_trace) >= 6
        if has_decision_trace:
            decision_trace_available += 1

        _remember_retrieval_cache(
            conversation_id,
            user_query=scenario.query,
            highlights=first_highlights,
            search_summary=first_summary,
        )
        cached_result = _find_cached_retrieval(conversation_id, scenario.query)
        cache_hit = bool(cached_result)
        if cache_hit:
            cache_reuse_hits += 1
            cached_highlights = [item for item in (cached_result.get("highlights") or []) if isinstance(item, dict)]
            cached_top_files = _extract_files(cached_highlights, limit=5)
            cache_top1 = cached_top_files[0] if cached_top_files else ""
            if first_top1 and first_top1 == cache_top1:
                cache_top1_consistent += 1
        else:
            cached_top_files = []

        scenario_results.append(
            {
                "name": scenario.name,
                "query": scenario.query,
                "expectedFiles": scenario.expected_files,
                "hit": hit,
                "firstTopFiles": first_top_files,
                "secondTopFiles": second_top_files,
                "top1Stable": stable_top1,
                "top5Jaccard": jaccard_top5,
                "decisionTraceSteps": len(decision_trace),
                "cacheHit": cache_hit,
                "cacheTopFiles": cached_top_files,
            }
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    scenario_count = len(SCENARIOS)
    avg_jaccard = round(sum(jaccard_values) / float(scenario_count), 4) if scenario_count else 0.0

    summary = {
        "scenarioCount": scenario_count,
        "hitRate": round(total_hits / float(scenario_count), 4) if scenario_count else 0.0,
        "top1StabilityRate": round(top1_stable / float(scenario_count), 4) if scenario_count else 0.0,
        "top5JaccardAvg": avg_jaccard,
        "decisionTraceAvailabilityRate": round(decision_trace_available / float(scenario_count), 4) if scenario_count else 0.0,
        "cacheReuseHitRate": round(cache_reuse_hits / float(scenario_count), 4) if scenario_count else 0.0,
        "cacheTop1ConsistencyRate": round(cache_top1_consistent / float(scenario_count), 4) if scenario_count else 0.0,
        "elapsedMs": elapsed_ms,
    }

    payload = {
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "projectPath": project_path,
        "conversationId": conversation_id,
        "summary": summary,
        "scenarios": scenario_results,
    }

    os.makedirs(report_dir, exist_ok=True)
    basename = f"fixed_scenario_benchmark_{_now_text()}"
    json_path = os.path.join(report_dir, f"{basename}.json")
    md_path = os.path.join(report_dir, f"{basename}.md")

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    lines = [
        "# 固定场景基准回归报告（命中率 / 稳定性对比）",
        "",
        f"- 生成时间: {payload['generatedAt']}",
        f"- 项目路径: `{project_path}`",
        f"- 场景数: {summary['scenarioCount']}",
        f"- 总耗时: {summary['elapsedMs']} ms",
        "",
        "## 汇总指标",
        "",
        f"- 命中率: **{summary['hitRate']:.2%}**",
        f"- Top1 稳定率: **{summary['top1StabilityRate']:.2%}**",
        f"- Top5 Jaccard 平均值: **{summary['top5JaccardAvg']:.4f}**",
        f"- 决策轨迹可用率: **{summary['decisionTraceAvailabilityRate']:.2%}**",
        f"- 检索缓存复用命中率: **{summary['cacheReuseHitRate']:.2%}**",
        f"- 缓存 Top1 一致率: **{summary['cacheTop1ConsistencyRate']:.2%}**",
        "",
        "## 场景明细",
        "",
        "| 场景 | 命中 | Top1稳定 | Top5Jaccard | 决策轨迹步数 | cache_hit |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for item in scenario_results:
        lines.append(
            "| {name} | {hit} | {stable} | {jaccard:.4f} | {steps} | {cache_hit} |".format(
                name=item["name"],
                hit="✅" if item["hit"] else "❌",
                stable="✅" if item["top1Stable"] else "❌",
                jaccard=float(item["top5Jaccard"]),
                steps=int(item["decisionTraceSteps"]),
                cache_hit="✅" if item["cacheHit"] else "❌",
            )
        )

    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    payload["artifacts"] = {"jsonPath": json_path, "markdownPath": md_path}
    payload["comparison"] = _build_latest_comparison(report_dir, json_path)

    comparison = _as_dict(payload.get("comparison"))
    if bool(comparison.get("hasPrevious")):
        delta = _as_dict(comparison.get("delta"))
        append_lines = [
            "",
            "## 与上次报告对比",
            "",
            f"- 上次报告: `{comparison.get('previousReport')}`",
            f"- 命中率变化: `{delta.get('hitRate')}`",
            f"- Top1 稳定率变化: `{delta.get('top1StabilityRate')}`",
            f"- Top5 Jaccard 变化: `{delta.get('top5JaccardAvg')}`",
            f"- 决策轨迹可用率变化: `{delta.get('decisionTraceAvailabilityRate')}`",
            f"- 缓存复用命中率变化: `{delta.get('cacheReuseHitRate')}`",
            f"- 缓存 Top1 一致率变化: `{delta.get('cacheTop1ConsistencyRate')}`",
            f"- 总耗时变化(ms): `{delta.get('elapsedMs')}`",
        ]
        with open(md_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(append_lines) + "\n")

    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run fixed scenario benchmark and export markdown/json report.")
    parser.add_argument("--project-path", dest="project_path", default=DEFAULT_PROJECT_PATH)
    parser.add_argument("--report-dir", dest="report_dir", default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()

    result = run_benchmark(project_path=args.project_path, report_dir=args.report_dir)
    print(json.dumps(result.get("summary") or {}, ensure_ascii=False, indent=2))
    print(json.dumps(result.get("artifacts") or {}, ensure_ascii=False, indent=2))
    print(json.dumps(result.get("comparison") or {}, ensure_ascii=False, indent=2))
