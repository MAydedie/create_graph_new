from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_optional_int(value: Any) -> Optional[int]:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


@dataclass
class PathEvidence:
    partition_id: str = ""
    partition_name: str = ""
    path_id: str = ""
    path_name: str = ""
    path_description: str = ""
    function_chain: List[str] = field(default_factory=list)
    leaf_node: str = ""
    worthiness_score: float = 0.0
    worthiness_reasons: List[str] = field(default_factory=list)
    deep_analysis_status: str = ""
    selection_policy: str = ""
    summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Optional[Dict[str, Any]]) -> "PathEvidence":
        normalized = payload if isinstance(payload, dict) else {}
        return cls(
            partition_id=_as_str(normalized.get("partition_id")),
            partition_name=_as_str(normalized.get("partition_name")),
            path_id=_as_str(normalized.get("path_id")),
            path_name=_as_str(normalized.get("path_name")),
            path_description=_as_str(normalized.get("path_description")),
            function_chain=_as_str_list(normalized.get("function_chain") or normalized.get("path")),
            leaf_node=_as_str(normalized.get("leaf_node")),
            worthiness_score=_as_float(normalized.get("worthiness_score")),
            worthiness_reasons=_as_str_list(normalized.get("worthiness_reasons")),
            deep_analysis_status=_as_str(normalized.get("deep_analysis_status")),
            selection_policy=_as_str(normalized.get("selection_policy")),
            summary=_as_str(normalized.get("summary")),
            metadata=dict(normalized.get("metadata") or {}),
        )


@dataclass
class CodeEvidence:
    file_path: str = ""
    class_name: str = ""
    method_signature: str = ""
    symbol: str = ""
    snippet_preview: str = ""
    language: str = ""
    symbol_kind: str = ""
    kind: str = ""
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    line: Optional[int] = None
    partition_id: str = ""
    path_id: str = ""
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Optional[Dict[str, Any]]) -> "CodeEvidence":
        normalized = payload if isinstance(payload, dict) else {}
        return cls(
            file_path=_as_str(normalized.get("file_path")),
            class_name=_as_str(normalized.get("class_name")),
            method_signature=_as_str(normalized.get("method_signature") or normalized.get("symbol")),
            symbol=_as_str(normalized.get("symbol") or normalized.get("method_signature")),
            snippet_preview=_as_str(normalized.get("snippet_preview")),
            language=_as_str(normalized.get("language")),
            symbol_kind=_as_str(normalized.get("symbol_kind") or normalized.get("kind")),
            kind=_as_str(normalized.get("kind") or normalized.get("symbol_kind")),
            line_start=_as_optional_int(normalized.get("line_start") or normalized.get("line")),
            line_end=_as_optional_int(normalized.get("line_end")),
            line=_as_optional_int(normalized.get("line") or normalized.get("line_start")),
            partition_id=_as_str(normalized.get("partition_id")),
            path_id=_as_str(normalized.get("path_id")),
            source=_as_str(normalized.get("source")),
            metadata=dict(normalized.get("metadata") or {}),
        )


@dataclass
class SkillCardV2:
    skill_id: str
    name: str
    summary: str = ""
    what: str = ""
    when_to_use: str = ""
    how: str = ""
    caution: List[str] = field(default_factory=list)
    description: str = ""
    partition_id: str = ""
    partition_name: str = ""
    tags: List[str] = field(default_factory=list)
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    path_refs: List[str] = field(default_factory=list)
    code_refs: List[str] = field(default_factory=list)
    path_evidence: List[PathEvidence] = field(default_factory=list)
    code_evidence: List[CodeEvidence] = field(default_factory=list)
    evidence_summary: Dict[str, Any] = field(default_factory=dict)
    partition_summary: Dict[str, Any] = field(default_factory=dict)
    quality: Dict[str, Any] = field(default_factory=dict)
    usable_for_matching: bool = True
    method_call_chain: List[str] = field(default_factory=list)
    chain_explanation: List[str] = field(default_factory=list)
    approach_graph: List[Dict[str, Any]] = field(default_factory=list)
    source_locations: List[Dict[str, Any]] = field(default_factory=list)
    retrieval_hints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["path_evidence"] = [item.to_dict() for item in self.path_evidence]
        payload["code_evidence"] = [item.to_dict() for item in self.code_evidence]
        return payload

    @classmethod
    def from_dict(cls, payload: Optional[Dict[str, Any]]) -> "SkillCardV2":
        normalized = payload if isinstance(payload, dict) else {}
        return cls(
            skill_id=_as_str(normalized.get("skill_id")),
            name=_as_str(normalized.get("name")),
            summary=_as_str(normalized.get("summary")),
            what=_as_str(normalized.get("what")),
            when_to_use=_as_str(normalized.get("when_to_use")),
            how=_as_str(normalized.get("how")),
            caution=_as_str_list(normalized.get("caution")),
            description=_as_str(normalized.get("description")),
            partition_id=_as_str(normalized.get("partition_id")),
            partition_name=_as_str(normalized.get("partition_name")),
            tags=_as_str_list(normalized.get("tags")),
            inputs=_as_str_list(normalized.get("inputs")),
            outputs=_as_str_list(normalized.get("outputs")),
            methods=_as_str_list(normalized.get("methods")),
            source_refs=_as_str_list(normalized.get("source_refs")),
            path_refs=_as_str_list(normalized.get("path_refs")),
            code_refs=_as_str_list(normalized.get("code_refs")),
            path_evidence=[PathEvidence.from_dict(item) for item in normalized.get("path_evidence") or []],
            code_evidence=[CodeEvidence.from_dict(item) for item in normalized.get("code_evidence") or []],
            evidence_summary=dict(normalized.get("evidence_summary") or {}),
            partition_summary=dict(normalized.get("partition_summary") or {}),
            quality=dict(normalized.get("quality") or {}),
            usable_for_matching=bool(normalized.get("usable_for_matching", True)),
            method_call_chain=_as_str_list(normalized.get("method_call_chain")),
            chain_explanation=_as_str_list(normalized.get("chain_explanation")),
            approach_graph=list(normalized.get("approach_graph") or []),
            source_locations=list(normalized.get("source_locations") or []),
            retrieval_hints=dict(normalized.get("retrieval_hints") or {}),
            metadata=dict(normalized.get("metadata") or {}),
        )
