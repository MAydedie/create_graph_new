# 问答按钮功能抽离版（对齐原问答状态机）

这份抽离包不是整站前端，仅保留问答入口页面 `qa_ui/index.html`，但已补齐原问答模块关键能力：

- 会话启动 / 会话回复（clarification）
- SSE 事件流进度（`/api/conversations/<id>/events`）
- 会话超时后的 messages 回补
- `nextStep=start_multi_agent` 的 handoff 接管
- 手动触发/继续查询多代理（`/api/multi_agent/session/*`）
- `output_root` + `auto_apply_output` + `opencode_enabled` 透传

## 启动
启动前先在 `config/user_runtime_config.json` 填写你自己的 key；仓库不附带任何可用 key。
填写后运行 `scripts/apply_user_config.py` 生成/应用 `.env`，或直接走现有的一键安装/启动流程。

1. 双击 `一键安装依赖.bat`（首次）
2. 双击 `一键启动_问答按钮专用.bat`
3. 打开 `http://127.0.0.1:5123/`

## 使用建议
- `project_path` 填你要分析的源码目录（绝对路径）
- 若希望落地写文件，填 `output_root`，或在 query 中给出目标目录（页面会尝试推断）
- 若出现 `start_multi_agent`，可直接点击“Manual Multi-Agent”继续执行

## 关键入口
- 后端入口：`qa_button_app.py`
- 前端页面：`qa_ui/index.html`
- 配置模板：`config/user_runtime_config.json`
- 环境生成：`scripts/apply_user_config.py`
