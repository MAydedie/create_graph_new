from __future__ import annotations

import importlib
import re
from typing import Any


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            normalized = _stringify(item)
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result
    return []


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_\-]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "skill"


def _maybe_skill_model(payload: dict[str, Any]) -> Any:
    try:
        module = importlib.import_module("skill_callchain_v2.models")
        model_cls = getattr(module, "SkillCardV2", None)
    except Exception:
        model_cls = None
    if model_cls is None:
        return payload
    try:
        return model_cls(**payload)
    except Exception:
        return payload


def _iter_partition_summaries(contract_payload: dict[str, Any]) -> list[dict[str, Any]]:
    adapters = contract_payload.get("adapters") or {}
    summaries = adapters.get("partition_summaries") or []
    result: list[dict[str, Any]] = []
    for item in summaries:
        if isinstance(item, dict):
            result.append(item)
    result.sort(key=lambda item: (_stringify(item.get("partition_id")), _stringify(item.get("name"))))
    return result


def _derive_tags(summary: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    name = _stringify(summary.get("name"))
    for token in re.split(r"[^\w\u4e00-\u9fff]+", name):
        normalized = token.strip().lower()
        if normalized and normalized not in tags:
            tags.append(normalized)

    analysis_status = _stringify(summary.get("analysis_status"))
    selection_policy = _stringify(summary.get("selection_policy"))
    for flag_name in ("has_cfg", "has_dfg", "has_io"):
        if summary.get(flag_name):
            tags.append(flag_name)
    if analysis_status:
        tags.append(analysis_status)
    if selection_policy:
        tags.append(selection_policy)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag and tag not in seen:
            seen.add(tag)
            deduped.append(tag)
    return deduped


def _build_skill_payload(summary: dict[str, Any]) -> dict[str, Any]:
    partition_id = _stringify(summary.get("partition_id"))
    name = _stringify(summary.get("name")) or partition_id or "Unnamed Partition"
    methods = _string_list(summary.get("methods"))
    skill_id = f"skill::{partition_id or _slugify(name)}"

    partition_summary = {
        "path_count": int(summary.get("path_count") or 0),
        "rich_path_count": int(summary.get("rich_path_count") or 0),
        "available_path_count": int(summary.get("available_path_count") or 0),
        "entry_point_count": int(summary.get("entry_point_count") or 0),
        "process_count": int(summary.get("process_count") or 0),
        "community_count": int(summary.get("community_count") or 0),
        "analysis_status": _stringify(summary.get("analysis_status")),
        "selection_policy": _stringify(summary.get("selection_policy")),
        "has_cfg": bool(summary.get("has_cfg")),
        "has_dfg": bool(summary.get("has_dfg")),
        "has_io": bool(summary.get("has_io")),
    }
    quality = _build_quality_flags(partition_summary)
    concise_summary = _build_concise_summary(name, methods, partition_summary)
    concise_what = _build_concise_what(name, methods, _stringify(summary.get("description")))
    concise_how = _build_concise_how(name, partition_summary)
    concise_description = _build_concise_description(name, partition_summary)

    return {
        "skill_id": skill_id,
        "partition_id": partition_id,
        "partition_name": name,
        "name": name,
        "summary": concise_summary,
        "what": concise_what,
        "when_to_use": f"当需求命中分区 {name} 或其相近功能时使用。" if name else "当需求命中该功能分区时使用。",
        "how": concise_how,
        "caution": [
            "优先使用轻量 partition summary，不直接把完整 hierarchy_result 送入下游 prompt。"
        ],
        "description": concise_description,
        "methods": methods,
        "tags": _derive_tags(summary),
        "source_refs": [partition_id] if partition_id else [],
        "path_refs": [],
        "code_refs": [],
        "inputs": ["结构化任务", "phase6 partition summary"],
        "outputs": ["技能候选", "路径证据", "源码证据"],
        "path_evidence": [],
        "code_evidence": [],
        "evidence_summary": {
            "path_count": 0,
            "code_ref_count": 0,
            "file_count": 0,
        },
        "partition_summary": partition_summary,
        "quality": quality,
        "usable_for_matching": bool(quality.get("usable_for_matching", True)),
    }


def _build_concise_summary(name: str, methods: list[str], partition_summary: dict[str, Any]) -> str:
    method_count = len(methods)
    path_count = int(partition_summary.get("path_count") or 0)
    analysis_status = _stringify(partition_summary.get("analysis_status")) or "unknown"
    return f"聚焦{name}能力，含{method_count}个候选方法与{path_count}条路径证据（状态:{analysis_status}）。"


def _build_concise_what(name: str, methods: list[str], partition_description: str) -> str:
    if partition_description:
        return f"该经验库代表功能分区“{name}”，核心能力：{partition_description}"
    top_methods = methods[:3]
    if top_methods:
        return f"围绕{name}分区执行调用链定位，优先关注：{', '.join(top_methods)}。"
    return f"围绕{name}分区执行调用链定位，输出可二次检索的符号线索。"


def _build_concise_how(name: str, partition_summary: dict[str, Any]) -> str:
    has_cfg = bool(partition_summary.get("has_cfg"))
    has_dfg = bool(partition_summary.get("has_dfg"))
    has_io = bool(partition_summary.get("has_io"))
    constraints: list[str] = []
    if has_cfg:
        constraints.append("CFG")
    if has_dfg:
        constraints.append("DFG")
    if has_io:
        constraints.append("输入输出")
    constraint_text = "+".join(constraints) if constraints else "基础路径"
    return (
        f"先把需求映射到{name}分区调用链，再依据{constraint_text}证据补全中间处理节点，"
        "输出可直接进入分析/设计阶段的过程说明。"
    )


def _build_concise_description(name: str, partition_summary: dict[str, Any]) -> str:
    has_io = bool(partition_summary.get("has_io"))
    has_cfg = bool(partition_summary.get("has_cfg"))
    has_dfg = bool(partition_summary.get("has_dfg"))
    signals = [
        "IO" if has_io else "",
        "CFG" if has_cfg else "",
        "DFG" if has_dfg else "",
    ]
    signal_text = "+".join([item for item in signals if item]) or "基础路径"
    return f"该skill用于{name}的调用链驱动检索，证据形态: {signal_text}。"


def _build_quality_flags(partition_summary: dict[str, Any]) -> dict[str, Any]:
    analysis_status = _stringify(partition_summary.get("analysis_status")).lower()
    path_count = int(partition_summary.get("path_count") or 0)
    rich_path_count = int(partition_summary.get("rich_path_count") or 0)
    available_path_count = int(partition_summary.get("available_path_count") or 0)
    degraded = analysis_status in {"partial_timeout", "timeout", "fallback", "lightweight_fallback"}
    low_signal = rich_path_count == 0 and path_count <= 1 and available_path_count <= 1
    usable_for_matching = not (degraded and low_signal)

    reasons: list[str] = []
    if degraded:
        reasons.append(f"analysis_status={analysis_status}")
    if low_signal:
        reasons.append("path_signal_low")
    if not reasons:
        reasons.append("quality_ok")

    return {
        "usable_for_matching": usable_for_matching,
        "is_degraded": degraded,
        "is_low_signal": low_signal,
        "reasons": reasons,
    }


def build_skills_from_partitions(contract_payload: dict[str, Any]) -> list[Any]:
    skills: list[Any] = []
    for summary in _iter_partition_summaries(contract_payload):
        payload = _build_skill_payload(summary)
        skill = _maybe_skill_model(payload)
        skills.append(skill)
    return skills
