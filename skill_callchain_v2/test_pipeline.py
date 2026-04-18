from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
TEST_MODULES = [
    "skill_callchain_v2.tests.test_skill_generation",
    "skill_callchain_v2.tests.test_xyz_context",
    "skill_callchain_v2.tests.test_pipeline_flow",
]


def main() -> None:
    for module_name in TEST_MODULES:
        print(f"[test-pipeline] start {module_name}")
        subprocess.run([sys.executable, "-m", "unittest", module_name], check=True, cwd=BASE_DIR.parent)
        print(f"[test-pipeline] done  {module_name}")
    print("[test-pipeline] all tests passed")


if __name__ == "__main__":
    main()
