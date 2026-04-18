# advisor_consultant_lab

独立顾问流程实验目录（不接入 `app.py` 启动链）。

## 目标

- 目录独立：只在本目录脚本中运行，不被 `python app.py` 自动加载。
- 流程固定：需求输入 -> 三匹配 Agent -> 分析 -> 设计 -> 代码生成。
- 过程可见：每一步都输出到 `runtime/`，便于你逐步审阅并确认。

## 目录说明

- `01_match_advisors.py`：三个匹配 Agent（path/semantic/code）对经验库顾问打分，选出 Top3。
- `02_analyze_advisor.py`：输出“匹配说明 + how + 约束”的分析文档。
- `03_design_solution.py`：基于分析结果输出系统设计文档。
- `04_generate_code.py`：基于分析文档 + 设计文档 + 源码调用线索输出代码草案。
- `runtime/`：中间产物目录（全部可审阅）。

## 运行方式

```bash
python advisor_consultant_lab/run_pipeline.py
```

批量 5 问测试：

```bash
python advisor_consultant_lab/run_batch_questions.py
```

或单步运行：

```bash
python advisor_consultant_lab/01_match_advisors.py
python advisor_consultant_lab/02_analyze_advisor.py
python advisor_consultant_lab/03_design_solution.py
python advisor_consultant_lab/04_generate_code.py
```

## 输入与输出

- 输入需求：`advisor_consultant_lab/task_input.txt`
- 经验库来源（优先）：`output_analysis/experience_paths/*.json`
- 兼容兜底来源：`skill_callchain_v2/runtime/generated_skills.json`

输出文件：

- `advisor_consultant_lab/runtime/step1_match_result.json`
- `advisor_consultant_lab/runtime/step1_match_process.json`
- `advisor_consultant_lab/runtime/step2_analysis.json`
- `advisor_consultant_lab/runtime/step2_analysis.md`
- `advisor_consultant_lab/runtime/step2_analysis_process.json`
- `advisor_consultant_lab/runtime/step3_design.json`
- `advisor_consultant_lab/runtime/step3_design.md`
- `advisor_consultant_lab/runtime/step3_design_process.json`
- `advisor_consultant_lab/runtime/step4_codegen.json`
- `advisor_consultant_lab/runtime/step4_codegen.md`
- `advisor_consultant_lab/runtime/step4_codegen_process.json`
- `advisor_consultant_lab/runtime/stage_traces.jsonl`
