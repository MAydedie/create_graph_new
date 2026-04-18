#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_sandbox - 工具函数模块

用于测试跨文件修改能力
"""


def format_result(operation: str, a: int, b: int, result: int) -> str:
    """格式化计算结果"""
    return f"{a} {operation} {b} = {result}"
