from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_callchain_v1.common import RUNTIME_DIR, ensure_runtime, load_json, print_output, save_json, save_text, utc_now


def main() -> None:
    ensure_runtime()
    clarified = load_json(RUNTIME_DIR / "step1_clarified_requirement.json")
    matched = load_json(RUNTIME_DIR / "step2_skill_matches.json")
    plan = load_json(RUNTIME_DIR / "step3_call_chain_plan.json")
    trace = load_json(RUNTIME_DIR / "step4_execution_trace.json")

    final_json = {
        "version": "v1.0",
        "created_at": utc_now(),
        "goal": clarified["structured_requirement"]["goal"],
        "selected_skill_ids": [item["skill_id"] for item in matched["selected_skills"]],
        "call_chain_stage_count": len(plan["call_chain"]),
        "execution_status": trace["final_status"],
        "artifacts": [
            "runtime/step1_clarified_requirement.json",
            "runtime/step2_skill_matches.json",
            "runtime/step3_call_chain_plan.json",
            "runtime/step3_call_chain_plan.md",
            "runtime/step4_execution_trace.json",
            "runtime/iteration_1_code.py",
            "runtime/iteration_2_code.py",
            "runtime/final_result.json",
            "runtime/final_result.md",
        ],
    }
    json_path = RUNTIME_DIR / "final_result.json"
    save_json(json_path, final_json)

    md_lines = [
        "# Skill 化调用链最终结果 v1.0",
        "",
        f"- 目标：{final_json['goal']}",
        f"- 最终状态：`{final_json['execution_status']}`",
        f"- 已选 Skill：`{', '.join(final_json['selected_skill_ids'])}`",
        f"- 调用链阶段数：`{final_json['call_chain_stage_count']}`",
        "",
        "## 关键结论",
        "",
        "- 旧的 project→笔记→agent 主链未改动，本实现完全独立。",
        "- 新增了 x/y/z 三个匹配 agent 的相似度聚合。",
        "- 新增了分析→设计→编写→测试→回退 的代码循环链。",
        "- 每一步都有中间结果文件，可被下一步脚本直接读取。",
        "",
        "## 运行顺序",
        "",
        "1. `python skill_callchain_v1/01_clarify_requirement.py`",
        "2. `python skill_callchain_v1/02_match_skills.py`",
        "3. `python skill_callchain_v1/03_build_call_chain.py`",
        "4. `python skill_callchain_v1/04_run_code_loop.py`",
        "5. `python skill_callchain_v1/05_finalize_result.py`",
        "",
        "## 产物",
        "",
    ]
    for artifact in final_json["artifacts"]:
        md_lines.append(f"- `{artifact}`")
    md_path = RUNTIME_DIR / "final_result.md"
    save_text(md_path, "\n".join(md_lines))

    print_output("final JSON 完成", json_path)
    print_output("final Markdown 完成", md_path)


if __name__ == "__main__":
    main()
