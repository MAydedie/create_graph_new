from __future__ import annotations

import json
from pathlib import Path
import unittest


BASE_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = BASE_DIR / "runtime"


class XyzContextTest(unittest.TestCase):
    def test_fused_context_contains_core_sections(self) -> None:
        payload = json.loads((RUNTIME_DIR / "step6_fused_context.json").read_text(encoding="utf-8"))
        self.assertIn("task_summary", payload)
        self.assertIn("recommended_skills", payload)
        self.assertIn("path_context", payload)
        self.assertIn("semantic_context", payload)
        self.assertIn("code_context", payload)

    def test_semantic_selection_ignores_pipeline_gate_terms(self) -> None:
        step1 = json.loads((RUNTIME_DIR / "step1_clarified_task.json").read_text(encoding="utf-8"))
        step4 = json.loads((RUNTIME_DIR / "step4_y_semantic_context.json").read_text(encoding="utf-8"))

        structured = step1.get("structured_requirement") or {}
        pipeline_constraints = structured.get("pipeline_constraints") or []
        if not any("gate" in str(item).lower() for item in pipeline_constraints):
            self.skipTest("当前场景未包含 pipeline gate 约束，不执行该断言")

        for item in step4.get("selected_skills") or []:
            reason = str(item.get("reason") or "").lower()
            self.assertNotIn("关键词重叠: error", reason)


if __name__ == "__main__":
    unittest.main()
