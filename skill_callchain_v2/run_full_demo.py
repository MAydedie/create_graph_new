from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / "runtime"
GENERATED_SKILLS_FILE = RUNTIME_DIR / "generated_skills.json"
SCRIPTS = [
    "01_build_clarified_task.py",
    "02_prepare_phase6_contract.py",
    "02_generate_skill_library.py",
    "03_x_path_agent.py",
    "04_y_semantic_agent.py",
    "05_z_code_agent.py",
    "06_fuse_xyz_context.py",
    "07_decompose_requirement.py",
    "08_requirement_analysis.py",
    "09_requirement_spec.py",
    "10_system_design.py",
    "11_detailed_design.py",
    "12_codegen.py",
    "13_run_tests.py",
    "14_error_gate.py",
    "15_demand_gate.py",
    "16_feedback_router.py",
    "17_finalize.py",
]

OPTIONAL_WITH_FALLBACK = {
    "02_prepare_phase6_contract.py",
    "02_generate_skill_library.py",
}


def main() -> None:
    for script_name in SCRIPTS:
        script_path = BASE_DIR / script_name
        print(f"[run-full-demo] start {script_name}")
        result = subprocess.run([sys.executable, str(script_path)], check=False)
        if result.returncode != 0:
            if script_name in OPTIONAL_WITH_FALLBACK and GENERATED_SKILLS_FILE.exists():
                print(f"[run-full-demo] skip  {script_name} (fallback to existing generated_skills.json)")
                continue
            raise subprocess.CalledProcessError(result.returncode, [sys.executable, str(script_path)])
        print(f"[run-full-demo] done  {script_name}")
    print("[run-full-demo] all steps passed")


if __name__ == "__main__":
    main()
