from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import unittest


BASE_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = BASE_DIR / "runtime"


class PipelineFlowTest(unittest.TestCase):
    def test_run_full_demo_and_final_result(self) -> None:
        subprocess.run([sys.executable, str(BASE_DIR / "run_full_demo.py")], check=True)
        self.assertTrue((RUNTIME_DIR / "step12_codegen_result.json").exists())
        self.assertTrue((RUNTIME_DIR / "step13_test_report.json").exists())
        self.assertTrue((RUNTIME_DIR / "step14_error_report.json").exists())
        self.assertTrue((RUNTIME_DIR / "step15_demand_report.json").exists())
        self.assertTrue((RUNTIME_DIR / "step16_feedback_action.json").exists())
        self.assertTrue((RUNTIME_DIR / "final_result.md").exists())


if __name__ == "__main__":
    unittest.main()
