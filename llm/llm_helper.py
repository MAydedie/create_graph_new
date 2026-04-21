#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 0 / Task 0.2: 统一 LLM 调用封装

目标：
- 统一 LangChain / 直接 requests 的调用路径
- 提供重试、超时、可选缓存 key
- 集中管理常用 Prompt 模板（逐步迁移）
"""

from __future__ import annotations

import os
import time
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    temperature: float = 0.3
    max_tokens: int = 8000
    timeout: int = 60
    max_retries: int = 3
    retry_backoff_base: float = 1.0


class PromptTemplate:
    """集中管理系统 Prompt（0.1 版本先放最常用的）。"""

    @staticmethod
    def code_explanation() -> str:
        return """你是一个资深的代码分析专家。
你的任务是用简洁清晰的语言解释给定的代码的功能和设计意图。

解释应该：
1. 简洁（不超过200字）
2. 清楚明了（避免过度技术术语）
3. 突出关键逻辑和设计决策
4. 指出该代码与系统其他部分的关系（如果有）

格式：
- 主要功能是什么？（1-2句）
- 关键算法或逻辑是什么？（1-2句）
- 与系统的关系？（1句）"""


class LLMHelper:
    """统一的 LLM 调用入口。"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = self._init_langchain_client()
        self._mem_cache: Dict[str, str] = {}

    def _init_langchain_client(self):
        """尽最大努力初始化 LangChain 客户端；失败则返回 None（走 requests）。"""
        try:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout,
            )
        except Exception:
            try:
                from langchain_community.chat_models import ChatOpenAI

                return ChatOpenAI(
                    openai_api_key=self.config.api_key,
                    openai_api_base=self.config.base_url,
                    model_name=self.config.model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    request_timeout=self.config.timeout,
                )
            except Exception as e:
                logger.warning(f"[LLMHelper] LangChain 客户端初始化失败，将使用直接 API 调用: {e}")
                return None

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        cache_key: Optional[str] = None,
        use_cache: bool = True,
    ) -> str:
        """调用 LLM 并返回文本结果。"""
        if use_cache and cache_key:
            cached = self._mem_cache.get(cache_key)
            if cached is not None:
                return cached

        last_err: Optional[Exception] = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                if self._client is not None:
                    from langchain_core.messages import SystemMessage, HumanMessage

                    resp = self._client.invoke(
                        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                    )
                    text = getattr(resp, "content", "") or ""
                else:
                    text = self._call_api_directly(system_prompt, user_prompt)

                if use_cache and cache_key:
                    self._mem_cache[cache_key] = text
                return text
            except Exception as e:
                last_err = e
                if attempt >= self.config.max_retries:
                    break
                sleep_s = self.config.retry_backoff_base * (2 ** (attempt - 1))
                logger.warning(f"[LLMHelper] 调用失败，{sleep_s:.1f}s 后重试 ({attempt}/{self.config.max_retries}): {e}")
                time.sleep(sleep_s)

        raise RuntimeError(f"LLM 调用失败: {last_err}")

    def _call_api_directly(self, system_prompt: str, user_prompt: str) -> str:
        import requests

        url = f"{self.config.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=self.config.timeout)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]


_global_llm_helper: Optional[LLMHelper] = None


def get_llm_helper() -> LLMHelper:
    """获取全局 LLMHelper（单例）。"""
    global _global_llm_helper
    if _global_llm_helper is None:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        if not api_key:
            logger.warning("[LLMHelper] DEEPSEEK_API_KEY 未设置，LLM 调用将失败（请配置 .env）")
        cfg = LLMConfig(api_key=api_key, base_url=base_url)
        _global_llm_helper = LLMHelper(cfg)
    return _global_llm_helper









