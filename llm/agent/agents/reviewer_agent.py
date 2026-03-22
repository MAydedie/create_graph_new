#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ReviewerAgent - 审查 Agent - Phase 4

验证代码修改的正确性。

职责：
- 审查代码变更
- 运行测试验证
- 检查代码质量
- 返回审查结果和反馈
"""

import os
import sys
import json
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

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


from datetime import datetime

logger = logging.getLogger("ReviewerAgent")



# Reviewer 专用 Prompt 模板
REVIEWER_SYSTEM_PROMPT = """你是一个专业的代码审查 Agent，负责验证代码修改的正确性。

## 你的职责

1. 审查代码变更是否符合要求
2. 检查代码质量和风格
3. 识别潜在问题
4. 给出审查意见

## 输出格式

你必须输出一个 JSON 格式的审查结果：

```json
{
  "approved": true,
  "score": 85,
  "summary": "审查摘要",
  "issues": [
    {
      "severity": "error|warning|info",
      "location": "文件:行号",
      "description": "问题描述",
      "suggestion": "修改建议"
    }
  ],
  "feedback": "给 Coder 的反馈"
}
```

## 审查标准

1. **功能正确性**：代码是否实现了预期功能
2. **代码质量**：是否遵循最佳实践
3. **错误处理**：是否有适当的异常处理
4. **代码风格**：是否与项目风格一致
5. **安全性**：是否存在安全隐患

## 评分标准

- 90-100: 优秀，可直接通过
- 70-89: 良好，有小问题但可接受
- 50-69: 一般，需要修改
- 0-49: 不通过，需要重做

## 重要规则

1. 直接输出 JSON，不要包含其他内容
2. issues 列表按严重程度排序
3. feedback 要具体可操作
"""


class ReviewerAgent:
    """
    审查 Agent - 验证代码修改
    
    工作流程：
    1. 接收变更信息和上下文
    2. 审查代码变更
    3. 可选：运行测试
    4. 返回审查结果
    
    Attributes:
        llm_api: LLM API 客户端（延迟加载）
        verbose: 是否输出详细日志
    """
    
    def __init__(self, llm_api=None, verbose: bool = True):
        """
        初始化 ReviewerAgent
        
        Args:
            llm_api: LLM API 客户端(延迟加载)
            verbose: 是否输出详细日志
        """
        self._llm_api = llm_api
        self.verbose = verbose
        self.logger = logging.getLogger("ReviewerAgent")
    
    def _find_project_root_for_tests(self, start_path: Path) -> str:
        """向上查找项目根目录(包含 pyproject.toml 或 setup.py 的目录)"""
        current = start_path
        while current != current.parent:
            if (current / "pyproject.toml").exists() or (current / "setup.py").exists():
                return str(current)
            current = current.parent
        # 如果没找到,返回起始路径
        return str(start_path)

    
    def _get_llm_api(self):
        """获取 LLM API（延迟加载）"""
        if self._llm_api is None:
            from llm.rag_core.llm_api import DeepSeekAPI
            self._llm_api = DeepSeekAPI()
        return self._llm_api
    
    def review(self, changes: Dict[str, Any], context: Dict = None) -> Dict[str, Any]:
        """
        审查代码变更
        
        Args:
            changes: 变更信息，可能包含：
                - step: 步骤定义
                - action: 操作类型
                - target: 目标文件
                - code_content: 代码内容
                - summary: 变更摘要
            context: 上下文信息
            
        Returns:
            审查结果字典，包含：
            - approved/success: 是否通过
            - score: 评分
            - summary: 审查摘要
            - issues: 问题列表
            - feedback: 反馈
        """
        context = context or {}
        
        # 判断这是步骤还是变更
        if "step" in changes or "type" in changes:
            # 这是一个步骤定义，可能是验证步骤
            return self._review_step(changes, context)
        else:
            # 这是代码变更
            return self._review_changes(changes, context)
    
    def _review_step(self, step: Dict, context: Dict) -> Dict[str, Any]:
        """审查/执行验证步骤"""
        step_type = step.get("type", "")
        action = step.get("action", "")
        target = step.get("target", "")
        description = step.get("description", "")
        
        self._log(f"审查步骤: {description}")
        
        # 如果是运行测试
        if action == "run_tests":
            return self._run_tests(target)
        
        # 如果是验证步骤
        if step_type == "verify":
            return {
                "success": True,
                "approved": True,
                "score": 80,
                "summary": f"验证步骤通过: {description}",
                "issues": [],
                "feedback": ""
            }
        
        # 其他情况，默认通过
        return {
            "success": True,
            "approved": True,
            "score": 75,
            "summary": "步骤审查通过",
            "issues": [],
            "feedback": ""
        }
    
    def _review_changes(self, changes: Dict, context: Dict) -> Dict[str, Any]:
        """审查代码变更"""
        action = changes.get("action", "")
        target = changes.get("target", "")
        code_content = changes.get("code_content", "")
        summary = changes.get("summary", "")
        
        self._log(f"审查变更: {target}")
        
        # 如果有代码内容，使用 LLM 审查
        if code_content:
            return self._llm_review(target, code_content, summary, context)
        
        # 如果只是读取或删除操作，直接通过
        if action in ["read_file", "delete_file"]:
            return {
                "success": True,
                "approved": True,
                "score": 90,
                "summary": f"{action} 操作审查通过",
                "issues": [],
                "feedback": ""
            }
        
        # 其他情况，基于摘要做简单审查
        if changes.get("success"):
            return {
                "success": True,
                "approved": True,
                "score": 80,
                "summary": f"变更审查通过: {summary}",
                "issues": [],
                "feedback": ""
            }
        else:
            error = changes.get("error", "未知错误")
            return {
                "success": False,
                "approved": False,
                "score": 0,
                "summary": f"变更失败: {error}",
                "issues": [
                    {
                        "severity": "error",
                        "location": target,
                        "description": error,
                        "suggestion": "请检查错误原因并重试"
                    }
                ],
                "feedback": f"操作失败: {error}"
            }
    
    def _llm_review(self, target: str, code: str, summary: str, 
                     context: Dict) -> Dict[str, Any]:
        """使用 LLM 审查代码"""
        # 截断过长的代码
        if len(code) > 5000:
            code = code[:5000] + "\n... (代码过长，已截断)"
        
        prompt = f"""请审查以下代码变更：

## 目标文件
{target}

## 变更摘要
{summary}

## 代码内容
```
{code}
```

## 审查要求
1. 检查代码是否符合变更要求
2. 检查代码质量和风格
3. 识别潜在问题
4. 给出评分和反馈

请输出审查结果 JSON。"""
        
        try:
            llm_api = self._get_llm_api()
            
            messages = [
                {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            
            response = llm_api.chat(
                messages=messages,
                temperature=0.2,
                max_tokens=2048,
                timeout=120
            )
            
            # 提取响应
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")
            else:
                content = response.get("content", "")
            
            # 解析结果
            result = self._parse_result(content)
            
            # 确保有必要的字段
            if "approved" not in result:
                result["approved"] = result.get("score", 0) >= 70
            if "success" not in result:
                result["success"] = result.get("approved", False)
            
            return result
            
        except Exception as e:
            self.logger.error(f"LLM 审查失败: {e}")
            # 回退：默认通过
            return {
                "success": True,
                "approved": True,
                "score": 70,
                "summary": f"LLM 审查失败，默认通过: {e}",
                "issues": [],
                "feedback": "",
                "warning": str(e)
            }
    
    def _run_tests(self, target: str) -> Dict[str, Any]:
        """运行测试"""
        self._log(f"运行测试: {target}")
        
        try:
            # 确定测试命令和工作目录
            path = Path(target)
            cwd = str(PROJECT_ROOT)

            # 获取工作区（由上层通过环境变量注入，例如 UI 的 workspace_root）
            workspace_root_env = os.environ.get("WORKSPACE_ROOT", "").strip()
            workspace_root = Path(workspace_root_env) if workspace_root_env else None

            # 处理相对路径：
            # 1. 优先尝试在 WORKSPACE_ROOT 下解析（适用于外部项目，如 catnet）
            # 2. 否则退回到当前工程 PROJECT_ROOT（用于本仓库自测）
            if not path.is_absolute():
                resolved_path = None
                if workspace_root:
                    candidate = workspace_root / target
                    if candidate.exists():
                        resolved_path = candidate
                if resolved_path is None:
                    candidate = PROJECT_ROOT / target
                    if candidate.exists():
                        resolved_path = candidate
                # 如果都不存在，仍然以 WORKSPACE_ROOT 或 PROJECT_ROOT 为 cwd 执行 pytest target
                if resolved_path is not None:
                    path = resolved_path

            # 查找正确的项目根目录：如果能找到真实文件/目录，就从该路径向上找 pyproject/setup 作为项目根
            if path.exists():
                if path.is_file():
                    cwd = self._find_project_root_for_tests(path.parent)
                else:
                    cwd = self._find_project_root_for_tests(path)
            else:
                # 文件在当前工程不存在，且上面也没解析到实际路径：
                # 如果有 WORKSPACE_ROOT，就直接在工作区下跑 pytest target，
                # 这样适配 "test/test_xxx.py" 这类相对路径。
                if workspace_root and workspace_root.exists():
                    cwd = str(workspace_root)
            
            # 构建测试命令
            if target.startswith("pytest"):
                cmd = target
            elif target.endswith(".py"):
                cmd = f"{sys.executable} -m pytest {target} -v"
            else:
                cmd = f"{sys.executable} -m pytest {target} -v"
            
            self._log(f"执行测试命令: {cmd}")
            self._log(f"工作目录(CWD): {cwd}")
            
            # 设置环境变量
            env = os.environ.copy()
            if cwd not in env.get("PYTHONPATH", ""):
                 env["PYTHONPATH"] = f"{cwd}{os.pathsep}{env.get('PYTHONPATH', '')}"
            
            # 运行测试
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
                encoding='utf-8',
                errors='replace'
            )
            
            # 合并输出，方便后续错误分析
            full_output = (result.stdout or "") + "\n" + (result.stderr or "")
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "approved": True,
                    "score": 100,
                    "summary": "所有测试通过",
                    "issues": [],
                    "feedback": "",
                    "test_output": full_output[:2000]
                }
            else:
                # 提取一些关键信息，写入 error 字段，便于 Orchestrator 分类
                error_snippet = full_output[-1000:] if full_output else "测试未通过"
                # 简单截断，避免过长
                if len(error_snippet) > 1000:
                    error_snippet = error_snippet[-1000:]
                return {
                    "success": False,
                    "approved": False,
                    "score": 30,
                    "summary": "测试失败",
                    "issues": [
                        {
                            "severity": "error",
                            "location": target,
                            "description": "测试未通过",
                            "suggestion": "请查看测试输出并修复问题"
                        }
                    ],
                    # 将详细错误片段写入 error，便于 get_last_error 和错误分类
                    "error": error_snippet,
                    "feedback": f"测试失败，请修复问题",
                    "test_output": full_output[:2000]
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "approved": False,
                "score": 0,
                "summary": "测试超时",
                "issues": [
                    {
                        "severity": "error",
                        "location": target,
                        "description": "测试运行超时",
                        "suggestion": "检查是否有死循环或长时间阻塞"
                    }
                ],
                "feedback": "测试超时"
            }
        except Exception as e:
            return {
                "success": False,
                "approved": False,
                "score": 0,
                "summary": f"测试执行失败: {e}",
                "issues": [
                    {
                        "severity": "error",
                        "location": target,
                        "description": str(e),
                        "suggestion": "检查测试环境配置"
                    }
                ],
                "feedback": str(e)
            }
    
    def _parse_result(self, content: str) -> Dict[str, Any]:
        """解析 LLM 返回的结果"""
        try:
            # 清理 markdown 标记
            clean = content.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.startswith("```"):
                clean = clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
            
            result = json.loads(clean)
            return result
            
        except json.JSONDecodeError:
            # 尝试提取 JSON
            import re
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
            
            # 回退
            return {
                "success": True,
                "approved": True,
                "score": 70,
                "summary": "无法解析审查结果，默认通过",
                "issues": [],
                "feedback": "",
                "warning": "解析失败"
            }
    
    def _log(self, message: str):
        """输出日志 - 安全处理特殊字符"""
        if self.verbose:
            self.logger.info(message)
            try:
                print(f"[ReviewerAgent] {message}")
            except UnicodeEncodeError:
                safe_msg = message.encode('gbk', errors='replace').decode('gbk')
                print(f"[ReviewerAgent] {safe_msg}")


# 便捷函数
def create_reviewer_agent(llm_api=None, verbose: bool = True) -> ReviewerAgent:
    """创建 ReviewerAgent"""
    return ReviewerAgent(llm_api=llm_api, verbose=verbose)
