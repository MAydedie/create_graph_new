from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
REPORT_DIR = PROJECT_ROOT.parent / "汇报" / "4.9" / "advisor_qa_5cases"
RUNTIME_DIR = BASE_DIR / "runtime"
TASK_INPUT_FILE = BASE_DIR / "task_input.txt"

STAGE_TRACE_FILE = RUNTIME_DIR / "stage_traces.jsonl"

ARTIFACTS = [
    "step1_match_result.json",
    "step1_match_process.json",
    "step2_analysis.json",
    "step2_analysis.md",
    "step2_analysis_process.json",
    "step3_design.json",
    "step3_design.md",
    "step3_design_process.json",
    "step4_codegen.json",
    "step4_codegen.md",
    "step4_codegen_process.json",
]

CASES = [
    {
        "id": "q01",
        "title": "新建图像篡改检测项目",
        "question": "我想从零创建一个图像篡改检测新项目，请按经验库给出最小可运行架构，并说明数据加载、模型主干、训练入口如何衔接。",
    },
    {
        "id": "q02",
        "title": "扩充GitHub分类仓库为可解释输出",
        "question": "我拿到一个 GitHub 上的图像分类仓库，想扩展成可解释输出和中间特征可视化，请给我改造分析与代码落点建议。",
    },
    {
        "id": "q03",
        "title": "多数据集统一训练改造",
        "question": "我想把一个已有检测项目改成多数据集统一训练，要求支持不同输入格式与公共评估接口，请按经验库给我设计与代码草案。",
    },
    {
        "id": "q04",
        "title": "模块化配置与约束校验",
        "question": "我有一个 Python 视觉项目，想增加模块化配置和约束校验（输入输出、CFG/DFG）机制，请给出顾问匹配、分析、设计和实现建议。",
    },
    {
        "id": "q05",
        "title": "推理服务化扩展",
        "question": "我拿到一个 GitHub 的模型仓库，想扩充推理服务化（批量推理+日志追踪+错误回退），请基于经验库给出端到端改造方案和关键代码骨架。",
    },
]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_case_artifacts(case_dir: Path) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    for name in ARTIFACTS:
        src = RUNTIME_DIR / name
        if src.exists():
            shutil.copy2(src, case_dir / name)


def _stage_process_summary(process_payload: dict[str, Any]) -> str:
    lines: list[str] = []
    for phase in process_payload.get("phase_traces") or []:
        if not isinstance(phase, dict):
            continue
        phase_name = str(phase.get("phase") or "unknown_phase")
        details = phase.get("details") or {}
        lines.extend(
            [
                f"### 阶段过程: {phase_name}",
                "```json",
                json.dumps(details, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _build_case_qa_markdown(case: dict[str, str], case_dir: Path) -> str:
    step1 = _read_json(case_dir / "step1_match_result.json")
    step1_process = _read_json(case_dir / "step1_match_process.json")
    step2 = _read_json(case_dir / "step2_analysis.json")
    step2_process = _read_json(case_dir / "step2_analysis_process.json")
    step3 = _read_json(case_dir / "step3_design.json")
    step3_process = _read_json(case_dir / "step3_design_process.json")
    step4 = _read_json(case_dir / "step4_codegen.json")
    step4_process = _read_json(case_dir / "step4_codegen_process.json")

    top_advisor = ((step1.get("matched_advisors") or [{}])[0] or {}).get("advisor_name", "")
    lines = [
        f"# {case['id']} - {case['title']} 问答全流程",
        "",
        "## 用户问题",
        case["question"],
        "",
        "## Step1 匹配（最终输出）",
        f"- Top1 顾问：{top_advisor}",
        f"- 文件：{case_dir / 'step1_match_result.json'}",
        "",
        "## Step1 匹配（中粒度过程）",
        _stage_process_summary(step1_process),
        "## Step2 分析（最终输出）",
        f"- 文件：{case_dir / 'step2_analysis.json'}",
        f"- 文档：{case_dir / 'step2_analysis.md'}",
        "",
        "## Step2 分析（中粒度过程）",
        _stage_process_summary(step2_process),
        "## Step3 设计（最终输出）",
        f"- 文件：{case_dir / 'step3_design.json'}",
        f"- 文档：{case_dir / 'step3_design.md'}",
        "",
        "## Step3 设计（中粒度过程）",
        _stage_process_summary(step3_process),
        "## Step4 代码草案（最终输出）",
        f"- 文件：{case_dir / 'step4_codegen.json'}",
        f"- 文档：{case_dir / 'step4_codegen.md'}",
        "",
        "## Step4 代码草案（中粒度过程）",
        _stage_process_summary(step4_process),
        "## 关键结论",
        f"- 推荐顾问：{(step2.get('analysis_result') or {}).get('recommended_advisor', '')}",
        f"- 推荐分区：{(step2.get('analysis_result') or {}).get('recommended_partition', '')}",
        f"- 设计目标：{step3.get('design_goal', '')}",
        f"- 代码依据：{(step4.get('codegen_basis') or {}).get('analysis_summary', '')}",
        "",
    ]
    return "\n".join(lines)


def _run_case(case: dict[str, str], run_id: str) -> dict[str, str]:
    TASK_INPUT_FILE.write_text(case["question"], encoding="utf-8")

    env = os.environ.copy()
    env["ADVISOR_RUN_ID"] = run_id
    env["ADVISOR_QUESTION_ID"] = case["id"]

    subprocess.run([sys.executable, str(BASE_DIR / "run_pipeline.py")], check=True, env=env)

    case_dir = REPORT_DIR / case["id"]
    _copy_case_artifacts(case_dir)

    qa_path = case_dir / f"{case['id']}_问答全流程.md"
    _write_text(qa_path, _build_case_qa_markdown(case, case_dir))
    return {
        "case_id": case["id"],
        "title": case["title"],
        "question": case["question"],
        "qa_file": str(qa_path),
    }


def _build_index(results: list[dict[str, str]], run_id: str) -> str:
    lines = [
        "# Agent顾问群 5问测试总览",
        "",
        f"- run_id: {run_id}",
        f"- 生成时间: {datetime.now().isoformat()}",
        f"- 运行目录: {REPORT_DIR}",
        "",
        "## 测试用例",
    ]
    for item in results:
        lines.extend(
            [
                f"### {item['case_id']} - {item['title']}",
                f"- 问题: {item['question']}",
                f"- 全流程问答文件: {item['qa_file']}",
                "",
            ]
        )

    lines.extend(
        [
            "## 统一中间过程文件",
            f"- stage trace: {RUNTIME_DIR / 'stage_traces.jsonl'}",
            "",
            "## 每个用例包含",
            "- Step1 最终 + Step1 中粒度过程",
            "- Step2 最终 + Step2 中粒度过程",
            "- Step3 最终 + Step3 中粒度过程",
            "- Step4 最终 + Step4 中粒度过程",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    run_id = datetime.now().strftime("batch_%Y%m%d_%H%M%S")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if STAGE_TRACE_FILE.exists():
        STAGE_TRACE_FILE.unlink()

    results: list[dict[str, str]] = []
    for case in CASES:
        print(f"[advisor-batch] running {case['id']} - {case['title']}")
        results.append(_run_case(case, run_id))

    _write_text(REPORT_DIR / "00_5问测试总览.md", _build_index(results, run_id))
    print(f"[advisor-batch] done: {REPORT_DIR}")


if __name__ == "__main__":
    main()
