# 日志解读说明

## 1. 为什么会有那么多 Retry？

日志中的 `Retrying in 1s [Retry 1/5]`、`Retrying in 2s [Retry 2/5]` 等来自 **huggingface_hub** 在下载模型时的重试逻辑。

- **原因**：连接 `huggingface.co` 超时（`Connection to huggingface.co timed out. (connect timeout=10)`）。在国内环境下，访问 Hugging Face 经常被墙或极慢，导致每次请求在 10 秒内无法建立连接。
- **行为**：库会按 1s、2s、4s、8s、8s 间隔最多重试 5 次，所以你会看到多行 “Retrying in Xs [Retry N/5]”。
- **建议**：
  1. 使用镜像：设置环境变量 `HF_ENDPOINT=https://hf-mirror.com` 再运行；
  2. 或使用代理/VPN 能访问 huggingface.co；
  3. 或提前在有网络的机器上下好模型，把缓存目录（如 `~/.cache/huggingface/hub`）拷到本机，并设置 `HF_HOME`/`TRANSFORMERS_CACHE` 指向该目录。

---

## 2. 为什么之前下过模型这里还要重新下载？

当前用到的是 **两个不同的模型**：

1. **Embedding 模型**：`BAAI/bge-small-zh-v1.5`  
   - 用于把文本变成向量，做检索。  
   - 若你之前已经成功下载过，会缓存在本地，一般不会重复下载。

2. **重排模型（Cross-encoder）**：`BAAI/bge-reranker-base`  
   - 用于对检索结果做精排。  
   - 配置在 `config/config.py` 的 `RERANKER_CONFIG["model_name"]`。  
   - 日志里报错、重试的都是这个模型在访问 `huggingface.co/BAAI/bge-reranker-base/...`。

所以：  
- “之前下过”的如果是 **bge-small-zh**，那 **bge-reranker-base** 仍是第一次下，需要联网（或镜像）拉取；  
- 若两个都下过，还反复拉取，可能是缓存路径变了（换环境、换用户、清过缓存），或 `HF_HOME`/`TRANSFORMERS_CACHE` 未指向原来的缓存目录。

**建议**：  
- 对 `bge-reranker-base` 同样用镜像或代理下一次，并保持 `HF_HOME` 一致；  
- 或在代码里改为从本地路径加载（若你已把模型拷到项目目录）。

---

## 3. 简要时间线（结合你的日志）

1. FAISS 索引和 Embedding 模型加载成功（745 个向量，bge-small-zh-v1.5）。
2. 开始加载重排模型 `BAAI/bge-reranker-base`，连接 huggingface.co 超时，出现多次 Retry。
3. WebSocket 已连接（`task_20260202_103519_30393e`），前端已连上。
4. 任务在执行：Reviewer 审查 `src/cli_tool/core.py`，Orchestrator 执行步骤 7、8（创建测试目录、单元测试），Coder 创建 `tests/__init__.py`、`tests/test_core.py`。
5. 重排模型仍在后台重试下载，与任务执行并行，所以你会同时看到 “Retrying” 和 “执行步骤 N”。
6. 最后 `Shutting down`、`connection closed` 表示服务/连接被关闭；若此时重排仍未下载成功，任务里依赖重排的 RAG 精排可能会失败或降级。

---

## 4. 总结

| 现象 | 原因 | 处理方向 |
|------|------|----------|
| 大量 Retry | 连不上 huggingface.co（超时） | 镜像 / 代理 / 本地缓存 |
| “又要下载” | 实际是另一个模型 bge-reranker-base | 确保该模型也下载并缓存，或改本地路径 |
| 任务在执行同时还有 Retry | 模型下载与任务并行 | 正常；若重排未就绪，相关 RAG 可能不可用 |
