# DeepSeek API Key 存放位置汇总

## 📍 找到的所有位置

### 1. **app.py** (2处)
- **第509行**: `api_key = os.getenv('DEEPSEEK_API_KEY', 'sk-a7e7d7ee44594ac98c27d64a7496742f')`
- **第1216行**: `api_key = os.getenv('DEEPSEEK_API_KEY', 'sk-a7e7d7ee44594ac98c27d64a7496742f')`
- ✅ 使用环境变量，但有硬编码的默认值

### 2. **llm/code_understanding_agent.py** (1处)
- **第947行**: `api_key = "sk-a7e7d7ee44594ac98c27d64a7496742f"` (测试代码中)
- ❌ 硬编码在测试代码中

### 3. **run_hierarchical_analysis.py** (1处)
- **第35行**: `api_key = "sk-a7e7d7ee44594ac98c27d64a7496742f"`
- ❌ 硬编码

### 4. **test_stage3_stage4_comprehensive.py** (1处)
- **第148行**: `api_key = os.getenv('DEEPSEEK_API_KEY', 'sk-a7e7d7ee44594ac98c27d64a7496742f')`
- ✅ 使用环境变量，但有硬编码的默认值

### 5. **config/config.py**
- ⚠️ 只有 `OPENAI_API_KEY`，没有 DeepSeek 的配置

---

## 🔒 安全建议

### ⚠️ 重要提醒
**你的 API key 已经暴露在代码中了！** 在推送到 GitHub 之前，必须：

1. **移除所有硬编码的 API key**
2. **使用环境变量或配置文件**
3. **确保 `.gitignore` 包含 `.env` 文件**

---

## 🛠️ 推荐的安全配置方案

### 方案 1: 使用环境变量（推荐）

#### 步骤 1: 创建 `.env` 文件（已在 .gitignore 中）
```bash
# .env 文件
DEEPSEEK_API_KEY=sk-a7e7d7ee44594ac98c27d64a7496742f
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

#### 步骤 2: 修改代码，移除硬编码的默认值
```python
# 修改前
api_key = os.getenv('DEEPSEEK_API_KEY', 'sk-a7e7d7ee44594ac98c27d64a7496742f')

# 修改后
api_key = os.getenv('DEEPSEEK_API_KEY')
if not api_key:
    raise ValueError("DEEPSEEK_API_KEY 环境变量未设置")
```

### 方案 2: 在 config/config.py 中统一管理

在 `config/config.py` 中添加：
```python
# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', None)
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
```

---

## 📝 需要修改的文件清单

1. ✅ **app.py** - 移除硬编码默认值（2处）
2. ✅ **llm/code_understanding_agent.py** - 移除测试代码中的硬编码
3. ✅ **run_hierarchical_analysis.py** - 改为使用环境变量
4. ✅ **test_stage3_stage4_comprehensive.py** - 移除硬编码默认值
5. ✅ **config/config.py** - 添加 DeepSeek 配置

---

## 🚀 下一步操作

我可以帮你：
1. 移除所有硬编码的 API key
2. 统一使用环境变量或配置文件
3. 创建 `.env.example` 模板文件（不含真实 key）
4. 更新 `.gitignore` 确保 `.env` 不被提交

需要我帮你执行这些修改吗？





































