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
STEP2_ANALYSIS_JSON_FILE = cfg.STEP2_ANALYSIS_JSON_FILE
STEP3_DESIGN_JSON_FILE = cfg.STEP3_DESIGN_JSON_FILE
STEP3_DESIGN_MD_FILE = cfg.STEP3_DESIGN_MD_FILE
STEP3_DESIGN_PROCESS_FILE = cfg.STEP3_DESIGN_PROCESS_FILE
STAGE_TRACE_FILE = cfg.STAGE_TRACE_FILE


def _build_design(analysis_payload: dict[str, Any], *, run_id: str, question_id: str) -> dict[str, Any]:
    analysis_result = analysis_payload.get("analysis_result") or {}
    constraints = as_str_list(analysis_payload.get("constraints"))
    constraints_structured = analysis_payload.get("constraints_structured") if isinstance(analysis_payload.get("constraints_structured"), dict) else {}
    constraints_structured_summary = (
        analysis_payload.get("constraints_structured_summary")
        if isinstance(analysis_payload.get("constraints_structured_summary"), dict)
        else {}
    )
    how_text = as_str(analysis_payload.get("how"))

    return {
        "version": "advisor.lab.v1",
        "step": "design_solution",
        "generated_at": utc_now(),
        "run_id": run_id,
        "question_id": question_id,
        "input_file": str(STEP2_ANALYSIS_JSON_FILE),
        "design_goal": as_str(analysis_payload.get("requirement")),
        "architecture_overview": (
            f"以 {as_str(analysis_result.get('recommended_advisor'))} 的调用链为核心，"
            "组织为数据加载层、模型主干层、训练入口层三段式最小可运行架构。"
        ),
        "interface_contract": (
            f"遵循约束类型 {', '.join(as_str_list((constraints_structured_summary or {}).get('types')))}；"
            "关键接口需显式声明输入输出并保持 CFG/DFG 路径一致。"
        ),
        "selected_advisor": {
            "name": as_str(analysis_result.get("recommended_advisor")),
            "partition": as_str(analysis_result.get("recommended_partition")),
        },
        "design_principles": [
            "匹配与顾问能力解耦，匹配 Agent 只负责检索，不直接做业务实现。",
            "分析阶段必须输出匹配依据、how、constraints 三类信息。",
            "设计阶段复用分析结果，不重复检索经验库。",
            "代码生成阶段必须引用调用链和源码锚点，避免脱离经验库编写。",
        ],
        "pipeline_design": [
            {
                "stage": "matching",
                "inputs": ["用户需求", "经验库技能卡"],
                "outputs": ["Top3 顾问候选", "三匹配 Agent 分数"],
                "notes": "path/semantic/code 三 Agent 并行评分，融合排序。",
            },
            {
                "stage": "analysis",
                "inputs": ["Top3 顾问候选", "主顾问 what/how/constraints"],
                "outputs": ["分析文档", "分析结论"],
                "notes": "必须包含第一步匹配说明、how、constraints。",
            },
            {
                "stage": "design",
                "inputs": ["分析结论", "how", "constraints"],
                "outputs": ["系统设计文档"],
                "notes": "输出模块划分、数据流、接口契约。",
            },
            {
                "stage": "codegen",
                "inputs": ["分析文档", "设计文档", "调用链源码线索"],
                "outputs": ["代码草案", "文件级实施建议"],
                "notes": "代码草案需明确入口函数和可落地文件锚点。",
            },
        ],
        "how_used_in_design": how_text,
        "constraints_used_in_design": constraints,
        "constraints_structured_used_in_design": constraints_structured,
        "constraints_structured_summary_used_in_design": constraints_structured_summary,
    }


def _build_design_process(analysis_payload: dict[str, Any], report: dict[str, Any], *, run_id: str, question_id: str) -> dict[str, Any]:
    pipeline_design = [item for item in (report.get("pipeline_design") or []) if isinstance(item, dict)]
    return {
        "version": "advisor.lab.v1",
        "step": "design_solution_process",
        "generated_at": utc_now(),
        "run_id": run_id,
        "question_id": question_id,
        "requirement": as_str(analysis_payload.get("requirement")),
        "phase_traces": [
            {
                "phase": "input_analysis_context",
                "details": {
                    "recommended_advisor": as_str((analysis_payload.get("analysis_result") or {}).get("recommended_advisor")),
                    "recommended_partition": as_str((analysis_payload.get("analysis_result") or {}).get("recommended_partition")),
                    "constraint_count": len(as_str_list(analysis_payload.get("constraints"))),
                },
            },
            {
                "phase": "pipeline_design_derivation",
                "details": {
                    "design_principles": as_str_list(report.get("design_principles")),
                    "pipeline_stages": [
                        {
                            "stage": as_str(item.get("stage")),
                            "inputs": as_str_list(item.get("inputs")),
                            "outputs": as_str_list(item.get("outputs")),
                            "notes": as_str(item.get("notes")),
                        }
                        for item in pipeline_design
                    ],
                },
            },
            {
                "phase": "how_constraints_projection",
                "details": {
                    "how_used_in_design": as_str(report.get("how_used_in_design")),
                    "constraints_used_in_design": as_str_list(report.get("constraints_used_in_design")),
                    "constraints_structured_summary_used_in_design": report.get("constraints_structured_summary_used_in_design") or {},
                },
            },
        ],
    }


def _build_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Step3 设计文档",
        "",
        "## 设计目标",
        f"- {as_str(payload.get('design_goal'))}",
        f"- 架构草图：{as_str(payload.get('architecture_overview'))}",
        f"- 接口协议：{as_str(payload.get('interface_contract'))}",
        "",
        "## 选定顾问",
        f"- 名称：{as_str((payload.get('selected_advisor') or {}).get('name'))}",
        f"- 分区：{as_str((payload.get('selected_advisor') or {}).get('partition'))}",
        "",
        "## 设计原则",
    ]
    for item in as_str_list(payload.get("design_principles")):
        lines.append(f"- {item}")

    lines.extend(["", "## 流程设计"])
    for stage in payload.get("pipeline_design") or []:
        if not isinstance(stage, dict):
            continue
        lines.append(f"- 阶段 `{as_str(stage.get('stage'))}`")
        lines.append(f"  - 输入：{', '.join(as_str_list(stage.get('inputs')))}")
        lines.append(f"  - 输出：{', '.join(as_str_list(stage.get('outputs')))}")
        lines.append(f"  - 说明：{as_str(stage.get('notes'))}")

    lines.extend(
        [
            "",
            "## 复用的 How 与约束",
            f"- How：{as_str(payload.get('how_used_in_design'))}",
            "- Constraints：",
        ]
    )
    for item in as_str_list(payload.get("constraints_used_in_design")):
        lines.append(f"  - {item}")

    structured_summary = payload.get("constraints_structured_summary_used_in_design") or {}
    lines.extend(
        [
            "",
            "## 结构化约束摘要",
            f"- 类型：{', '.join(as_str_list(structured_summary.get('types')))}",
            f"- has_cfg: {bool(structured_summary.get('has_cfg'))}",
            f"- has_dfg: {bool(structured_summary.get('has_dfg'))}",
            f"- has_io_graph: {bool(structured_summary.get('has_io_graph'))}",
            f"- cfg_node_count: {structured_summary.get('cfg_node_count', 0)}",
            f"- dfg_node_count: {structured_summary.get('dfg_node_count', 0)}",
            f"- io_node_count: {structured_summary.get('io_node_count', 0)}",
        ]
    )

    return "\n".join(lines) + "\n"


def main() -> None:
    ensure_runtime(RUNTIME_DIR)
    run_id = as_str(os.environ.get("ADVISOR_RUN_ID")) or "single_run"
    question_id = as_str(os.environ.get("ADVISOR_QUESTION_ID")) or "q00"
    analysis_payload = read_json(STEP2_ANALYSIS_JSON_FILE)
    report = _build_design(analysis_payload, run_id=run_id, question_id=question_id)
    process = _build_design_process(analysis_payload, report, run_id=run_id, question_id=question_id)
    write_json(STEP3_DESIGN_JSON_FILE, report)
    write_text(STEP3_DESIGN_MD_FILE, _build_markdown(report))
    write_json(STEP3_DESIGN_PROCESS_FILE, process)
    append_jsonl(
        STAGE_TRACE_FILE,
        {
            "version": "advisor.lab.v1",
            "run_id": run_id,
            "question_id": question_id,
            "step": "step3",
            "stage": "design",
            "generated_at": report.get("generated_at"),
            "status": "completed",
            "final_artifacts": [str(STEP3_DESIGN_JSON_FILE), str(STEP3_DESIGN_MD_FILE)],
            "process_artifact": str(STEP3_DESIGN_PROCESS_FILE),
            "summary": {
                "selected_advisor": as_str((report.get("selected_advisor") or {}).get("name")),
                "pipeline_stage_count": len([item for item in (report.get("pipeline_design") or []) if isinstance(item, dict)]),
            },
        },
    )
    print(f"[advisor-lab] step3 done: {STEP3_DESIGN_MD_FILE}")


if __name__ == "__main__":
    main()
