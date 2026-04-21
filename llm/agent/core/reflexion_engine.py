#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ReflexionEngine - 反思引擎 - Phase 5.2

使用 LLM 分析错误原因并生成改进建议。

核心功能：
1. 分析错误根本原因
2. 评估之前的尝试
3. 生成改进建议
4. 推荐解决方案
"""

import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


logger = logging.getLogger("ReflexionEngine")


@dataclass
class ReflexionResult:
    """Reflexion 分析结果"""
    root_cause: str
    why_failed: str
    improvements: List[str]
    recommended_solution: str
    confidence: float
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "root_cause": self.root_cause,
            "why_failed": self.why_failed,
            "improvements": self.improvements,
            "recommended_solution": self.recommended_solution,
            "confidence": self.confidence
        }


class ReflexionEngine:
    """
    Reflexion 引擎
    
    使用 LLM 深度分析错误，生成改进建议。
    
    核心流程：
    1. 收集错误信息和上下文
    2. 分析之前的尝试
    3. 使用 LLM 进行 Reflexion
    4. 生成改进建议
    
    使用示例：
    ```python
    engine = ReflexionEngine()
    
    result = engine.analyze_error(
        error=FileNotFoundError("file.txt not found"),
        context={"step": "read_file", "file": "file.txt"},
        previous_attempts=[
            {"attempt": 1, "action": "直接读取", "result": "失败"}
        ]
    )
    
    print(result.root_cause)  # "文件路径错误"
    print(result.recommended_solution)  # "使用绝对路径"
    ```
    """
    
    # Reflexion Prompt 模板
    REFLEXION_PROMPT = """你是一个错误分析专家。请深度分析以下错误并提供改进建议。

## 错误信息

**错误类型**: {error_type}
**错误消息**: {error_message}

## 上下文

{context}

## 之前的尝试

{previous_attempts}

## 请回答以下问题

1. **根本原因**: 这个错误的根本原因是什么？
2. **失败分析**: 为什么之前的尝试失败了？
3. **改进建议**: 应该如何改进？（列出 3-5 条具体建议）
4. **推荐方案**: 你推荐的解决方案是什么？
5. **置信度**: 你对这个分析的置信度（0-1）？

## 输出格式

请以 JSON 格式输出，格式如下：

```json
{{
  "root_cause": "根本原因描述",
  "why_failed": "失败原因分析",
  "improvements": [
    "改进建议1",
    "改进建议2",
    "改进建议3"
  ],
  "recommended_solution": "推荐的解决方案",
  "confidence": 0.9
}}
```

只输出 JSON，不要其他内容。
"""
    
    def __init__(self, llm_api=None, verbose: bool = True):
        """
        初始化 Reflexion 引擎
        
        Args:
            llm_api: LLM API 客户端（如果不提供则延迟加载）
            verbose: 是否输出详细日志
        """
        self._llm_api = llm_api
        self.verbose = verbose
        self.logger = logging.getLogger("ReflexionEngine")
    
    def _get_llm_api(self):
        """获取 LLM API（延迟加载）"""
        if self._llm_api is None:
            from llm.rag_core.llm_api import DeepSeekAPI
            self._llm_api = DeepSeekAPI()
        return self._llm_api
    
    def analyze_error(
        self,
        error: Exception,
        context: Dict[str, Any],
        previous_attempts: List[Dict[str, Any]]
    ) -> ReflexionResult:
        """
        分析错误
        
        Args:
            error: 异常对象
            context: 错误上下文
            previous_attempts: 之前的尝试列表
        
        Returns:
            Reflexion 分析结果
        """
        if self.verbose:
            self.logger.info(f"开始 Reflexion 分析: {type(error).__name__}")
        
        # 构建 prompt
        prompt = self._build_prompt(error, context, previous_attempts)
        
        # 调用 LLM
        try:
            llm_api = self._get_llm_api()
            
            messages = [
                {"role": "user", "content": prompt}
            ]
            
            response = llm_api.chat(
                messages=messages,
                temperature=0.1,  # 低温度，更确定性
                max_tokens=1024
            )
            
            # 解析响应
            result = self._parse_response(response)
            
            if self.verbose:
                self.logger.info(f"Reflexion 完成，置信度: {result.confidence}")
            
            return result
        
        except Exception as e:
            self.logger.error(f"Reflexion 分析失败: {e}")
            
            # 返回默认结果
            return self._default_result(error)
    
    def _build_prompt(
        self,
        error: Exception,
        context: Dict[str, Any],
        previous_attempts: List[Dict[str, Any]]
    ) -> str:
        """构建 Reflexion prompt"""
        error_type = type(error).__name__
        error_message = str(error)
        
        # 格式化上下文
        context_str = json.dumps(context, indent=2, ensure_ascii=False)
        
        # 格式化尝试历史
        if previous_attempts:
            attempts_str = "\n".join([
                f"尝试 {i+1}:\n{json.dumps(attempt, indent=2, ensure_ascii=False)}"
                for i, attempt in enumerate(previous_attempts)
            ])
        else:
            attempts_str = "（无之前的尝试）"
        
        # 填充模板
        prompt = self.REFLEXION_PROMPT.format(
            error_type=error_type,
            error_message=error_message,
            context=context_str,
            previous_attempts=attempts_str
        )
        
        return prompt
    
    def _parse_response(self, response: str) -> ReflexionResult:
        """解析 LLM 响应"""
        try:
            # 尝试提取 JSON
            import re
            
            # 查找 JSON 块
            json_match = re.search(r'\{[\s\S]*\}', response)
            
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
            else:
                # 直接解析
                data = json.loads(response)
            
            # 创建结果
            return ReflexionResult(
                root_cause=data.get("root_cause", "未知"),
                why_failed=data.get("why_failed", "未知"),
                improvements=data.get("improvements", []),
                recommended_solution=data.get("recommended_solution", "未知"),
                confidence=float(data.get("confidence", 0.5))
            )
        
        except Exception as e:
            self.logger.error(f"解析 Reflexion 响应失败: {e}")
            self.logger.debug(f"响应内容: {response}")
            
            # 返回默认结果
            return ReflexionResult(
                root_cause="解析失败",
                why_failed="无法解析 LLM 响应",
                improvements=["检查 LLM 输出格式"],
                recommended_solution="手动分析错误",
                confidence=0.1
            )
    
    def _default_result(self, error: Exception) -> ReflexionResult:
        """生成默认结果（当 LLM 调用失败时）"""
        error_type = type(error).__name__
        
        # 基于错误类型的简单规则
        if error_type == "FileNotFoundError":
            return ReflexionResult(
                root_cause="文件不存在",
                why_failed="文件路径错误或文件未创建",
                improvements=[
                    "检查文件路径是否正确",
                    "使用绝对路径",
                    "确认文件是否存在"
                ],
                recommended_solution="使用 Path.resolve() 转换为绝对路径，并检查文件存在性",
                confidence=0.7
            )
        
        elif error_type == "SyntaxError":
            return ReflexionResult(
                root_cause="代码语法错误",
                why_failed="生成的代码不符合 Python 语法",
                improvements=[
                    "检查括号是否匹配",
                    "检查缩进是否正确",
                    "使用 ast.parse 验证语法"
                ],
                recommended_solution="重新生成代码，确保语法正确",
                confidence=0.8
            )
        
        elif error_type == "ImportError":
            return ReflexionResult(
                root_cause="模块导入失败",
                why_failed="模块不存在或未安装",
                improvements=[
                    "检查模块是否已安装",
                    "检查模块名称是否正确",
                    "使用 pip install 安装缺失的模块"
                ],
                recommended_solution="安装缺失的依赖或修正导入路径",
                confidence=0.8
            )
        
        else:
            return ReflexionResult(
                root_cause=f"{error_type} 错误",
                why_failed="未知原因",
                improvements=[
                    "查看错误堆栈",
                    "检查输入参数",
                    "查阅文档"
                ],
                recommended_solution="根据错误信息进行调试",
                confidence=0.5
            )
    
    def _log(self, message: str):
        """输出日志"""
        if self.verbose:
            self.logger.info(message)
            try:
                print(f"[ReflexionEngine] {message}")
            except UnicodeEncodeError:
                safe_msg = message.encode('gbk', errors='replace').decode('gbk')
                print(f"[ReflexionEngine] {safe_msg}")


# 便捷函数
def analyze_error(
    error: Exception,
    context: Dict[str, Any],
    previous_attempts: List[Dict[str, Any]] = None,
    llm_api=None
) -> ReflexionResult:
    """
    分析错误（便捷函数）
    
    Args:
        error: 异常对象
        context: 错误上下文
        previous_attempts: 之前的尝试列表
        llm_api: LLM API 客户端
    
    Returns:
        Reflexion 分析结果
    """
    engine = ReflexionEngine(llm_api=llm_api)
    return engine.analyze_error(
        error=error,
        context=context,
        previous_attempts=previous_attempts or []
    )
