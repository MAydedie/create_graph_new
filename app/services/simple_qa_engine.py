from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from llm.rag_core.llm_api import DeepSeekAPI

from app.services import persona_skill_service as pss
from app.services.simple_qa_agents import SIMPLE_QA_AGENTS, SIMPLE_QA_WORKFLOW_STEPS, WorkflowContext
from app.services.se_team_embedded_service import _extract_ai_team_model_config, _load_ai_team_modules


# 剥离 LLM 响应里的 <think>...</think> 推理块
# M3 / 推理类模型会把 chain-of-thought 放在正文前面,要送进前端必须先去掉
_THINK_BLOCK_PATTERN = re.compile(
    r"<think>[\s\S]*?</think>\s*",
    re.IGNORECASE,
)

_PROJECT_EVIDENCE_PARTITION_LIMIT = int(os.getenv("SIMPLE_QA_PARTITION_LIMIT", "0"))
_PROJECT_EVIDENCE_PATH_LIMIT = int(os.getenv("SIMPLE_QA_PATH_LIMIT", "0"))
_EXPERIENCE_PROJECT_LIMIT = int(os.getenv("SIMPLE_QA_PROJECT_LIMIT", "0"))


def _limit_items(items: list[Any], limit: int) -> list[Any]:
    if limit <= 0:
        return items
    return items[:limit]


def _strip_thinking_block(text: str) -> str:
    """去掉响应开头的 <think>...</think> 推理块,保留正式答复。

    支持以下变体:
      - <think>...</think>
      - <think>\\n...\\n</think>
      - 大小写不敏感
    如果找不到 think 块,原样返回。
    """
    if not text:
        return text
    cleaned = _THINK_BLOCK_PATTERN.sub("", text).strip()
    return cleaned or text.strip()


# 简易问候 / 寒暄词集合 —— 这些场景不需要走 7 阶段工作流
# 配套的 casual 结尾(只能跟在问候词后面,单独出现不算问候)
_GREETING_CASUAL_SUFFIXES = ("啊", "呀", "哦", "哈", "嘿", "嘞", "哇", "呀", "哎", "呀")

_SIMPLE_GREETING_PATTERNS = (
    "你好", "您好", "hello", "hi", "嗨", "hey",
    "在吗", "在么", "哈喽", "早上好", "中午好", "下午好", "晚上好",
    "thanks", "thank you", "thx", "好的", "ok", "okay",
    "再见", "拜拜", "byebye", "bye",
)


def _is_simple_greeting(requirement: str) -> bool:
    """判断用户输入是不是一句纯粹的寒暄/问候,不需要走完整工作流。

    规则:
      - 去除标点和空白后,长度 ≤ 8
      - 等于某个问候词,或 问候词 + 1-2 个语气词(如"你好啊")
      - 不能含有非语气词的真实内容(避免 "你好,请帮我" 误判)
    """
    text = str(requirement or "").strip().lower()
    if not text or len(text) > 30:
        return False
    normalized = re.sub(r"[\s,.!?;:'\"，。！？；:]+", "", text)
    if not normalized:
        return False
    if len(normalized) > 8:
        return False

    for pattern in _SIMPLE_GREETING_PATTERNS:
        pat = pattern.lower()
        if normalized == pat:
            return True
        # 问候词 + 最多 2 个语气字
        if normalized.startswith(pat):
            suffix = normalized[len(pat):]
            if 0 <= len(suffix) <= 2 and all(c in _GREETING_CASUAL_SUFFIXES for c in suffix):
                return True
    return False


def _compose_persona_system_prompt(base_prompt: str) -> dict[str, Any]:
    payload = pss.compose_system_prompt(base_prompt)
    if not isinstance(payload, dict):
        return {"systemPrompt": base_prompt, "temperature": None, "activePersona": None}
    return payload


def _resolve_persona_temperature(default_temperature: float, prompt_bundle: dict[str, Any]) -> float:
    raw = prompt_bundle.get("temperature") if isinstance(prompt_bundle, dict) else None
    if raw is None:
        return float(default_temperature)
    try:
        parsed = float(raw)
        if 0 <= parsed <= 1.5:
            return parsed
    except (TypeError, ValueError):
        pass
    return float(default_temperature)


def _active_persona_name() -> str:
    active = pss.get_active_persona_state()
    persona_raw = active.get("persona") if isinstance(active, dict) else None
    if not isinstance(persona_raw, dict):
        return ""
    return str(persona_raw.get("name") or persona_raw.get("personaId") or "").strip()


def _apply_persona_voice_prefix(answer: str) -> str:
    text = str(answer or "").strip()
    if not text:
        return text
    persona_name = _active_persona_name()
    if not persona_name:
        return text
    prefix = f"[{persona_name}视角] "
    if text.startswith(prefix):
        return text
    return f"{prefix}{text}"


def _finalize_persona_answer(answer: str) -> str:
    text = str(answer or "").strip()
    disclaimer = pss.consume_pending_disclaimer()
    if disclaimer:
        return f"{disclaimer}\n\n{text}" if text else disclaimer
    return text


class SimpleQaEngine:
    """简答问答工作流引擎，输出格式与 8 段工作流保持一致。"""

    def __init__(self):
        self._api_key, self._model_name, self._base_url = _extract_ai_team_model_config()

    def _normalize_history(self, history: Optional[list[dict[str, str]]]) -> list[dict[str, str]]:
        if not isinstance(history, list):
            return []
        normalized: list[dict[str, str]] = []
        for item in history[-10:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "user").strip() or "user"
            if role not in {"user", "assistant", "system"}:
                role = "user"
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            normalized.append({"role": role, "content": content})
        return normalized

    async def _call_agent(
        self,
        agent_name: str,
        context: WorkflowContext,
        step: dict[str, Any],
        history: Optional[list[dict[str, str]]] = None,
    ) -> str:
        agent = SIMPLE_QA_AGENTS.get(agent_name)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_name}")

        prompt_params: dict[str, str] = {
            "requirement": context.raw_requirement,
            "session_mode": context.session_mode,
            "project_path": context.project_path,
            "project_name": context.project_name,
            "project_description": context.project_description,
            "project_readme_excerpt": context.project_readme_excerpt,
            "project_structure": context.project_structure,
            "retrieval_overview": context.retrieval_overview,
            "experience_summary": context.experience_summary,
            "experience_evidence": context.experience_evidence,
            "project_evidence_blocks": context.project_evidence_blocks,
            "project_bias_summary": context.project_bias_summary,
            "per_project_result": str(context.get_output("per_project_result") or ""),
            "comparison_result": str(context.get_output("comparison_result") or ""),
            "advisor_guidance": str(context.get_output("advisor_guidance") or ""),
            "reasoning_result": str(context.get_output("reasoning_result") or ""),
        }
        for input_key in step.get("input_keys", []):
            if input_key == "raw_requirement":
                continue
            value = context.get_output(input_key, "")
            if value is None:
                value = ""
            prompt_params[input_key] = str(value)

        prompt = agent.prompt_template.format(**prompt_params)
        stage = str(step.get("stage") or "")
        base_system_prompt = (
            "你是 SE-Team 的简答流程智能体。"
            "请严格按照当前阶段目标输出，避免跑题；"
            "在信息不足时明确边界，不要编造。"
        )
        prompt_bundle = _compose_persona_system_prompt(base_system_prompt)
        system_prompt = str(prompt_bundle.get("systemPrompt") or base_system_prompt)
        answer_temperature = _resolve_persona_temperature(0.3, prompt_bundle)

        if not (self._api_key and self._model_name and self._base_url):
            fallback = self._fallback_stage_output(step["stage"], context)
            if stage == "qa_reply":
                return _apply_persona_voice_prefix(fallback)
            return fallback

        client = DeepSeekAPI(
            api_key=self._api_key,
            base_url=self._base_url,
            model=self._model_name,
            timeout=agent.timeout_seconds,
        )

        response = await asyncio.to_thread(
            client.chat,
            messages=[{"role": "system", "content": system_prompt}] + self._normalize_history(history) + [{"role": "user", "content": prompt}],
            temperature=answer_temperature,
            max_tokens={
                "requirement_analysis": 600,
                "experience_retrieval": 1300,
                "per_project_extraction": 2200,
                "cross_project_comparison": 1500,
                "qa_advisor": 1200,
                "qa_evidence_reasoning": 2200,
                "qa_reply": 3200,
            }.get(stage, 900),
            timeout=agent.timeout_seconds,
        )
        content = str(((response or {}).get("choices") or [{}])[0].get("message", {}).get("content", "")).strip()
        content = _strip_thinking_block(content)
        if content:
            return self._normalize_stage_output(stage, content)
        return self._fallback_stage_output(step["stage"], context)

    async def _handle_simple_greeting(self, context: WorkflowContext) -> str:
        """快速通道处理:简短寒暄/问候,只调一次 LLM,不跑 7 阶段。

        失败时(LLM 不可用/无 key/超时)返回空字符串,让外层走原本的 fallback。
        """
        api_key, model_name, base_url = self._api_key, self._model_name, self._base_url
        if not (api_key and model_name and base_url):
            return ""

        system_prompt = (
            "你是 SE-Team 顾问智能体。"
            "用户只是简短地寒暄或打招呼(比如 '你好'、'hi'、'在吗')。"
            "请用一两句话自然地回礼,顺便简短说明你能帮他做什么(代码生成 / 经验检索 / 任务编排)。"
            "禁止输出 '<think>' 等内部推理块,直接给最终答复。"
        )
        user_prompt = (
            f"用户说: {context.raw_requirement.strip()}\n\n"
            "请简短回应(50-120 字以内,直接给用户,不要解释你为什么这么答)。"
        )
        try:
            client = DeepSeekAPI(
                api_key=api_key,
                base_url=base_url,
                model=model_name,
                timeout=15,
            )
            response = await asyncio.to_thread(
                client.chat,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=200,
                timeout=15,
            )
            content = str(
                ((response or {}).get("choices") or [{}])[0]
                .get("message", {})
                .get("content", "")
            ).strip()
            content = _strip_thinking_block(content)
            return content
        except Exception:
            return ""

    async def run_workflow(
        self,
        session_id: str,
        requirement: str,
        project_path: str = "",
        decision: dict[str, Any] | None = None,
        history: Optional[list[dict[str, str]]] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        resolved_mode, resolved_project_path = self._resolve_session_scope(
            session_id=session_id,
            project_path=project_path,
        )
        project_info = self._get_project_info(resolved_project_path)
        context = WorkflowContext(
            raw_requirement=requirement,
            session_id=session_id,
            session_mode=resolved_mode,
            project_path=resolved_project_path,
            project_name=str(project_info.get("name") or ""),
            project_description=str(project_info.get("description") or ""),
            project_readme_excerpt=str(project_info.get("readme_excerpt") or ""),
            project_structure=self._build_project_structure_summary(resolved_project_path),
        )
        decision_payload = dict(decision or {})
        route_code = int(decision_payload.get("route_code") or 2)

        yield {
            "event": "route_decision",
            "type": "route_decision",
            "route_code": route_code,
            "mode": "simple_qa",
            "session_id": session_id,
            "reason": str(decision_payload.get("reason") or "simple_qa_engine"),
            "confidence": float(decision_payload.get("confidence") or 0.85),
            "model_used": bool(decision_payload.get("model_used", False)),
            "timestamp": _utcnow_iso(),
        }

        yield {
            "event": "workflow_start",
            "type": "workflow_start",
            "session_id": session_id,
            "requirement": requirement,
            "total_steps": len(SIMPLE_QA_WORKFLOW_STEPS),
            "mode": "simple_qa",
            "route_code": route_code,
            "project_path": resolved_project_path,
            "project_name": context.project_name,
            "session_mode": context.session_mode,
            "timestamp": _utcnow_iso(),
        }

        # 快速通道:简短寒暄 + 经验库无相关命中 → 只跑 1 次 LLM(走 qa_reply agent)
        # 而不是 7 个 stage 全跑一遍
        if _is_simple_greeting(requirement):
            greeting_reply = await self._handle_simple_greeting(context)
            if greeting_reply:
                yield {
                    "event": "fast_path",
                    "type": "fast_path",
                    "reason": "simple_greeting",
                    "stage": "qa_reply",
                    "timestamp": _utcnow_iso(),
                    "session_id": session_id,
                }
                final_answer = _apply_persona_voice_prefix(greeting_reply)
                final_answer = _finalize_persona_answer(final_answer)
                for chunk in _chunk_text(final_answer):
                    yield {
                        "event": "stream_chunk",
                        "type": "stream_chunk",
                        "timestamp": _utcnow_iso(),
                        "step": 99,
                        "stage": "qa_reply",
                        "content": chunk,
                        "mode": "simple_qa",
                        "session_id": session_id,
                    }
                    await asyncio.sleep(0.005)
                yield {
                    "event": "simple_qa_answer",
                    "type": "simple_qa_answer",
                    "role": "assistant",
                    "mode": "simple_qa",
                    "session_id": session_id,
                    "stage": "给出回复",
                    "content": final_answer,
                    "fast_path": True,
                    "done": True,
                    "timestamp": _utcnow_iso(),
                }
                yield {
                    "event": "workflow_complete",
                    "type": "workflow_complete",
                    "status": "completed",
                    "mode": "simple_qa",
                    "session_id": session_id,
                    "timestamp": _utcnow_iso(),
                }
                return

        for step in SIMPLE_QA_WORKFLOW_STEPS:
            step_num = int(step["step"])
            stage = str(step["stage"])
            display_name = str(step["display"])
            agent_name = str(step["agent"])
            agent = SIMPLE_QA_AGENTS.get(agent_name)

            yield {
                "event": "stage_start",
                "type": "stage_start",
                "timestamp": _utcnow_iso(),
                "step": step_num,
                "stage": stage,
                "display_name": display_name,
                "agent_name": agent_name,
                "agent_type": agent.agent_type.value if agent else "standard",
                "icon": agent.icon if agent else "🧩",
                "mode": "simple_qa",
                "session_id": session_id,
            }

            if agent and agent.agent_type.value == "advisor":
                experiences, candidate_projects = self._search_experience(
                    requirement=requirement,
                    project_path=context.project_path,
                    session_mode=context.session_mode,
                )
                context.experience_refs = experiences
                context.candidate_projects = candidate_projects
                context.experience_summary = self._build_experience_summary(
                    experiences,
                    candidate_projects=candidate_projects,
                    session_mode=context.session_mode,
                )
                context.experience_evidence = self._build_experience_evidence(experiences)
                context.project_evidence_blocks = self._build_project_evidence_blocks(experiences)
                context.project_bias_summary = self._build_project_bias_summary(
                    experiences,
                    candidate_projects=candidate_projects,
                )
                yield {
                    "event": "experience_matched",
                    "type": "experience_matched",
                    "timestamp": _utcnow_iso(),
                    "step": step_num,
                    "stage": stage,
                    "experiences": experiences,
                    "candidate_projects": candidate_projects,
                    "project_bias_summary": context.project_bias_summary,
                    "project_evidence_blocks": context.project_evidence_blocks,
                    "session_mode": context.session_mode,
                    "mode": "simple_qa",
                    "session_id": session_id,
                }

            yield {
                "event": "workflow_step",
                "type": "workflow_step",
                "mode": "simple_qa",
                "session_id": session_id,
                "stage": display_name,
                "content": f"正在执行 {display_name}...",
                "timestamp": _utcnow_iso(),
            }

            stage_error: str | None = None
            try:
                result = await self._call_agent(agent_name, context, step, history=history)
            except Exception as exc:
                stage_error = str(exc)
                result = self._fallback_stage_output(stage, context)
                if stage == "qa_reply":
                    result = _apply_persona_voice_prefix(result)

            if stage == "qa_reply":
                result = _apply_persona_voice_prefix(result)
                result = self._ensure_structured_final_answer(result, context)
                result = _finalize_persona_answer(result)

            context.set_output(step["output_key"], result)
            if step.get("output_key") == "retrieval_overview":
                context.retrieval_overview = result

            if stage_error:
                yield {
                    "event": "stage_error",
                    "type": "stage_error",
                    "timestamp": _utcnow_iso(),
                    "step": step_num,
                    "stage": stage,
                    "error": stage_error,
                    "mode": "simple_qa",
                    "session_id": session_id,
                }

            for chunk in _chunk_text(result):
                yield {
                    "event": "stream_chunk",
                    "type": "stream_chunk",
                    "timestamp": _utcnow_iso(),
                    "step": step_num,
                    "stage": stage,
                    "content": chunk,
                    "mode": "simple_qa",
                    "session_id": session_id,
                }
                await asyncio.sleep(0.005)

            yield {
                "event": "stage_complete",
                "type": "stage_complete",
                "timestamp": _utcnow_iso(),
                "step": step_num,
                "stage": stage,
                "display_name": display_name,
                "output": result,
                "pass_token": step.get("pass_token"),
                "mode": "simple_qa",
                "session_id": session_id,
            }

        final_answer = str(context.get_output("final_answer") or "").strip()
        if not final_answer:
            final_answer = self._fallback_stage_output("qa_reply", context)

        yield {
            "event": "simple_qa_answer",
            "type": "simple_qa_answer",
            "role": "assistant",
            "mode": "simple_qa",
            "session_id": session_id,
            "stage": "给出回复",
            "content": final_answer,
            "done": True,
            "timestamp": _utcnow_iso(),
        }

        yield {
            "event": "workflow_complete",
            "type": "workflow_complete",
            "status": "completed",
            "mode": "simple_qa",
            "session_id": session_id,
            "timestamp": _utcnow_iso(),
        }

    def _fallback_stage_output(self, stage: str, context: WorkflowContext) -> str:
        requirement = context.raw_requirement.strip()
        if stage == "requirement_analysis":
            return (
                "问题类型: 实现细节\n"
                "检索目标: 提取每个经验库的关键路径、方法链和适用场景\n"
                "回答策略: 先逐经验库列证据，再做优先级对比与融合结论"
            )
        if stage == "experience_retrieval":
            if context.experience_summary:
                return context.experience_summary
            return "- 检索覆盖: 0 个经验库 / 0 条路径\n- 重点经验库: 暂无\n- 下一步提取策略: 待补充证据"
        if stage == "per_project_extraction":
            if context.project_evidence_blocks:
                return context.project_evidence_blocks[:3500]
            return "### [无可用经验库]\n- 未匹配到可用路径证据"
        if stage == "cross_project_comparison":
            if context.project_bias_summary:
                return context.project_bias_summary
            return "1) 经验库优先级排序: 暂无\n2) 子问题适配: 暂无\n3) 融合策略: 先补全证据后再比较"
        if stage == "qa_advisor":
            if context.retrieval_overview:
                return (
                    "- 总结结论: 先给全局判断\n"
                    "- 按经验库列证据: 每库至少2条路径\n"
                    "- 最终融合建议: 按优先级组合并给落地步骤"
                )
            return "- 总结结论\n- 按经验库列证据\n- 最终融合建议"
        if stage == "qa_evidence_reasoning":
            if context.experience_evidence:
                return f"已检索到经验证据，优先依据以下路径推理：\n{context.experience_evidence[:3200]}"
            description = context.project_description or "暂无项目描述"
            return f"该问题优先按项目上下文回答：项目为 {context.project_name or '当前项目'}，{description}。"
        if stage == "qa_reply":
            reasoning = str(context.get_output("reasoning_result") or "").strip()
            if reasoning:
                return self._strip_source_trace_lines(reasoning[:6400])
            if context.experience_evidence:
                bias_summary = self._build_bias_section_text(context)
                return (
                    "已基于经验库完成检索与比对。"
                    + (f" {bias_summary}" if bias_summary else "")
                    + " 回答将保留结论与实现思路，不再附带原始来源条目列表。"
                )
            if context.project_name:
                return f"当前项目是 {context.project_name}。基于当前可见信息，它的核心目标是：{context.project_description or '请结合仓库结构进一步确认具体功能'}。"
            return f"这是一个解释型问题：{requirement}。建议先明确概念定义，再说明原理和适用边界。"
        return requirement

    def _resolve_session_scope(self, session_id: str, project_path: str) -> tuple[str, str]:
        explicit_path = str(project_path or "").strip()
        default_mode = "single_project" if explicit_path else "global"
        try:
            modules = _load_ai_team_modules()
            engine = modules["get_engine"]()
            state = engine.get_session(session_id)
            if state:
                mode_raw = str(getattr(state, "mode", "") or "").strip().lower()
                resolved_mode = mode_raw if mode_raw in {"single_project", "global"} else default_mode
                resolved_path = explicit_path or str(getattr(state, "selected_project_path", "") or "").strip()
                if resolved_mode == "global":
                    resolved_path = ""
                return resolved_mode, resolved_path
        except Exception:
            pass
        return default_mode, explicit_path

    def _resolve_project_path(self, session_id: str, project_path: str) -> str:
        _, resolved_path = self._resolve_session_scope(session_id=session_id, project_path=project_path)
        return resolved_path

    def _get_project_info(self, project_path: str) -> dict[str, str]:
        normalized = str(project_path or "").strip()
        if not normalized:
            return {"name": "", "description": "", "readme_excerpt": ""}

        path_obj = Path(normalized)
        if not path_obj.exists():
            return {
                "name": path_obj.name,
                "description": "项目路径不存在，无法读取更多信息。",
                "readme_excerpt": "",
            }

        project_name = path_obj.name
        description = ""

        package_json = path_obj / "package.json"
        if package_json.exists():
            try:
                pkg = json.loads(package_json.read_text(encoding="utf-8"))
                project_name = str(pkg.get("name") or project_name)
                description = str(pkg.get("description") or "").strip()
            except Exception:
                pass

        if not description:
            pyproject = path_obj / "pyproject.toml"
            if pyproject.exists():
                try:
                    content = pyproject.read_text(encoding="utf-8", errors="ignore")
                    name_match = re.search(r"(?m)^\s*name\s*=\s*['\"]([^'\"]+)['\"]", content)
                    desc_match = re.search(r"(?m)^\s*description\s*=\s*['\"]([^'\"]+)['\"]", content)
                    if name_match:
                        project_name = name_match.group(1).strip() or project_name
                    if desc_match:
                        description = desc_match.group(1).strip()
                except Exception:
                    pass

        readme_excerpt = ""
        for readme_name in ("README.md", "README.MD", "readme.md", "README.txt"):
            readme_file = path_obj / readme_name
            if readme_file.exists():
                try:
                    readme_excerpt = self._extract_readme_excerpt(readme_file.read_text(encoding="utf-8", errors="ignore"))
                    if readme_excerpt and not description:
                        description = readme_excerpt[:120]
                except Exception:
                    pass
                break

        return {
            "name": project_name,
            "description": description,
            "readme_excerpt": readme_excerpt,
        }

    def _extract_readme_excerpt(self, text: str) -> str:
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        filtered = [line for line in lines if not line.startswith("#")]
        excerpt = " ".join(filtered[:3]).strip() if filtered else ""
        return excerpt[:240]

    def _build_project_structure_summary(self, project_path: str) -> str:
        normalized = str(project_path or "").strip()
        if not normalized:
            return "未提供项目路径"
        path_obj = Path(normalized)
        if not path_obj.exists() or not path_obj.is_dir():
            return "项目路径不可用"

        entries: list[str] = []
        try:
            for item in sorted(path_obj.iterdir(), key=lambda x: x.name.lower()):
                if item.name.startswith("."):
                    continue
                suffix = "/" if item.is_dir() else ""
                entries.append(f"{item.name}{suffix}")
                if len(entries) >= 14:
                    break
        except Exception:
            return "项目结构读取失败"

        return "顶层结构: " + (", ".join(entries) if entries else "(空目录)")

    def _search_experience(
        self,
        requirement: str,
        project_path: str,
        session_mode: str = "single_project",
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        try:
            modules = _load_ai_team_modules()
            store = modules["get_experience_store"]()
            normalized_mode = str(session_mode or "single_project").strip().lower()
            if normalized_mode == "global":
                candidate_projects: list[dict[str, Any]] = []
                try:
                    from app.services.project_manager_service import get_project_manager_service

                    pm_service = get_project_manager_service()
                    pm_service.bulk_register_from_experience_paths(force_refresh=False)
                    candidate_projects = pm_service.retrieve_top_projects(
                        query=requirement,
                        top_k=6,
                        mmr_lambda=0.7,
                        expand_query=False,
                    ) or []
                except Exception:
                    candidate_projects = []

                global_top_k = 10
                if candidate_projects:
                    global_top_k = min(max(len(candidate_projects) * 2, 8), 14)

                experiences = store.search(
                    requirement,
                    top_k=global_top_k,
                    project_path=None,
                    project_whitelist=candidate_projects or None,
                    attach_source=True,
                    per_project_top_paths=6,
                )
                return experiences, candidate_projects

            experiences = store.search(
                requirement,
                top_k=8,
                project_path=project_path or None,
                attach_source=True,
                per_project_top_paths=6,
            )
            return experiences, []
        except Exception:
            return [], []

    def _build_experience_summary(
        self,
        experiences: list[dict[str, Any]],
        candidate_projects: Optional[list[dict[str, Any]]] = None,
        session_mode: str = "single_project",
    ) -> str:
        if not experiences:
            if str(session_mode or "").strip().lower() == "global":
                return "全局模式：未匹配到经验路径"
            return "单项目模式：未匹配到经验路径"
        lines: list[str] = []
        if str(session_mode or "").strip().lower() == "global":
            candidate_names = []
            for item in (candidate_projects or [])[:4]:
                name = str(item.get("project_name") or "").strip()
                if name:
                    score = item.get("score")
                    score_text = f" ({score})" if score is not None else ""
                    candidate_names.append(f"{name}{score_text}")
            if candidate_names:
                lines.append("候选项目: " + " / ".join(candidate_names))
        total_paths = 0
        for exp in _limit_items(experiences, _EXPERIENCE_PROJECT_LIMIT):
            name = str(exp.get("project_name") or "未知项目")
            score = exp.get("match_score", "N/A")
            total_paths = int(exp.get("total_paths") or 0)
            lines.append(f"- {name} (score={score}, paths={total_paths})")
        lines.insert(0, f"检索覆盖: 项目 {len(experiences)} 个 / 路径 {sum(int(item.get('total_paths') or 0) for item in experiences)} 条")
        return "\n".join(lines)

    def _build_experience_evidence(self, experiences: list[dict[str, Any]]) -> str:
        if not experiences:
            return ""

        lines: list[str] = []
        path_count = 0
        for exp in _limit_items(experiences, _EXPERIENCE_PROJECT_LIMIT):
            exp_project = str(exp.get("project_name") or "未知项目")
            partitions = exp.get("partitions") or []
            if not isinstance(partitions, list):
                continue
            for partition in _limit_items(partitions, _PROJECT_EVIDENCE_PARTITION_LIMIT):
                if not isinstance(partition, dict):
                    continue
                partition_name = str(partition.get("partition_name") or "未分区")
                paths = partition.get("paths") or []
                if not isinstance(paths, list):
                    continue
                for path_item in _limit_items(paths, _PROJECT_EVIDENCE_PATH_LIMIT):
                    if not isinstance(path_item, dict):
                        continue
                    source_project = str(path_item.get("source_project_name") or exp_project or "未知项目")
                    source_partition = str(path_item.get("source_partition_name") or partition_name or "未分区")
                    path_name = str(path_item.get("path_name") or path_item.get("name") or "未命名路径")
                    description = str(path_item.get("path_description") or path_item.get("description") or "").strip()
                    method_chain = self._extract_path_methods(path_item)

                    line = f"- 来源: {source_project} / {source_partition} / {path_name}"
                    details = []
                    if description:
                        details.append(f"描述: {description[:220]}")
                    if method_chain:
                        details.append(f"方法: {method_chain}")
                    if details:
                        line += " | " + "；".join(details)
                    lines.append(line)

                    path_count += 1
                    if path_count >= 80:
                        return "\n".join(lines)

        return "\n".join(lines)

    def _build_project_evidence_blocks(self, experiences: list[dict[str, Any]]) -> str:
        if not experiences:
            return ""

        blocks: list[str] = []
        for exp in experiences[:10]:
            project_name = str(exp.get("project_name") or "未知项目")
            score = exp.get("match_score", "N/A")
            project_lines = [f"### {project_name} (match_score={score})"]

            partitions = exp.get("partitions") or []
            path_written = 0
            for partition in _limit_items(partitions, _PROJECT_EVIDENCE_PARTITION_LIMIT):
                if not isinstance(partition, dict):
                    continue
                partition_name = str(partition.get("partition_name") or "未分区")
                paths = partition.get("paths") or []
                if not isinstance(paths, list):
                    continue
                for path_item in _limit_items(paths, _PROJECT_EVIDENCE_PATH_LIMIT):
                    if not isinstance(path_item, dict):
                        continue
                    path_name = str(path_item.get("path_name") or path_item.get("name") or "未命名路径")
                    description = str(path_item.get("path_description") or path_item.get("description") or "").strip()
                    method_chain = self._extract_path_methods(path_item)
                    detail_parts = []
                    if description:
                        detail_parts.append(f"描述:{description[:180]}")
                    if method_chain:
                        detail_parts.append(f"方法:{method_chain}")
                    suffix = f" | {'；'.join(detail_parts)}" if detail_parts else ""
                    project_lines.append(f"- {project_name} / {partition_name} / {path_name}{suffix}")
                    path_written += 1
                    if path_written >= 12:
                        break
                if path_written >= 12:
                    break

            if path_written > 0:
                blocks.append("\n".join(project_lines))

        return "\n\n".join(blocks)

    def _build_project_bias_summary(
        self,
        experiences: list[dict[str, Any]],
        candidate_projects: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        if not experiences and not candidate_projects:
            return ""

        lines: list[str] = ["经验库优先级建议:"]
        if candidate_projects:
            for idx, item in enumerate(candidate_projects[:6], start=1):
                name = str(item.get("project_name") or "未知项目")
                score = item.get("score")
                lines.append(f"- Top {idx}: {name} (project_score={score if score is not None else 'N/A'})")

        exp_rank = sorted(
            experiences,
            key=lambda item: float(item.get("match_score") or 0.0),
            reverse=True,
        )
        lines.append("路径匹配强度:")
        for exp in _limit_items(exp_rank, _EXPERIENCE_PROJECT_LIMIT):
            name = str(exp.get("project_name") or "未知项目")
            score = exp.get("match_score", "N/A")
            total_paths = int(exp.get("total_paths") or 0)
            lines.append(f"- {name}: match_score={score}, matched_paths={total_paths}")
        lines.append("融合原则: 优先高匹配项目提供主干方案，再用次优项目补充边界场景与工程约束。")
        return "\n".join(lines)

    def _build_grouped_project_items_for_answer(
        self,
        experiences: list[dict[str, Any]],
        max_projects: int = 6,
        max_paths_per_project: int = 4,
    ) -> str:
        if not experiences:
            return "- 当前未检索到可分组的经验路径。"

        blocks: list[str] = []
        for exp in experiences[:max_projects]:
            project_name = str(exp.get("project_name") or "未知项目")
            score = exp.get("match_score", "N/A")
            block_lines = [f"#### 经验库：{project_name} (match_score={score})"]
            path_written = 0
            partitions = exp.get("partitions") or []
            for partition in _limit_items(partitions, _PROJECT_EVIDENCE_PARTITION_LIMIT):
                if not isinstance(partition, dict):
                    continue
                partition_name = str(partition.get("partition_name") or "未分区")
                for path_item in _limit_items(partition.get("paths") or [], _PROJECT_EVIDENCE_PATH_LIMIT):
                    if not isinstance(path_item, dict):
                        continue
                    path_name = str(path_item.get("path_name") or path_item.get("name") or "未命名路径")
                    desc = str(path_item.get("path_description") or path_item.get("description") or "").strip()
                    summary = desc[:90] if desc else "用于支撑该主题的实现路径"
                    block_lines.append(f"- 来源: {project_name} / {partition_name} / {path_name} | {summary}")
                    path_written += 1
                    if path_written >= max_paths_per_project:
                        break
                if path_written >= max_paths_per_project:
                    break
            if path_written > 0:
                blocks.append("\n".join(block_lines))

        return "\n\n".join(blocks) if blocks else "- 当前未检索到可分组的经验路径。"

    def _build_bias_section_text(self, context: WorkflowContext) -> str:
        candidates = context.candidate_projects or []
        if candidates:
            top_names = [str(item.get("project_name") or "未知项目") for item in candidates[:3]]
            lead = top_names[0]
            others = "、".join(top_names[1:]) if len(top_names) > 1 else ""
            if others:
                return (
                    f"优先参考 `{lead}` 作为主干经验库；"
                    f"再结合 `{others}` 提供的补充路径，覆盖边界场景与工程约束。"
                )
            return f"优先参考 `{lead}`，其匹配得分和相关路径覆盖更稳定。"

        experiences = context.experience_refs or []
        if experiences:
            best = max(experiences, key=lambda item: float(item.get("match_score") or 0.0))
            best_name = str(best.get("project_name") or "未知项目")
            return f"优先参考 `{best_name}`，其路径匹配强度最高，适合作为回答主线。"
        return "当前未命中有效经验库，建议先补充检索条件后再给出偏向判断。"

    def _build_fusion_section_text(self, context: WorkflowContext) -> str:
        candidates = [str(item.get("project_name") or "未知项目") for item in (context.candidate_projects or [])[:4]]
        if not candidates:
            candidates = [
                str(item.get("project_name") or "未知项目")
                for item in (context.experience_refs or [])[:4]
            ]

        if not candidates:
            return "1. 澄清问题边界；2. 重新检索经验库；3. 按主干路径与补充路径组织回答。"

        primary = candidates[0]
        supplements = candidates[1:]
        supplement_text = "、".join(supplements) if supplements else "其他相关经验库"
        return (
            "1. 先以 `"
            + primary
            + "` 的核心路径构建主干方案；\n"
            "2. 再用 `"
            + supplement_text
            + "` 补充异常处理、扩展场景与工程化细节；\n"
            "3. 最后统一到单一执行流程，形成可落地的最终方案。"
        )

    def _strip_duplicate_evidence_section(self, text: str) -> str:
        body = str(text or "").strip()
        if not body:
            return body

        patterns = [
            r"\n\s*#{1,6}\s*经验库证据[\s\S]*$",
            r"\n\s*\*\*经验库证据\*\*[\s\S]*$",
            r"\n\s*经验库证据\s*[：:][\s\S]*$",
        ]
        cleaned = body
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).rstrip()
        return cleaned

    def _strip_source_trace_lines(self, text: str) -> str:
        body = str(text or "").strip()
        if not body:
            return body

        cleaned_lines: list[str] = []
        skip_grouped_section = False
        for raw_line in body.splitlines():
            line = raw_line.rstrip()
            normalized = line.strip()

            if re.match(r"^#{1,6}\s*按经验库分组的具体路径条目\s*$", normalized):
                skip_grouped_section = True
                continue

            if skip_grouped_section:
                if normalized.startswith("#"):
                    skip_grouped_section = False
                elif not normalized:
                    continue
                else:
                    continue

            if re.match(r"^#{1,6}\s*.+\(match_score=.*\)\s*$", normalized, flags=re.IGNORECASE):
                continue
            if re.match(r"^#{1,6}\s*经验库[：:].*$", normalized):
                continue
            if re.match(r"^[-*]\s*来源:\s*.*$", normalized):
                continue
            if re.match(r"^[-*]\s*经验库[：:].*$", normalized):
                continue
            if "match_score=" in normalized:
                continue
            if re.search(r"/\s*partition_\d+\s*/", normalized):
                continue

            cleaned_lines.append(line)

        cleaned = "\n".join(cleaned_lines)
        return re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    def _ensure_structured_final_answer(self, answer: str, context: WorkflowContext) -> str:
        text = self._strip_duplicate_evidence_section(answer)
        text = self._strip_source_trace_lines(text)
        if not text:
            text = self._fallback_stage_output("qa_reply", context)
        return self._strip_source_trace_lines(text)

    def _extract_path_methods(self, path_item: dict[str, Any]) -> str:
        raw_methods = (
            path_item.get("method_sequence")
            or path_item.get("methods")
            or path_item.get("method_calls")
            or path_item.get("call_chain")
            or []
        )
        method_names: list[str] = []
        if isinstance(raw_methods, list):
            for item in raw_methods:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("method_name") or "").strip()
                else:
                    name = str(item or "").strip()
                if name:
                    method_names.append(name)
        elif isinstance(raw_methods, str):
            method_names = [seg.strip() for seg in raw_methods.split("->") if seg.strip()]

        if not method_names:
            semantics = path_item.get("semantics") or {}
            if isinstance(semantics, dict):
                kws = semantics.get("keywords") or []
                if isinstance(kws, list):
                    method_names = [str(k).strip() for k in kws if str(k).strip()]

        if not method_names:
            return ""
        return " -> ".join(method_names[:6])

    def _normalize_stage_output(self, stage: str, content: str) -> str:
        text = _strip_thinking_block(str(content or ""))
        if not text:
            return text

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if stage == "requirement_analysis":
            return "\n".join(lines[:5])[:500]
        if stage == "experience_retrieval":
            return "\n".join(lines[:24])[:1800]
        if stage == "per_project_extraction":
            return "\n".join(lines[:100])[:7000]
        if stage == "cross_project_comparison":
            return "\n".join(lines[:70])[:4500]
        if stage == "qa_advisor":
            return "\n".join(lines[:24])[:2200]
        if stage == "qa_evidence_reasoning":
            return "\n".join(lines[:120])[:7000]
        if stage == "qa_reply":
            return "\n".join(lines[:220])[:12000]
        return text[:1200]


def _chunk_text(text: str, chunk_size: int = 80) -> list[str]:
    body = str(text or "")
    if not body:
        return [""]
    return [body[i : i + chunk_size] for i in range(0, len(body), chunk_size)]


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"
