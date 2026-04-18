#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services import multi_agent_service as mas


@dataclass
class Scenario:
    name: str
    query: str
    expected_invoke: bool
    task_mode: str = "modify_existing"


SCENARIOS = [
    Scenario("locate_conversation_status", "conversation session status result 接口在哪里", False),
    Scenario("locate_multi_agent_evidence", "multi agent evidence extraction 在哪里实现", False),
    Scenario("rightpanel_strategy_code", "RightPanel 展示 Retrieval Strategy 的代码", True),
    Scenario("locate_retrieval_core", "run_codebase_retrieval query decomposition followup 在哪里", False),
    Scenario("architecture_security_refactor", "我要重构多代理架构并提高安全性", True),
    Scenario("cross_module_design", "请设计一个新的跨模块调用链方案", True),
    Scenario("fix_sse_endpoint", "修复 conversation events sse endpoint 的小 bug", False),
    Scenario("add_logging_existing_path", "在现有路径里补一个日志输出", True),
]


def _now_text() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _match_symbol(symbol: str, detail: dict[str, Any]) -> bool:
    target = _norm(symbol)
    if not target:
        return False
    for candidate in (_norm(detail.get("signature")), _norm(detail.get("entity_id")), _norm(detail.get("display_name"))):
        if not candidate:
            continue
        if candidate == target or candidate.endswith(f".{target}") or target.endswith(f".{candidate}"):
            return True
    return False


def _simulate_old_path_node_details(project_path: str, selected_path: dict[str, Any], fallback_details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    seen: set[str] = set()
    chain = _as_list(selected_path.get("function_chain")) or _as_list(selected_path.get("path"))
    for symbol in chain[:5]:
        if not isinstance(symbol, str) or not symbol.strip() or symbol in seen:
            continue
        seen.add(symbol)
        detail = mas._build_node_detail_payload(project_path, symbol)
        if isinstance(detail, dict):
            details.append(detail)
    return details if details else [item for item in fallback_details if isinstance(item, dict)]


def _chain_quality(chain_symbols: list[str], details: list[dict[str, Any]]) -> dict[str, float]:
    if not chain_symbols:
        return {"node_presence_rate": 0.0, "anchor_coverage_rate": 0.0, "structured_detail_rate": 0.0}
    present = 0
    anchored = 0
    structured = 0
    for symbol in chain_symbols:
        matched = None
        for detail in details:
            if _match_symbol(symbol, detail):
                matched = detail
                break
        if matched is None:
            continue
        present += 1
        file_path = _norm(matched.get("file_path") or _as_dict(matched.get("source")).get("file_path"))
        if file_path:
            anchored += 1
        if isinstance(matched.get("step_index"), int) and _norm(matched.get("chain_role")) and _norm(matched.get("call_explanation")):
            structured += 1
    total = float(len(chain_symbols))
    return {
        "node_presence_rate": round(present / total, 4),
        "anchor_coverage_rate": round(anchored / total, 4),
        "structured_detail_rate": round(structured / total, 4),
    }


def run_ab(project_path: str, report_dir: str) -> dict[str, Any]:
    project_path = str(Path(project_path).resolve())
    report_root = Path(report_dir)
    report_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    control_correct = treatment_correct = 0
    control_unnecessary = treatment_unnecessary = 0
    control_missed = treatment_missed = 0
    c_pres = t_pres = c_anchor = t_anchor = c_struct = t_struct = 0.0

    for scenario in SCENARIOS:
        rb = mas._build_retrieval_bundle(project_path, scenario.query)
        control_invoke = True
        treatment_invoke, reason, signals = mas._should_invoke_advisor(scenario.query, scenario.task_mode, rb)
        expected = bool(scenario.expected_invoke)

        control_correct += int(control_invoke == expected)
        treatment_correct += int(bool(treatment_invoke) == expected)
        control_unnecessary += int(control_invoke and not expected)
        treatment_unnecessary += int(bool(treatment_invoke) and not expected)
        control_missed += int((not control_invoke) and expected)
        treatment_missed += int((not bool(treatment_invoke)) and expected)

        selected_path = _as_dict(rb.get("selected_path"))
        chain_symbols = [_norm(item) for item in (_as_list(selected_path.get("function_chain")) or _as_list(selected_path.get("path"))) if _norm(item)]
        evidence_node_details = mas._build_node_details(project_path, _as_list(rb.get("evidence")))
        control_details = _simulate_old_path_node_details(project_path, selected_path, evidence_node_details)
        treatment_details = [item for item in _as_list(rb.get("chain_node_details")) if isinstance(item, dict)]

        c = _chain_quality(chain_symbols, control_details)
        t = _chain_quality(chain_symbols, treatment_details)
        c_pres += c["node_presence_rate"]
        t_pres += t["node_presence_rate"]
        c_anchor += c["anchor_coverage_rate"]
        t_anchor += t["anchor_coverage_rate"]
        c_struct += c["structured_detail_rate"]
        t_struct += t["structured_detail_rate"]

        rows.append({
            "name": scenario.name,
            "query": scenario.query,
            "expected_invoke": expected,
            "control_invoke": control_invoke,
            "treatment_invoke": bool(treatment_invoke),
            "treatment_reason": reason,
            "treatment_signals": signals,
            "selection_mode": rb.get("selection_mode"),
            "confidence": rb.get("confidence"),
            "chain_length": len(chain_symbols),
            "control_chain_quality": c,
            "treatment_chain_quality": t,
        })

    n = float(len(SCENARIOS))
    summary = {
        "scenario_count": int(n),
        "advisor_quality": {
            "control_accuracy": round(control_correct / n, 4),
            "treatment_accuracy": round(treatment_correct / n, 4),
            "accuracy_delta": round((treatment_correct - control_correct) / n, 4),
            "control_unnecessary_invoke_rate": round(control_unnecessary / n, 4),
            "treatment_unnecessary_invoke_rate": round(treatment_unnecessary / n, 4),
            "unnecessary_invoke_delta": round((treatment_unnecessary - control_unnecessary) / n, 4),
            "control_missed_needed_rate": round(control_missed / n, 4),
            "treatment_missed_needed_rate": round(treatment_missed / n, 4),
        },
        "chain_locator_quality": {
            "control_node_presence_avg": round(c_pres / n, 4),
            "treatment_node_presence_avg": round(t_pres / n, 4),
            "node_presence_delta": round((t_pres - c_pres) / n, 4),
            "control_anchor_coverage_avg": round(c_anchor / n, 4),
            "treatment_anchor_coverage_avg": round(t_anchor / n, 4),
            "anchor_coverage_delta": round((t_anchor - c_anchor) / n, 4),
            "control_structured_detail_avg": round(c_struct / n, 4),
            "treatment_structured_detail_avg": round(t_struct / n, 4),
            "structured_detail_delta": round((t_struct - c_struct) / n, 4),
        },
    }

    gates = {
        "advisor_accuracy_improved": summary["advisor_quality"]["accuracy_delta"] > 0,
        "unnecessary_invoke_reduced": summary["advisor_quality"]["unnecessary_invoke_delta"] < 0,
        "structured_chain_detail_improved": summary["chain_locator_quality"]["structured_detail_delta"] > 0,
        "anchor_coverage_not_worse": summary["chain_locator_quality"]["anchor_coverage_delta"] >= 0,
    }
    summary["gates"] = gates
    summary["pass"] = all(gates.values())

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "project_path": project_path,
        "summary": summary,
        "scenarios": rows,
    }

    stamp = _now_text()
    json_path = report_root / f"advisor_chain_ab_{stamp}.json"
    md_path = report_root / f"advisor_chain_ab_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Advisor + Chain A/B 质量报告",
        "",
        f"- 生成时间: {payload['generated_at']}",
        f"- 项目路径: `{project_path}`",
        f"- 样本数: {len(SCENARIOS)}",
        "",
        "## Advisor 智能调用",
        f"- control 准确率: {summary['advisor_quality']['control_accuracy']:.2%}",
        f"- treatment 准确率: {summary['advisor_quality']['treatment_accuracy']:.2%}",
        f"- 准确率提升: {summary['advisor_quality']['accuracy_delta']:+.2%}",
        f"- control 非必要调用率: {summary['advisor_quality']['control_unnecessary_invoke_rate']:.2%}",
        f"- treatment 非必要调用率: {summary['advisor_quality']['treatment_unnecessary_invoke_rate']:.2%}",
        f"- 非必要调用率变化: {summary['advisor_quality']['unnecessary_invoke_delta']:+.2%}",
        "",
        "## 方法链节点定位",
        f"- control 结构化节点率: {summary['chain_locator_quality']['control_structured_detail_avg']:.2%}",
        f"- treatment 结构化节点率: {summary['chain_locator_quality']['treatment_structured_detail_avg']:.2%}",
        f"- 结构化节点率提升: {summary['chain_locator_quality']['structured_detail_delta']:+.2%}",
        f"- control 锚点覆盖: {summary['chain_locator_quality']['control_anchor_coverage_avg']:.2%}",
        f"- treatment 锚点覆盖: {summary['chain_locator_quality']['treatment_anchor_coverage_avg']:.2%}",
        f"- 锚点覆盖变化: {summary['chain_locator_quality']['anchor_coverage_delta']:+.2%}",
        "",
        "## 通过门槛",
        f"- advisor 准确率提升: {gates['advisor_accuracy_improved']}",
        f"- 非必要调用下降: {gates['unnecessary_invoke_reduced']}",
        f"- 链路结构化提升: {gates['structured_chain_detail_improved']}",
        f"- 锚点覆盖不下降: {gates['anchor_coverage_not_worse']}",
        f"- 总体通过: {summary['pass']}",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    artifacts = {"json_path": str(json_path), "markdown_path": str(md_path)}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(artifacts, ensure_ascii=False, indent=2))
    payload["artifacts"] = artifacts
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run advisor and chain A/B benchmark")
    parser.add_argument("--project-path", default=r"D:\代码仓库生图\create_graph")
    parser.add_argument("--report-dir", default=r"D:\代码仓库生图\create_graph\benchmark_reports\advisor_chain_ab")
    args = parser.parse_args()
    run_ab(project_path=args.project_path, report_dir=args.report_dir)


if __name__ == "__main__":
    main()
