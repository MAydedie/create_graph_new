from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_PATH = BASE_DIR.parent
RUNTIME_DIR = BASE_DIR / "runtime"
DEFAULT_SOURCE_PROJECT_PATH = Path(r"D:\代码仓库生图\借鉴项目\CAT-Net-main")
GENERATED_SKILLS_FILE = RUNTIME_DIR / "generated_skills.json"
PHASE6_CONTRACT_FILE = RUNTIME_DIR / "phase6_read_contract.json"
PHASE6_CONTRACT_REAL_FILE = RUNTIME_DIR / "phase6_read_contract_real.json"
PHASE6_CONTRACT_SUBSET_FILE = RUNTIME_DIR / "phase6_read_contract_subset.json"
TASK_INPUT_FILE = BASE_DIR / "task_input.txt"
STEP1_CLARIFIED_TASK_FILE = RUNTIME_DIR / "step1_clarified_task.json"
STEP7_DECOMPOSED_REQUIREMENTS_FILE = RUNTIME_DIR / "step7_decomposed_requirements.json"
STEP8_REQUIREMENT_ANALYSIS_FILE = RUNTIME_DIR / "step8_requirement_analysis.md"
STEP9_REQUIREMENT_SPEC_FILE = RUNTIME_DIR / "step9_requirement_spec.md"
STEP10_SYSTEM_DESIGN_FILE = RUNTIME_DIR / "step10_system_design.md"
STEP11_DETAILED_DESIGN_FILE = RUNTIME_DIR / "step11_detailed_design.md"
STEP12_CODEGEN_RESULT_FILE = RUNTIME_DIR / "step12_codegen_result.json"
STEP13_TEST_REPORT_FILE = RUNTIME_DIR / "step13_test_report.json"
STEP14_ERROR_REPORT_FILE = RUNTIME_DIR / "step14_error_report.json"
STEP15_DEMAND_REPORT_FILE = RUNTIME_DIR / "step15_demand_report.json"
STEP16_FEEDBACK_ACTION_FILE = RUNTIME_DIR / "step16_feedback_action.json"
FINAL_RESULT_JSON_FILE = RUNTIME_DIR / "final_result.json"
FINAL_RESULT_MD_FILE = RUNTIME_DIR / "final_result.md"
STEP4_Y_SEMANTIC_CONTEXT_FILE = RUNTIME_DIR / "step4_y_semantic_context.json"
STEP5_Z_CODE_CONTEXT_FILE = RUNTIME_DIR / "step5_z_code_context.json"

DOT_SKILL_DIR = PROJECT_PATH / ".skill"
DOT_SKILL_SCENARIO_DIR = DOT_SKILL_DIR / "cat-net-main"

XYZ_TOP_N = 5
MAX_CODE_SNIPPETS_PER_SKILL = 3
ENABLE_CACHE = True
DEFAULT_SUBSET_SKILL_COUNT = 12
