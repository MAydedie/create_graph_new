# create_graph vs SE Agent Team（5-13代码汇总）问答系统对比报告

## 1. 任务目标

对比两个项目的问答系统：

1. `D:\代码仓库生图\create_graph`
2. `D:\代码仓库生图\借鉴项目\5-13代码汇总`

重点覆盖：

- README 与整体架构
- 问答对应模块
- RAG / 混合检索 / advisor / 多智能体 / OpenCode 关系
- 本地启动情况
- 同题问答质量对比
- 最终优劣判断与原因分析

---

## 2. 对比方法

### 2.1 代码与文档调查

已实际检查：

- `create_graph/README.md`
- `create_graph/app/routes/api_routes.py`
- `create_graph/app/services/conversation_service.py`
- `create_graph/app/services/multi_agent_service.py`
- `create_graph/app/services/opencode_qa_service.py`
- `create_graph/advisor_consultant_lab/README.md`
- `借鉴项目/5-13代码汇总/README.txt`
- `借鉴项目/5-13代码汇总/architecture-and-api.md`
- `借鉴项目/5-13代码汇总/projects/README.md`
- `借鉴项目/5-13代码汇总/projects/src/app/api/chat/route.ts`
- `借鉴项目/5-13代码汇总/projects/src/app/chat/page.tsx`
- `借鉴项目/5-13代码汇总/ProjectManager/components/project_retriever.py`
- `借鉴项目/5-13代码汇总/.opencode/skills/advisor_consultant/SKILL.md`

### 2.2 运行验证

已实际验证：

- `create_graph` 的 Flask 主问答链可以启动并返回答案
- 借鉴项目的 Next 服务可以启动并访问页面
- 借鉴项目的 `/api/chat` 连续多次超时

### 2.3 题集设计

为了同时覆盖“架构解释”“代码事实路径”“是否进入多智能体”三类能力，使用以下 3 题：

#### Q1 架构解释题

> 这个项目的问答链路是怎么工作的？请简洁说明检索、advisor 和多智能体分别在什么情况下介入。

#### Q2 代码事实路径题

> 如果我问一个具体代码事实问题，比如某个接口定义在哪里，这个系统应该走什么路径？

#### Q3 多智能体决策题

> 如果我想让系统帮我修改代码而不是解释代码，它会如何决定是否进入多智能体流程？

---

## 3. 两个项目的问答系统对应关系

## 3.1 create_graph

### 主问答链

- 入口：`app.py`
- 路由：`app/routes/api_routes.py`
- 主接口：`/api/conversations/session/start`
- 主服务：`app/services/conversation_service.py`

### 检索链

- `conversation_service._run_retrieval_tool()`
- `app/services/codebase_retrieval_service.py`
- `src/search/hybrid_search.py`
- `src/search/adapters/hybrid_shadow_adapter.py`

### advisor

- 独立实验目录：`advisor_consultant_lab/*`
- 在 `app/services/multi_agent_service.py` 中按条件调用 sidecar

### 多智能体 / 三省六部

- `app/services/multi_agent_service.py`
- 实际存在：太子、 中书、 门下、 尚书等阶段

### OpenCode

- `app/services/opencode_qa_service.py`
- `app/services/opencode_kernel_service.py`

### 本质判断

`create_graph` 是一个**后端真实执行型问答系统**，不是单纯的聊天页面。

---

## 3.2 借鉴项目（SE Agent Team）

### 主问答链

- 页面：`projects/src/app/chat/page.tsx`
- API：`projects/src/app/api/chat/route.ts`

### 经验注入

- `page.tsx` 中硬编码 `AVAILABLE_AGENTS`
- 提交请求时把经验列表作为 `experiences` 发送给 `/api/chat`
- `route.ts` 对 `features` 做关键词打分，Top3 拼入 prompt

### advisor

- `.opencode/skills/advisor_consultant/SKILL.md`
- `.opencode/AGENTS.md`

### 经验检索原型

- `ProjectManager/components/project_register.py`
- `ProjectManager/components/project_retriever.py`
- `ProjectManager/services/project_manager_service.py`

### 多智能体/团队

- `.opencode/AGENTS.md` 定义 15 步 AI Team 状态机
- `projects/src/app/api/chat/route.ts` 的 team 模式主要体现为 **8 阶段格式化输出 prompt**

### 本质判断

这个项目更像**前端问答壳 + ProjectManager 检索原型 + OpenCode 工作流配置**的组合体，尚未形成像 `create_graph` 那样统一打通的后端执行链。

---

## 4. 本地启动验证

## 4.1 create_graph

### 已验证入口

1. `ui/server.py`
2. `app.py`（更适合作为主问答链验证入口）

### 实测结果

- `http://127.0.0.1:8000/health` 返回正常
- `http://127.0.0.1:5001/api/conversations/session/start` 可成功创建 session
- 后续 status/result 轮询可拿到完整回答

### 结论

`create_graph` 的主问答链**可运行**。

---

## 4.2 借鉴项目

### 启动路径

README 推荐：

- `coze dev`
- `coze build`
- `coze start`

但实际本地运行中：

- `projects/package.json` -> `bash ./scripts/dev.sh`
- `dev.sh` 最终执行 `pnpm tsx watch src/server.ts`

### 实测问题

- 环境中全局 `pnpm` 不在 PATH
- 直接跑 `pnpm dev` 会因脚本内找不到 `pnpm` 失败
- 改用 `npx pnpm@9.0.0 tsx src/server.ts` 后，服务可启动

### 实测结果

- `GET /` 返回 `200`
- 页面能打开
- 但 `/api/chat` 连续多次请求超时

### 结论

借鉴项目**服务层可启动**，但**核心问答链未打通**。

---

## 5. `/api/chat` 超时根因分析（借鉴项目）

### 直接调用点

`projects/src/app/api/chat/route.ts` 中：

- `const config = new Config();`
- `const client = new LLMClient(config, customHeaders);`
- 然后调用 `client.stream(...)`

### 已确认现象

- 请求能进入 route
- SSE 能开始工作
- 超时发生在 SDK / 模型调用层，不是 Next 路由层

### 高概率根因

项目示例 env 与 SDK 实际期望 env 不匹配：

#### 项目示例

`projects/.env.local.example`

- `COZE_API_TOKEN`
- `DASHSCOPE_API_KEY`

#### 诊断中发现 SDK 更可能期望

- `COZE_WORKLOAD_IDENTITY_API_KEY`
- `COZE_INTEGRATION_BASE_URL`
- `COZE_INTEGRATION_MODEL_BASE_URL`

### 结论

借鉴项目当前的失败主因更像是：

**运行时环境 / SDK 接线问题**，而不是页面、SSE 或整体架构完全不可用。

---

## 6. 问答实测结果

## 6.1 create_graph 实测结果

### Q1 结果

- 成功返回
- 但回答把项目描述成 `skill-first` / “技能库匹配主导”
- 这与源码中真实的 `conversation_service + retrieval + advisor sidecar + multi_agent_service` 主链不一致

### Q2 结果

- 成功返回
- 但回答声称会优先查 `.skill`、`skill_callchain_v2`
- 与当前真实主问答链不一致

### Q3 结果

- 成功返回
- 仍把多智能体判断逻辑解释成“先查 skill 目录再决定”
- 与实际 `conversation_service` 的 action 决策逻辑不符

### 综合判断

`create_graph` 的优点是：

- 能答
- 能闭环

但主要问题是：

- **回答忠实度不稳定**
- 会把系统解释成另一套偏 `skill` 的体系

---

## 6.2 借鉴项目实测结果

### Q1

- 超时

### Q2

- 超时

### Q3

- 超时

### 综合判断

借鉴项目当前无法形成可用问答闭环，因此：

- 不能公平评价其“答案质量高低”
- 只能评价其**运行可用性**目前不足

---

## 7. 质量评分（基于当前可观测结果）

| 维度 | create_graph | 借鉴项目 |
|---|---:|---:|
| 服务是否可启动 | 5 | 4 |
| 主问答链是否跑通 | 5 | 1 |
| 是否能返回答案 | 5 | 1 |
| 回答忠实度 | 2 | N/A |
| 架构执行完整度 | 5 | 2 |
| 工程集成完成度 | 4 | 2 |
| 当前实践可用性 | 4 | 1 |

说明：

- 借鉴项目“服务能起”所以不是 0 分
- 但聊天链没跑通，因此在“是否能答”上只能给低分
- `create_graph` 的主要扣分点是**答案不够贴源码事实**

---

## 8. 结构 vs 技术用法：问题归因

## 8.1 create_graph

### 强项

- 结构已经落地
- 检索、advisor、多智能体、OpenCode 不是口号，而是后端链路的一部分

### 弱项

- 回答生成阶段 grounding 不稳
- 可能存在旧链路/新链路/skill 系信息串台
- 元问题（“你自己是怎么工作的”）回答准确性不足

### 归因

create_graph 当前主要是：

**结构成熟，但回答生成策略/信息对齐有问题**

---

## 8.2 借鉴项目

### 强项

- 产品表达清晰
- advisor / team / experience 概念化很好
- 前端交互与展示结构完整

### 弱项

- `projects`、`ProjectManager`、`.opencode` 更像并列原型
- 未形成统一后端执行链
- 运行高度依赖外部 SDK 配置

### 归因

借鉴项目当前主要是：

**技术接法 / 运行时环境接线问题为主，架构未完全落地为统一执行系统**

---

## 9. 最终结论

## 9.1 当前谁更好

**当前更好的是 `create_graph`。**

理由：

- 能启动
- 能走主问答链
- 能真正返回答案

---

## 9.2 当前谁更差

**当前更差的是借鉴项目。**

但这里的“差”要精确理解为：

- 不是说它的设计思想一定更差
- 而是它**现在本地问答链没有打通**

---

## 9.3 更公平的总评

### create_graph

- **优点**：运行闭环完整，后端执行链成熟
- **缺点**：回答忠实度仍需提升

### 借鉴项目

- **优点**：AI Team / advisor / experience 设计表达清楚，适合继续产品化
- **缺点**：当前问答运行链未打通，无法进入公平质量对比阶段

### 一句话判决

> 现阶段，`create_graph` 是一个“能跑但回答还不够稳”的后端问答系统；借鉴项目是一个“设计思路清楚但问答运行链尚未打通”的 AI Team 原型系统。

---

## 10. 后续建议

## 10.1 先修借鉴项目

优先目标：

- 让 `/api/chat` 真正答出内容

建议排查：

- `coze-coding-dev-sdk` 所需真实环境变量
- `.env.local.example` 是否已过时
- `Config()` 默认读取逻辑
- 本地启动路径是否正确加载 env

## 10.2 再修 create_graph

优先目标：

- 提高“解释系统自身架构”时的忠实度

建议排查：

- `general_chat` 路径是否缺少强 grounding
- 是否混入旧 skill 系上下文
- 元问题是否应强制切到 retrieval / evidence-first 路径

---

## 11. 最后总结

如果只看当前你最关心的结果：

- **谁现在更能用？** `create_graph`
- **谁现在更不稳定？** 借鉴项目
- **create_graph 最大问题是什么？** 回答忠实度不稳
- **借鉴项目最大问题是什么？** 运行时 SDK / 环境接线没通
