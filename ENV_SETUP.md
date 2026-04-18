# 环境变量配置说明

## 📋 概述

本项目使用环境变量管理敏感信息（如 API Key），避免硬编码在代码中。

## 🔧 配置步骤

### 步骤1: 安装 python-dotenv

```bash
pip install python-dotenv
```

或者使用 requirements.txt：

```bash
pip install -r requirements.txt
```

### 步骤2: 创建 .env 文件

在项目根目录（`D:\代码仓库生图\create_graph\`）创建 `.env` 文件：

```bash
# Windows PowerShell
New-Item -Path .env -ItemType File -Force

# Linux/Mac
touch .env
```

### 步骤3: 配置 API Key

编辑 `.env` 文件，添加以下内容：

```env
# DeepSeek API 配置
DEEPSEEK_API_KEY=sk-1a507b1f2afc4a37bb35bbc6b6e87595
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

**注意**：请将 `sk-1a507b1f2afc4a37bb35bbc6b6e87595` 替换为你自己的 API Key。

### 步骤4: 验证配置

运行以下命令验证环境变量是否正确加载：

```python
# 在项目根目录运行
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('API Key:', os.getenv('DEEPSEEK_API_KEY')[:10] + '...')"
```

如果输出显示你的 API Key 前10个字符，说明配置成功。

## 🔒 安全提示

1. ✅ **.env 文件已在 .gitignore 中**，不会被提交到 Git 仓库
2. ✅ **不要将 .env 文件上传到 GitHub 或其他公共仓库**
3. ✅ **不要在代码中硬编码 API Key**
4. ✅ **如果 API Key 泄露，请立即在 DeepSeek 平台重新生成**

## 📝 示例 .env 文件内容

```env
# DeepSeek API 配置
DEEPSEEK_API_KEY=sk-your-api-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# 可选：OpenAI API 配置（如果使用 OpenAI）
# OPENAI_API_KEY=sk-your-openai-key-here
```

## 🚀 使用方式

代码会自动从 `.env` 文件加载环境变量：

```python
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 读取环境变量
api_key = os.getenv('DEEPSEEK_API_KEY')
base_url = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')

if not api_key:
    raise ValueError("DEEPSEEK_API_KEY 环境变量未设置，请在 .env 文件中配置")
```

## ❓ 常见问题

### Q1: 运行时报错 "DEEPSEEK_API_KEY 环境变量未设置"

**解决方案**：
1. 检查 `.env` 文件是否存在于项目根目录
2. 检查 `.env` 文件中的 `DEEPSEEK_API_KEY` 是否正确配置
3. 确保已安装 `python-dotenv`：`pip install python-dotenv`
4. 确保代码中调用了 `load_dotenv()`

### Q2: .env 文件会被提交到 Git 吗？

**答案**：不会。`.env` 文件已在 `.gitignore` 中，不会被提交到 Git 仓库。

### Q3: 如何在生产环境中配置？

**方案1**：使用环境变量（推荐）
- 在服务器上直接设置环境变量：`export DEEPSEEK_API_KEY=sk-...`
- 或者在 Docker 中使用 `-e DEEPSEEK_API_KEY=sk-...`

**方案2**：使用配置文件
- 在生产服务器上创建 `.env` 文件（不提交到 Git）
- 确保 `.env` 文件权限设置为仅所有者可读：`chmod 600 .env`

---

**最后更新**：2024-01-XX



































