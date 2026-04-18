from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SCRIPTS = [
    "01_clarify_requirement.py",
    "02_match_skills.py",
    "03_build_call_chain.py",
    "04_run_code_loop.py",
    "05_finalize_result.py",
]


def main() -> None:
    for script_name in SCRIPTS:
        script_path = BASE_DIR / script_name
        print(f"[full-demo] running {script_name}")
        subprocess.run([sys.executable, str(script_path)], check=True)
    print("[full-demo] all steps passed")


if __name__ == "__main__":
    main()
