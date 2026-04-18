from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SkillCard:
    skill_id: str
    name: str
    what: str
    how: str
    example: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    workflow_stage: str = "general"

    @staticmethod
    def _to_str_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        return []

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SkillCard":
        return cls(
            skill_id=str(payload.get("skill_id") or ""),
            name=str(payload.get("name") or ""),
            what=str(payload.get("what") or ""),
            how=str(payload.get("how") or ""),
            example=str(payload.get("example") or ""),
            inputs=cls._to_str_list(payload.get("inputs")),
            outputs=cls._to_str_list(payload.get("outputs")),
            tags=cls._to_str_list(payload.get("tags")),
            workflow_stage=str(payload.get("workflow_stage") or "general"),
        )
