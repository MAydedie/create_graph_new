from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR.parent) not in sys.path:
    sys.path.insert(0, str(BASE_DIR.parent))

from advisor_consultant_lab import common as c
from advisor_consultant_lab import config as cfg


as_str = c.as_str
as_str_list = c.as_str_list
append_jsonl = c.append_jsonl
ensure_runtime = c.ensure_runtime
read_json = c.read_json
utc_now = c.utc_now
write_json = c.write_json
write_text = c.write_text

RUNTIME_DIR = cfg.RUNTIME_DIR
STEP1_MATCH_RESULT_FILE = cfg.STEP1_MATCH_RESULT_FILE
STEP2_ANALYSIS_JSON_FILE = cfg.STEP2_ANALYSIS_JSON_FILE
STEP2_ANALYSIS_MD_FILE = cfg.STEP2_ANALYSIS_MD_FILE
STEP2_ANALYSIS_PROCESS_FILE = cfg.STEP2_ANALYSIS_PROCESS_FILE
STAGE_TRACE_FILE = cfg.STAGE_TRACE_FILE


def _select_followup_advisors(advisors: list[dict[str, Any]], query_profile: dict[str, Any]) -> list[dict[str, Any]]:
    if not advisors:
        return []

    scope = as_str(query_profile.get("scope")) or "mixed"
    top_score = float((advisors[0] or {}).get("fused_score") or 0.0)

    if scope == "broad":
        ratio = 0.7
        hard_min = 6
        hard_max = 14
    elif scope == "specific":
        ratio = 0.86
        hard_min = 2
        hard_max = 6
    else:
        ratio = 0.78
        hard_min = 4
        hard_max = 10

    threshold = top_score * ratio if top_score > 0 else 0.0
    selected = [
        item for item in advisors if float(item.get("fused_score") or 0.0) >= threshold and int(item.get("total_hits") or 0) > 0
    ]

    if len(selected) < hard_min:
        selected = advisors[: min(hard_min, len(advisors))]
    if len(selected) > hard_max:
        selected = selected[:hard_max]
    return selected


def _advisor_brief(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": item.get("rank"),
        "advisor_id": as_str(item.get("advisor_id")),
        "advisor_name": as_str(item.get("advisor_name")),
        "project_name": as_str(item.get("project_name")),
        "partition_id": as_str(item.get("partition_id")),
        "fused_score": item.get("fused_score"),
        "what": as_str(item.get("what")),
        "how": as_str(item.get("how")),
    }


def _normalize_constraints_structured(payload: Any) -> dict[str, Any]:
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    if not isinstance(payload, dict):
        payload = {}
    cfg_payload = _as_dict(payload.get("cfg"))
    dfg_payload = _as_dict(payload.get("dfg"))
    io_payload = _as_dict(payload.get("io_graph"))
    explain_payload = _as_dict(payload.get("constraint_explain"))
    cfg_summary = _as_dict(cfg_payload.get("summary"))
    dfg_summary = _as_dict(dfg_payload.get("summary"))
    io_summary = _as_dict(io_payload.get("summary"))
    return {
        "version": as_str(payload.get("version")) or "constraints.v1",
        "types": as_str_list(payload.get("types")),
        "cfg": {
            "summary": cfg_summary,
            "input_info_keys": as_str_list(cfg_payload.get("input_info_keys")),
            "output_info_keys": as_str_list(cfg_payload.get("output_info_keys")),
        },
        "dfg": {
            "summary": dfg_summary,
        },
        "io_graph": {
            "summary": io_summary,
            "inputs": as_str_list(io_payload.get("inputs")),
            "outputs": as_str_list(io_payload.get("outputs")),
        },
        "input_info": payload.get("input_info") if isinstance(payload.get("input_info"), dict) else {},
        "output_info": payload.get("output_info") if isinstance(payload.get("output_info"), dict) else {},
        "constraint_explain": {
            "exists": bool(explain_payload.get("exists")),
            "markdown": as_str(explain_payload.get("markdown")),
        },
    }


def _structured_constraints_summary(constraints_structured: dict[str, Any]) -> dict[str, Any]:
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    cfg_summary = _as_dict(_as_dict(constraints_structured.get("cfg")).get("summary"))
    dfg_summary = _as_dict(_as_dict(constraints_structured.get("dfg")).get("summary"))
    io_summary = _as_dict(_as_dict(constraints_structured.get("io_graph")).get("summary"))
    explain_payload = _as_dict(constraints_structured.get("constraint_explain"))
    return {
        "types": as_str_list(constraints_structured.get("types")),
        "has_cfg": bool(cfg_summary.get("exists")),
        "has_dfg": bool(dfg_summary.get("exists")),
        "has_io_graph": bool(io_summary.get("exists")),
        "cfg_node_count": int(cfg_summary.get("node_count") or 0),
        "dfg_node_count": int(dfg_summary.get("node_count") or 0),
        "io_node_count": int(io_summary.get("node_count") or 0),
        "has_constraint_explain": bool(explain_payload.get("exists")),
    }


def _build_analysis(match_payload: dict[str, Any], *, run_id: str, question_id: str) -> dict[str, Any]:
    advisors = [item for item in (match_payload.get("matched_advisors") or []) if isinstance(item, dict)]
    if not advisors:
        raise ValueError("no matched advisors found in step1 result")

    query_profile_raw = match_payload.get("query_profile")
    query_profile: dict[str, Any] = query_profile_raw if isinstance(query_profile_raw, dict) else {}
    selected_followup = _select_followup_advisors(advisors, query_profile)
    primary = advisors[0]
    constraints_structured = _normalize_constraints_structured(primary.get("constraints_structured"))
    constraints_structured_summary = _structured_constraints_summary(constraints_structured)

    return {
        "version": "advisor.lab.v1",
        "step": "analyze_advisor",
        "generated_at": utc_now(),
        "run_id": run_id,
        "question_id": question_id,
        "requirement": as_str(match_payload.get("requirement")),
        "match_summary": {
            "policy": (match_payload.get("matching_explanation") or {}).get("policy"),
            "query_profile": query_profile,
            "matched_count": len(advisors),
            "top_advisor": {
                "advisor_id": as_str(primary.get("advisor_id")),
                "advisor_name": as_str(primary.get("advisor_name")),
                "fused_score": primary.get("fused_score"),
                "agent_scores": primary.get("agent_scores") or {},
                "match_reason": as_str(primary.get("match_reason")),
                "what": as_str(primary.get("what")),
                "how": as_str(primary.get("how")),
            },
            "top_candidates_preview": [_advisor_brief(item) for item in advisors[:10]],
            "selected_for_followup": [_advisor_brief(item) for item in selected_followup],
        },
        "what": as_str(primary.get("what")),
        "how": as_str(primary.get("how")),
        "constraints": as_str_list(primary.get("constraints")),
        "constraints_structured": constraints_structured,
        "constraints_structured_summary": constraints_structured_summary,
        "analysis_result": {
            "recommended_advisor": as_str(primary.get("advisor_name")),
            "recommended_partition": as_str(primary.get("partition_id")),
            "what": as_str(primary.get("what")),
            "how": as_str(primary.get("how")),
            "key_call_chain": as_str_list(primary.get("method_call_chain")),
            "key_code_refs": as_str_list(primary.get("code_refs"))[:8],
            "constraint_types": as_str_list(constraints_structured_summary.get("types")),
            "selected_advisors_for_followup_ids": [as_str(item.get("advisor_id")) for item in selected_followup],
            "selected_advisors_for_followup": [_advisor_brief(item) for item in selected_followup],
            "next_step": "进入系统设计阶段，复用该顾问的 how 与 constraints。",
        },
    }


def _build_analysis_process(match_payload: dict[str, Any], report: dict[str, Any], *, run_id: str, question_id: str) -> dict[str, Any]:
    matched_advisors = [item for item in (match_payload.get("matched_advisors") or []) if isinstance(item, dict)]
    top = (matched_advisors or [{}])[0]
    followup = as_str_list((report.get("analysis_result") or {}).get("selected_advisors_for_followup_ids"))
    return {
        "version": "advisor.lab.v1",
        "step": "analyze_advisor_process",
        "generated_at": utc_now(),
        "run_id": run_id,
        "question_id": question_id,
        "requirement": as_str(match_payload.get("requirement")),
        "phase_traces": [
            {
                "phase": "input_parse",
                "details": {
                    "matched_advisor_count": len(matched_advisors),
                    "policy": as_str((match_payload.get("matching_explanation") or {}).get("policy")),
                },
            },
            {
                "phase": "primary_advisor_selection",
                "details": {
                    "selected_advisor": {
                        "advisor_id": as_str(top.get("advisor_id")),
                        "advisor_name": as_str(top.get("advisor_name")),
                        "partition_id": as_str(top.get("partition_id")),
                        "fused_score": top.get("fused_score"),
                    },
                    "top_candidates_preview": report.get("match_summary", {}).get("top_candidates_preview", []),
                    "selected_for_followup_count": len(followup),
                    "selected_for_followup_ids": followup,
                },
            },
            {
                "phase": "analysis_materialization",
                "details": {
                    "what": as_str(report.get("what")),
                    "how": as_str(report.get("how")),
                    "constraints": as_str_list(report.get("constraints")),
                    "constraints_structured_summary": report.get("constraints_structured_summary") or {},
                    "key_call_chain": as_str_list((report.get("analysis_result") or {}).get("key_call_chain")),
                    "key_code_refs": as_str_list((report.get("analysis_result") or {}).get("key_code_refs")),
                },
            },
        ],
    }


def _build_markdown(payload: dict[str, Any]) -> str:
    match_summary = payload.get("match_summary") or {}
    top_advisor = match_summary.get("top_advisor") or {}
    agent_scores = top_advisor.get("agent_scores") or {}

    lines = [
        "# Step2 分析文档",
        "",
        "## 1) 第一步匹配说明",
        f"- 匹配策略：{as_str(match_summary.get('policy'))}",
        f"- query_scope：{as_str((match_summary.get('query_profile') or {}).get('scope'))}",
        f"- 匹配总数：{match_summary.get('matched_count', 0)}",
        f"- 主顾问：{as_str(top_advisor.get('advisor_name'))} ({as_str(top_advisor.get('advisor_id'))})",
        f"- 融合分数：{top_advisor.get('fused_score')}",
        f"- path_matcher：{agent_scores.get('path_matcher', 0)}",
        f"- semantic_matcher：{agent_scores.get('semantic_matcher', 0)}",
        f"- code_matcher：{agent_scores.get('code_matcher', 0)}",
        f"- 匹配理由：{as_str(top_advisor.get('match_reason'))}",
        f"- Top1 what：{as_str(top_advisor.get('what'))}",
        f"- Top1 how：{as_str(top_advisor.get('how'))}",
        "",
        "## 1.1) 纳入后续流程的顾问集合",
    ]
    for item in match_summary.get("selected_for_followup") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- [{item.get('rank')}] {as_str(item.get('advisor_name'))} / project={as_str(item.get('project_name'))} / score={item.get('fused_score')}"
        )

    lines.extend(
        [
            "",
        "## 2) How（实现路径）",
        f"- {as_str(payload.get('how'))}",
        "",
        "## 3) 约束（Constraints）",
        ]
    )
    for item in as_str_list(payload.get("constraints")):
        lines.append(f"- {item}")

    analysis_result = payload.get("analysis_result") or {}
    structured_summary = payload.get("constraints_structured_summary") or {}
    lines.extend(
        [
            "",
            "## 3.1) 结构化约束摘要",
            f"- 类型：{', '.join(as_str_list(structured_summary.get('types')))}",
            f"- has_cfg: {bool(structured_summary.get('has_cfg'))}",
            f"- has_dfg: {bool(structured_summary.get('has_dfg'))}",
            f"- has_io_graph: {bool(structured_summary.get('has_io_graph'))}",
            f"- cfg_node_count: {structured_summary.get('cfg_node_count', 0)}",
            f"- dfg_node_count: {structured_summary.get('dfg_node_count', 0)}",
            f"- io_node_count: {structured_summary.get('io_node_count', 0)}",
            "",
            "## 分析结论",
            f"- 推荐经验库顾问：{as_str(analysis_result.get('recommended_advisor'))}",
            f"- 推荐分区：{as_str(analysis_result.get('recommended_partition'))}",
            f"- 下一步：{as_str(analysis_result.get('next_step'))}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    ensure_runtime(RUNTIME_DIR)
    run_id = as_str(os.environ.get("ADVISOR_RUN_ID")) or "single_run"
    question_id = as_str(os.environ.get("ADVISOR_QUESTION_ID")) or "q00"
    match_payload = read_json(STEP1_MATCH_RESULT_FILE)
    report = _build_analysis(match_payload, run_id=run_id, question_id=question_id)
    process = _build_analysis_process(match_payload, report, run_id=run_id, question_id=question_id)
    write_json(STEP2_ANALYSIS_JSON_FILE, report)
    write_text(STEP2_ANALYSIS_MD_FILE, _build_markdown(report))
    write_json(STEP2_ANALYSIS_PROCESS_FILE, process)
    append_jsonl(
        STAGE_TRACE_FILE,
        {
            "version": "advisor.lab.v1",
            "run_id": run_id,
            "question_id": question_id,
            "step": "step2",
            "stage": "analysis",
            "generated_at": report.get("generated_at"),
            "status": "completed",
            "final_artifacts": [str(STEP2_ANALYSIS_JSON_FILE), str(STEP2_ANALYSIS_MD_FILE)],
            "process_artifact": str(STEP2_ANALYSIS_PROCESS_FILE),
            "summary": {
                "selected_advisor": as_str((report.get("analysis_result") or {}).get("recommended_advisor")),
                "constraint_count": len(as_str_list(report.get("constraints"))),
            },
        },
    )
    print(f"[advisor-lab] step2 done: {STEP2_ANALYSIS_MD_FILE}")


if __name__ == "__main__":
    main()
