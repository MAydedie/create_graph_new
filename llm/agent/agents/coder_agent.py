#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CoderAgent - 编码 Agent - Phase 4

根据计划步骤执行代码修改操作。

职责：
- 执行计划中的代码修改步骤
- 读取、创建、修改、删除文件
- 返回执行结果和变更摘要
"""

import os
import sys
import json
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


logger = logging.getLogger("CoderAgent")


# Coder 专用 Prompt 模板
CODER_SYSTEM_PROMPT = """你是一个专业的编码 Agent，负责根据计划执行代码修改。

## 你的职责

1. 理解当前步骤要求
2. 分析相关代码知识
3. 执行代码修改操作
4. 返回执行结果

## 输出格式

你必须输出一个 JSON 格式的执行结果：

```json
{
  "success": true,
  "action": "执行的操作类型",
  "target": "目标文件路径",
  "summary": "执行摘要",
  "changes": {
    "files_created": ["新建的文件列表"],
    "files_modified": ["修改的文件列表"],
    "files_deleted": ["删除的文件列表"]
  },
  "code_content": "如果是创建或修改文件，这里是代码内容"
}
```

## 编码原则

1. **遵循现有风格**：代码风格与项目一致
2. **添加注释**：重要逻辑添加中文注释
3. **最小修改**：只修改必要的部分
4. **保持兼容**：不破坏现有功能
5. **保证可运行**：生成的代码必须在当前工程中可以被正常导入和执行（尤其是测试文件）

## 重要规则

1. 直接输出 JSON，不要包含其他内容
2. 如果无法执行，设置 success 为 false 并说明原因
3. code_content 中的代码要完整可用

## 针对“测试相关”步骤的额外规则

1. 当你执行的步骤描述中包含“测试、单元测试、pytest、test_xxx.py”等关键词时，说明这是在创建/修改测试文件或运行测试：
   - 在 **创建或修改测试文件之前**，你必须先根据上下文信息（用户目标、RAG 知识、文件结构）确认：
     - 要测试的模块/函数/类在工程中真实存在；
     - 导入语句是合理的，例如 `from utils import foo` 前提是存在 `utils.py` 且其中有 `foo`。
   - 如果你无法确信导入目标存在，优先返回：
     ```json
     {
       "success": false,
       "action": "create_file",
       "target": "…",
       "summary": "无法创建稳定的测试文件：相关函数/模块不存在或不确定",
       "changes": { "files_created": [], "files_modified": [], "files_deleted": [] }
     }
     ```
     由上游重新规划，而不是盲目生成一定会失败的测试。
2. **测试内容要渐进式**：
   - 第一次为某个模块生成测试时，只写少量核心的、容易通过的用例（例如：函数可调用、基础输入输出关系），避免一次性写大量复杂断言。
   - 对于复杂数值算法（如 DCT、图像处理），优先测试：
     - 形状是否保持一致；
     - 简单的逆变换关系；
     - 是否抛出异常等基础性质。
3. 如果你认为某些断言在当前实现下“可能失败但仍有价值”，可以：
   - 在测试注释中明确标注这是“增强型断言”，或者
   - 使用 pytest 的 xfail/skip 标记（如果上下文环境支持 pytest），避免整个测试套件立即失败。
"""


class CoderAgent:
    """
    编码 Agent - 执行代码修改操作
    
    工作流程：
    1. 接收步骤定义和上下文
    2. 分析需要的修改
    3. 生成代码或执行修改
    4. 返回执行结果
    
    Attributes:
        llm_api: LLM API 客户端（延迟加载）
        file_manager: 文件管理器（可选）
        verbose: 是否输出详细日志
    """
    
    def __init__(self, llm_api=None, file_manager=None, verbose: bool = True):
        """
        初始化 CoderAgent
        
        Args:
            llm_api: LLM API 客户端
            file_manager: 文件管理器
            verbose: 是否输出详细日志
        """
        self._llm_api = llm_api
        self.file_manager = file_manager
        self.verbose = verbose
        self.logger = logging.getLogger("CoderAgent")
    
    def _get_llm_api(self):
        """获取 LLM API（延迟加载）"""
        if self._llm_api is None:
            from llm.rag_core.llm_api import DeepSeekAPI
            self._llm_api = DeepSeekAPI()
        return self._llm_api
    
    def _get_workspace_root(self, context: Dict) -> Path:
        """获取工作区根目录（优先级：context > 环境变量 > PROJECT_ROOT）"""
        # 1. 尝试从 context 获取
        workspace = context.get("workspace_root", "")
        if workspace:
            return Path(workspace)
        
        # 2. 尝试从环境变量获取（server.py 设置的）
        env_workspace = os.environ.get("WORKSPACE_ROOT", "")
        if env_workspace:
            return Path(env_workspace)
        
        # 3. 回退到项目根目录
        return PROJECT_ROOT

    
    def execute_step(self, step: Dict[str, Any], context: Dict = None) -> Dict[str, Any]:
        """
        执行计划中的一个步骤
        
        Args:
            step: 步骤定义，包含 type、action、target、description
            context: 上下文信息，应包含 workspace_root
            
        Returns:
            执行结果字典
        """
        context = context or {}
        step_type = step.get("type", "code_change")
        action = step.get("action", "")
        target = step.get("target", "")
        description = step.get("description", "")
        
        self._log(f"执行步骤: {description}")
        self._log(f"  类型: {step_type}, 操作: {action}, 目标: {target}")
        
        try:
            # 根据操作类型执行
            if action == "read_file":
                return self._execute_read(target, context)
            elif action == "create_file":
                return self._execute_create(target, description, context)
            elif action == "modify_file":
                return self._execute_modify(target, description, context)
            elif action == "delete_file":
                return self._execute_delete(target, context)
            elif action == "create_directory":
                return self._execute_create_directory(target, context)
            elif action in ["run_tests", "verify"]:
                return self._execute_run_tests(target, context)
            else:
                # 通用处理：调用 LLM
                return self._execute_with_llm(step, context)
                
        except Exception as e:
            self.logger.error(f"执行失败: {e}")
            return {
                "success": False,
                "action": action,
                "target": target,
                "error": str(e)
            }
    
    def _execute_read(self, target: str, context: Dict) -> Dict[str, Any]:
        """执行读取文件操作"""
        if self.file_manager:
            result = self.file_manager.safe_read(target)
            if result.get("success"):
                return {
                    "success": True,
                    "action": "read_file",
                    "target": target,
                    "summary": f"成功读取 {target}",
                    "content": result.get("content", ""),
                    "changes": {}
                }
            else:
                return {
                    "success": False,
                    "action": "read_file",
                    "target": target,
                    "error": result.get("error", "读取失败")
                }
        else:
            # 直接读取
            try:
                # 检查是否包含通配符
                import glob
                if any(char in target for char in ['*', '?', '[']):
                    path = Path(target)
                    if not path.is_absolute():
                        workspace_root = self._get_workspace_root(context)
                        search_pattern = str(workspace_root / target)
                    else:
                        search_pattern = target
                    
                    files = glob.glob(search_pattern, recursive=True)
                    if not files:
                        return {
                            "success": False,
                            "action": "read_file",
                            "target": target,
                            "error": f"未找到匹配的文件: {target}"
                        }
                    
                    # 如果匹配到单个文件，按单文件处理
                    if len(files) == 1:
                        target = files[0]
                        # 转换回 Path 对象继续后续逻辑（注意 logical flow，这里直接递归可能更简单，或者修改 target 后往下走）
                        # 为简单起见，这里直接修改 target 并继续，或者直接在这里处理
                        path = Path(target)
                    else:
                        # 匹配到多个文件，返回列表摘要
                        content = f"Found {len(files)} files matching '{target}':\n"
                        # 限制列出的文件数，防止过多
                        content += "\n".join(files[:50])
                        if len(files) > 50:
                            content += f"\n... and {len(files) - 50} more."
                            
                        return {
                            "success": True,
                            "action": "read_file",
                            "target": target,
                            "summary": f"成功匹配 {len(files)} 个文件",
                            "content": content,
                            "changes": {}
                        }

                path = Path(target)
                if not path.is_absolute():
                    workspace_root = self._get_workspace_root(context)
                    path = workspace_root / target
                
                if path.exists():
                    if path.is_dir():
                        # 如果是目录，返回文件列表
                        items = [p.name for p in path.iterdir()]
                        content = f"Directory listing for {target}:\n" + "\n".join(items)
                        return {
                            "success": True,
                            "action": "read_file",
                            "target": target,
                            "summary": f"成功读取目录 {target}",
                            "content": content,
                            "changes": {}
                        }
                    
                    content = path.read_text(encoding="utf-8", errors="replace")
                    return {
                        "success": True,
                        "action": "read_file",
                        "target": target,
                        "summary": f"成功读取 {target} ({len(content)} 字符)",
                        "content": content[:5000],  # 截断过长内容
                        "changes": {}
                    }

                else:
                    return {
                        "success": False,
                        "action": "read_file",
                        "target": target,
                        "error": f"文件不存在: {target}"
                    }
            except Exception as e:
                return {
                    "success": False,
                    "action": "read_file",
                    "target": target,
                    "error": str(e)
                }
    
    def _execute_create(self, target: str, description: str, context: Dict) -> Dict[str, Any]:
        """执行创建文件操作"""
        # 调用 LLM 生成代码
        prompt = self._build_create_prompt(target, description, context)
        
        try:
            llm_api = self._get_llm_api()
            
            messages = [
                {"role": "system", "content": CODER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            
            response = llm_api.chat(
                messages=messages,
                temperature=0.2,
                max_tokens=8192,  # 增加到8192以防止测试文件被截断
                timeout=120
            )
            
            # 提取响应
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")
            else:
                content = response.get("content", "")
            
            # 解析结果
            result = self._parse_result(content)
            
            # V4: 检测代码截断
            if result.get("success") and result.get("code_content"):
                code = result["code_content"]
                if self._is_code_truncated(code):
                    self._log("检测到代码被截断，标记为失败", level="warning")
                    result["success"] = False
                    result["error"] = "生成的代码不完整（可能被截断），请尝试简化需求或分解为多个文件"
                    result["truncated"] = True
            
            # 如果成功，尝试写入文件
            if result.get("success") and result.get("code_content"):
                write_result = self._write_file(target, result["code_content"], context)
                if write_result["success"]:
                    # 额外自检：如果这是测试文件，至少保证语法正确
                    is_test_file = "test" in os.path.basename(target).lower()
                    if is_test_file:
                        try:
                            import subprocess
                            path = Path(target)
                            if not path.is_absolute():
                                workspace_root = self._get_workspace_root(context)
                                path = workspace_root / target
                            cmd = f"{sys.executable} -m py_compile \"{str(path)}\""
                            self._log(f"自检测试文件语法: {cmd}")
                            check_res = subprocess.run(
                                cmd,
                                shell=True,
                                cwd=str(path.parent),
                                capture_output=True,
                                text=True,
                                timeout=60,
                                encoding="utf-8",
                                errors="replace",
                            )
                            if check_res.returncode != 0:
                                # 语法错误，标记为失败，让上游重新规划/调整
                                err_snippet = (check_res.stdout or "") + "\n" + (check_res.stderr or "")
                                err_snippet = err_snippet[-800:] if len(err_snippet) > 800 else err_snippet
                                self._log(f"测试文件语法检查失败: {err_snippet}", level="warning")
                                result["success"] = False
                                result["error"] = f"测试文件语法检查失败: {err_snippet}"
                            else:
                                result["summary"] = f"成功创建 {target}"
                                result["changes"] = {"files_created": [target]}
                        except Exception as e:
                            # 自检异常不应导致崩溃，但要把信息返回给上游
                            self._log(f"测试文件语法自检异常: {e}", level="warning")
                            result["summary"] = f"成功创建 {target}（语法自检时出现异常）"
                            result["changes"] = {"files_created": [target]}
                    else:
                        result["summary"] = f"成功创建 {target}"
                        result["changes"] = {"files_created": [target]}
                else:
                    result["success"] = False
                    result["error"] = write_result.get("error", "写入失败")
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "action": "create_file",
                "target": target,
                "error": str(e)
            }
    
    def _execute_modify(self, target: str, description: str, context: Dict) -> Dict[str, Any]:
        """执行修改文件操作"""
        # 先读取原文件
        read_result = self._execute_read(target, context)
        if not read_result.get("success"):
            return {
                "success": False,
                "action": "modify_file",
                "target": target,
                "error": f"无法读取原文件: {read_result.get('error')}"
            }
        
        original_content = read_result.get("content", "")
        
        # 调用 LLM 生成修改
        prompt = self._build_modify_prompt(target, description, original_content, context)
        
        try:
            llm_api = self._get_llm_api()
            
            messages = [
                {"role": "system", "content": CODER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            
            response = llm_api.chat(
                messages=messages,
                temperature=0.2,
                max_tokens=4096,
                timeout=120
            )
            
            # 提取响应
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")
            else:
                content = response.get("content", "")
            
            # 解析结果
            result = self._parse_result(content)
            
            # 如果成功，尝试写入文件
            if result.get("success") and result.get("code_content"):
                write_result = self._write_file(target, result["code_content"], context)
                if write_result["success"]:
                    result["summary"] = f"成功修改 {target}"
                    result["changes"] = {"files_modified": [target]}
                else:
                    result["success"] = False
                    result["error"] = write_result.get("error", "写入失败")
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "action": "modify_file",
                "target": target,
                "error": str(e)
            }
    
    def _execute_delete(self, target: str, context: Dict) -> Dict[str, Any]:
        """执行删除文件操作"""
        try:
            path = Path(target)
            if not path.is_absolute():
                workspace_root = self._get_workspace_root(context)
                path = workspace_root / target
            
            if path.exists():
                path.unlink()
                return {
                    "success": True,
                    "action": "delete_file",
                    "target": target,
                    "summary": f"成功删除 {target}",
                    "changes": {"files_deleted": [target]}
                }
            else:
                return {
                    "success": False,
                    "action": "delete_file",
                    "target": target,
                    "error": f"文件不存在: {target}"
                }
        except Exception as e:
            return {
                "success": False,
                "action": "delete_file",
                "target": target,
                "error": str(e)
            }
    
    def _execute_create_directory(self, target: str, context: Dict) -> Dict[str, Any]:
        """执行创建目录操作"""
        try:
            path = Path(target)
            if not path.is_absolute():
                workspace_root = self._get_workspace_root(context)
                path = workspace_root / target
            
            if path.exists():
                if path.is_dir():
                    return {
                        "success": True,
                        "action": "create_directory",
                        "target": target,
                        "summary": f"目录已存在: {target}",
                        "changes": {}
                    }
                else:
                    return {
                        "success": False,
                        "action": "create_directory",
                        "target": target,
                        "error": f"路径已存在但不是目录: {target}"
                    }
            
            # 创建目录（包括父目录）
            path.mkdir(parents=True, exist_ok=True)
            
            # 创建 __init__.py 使其成为 Python 包
            init_file = path / "__init__.py"
            if not init_file.exists():
                init_file.write_text("# Auto-generated\n", encoding="utf-8")
            
            return {
                "success": True,
                "action": "create_directory",
                "target": target,
                "summary": f"成功创建目录: {target}",
                "changes": {"directories_created": [target]}
            }
        except Exception as e:
            return {
                "success": False,
                "action": "create_directory",
                "target": target,
                "error": str(e)
            }
    
    def _execute_run_tests(self, target: str, context: Dict) -> Dict[str, Any]:
        """执行运行测试操作 - V1: 真正运行 pytest"""
        import subprocess
        
        try:
            path = Path(target)
            if not path.is_absolute():
                workspace_root = self._get_workspace_root(context)
                path = workspace_root / target
            
            # 确定测试路径和工作目录
            if path.is_file():
                test_path = str(path)
                # 向上查找包含 pyproject.toml 或 setup.py 的目录
                cwd = self._find_project_root_for_tests(path.parent)
            elif path.is_dir():
                test_path = str(path)
                # 向上查找包含 pyproject.toml 或 setup.py 的目录
                cwd = self._find_project_root_for_tests(path)
            else:
                # 可能是 pattern，使用 workspace
                workspace_root = self._get_workspace_root(context)
                test_path = target
                cwd = str(workspace_root)
            
            self._log(f"运行测试: {test_path}")
            
            # 运行 pytest
            result = subprocess.run(
                ["python", "-m", "pytest", test_path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=120,  # 2 分钟超时
                encoding='utf-8',
                errors='replace'
            )
            
            # 解析结果
            output = result.stdout + result.stderr
            passed = "passed" in output.lower()
            
            # 提取测试统计
            import re
            stats_match = re.search(r'(\d+) passed', output)
            passed_count = int(stats_match.group(1)) if stats_match else 0
            
            failed_match = re.search(r'(\d+) failed', output)
            failed_count = int(failed_match.group(1)) if failed_match else 0
            
            # 截断过长的输出
            if len(output) > 3000:
                output = output[:3000] + "\n... (输出过长，已截断)"
            
            success = result.returncode == 0
            
            return {
                "success": success,
                "action": "run_tests",
                "target": target,
                "summary": f"测试完成: {passed_count} 通过, {failed_count} 失败",
                "test_output": output,
                "passed_count": passed_count,
                "failed_count": failed_count,
                "changes": {}
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "action": "run_tests",
                "target": target,
                "error": "测试运行超时 (120秒)"
            }
        except Exception as e:
            return {
                "success": False,
                "action": "run_tests",
                "target": target,
                "error": str(e)
            }
    
    def _find_project_root_for_tests(self, start_path: Path) -> str:
        """向上查找项目根目录（包含 pyproject.toml 或 setup.py 的目录）"""
        current = start_path
        while current != current.parent:
            if (current / "pyproject.toml").exists() or (current / "setup.py").exists():
                return str(current)
            current = current.parent
        # 如果没找到，返回起始路径
        return str(start_path)
    
    def _execute_with_llm(self, step: Dict, context: Dict) -> Dict[str, Any]:
        """通用 LLM 执行"""
        prompt = f"""请执行以下步骤：

步骤类型: {step.get('type', '')}
操作: {step.get('action', '')}
目标: {step.get('target', '')}
描述: {step.get('description', '')}

上下文:
{json.dumps(context.get('step', {}), ensure_ascii=False, indent=2) if context.get('step') else '无'}

请输出执行结果 JSON。"""
        
        try:
            llm_api = self._get_llm_api()
            
            messages = [
                {"role": "system", "content": CODER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            
            response = llm_api.chat(
                messages=messages,
                temperature=0.2,
                max_tokens=2048,
                timeout=120
            )
            
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")
            else:
                content = response.get("content", "")
            
            return self._parse_result(content)
            
        except Exception as e:
            return {
                "success": False,
                "action": step.get("action", "unknown"),
                "target": step.get("target", ""),
                "error": str(e)
            }
    
    def _build_create_prompt(self, target: str, description: str, context: Dict) -> str:
        """构建创建文件的 prompt - V3: 增强测试文件生成 + Mock 指导"""
        lines = [
            f"## 任务",
            f"创建新文件: {target}",
            f"",
            f"## 要求",
            f"{description}",
        ]
        
        # 添加 RAG 知识
        rag = context.get("rag_knowledge", {})
        if rag:
            summary = rag.get("context_summary", "")
            if summary:
                lines.append(f"\n## 相关代码知识\n{summary}")
        
        # V3 增强：如果是测试文件，尝试读取对应的源文件并添加 Mock 指导
        if "test_" in Path(target).name or "_test" in Path(target).name:
            source_file = self._infer_source_file(target, context)
            if source_file:
                source_content = self._safe_read_file(source_file)
                if source_content:
                    # 截断过长的源文件
                    if len(source_content) > 4000:
                        source_content = source_content[:4000] + "\n... (内容过长，已截断)"
                    lines.append(f"\n## 被测试的源文件内容 ({source_file})\n```python\n{source_content}\n```")
            
            # V3 新增：简化的单元测试编写指南（避免prompt过长导致截断）
            lines.append("\n## 单元测试编写规范")
            lines.append("""
### Mock 使用要点
1. 使用 `unittest.mock.patch` 模拟外部依赖（随机函数、时间、网络等）
2. 每个测试必须快速、确定性、独立
3. 测试行为而非实现细节

### 示例
```python
from unittest.mock import patch

class TestExample:
    @patch('module.random.uniform', return_value=0.5)
    def test_with_mock(self, mock_random):
        result = function_under_test()
        assert result == expected_value
        mock_random.assert_called_once()
```

### 注意事项
- 避免依赖真实随机数或当前时间
- 使用 mock 确保测试结果可预测
- 为所有主要函数编写测试用例
""")
        
        lines.append("\n请生成完整的代码文件内容，确保所有测试都使用 Mock 并符合上述规范。")
        
        return "\n".join(lines)
    
    def _infer_source_file(self, test_file: str, context: Dict) -> Optional[str]:
        """从测试文件路径推断对应的源文件路径"""
        test_path = Path(test_file)
        test_name = test_path.name
        
        # 常见模式: test_xxx.py -> xxx.py
        source_name = None
        if test_name.startswith("test_"):
            source_name = test_name[5:]  # 移除 test_ 前缀
        elif test_name.endswith("_test.py"):
            source_name = test_name[:-8] + ".py"  # 移除 _test 后缀
        
        if not source_name:
            return None
        
        # 尝试在多个位置查找源文件
        workspace_root = self._get_workspace_root(context)
        possible_locations = [
            test_path.parent.parent / source_name,  # tests/../xxx.py
            test_path.parent.parent / "src" / source_name,  # tests/../src/xxx.py
            test_path.parent.parent / test_path.parent.parent.name / source_name,  # tests/../package_name/xxx.py
            workspace_root / source_name,  # workspace/xxx.py
        ]
        
        # 从上下文中获取文件结构信息
        file_structure = context.get("file_structure", {})
        if isinstance(file_structure, dict):
            source_files = file_structure.get("source_files", [])
            paths = file_structure.get("paths", [])
            
            # 在扫描的源文件中查找匹配项
            for src in source_files:
                if source_name in src:
                    for base_path in paths:
                        full_path = Path(base_path) / src
                        if full_path.exists():
                            return str(full_path)
        
        # 尝试常见位置
        for loc in possible_locations:
            if loc.exists():
                return str(loc)
        
        return None
    
    def _safe_read_file(self, file_path: str) -> Optional[str]:
        """安全读取文件内容"""
        try:
            path = Path(file_path)
            if path.exists() and path.is_file():
                return path.read_text(encoding="utf-8")
        except Exception:
            pass
        return None

    
    def _build_modify_prompt(self, target: str, description: str, 
                              original: str, context: Dict) -> str:
        """构建修改文件的 prompt"""
        # 截断过长的原始内容
        if len(original) > 3000:
            original = original[:3000] + "\n... (内容过长，已截断)"
        
        lines = [
            f"## 任务",
            f"修改文件: {target}",
            f"",
            f"## 修改要求",
            f"{description}",
            f"",
            f"## 原始内容",
            f"```",
            original,
            f"```",
        ]
        
        # 添加 RAG 知识
        rag = context.get("rag_knowledge", {})
        if rag:
            summary = rag.get("context_summary", "")
            if summary:
                lines.append(f"\n## 相关代码知识\n{summary}")
        
        lines.append("\n请输出修改后的完整代码。")
        
        return "\n".join(lines)
    
    def _write_file(self, target: str, content: str, context: Dict = None) -> Dict[str, Any]:
        """写入文件"""
        try:
            path = Path(target)
            if not path.is_absolute():
                workspace_root = self._get_workspace_root(context or {})
                path = workspace_root / target
            
            # 确保目录存在
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入内容
            path.write_text(content, encoding="utf-8")
            
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
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
            
            # 尝试提取代码块
            code_match = re.search(r'```(?:python)?\n([\s\S]*?)```', content)
            if code_match:
                return {
                    "success": True,
                    "action": "code_generation",
                    "summary": "代码生成成功",
                    "code_content": code_match.group(1),
                    "changes": {}
                }
            
            # 回退
            return {
                "success": False,
                "error": "无法解析 LLM 返回结果",
                "raw_content": content[:500]
            }
    
    def _is_code_truncated(self, code: str) -> bool:
        """检测代码是否被截断（V4 新增）"""
        if not code or len(code) < 50:
            return True
        
        # 检查常见的截断模式
        lines = code.strip().split('\n')
        last_line = lines[-1].strip() if lines else ""
        
        # 1. 检查是否以不完整的语句结尾
        incomplete_patterns = [
            'def ',      # 函数定义未完成
            'class ',    # 类定义未完成
            'if ',       # if语句未完成
            'for ',      # for循环未完成
            'while ',    # while循环未完成
            '"""',       # 文档字符串未闭合
            "'''",       # 文档字符串未闭合
        ]
        
        for pattern in incomplete_patterns:
            if last_line.startswith(pattern) or last_line.endswith(pattern):
                return True
        
        # 2. 检查括号/引号是否匹配
        open_count = code.count('(') - code.count(')')
        bracket_count = code.count('[') - code.count(']')
        brace_count = code.count('{') - code.count('}')
        
        if abs(open_count) > 3 or abs(bracket_count) > 3 or abs(brace_count) > 3:
            return True
        
        # 3. 检查是否有明显的截断标记
        if "..." in last_line or "# ..." in code[-200:]:
            return True
        
        return False
    
    def _log(self, message: str, level: str = "info"):
        """输出日志 - 安全处理特殊字符"""
        if self.verbose:
            if level == "warning":
                self.logger.warning(message)
            elif level == "error":
                self.logger.error(message)
            else:
                self.logger.info(message)
            # 安全打印：避免 Windows GBK 编码问题
            try:
                print(f"[CoderAgent] {message}")
            except UnicodeEncodeError:
                # 替换非 ASCII 字符
                safe_msg = message.encode('gbk', errors='replace').decode('gbk')
                print(f"[CoderAgent] {safe_msg}")


# 便捷函数
def create_coder_agent(llm_api=None, verbose: bool = True) -> CoderAgent:
    """创建 CoderAgent"""
    return CoderAgent(llm_api=llm_api, verbose=verbose)
