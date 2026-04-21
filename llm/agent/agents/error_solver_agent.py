#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
错误解决代理 (Error Solver Agent) - Phase 4 V3

专门负责分析错误日志、诊断问题并生成解决方案。

核心功能：
1. analyze_error: 分析错误日志，识别根因
2. generate_solution: 基于错误分析生成解决方案
3. create_micro_plan: 生成针对错误点的小计划
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

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

from llm.rag_core.llm_api import DeepSeekAPI


logger = logging.getLogger("ErrorSolverAgent")


class ErrorSolverAgent:
    """
    错误解决代理
    
    当执行步骤失败时，由 Orchestrator 调用此 Agent 来：
    1. 分析错误日志，找出根本原因
    2. 生成具体的解决方案
    3. 创建针对该错误点的小计划（micro-plan）
    """
    
    def __init__(self, llm_api=None, verbose: bool = True):
        """
        初始化错误解决代理
        
        Args:
            llm_api: 共享的 LLM API 实例
            verbose: 是否输出详细日志
        """
        self.verbose = verbose
        self.logger = logging.getLogger("ErrorSolverAgent")
        
        # 使用传入的 API 或创建新实例
        if llm_api:
            self.api = llm_api
        else:
            self.api = DeepSeekAPI()
    
    
    def analyze_error(
        self, 
        error_log: str, 
        step_info: Dict[str, Any] = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        分析错误日志，识别根因
        
        Args:
            error_log: 错误日志文本
            step_info: 失败步骤的信息
            context: 上下文信息
            
        Returns:
            错误分析结果字典，包含：
            - root_cause: 根本原因
            - error_type: 错误类型
            - affected_components: 受影响的组件
            - severity: 严重程度 (low/medium/high/critical)
        """
        self._log("分析错误日志...")
        
        step_desc = ""
        if step_info:
            step_desc = f"""
失败的步骤信息：
- 步骤ID: {step_info.get('step_id', 'unknown')}
- 步骤类型: {step_info.get('type', 'unknown')}
- 步骤描述: {step_info.get('description', 'unknown')}
- 目标: {step_info.get('target', 'unknown')}
"""
        
        prompt = f"""你是一个专业的错误诊断专家。请分析以下错误日志，找出根本原因。

{step_desc}

错误日志:
```
{error_log[:3000]}
```

请用JSON格式返回分析结果，包含以下字段：
{{
    "root_cause": "具体描述根本原因",
    "error_type": "错误类型（如：dependency_missing, file_not_found, permission_denied, timeout, syntax_error, runtime_error, configuration_error 等）",
    "affected_components": ["受影响的组件列表"],
    "severity": "严重程度：low/medium/high/critical",
    "quick_diagnosis": "一句话概括问题"
}}

只返回JSON，不要有其他内容。"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.api.chat(messages, temperature=0.2, max_tokens=800)
            
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0]["message"]["content"].strip()
                # 尝试解析JSON
                import json
                # 移除可能的markdown代码块标记
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()
                
                result = json.loads(content)
                
                # V4: 检测截断错误模式
                if self._is_truncation_error(error_log, result):
                    result["error_type"] = "code_truncation"
                    result["severity"] = "critical"
                    result["quick_diagnosis"] = "代码生成被截断，文件不完整"
                
                self._log(f"错误分析完成: {result.get('quick_diagnosis', '')}")
                return result
        except Exception as e:
            self._log(f"错误分析失败: {e}", level="warning")
        
        # 返回默认分析
        return {
            "root_cause": f"执行失败: {error_log[:200]}",
            "error_type": "unknown",
            "affected_components": [],
            "severity": "medium",
            "quick_diagnosis": "执行过程中发生未知错误"
        }
    
    def generate_solution(
        self, 
        error_analysis: Dict[str, Any],
        step_info: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
        error_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        基于错误分析生成解决方案
        
        Args:
            error_analysis: 错误分析结果
            step_info: 失败步骤的信息
            context: 上下文信息
            error_history: 历史错误记录列表（V4 新增）
            
        Returns:
            解决方案字典，包含：
            - solution: 解决方案描述
            - actions: 具体行动步骤列表
            - alternative: 备选方案（如果主方案不可行）
            - confidence: 解决方案置信度 (0-1)
            - give_up: 是否放弃修复（V4 新增）
            - give_up_reason: 放弃原因（V4 新增）
        """
        self._log("生成解决方案...")
        
        root_cause = error_analysis.get("root_cause", "未知错误")
        error_type = error_analysis.get("error_type", "unknown")
        error_history = error_history or []
        
        # V4: 构建错误历史描述
        history_desc = ""
        if error_history:
            history_desc = "\n\n## 已尝试过的修复（均失败）:\n"
            for i, h in enumerate(error_history[-5:], 1):  # 只取最近5次
                history_desc += f"- 尝试 {i}: {h.get('fix_summary', h.get('error', '未知'))[:100]}\n"
            history_desc += f"\n已累计尝试 {len(error_history)} 次修复。"
        
        prompt = f"""你是一个专业的问题解决专家。请基于以下错误分析，生成具体的解决方案。

## 错误分析：
- 根本原因: {root_cause}
- 错误类型: {error_type}
- 严重程度: {error_analysis.get('severity', 'medium')}

## 原始步骤信息：
{step_info if step_info else '无'}
{history_desc}

## 重要判断：
如果你认为这个错误**无法解决**（例如：缺少外部依赖、需要人工干预、已经尝试多种方案均失败），
请设置 "give_up": true，并在 "give_up_reason" 中说明原因。

请用JSON格式返回解决方案：
{{
    "solution": "解决方案的核心思路",
    "actions": [
        "具体行动步骤1",
        "具体行动步骤2"
    ],
    "alternative": "备选方案（如果主方案不可行）",
    "confidence": 0.8,
    "give_up": false,
    "give_up_reason": "",
    "skip_step": false,
    "retry_with_modification": "如果需要修改原步骤，描述修改内容"
}}

注意：
1. actions 应该是具体、可执行的步骤
2. 如果问题无法解决，设置 give_up 为 true
3. confidence 是置信度，0-1之间的浮点数
4. 如果已经尝试多次相同类型的修复，请果断放弃 (give_up: true)

只返回JSON，不要有其他内容。"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.api.chat(messages, temperature=0.3, max_tokens=1000)
            
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0]["message"]["content"].strip()
                import json
                # 移除markdown代码块
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()
                
                result = json.loads(content)
                self._log(f"解决方案生成完成: {result.get('solution', '')[:50]}...")
                
                # V4: 截断错误立即放弃检查
                if error_type == "code_truncation" or "截断" in root_cause or "truncat" in root_cause.lower():
                    truncation_count = sum(1 for h in error_history if "截断" in h.get("error", "") or "truncat" in h.get("error", "").lower())
                    if truncation_count >= 1:  # 只要出现过1次截断就放弃
                        self._log("检测到重复的代码截断错误，立即放弃", level="warning")
                        result["give_up"] = True
                        result["give_up_reason"] = f"代码生成多次被截断（{truncation_count + 1}次），建议：1) 简化测试需求 2) 分解为多个小文件 3) 减少被测函数数量"
                        return result
                
                # V4: 强制放弃检查 - 如果已尝试 5 次以上且置信度低
                if len(error_history) >= 5 and result.get("confidence", 1.0) < 0.4:
                    self._log("多次尝试失败且置信度低，强制放弃", level="warning")
                    result["give_up"] = True
                    result["give_up_reason"] = f"已尝试 {len(error_history)} 次修复均失败，置信度过低 ({result.get('confidence', 0):.2f})，建议跳过"
                
                return result
        except Exception as e:
            self._log(f"生成解决方案失败: {e}", level="warning")
        
        # V4: 默认返回增加 give_up 字段
        return {
            "solution": "自动重试执行该步骤",
            "actions": ["重新执行失败的步骤"],
            "alternative": "跳过该步骤，继续后续执行",
            "confidence": 0.3,
            "give_up": False,
            "give_up_reason": "",
            "skip_step": False,
            "retry_with_modification": None
        }
    
    def create_micro_plan(
        self,
        error_analysis: Dict[str, Any],
        solution: Dict[str, Any],
        original_step: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        创建针对错误点的小计划（micro-plan）
        
        这个小计划只负责修复当前错误，不影响整体大计划。
        
        Args:
            error_analysis: 错误分析结果
            solution: 解决方案
            original_step: 原始失败的步骤
            
        Returns:
            小计划字典，格式与 PlannerAgent 生成的计划兼容
        """
        self._log("创建错误修复小计划...")
        
        actions = solution.get("actions", [])
        
        # 如果解决方案建议跳过步骤
        if solution.get("skip_step", False):
            return {
                "plan_id": "micro_plan_skip",
                "type": "error_recovery",
                "goal": f"跳过失败步骤: {error_analysis.get('quick_diagnosis', '')}",
                "steps": [],
                "skip_original": True,
                "reason": solution.get("alternative", "无法修复，跳过该步骤")
            }
        
        # 构建小计划步骤
        micro_steps = []
        for i, action in enumerate(actions[:3]):  # 最多3个步骤
            micro_steps.append({
                "step_id": i,
                "type": "error_fix",
                "action": "fix",
                "description": action,
                "target": original_step.get("target", ".") if original_step else ".",
                "is_micro_plan": True
            })
        
        # 移除自动重试原步骤逻辑，由 Orchestrator 负责重试
        # 这避免了 Micro-Plan 因为原测试脚本依然失败而被判定为修复失败
        if False: # Deprecated logic
            if original_step and not solution.get("skip_step", False):
                modification = solution.get("retry_with_modification")
                retry_step = original_step.copy()
                retry_step["step_id"] = len(micro_steps)
                retry_step["is_retry"] = True
                if modification:
                    retry_step["modification"] = modification
                micro_steps.append(retry_step)
        
        micro_plan = {
            "plan_id": f"micro_plan_{error_analysis.get('error_type', 'fix')}",
            "type": "error_recovery",
            "goal": f"修复: {error_analysis.get('quick_diagnosis', '执行错误')}",
            "original_error": error_analysis,
            "solution": solution.get("solution", ""),
            "steps": micro_steps,
            "confidence": solution.get("confidence", 0.5)
        }
        
        self._log(f"小计划创建完成: {len(micro_steps)} 步")
        return micro_plan
    
    def solve_error(
        self,
        error_log: str,
        step_info: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
        error_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        一站式错误解决：分析 + 方案 + 小计划
        
        这是供 Orchestrator 调用的主要方法。
        
        Args:
            error_log: 错误日志
            step_info: 失败步骤信息
            context: 上下文
            error_history: 历史错误记录（V4 新增）
            
        Returns:
            包含完整解决方案的字典，V4 新增 give_up 字段
        """
        error_history = error_history or []
        
        # 1. 分析错误
        analysis = self.analyze_error(error_log, step_info, context)
        
        # 2. 生成解决方案（传入错误历史）
        solution = self.generate_solution(analysis, step_info, context, error_history)
        
        # 3. 检查是否放弃
        if solution.get("give_up", False):
            self._log(f"决定放弃修复: {solution.get('give_up_reason', '未知原因')}", level="warning")
            return {
                "analysis": analysis,
                "solution": solution,
                "micro_plan": None,
                "give_up": True,
                "give_up_reason": solution.get("give_up_reason", "模型判定无法解决"),
                "success": False
            }
        
        # 4. 创建小计划
        micro_plan = self.create_micro_plan(analysis, solution, step_info)
        
        return {
            "analysis": analysis,
            "solution": solution,
            "micro_plan": micro_plan,
            "give_up": False,
            "give_up_reason": "",
            "success": True
        }
    
    def _log(self, message: str, level: str = "info"):
        """输出日志"""
        if self.verbose:
            if level == "info":
                self.logger.info(message)
            elif level == "warning":
                self.logger.warning(message)
            elif level == "error":
                self.logger.error(message)
            try:
                print(f"[ErrorSolverAgent] {message}")
            except UnicodeEncodeError:
                safe_msg = message.encode('gbk', errors='replace').decode('gbk')
                print(f"[ErrorSolverAgent] {safe_msg}")
    
    def _is_truncation_error(self, error_log: str, analysis: Dict) -> bool:
        """检测是否为代码截断错误（V4 新增）"""
        truncation_keywords = [
            "被截断",
            "truncat",
            "不完整",
            "incomplete",
            "syntax error",  # 通常截断会导致语法错误
            "unexpected EOF",
            "SyntaxError",
        ]
        
        error_lower = error_log.lower()
        for keyword in truncation_keywords:
            if keyword.lower() in error_lower:
                # 进一步检查是否真的是截断（而非其他语法错误）
                if "截断" in error_log or "truncat" in error_lower or "incomplete" in error_lower:
                    return True
                # 如果是语法错误，检查是否在文件末尾
                if "syntax" in error_lower and ("eof" in error_lower or "end of file" in error_lower):
                    return True
        
        return False


# 便捷函数
def create_error_solver(llm_api=None, verbose: bool = True) -> ErrorSolverAgent:
    """创建错误解决代理"""
    return ErrorSolverAgent(llm_api=llm_api, verbose=verbose)
