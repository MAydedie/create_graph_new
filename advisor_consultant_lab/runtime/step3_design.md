# Step3 设计文档

## 设计目标
- 请基于当前 CAT-Net 的经验库，在 D:/代码仓库生图/汇报/4.21/test/ 下生成一个真实可落地的 Python 命令行 demo 项目。这个项目要演示 CAT-Net 最核心的篡改定位能力：输入一张图像路径后，输出一个简化版的篡改定位结果，并打印关键处理阶段说明。
- 架构草图：以 CAT-Net-main:partition_2:获取篡改数据 的调用链为核心，组织为数据加载层、模型主干层、训练入口层三段式最小可运行架构。
- 接口协议：遵循约束类型 cfg, dfg, io_graph, input_info, output_info, constraint_explain；关键接口需显式声明输入输出并保持 CFG/DFG 路径一致。

## 选定顾问
- 名称：CAT-Net-main:partition_2:获取篡改数据
- 分区：partition_2

## 设计原则
- 匹配与顾问能力解耦，匹配 Agent 只负责检索，不直接做业务实现。
- 分析阶段必须输出匹配依据、how、constraints 三类信息。
- 设计阶段复用分析结果，不重复检索经验库。
- 代码生成阶段必须引用调用链和源码锚点，避免脱离经验库编写。

## 流程设计
- 阶段 `matching`
  - 输入：用户需求, 经验库技能卡
  - 输出：Top3 顾问候选, 三匹配 Agent 分数
  - 说明：path/semantic/code 三 Agent 并行评分，融合排序。
- 阶段 `analysis`
  - 输入：Top3 顾问候选, 主顾问 what/how/constraints
  - 输出：分析文档, 分析结论
  - 说明：必须包含第一步匹配说明、how、constraints。
- 阶段 `design`
  - 输入：分析结论, how, constraints
  - 输出：系统设计文档
  - 说明：输出模块划分、数据流、接口契约。
- 阶段 `codegen`
  - 输入：分析文档, 设计文档, 调用链源码线索
  - 输出：代码草案, 文件级实施建议
  - 说明：代码草案需明确入口函数和可落地文件锚点。

## 复用的 How 与约束
- How：[1] 输入需求输入 -> 进入np.array；执行模块处理；得到step_1_output；下一步CASIA.get_tamp。；[2] 输入step_1_output -> 进入CASIA.get_tamp；执行模块处理；得到np.array；下一步END。；约束依据：CFG、DFG、输入输出、np.array、CASIA.get_tamp。
- Constraints：
  - np.array
  - CASIA.get_tamp
  - 优先复用经验库中的 CFG/DFG/IO 证据，不直接跳过中间路径步骤。
  - 需要 CFG 约束证据
  - 需要 DFG 约束证据
  - 需要输入输出约束

## 结构化约束摘要
- 类型：cfg, dfg, io_graph, input_info, output_info, constraint_explain
- has_cfg: True
- has_dfg: True
- has_io_graph: True
- cfg_node_count: 12
- dfg_node_count: 20
- io_node_count: 5
