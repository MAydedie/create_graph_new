from __future__ import annotations

from typing import Any, Dict, List, Optional

from llm.agent.utils.question_detector import QuestionDetector


class ClarificationAdapter:
    STRUCTURED_REQUIREMENT_KEYS = (
        "goal",
        "target",
        "expected_output",
        "constraints",
    )

    @classmethod
    def assess(
        cls,
        user_query: str,
        *,
        clarification_context: Optional[Dict[str, Any]] = None,
        has_context: bool = False,
    ) -> Dict[str, Any]:
        normalized_query = cls._as_string(user_query)
        normalized_context = clarification_context if isinstance(clarification_context, dict) else {}
        clarification_payload = QuestionDetector.assess_clarification_need(
            normalized_query,
            has_context=bool(has_context),
            clarification_context=normalized_context,
        )
        return cls.normalize(
            clarification_payload,
            clarification_context=normalized_context,
        )

    @classmethod
    def normalize(
        cls,
        clarification_payload: Optional[Dict[str, Any]],
        *,
        clarification_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_payload = clarification_payload if isinstance(clarification_payload, dict) else {}
        normalized_context = clarification_context if isinstance(clarification_context, dict) else {}
        return {
            "route": cls._as_string(normalized_payload.get("route")),
            "task_mode": cls._as_string(normalized_payload.get("task_mode")),
            "confidence": cls._as_float(normalized_payload.get("confidence")),
            "reason": cls._as_string(normalized_payload.get("reason")),
            "missing_slots": cls._as_string_list(normalized_payload.get("missing_slots")),
            "inferred_intent": cls._as_string(normalized_payload.get("inferred_intent")),
            "structured_requirement": cls._build_structured_requirement(
                clarification_context=normalized_context,
                clarification_payload=normalized_payload,
            ),
            "original_clarification_payload": normalized_payload,
        }

    @classmethod
    def _build_structured_requirement(
        cls,
        *,
        clarification_context: Dict[str, Any],
        clarification_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "goal": cls._pick_string("goal", clarification_context, clarification_payload),
            "target": cls._pick_string("target", clarification_context, clarification_payload),
            "expected_output": cls._pick_string(
                "expected_output",
                clarification_context,
                clarification_payload,
                aliases=("expectedOutput",),
            ),
            "constraints": cls._pick_constraints(clarification_context, clarification_payload),
        }

    @classmethod
    def _pick_string(
        cls,
        field_name: str,
        clarification_context: Dict[str, Any],
        clarification_payload: Dict[str, Any],
        *,
        aliases: tuple[str, ...] = (),
    ) -> str:
        for source in cls._iter_sources(clarification_context, clarification_payload):
            for key in (field_name, *aliases):
                value = cls._as_string(source.get(key))
                if value:
                    return value
        return ""

    @classmethod
    def _pick_constraints(
        cls,
        clarification_context: Dict[str, Any],
        clarification_payload: Dict[str, Any],
    ) -> List[str]:
        for source in cls._iter_sources(clarification_context, clarification_payload):
            value = source.get("constraints")
            normalized = cls._as_string_list(value)
            if normalized:
                return normalized
            single_value = cls._as_string(value)
            if single_value:
                return [single_value]
        return []

    @classmethod
    def _iter_sources(
        cls,
        clarification_context: Dict[str, Any],
        clarification_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        sources: List[Dict[str, Any]] = []
        for candidate in (
            clarification_context,
            clarification_context.get("structured_requirement"),
            clarification_context.get("structuredRequirement"),
            clarification_payload.get("structured_requirement"),
            clarification_payload.get("structuredRequirement"),
        ):
            if isinstance(candidate, dict):
                sources.append(candidate)
        return sources

    @staticmethod
    def _as_string(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _as_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _as_string_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


def assess_clarification(
    user_query: str,
    *,
    clarification_context: Optional[Dict[str, Any]] = None,
    has_context: bool = False,
) -> Dict[str, Any]:
    return ClarificationAdapter.assess(
        user_query,
        clarification_context=clarification_context,
        has_context=has_context,
    )
