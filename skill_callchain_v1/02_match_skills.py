from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_callchain_v1.common import RUNTIME_DIR, SKILL_LIBRARY_FILE, ensure_runtime, load_json, print_output, save_json, similarity, tokenize, utc_now
from skill_callchain_v1.models import SkillCard
from skill_callchain_v1.prompts import X_MATCH_AGENT_PROMPT, Y_MATCH_AGENT_PROMPT, Z_MATCH_AGENT_PROMPT


def score_x(requirement_tokens: List[str], skill: SkillCard) -> float:
    return similarity(requirement_tokens, tokenize(" ".join([skill.name, skill.what, " ".join(skill.tags)])))


def score_y(requirement_text: str, skill: SkillCard) -> float:
    io_text = " ".join(skill.inputs + skill.outputs + [skill.example])
    return similarity(tokenize(requirement_text), tokenize(io_text))


def score_z(requirement_text: str, skill: SkillCard) -> float:
    process_text = f"{skill.how} {skill.workflow_stage}"
    return similarity(tokenize(requirement_text), tokenize(process_text))


def build_result(requirement_payload: Dict[str, Any]) -> Dict[str, Any]:
    skills = [SkillCard.from_dict(item) for item in load_json(SKILL_LIBRARY_FILE)]
    structured = dict(requirement_payload.get("structured_requirement") or {})
    requirement_text = " ".join(
        [
            str(structured.get("goal") or ""),
            str(structured.get("target") or ""),
            str(structured.get("expected_output") or ""),
            " ".join(str(item) for item in structured.get("constraints") or []),
        ]
    )
    requirement_tokens = tokenize(requirement_text)

    ranking = []
    for skill in skills:
        x_score = score_x(requirement_tokens, skill)
        y_score = score_y(requirement_text, skill)
        z_score = score_z(requirement_text, skill)
        final_score = round(x_score * 0.4 + y_score * 0.3 + z_score * 0.3, 4)
        ranking.append(
            {
                "skill_id": skill.skill_id,
                "skill_name": skill.name,
                "workflow_stage": skill.workflow_stage,
                "scores": {
                    "x_agent": round(x_score, 4),
                    "y_agent": round(y_score, 4),
                    "z_agent": round(z_score, 4),
                    "final": final_score,
                },
                "why_selected": [
                    f"What 匹配: {skill.what}",
                    f"How 匹配: {skill.how}",
                    f"Example 匹配: {skill.example}",
                ],
            }
        )

    ranking.sort(key=lambda item: item["scores"]["final"], reverse=True)
    selected = [item for item in ranking if item["scores"]["final"] >= 0.08][:4]

    return {
        "version": "v1.0",
        "step": "match_skills",
        "created_at": utc_now(),
        "input_file": str(RUNTIME_DIR / "step1_clarified_requirement.json"),
        "agents": {
            "x_agent": X_MATCH_AGENT_PROMPT,
            "y_agent": Y_MATCH_AGENT_PROMPT,
            "z_agent": Z_MATCH_AGENT_PROMPT,
        },
        "ranking": ranking,
        "selected_skills": selected,
        "selection_summary": {
            "selected_count": len(selected),
            "strategy": "x/y/z 三视角加权聚合",
            "recommended_next_step": "根据 Top skills 构建调用链计划",
        },
    }


def main() -> None:
    ensure_runtime()
    requirement_payload = load_json(RUNTIME_DIR / "step1_clarified_requirement.json")
    output = build_result(requirement_payload)
    output_path = RUNTIME_DIR / "step2_skill_matches.json"
    save_json(output_path, output)
    print_output("step2 完成", output_path)


if __name__ == "__main__":
    main()
