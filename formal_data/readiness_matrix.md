# Stage 1 Formal Data Readiness Matrix

Overall Stage 1 status: `READY_FOR_STAGE2`.

Stage 1 may pass with dataset-level exclusions because all limitations are explicit, optional QA/C2 absence is allowed, and unsupported splits are not runnable.

| Dataset | Readiness | Runnable formal split | Gold/protocol note | Exclusions |
| --- | --- | --- | --- | --- |
| RepoQA | PROTOCOL_READY | Yes, official paper subset | Search Needle Function task; 50 repos/500 needles official subset; syntax-nearest evaluator threshold 0.8 | Go excluded from official subset |
| CodeSearchNet | LOADER_READY | No official relevance scoring | Test rows load, but official 99-query human relevance gold is absent | Official relevance scoring excluded |
| RepoBench-R | PROTOCOL_READY | Yes | golden_snippet_index gold present | None |
| RepoBench v1.1 | PROTOCOL_READY | Yes | gold_snippet_index gold present | None |
| CrossCodeEval | PROTOCOL_READY | Yes, base and aligned variants | groundtruth present | Two short C# OpenAI cosine variants excluded from aligned scoring |
| RepoEval | PROTOCOL_READY | Yes | metadata.ground_truth present | None |
| FEA-Bench | LOADER_READY | No C1 runnable formal split | metadata loads; checkout/test environment unverified | Runnable C1 split excluded |
| SWE-bench Verified | GOLD_READY | No runnable formal split | tests/patches present; Docker/harness unverified | Runnable harness split excluded |

Readiness order: NOT_PROVIDED < PRESENT < FORMAT_VERIFIED < LOADER_READY < GOLD_READY < PROTOCOL_READY.
