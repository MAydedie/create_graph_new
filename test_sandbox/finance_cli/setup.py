#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

# 读取 README 文件内容作为长描述
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# 读取依赖文件
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = fh.read().splitlines()

setup(
    # 基础元数据
    name="your-project-name",  # 项目名称，请根据实际情况修改
    version="0.1.0",  # 初始版本号
    author="Your Name",  # 作者姓名
    author_email="your.email@example.com",  # 作者邮箱
    description="A brief description of your project",  # 简短描述
    long_description=long_description,  # 详细描述（从 README 读取）
    long_description_content_type="text/markdown",  # 详细描述格式
    url="https://github.com/yourusername/your-project",  # 项目地址
    
    # 包管理
    packages=find_packages(where="src"),  # 自动发现包
    package_dir={"": "src"},  # 包目录映射
    include_package_data=True,  # 包含包数据文件
    
    # 依赖管理
    install_requires=requirements,  # 安装依赖
    python_requires=">=3.7",  # Python 版本要求
    
    # 分类信息
    classifiers=[
        "Development Status :: 3 - Alpha",  # 开发状态
        "Intended Audience :: Developers",  # 目标用户
        "Topic :: Software Development :: Build Tools",  # 主题分类
        "License :: OSI Approved :: MIT License",  # 许可证
        "Programming Language :: Python :: 3",  # 编程语言
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",  # 操作系统无关
    ],
    
    # 命令行工具入口点
    entry_points={
        "console_scripts": [
            "your-command=your_package.main:main",  # 命令行工具入口
        ],
    },
    
    # 项目关键词
    keywords="sample, project, template",  # 关键词列表
    
    # 许可证
    license="MIT",  # 许可证类型
    
    # 额外链接
    project_urls={
        "Bug Reports": "https://github.com/yourusername/your-project/issues",
        "Source": "https://github.com/yourusername/your-project",
    },
)