"""
配置文件 - 系统全局配置
"""

# ============= 解析器配置 =============

# 最大追踪深度（防止无限递归）
MAX_DEPTH = 10

# 忽略的文件模式
IGNORE_PATTERNS = [
    'test_', 'conftest.py', '__pycache__',
    '.git', '.venv', 'venv', 'node_modules',
    '*.pyc', '*.pyo', '__cache__'
]

# 忽略的目录
IGNORE_DIRS = ['.git', '.venv', 'venv', '__pycache__', '.pytest_cache']

# ============= 输出配置 =============

# 导出格式
EXPORT_FORMATS = ['json', 'markdown', 'html']

# 图表布局算法
GRAPH_LAYOUT = 'dagre'  # 可选: 'dagre', 'cose', 'circle'

# ============= 分析配置 =============

# 是否分析第三方库
ANALYZE_EXTERNAL_LIBS = False

# 最大方法调用深度
MAX_CALL_DEPTH = 8

# 是否检测循环调用
DETECT_CYCLES = True

# ============= 可视化配置 =============

# 图表节点大小
NODE_SIZES = {
    'class': (120, 60),
    'method': (100, 40),
    'function': (100, 40)
}

# 图表颜色
NODE_COLORS = {
    'class': '#3498db',
    'method': '#2ecc71',
    'function': '#e74c3c'
}

# 边样式
EDGE_STYLES = {
    'calls': {
        'line_color': '#f39c12',
        'target_arrow_shape': 'vee',
        'width': 1.5
    },
    'inherits': {
        'line_color': '#9b59b6',
        'target_arrow_shape': 'triangle',
        'width': 2
    },
    'contains': {
        'line_color': '#95a5a6',
        'line_style': 'dotted',
        'width': 1,
        'opacity': 0.5
    }
}

# ============= 报告配置 =============

# 是否生成 Markdown 报告
GENERATE_MARKDOWN = True

# 是否生成 JSON 报告
GENERATE_JSON = True

# 是否生成 HTML 可视化
GENERATE_HTML = True

# 是否生成执行流指南
GENERATE_EXECUTION_GUIDE = True

# ============= 日志配置 =============

# 日志级别
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR

# 详细模式
VERBOSE = False

# ============= 性能配置 =============

# 是否缓存解析结果
USE_CACHE = False

# 缓存目录
CACHE_DIR = './.cache'

# 并行处理文件数
PARALLEL_JOBS = 1  # 0 表示自动

# ============= 高级配置 =============

# Python 版本
PYTHON_VERSION = '3.8'

# 支持的编程语言
SUPPORTED_LANGUAGES = ['python', 'java']

# 默认语言
DEFAULT_LANGUAGE = 'python'

# ============= 功能开关 =============

# 是否启用 AI 语义分析
ENABLE_AI_ANALYSIS = False  # 需要 OpenAI API

# 是否启用数据流分析
ENABLE_DATA_FLOW = True

# 是否启用依赖分析
ENABLE_DEPENDENCY_ANALYSIS = True

# 是否启用复杂度计算
ENABLE_COMPLEXITY_ANALYSIS = True

# ============= API 配置（如果启用 AI）=============

import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# DeepSeek API 配置
DEEPSEEK_API_KEY = "sk-1a507b1f2afc4a37bb35bbc6b6e87595"
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')

# ============= Model Cache Configuration =============
from pathlib import Path

# 设置HuggingFace缓存目录
PROJECT_ROOT = Path(__file__).parent.parent
MODEL_CACHE_DIR = PROJECT_ROOT / "models" / "huggingface_cache"
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 设置环境变量
os.environ["HF_HOME"] = str(MODEL_CACHE_DIR)
os.environ["TRANSFORMERS_CACHE"] = str(MODEL_CACHE_DIR)
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"  # 使用镜像加速


# OpenAI API Key (保留兼容性)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# OpenAI 模型
OPENAI_MODEL = 'gpt-4'

API_TIMEOUT = 30


# ============= RAG System Configuration =============
# Migrated from 喜哥问答agent

# DeepSeek Model Config
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

# RAG Configuration
RAG_CONFIG = {
    "retrieval_top_k": 25,
    "rerank_top_k": 5,
    "temperature": 0.7,
    "max_tokens": 1000,
}

# Vector Database Configuration
VECTOR_DB_CONFIG = {
    "index_type": "flat",
    "embedding_dim": 512,
}

# Embedding Model Configuration
EMBEDDING_CONFIG = {
    "model_name": "BAAI/bge-small-zh-v1.5",
    "batch_size": 32,
}

# Re-ranker Configuration
RERANKER_CONFIG = {
    "model_name": "BAAI/bge-reranker-base",
}

# Data Paths (Updated references to create_graph structure)
import os
DATA_CONFIG = {
    # Points to the copied qna_source directory
    "excel_file": os.path.join("data", "qna_source", "喜哥帮AI客服Q&A【知识库】20260119.xlsx"),
    "index_dir": "data",
    "faiss_index": os.path.join("data", "faiss_index.bin"),
    "metadata_file": os.path.join("data", "metadata.pkl"),
}


# ============= Model Cache Configuration =============
# 防止模型每次启动都重新下载

import os
from pathlib import Path

# 设置HuggingFace缓存目录
PROJECT_ROOT = Path(__file__).parent.parent
MODEL_CACHE_DIR = PROJECT_ROOT / "models" / "huggingface_cache"
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 设置环境变量（确保sentence-transformers使用此缓存）
os.environ["HF_HOME"] = str(MODEL_CACHE_DIR)
os.environ["TRANSFORMERS_CACHE"] = str(MODEL_CACHE_DIR)
os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(MODEL_CACHE_DIR)
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"  # 使用镜像加速下载

print(f"[Config] 模型缓存目录: {MODEL_CACHE_DIR}")
