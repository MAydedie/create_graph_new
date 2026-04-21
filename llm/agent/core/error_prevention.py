#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ErrorPreventionChecker - 错误预防检查器 - Phase 5.2

在执行前检查潜在问题，预防错误发生。

核心功能：
1. 文件访问检查
2. 依赖检查
3. 语法检查
4. 资源检查
"""

import os
import ast
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


logger = logging.getLogger("ErrorPreventionChecker")


@dataclass
class CheckResult:
    """检查结果"""
    safe: bool
    warnings: List[str]
    suggestions: List[str]
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "safe": self.safe,
            "warnings": self.warnings,
            "suggestions": self.suggestions
        }


class ErrorPreventionChecker:
    """
    错误预防检查器
    
    在执行步骤前进行预防性检查，避免常见错误。
    
    检查项：
    1. 文件访问检查 - 文件是否存在、是否有权限
    2. 依赖检查 - 模块是否已安装
    3. 语法检查 - 代码语法是否正确
    4. 资源检查 - 磁盘空间、内存等
    
    使用示例：
    ```python
    checker = ErrorPreventionChecker()
    
    result = checker.check_before_execute({
        "action": "write",
        "target": "/path/to/file.py",
        "content": "print('hello')"
    })
    
    if not result.safe:
        print("警告:", result.warnings)
        print("建议:", result.suggestions)
    ```
    """
    
    def __init__(self, verbose: bool = True):
        """
        初始化检查器
        
        Args:
            verbose: 是否输出详细日志
        """
        self.verbose = verbose
        self.logger = logging.getLogger("ErrorPreventionChecker")
    
    def check_before_execute(self, step: Dict[str, Any]) -> CheckResult:
        """
        执行前检查
        
        Args:
            step: 执行步骤字典
        
        Returns:
            检查结果
        """
        warnings = []
        suggestions = []
        
        # 获取动作类型
        action = step.get("action", "")
        
        # 文件相关检查
        if action in ["read", "write", "edit"]:
            file_warnings, file_suggestions = self._check_file_access(step)
            warnings.extend(file_warnings)
            suggestions.extend(file_suggestions)
        
        # 代码相关检查
        if action in ["write", "edit"] and "content" in step:
            syntax_warnings, syntax_suggestions = self._check_syntax(step)
            warnings.extend(syntax_warnings)
            suggestions.extend(syntax_suggestions)
        
        # 导入相关检查
        if action in ["write", "edit"] and "content" in step:
            import_warnings, import_suggestions = self._check_imports(step)
            warnings.extend(import_warnings)
            suggestions.extend(import_suggestions)
        
        # 资源检查
        resource_warnings, resource_suggestions = self._check_resources(step)
        warnings.extend(resource_warnings)
        suggestions.extend(resource_suggestions)
        
        # 判断是否安全
        safe = len(warnings) == 0
        
        if self.verbose and warnings:
            self.logger.warning(f"发现 {len(warnings)} 个潜在问题")
        
        return CheckResult(
            safe=safe,
            warnings=warnings,
            suggestions=suggestions
        )
    
    def _check_file_access(self, step: Dict) -> tuple:
        """检查文件访问"""
        warnings = []
        suggestions = []
        
        target = step.get("target", "")
        action = step.get("action", "")
        
        if not target:
            return warnings, suggestions
        
        file_path = Path(target)
        
        # 检查文件是否存在
        if action == "read":
            if not file_path.exists():
                warnings.append(f"文件不存在: {target}")
                suggestions.append("检查文件路径是否正确")
        
        # 检查父目录是否存在
        if action in ["write", "edit"]:
            parent_dir = file_path.parent
            if not parent_dir.exists():
                warnings.append(f"父目录不存在: {parent_dir}")
                suggestions.append("创建父目录或检查路径")
        
        # 检查写权限
        if action in ["write", "edit"]:
            if file_path.exists():
                if not os.access(file_path, os.W_OK):
                    warnings.append(f"没有写权限: {target}")
                    suggestions.append("检查文件权限")
            else:
                # 检查父目录写权限
                parent_dir = file_path.parent
                if parent_dir.exists() and not os.access(parent_dir, os.W_OK):
                    warnings.append(f"没有写权限: {parent_dir}")
                    suggestions.append("检查目录权限")
        
        # 检查读权限
        if action == "read":
            if file_path.exists() and not os.access(file_path, os.R_OK):
                warnings.append(f"没有读权限: {target}")
                suggestions.append("检查文件权限")
        
        return warnings, suggestions
    
    def _check_syntax(self, step: Dict) -> tuple:
        """检查 Python 语法"""
        warnings = []
        suggestions = []
        
        content = step.get("content", "")
        target = step.get("target", "")
        
        # 只检查 Python 文件
        if not target.endswith(".py"):
            return warnings, suggestions
        
        if not content:
            return warnings, suggestions
        
        try:
            # 尝试解析语法
            ast.parse(content)
        except SyntaxError as e:
            warnings.append(f"语法错误: {e.msg} (行 {e.lineno})")
            suggestions.append("修正代码语法错误")
        except Exception as e:
            warnings.append(f"代码解析失败: {str(e)}")
            suggestions.append("检查代码格式")
        
        return warnings, suggestions
    
    def _check_imports(self, step: Dict) -> tuple:
        """检查导入语句"""
        warnings = []
        suggestions = []
        
        content = step.get("content", "")
        
        if not content:
            return warnings, suggestions
        
        try:
            # 解析代码
            tree = ast.parse(content)
            
            # 提取导入语句
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module.split('.')[0])
            
            # 检查常见的第三方库
            common_libs = {
                "numpy": "numpy",
                "pandas": "pandas",
                "requests": "requests",
                "flask": "flask",
                "django": "django"
            }
            
            for imp in imports:
                if imp in common_libs:
                    # 尝试导入
                    try:
                        __import__(imp)
                    except ImportError:
                        warnings.append(f"模块未安装: {imp}")
                        suggestions.append(f"运行: pip install {common_libs[imp]}")
        
        except Exception as e:
            # 解析失败，跳过导入检查
            pass
        
        return warnings, suggestions
    
    def _check_resources(self, step: Dict) -> tuple:
        """检查系统资源"""
        warnings = []
        suggestions = []
        
        # 检查磁盘空间
        try:
            import shutil
            
            target = step.get("target", "")
            if target:
                file_path = Path(target)
                parent_dir = file_path.parent if file_path.parent.exists() else Path(".")
                
                stat = shutil.disk_usage(parent_dir)
                free_gb = stat.free / (1024 ** 3)
                
                if free_gb < 0.1:  # 小于 100MB
                    warnings.append(f"磁盘空间不足: {free_gb:.2f} GB")
                    suggestions.append("清理磁盘空间")
        
        except Exception as e:
            # 检查失败，跳过
            pass
        
        return warnings, suggestions
    
    def _log(self, message: str):
        """输出日志"""
        if self.verbose:
            self.logger.info(message)


# 便捷函数
def check_step(step: Dict[str, Any]) -> CheckResult:
    """
    检查步骤（便捷函数）
    
    Args:
        step: 执行步骤
    
    Returns:
        检查结果
    """
    checker = ErrorPreventionChecker()
    return checker.check_before_execute(step)
