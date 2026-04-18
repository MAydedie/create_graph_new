"""
CLI 工具包

提供命令行工具的核心功能模块。
"""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"
__description__ = "一个功能强大的命令行工具包"

# 导入核心模块，方便用户直接使用
from .core import main
from .parser import parse_args
from .utils import setup_logging

# 定义包的公开接口
__all__ = [
    "main",
    "parse_args",
    "setup_logging",
    "__version__",
    "__author__",
    "__description__",
]
