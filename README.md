# 📊 代码分析与可视化系统

一个**强大的、企业级的代码分析与可视化工具**，用于深度理解代码仓库的结构、调用关系和执行流程。

## ✨ 核心特性

### 🔍 **深度代码分析**
- ✅ **完整的代码解析** - 提取所有类、方法、函数和字段
- ✅ **符号表管理** - 建立完整的符号表用于名称解析
- ✅ **调用图生成** - 追踪所有方法间的调用关系
- ✅ **继承关系分析** - 识别类之间的继承和实现关系
- ✅ **执行流追踪** - 从入口点开始追踪完整的执行路径

### 📈 **多维可视化**
- ✅ **交互式代码图表** - 使用 Cytoscape.js 生成美观的、可交互的图表
- ✅ **分层展示** - 类、方法、调用关系的清晰分层
- ✅ **实时搜索和过滤** - 快速找到感兴趣的代码元素
- ✅ **缩放和导航** - 灵活的视图控制

### 📋 **智能报告生成**
- ✅ **Markdown 分析报告** - 详细的文本分析报告
- ✅ **JSON 数据导出** - 结构化的数据用于进一步分析
- ✅ **项目统计** - 代码规模、复杂度等关键指标
- ✅ **执行流指南** - 逐步的项目运行流程说明

### 🚀 **执行流分析**
- ✅ **入口点识别** - 自动识别 main 方法和 __main__ 块
- ✅ **关键路径分析** - 找到最重要的执行路径
- ✅ **循环调用检测** - 识别可能的递归或循环调用
- ✅ **调用深度分析** - 分析调用链的深度和复杂性

## 🛠️ 支持的语言

### 当前支持
- 🐍 **Python** - 完整支持（使用 Python AST）
  
### 计划支持
- ☕ **Java** - 使用 Soot 框架（开发中）
- 🔄 **其他语言** - 通过 Tree-Sitter 扩展

## 📦 项目结构

```
create_graph/
├── analysis/                      # 代码分析核心
│   ├── __init__.py
│   ├── code_model.py             # 数据模型定义
│   ├── symbol_table.py           # 符号表实现
│   ├── call_graph.py             # 调用图生成
│   └── semantic_analyzer.py      # 语义分析（未来）
│
├── parsers/                       # 代码解析器
│   ├── __init__.py
│   ├── base_parser.py            # 基类
│   ├── python_parser.py          # Python 解析器
│   └── java_parser.py            # Java 解析器（计划）
│
├── visualization/                 # 可视化和报告
│   ├── __init__.py
│   ├── graph_data.py             # 图表数据转换
│   ├── report_generator.py       # 报告生成
│   └── templates/
│       └── visualization.html    # HTML 模板
│
├── config/                        # 配置管理
│   ├── __init__.py
│   └── config.py
│
├── main.py                        # 主程序入口
├── requirements.txt               # 依赖包
└── README.md                      # 文档
```

## 🚀 快速开始

### 1. 安装依赖

```bash
# 克隆或进入项目目录
cd create_graph

# 安装 Python 依赖
pip install -r requirements.txt
```

### 2. 分析代码项目

```bash
# 分析 Python 项目
python main.py /path/to/your/project -o output -l python

# 示例：分析当前目录
python main.py . -o analysis_output

# 带详细输出
python main.py /path/to/project -v
```

### 3. 查看结果

分析完成后，在输出目录中生成以下文件：

- 📊 **graph_data.json** - Cytoscape.js 格式的图表数据
- 📄 **analysis_report.md** - Markdown 格式的详细分析报告
- 📊 **report_summary.json** - JSON 格式的汇总报告
- 🌐 **visualization.html** - 交互式可视化（在浏览器中打开）

```bash
# 在浏览器中打开可视化
open output/visualization.html  # macOS
start output/visualization.html # Windows
xdg-open output/visualization.html # Linux
```

## 📊 命令行用法

### 基本语法

```bash
python main.py <project_path> [options]
```

### 参数说明

| 参数 | 短选项 | 说明 | 默认值 |
|------|-------|------|--------|
| project_path | - | 要分析的项目路径 | 必需 |
| --output | -o | 输出目录 | output |
| --language | -l | 编程语言 (python/java) | python |
| --verbose | -v | 详细输出 | False |

### 使用示例

```bash
# 分析 Python 项目
python main.py ./my_project -o ./analysis

# 详细模式分析
python main.py ./my_project -v

# 指定输出目录
python main.py /home/user/projects/myapp -o /tmp/reports
```

## 🎨 交互式可视化功能

### 基本操作

| 操作 | 说明 |
|------|------|
| 🖱️ 点击节点 | 显示节点详情 |
| 🔍 悬停 | 高亮相关连接 |
| 🔍+ / 🔍- | 放大/缩小 |
| 📊 适应屏幕 | 调整到最佳视图 |
| 🔄 重置 | 重置图表布局 |
| 🔎 搜索框 | 实时搜索和过滤 |

### 图形元素

| 颜色 | 类型 | 说明 |
|------|------|------|
| 🔵 蓝色 | 类 | 代码中定义的类 |
| 🟢 绿色 | 方法 | 类中的方法 |
| 🔴 红色 | 函数 | 模块级函数 |
| → 箭头 | 调用 | 方法调用关系 |
| ▲ 箭头 | 继承 | 类继承关系 |
| ⋯ 虚线 | 包含 | 类包含方法关系 |

## 📈 分析报告示例

### 项目概览
```
总文件数:     15
总行数:      2,340
类的数量:      8
方法总数:     45
函数总数:      12
```

### 代码结构
```
GeneticAlgorithm
├── __init__
├── run
├── fitness
├── select_parents
├── crossover
├── mutate
└── initialize_population

GradientDescent
├── __init__
├── gradient
└── run
```

### 调用关系
```
总调用关系: 32
循环调用: 0
最常被调用的方法:
- fitness: 15 次
- run: 8 次
```

## 🔧 API 使用示例

### Python 代码中使用

```python
from parsers.python_parser import PythonParser
from analysis.call_graph import CallGraph, ExecutionFlowAnalyzer
from visualization.graph_data import GraphDataConverter

# 1. 解析项目
parser = PythonParser('./my_project')
report = parser.parse_project()

# 2. 构建调用图
call_graph = CallGraph(report)

# 3. 分析执行流
flow_analyzer = ExecutionFlowAnalyzer(call_graph, report)
execution_paths = flow_analyzer.analyze_execution_flow()

# 4. 生成可视化
converter = GraphDataConverter(report, call_graph)
converter.export_to_json('output/graph_data.json')
```

## 📚 数据结构

### ClassInfo
```python
{
    "name": "GeneticAlgorithm",
    "full_name": "GeneticAlgorithm",
    "parent_class": None,
    "methods": { "run": MethodInfo, ... },
    "fields": { ... },
    "source_location": SourceLocation
}
```

### MethodInfo
```python
{
    "name": "run",
    "class_name": "GeneticAlgorithm",
    "signature": "GeneticAlgorithm.run()",
    "return_type": "tuple",
    "parameters": [Parameter, ...],
    "calls": set(),
    "source_location": SourceLocation
}
```

### ExecutionPath
```python
{
    "entry_method": MethodInfo,
    "steps": [ExecutionStep, ...],
    "total_depth": 5
}
```

## 🎯 工作流程

```
1. 输入项目路径
   ↓
2. 选择解析器（Python/Java/其他）
   ↓
3. 代码解析
   ├─ 提取类和方法定义
   ├─ 建立符号表
   └─ 记录源代码位置
   ↓
4. 调用关系分析
   ├─ 遍历所有方法调用
   ├─ 构建调用图
   └─ 检测循环调用
   ↓
5. 执行流分析
   ├─ 识别入口点
   ├─ 追踪调用链
   └─ 分析执行深度
   ↓
6. 生成报告和可视化
   ├─ Markdown 文档
   ├─ JSON 数据
   └─ HTML 交互图表
```

## 🔄 支持的操作

### Python 代码分析

✅ 类定义和继承
✅ 方法和函数定义
✅ 方法参数和返回类型
✅ 方法调用关系
✅ 类字段/属性
✅ Docstring 提取
✅ 修饰符识别
✅ 作用域分析

### 关系分析

✅ 类继承关系
✅ 方法调用链
✅ 依赖关系
✅ 数据流（基础）
✅ 循环检测
✅ 调用深度

## 🚧 未来计划

### 阶段 2（逐步添加）
- [ ] Java 支持（Soot）
- [ ] AI Agent 语义分析
- [ ] 更详细的数据流分析
- [ ] 性能瓶颈识别
- [ ] 自动化测试覆盖率分析

### 阶段 3（高级功能）
- [ ] 完整的数据流图
- [ ] 并发分析
- [ ] 安全漏洞检测
- [ ] 代码质量评分
- [ ] 自动化重构建议

## 📝 配置文件

创建 `config/config.py` 进行自定义配置：

```python
# 解析器配置
MAX_DEPTH = 10  # 最大追踪深度
IGNORE_PATTERNS = ['test_', '__pycache__']

# 输出配置
EXPORT_FORMATS = ['json', 'markdown', 'html']
GRAPH_LAYOUT = 'dagre'  # cytoscape 布局算法
```

## 🐛 常见问题

### Q: 如何分析大型项目？
A: 系统支持大型项目分析。对于超过 10,000 行代码的项目，建议：
- 使用 `-v` 模式查看进度
- 在输出目录中查看中间结果
- 根据需要调整配置参数

### Q: 如何排除某些文件/目录？
A: 编辑 `config/config.py`，添加 `IGNORE_PATTERNS`：
```python
IGNORE_PATTERNS = ['test_', 'conftest.py', '__pycache__']
```

### Q: 可视化无法加载怎么办？
A: 确保 `graph_data.json` 和 `visualization.html` 在同一目录中。

## 📞 支持和反馈

- 📧 问题报告：请提交 Issue
- 💡 功能建议：欢迎讨论
- 🤝 贡献代码：欢迎 Pull Request

## 📄 许可证

MIT License

## 🙏 致谢

感谢以下开源项目的支持：
- [Cytoscape.js](https://js.cytoscape.org/) - 图表可视化
- [Dagre](https://github.com/dagrejs/dagre) - 图布局算法
- Python AST - 代码解析

---

**版本**: 1.0.0  
**最后更新**: 2025年12月6日

**🌟 如果这个项目对您有帮助，请给个 Star！**
