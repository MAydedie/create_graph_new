# skill_callchain_v1

这是一个和现有主链完全隔离的 `v1.0` 最小实现，只补两件事：

- `xyz skill` 相似度匹配
- 代码编辑循环调用链

## 运行方式

逐步运行：

```bash
python skill_callchain_v1/01_clarify_requirement.py
python skill_callchain_v1/02_match_skills.py
python skill_callchain_v1/03_build_call_chain.py
python skill_callchain_v1/04_run_code_loop.py
python skill_callchain_v1/05_finalize_result.py
```

一键跑全流程：

```bash
python skill_callchain_v1/run_full_demo.py
```

运行测试：

```bash
python skill_callchain_v1/test_pipeline.py
```

## 输出目录

所有中间结果和最终结果都在 `skill_callchain_v1/runtime/`。
