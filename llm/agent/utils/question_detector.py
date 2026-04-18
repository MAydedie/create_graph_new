"""
智能问题检测器

用于区分简单问答、明确任务和需要澄清的任务。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class QuestionDetector:
    """检测用户输入并评估是否需要澄清。"""

    QUESTION_KEYWORDS = [
        "什么", "为什么", "怎么", "如何", "哪个", "哪些", "谁", "哪里",
        "what", "why", "how", "which", "who", "where", "when",
        "是什么", "是谁", "能做什么", "可以做什么", "有什么功能",
        "你好", "hello", "hi", "介绍", "说明",
    ]

    TASK_KEYWORDS = [
        "创建", "生成", "修改", "删除", "添加", "更新", "实现", "编写",
        "测试", "运行", "执行", "部署", "重构", "优化", "修复", "改",
        "create", "generate", "modify", "delete", "add", "update",
        "implement", "write", "test", "run", "execute", "deploy",
        "refactor", "optimize", "fix", "debug",
    ]

    WRITE_NEW_CODE_KEYWORDS = [
        "新增", "新建", "写一个", "写一段", "做一个", "补一个功能", "加一个功能",
        "create", "generate", "new file", "new function", "write new", "build new",
    ]

    MODIFY_EXISTING_KEYWORDS = [
        "修改", "修复", "优化", "重构", "替换", "调整", "补丁", "改一下",
        "modify", "fix", "optimize", "refactor", "update", "patch", "change",
    ]

    TARGET_HINT_KEYWORDS = [
        "文件", "模块", "页面", "接口", "函数", "方法", "类", "组件", "路由", "服务",
        "file", "module", "page", "api", "function", "method", "class", "component", "route", "service",
    ]

    EXPECTATION_HINT_KEYWORDS = [
        "希望", "想要", "变成", "达到", "支持", "输出", "结果", "效果", "目标",
        "expect", "expected", "should", "want", "result", "support", "behavior", "goal",
    ]

    INDICATOR_HINT_KEYWORDS = [
        "性能", "速度", "延迟", "稳定", "稳定性", "安全", "可维护", "兼容", "容错", "边界",
        "风格", "测试", "日志", "指标", "约束", "优先", "精度", "可读性", "风险",
        "performance", "latency", "stability", "security", "maintainability", "compatibility",
        "test", "logging", "metric", "constraint", "priority", "accuracy", "readability", "risk",
    ]

    STRUCTURED_FIELDS = [
        {"id": "goal", "label": "你要完成什么目标"},
        {"id": "target", "label": "你想改哪个模块/文件/函数"},
        {"id": "expected_output", "label": "你希望最后变成什么样"},
        {"id": "constraints", "label": "是否有约束、指标或风格要求"},
    ]

    @classmethod
    def is_simple_question(cls, user_input: str) -> bool:
        user_input_lower = user_input.lower()
        has_question_keyword = any(keyword in user_input_lower for keyword in cls.QUESTION_KEYWORDS)
        has_task_keyword = any(keyword in user_input_lower for keyword in cls.TASK_KEYWORDS)
        is_short = len(user_input) < 100
        has_question_mark = "?" in user_input or "？" in user_input

        if has_task_keyword:
            return False
        if has_question_keyword or has_question_mark:
            return True
        if is_short and not has_task_keyword:
            return True
        return False

    @classmethod
    def analyze(cls, user_input: str) -> Dict[str, Any]:
        is_question = cls.is_simple_question(user_input)
        user_input_lower = user_input.lower()
        question_score = sum(1 for kw in cls.QUESTION_KEYWORDS if kw in user_input_lower)
        task_score = sum(1 for kw in cls.TASK_KEYWORDS if kw in user_input_lower)

        if is_question:
            confidence = min(0.5 + question_score * 0.1, 1.0)
            reason = "包含问答关键词" if question_score > 0 else "短文本且无任务关键词"
        else:
            confidence = min(0.5 + task_score * 0.1, 1.0)
            reason = "包含任务关键词" if task_score > 0 else "长文本或复杂请求"

        return {
            "is_question": is_question,
            "confidence": confidence,
            "reason": reason,
        }

    @classmethod
    def detect_task_mode(cls, user_input: str) -> str:
        user_input_lower = user_input.lower()
        write_score = sum(1 for kw in cls.WRITE_NEW_CODE_KEYWORDS if kw in user_input_lower)
        modify_score = sum(1 for kw in cls.MODIFY_EXISTING_KEYWORDS if kw in user_input_lower)
        if write_score > modify_score:
            return "write_new_code"
        return "modify_existing"

    @classmethod
    def assess_clarification_need(
        cls,
        user_input: str,
        *,
        has_context: bool = False,
        clarification_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        clarification_context = clarification_context or {}
        round_index = int(clarification_context.get("round") or 0)
        original_query = str(clarification_context.get("originalQuery") or user_input).strip()
        latest_user_reply = str(clarification_context.get("latestUserReply") or user_input).strip()
        selected_option_labels = cls._normalize_selected_option_labels(clarification_context.get("selectedOptionLabels"))
        combined_text = cls._merge_texts(original_query, latest_user_reply, selected_option_labels)

        analysis = cls.analyze(combined_text)
        task_mode = cls.detect_task_mode(combined_text)
        task_signal = cls._contains_any(combined_text, cls.TASK_KEYWORDS) or round_index > 0
        target_present = cls._has_target_hint(combined_text, has_context)
        expectation_present = cls._has_expectation_hint(combined_text)
        indicator_present = cls._has_indicator_hint(combined_text, selected_option_labels)

        inferred_intent = cls._build_inferred_intent(combined_text, task_mode)
        missing_slots: List[str] = []
        if not target_present:
            missing_slots.append("target")
        if not expectation_present:
            missing_slots.append("expected_output")
        if not indicator_present:
            missing_slots.append("constraints")

        if analysis.get("is_question") and not task_signal and round_index == 0:
            return {
                "route": "general_chat",
                "confidence": float(analysis.get("confidence") or 0.0),
                "reason": str(analysis.get("reason") or "命中问答路由"),
                "task_mode": None,
                "clarity_level": "general_chat",
                "inferred_intent": combined_text or original_query,
                "missing_slots": [],
            }

        if not task_signal:
            return cls._build_clarification_result(
                route="clarify",
                confidence=0.42,
                reason="缺少稳定任务意图，先做结构化澄清",
                task_mode=task_mode,
                clarity_level="very_ambiguous",
                inferred_intent=inferred_intent,
                missing_slots=["goal", "target", "expected_output", "constraints"],
                round_index=round_index,
                original_query=original_query,
                prompt=(
                    f"我推测你可能想处理一个代码任务，但现在还无法稳定判断具体目标。\n"
                    f"我当前理解的方向：{inferred_intent}\n"
                    "请按下面结构重新描述一次：1）要做什么；2）改哪里；3）期望结果；4）约束/指标。"
                ),
                options=cls._build_restatement_options(task_mode),
                allow_freeform=True,
                structured_fields=cls.STRUCTURED_FIELDS,
                terminal=round_index >= 1,
            )

        if not target_present:
            return cls._build_clarification_result(
                route="clarify",
                confidence=0.58,
                reason="任务方向已出现，但修改目标仍不明确",
                task_mode=task_mode,
                clarity_level="ambiguous",
                inferred_intent=inferred_intent,
                missing_slots=missing_slots,
                round_index=round_index,
                original_query=original_query,
                prompt=(
                    f"我理解你大概率想{inferred_intent}，但还缺少明确落点。\n"
                    "请优先告诉我是哪个模块/文件/函数，或者直接选一个更接近的方向。"
                ),
                options=cls._build_target_options(task_mode),
                allow_freeform=True,
                structured_fields=cls.STRUCTURED_FIELDS[:3],
                terminal=round_index >= 1,
            )

        if not expectation_present:
            return cls._build_clarification_result(
                route="clarify",
                confidence=0.67,
                reason="已定位到大致任务，但预期结果还不够明确",
                task_mode=task_mode,
                clarity_level="lightly_ambiguous",
                inferred_intent=inferred_intent,
                missing_slots=missing_slots,
                round_index=round_index,
                original_query=original_query,
                prompt=(
                    f"我基本理解你想{inferred_intent}。\n"
                    "请确认你更接近哪种结果，或者直接补充你自己的预期效果。"
                ),
                options=cls._build_expectation_options(task_mode),
                allow_freeform=True,
                structured_fields=cls.STRUCTURED_FIELDS[1:4],
                terminal=round_index >= 1,
            )

        if not indicator_present:
            return cls._build_clarification_result(
                route="clarify",
                confidence=0.76,
                reason="主任务已理解，但还缺少指标、约束或实现框架偏好",
                task_mode=task_mode,
                clarity_level="missing_indicators",
                inferred_intent=inferred_intent,
                missing_slots=missing_slots,
                round_index=round_index,
                original_query=original_query,
                prompt=(
                    f"我已经理解你的主任务：{inferred_intent}。\n"
                    "在开始写代码前，请确认你更看重哪些指标或实现约束。"
                ),
                options=cls._build_indicator_options(task_mode),
                allow_freeform=True,
                structured_fields=[cls.STRUCTURED_FIELDS[-1]],
                terminal=round_index >= 1,
            )

        return {
            "route": task_mode,
            "confidence": max(float(analysis.get("confidence") or 0.0), 0.82),
            "reason": "任务目标、预期结果与约束已达到进入代码流的最低要求",
            "task_mode": task_mode,
            "clarity_level": "clear",
            "inferred_intent": inferred_intent,
            "missing_slots": [],
        }

    @classmethod
    def _contains_any(cls, text: str, keywords: List[str]) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in keywords)

    @classmethod
    def _has_target_hint(cls, text: str, has_context: bool) -> bool:
        lowered = text.lower()
        if has_context:
            return True
        if any(keyword in lowered for keyword in cls.TARGET_HINT_KEYWORDS):
            return True
        return any(token in text for token in ["/", "\\", ".py", ".ts", ".tsx", "::", "->", "#", "@"])

    @classmethod
    def _has_expectation_hint(cls, text: str) -> bool:
        lowered = text.lower()
        if any(keyword in lowered for keyword in cls.EXPECTATION_HINT_KEYWORDS):
            return True
        expectation_markers = ["让", "改成", "避免", "支持", "返回", "输出", "展示", "不要", "需要", "should", "so that"]
        return any(marker in lowered for marker in expectation_markers)

    @classmethod
    def _has_indicator_hint(cls, text: str, selected_option_labels: List[str]) -> bool:
        lowered = text.lower()
        if any(keyword in lowered for keyword in cls.INDICATOR_HINT_KEYWORDS):
            return True
        selected_text = " ".join(selected_option_labels).lower()
        return any(keyword in selected_text for keyword in cls.INDICATOR_HINT_KEYWORDS)

    @classmethod
    def _normalize_selected_option_labels(cls, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @classmethod
    def _merge_texts(cls, original_query: str, latest_user_reply: str, option_labels: List[str]) -> str:
        parts: List[str] = []
        for item in [original_query, latest_user_reply, *option_labels]:
            normalized = str(item).strip()
            if normalized and normalized not in parts:
                parts.append(normalized)
        return "\n".join(parts)

    @classmethod
    def _build_inferred_intent(cls, text: str, task_mode: str) -> str:
        concise = " ".join(part.strip() for part in text.splitlines() if part.strip())
        concise = concise[:160] if len(concise) > 160 else concise
        if concise:
            return concise
        return "基于现有代码补足明确需求" if task_mode == "write_new_code" else "围绕现有代码做定向修改"

    @classmethod
    def _build_clarification_result(
        cls,
        *,
        route: str,
        confidence: float,
        reason: str,
        task_mode: str,
        clarity_level: str,
        inferred_intent: str,
        missing_slots: List[str],
        round_index: int,
        original_query: str,
        prompt: str,
        options: List[Dict[str, str]],
        allow_freeform: bool,
        structured_fields: List[Dict[str, str]],
        terminal: bool,
    ) -> Dict[str, Any]:
        round_number = min(round_index + 1, 2)
        return {
            "route": route,
            "confidence": confidence,
            "reason": reason,
            "task_mode": task_mode,
            "clarity_level": clarity_level,
            "inferred_intent": inferred_intent,
            "missing_slots": missing_slots,
            "clarification": {
                "round": round_number,
                "maxRounds": 2,
                "clarityLevel": clarity_level,
                "inferredIntent": inferred_intent,
                "prompt": prompt,
                "options": options,
                "allowFreeform": allow_freeform,
                "structuredFields": structured_fields,
                "terminal": terminal,
                "originalQuery": original_query,
            },
        }

    @classmethod
    def _build_restatement_options(cls, task_mode: str) -> List[Dict[str, str]]:
        task_hint = "新写一段代码" if task_mode == "write_new_code" else "改现有代码"
        return [
            {"id": "restate_modify", "label": "我要改现有代码", "description": "直接说明要改哪个位置和预期结果", "promptFragment": "我想改现有代码，目标位置是："},
            {"id": "restate_new", "label": "我要基于现有代码写新代码", "description": "说明要新增的功能和依附位置", "promptFragment": "我想基于现有代码写新代码，依附位置是："},
            {"id": "restate_free", "label": f"按结构化方式重述（当前更像{task_hint}）", "description": "按目标/位置/预期/约束四项补充", "promptFragment": "目标：\n位置：\n预期结果：\n约束/指标："},
        ]

    @classmethod
    def _build_target_options(cls, task_mode: str) -> List[Dict[str, str]]:
        base = "新增功能依附位置" if task_mode == "write_new_code" else "修改位置"
        return [
            {"id": "target_file", "label": "按文件定位", "description": "直接给文件路径或文件名", "promptFragment": f"{base}：文件 "},
            {"id": "target_symbol", "label": "按函数/类定位", "description": "直接给函数名、类名或接口名", "promptFragment": f"{base}：函数/类 "},
            {"id": "target_module", "label": "按模块/页面定位", "description": "给模块名、页面名或接口域", "promptFragment": f"{base}：模块/页面 "},
        ]

    @classmethod
    def _build_expectation_options(cls, task_mode: str) -> List[Dict[str, str]]:
        if task_mode == "write_new_code":
            return [
                {"id": "expect_feature", "label": "补一个完整功能", "description": "需要直接给可复制的新逻辑", "promptFragment": "预期结果：补一个完整功能，表现为："},
                {"id": "expect_extension", "label": "在现有流程上扩展一步", "description": "保持原结构，仅新增必要逻辑", "promptFragment": "预期结果：在现有流程上扩展一步，具体是："},
                {"id": "expect_scaffold", "label": "先给可落地骨架", "description": "优先给接口/类/函数骨架与插入点", "promptFragment": "预期结果：先给可落地骨架，重点是："},
            ]
        return [
            {"id": "expect_fix", "label": "修复现有问题", "description": "以 bug 修复或逻辑纠正为主", "promptFragment": "预期结果：修复的问题是："},
            {"id": "expect_optimize", "label": "优化现有实现", "description": "不改大结构，提升效果或质量", "promptFragment": "预期结果：优化后的效果是："},
            {"id": "expect_refine", "label": "做最小改动增强", "description": "在保持现有结构下补能力", "promptFragment": "预期结果：在最小改动下增强："},
        ]

    @classmethod
    def _build_indicator_options(cls, task_mode: str) -> List[Dict[str, str]]:
        if task_mode == "write_new_code":
            return [
                {"id": "indicator_minimal", "label": "最小侵入", "description": "优先保持现有结构与调用方式", "promptFragment": "约束/指标：最小侵入，尽量复用现有结构。"},
                {"id": "indicator_quality", "label": "优先可维护性", "description": "结构清晰、易扩展、便于后续修改", "promptFragment": "约束/指标：优先可维护性和后续扩展。"},
                {"id": "indicator_speed", "label": "优先实现速度", "description": "先给能落地的直接方案", "promptFragment": "约束/指标：优先快速落地，先给最直接可用方案。"},
            ]
        return [
            {"id": "indicator_safe", "label": "优先稳定性", "description": "尽量减少副作用和回归风险", "promptFragment": "约束/指标：优先稳定性，降低回归风险。"},
            {"id": "indicator_perf", "label": "优先性能/效率", "description": "更看重延迟、耗时或资源消耗", "promptFragment": "约束/指标：优先性能和执行效率。"},
            {"id": "indicator_readable", "label": "优先可读性", "description": "更看重结构清晰与可维护性", "promptFragment": "约束/指标：优先可读性和可维护性。"},
        ]
