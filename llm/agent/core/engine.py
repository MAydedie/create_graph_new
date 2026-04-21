#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ReAct 引擎 (ReAct Engine)

实现 ReAct (Reasoning and Acting) 循环：
1. 思考 (Thinking) - 分析问题
2. 行动 (Action) - 调用工具
3. 观察 (Observation) - 查看结果
4. 重复或回答

核心类：
- AgentConfig: Agent 配置
- ReActEngine: ReAct 循环引擎
"""

import os
import sys
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
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


logger = logging.getLogger("ReActEngine")


@dataclass
class AgentConfig:
    """Agent 配置"""
    model_name: str = "deepseek-chat"
    max_steps: int = 10              # 最大循环步数
    max_tool_calls: int = 5          # 最大工具调用次数
    temperature: float = 0.1         # LLM 温度
    timeout: int = 120               # LLM 调用超时（秒）
    max_tokens: int = 4096           # 最大生成 token 数
    verbose: bool = True             # 是否输出详细日志


@dataclass
class StepRecord:
    """单步执行记录"""
    step_num: int
    thinking: str = ""
    action: Optional[Dict[str, Any]] = None
    observation: str = ""
    final_answer: str = ""
    raw_response: str = ""


@dataclass
class RunResult:
    """运行结果"""
    success: bool
    answer: str
    steps: List[StepRecord] = field(default_factory=list)
    total_steps: int = 0
    tool_calls: int = 0
    error: str = ""


class ReActEngine:
    """
    ReAct 循环引擎
    
    实现 Reasoning and Acting 循环，让 Agent 能够多轮调用工具来解决问题。
    """
    
    # 正则表达式：提取 XML 标签内容
    THINKING_PATTERN = re.compile(r'<thinking>(.*?)</thinking>', re.DOTALL)
    PLAN_PATTERN = re.compile(r'<plan>(.*?)</plan>', re.DOTALL)
    ACTION_PATTERN = re.compile(r'<action>(.*?)</action>', re.DOTALL)
    FINAL_ANSWER_PATTERN = re.compile(r'<final_answer>(.*?)</final_answer>', re.DOTALL)
    
    def __init__(
        self, 
        config: AgentConfig = None, 
        tool_registry = None,
        conversation_memory = None
    ):
        """
        初始化 ReAct 引擎
        
        Args:
            config: Agent 配置
            tool_registry: 工具注册表
            conversation_memory: 会话记忆（Phase 3.5 新增）
        """
        self.config = config or AgentConfig()
        self.tool_registry = tool_registry
        self.conversation_memory = conversation_memory  # 会话记忆
        self.logger = logging.getLogger("ReActEngine")
        
        # 延迟加载 LLM API
        self._llm_api = None
        
        # 导入 prompt 模块
        from .prompt import build_system_prompt, build_few_shot_messages, format_observation
        self._build_system_prompt = build_system_prompt
        self._build_few_shot_messages = build_few_shot_messages
        self._format_observation = format_observation
    
    def _get_llm_api(self):
        """获取 LLM API（延迟加载）"""
        if self._llm_api is None:
            # 设置 HuggingFace 镜像
            if not os.environ.get("HF_ENDPOINT"):
                os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
            
            from llm.rag_core.llm_api import DeepSeekAPI
            self._llm_api = DeepSeekAPI()
        return self._llm_api
    
    def _get_tools_info(self) -> List[Dict[str, Any]]:
        """获取所有工具的描述信息"""
        if not self.tool_registry:
            return []
        
        tools_info = []
        for tool in self.tool_registry.get_all_tools():
            tools_info.append(tool.to_prompt_dict())
        return tools_info
    
    def _build_initial_messages(self, user_input: str) -> List[Dict[str, str]]:
        """
        构建初始对话消息
        
        Phase 3.5 增强：支持语义化上下文检索
        
        Args:
            user_input: 用户输入
            
        Returns:
            消息列表
        """
        tools_info = self._get_tools_info()
        system_prompt = self._build_system_prompt(
            tools_info,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Phase 3.5: 添加会话记忆上下文（按需加载）
        if self.conversation_memory:
            relevant_context = self.conversation_memory.get_relevant_context(
                query=user_input,
                max_units=3,
                include_current=True
            )
            if relevant_context:
                messages.append({
                    "role": "system",
                    "content": f"以下是与当前问题相关的对话上下文：\n\n{relevant_context}"
                })
                if self.config.verbose:
                    self.logger.info(f"已加载会话上下文 ({len(relevant_context)} 字符)")
        
        # 添加 few-shot 示例
        few_shot = self._build_few_shot_messages()
        messages.extend(few_shot)
        
        # 添加用户输入
        messages.append({"role": "user", "content": user_input})
        
        return messages
    
    def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """
        调用 LLM
        
        Args:
            messages: 对话消息列表
            
        Returns:
            LLM 响应文本
        """
        llm_api = self._get_llm_api()
        
        try:
            response = llm_api.chat(
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout
            )
            
            # 从响应中提取内容
            if "choices" in response and len(response["choices"]) > 0:
                return response["choices"][0].get("message", {}).get("content", "")
            return response.get("content", "")
        except Exception as e:
            self.logger.error(f"LLM 调用失败: {e}")
            raise
    
    def _parse_response(self, response: str) -> Tuple[str, Optional[Dict], str]:
        """
        解析 LLM 响应
        
        Args:
            response: LLM 响应文本
            
        Returns:
            (thinking, action_dict, final_answer) 元组
        """
        thinking = ""
        action = None
        final_answer = ""
        
        # 提取 thinking
        thinking_match = self.THINKING_PATTERN.search(response)
        if thinking_match:
            thinking = thinking_match.group(1).strip()
        
        # 提取 action
        action_match = self.ACTION_PATTERN.search(response)
        if action_match:
            action_str = action_match.group(1).strip()
            try:
                action = json.loads(action_str)
            except json.JSONDecodeError as e:
                self.logger.warning(f"Action JSON 解析失败: {e}")
                # 尝试修复常见问题
                try:
                    # 处理单引号
                    fixed = action_str.replace("'", '"')
                    action = json.loads(fixed)
                except:
                    pass
        
        # 提取 final_answer
        final_match = self.FINAL_ANSWER_PATTERN.search(response)
        if final_match:
            final_answer = final_match.group(1).strip()
        
        return thinking, action, final_answer
    
    def _execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具调用
        
        Args:
            action: 工具调用信息 {"tool": "...", "args": {...}}
            
        Returns:
            执行结果
        """
        if not self.tool_registry:
            return {"success": False, "error": "未配置工具注册表"}
        
        tool_name = action.get("tool")
        args = action.get("args", {})
        
        if not tool_name:
            return {"success": False, "error": "未指定工具名称"}
        
        tool = self.tool_registry.get(tool_name)
        if not tool:
            return {"success": False, "error": f"工具 '{tool_name}' 不存在"}
        
        try:
            result = tool.execute(**args)
            return result
        except Exception as e:
            self.logger.error(f"工具 {tool_name} 执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def run(self, user_input: str) -> RunResult:
        """
        运行 ReAct 循环
        
        Args:
            user_input: 用户输入
            
        Returns:
            运行结果
        """
        if self.config.verbose:
            self.logger.info(f"开始 ReAct 循环，问题: {user_input[:100]}...")
        
        messages = self._build_initial_messages(user_input)
        steps: List[StepRecord] = []
        tool_calls = 0
        
        for step_num in range(1, self.config.max_steps + 1):
            if self.config.verbose:
                self.logger.info(f"--- 步骤 {step_num} ---")
            
            # 调用 LLM
            try:
                response = self._call_llm(messages)
            except Exception as e:
                return RunResult(
                    success=False,
                    answer="",
                    steps=steps,
                    total_steps=step_num,
                    tool_calls=tool_calls,
                    error=f"LLM 调用失败: {e}"
                )
            
            # 解析响应
            thinking, action, final_answer = self._parse_response(response)
            
            step = StepRecord(
                step_num=step_num,
                thinking=thinking,
                action=action,
                final_answer=final_answer,
                raw_response=response
            )
            
            if self.config.verbose:
                self.logger.info(f"Thinking: {thinking[:100]}..." if thinking else "Thinking: (无)")
            
            # 情况 1: 有最终答案
            if final_answer:
                if self.config.verbose:
                    self.logger.info(f"获得最终答案，共 {step_num} 步，{tool_calls} 次工具调用")
                steps.append(step)
                return RunResult(
                    success=True,
                    answer=final_answer,
                    steps=steps,
                    total_steps=step_num,
                    tool_calls=tool_calls
                )
            
            # 情况 2: 有工具调用
            if action:
                tool_name = action.get("tool", "未知")
                if self.config.verbose:
                    self.logger.info(f"调用工具: {tool_name}")
                
                # 检查工具调用限制
                if tool_calls >= self.config.max_tool_calls:
                    step.observation = "【系统提示】已达到最大工具调用次数限制，请直接给出答案。"
                    steps.append(step)
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": step.observation})
                    continue
                
                # 执行工具
                result = self._execute_action(action)
                tool_calls += 1
                
                # 格式化观察结果
                observation = self._format_observation(tool_name, result)
                step.observation = observation
                
                if self.config.verbose:
                    self.logger.info(f"Observation: {observation[:100]}...")
                
                # 更新消息历史
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": observation})
                steps.append(step)
                continue
            
            # 情况 3: 无 action 也无 final_answer（格式错误）
            if self.config.verbose:
                self.logger.warning("响应格式错误，提示 LLM 修正")
            
            error_msg = """【系统提示】你的输出格式不正确。请严格按照以下格式：

如果需要调用工具：
<thinking>你的思考...</thinking>
<action>{"tool": "工具名称", "args": {"参数": "值"}}</action>

如果要给出最终答案：
<thinking>你的总结...</thinking>
<final_answer>你的答案...</final_answer>

请重新回答。"""
            
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": error_msg})
            step.observation = error_msg
            steps.append(step)
        
        # 已达最大步数
        if self.config.verbose:
            self.logger.warning(f"已达最大步数 {self.config.max_steps}，强制结束")
        
        # 尝试提取思考内容作为答案
        last_thinking = steps[-1].thinking if steps else ""
        fallback_answer = f"抱歉，我已尽力分析但未能得出完整答案。\n\n目前的思考：{last_thinking}" if last_thinking else "抱歉，我未能回答这个问题。"
        
        return RunResult(
            success=False,
            answer=fallback_answer,
            steps=steps,
            total_steps=self.config.max_steps,
            tool_calls=tool_calls,
            error="达到最大步数限制"
        )
