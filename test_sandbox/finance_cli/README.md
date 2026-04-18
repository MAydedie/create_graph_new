# 智能代码分析工具

一个基于 AI 的代码分析与重构工具，帮助开发者理解、优化和改进代码质量。

## 功能特性

- **代码智能分析**：自动分析代码结构、依赖关系和潜在问题
- **重构建议**：提供代码重构和优化建议
- **代码解释**：用自然语言解释复杂代码逻辑
- **质量评估**：评估代码质量并提供改进建议
- **多语言支持**：支持多种编程语言分析

## 安装方法

### 前提条件

- Python 3.8 或更高版本
- Git

### 安装步骤

1. 克隆项目仓库：
   ```bash
   git clone https://github.com/yourusername/code-analysis-tool.git
   cd code-analysis-tool
   ```

2. 创建虚拟环境（推荐）：
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # 或
   venv\Scripts\activate  # Windows
   ```

3. 安装依赖包：
   ```bash
   pip install -r requirements.txt
   ```

4. 配置环境变量：
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入必要的 API 密钥和配置
   ```

## 基本用法

### 命令行使用

```bash
# 分析单个文件
python main.py analyze --file path/to/your/file.py

# 分析整个目录
python main.py analyze --dir path/to/your/project

# 获取代码解释
python main.py explain --file path/to/your/file.py

# 获取重构建议
python main.py refactor --file path/to/your/file.py
```

### Python API 使用

```python
from code_analyzer import CodeAnalyzer

# 初始化分析器
analyzer = CodeAnalyzer()

# 分析代码
result = analyzer.analyze_file("path/to/your/file.py")
print(f"代码复杂度: {result.complexity}")
print(f"潜在问题: {result.issues}")

# 获取代码解释
explanation = analyzer.explain_code("path/to/your/file.py")
print(f"代码解释: {explanation}")
```

### 配置文件

项目使用 `config.yaml` 进行配置，主要配置项包括：

```yaml
analysis:
  max_file_size: 10000  # 最大文件大小（字节）
  supported_languages:  # 支持的语言
    - python
    - javascript
    - java
    - cpp

ai:
  model: "gpt-4"  # 使用的 AI 模型
  temperature: 0.3  # 生成温度
  max_tokens: 2000  # 最大 token 数

output:
  format: "markdown"  # 输出格式
  save_to_file: true  # 是否保存到文件
```

## 项目结构

```
.
├── src/                    # 源代码目录
│   ├── analyzers/         # 代码分析器
│   ├── ai/               # AI 相关功能
│   ├── utils/            # 工具函数
│   └── main.py           # 主程序
├── tests/                # 测试文件
├── config.yaml           # 配置文件
├── requirements.txt      # 依赖包列表
├── .env.example          # 环境变量示例
└── README.md            # 本文档
```

## 贡献指南

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 支持

- 问题反馈：[GitHub Issues](https://github.com/yourusername/code-analysis-tool/issues)
- 文档：[项目 Wiki](https://github.com/yourusername/code-analysis-tool/wiki)
- 邮件支持：support@example.com

## 更新日志

### v1.0.0 (2024-01-01)
- 初始版本发布
- 支持基础代码分析功能
- 提供 AI 驱动的代码解释
- 支持多语言分析
```