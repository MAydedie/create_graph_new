#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Shell 工具 (Shell Tools)

提供执行 Shell 命令和运行测试的工具。
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional


# 确保项目路径
def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "config" / "config.py").exists():
            return current
        current = current.parent
    return Path.cwd()

PROJECT_ROOT = _find_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from llm.agent.tools.base import Tool, ToolInputSchema
from llm.agent.infrastructure.shell_executor import ShellExecutor


class RunCommandTool(Tool):
    """
    执行 Shell 命令工具
    
    ⚠️ 警告：此工具可以执行任意命令，使用时需谨慎！
    """
    
    def __init__(self, project_root: str = None):
        """
        初始化 RunCommandTool
        
        Args:
            project_root: 项目根目录
        """
        self.executor = ShellExecutor(project_root=project_root or str(PROJECT_ROOT))
    
    @property
    def name(self) -> str:
        return "RunCommand"
    
    @property
    def description(self) -> str:
        return """执行 Shell 命令。

⚠️ 警告：此工具可以执行任意命令，请谨慎使用！

适用场景：
- 运行构建命令
- 执行脚本
- 查看系统信息

不适用场景：
- 修改系统配置
- 安装软件
- 删除重要文件"""
    
    @property
    def input_schema(self) -> Optional[ToolInputSchema]:
        return ToolInputSchema(
            properties={
                "command": {
                    "type": "string",
                    "description": "要执行的命令"
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录（相对于项目根目录），默认为项目根目录"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒），默认 60 秒"
                }
            },
            required=["command"]
        )
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行命令
        
        Args:
            command: 命令字符串
            cwd: 工作目录
            timeout: 超时时间
            
        Returns:
            执行结果
        """
        command = kwargs.get("command")
        cwd = kwargs.get("cwd")
        timeout = kwargs.get("timeout")
        
        if not command:
            return {
                "success": False,
                "error": "未指定命令"
            }
        
        result = self.executor.run(
            cmd=command,
            cwd=cwd,
            timeout=timeout
        )
        
        # 格式化输出
        if result["success"]:
            output = f"命令执行成功 (退出码: {result['exit_code']})\n\n"
            if result["stdout"]:
                output += f"标准输出:\n{result['stdout']}\n"
            if result["stderr"]:
                output += f"标准错误:\n{result['stderr']}\n"
            if result.get("truncated"):
                output += "\n⚠️ 输出已截断，仅显示尾部内容"
            
            return {
                "success": True,
                "result": output.strip()
            }
        else:
            error_msg = f"命令执行失败 (退出码: {result['exit_code']})\n\n"
            if result.get("timeout"):
                error_msg += "⚠️ 命令执行超时\n\n"
            if result["stderr"]:
                error_msg += f"错误信息:\n{result['stderr']}\n"
            if result["stdout"]:
                error_msg += f"\n标准输出:\n{result['stdout']}\n"
            if result.get("error"):
                error_msg += f"\n系统错误: {result['error']}"
            
            return {
                "success": False,
                "error": error_msg.strip()
            }


class RunTestsTool(Tool):
    """
    运行测试工具
    
    专门用于运行测试脚本，比 RunCommandTool 更安全。
    """
    
    def __init__(self, project_root: str = None):
        """
        初始化 RunTestsTool
        
        Args:
            project_root: 项目根目录
        """
        self.executor = ShellExecutor(project_root=project_root or str(PROJECT_ROOT))
    
    @property
    def name(self) -> str:
        return "RunTests"
    
    @property
    def description(self) -> str:
        return """运行测试脚本。

适用场景：
- 运行 Python 测试文件
- 验证代码修改是否破坏功能
- 检查测试是否通过

示例：
- test_agent_tools.py
- tests/test_*.py"""
    
    @property
    def input_schema(self) -> Optional[ToolInputSchema]:
        return ToolInputSchema(
            properties={
                "test_path": {
                    "type": "string",
                    "description": "测试文件路径（相对于项目根目录），例如 'test_agent_tools.py'"
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录（相对于项目根目录），默认为项目根目录"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒），默认 60 秒"
                }
            },
            required=["test_path"]
        )
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        运行测试
        
        Args:
            test_path: 测试文件路径
            cwd: 工作目录
            timeout: 超时时间
            
        Returns:
            执行结果
        """
        test_path = kwargs.get("test_path")
        cwd = kwargs.get("cwd")
        timeout = kwargs.get("timeout")
        
        if not test_path:
            return {
                "success": False,
                "error": "未指定测试文件路径"
            }
        
        result = self.executor.run_tests(
            test_path=test_path,
            cwd=cwd,
            timeout=timeout
        )
        
        # 格式化输出
        if result["success"]:
            output = f"✅ 测试通过！\n\n"
            if result["stdout"]:
                output += f"{result['stdout']}\n"
            if result.get("truncated"):
                output += "\n⚠️ 输出已截断，仅显示尾部内容"
            
            return {
                "success": True,
                "result": output.strip()
            }
        else:
            error_msg = f"❌ 测试失败 (退出码: {result['exit_code']})\n\n"
            if result.get("timeout"):
                error_msg += "⚠️ 测试执行超时\n\n"
            
            # 优先显示 stderr（通常包含错误信息）
            if result["stderr"]:
                error_msg += f"错误信息:\n{result['stderr']}\n"
            
            # 然后显示 stdout（可能包含测试输出）
            if result["stdout"]:
                error_msg += f"\n测试输出:\n{result['stdout']}\n"
            
            if result.get("error"):
                error_msg += f"\n系统错误: {result['error']}"
            
            return {
                "success": False,
                "error": error_msg.strip()
            }


# 便捷函数
def create_run_command_tool(project_root: str = None) -> RunCommandTool:
    """创建 RunCommandTool 实例"""
    return RunCommandTool(project_root=project_root)


def create_run_tests_tool(project_root: str = None) -> RunTestsTool:
    """创建 RunTestsTool 实例"""
    return RunTestsTool(project_root=project_root)
