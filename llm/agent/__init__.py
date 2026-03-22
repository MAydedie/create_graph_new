#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Agent 框架主入口
Phase 5: 智能代码 Agent - Option A: Hardcore Native

此模块是 Agent 框架的根目录，提供统一的导入入口。
"""

from .tools.base import Tool, ToolRegistry

__all__ = [
    "Tool",
    "ToolRegistry",
]
