from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_callchain_v1.common import INPUT_FILE, ensure_runtime, print_output, save_json, tokenize, utc_now, read_text
from skill_callchain_v1.prompts import CLARIFY_AGENT_PROMPT


def main() -> None:
    runtime_dir = ensure_runtime()
    raw_requirement = read_text(INPUT_FILE).strip()

    payload = {
        "version": "v1.0",
        "step": "clarify_requirement",
        "created_at": utc_now(),
        "agent": "ClarifyAgent",
        "prompt": CLARIFY_AGENT_PROMPT,
        "raw_requirement": raw_requirement,
        "structured_requirement": {
            "goal": "在不干扰旧链路的前提下，新增一套可运行的 skill 化与代码循环链 v1.0。",
            "target": "create_graph/skill_callchain_v1 独立目录及其脚本、运行产物、汇报蓝图文档。",
            "expected_output": "可顺序运行的多个 Python 脚本、每步中间结果文件、最终结果文件、整条流程测试。",
            "constraints": [
                "不重复 project→笔记→agent 既有能力",
                "聚焦 xyz skill 相似度匹配",
                "聚焦代码编辑循环调用链",
                "先做 agent + prompt 级别 v1.0",
                "不嵌入前端",
                "和旧逻辑分隔开",
            ],
            "acceptance": [
                "运行 01-05 脚本可以逐步生成中间结果",
                "后一步脚本读取前一步输出",
                "run_full_demo.py 可串行跑完整流程",
                "包含 xyz agent 匹配分数与聚合结果",
                "包含代码循环链的测试与回退记录",
            ],
            "keywords": tokenize(raw_requirement),
        },
    }

    output_path = runtime_dir / "step1_clarified_requirement.json"
    save_json(output_path, payload)
    print_output("step1 完成", output_path)


if __name__ == "__main__":
    main()
