# 环境变量配置快速指南

## 🚀 快速开始

### 1. 创建 .env 文件

在项目根目录（`D:\代码仓库生图\create_graph\`）创建 `.env` 文件。

**Windows PowerShell:**
```powershell
New-Item -Path .env -ItemType File -Force
notepad .env
```

**Linux/Mac:**
```bash
touch .env
nano .env
```

### 2. 添加以下内容到 .env 文件

```env
DEEPSEEK_API_KEY=sk-1a507b1f2afc4a37bb35bbc6b6e87595
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

**重要**：请将上面的 API Key 替换为你自己的 API Key（如果不同）。

### 3. 安装依赖

```bash
pip install python-dotenv
```

或者：

```bash
pip install -r requirements.txt
```

### 4. 验证配置

运行应用后，如果没有报错，说明配置成功。

---

## ✅ 完成

现在你的 API Key 已经安全地存储在 `.env` 文件中，不会被提交到 Git 仓库。

详细配置说明请参考 `ENV_SETUP.md`。



































