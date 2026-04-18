# app.py 拆分任务说明（Phase 0 / 任务0.3，当前执行选项A）

## 目标与约束
- **本轮仅执行选项A（轻量拆分）**：将主页面路由拆分为 Blueprint，保留所有 API 路径与行为 100% 不变，业务逻辑不动。
- **兼容性要求**：外部访问的 URL 不变，行为不变；允许内部 import 路径调整。
- **行数目标**：本轮把 app.py 的静态页面路由移出，app.py 将减少若干行；最终整体目标 < 200 行将在后续选项B/C 继续完成。

## 已完成的选项A内容
- 新增 Blueprint 路由文件：`app/routes/main_routes.py`
  - `/` -> `index.html`
  - `/hierarchy` -> `index_hierarchy.html`
  - `/function_hierarchy` -> `function_hierarchy.html`
- 在 `app.py` 中注册 Blueprint：`app.register_blueprint(main_bp)`
- 保证原有路径与模板渲染行为不变。

## 后续拆分计划（选项B/C 预告）
> 本轮不执行，只做预告，后续迭代时按需启用。

- 选项B（中等拆分）思路：
  - 新建 `app/routes/api_routes.py`，搬运主分析与层级分析相关 API（`/api/analyze`、`/api/result`、`/api/analyze_hierarchy`、`/api/analyze_function_hierarchy` 等），内部调用仍复用现有分析函数。
  - 业务逻辑暂留 app.py。
  - 行数继续下降，为下一步彻底解耦铺路。

- 选项C（完整拆分）思路：
  - 新建 `app/services/analysis_service.py` 等，把 `analyze_project` / `analyze_hierarchy` / `analyze_function_hierarchy` 和工具函数迁出。
  - 路由全部 Blueprint 化，app.py 仅保留创建 app 与注册蓝图。
  - 目标：app.py < 200 行。

## 验收标准（本轮）
- 主页面三个路由已迁移至 Blueprint，访问路径与行为无变化。
- app.py 正常启动，无 ImportError / 路由缺失。
- 现有 API 行为不受影响。

## 文件清单
- 新增：`app/routes/main_routes.py`
- 已注册：`app.py` 中 `app.register_blueprint(main_bp)`
- 现有文件未删除，API 保持原样。


