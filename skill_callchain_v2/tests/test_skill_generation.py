from __future__ import annotations

import json
from pathlib import Path
import unittest


BASE_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = BASE_DIR / "runtime"


class SkillGenerationTest(unittest.TestCase):
    def test_generated_skills_exists_and_has_skills(self) -> None:
        payload = json.loads((RUNTIME_DIR / "generated_skills.json").read_text(encoding="utf-8"))
        self.assertIn("skills", payload)
        self.assertGreaterEqual(len(payload["skills"]), 1)

    def test_generated_skill_contains_callchain_and_locator(self) -> None:
        payload = json.loads((RUNTIME_DIR / "generated_skills.json").read_text(encoding="utf-8"))
        skills = payload.get("skills") or []
        self.assertGreaterEqual(len(skills), 1)
        first_skill = skills[0]
        self.assertIn("method_call_chain", first_skill)
        self.assertIn("chain_explanation", first_skill)
        self.assertIn("approach_graph", first_skill)
        self.assertIn("source_locations", first_skill)
        self.assertIn("retrieval_hints", first_skill)
        self.assertIsInstance(first_skill.get("method_call_chain"), list)
        self.assertIsInstance(first_skill.get("chain_explanation"), list)
        self.assertIsInstance(first_skill.get("approach_graph"), list)
        self.assertIsInstance(first_skill.get("source_locations"), list)
        self.assertIsInstance(first_skill.get("retrieval_hints"), dict)

    def test_summary_is_concise(self) -> None:
        payload = json.loads((RUNTIME_DIR / "generated_skills.json").read_text(encoding="utf-8"))
        for skill in payload.get("skills") or []:
            summary = str(skill.get("summary") or "")
            self.assertLessEqual(len(summary), 120)


if __name__ == "__main__":
    unittest.main()
