#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Shell 执行器 (Shell Executor)

安全地执行 Shell 命令，支持超时控制和输出限制。

安全特性：
- 超时控制：防止命令无限运行
- 输出限制：避免过长输出占用内存
- 工作目录限制：仅允许在项目目录内执行
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Union, Optional
import logging


logger = logging.getLogger("ShellExecutor")


class ShellExecutor:
    """
    Shell 命令执行器
    
    提供安全的命令执行能力，包含超时控制、输出限制等安全特性。
    """
    
    DEFAULT_TIMEOUT = 60  # 默认超时 60 秒
    MAX_OUTPUT_LINES = 500  # 最多保留 500 行输出
    
    def __init__(
        self,
        project_root: str = None,
        allowed_dirs: List[str] = None,
        default_timeout: int = DEFAULT_TIMEOUT
    ):
        """
        初始化 Shell 执行器
        
        Args:
            project_root: 项目根目录，默认为当前工作目录
            allowed_dirs: 允许执行命令的目录列表（相对于 project_root）
            default_timeout: 默认超时时间（秒）
        """
        self.project_root = Path(project_root or os.getcwd()).resolve()
        self.default_timeout = default_timeout
        
        # 默认只允许在项目根目录执行
        if allowed_dirs is None:
            self.allowed_dirs = [self.project_root]
        else:
            self.allowed_dirs = [
                (self.project_root / d).resolve() for d in allowed_dirs
            ]
        
        logger.info(f"ShellExecutor 初始化，项目根目录: {self.project_root}")
    
    def _is_dir_allowed(self, target_dir: Path) -> bool:
        """
        检查目标目录是否在允许范围内
        
        Args:
            target_dir: 目标目录
            
        Returns:
            是否允许
        """
        target_dir = target_dir.resolve()
        
        for allowed in self.allowed_dirs:
            try:
                # 检查是否是子目录
                target_dir.relative_to(allowed)
                return True
            except ValueError:
                continue
        
        return False
    
    def _limit_output(self, text: str, max_lines: int = None) -> tuple[str, bool]:
        """
        限制输出行数，保留尾部内容
        
        Args:
            text: 原始文本
            max_lines: 最大行数
            
        Returns:
            (限制后的文本, 是否被截断)
        """
        max_lines = max_lines or self.MAX_OUTPUT_LINES
        lines = text.splitlines()
        
        if len(lines) <= max_lines:
            return text, False
        
        # 保留尾部 max_lines 行
        kept_lines = lines[-max_lines:]
        truncated_text = f"... (省略前 {len(lines) - max_lines} 行)\n" + "\n".join(kept_lines)
        return truncated_text, True
    
    def run(
        self,
        cmd: Union[str, List[str]],
        cwd: str = None,
        timeout: int = None,
        capture_output: bool = True,
        shell: bool = True,
        max_output_lines: int = None
    ) -> Dict[str, Any]:
        """
        执行 Shell 命令
        
        Args:
            cmd: 命令字符串或命令列表
            cwd: 工作目录（相对于 project_root）
            timeout: 超时时间（秒），None 使用默认值
            capture_output: 是否捕获输出
            shell: 是否使用 shell 执行
            max_output_lines: 最大输出行数
            
        Returns:
            {
                "success": bool,
                "exit_code": int,
                "stdout": str,
                "stderr": str,
                "timeout": bool,
                "truncated": bool,
                "error": str (如果失败)
            }
        """
        timeout = timeout or self.default_timeout
        
        # 确定工作目录
        if cwd:
            work_dir = (self.project_root / cwd).resolve()
        else:
            work_dir = self.project_root
        
        # 安全检查：工作目录
        if not self._is_dir_allowed(work_dir):
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "timeout": False,
                "truncated": False,
                "error": f"工作目录不在允许范围内: {work_dir}"
            }
        
        if not work_dir.exists():
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "timeout": False,
                "truncated": False,
                "error": f"工作目录不存在: {work_dir}"
            }
        
        # 准备命令
        if isinstance(cmd, list):
            cmd_str = " ".join(cmd)
            cmd_exec = cmd
        else:
            cmd_str = cmd
            cmd_exec = cmd
        
        logger.info(f"执行命令: {cmd_str[:100]}... (工作目录: {work_dir})")
        
        try:
            # 执行命令
            result = subprocess.run(
                cmd_exec,
                cwd=str(work_dir),
                shell=shell,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='replace'  # 处理编码错误
            )
            
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            
            # 限制输出
            stdout, stdout_truncated = self._limit_output(stdout, max_output_lines)
            stderr, stderr_truncated = self._limit_output(stderr, max_output_lines)
            truncated = stdout_truncated or stderr_truncated
            
            success = result.returncode == 0
            
            if success:
                logger.info(f"命令执行成功，退出码: {result.returncode}")
            else:
                logger.warning(f"命令执行失败，退出码: {result.returncode}")
            
            return {
                "success": success,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "timeout": False,
                "truncated": truncated
            }
        
        except subprocess.TimeoutExpired as e:
            logger.error(f"命令执行超时 ({timeout}s): {cmd_str[:100]}")
            
            # 尝试获取部分输出
            stdout = e.stdout or "" if hasattr(e, 'stdout') else ""
            stderr = e.stderr or "" if hasattr(e, 'stderr') else ""
            
            stdout, _ = self._limit_output(stdout, max_output_lines)
            stderr, _ = self._limit_output(stderr, max_output_lines)
            
            return {
                "success": False,
                "exit_code": -1,
                "stdout": stdout,
                "stderr": stderr,
                "timeout": True,
                "truncated": True,
                "error": f"命令执行超时 ({timeout}s)"
            }
        
        except Exception as e:
            logger.error(f"命令执行异常: {e}")
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "timeout": False,
                "truncated": False,
                "error": f"命令执行异常: {str(e)}"
            }
    
    def run_python(
        self,
        script: str,
        cwd: str = None,
        timeout: int = None
    ) -> Dict[str, Any]:
        """
        执行 Python 脚本
        
        Args:
            script: Python 脚本路径（相对于 project_root）
            cwd: 工作目录
            timeout: 超时时间
            
        Returns:
            执行结果
        """
        cmd = f"python {script}"
        return self.run(cmd, cwd=cwd, timeout=timeout)
    
    def run_tests(
        self,
        test_path: str = None,
        cwd: str = None,
        timeout: int = None
    ) -> Dict[str, Any]:
        """
        运行测试
        
        Args:
            test_path: 测试文件/目录路径
            cwd: 工作目录
            timeout: 超时时间
            
        Returns:
            执行结果
        """
        if test_path:
            # 如果指定了测试路径，先尝试 pytest，失败则用 python
            cmd = f"python {test_path}"
        else:
            cmd = "pytest"
        
        return self.run(cmd, cwd=cwd, timeout=timeout)


# 便捷函数
def create_shell_executor(project_root: str = None) -> ShellExecutor:
    """
    创建 ShellExecutor 实例
    
    Args:
        project_root: 项目根目录
        
    Returns:
        ShellExecutor 实例
    """
    return ShellExecutor(project_root=project_root)
