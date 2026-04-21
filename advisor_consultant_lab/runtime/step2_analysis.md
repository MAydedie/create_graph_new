# Step2 分析文档

## 1) 第一步匹配说明
- 匹配策略：project_partition_path_hierarchical_fusion
- query_scope：mixed
- 匹配总数：12
- 主顾问：CAT-Net-main:partition_2:获取篡改数据 (experience::CAT-Net-main::partition_2::path_2)
- 融合分数：74.1491
- path_matcher：14.7567
- semantic_matcher：21.5556
- code_matcher：2.2963
- 匹配理由：从CASIA数据集中获取图像篡改样本，用于后续的篡改检测模型训练或测试。
- Top1 what：该经验库来自项目CAT-Net-main，功能分区“partition_2”，路径“获取篡改数据”，能力描述：从CASIA数据集中获取图像篡改样本，用于后续的篡改检测模型训练或测试。
- Top1 how：[1] 输入需求输入 -> 进入np.array；执行模块处理；得到step_1_output；下一步CASIA.get_tamp。；[2] 输入step_1_output -> 进入CASIA.get_tamp；执行模块处理；得到np.array；下一步END。；约束依据：CFG、DFG、输入输出、np.array、CASIA.get_tamp。

## 1.1) 纳入后续流程的顾问集合
- [1] CAT-Net-main:partition_2:获取篡改数据 / project=CAT-Net-main / score=74.1491
- [2] GitNexus-main:partition_14:获取仓库信息 / project=GitNexus-main / score=66.9108
- [3] CAT-Net-main:partition_11:配置参数解析更新 / project=CAT-Net-main / score=67.9683
- [4] CAT-Net-main:partition_2:获取篡改数据 / project=CAT-Net-main / score=66.3005
- [5] CAT-Net-main:partition_7:前向传播测试 / project=CAT-Net-main / score=65.7623
- [6] CAT-Net-main:partition_7:前向传播测试 / project=CAT-Net-main / score=65.7623
- [7] CAT-Net-main:partition_11:配置参数更新 / project=CAT-Net-main / score=65.349
- [8] CAT-Net-main:partition_11:配置更新主流程 / project=CAT-Net-main / score=65.349
- [9] CAT-Net-main:partition_2:创建张量 / project=CAT-Net-main / score=64.8809
- [10] CAT-Net-main:partition_2:创建张量数据集 / project=CAT-Net-main / score=64.8809

## 2) How（实现路径）
- [1] 输入需求输入 -> 进入np.array；执行模块处理；得到step_1_output；下一步CASIA.get_tamp。；[2] 输入step_1_output -> 进入CASIA.get_tamp；执行模块处理；得到np.array；下一步END。；约束依据：CFG、DFG、输入输出、np.array、CASIA.get_tamp。

## 3) 约束（Constraints）
- np.array
- CASIA.get_tamp
- 优先复用经验库中的 CFG/DFG/IO 证据，不直接跳过中间路径步骤。
- 需要 CFG 约束证据
- 需要 DFG 约束证据
- 需要输入输出约束

## 3.1) 结构化约束摘要
- 类型：cfg, dfg, io_graph, input_info, output_info, constraint_explain
- has_cfg: True
- has_dfg: True
- has_io_graph: True
- cfg_node_count: 12
- dfg_node_count: 20
- io_node_count: 5

## 分析结论
- 推荐经验库顾问：CAT-Net-main:partition_2:获取篡改数据
- 推荐分区：partition_2
- 下一步：进入系统设计阶段，复用该顾问的 how 与 constraints。
