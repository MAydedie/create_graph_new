from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
RUNTIME_DIR = BASE_DIR / "runtime"

TASK_INPUT_FILE = BASE_DIR / "task_input.txt"
SKILLS_FILE = PROJECT_DIR / "skill_callchain_v2" / "runtime" / "generated_skills.json"
EXPERIENCE_PATHS_DIR = Path(os.getenv("FH_EXPERIENCE_PATHS_DIR") or (PROJECT_DIR / "output_analysis" / "experience_paths"))
EXPERIENCE_SOURCE_MODE = "experience_first"  # experience_first | experience_only | skill_fallback

STEP1_MATCH_RESULT_FILE = RUNTIME_DIR / "step1_match_result.json"
STEP1_MATCH_PROCESS_FILE = RUNTIME_DIR / "step1_match_process.json"
STEP2_ANALYSIS_JSON_FILE = RUNTIME_DIR / "step2_analysis.json"
STEP2_ANALYSIS_MD_FILE = RUNTIME_DIR / "step2_analysis.md"
STEP2_ANALYSIS_PROCESS_FILE = RUNTIME_DIR / "step2_analysis_process.json"
STEP3_DESIGN_JSON_FILE = RUNTIME_DIR / "step3_design.json"
STEP3_DESIGN_MD_FILE = RUNTIME_DIR / "step3_design.md"
STEP3_DESIGN_PROCESS_FILE = RUNTIME_DIR / "step3_design_process.json"
STEP4_CODEGEN_JSON_FILE = RUNTIME_DIR / "step4_codegen.json"
STEP4_CODEGEN_MD_FILE = RUNTIME_DIR / "step4_codegen.md"
STEP4_CODEGEN_PROCESS_FILE = RUNTIME_DIR / "step4_codegen_process.json"
STAGE_TRACE_FILE = RUNTIME_DIR / "stage_traces.jsonl"

TOP_MATCH_COUNT = 3
