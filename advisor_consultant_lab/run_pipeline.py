from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SCRIPTS = (
    "01_match_advisors.py",
    "02_analyze_advisor.py",
    "03_design_solution.py",
    "04_generate_code.py",
)


def main() -> None:
    for script in SCRIPTS:
        script_path = BASE_DIR / script
        print(f"[advisor-lab] running: {script_path.name}")
        subprocess.run([sys.executable, str(script_path)], check=True)
    print("[advisor-lab] pipeline finished")


if __name__ == "__main__":
    main()
