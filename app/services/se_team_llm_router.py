from __future__ import annotations

import re
from typing import Any, Callable

from llm.rag_core.llm_api import DeepSeekAPI


_ROUTING_SYSTEM_PROMPT = (
    "你是严格的路由分类器。"
    "你只能输出一个数字：1 或 2。"
    "禁止输出任何解释、标点、换行或其他字符。"
)

_ROUTING_USER_PROMPT = """判断以下用户输入属于哪一类：
- 输出 1（代码生成/改造）：
  用户明确要求“写、改、实现、修复、重构、新增”代码/脚本/测试/接口/配置，
  或要求你直接产出可执行实现方案（包含 patch、函数、类、接口、测试、脚本）。
- 输出 2（简答问答）：
  用户仅要求解释、介绍、分析、梳理、定位、说明、比较、给建议，
  且没有要求你实际编写或修改代码。

判定优先级（必须遵守）：
1) 只要有明确编码动作和实现交付要求，优先判 1。
2) 仅做项目介绍、调用链说明、原理解释、问题诊断建议，判 2。
3) 像“找到核心方法调用链并解释每个节点作用”属于分析说明，不是写代码，判 2。

示例：
- “请介绍这个项目架构” -> 2
- “给我找到核心调用链并解释每个节点作用” -> 2
- “请修改 se_team_llm_router，让项目介绍类问题走2” -> 1
- “写一个脚本批量验证路由分类” -> 1

用户输入：{requirement}

只输出数字1或2。"""


_EXPLICIT_CODE_ACTION_PATTERN = re.compile(
    r"(修改|改|实现|修复|重构|新增|新建|编写|写|生成|添加|优化|调整|改造|补充)",
    re.IGNORECASE,
)

_CODE_DELIVERABLE_HINT_PATTERN = re.compile(
    r"(代码|脚本|测试|接口|函数|类|参数|配置|补丁|patch|api|route|router|workflow|\.py\b|\.ts\b|\.tsx\b|\.js\b)",
    re.IGNORECASE,
)

_NEGATIVE_CODE_ACTION_PATTERN = re.compile(
    r"(不要|无需|不用|不需要).{0,8}(改代码|写代码|修改|实现|重构|修复)",
    re.IGNORECASE,
)


def llm_semantic_route(
    requirement: str,
    api_key: str = "",
    model_name: str = "",
    base_url: str = "",
    timeout_seconds: int = 8,
    fallback_router: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    text = str(requirement or "").strip()
    if not text:
        return {
            "route_code": 1,
            "reason": "empty requirement fallback",
            "model_used": False,
            "signals": ["empty_requirement"],
            "confidence": 0.5,
        }

    if not (api_key and model_name and base_url):
        return _fallback_rule_route(
            requirement=text,
            reason="llm config missing",
            fallback_router=fallback_router,
        )

    try:
        client = DeepSeekAPI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            timeout=timeout_seconds,
        )
        response = client.chat(
            messages=[
                {"role": "system", "content": _ROUTING_SYSTEM_PROMPT},
                {"role": "user", "content": _ROUTING_USER_PROMPT.format(requirement=text)},
            ],
            temperature=0.0,
            max_tokens=2,
            timeout=timeout_seconds,
        )
        content = str(
            ((response or {}).get("choices") or [{}])[0].get("message", {}).get("content", "")
        ).strip()

        match = re.search(r"(?<!\d)([12])(?!\d)", content)
        if match:
            route_code = int(match.group(1))
            if _should_force_code_generation(text) and route_code != 1:
                route_code = 1
                reason = "llm judged 2; explicit code-action constraint forced 1"
                signals = ["llm_semantic_route", "explicit_code_action_override"]
            else:
                reason = f"llm judged: {route_code}"
                signals = ["llm_semantic_route"]
            return {
                "route_code": route_code,
                "reason": reason,
                "model_used": True,
                "signals": signals,
                "confidence": 0.9,
            }

        return _fallback_rule_route(
            requirement=text,
            reason=f"llm output invalid: {content[:32]}",
            fallback_router=fallback_router,
        )
    except Exception as exc:
        return _fallback_rule_route(
            requirement=text,
            reason=f"llm call failed: {str(exc)}",
            fallback_router=fallback_router,
        )


def _fallback_rule_route(
    requirement: str,
    reason: str,
    fallback_router: Callable[[str], dict[str, Any]] | None,
) -> dict[str, Any]:
    if fallback_router is None:
        return {
            "route_code": 1,
            "reason": f"fallback - {reason}",
            "model_used": False,
            "signals": ["fallback_without_rule_router"],
            "confidence": 0.6,
        }

    result = dict(fallback_router(requirement) or {})
    result["reason"] = f"fallback - {reason}"
    result["model_used"] = False
    signals = list(result.get("signals") or [])
    if "llm_fallback" not in signals:
        signals.append("llm_fallback")
    result["signals"] = signals
    if "confidence" not in result:
        result["confidence"] = 0.7
    return result


def _should_force_code_generation(requirement: str) -> bool:
    text = str(requirement or "").strip()
    if not text:
        return False

    if _NEGATIVE_CODE_ACTION_PATTERN.search(text):
        return False

    has_action = bool(_EXPLICIT_CODE_ACTION_PATTERN.search(text))
    has_deliverable = bool(_CODE_DELIVERABLE_HINT_PATTERN.search(text))
    return has_action and has_deliverable
