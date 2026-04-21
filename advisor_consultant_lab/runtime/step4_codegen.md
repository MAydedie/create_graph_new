# Step4 代码草案

## 代码生成依据
- 分析结论：进入系统设计阶段，复用该顾问的 how 与 constraints。
- 设计目标：请基于当前 CAT-Net 的经验库，在 D:/代码仓库生图/汇报/4.21/test/ 下生成一个真实可落地的 Python 命令行 demo 项目。这个项目要演示 CAT-Net 最核心的篡改定位能力：输入一张图像路径后，输出一个简化版的篡改定位结果，并打印关键处理阶段说明。
- 结构化约束类型：cfg, dfg, io_graph, input_info, output_info, constraint_explain
- 生成模式：file_level_code
- 场景识别：generic_refactor
- 代码生成主导：template_fallback
- 是否回退模板：True
- OpenCode状态：error
- 目标仓库根：D:\catnet\CAT-Net-main

## 源码落点
- 顾问 CAT-Net-main:partition_2:获取篡改数据 (experience::CAT-Net-main::partition_2::path_2)
  - Splicing\data\dataset_CASIA.py:46
- 顾问 GitNexus-main:partition_14:获取仓库信息 (experience::GitNexus-main::partition_14::path_0)
  - GitNexusDockerEnvironment._get_repo_info
  - _get_repo_info
- 顾问 CAT-Net-main:partition_11:配置参数解析更新 (experience::CAT-Net-main::partition_11::path_4)
  - tools\infer.py:42
  - lib\config\default.py:111
- 顾问 CAT-Net-main:partition_7:前向传播测试 (experience::CAT-Net-main::partition_7::path_0)
  - lib\utils\test\test_utils.py:57
- 顾问 CAT-Net-main:partition_7:前向传播测试 (experience::CAT-Net-main::partition_7::path_2)
  - lib\utils\test\test_utils.py:57
- 顾问 CAT-Net-main:partition_11:配置参数更新 (experience::CAT-Net-main::partition_11::path_0)
  - lib\config\default.py:111
  - tools\infer.py:42
- 顾问 CAT-Net-main:partition_11:配置更新主流程 (experience::CAT-Net-main::partition_11::path_1)
  - lib\config\default.py:111
  - tools\infer.py:60
- 顾问 CAT-Net-main:partition_2:创建张量 (experience::CAT-Net-main::partition_2::path_3)
  - Splicing\data\AbstractDataset.py:103
- 顾问 CAT-Net-main:partition_2:创建张量数据集 (experience::CAT-Net-main::partition_2::path_4)
  - Splicing\data\AbstractDataset.py:103

## 文件级代码实现建议
### app/refactor/plan.py
- 目的：通用改造入口（默认场景）
```python
def build_refactor_plan(requirement: str, source_targets: list[str], constraint_types: list[str]) -> dict:
    return {
        "requirement": requirement,
        "source_targets": source_targets,
        "constraint_types": constraint_types,
        "next_actions": ["extract modules", "define interfaces", "implement tests"],
    }
```


## 补丁级输出（Diff Proposal）
### app/refactor/plan.py
- operation: add_candidate
- apply_strategy: apply_add_file
- is_apply_ready: True
```diff
--- a/app/refactor/plan.py
+++ b/app/refactor/plan.py
@@ -0,0 +1,7 @@
+def build_refactor_plan(requirement: str, source_targets: list[str], constraint_types: list[str]) -> dict:
+    return {
+        "requirement": requirement,
+        "source_targets": source_targets,
+        "constraint_types": constraint_types,
+        "next_actions": ["extract modules", "define interfaces", "implement tests"],
+    }
```
