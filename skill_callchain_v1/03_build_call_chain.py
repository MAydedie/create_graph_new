from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_callchain_v1.common import RUNTIME_DIR, ensure_runtime, load_json, print_output, save_json, save_text, utc_now
from skill_callchain_v1.prompts import CHAIN_PLANNER_PROMPT


def main() -> None:
    ensure_runtime()
    clarified = load_json(RUNTIME_DIR / "step1_clarified_requirement.json")
    matched = load_json(RUNTIME_DIR / "step2_skill_matches.json")

    stages = [
        {
            "stage_id": "clarify",
            "owner": "ClarifyAgent",
            "input_file": "requirements_input.txt",
            "output_file": "runtime/step1_clarified_requirement.json",
            "purpose": "把原始需求转成结构化任务包",
            "rollback_to": None,
        },
        {
            "stage_id": "match",
            "owner": "X/Y/Z Match Agents",
            "input_file": "runtime/step1_clarified_requirement.json",
            "output_file": "runtime/step2_skill_matches.json",
            "purpose": "对 skill 库做多视角相似度匹配",
            "rollback_to": "clarify",
        },
        {
            "stage_id": "plan",
            "owner": "ChainPlanner",
            "input_file": "runtime/step2_skill_matches.json",
            "output_file": "runtime/step3_call_chain_plan.json",
            "purpose": "把已选 skill 拼成输入→中间结果→最终结果的调用链",
            "rollback_to": "match",
        },
        {
            "stage_id": "execute_loop",
            "owner": "CodeLoopAgent",
            "input_file": "runtime/step3_call_chain_plan.json",
            "output_file": "runtime/step4_execution_trace.json",
            "purpose": "执行分析、设计、编写、测试、回退闭环",
            "rollback_to": "plan",
        },
        {
            "stage_id": "finalize",
            "owner": "ResultAssembler",
            "input_file": "runtime/step4_execution_trace.json",
            "output_file": "runtime/final_result.md",
            "purpose": "汇总最终结果与可交付物",
            "rollback_to": "execute_loop",
        },
    ]

    plan = {
        "version": "v1.0",
        "step": "build_call_chain",
        "created_at": utc_now(),
        "agent": "ChainPlanner",
        "prompt": CHAIN_PLANNER_PROMPT,
        "goal": clarified["structured_requirement"]["goal"],
        "selected_skills": matched["selected_skills"],
        "call_chain": stages,
        "success_definition": clarified["structured_requirement"]["acceptance"],
    }
    json_path = RUNTIME_DIR / "step3_call_chain_plan.json"
    save_json(json_path, plan)

    md_lines = [
        "# Skill 调用链蓝图 v1.0",
        "",
        f"- 目标：{plan['goal']}",
        f"- 使用 Skill 数：{len(matched['selected_skills'])}",
        f"- 规划 Agent：{plan['agent']}",
        "",
        "## 阶段计划",
        "",
    ]
    for index, stage in enumerate(stages, start=1):
        md_lines.append(f"{index}. `{stage['stage_id']}` | {stage['owner']} | {stage['input_file']} -> {stage['output_file']}")
    md_lines.extend(["", "## 已选 Skill", ""])
    for item in matched["selected_skills"]:
        md_lines.append(f"- `{item['skill_id']}` | 分数 `{item['scores']['final']}` | {item['skill_name']}")
    md_path = RUNTIME_DIR / "step3_call_chain_plan.md"
    save_text(md_path, "\n".join(md_lines))

    print_output("step3 JSON 完成", json_path)
    print_output("step3 Markdown 完成", md_path)


if __name__ == "__main__":
    main()
