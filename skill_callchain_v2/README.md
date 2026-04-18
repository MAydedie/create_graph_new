# skill_callchain_v2

这是老师新流程的 `v2` 开工目录。

当前已完成 `Phase A` 的最小实现：

- 独立目录骨架
- 统一配置与通用读写
- 复用前门 `QuestionDetector` 的澄清适配器
- 生成 `step1_clarified_task.json`

当前也已完成 `Phase B` 的主要代码骨架：

- `phase6` / hierarchy 适配器
- `SkillCardV2` / `PathEvidence` / `CodeEvidence` 模型
- 动态 skill builders
- `02_generate_skill_library.py`

## 运行方式

```bash
python skill_callchain_v2/00_build_real_phase6_contract.py
python skill_callchain_v2/00_select_phase6_subset.py
python skill_callchain_v2/01_build_clarified_task.py
python skill_callchain_v2/02_prepare_phase6_contract.py
python skill_callchain_v2/02_generate_skill_library.py
python skill_callchain_v2/03_x_path_agent.py
python skill_callchain_v2/04_y_semantic_agent.py
python skill_callchain_v2/05_z_code_agent.py
python skill_callchain_v2/06_fuse_xyz_context.py
python skill_callchain_v2/07_decompose_requirement.py
python skill_callchain_v2/08_requirement_analysis.py
python skill_callchain_v2/09_requirement_spec.py
python skill_callchain_v2/10_system_design.py
python skill_callchain_v2/11_detailed_design.py
python skill_callchain_v2/12_codegen.py
python skill_callchain_v2/13_run_tests.py
python skill_callchain_v2/14_error_gate.py
python skill_callchain_v2/15_demand_gate.py
python skill_callchain_v2/16_feedback_router.py
python skill_callchain_v2/17_finalize.py
python skill_callchain_v2/18_export_skills_to_dot_skill.py
python skill_callchain_v2/run_full_demo.py
python skill_callchain_v2/run_real_subset_demo.py
python skill_callchain_v2/test_pipeline.py
```

## 输入文件

- `skill_callchain_v2/task_input.txt`

## Phase B 前置条件

- `02_generate_skill_library.py` 依赖已有的 `phase6 / function hierarchy` 结果。
- 如果当前 Python 进程里没有可用缓存，生成器会明确报错提示，而不是静默生成假数据。
- 正确使用方式是：先让主系统产出或缓存 `phase6_read_contract / hierarchy_result`，再运行 `02`。
- `02_prepare_phase6_contract.py` 用于把当前可用的 phase6 轻量 contract 导出到 `runtime/phase6_read_contract.json`，供 `02_generate_skill_library.py` 读取。

## 输出文件

- `skill_callchain_v2/runtime/step1_clarified_task.json`
- `skill_callchain_v2/runtime/phase6_read_contract_real.json`
- `skill_callchain_v2/runtime/phase6_read_contract_subset.json`
- `skill_callchain_v2/runtime/phase6_subset_selection_report.json`
- `skill_callchain_v2/runtime/phase6_read_contract.json`
- `skill_callchain_v2/runtime/generated_skills.json`
- `skill_callchain_v2/runtime/step3_x_path_context.json`
- `skill_callchain_v2/runtime/step4_y_semantic_context.json`
- `skill_callchain_v2/runtime/step5_z_code_context.json`
- `skill_callchain_v2/runtime/step6_fused_context.json`
- `skill_callchain_v2/runtime/step7_decomposed_requirements.json`
- `skill_callchain_v2/runtime/step8_requirement_analysis.md`
- `skill_callchain_v2/runtime/step9_requirement_spec.md`
- `skill_callchain_v2/runtime/step10_system_design.md`
- `skill_callchain_v2/runtime/step11_detailed_design.md`
- `skill_callchain_v2/runtime/step12_codegen_result.json`
- `skill_callchain_v2/runtime/step13_test_report.json`
- `skill_callchain_v2/runtime/step14_error_report.json`
- `skill_callchain_v2/runtime/step15_demand_report.json`
- `skill_callchain_v2/runtime/step16_feedback_action.json`
- `skill_callchain_v2/runtime/final_result.json`
- `skill_callchain_v2/runtime/final_result.md`
- `create_graph/.skill/cat-net-main/*.skill.json`
- `create_graph/.skill/cat-net-main/*.skill.md`

## 一键运行

```bash
python skill_callchain_v2/run_full_demo.py
```

## 真实主链+子集运行

```bash
python skill_callchain_v2/run_real_subset_demo.py
```

## 流程测试

```bash
python skill_callchain_v2/test_pipeline.py
```
