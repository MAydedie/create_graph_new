# 演示代码包 (Demo Code Package)

这个包包含了用于演示功能层级分析的完整代码，所有方法之间都有真实的调用关系，确保超图能够正确显示。

## 生成演示代码的逻辑

`generate_demo_code.py` 文件包含了从 `app.py` 中提取的生成演示分区的完整逻辑，包括：

1. **`generate_demo_partition_from_call_graph()`** - 基于真实调用关系生成演示分区
   - 从调用图中找到连通分量
   - 识别叶子节点和入口点
   - 从叶子节点回溯生成路径
   - 适用于步骤2.7的逻辑

2. **`generate_demo_partition_with_methods()`** - 基于方法列表生成演示分区
   - 创建不同长度的路径（2、3、4）
   - 生成FQMN信息（四段内部格式）
   - 生成输入输出信息
   - 适用于步骤6.5.4的逻辑

这些函数可以直接在 `app.py` 中使用，或者用于生成演示代码。

## 目录结构

```
demo_code_package/
├── analysis/                    # 分析模块
│   ├── __init__.py
│   ├── function_node_enhancer.py    # 功能节点增强器
│   └── path_level_analyzer.py       # 路径级别分析器
├── parsers/                     # 解析器模块
│   ├── __init__.py
│   └── python_parser.py            # Python解析器
├── visualization/               # 可视化模块
│   ├── __init__.py
│   └── enhanced_visualizer.py       # 增强的可视化器
├── llm/                         # LLM模块
│   ├── __init__.py
│   └── code_understanding_agent.py  # 代码理解代理
├── config/                      # 配置模块
│   ├── __init__.py
│   └── config.py                    # 配置管理
├── app.py                       # 应用主程序
└── README.md                    # 本文件
```

## 方法签名格式

所有方法签名都遵循四段内部格式：`包.文件.类.方法`

例如：
- `analysis.function_node_enhancer.FunctionNodeEnhancer.identify_leaf_nodes`
- `analysis.path_level_analyzer.PathLevelAnalyzer.generate_path_level_cfg`
- `parsers.python_parser.PythonParser.parse`
- `visualization.enhanced_visualizer.EnhancedVisualizer.render`
- `llm.code_understanding_agent.CodeUnderstandingAgent.enhance_partition`
- `config.config.Config.load`
- `app.analyze_function_hierarchy`

## 调用关系

### 主要调用链

1. **app.analyze_function_hierarchy** (入口点)
   - 调用 `config.config.Config.load`
   - 调用 `parsers.python_parser.PythonParser.parse`
   - 调用 `visualization.enhanced_visualizer.EnhancedVisualizer.generate_graph`
   - 调用 `visualization.enhanced_visualizer.EnhancedVisualizer.render`
   - 调用 `llm.code_understanding_agent.CodeUnderstandingAgent.enhance_partition`
   - 调用 `llm.code_understanding_agent.CodeUnderstandingAgent.analyze_code`
   - 调用 `analysis.path_level_analyzer.generate_path_level_cfg`
   - 调用 `analysis.path_level_analyzer.generate_path_level_dfg`

2. **analysis.function_node_enhancer.FunctionNodeEnhancer**
   - `identify_leaf_nodes` → 调用内部方法
   - `explore_paths_in_partition` → 调用 `explore_paths`
   - `explore_paths` → 调用 `_build_reverse_graph` 和 `_backtrack_paths`
   - `add_function_nodes` → 操作超图

3. **analysis.path_level_analyzer.PathLevelAnalyzer**
   - `generate_path_level_cfg` → 调用 `_generate_method_cfg`, `_collect_cfg_nodes_edges`, `_add_method_call_edges`, `_generate_dot`
   - `generate_path_level_dfg` → 调用 `_generate_method_dfg`, `_collect_dfg_nodes_edges`, `_find_parameter_flows`, `_find_return_flows`, `_generate_dfg_dot`

4. **parsers.python_parser.PythonParser**
   - `parse` → 调用 `_build_ast`
   - `extract_classes` → 调用 `_traverse_for_classes` 和 `_process_classes`
   - `extract_functions` → 调用 `_traverse_for_functions`

5. **visualization.enhanced_visualizer.EnhancedVisualizer**
   - `render` → 调用 `_create_nodes`, `_create_edges`, `_calculate_statistics`
   - `generate_graph` → 创建图数据

6. **llm.code_understanding_agent.CodeUnderstandingAgent**
   - `enhance_partition` → 调用 `_analyze_code_structure`, `_add_semantic_labels`
   - `analyze_code` → 调用 `_extract_semantics`, `_identify_patterns`

7. **config.config.Config**
   - `load` → 调用 `_read_config_file`
   - `get` → 获取配置值

## 使用说明

这个演示代码包设计用于：

1. **功能层级分析演示**：展示如何分析代码的功能层级结构
2. **超图生成**：确保方法之间有真实的调用关系，超图能够正确显示
3. **路径分析**：展示如何从叶子节点回溯到入口点的路径
4. **调用图构建**：展示如何构建方法调用图

## 注意事项

- 所有方法签名都遵循四段内部格式
- 方法之间有真实的调用关系，形成连通分量
- 包含叶子节点（不调用其他分区内方法的节点）
- 包含入口点（不被分区内其他方法调用的节点）
- 包含不同长度的路径（2、3、4、5等）

## 与主程序的关系

这个演示代码包对应主程序（`app.py`）中步骤2.7和步骤6.5.4创建的演示分区。当主程序检测到没有符合要求的分区时，会使用这个演示代码包来创建演示分区，确保超图能够正确显示。


