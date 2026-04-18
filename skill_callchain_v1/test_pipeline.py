from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / "runtime"


class PipelineTest(unittest.TestCase):
    def test_full_demo_generates_final_files(self) -> None:
        subprocess.run([sys.executable, str(BASE_DIR / "run_full_demo.py")], check=True)
        self.assertTrue((RUNTIME_DIR / "step1_clarified_requirement.json").exists())
        self.assertTrue((RUNTIME_DIR / "step2_skill_matches.json").exists())
        self.assertTrue((RUNTIME_DIR / "step3_call_chain_plan.json").exists())
        self.assertTrue((RUNTIME_DIR / "step4_execution_trace.json").exists())
        self.assertTrue((RUNTIME_DIR / "final_result.md").exists())


if __name__ == "__main__":
    unittest.main()
