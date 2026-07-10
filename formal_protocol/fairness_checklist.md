# Formal Protocol Fairness Checklist

Protocol label: `formal`

- [x] Every B0-B3 and S0-S5 method uses `deepseek-v4-flash` as the same base LLM.
- [x] B1, B2, and S0-S5 share retrieval `top_k: 8` whenever retrieval applies.
- [x] File and graph methods share `BAAI/bge-reranker-base`, candidate limit `25`, output `top_k: 8`, and truncation limit `512` tokens.
- [x] Every method shares an evidence assembly budget of `8192` tokens.
- [x] Every method is capped at `8` retrieved files and `8` retrieved snippets when retrieval applies.
- [x] B3 long-context and S5 final model input are both capped at `16384` tokens.
- [x] Community-summary and path-explanation preprocessing latency, LLM calls, input tokens, and output tokens are accounted separately.
- [x] Any community summary or path explanation included in final context consumes the common evidence and final-input budgets.
- [x] Partial and failed samples remain in the denominator and cannot be silently dropped.
- [x] `scripts/pdf_experiment_runner.py` remains `adapted/preliminary` and is not declared as the formal runner.
- [x] The formal runner remains explicitly pending Stage 2 implementation; Stage 0 freezes declarations only.
- [x] Formal manifests must record the runtime model snapshot hashes, code commit, protocol hashes, and dirty-worktree classification.

Budget values absent from the experiment design were frozen conservatively from repository defaults and server constraints. Each such value records its `decision_source` in `protocol.yaml` or `model_lock.json`.
