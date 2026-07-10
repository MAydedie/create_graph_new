#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple


SECTION_TITLES: Dict[str, str] = {
    "overview": "项目概览",
    "partition_architecture": "功能架构",
    "core_call_chains": "核心调用链",
    "module_list": "模块清单",
    "design_patterns": "设计模式",
    "api_routes": "API 路由",
    "readme_summary": "README 摘要",
    "experience_stats": "经验库统计",
}

BUILT_IN_FALLBACK_TEMPLATE = """# {project_name} 项目说明书

## 1. 项目概览
{overview}

## 2. 功能架构
{partition_architecture}

## 3. 核心调用链
{core_call_chains}

## 4. 模块清单
{module_list}

## 5. 设计模式
{design_patterns}

## 6. API 路由
{api_routes}

## 7. README 摘要
{readme_summary}

## 8. 经验库统计
{experience_stats}
"""


def load_template(template_path: str | None) -> Tuple[str, str]:
    if not template_path:
        return BUILT_IN_FALLBACK_TEMPLATE, "built_in_fallback"
    path = Path(template_path)
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return BUILT_IN_FALLBACK_TEMPLATE, "built_in_fallback"
    placeholders = {"{overview}", "{partition_architecture}", "{core_call_chains}", "{module_list}", "{design_patterns}", "{api_routes}", "{readme_summary}", "{experience_stats}"}
    if not text.strip() or not all(placeholder in text for placeholder in placeholders):
        return BUILT_IN_FALLBACK_TEMPLATE, "built_in_fallback"
    return text, str(path.resolve()).replace("\\", "/")


def render_template(template: str, project_name: str, rendered_sections: Dict[str, str]) -> str:
    values = {key: rendered_sections.get(key, "") for key in SECTION_TITLES}
    values["project_name"] = project_name
    return template.format(**values).rstrip() + "\n"
