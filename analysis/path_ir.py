#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class PathIR:
    path_id: str
    run_id: str
    partition_id: str
    leaf_node: str
    function_chain: List[str] = field(default_factory=list)
    path_index: int = 0
    path_name: str = ""
    path_description: str = ""
    semantic_label: str = ""
    keywords: List[str] = field(default_factory=list)
    functional_domain: str = ""
    description: str = ""
    worthiness_score: float = 0.0
    worthiness_reasons: List[str] = field(default_factory=list)
    deep_analysis_status: str = "ready"
    cfg: Optional[Dict[str, Any]] = None
    dfg: Optional[Dict[str, Any]] = None
    input_info: Dict[str, Any] = field(default_factory=dict)
    output_info: Dict[str, Any] = field(default_factory=dict)
    cfg_dfg_explain_md: str = ""
    source_project_path: Optional[str] = None
    skip_reason: Optional[str] = None
    trigger_mode: str = "skip"
    llm_reasoning: str = ""
    model: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["path"] = list(self.function_chain)
        payload["semantics"] = {
            "semantic_label": self.semantic_label,
            "keywords": list(self.keywords),
            "functional_domain": self.functional_domain,
            "description": self.description,
        }
        return payload
