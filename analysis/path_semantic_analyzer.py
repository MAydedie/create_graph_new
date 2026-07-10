#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件路径语义分析器 - 从文件路径提取语义信息
用于功能分区识别的路径语义分析
"""

import os
import re
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class PathSemanticAnalyzer:
    """文件路径语义分析器"""
    
    # 功能关键词映射（中英文）
    FUNCTION_KEYWORDS = {
        "parser": ["解析", "parsing", "parse", "解析器"],
        "analyzer": ["分析", "analysis", "analyze", "分析器"],
        "generator": ["生成", "generation", "generate", "生成器"],
        "visualizer": ["可视化", "visualization", "visualize", "可视化器"],
        "handler": ["处理", "handling", "handle", "处理器"],
        "service": ["服务", "service", "服务层"],
        "model": ["模型", "model", "数据模型"],
        "util": ["工具", "utility", "util", "工具类"],
        "utils": ["工具", "utility", "utils"],
        "helper": ["辅助", "helper", "辅助类"],
        "api": ["接口", "api", "接口层"],
        "auth": ["认证", "authentication", "auth", "权限"],
        "cache": ["缓存", "cache", "缓存层"],
        "database": ["数据库", "database", "db", "数据层"],
        "controller": ["控制器", "controller", "控制层"],
        "view": ["视图", "view", "视图层"],
        "test": ["测试", "test", "测试用例"],
        "config": ["配置", "config", "配置管理"],
        "middleware": ["中间件", "middleware"],
        "repository": ["仓库", "repository", "数据仓库"],
        "factory": ["工厂", "factory", "工厂模式"],
        "adapter": ["适配器", "adapter", "适配器模式"],
        "decorator": ["装饰器", "decorator", "装饰器模式"],
        "strategy": ["策略", "strategy", "策略模式"],
    }
    
    def __init__(self, project_path: Optional[str] = None):
        """
        初始化路径语义分析器
        
        Args:
            project_path: 项目根路径（用于计算相对路径）
        """
        self.project_path = project_path
    
    def extract_path_semantics(self, file_path: str) -> Dict[str, Any]:
        """
        从文件路径提取语义信息
        
        Args:
            file_path: 文件路径（绝对路径或相对路径）
        
        Returns:
            包含路径语义信息的字典：
            {
                "path_tokens": List[str],           # 路径token列表
                "suggested_functions": List[str],   # 推断的功能列表
                "path_depth": int,                  # 路径深度
                "naming_style": str,                # 命名风格
                "is_module": bool,                  # 是否是模块（深度>1）
                "is_test": bool,                    # 是否是测试文件
                "raw_path": str,                    # 原始路径
                "relative_path": str,               # 相对路径（如果提供了project_path）
                "folder_path": str,                 # 文件夹路径
                "file_name": str,                   # 文件名（不含扩展名）
            }
        """
        # 标准化路径
        normalized_path = file_path.replace('\\', '/')
        
        # 计算相对路径
        relative_path = normalized_path
        if self.project_path:
            try:
                rel_path = os.path.relpath(normalized_path, self.project_path)
                relative_path = rel_path.replace('\\', '/')
            except ValueError:
                # 如果无法计算相对路径，使用原始路径
                pass
        
        # 提取路径部分
        raw_path_parts = [part for part in relative_path.split('/') if part]
        path_parts = [
            Path(part).stem if part.endswith('.py') else part
            for part in raw_path_parts
        ]
        
        # 分离文件夹路径和文件名
        if path_parts:
            file_name = path_parts[-1]
            folder_parts = path_parts[:-1]
            folder_path = '/'.join(folder_parts) if folder_parts else ''
        else:
            file_name = ''
            folder_parts = []
            folder_path = ''
        
        # 提取路径token
        tokens = self._extract_path_tokens(path_parts)
        
        # 识别测试文件
        is_test = self._is_test_file(file_name, folder_parts, tokens)
        
        # 识别命名风格
        naming_style = self._detect_naming_style(path_parts)
        
        # 推断功能（关键词匹配）
        suggested_functions = self._infer_functions_from_tokens(tokens)
        
        return {
            "path_tokens": tokens,
            "suggested_functions": suggested_functions,
            "path_depth": len(path_parts),
            "naming_style": naming_style,
            "is_module": len(path_parts) > 1,
            "is_test": is_test,
            "raw_path": file_path,
            "relative_path": relative_path,
            "folder_path": folder_path,
            "file_name": file_name,
        }

    def _extract_path_tokens(self, path_parts: List[str]) -> List[str]:
        """将路径分解为去重后的语义 token。"""
        tokens = []

        for part in path_parts:
            if not part:
                continue

            if '_' in part:
                tokens.extend(part.split('_'))
            elif re.match(r'^[A-Z]', part):
                camel_tokens = re.findall(r'[A-Z][a-z]*', part)
                tokens.extend(camel_tokens or [part])
            elif part[:1].islower() and re.search(r'[A-Z]', part[1:]):
                camel_tokens = re.findall(r'[a-z]+|[A-Z][a-z]*', part)
                tokens.extend(camel_tokens or [part])
            else:
                tokens.append(part.lower())

        seen = set()
        unique_tokens = []
        for token in tokens:
            token_lower = token.lower()
            if token_lower not in seen:
                seen.add(token_lower)
                unique_tokens.append(token_lower)

        return unique_tokens

    def _is_test_file(
        self,
        file_name: str,
        folder_parts: List[str],
        tokens: List[str],
    ) -> bool:
        """识别路径是否指向测试文件。"""
        if 'test' in file_name.lower():
            return True
        if any('test' in folder.lower() for folder in folder_parts):
            return True
        return any('test' in token.lower() for token in tokens)

    def _detect_naming_style(self, path_parts: List[str]) -> str:
        """检测路径各部分的主要命名风格。"""
        if not path_parts:
            return "unknown"

        has_snake = any('_' in part for part in path_parts)
        has_pascal = any(re.match(r'^[A-Z]', part) for part in path_parts)
        has_camel = any(
            part[:1].islower() and re.search(r'[A-Z]', part[1:])
            for part in path_parts
        )
        has_kebab = any('-' in part for part in path_parts)

        if has_snake and not has_pascal and not has_camel and not has_kebab:
            return "snake_case"
        if has_pascal and not has_snake and not has_camel and not has_kebab:
            return "PascalCase"
        if has_camel and not has_snake and not has_pascal and not has_kebab:
            return "camelCase"
        if has_kebab and not has_snake and not has_pascal and not has_camel:
            return "kebab-case"
        if sum((has_snake, has_pascal, has_camel, has_kebab)) > 1:
            return "mixed"
        return "unknown"

    def _infer_functions_from_tokens(self, tokens: List[str]) -> List[str]:
        """根据路径 token 和关键词表推断功能标签。"""
        functions = []
        tokens_lower = [token.lower() for token in tokens]

        for keyword, function_names in self.FUNCTION_KEYWORDS.items():
            if keyword.lower() in tokens_lower:
                functions.extend(function_names)

        seen = set()
        unique_functions = []
        for function_name in functions:
            if function_name not in seen:
                seen.add(function_name)
                unique_functions.append(function_name)

        return unique_functions

    def batch_extract(self, file_paths: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量提取路径语义，单个文件失败时保留错误信息。"""
        results = {}
        for file_path in file_paths:
            try:
                results[file_path] = self.extract_path_semantics(file_path)
            except Exception as exc:
                logger.warning(f"提取路径语义失败 {file_path}: {exc}")
                results[file_path] = {
                    "error": str(exc),
                    "raw_path": file_path,
                }

        return results


def infer_functional_domain(path: List[str]) -> str:
    """
    根据路径方法名做非常轻量的功能域推断（启发式）。
    """
    joined = " ".join(path).lower()
    rules = [
        ("auth", ["auth", "login", "token", "oauth", "jwt", "verify", "password"]),
        ("data", ["db", "dao", "repository", "save", "load", "query", "fetch"]),
        ("api", ["api", "route", "handler", "controller", "request", "response"]),
        ("analysis", ["analyze", "analysis", "graph", "cfg", "dfg", "call", "hypergraph"]),
        ("io", ["input", "output", "serialize", "deserialize", "parse", "format"]),
    ]
    for domain, keys in rules:
        if any(k in joined for k in keys):
            return domain
    return "general"


def generate_path_description(path: List[str]) -> str:
    """生成路径描述（启发式）。"""
    if not path:
        return ""
    if len(path) == 1:
        name = path[0].split(".")[-1]
        return f"围绕 {name} 的单点功能路径"
    start = path[0].split(".")[-1]
    end = path[-1].split(".")[-1]
    return f"从 {start} 到 {end} 的调用链，包含 {len(path)} 个方法"


def generate_semantic_label(path: List[str], keywords: List[str]) -> str:
    """生成语义标签（启发式）。"""
    if not path:
        return "空路径"
    domain = infer_functional_domain(path)
    # 优先用关键词拼一个可读标签
    if keywords:
        top = [k for k in keywords if k][:3]
        return f"{domain}: " + " / ".join(top)
    # fallback 用首尾方法
    start = path[0].split(".")[-1]
    end = path[-1].split(".")[-1]
    if start == end:
        return f"{domain}: {start}"
    return f"{domain}: {start} -> {end}"


def analyze_path_semantics(
    path: List[str],
    analyzer_report=None,
    method_profiles: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Phase 1 / Task 1.1: 路径级语义画像（轻量启发式）
    - 不依赖 LLM，保证稳定；只新增字段，不影响现有逻辑。
    """
    method_profiles = method_profiles or {}

    # 汇总关键词：方法名 + docstring/comments/装饰器等线索
    keywords_set = []

    def add_kw(w: str):
        w = (w or "").strip()
        if not w:
            return
        lw = w.lower()
        if lw not in {k.lower() for k in keywords_set}:
            keywords_set.append(w)

    for sig in path or []:
        add_kw(sig.split(".")[-1])
        prof = method_profiles.get(sig)
        if not prof:
            continue
        # code_clues 里尽可能抽一些“短 token”
        clues = getattr(prof, "code_clues", None) or (prof.get("code_clues") if isinstance(prof, dict) else None) or {}
        for dec in clues.get("decorators", []) or []:
            add_kw(str(dec))
        doc = clues.get("docstring") or ""
        if isinstance(doc, str) and doc.strip():
            add_kw(doc.strip().splitlines()[0][:40])
        for c in clues.get("comments", []) or []:
            if isinstance(c, str) and c.strip():
                add_kw(c.strip()[:40])

    functional_domain = infer_functional_domain(path or [])
    semantic_label = generate_semantic_label(path or [], keywords_set)
    description = generate_path_description(path or [])

    return {
        "semantic_label": semantic_label,
        "keywords": keywords_set,
        "functional_domain": functional_domain,
        "description": description,
    }


def main():
    """测试代码"""
    import sys
    
    analyzer = PathSemanticAnalyzer(project_path="D:/代码仓库生图/create_graph")
    
    # 测试用例
    test_paths = [
        "D:/代码仓库生图/create_graph/parsers/python_parser.py",
        "D:/代码仓库生图/create_graph/analysis/call_graph_analyzer.py",
        "D:/代码仓库生图/create_graph/llm/code_understanding_agent.py",
        "D:/代码仓库生图/create_graph/test/test_analyzer.py",
        "D:/代码仓库生图/create_graph/utils/helper_functions.py",
    ]
    
    print("=" * 60)
    print("路径语义分析测试")
    print("=" * 60)
    
    for path in test_paths:
        print(f"\n文件路径: {path}")
        semantics = analyzer.extract_path_semantics(path)
        print(f"  路径token: {semantics['path_tokens']}")
        print(f"  推断功能: {semantics['suggested_functions']}")
        print(f"  路径深度: {semantics['path_depth']}")
        print(f"  命名风格: {semantics['naming_style']}")
        print(f"  是否测试: {semantics['is_test']}")
        print(f"  相对路径: {semantics['relative_path']}")


if __name__ == "__main__":
    main()

















































