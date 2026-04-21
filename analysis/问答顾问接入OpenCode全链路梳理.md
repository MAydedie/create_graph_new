# 问答顾问接入OpenCode全链路梳理

## 1. 文档范围

本文只基于用户指定的已核实行号整理，不补充未经这些锚点证明的行为。核心链路如下：

`qa_ui/index.html -> qa_button_app.py -> app/services/conversation_service.py -> app/services/multi_agent_service.py -> app/services/opencode_kernel_service.py`

## 2. 先讲人话

这套问答链路本质上分成两段。

第一段是“问答前台”。页面 `qa_ui/index.html` 负责收集 `project_path`、问题文本、澄清回复、输出目录、经验库选择，并通过 `/api/conversations/session/start`、`/api/conversations/<conversation_id>/reply`、`/api/multi_agent/session/start` 等接口驱动后端，还会用 SSE 持续拉取会话事件和状态，见 `qa_ui/index.html` 第 15-17、19、21、23、25、27、28、29、30、31 行。

第二段是“执行后场”。`conversation_service.py` 先把本轮问答建成一个 conversation turn，再决定这一轮是继续澄清、做检索回答、普通聊天，还是把任务交给 multi-agent 执行链，见 `conversation_service.py` 第 1653、1826-1880、1883-2042、2044-2256、2258-2299、2302-2523、2543-2622、2625-2642、2645-2653、2808-2884、2980-2995、2998-3096 行。

顾问怎么接进 OpenCode，是这份文档的重点。结论很明确：**在这个仓库里，advisor 不是 OpenCode 的内建角色。** 项目并没有把 advisor 直接注册成 OpenCode 的 builtin role，而是单独跑一个 advisor sidecar。这个 sidecar 在 `advisor_consultant_lab` 目录里独立运行，不走主应用自动启动链，见 `advisor_consultant_lab/README.md` 第 5-17 行。multi-agent 阶段会按条件决定是否调用 sidecar，把 sidecar 的运行产物整理成 `advisor_packet`，再把它并入 `analysis` 和 `output_protocol`，最后把这些上下文一起交给 OpenCode 内核桥接层，见 `multi_agent_service.py` 第 421-476、479-557、560-651、654-729、2074-2174、2900-3175+、2997-3018、3201-3513 行，以及 `opencode_kernel_service.py` 第 114-160、163-292 行。

## 3. 问答全链路总览

### 3.1 页面入口

`qa_ui/index.html` 做了几件事。

1. 第 15-17 行加载经验库和 workbench 项目状态。
2. 第 19 行处理 SSE 事件，把 `turn.state_changed`、`clarification.requested`、`multi_agent.*` 等状态写回页面。
3. 第 21 行渲染待澄清问题。
4. 第 23 行建立 SSE 长连接，监听 `/api/conversations/<conversation_id>/events`。
5. 第 25 行轮询 `/api/conversations/session/<session_id>/status`。
6. 第 27 行在超时或刷新后恢复 pending question 或 task handoff。
7. 第 28 行串起一次完整 conversation flow，最终再取 `/result`。
8. 第 29 行提交新问题或澄清回复。
9. 第 30 行手动触发 multi-agent。
10. 第 31 行把按钮事件绑到上述函数。

### 3.2 Flask API 入口

`qa_button_app.py` 把单页 UI 和后端服务粘起来。

1. 第 40-42 行提供 `/`，直接返回 `qa_ui/index.html`。
2. 第 45-77 行暴露 conversation 相关接口，包括 start、status、result、messages、reply、events、export_runbook。
3. 第 80-92 行暴露 multi-agent 的 start、status、result。
4. 第 95-112 行暴露经验库和 workbench 入口，给页面训练经验库、查看项目状态。

## 4. 按数据流顺序展开

### 4.1 提问进入 conversation turn

前端在 `submit()` 中组装请求体。这里会把 `project_path`、`query` 或 `answer`、`clarification_context`、`output_root`、`auto_apply_output`、`opencode_enabled` 一起发给后端，见 `qa_ui/index.html` 第 29-30 行。

后端在 `api_conversation_session_start()` 中校验这些字段，创建 session，并用后台线程跑 `_run_conversation_turn()`，见 `conversation_service.py` 第 2543-2622 行。真正的 turn 元数据由 `_create_conversation_session()` 生成，其中会保存：

1. `sessionId`
2. `conversationId`
3. `projectPath`
4. `query`
5. `clarificationContext`
6. `outputRoot`
7. `autoApplyOutput`

对应代码在 `conversation_service.py` 第 1653 行。

这些会话态和消息态由 `data_accessor.py` 保管。

1. multi-agent session 缓存在第 229-235 行。
2. conversation turn session 缓存在第 249-264 行。
3. conversation 默认结构在第 280-299 行。
4. conversation 对象创建在第 399-406 行。
5. 消息追加在第 421-441 行。
6. part 追加在第 456-474 行。
7. pending question 存取在第 476-494 行。
8. question reply 存取在第 505-529 行。
9. key facts memory 存取在第 581-603 行。
10. 事件日志追加在第 614-643 行。

### 4.2 本轮动作决策

`_run_conversation_turn()` 先写入用户消息和消息 part，再进入 `decide` 阶段，见 `conversation_service.py` 第 1883-2042 行。

这一段会调用 `QuestionDetector` 做两层判断：

1. `QuestionDetector` 类定义在 `question_detector.py` 第 12 行。
2. `detect_task_mode()` 在第 102 行，用关键词把任务偏向分成 `write_new_code` 或 `modify_existing`。
3. `assess_clarification_need()` 在第 111 行，综合原问题、最新回复、选项标签和上下文，判断是否还要继续澄清。

如果结果是 `clarify`，后端会生成待澄清问题，写入 `pendingQuestion`，追加 assistant 消息和 `question_request` part，并把结果收口为 `nextStep = ask_clarification`，见 `conversation_service.py` 第 1981-2042 行。

如果结果是 `run_retrieval`，后端会启动检索工具，追加 `tool_call`、`tool_result`、assistant answer，并把结果收口为 `nextStep = retrieval_answer`，见 `conversation_service.py` 第 2044-2256 行。底层检索入口是 `codebase_retrieval_service.py` 第 752 行的 `run_codebase_retrieval()`。

如果结果是 `general_chat`，就直接生成普通回答，见 `conversation_service.py` 第 2258-2299 行。

如果前三种都不是，就进入代码流 handoff，见下一节。

### 4.3 从 conversation handoff 到 multi-agent

`conversation_service.py` 第 2302-2523 行会构造 `handoff`，其中带上：

1. `project_path`
2. `query`
3. `task_mode`
4. `partition_id`
5. `selected_node`
6. `clarification_context`
7. `output_root`
8. `auto_apply_output`
9. `opencode_enabled`

如果前端打开 `auto_start_multi_agent`，这里有两种走法。

1. 先尝试 `_try_inline_codegen_result()`，也就是在 conversation 内部直接创建 multi-agent 会话并同步跑完，见 `conversation_service.py` 第 1826-1880、2315-2417 行。
2. 如果内联失败，或者没有走内联，就异步创建 multi-agent session，后台线程执行 `_run_multi_agent_session()`，同时把 `task_handoff` part 写进会话，见 `conversation_service.py` 第 2430-2523 行。

前端随后会通过 `/api/multi_agent/session/start`、`/status`、`/result` 继续推进，接口定义在 `qa_button_app.py` 第 80-92 行，前端调用在 `qa_ui/index.html` 第 30 行。

### 4.4 multi-agent 会话初始化

`multi_agent_service.py` 第 1141-1201 行创建 multi-agent session。这里会把本轮执行所需的关键标志放进 session：

1. `clarificationContext`
2. `conversationId`
3. `swarmEnabled`
4. `outputRoot`
5. `autoApplyOutput`
6. `advisorEnabled`
7. `opencodeEnabled`

同时它还在 `packets.roles.advisor` 里挂了项目侧的 advisor profile，说明 advisor 是会话上下文的一部分，不是 OpenCode 内核里的内建角色，见 `multi_agent_service.py` 第 1180-1192 行。

`api_multi_agent_session_start()` 则负责从 HTTP 请求读取参数并起线程，见 `multi_agent_service.py` 第 3515-3582 行。

### 4.5 检索证据和路径选择

真正的执行链在 `_run_multi_agent_session()` 中，见 `multi_agent_service.py` 第 3201-3513 行。

它先做这些事：

1. 组装 `shared_swarm_context`，把问题、项目、任务模式、澄清上下文带到后续阶段，见第 3234-3241 行。
2. 读取 `prioritizedExperienceLibraries`，解析经验库优先级，见第 3242-3245 行。
3. 生成 `intent_packet`，跑 `taizi` 阶段，见第 3246-3282 行。
4. 调用 `_ensure_workbench_ready(project_path)`，说明正式问答前依赖 workbench / 经验库准备态，见第 3283 行。
5. 调用 `_build_retrieval_bundle()` 做证据汇总和主路径选择，见第 3284 行。

`_build_retrieval_bundle()` 本身会：

1. 抽取搜索证据。
2. 生成候选 partition。
3. 选出 `selected_path` 和 `candidate_paths`。
4. 整理 `node_details`、`chain_node_details`、`impacted_files`。
5. 产出 `evidence_packet`。

对应代码在 `multi_agent_service.py` 第 2772-2856 行。随后 `_build_evidence_verdict()` 会根据证据完整度决定是否批准继续代码生成，见第 2859-2897 行。

### 4.6 advisor sidecar 何时触发

advisor 不是无条件执行。`_should_invoke_advisor()` 会根据当前检索结果判断要不要拉起 advisor sidecar，主要看：

1. 当前是否拿到了可落位源码锚点。
2. 是否有稳定 function chain。
3. 置信度和选择模式是否够高。
4. 用户问题是否带架构、重构、安全、性能、调用链等高风险标记。

对应代码是 `multi_agent_service.py` 第 421-476 行。

在 `_run_multi_agent_session()` 里，只有 `advisor_enabled` 打开且 `_should_invoke_advisor()` 返回需要调用时，才会真正执行 `_run_advisor_sidecar()`，并把结果落到 `retrieval_bundle['advisor_packet']`，见 `multi_agent_service.py` 第 3287-3333 行。

### 4.7 advisor sidecar 如何产出 `advisor_packet`

这一段是“顾问插入 OpenCode”的核心。

先看 sidecar 本身是什么。`advisor_consultant_lab/README.md` 第 5-17 行说明它是独立实验目录，不接入 `app.py` 启动链，流程固定为“需求输入 -> 三匹配 Agent -> 分析 -> 设计 -> 代码生成”，每一步都把中间产物写入 `runtime/`。

`02_analyze_advisor.py` 负责把匹配结果整理成结构化分析结果。

1. 第 34-63 行选择后续跟进顾问集合。
2. 第 137-189 行生成 `report`，核心字段包括 `what`、`how`、`constraints`、`analysis_result.recommended_advisor`、`recommended_partition`、`key_call_chain`、`key_code_refs`、`selected_advisors_for_followup`。
3. 第 240-302 行把这些内容写成可读 Markdown。
4. 第 305-333 行把 JSON、Markdown、process 文件输出到 runtime。

运行时样本 `advisor_consultant_lab/runtime/step2_analysis.json` 也能看到这些内容已经被物化：

1. 第 16-28 行给出 `top_advisor`、`what`、`how`。
2. 第 131-220 行给出 `selected_for_followup`，也就是后续可能继续复用的顾问集合。

`04_generate_code.py` 则说明 sidecar 在代码生成阶段怎么继续把顾问信息向下游传。

1. 第 1371-1579+ 行会从 `analysis_payload`、`design_payload`、`source_targets` 构造 `retrieval_bundle`、`advisor_packet`、`output_protocol`，必要时调用 OpenCode 桥接服务。
2. 第 1498-1509 行是实际调用 `_run_opencode_kernel_service(...)` 的位置。

运行时样本 `advisor_consultant_lab/runtime/step4_codegen.json` 进一步证明了 sidecar 的落地产物结构：

1. 第 19-25 行是 sidecar 内部一次 OpenCode 尝试的状态记录。
2. 第 27-55 行是 codegen 依据，里面有分析结论和结构化约束摘要。
3. 第 56-142 行是 `source_targets`，也就是顾问给出的源码目标。
4. 第 144-189 行是实现目标、生成代码块和 patch 草案。

主链路里，multi-agent 并不会把这些 runtime 文件原样交给 OpenCode，而是先经过 `_build_advisor_packet_from_runtime()` 清洗成统一结构，见 `multi_agent_service.py` 第 479-557 行。这个函数明确把 step2 和 step4 里的信息汇成：

1. `recommended`
2. `analysis`
3. `constraints`
4. `followup_advisors`
5. `source_targets`
6. `artifacts`

真正执行 sidecar 的地方是 `_run_advisor_sidecar()`，它会写 `task_input.txt`、跑 `run_pipeline.py`、读取 runtime 文件，再产出 `advisor_packet`，见 `multi_agent_service.py` 第 560-651 行。

### 4.8 `advisor_packet` 如何并入分析和输出协议

拿到 `advisor_packet` 后，不是直接喂给 OpenCode。代码先做两层并入。

第一层是并入 `analysis_payload`。`_merge_advisor_context_into_analysis()` 会把顾问的 `how` 追加到 `key_reasoning`，把顾问的 `source_targets` 补进 `impacted_files`，必要时甚至补出 `selected_path`，并把结构化的 `advisor` 节点放进分析结果，见 `multi_agent_service.py` 第 654-729 行。

第二层是并入 `output_protocol`。`_build_output_protocol()` 明确把 `advisor_packet` 拆成 `advisor_section`，再和 `analysis`、`opencode.system_context`、`preferred_files`、`preferred_symbols` 一起组成最终下发给 OpenCode 的协议对象，见 `multi_agent_service.py` 第 2074-2174 行。

`_build_solution_packet()` 则把这两层串起来。无论证据不足还是证据通过，它都会把 advisor 信息纳入最终的 `analysis` 和 `output_protocol`；证据通过时还会生成 `opencode_seed`，再桥接到 OpenCode，见 `multi_agent_service.py` 第 2900-3175+ 行，尤其是第 2997-3018 行。

### 4.9 OpenCode 内核桥接层怎么接收这些上下文

`_run_opencode_kernel_bridge()` 只是桥接入口，真正和 OpenCode CLI 打交道的是 `opencode_kernel_service.py`，见 `multi_agent_service.py` 第 173-191 行。

`opencode_kernel_service.py` 的动作非常直接。

1. 第 28-36 行解析 OpenCode 可执行文件。
2. 第 39-45 行拼出命令行。
3. 第 48-67 行从 `impacted_files` 里抽出现有文件，作为附带上下文。
4. 第 90-111 行解析 OpenCode 标准输出里的 JSON 行和 `sessionID`。
5. 第 114-160 行构造给 OpenCode 的 message。这里很关键，它并没有把 advisor 当成一个独立 agent 传进去，而是把顾问内容放进 `advisor_summary`，同时附带 `selected_path`、`impacted_files`、`required_files`、`system_context`。
6. 第 163-292 行真正执行 `opencode run --format json`，传入 `project_path`、`user_query`、`task_mode`、`retrieval_bundle`、`advisor_packet`、`output_protocol`，再把返回结果解析成 `OpenCodeKernelResult`。

所以，advisor 接入 OpenCode 的真实方式不是“把 OpenCode 换成 advisor 模式”，而是“把 advisor 侧车产出的上下文整理成结构化包，再作为 OpenCode 的输入上下文之一”。

### 4.10 结果如何回到页面

当 multi-agent 执行完成，`_run_multi_agent_session()` 会把这些对象收进最终结果：

1. `workbench`
2. `intent_packet`
3. `retrieval_bundle`
4. `advisor_packet`
5. `evidence_verdict`
6. `solution_packet`
7. `output_protocol`
8. `opencode_kernel`
9. `output_write`
10. `swarm_packet`

对应代码在 `multi_agent_service.py` 第 3468-3487 行。页面随后通过 `api_multi_agent_session_status()` 和 `api_multi_agent_session_result()` 读取这些状态与结果，见 `multi_agent_service.py` 第 3713-3773、3776-3784 行。

如果是 conversation 内联代码生成，`conversation_service.py` 第 2330-2416 行会把 `solution_packet`、`output_protocol`、`evidence_verdict`、`opencode_kernel`、`swarm_packet` 摘出来，直接作为当前 conversation result 返回给页面。

## 5. 经验库与 workbench 的前置关系

这条链路还有一个前置条件，就是项目经验库尽量要先就绪。

1. `experience_library_service.py` 第 229 行提供经验库总览接口，供页面加载经验库列表。
2. `analysis_service.py` 第 3575 行启动 workbench session。
3. `analysis_service.py` 第 3624 行查询 workbench session 状态。
4. `analysis_service.py` 第 3782 行查询项目级 workbench 状态。

页面端对应的训练与状态刷新逻辑在 `qa_ui/index.html` 第 15-17 行。配置层面，`config/user_runtime_config.example.json` 第 14-25 行给出了两组关键开关：

1. `opencode.enable_opencode_kernel`
2. `advisor.enable_advisor_sidecar`
3. `advisor.advisor_pipeline_timeout_seconds`
4. `advisor.advisor_reuse_runtime`

这说明 advisor sidecar 和 OpenCode kernel 是两条并行能力开关，前者负责补顾问上下文，后者负责真正调用 OpenCode。

## 6. 关键结论

1. 问答主入口是 `qa_ui/index.html`，后端薄入口是 `qa_button_app.py`，真正的决策和分流在 `conversation_service.py`。
2. conversation 阶段只负责把当前问题分成澄清、检索、聊天、代码流 handoff 四类，不直接承担完整代码生成编排。
3. 代码流真正落在 `multi_agent_service.py`，这里负责 workbench 准备、检索取证、证据裁决、顾问侧车调用、OpenCode 调用和结果回写。
4. advisor 在这个仓库里不是 OpenCode builtin role，而是 `advisor_consultant_lab` 侧车流程的运行结果。
5. sidecar 的 step2 与 step4 runtime 会被整理成统一 `advisor_packet`。
6. `advisor_packet` 会先并入 `analysis`，再并入 `output_protocol`，最后随 `retrieval_bundle` 和 `system_context` 一起传给 OpenCode。
7. OpenCode 接收 advisor 的方式是“上下文注入”，不是“角色切换”。

## 7. 代码文件与行号清单

| 文件 | 行号 | 用途 |
| --- | --- | --- |
| `qa_ui/index.html` | 15-17, 19, 21, 23, 25, 27, 28, 29, 30, 31 | 单页问答入口，负责经验库加载、SSE、澄清交互、提交问题、触发 multi-agent |
| `qa_button_app.py` | 40-112 | Flask API 装配层，把 UI、conversation、multi-agent、经验库、workbench 路由暴露出来 |
| `app/services/conversation_service.py` | 1653 | 创建 conversation turn session |
| `app/services/conversation_service.py` | 1826-1880 | 内联创建并同步执行 multi-agent 代码生成 |
| `app/services/conversation_service.py` | 1883-2042 | conversation 主执行函数，写用户消息，决策 clarify |
| `app/services/conversation_service.py` | 2044-2256 | 检索分支，调用代码检索并返回 retrieval answer |
| `app/services/conversation_service.py` | 2258-2299 | 普通聊天分支 |
| `app/services/conversation_service.py` | 2302-2523 | handoff 到 multi-agent，支持 inline 和 auto start |
| `app/services/conversation_service.py` | 2543-2622 | 启动 conversation session 的 HTTP 接口 |
| `app/services/conversation_service.py` | 2625-2642 | 查询 conversation session 状态 |
| `app/services/conversation_service.py` | 2645-2653 | 查询 conversation session 结果 |
| `app/services/conversation_service.py` | 2808-2884 | SSE 事件流接口 |
| `app/services/conversation_service.py` | 2980-2995 | 读取 conversation messages / parts |
| `app/services/conversation_service.py` | 2998-3096 | 回复澄清问题，继续下一轮 turn |
| `llm/agent/utils/question_detector.py` | 12, 102, 111 | 定义问题检测器、任务模式识别、澄清需求评估 |
| `data/data_accessor.py` | 229-235 | multi-agent session 缓存 |
| `data/data_accessor.py` | 249-264 | conversation turn session 缓存 |
| `data/data_accessor.py` | 280-299 | conversation 默认数据结构 |
| `data/data_accessor.py` | 399-406 | 确保 conversation 存在 |
| `data/data_accessor.py` | 421-441 | 追加 conversation message |
| `data/data_accessor.py` | 456-474 | 追加 conversation part |
| `data/data_accessor.py` | 476-494 | pending question 存取 |
| `data/data_accessor.py` | 505-529 | question reply 存取 |
| `data/data_accessor.py` | 581-603 | key facts memory 存取 |
| `data/data_accessor.py` | 614-643 | conversation event 日志 |
| `app/services/codebase_retrieval_service.py` | 752 | 代码检索主入口 `run_codebase_retrieval()` |
| `app/services/multi_agent_service.py` | 173-191 | OpenCode kernel 桥接入口 |
| `app/services/multi_agent_service.py` | 216-226 | advisor sidecar 开关判断 |
| `app/services/multi_agent_service.py` | 251-260 | OpenCode kernel 开关判断 |
| `app/services/multi_agent_service.py` | 421-476 | 判断是否需要调用 advisor sidecar |
| `app/services/multi_agent_service.py` | 479-557 | 从 sidecar runtime 生成 `advisor_packet` |
| `app/services/multi_agent_service.py` | 560-651 | 执行 advisor sidecar 流程并读取 runtime |
| `app/services/multi_agent_service.py` | 654-729 | 把 advisor 上下文并入 analysis |
| `app/services/multi_agent_service.py` | 1141-1201 | 创建 multi-agent session |
| `app/services/multi_agent_service.py` | 2074-2174 | 构建 `output_protocol`，把 advisor / analysis / opencode 上下文合并 |
| `app/services/multi_agent_service.py` | 2772-2856 | 构建 `retrieval_bundle` |
| `app/services/multi_agent_service.py` | 2859-2897 | 证据裁决 `evidence_verdict` |
| `app/services/multi_agent_service.py` | 2900-3175+ | 构建 `solution_packet`，决定是否调用 OpenCode |
| `app/services/multi_agent_service.py` | 2997-3018 | 构建 `opencode_seed` 并桥接到 OpenCode |
| `app/services/multi_agent_service.py` | 3201-3513 | multi-agent 主执行链 |
| `app/services/multi_agent_service.py` | 3515-3582 | 启动 multi-agent session 的 HTTP 接口 |
| `app/services/multi_agent_service.py` | 3713-3773 | 查询 multi-agent 状态 |
| `app/services/multi_agent_service.py` | 3776-3784 | 查询 multi-agent 结果 |
| `app/services/opencode_kernel_service.py` | 28-36 | 解析 OpenCode 可执行文件 |
| `app/services/opencode_kernel_service.py` | 39-45 | 构造 OpenCode 命令行 |
| `app/services/opencode_kernel_service.py` | 48-67 | 选取附带上下文文件 |
| `app/services/opencode_kernel_service.py` | 90-111 | 解析 OpenCode 标准输出 |
| `app/services/opencode_kernel_service.py` | 114-160 | 构造发给 OpenCode 的 message，其中包含 `advisor_summary` |
| `app/services/opencode_kernel_service.py` | 163-292 | 执行 OpenCode CLI 并解析返回结果 |
| `advisor_consultant_lab/README.md` | 5-17 | 说明 sidecar 独立运行，不接入主应用启动链 |
| `advisor_consultant_lab/02_analyze_advisor.py` | 34-63 | 选择 followup advisors |
| `advisor_consultant_lab/02_analyze_advisor.py` | 137-189 | 生成 step2 结构化分析结果 |
| `advisor_consultant_lab/02_analyze_advisor.py` | 240-302 | 生成 step2 Markdown 报告 |
| `advisor_consultant_lab/02_analyze_advisor.py` | 305-333 | 把 step2 产物写入 runtime |
| `advisor_consultant_lab/04_generate_code.py` | 1371-1579+ | sidecar 代码生成主流程，构造 `retrieval_bundle`、`advisor_packet`、`output_protocol`，必要时调用 OpenCode |
| `advisor_consultant_lab/04_generate_code.py` | 1498-1509 | sidecar 内实际调用 OpenCode kernel service |
| `advisor_consultant_lab/runtime/step2_analysis.json` | 16-28 | 运行时 `top_advisor`、`what`、`how` |
| `advisor_consultant_lab/runtime/step2_analysis.json` | 131-220 | 运行时 `selected_for_followup` |
| `advisor_consultant_lab/runtime/step4_codegen.json` | 19-25 | sidecar 内 OpenCode 执行状态 |
| `advisor_consultant_lab/runtime/step4_codegen.json` | 27-55 | codegen_basis 和结构化约束摘要 |
| `advisor_consultant_lab/runtime/step4_codegen.json` | 56-142 | `source_targets` |
| `advisor_consultant_lab/runtime/step4_codegen.json` | 144-189 | `implementation_targets`、`generated_code_blocks`、`generated_patch_blocks` |
| `config/user_runtime_config.example.json` | 14-25 | OpenCode 与 advisor sidecar 的运行开关 |
| `app/services/experience_library_service.py` | 229 | 经验库总览接口 |
| `app/services/analysis_service.py` | 3575 | 启动 workbench session |
| `app/services/analysis_service.py` | 3624 | workbench session 状态接口 |
| `app/services/analysis_service.py` | 3782 | workbench 项目状态接口 |

## 8. 交接建议

如果后续要继续排查“顾问为什么没进 OpenCode”，按下面顺序看最快。

1. 先看 `qa_ui/index.html` 第 29-30 行，确认请求里有没有把 `opencode_enabled`、`clarification_context`、`output_root` 带上。
2. 再看 `conversation_service.py` 第 2302-2523 行，确认这一轮是不是已经 handoff 到 multi-agent。
3. 再看 `multi_agent_service.py` 第 421-476、3287-3333 行，确认 advisor 是否被判定为 invoked，还是 skipped。
4. 再看 `multi_agent_service.py` 第 479-557、654-729、2074-2174 行，确认 `advisor_packet` 有没有成功并入 `analysis` 和 `output_protocol`。
5. 最后看 `opencode_kernel_service.py` 第 114-160、163-292 行，确认 OpenCode 实际收到的 message 里是否已经带上 `advisor_summary`。
