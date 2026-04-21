from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR.parent) not in sys.path:
    sys.path.insert(0, str(BASE_DIR.parent))

from advisor_consultant_lab import common as c
from advisor_consultant_lab import config as cfg


as_str = c.as_str
as_str_list = c.as_str_list
append_jsonl = c.append_jsonl
ensure_runtime = c.ensure_runtime
read_json = c.read_json
read_text = c.read_text
tokenize = c.tokenize
utc_now = c.utc_now
write_json = c.write_json

RUNTIME_DIR = cfg.RUNTIME_DIR
SKILLS_FILE = cfg.SKILLS_FILE
EXPERIENCE_PATHS_DIR = cfg.EXPERIENCE_PATHS_DIR
EXPERIENCE_SOURCE_MODE = cfg.EXPERIENCE_SOURCE_MODE
STEP1_MATCH_RESULT_FILE = cfg.STEP1_MATCH_RESULT_FILE
STEP1_MATCH_PROCESS_FILE = cfg.STEP1_MATCH_PROCESS_FILE
STAGE_TRACE_FILE = cfg.STAGE_TRACE_FILE
TASK_INPUT_FILE = cfg.TASK_INPUT_FILE
TOP_MATCH_COUNT = cfg.TOP_MATCH_COUNT

BROAD_QUERY_KEYWORDS = (
    "创建",
    "新项目",
    "改写",
    "改造",
    "扩展",
    "扩充",
    "端到端",
    "整体",
    "架构",
    "服务化",
    "统一训练",
    "多数据集",
)

SPECIFIC_QUERY_KEYWORDS = (
    "字段",
    "数据库",
    "写入",
    "更新",
    "失败",
    "报错",
    "接口",
    "事务",
    "rollback",
    "commit",
)


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _token_set_from_text(text: str) -> set[str]:
    tokens = tokenize(text)
    expanded: set[str] = set(tokens)
    for token in tokens:
        normalized = as_str(token)
        if not normalized:
            continue
        if not _contains_cjk(normalized) or len(normalized) < 4:
            continue
        # 中文长 token 切分成 2~3 字 n-gram，提升粒度匹配能力
        for ngram_size in (2, 3):
            for index in range(len(normalized) - ngram_size + 1):
                piece = normalized[index : index + ngram_size]
                if piece:
                    expanded.add(piece)
    return expanded


def _overlap_signal(requirement_tokens: set[str], text: str, *, boost: float = 1.0) -> dict[str, Any]:
    if not requirement_tokens:
        return {"score": 0.0, "hit_count": 0, "coverage": 0.0}
    candidate_tokens = _token_set_from_text(text)
    if not candidate_tokens:
        return {"score": 0.0, "hit_count": 0, "coverage": 0.0}
    overlap = requirement_tokens.intersection(candidate_tokens)
    hit_count = len(overlap)
    coverage = hit_count / max(len(requirement_tokens), 1)
    score = (hit_count + coverage) * boost
    return {"score": score, "hit_count": hit_count, "coverage": coverage}


def _overlap_score(requirement_tokens: set[str], text: str, *, boost: float = 1.0) -> float:
    return float(_overlap_signal(requirement_tokens, text, boost=boost).get("score", 0.0))


def _join_unique_text(chunks: list[str], *, limit: int = 120) -> str:
    result: list[str] = []
    seen: set[str] = set()
    for item in chunks:
        normalized = as_str(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return " ".join(result)


def _io_labels(path_payload: dict[str, Any], node_type: str) -> list[str]:
    io_graph = path_payload.get("io_graph") or {}
    labels: list[str] = []
    if isinstance(io_graph, dict):
        for node in io_graph.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            if as_str(node.get("type")) != node_type:
                continue
            label = as_str(node.get("label"))
            if label:
                labels.append(label)
    return labels


def _extract_inputs_outputs(path_payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    inputs = _io_labels(path_payload, "input")
    outputs = _io_labels(path_payload, "output")

    input_info = path_payload.get("input_info") or {}
    output_info = path_payload.get("output_info") or {}
    if isinstance(input_info, dict):
        inputs.extend([as_str(key) for key in input_info.keys() if as_str(key)])
    if isinstance(output_info, dict):
        outputs.extend([as_str(key) for key in output_info.keys() if as_str(key)])

    return as_str_list(inputs), as_str_list(outputs)


def _build_how_from_chain(function_chain: list[str], inputs: list[str], outputs: list[str]) -> str:
    if not function_chain:
        return "按经验库路径执行需求映射，并依据 CFG/DFG/输入输出约束完成分析。"

    lines: list[str] = []
    for index, module_name in enumerate(function_chain, start=1):
        prev_output = f"step_{index - 1}_output" if index > 1 else "需求输入"
        curr_output = outputs[0] if index == len(function_chain) and outputs else f"step_{index}_output"
        next_module = function_chain[index] if index < len(function_chain) else "END"
        lines.append(
            f"[{index}] 输入{prev_output} -> 进入{module_name}；执行模块处理；得到{curr_output}；下一步{next_module}。"
        )

    constraints: list[str] = ["CFG", "DFG", "输入输出"]
    constraints.extend(inputs[:2])
    constraints.extend(outputs[:2])
    return "；".join(lines) + f"；约束依据：{'、'.join(as_str_list(constraints)[:6])}。"


_SYMBOL_INDEX_CACHE: dict[str, dict[str, list[dict[str, Any]]]] = {}
_SOURCE_SCAN_EXCLUDE_SEGMENTS = {
    '__pycache__',
    '.git',
    '.idea',
    '.vscode',
    'node_modules',
    '.venv',
    'venv',
    'dist',
    'build',
}


def _normalize_symbol_variants(symbol: str) -> list[str]:
    text = as_str(symbol)
    if not text:
        return []

    text = text.replace('::', '.').replace('->', '.')
    text = re.sub(r'\([^)]*\)$', '', text).strip()
    text = text.strip('`"\' ')
    if not text:
        return []

    variants: list[str] = [text]
    if text.startswith('self.'):
        variants.append(text[5:])
    if '.' in text:
        variants.append(text.split('.')[-1])
    if ':' in text and '/' not in text and '\\\\' not in text:
        variants.append(text.split(':')[-1])

    result: list[str] = []
    seen: set[str] = set()
    for item in variants:
        normalized = as_str(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _register_symbol_index_entry(index: dict[str, list[dict[str, Any]]], symbol: str, file_path: str, line: int | None = None) -> None:
    normalized_symbol = as_str(symbol)
    normalized_path = as_str(file_path)
    if not normalized_symbol or not normalized_path:
        return

    entry: dict[str, Any] = {
        'symbol': normalized_symbol,
        'file_path': normalized_path,
    }
    if isinstance(line, int) and line > 0:
        entry['line'] = line

    for variant in _normalize_symbol_variants(normalized_symbol):
        key = variant.lower()
        bucket = index.setdefault(key, [])
        exists = any(
            as_str(item.get('file_path')) == normalized_path
            and int(item.get('line') or 0) == int(entry.get('line') or 0)
            for item in bucket
            if isinstance(item, dict)
        )
        if not exists:
            bucket.append(dict(entry))


def _build_python_symbol_index(project_path: str) -> dict[str, list[dict[str, Any]]]:
    root = Path(as_str(project_path))
    if not root.exists() or not root.is_dir():
        return {}

    cache_key = str(root.resolve())
    cached = _SYMBOL_INDEX_CACHE.get(cache_key)
    if isinstance(cached, dict):
        return cached

    index: dict[str, list[dict[str, Any]]] = {}

    for file_path in root.rglob('*.py'):
        if not file_path.is_file():
            continue
        if any(part in _SOURCE_SCAN_EXCLUDE_SEGMENTS or part.startswith('.') for part in file_path.parts):
            continue

        try:
            source = file_path.read_text(encoding='utf-8')
        except Exception:
            continue

        try:
            tree = ast.parse(source)
        except Exception:
            continue

        try:
            normalized_path = str(file_path.resolve().relative_to(root.resolve())).replace('\\\\', '/')
        except Exception:
            normalized_path = str(file_path)

        def walk(node: ast.AST, class_stack: list[str]) -> None:
            if isinstance(node, ast.ClassDef):
                class_name = as_str(node.name)
                class_line = int(getattr(node, 'lineno', 0) or 0)
                if class_name:
                    _register_symbol_index_entry(index, class_name, normalized_path, class_line)
                next_stack = class_stack + [class_name] if class_name else list(class_stack)
                for child in node.body:
                    walk(child, next_stack)
                return

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_name = as_str(node.name)
                func_line = int(getattr(node, 'lineno', 0) or 0)
                if func_name:
                    _register_symbol_index_entry(index, func_name, normalized_path, func_line)
                    _register_symbol_index_entry(index, f'self.{func_name}', normalized_path, func_line)
                    if class_stack:
                        full_symbol = f"{class_stack[-1]}.{func_name}"
                        _register_symbol_index_entry(index, full_symbol, normalized_path, func_line)
                for child in node.body:
                    walk(child, class_stack)
                return

            for child in ast.iter_child_nodes(node):
                walk(child, class_stack)

        walk(tree, [])

    _SYMBOL_INDEX_CACHE[cache_key] = index
    return index


def _resolve_symbol_location(symbol: str, project_path: str) -> dict[str, Any]:
    variants = _normalize_symbol_variants(symbol)
    if not variants:
        return {}

    symbol_index = _build_python_symbol_index(project_path)
    if not symbol_index:
        return {}

    for variant in variants:
        matches = symbol_index.get(variant.lower()) or []
        if matches:
            first = matches[0]
            return first if isinstance(first, dict) else {}

    for variant in variants:
        lowered = variant.lower()
        for key, values in symbol_index.items():
            if key.endswith(f'.{lowered}') or lowered.endswith(f'.{key}'):
                if values:
                    first = values[0]
                    if isinstance(first, dict):
                        return first
    return {}


def _build_source_locations(path_payload: dict[str, Any], function_chain: list[str], project_path: str) -> list[dict[str, Any]]:
    cfg_payload = path_payload.get('cfg') or {}
    nodes = cfg_payload.get('nodes') if isinstance(cfg_payload, dict) else {}

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append_symbol(method_name: str, line_hint: Any = None) -> None:
        normalized = as_str(method_name)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)

        resolved = _resolve_symbol_location(normalized, project_path)
        item: dict[str, Any] = {
            'file_path': as_str(resolved.get('file_path')),
            'symbol': as_str(resolved.get('symbol')) or normalized,
        }

        resolved_line = resolved.get('line')
        if isinstance(resolved_line, int) and resolved_line > 0:
            item['line'] = resolved_line
        elif isinstance(line_hint, int) and line_hint > 0:
            item['line'] = int(line_hint)

        results.append(item)

    if isinstance(nodes, dict):
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            append_symbol(as_str(node.get('method')), node.get('line_number'))
            if len(results) >= 12:
                break

    if not results:
        for method_name in function_chain[:12]:
            append_symbol(method_name)

    return results


def _graph_summary(graph_payload: Any) -> dict[str, Any]:
    if not isinstance(graph_payload, dict):
        return {"exists": False, "node_count": 0, "edge_count": 0}

    nodes = graph_payload.get("nodes") or []
    edges = graph_payload.get("edges") or []

    if isinstance(nodes, dict):
        node_count = len(nodes.keys())
    elif isinstance(nodes, list):
        node_count = len(nodes)
    else:
        node_count = 0

    if isinstance(edges, dict):
        edge_count = len(edges.keys())
    elif isinstance(edges, list):
        edge_count = len(edges)
    else:
        edge_count = 0

    return {
        "exists": bool(node_count or edge_count),
        "node_count": node_count,
        "edge_count": edge_count,
    }


def _build_structured_constraints_from_path(path_payload: dict[str, Any], inputs: list[str], outputs: list[str]) -> dict[str, Any]:
    cfg_payload = path_payload.get("cfg") if isinstance(path_payload.get("cfg"), dict) else {}
    dfg_payload = path_payload.get("dfg") if isinstance(path_payload.get("dfg"), dict) else {}
    io_graph_payload = path_payload.get("io_graph") if isinstance(path_payload.get("io_graph"), dict) else {}
    input_info = path_payload.get("input_info") if isinstance(path_payload.get("input_info"), dict) else {}
    output_info = path_payload.get("output_info") if isinstance(path_payload.get("output_info"), dict) else {}
    explain_markdown = as_str(path_payload.get("cfg_dfg_explain_md"))

    cfg_summary = _graph_summary(cfg_payload)
    dfg_summary = _graph_summary(dfg_payload)
    io_summary = _graph_summary(io_graph_payload)
    input_info_keys = as_str_list(list(input_info.keys())) if isinstance(input_info, dict) else []
    output_info_keys = as_str_list(list(output_info.keys())) if isinstance(output_info, dict) else []

    constraint_types: list[str] = []
    if cfg_summary["exists"]:
        constraint_types.append("cfg")
    if dfg_summary["exists"]:
        constraint_types.append("dfg")
    if io_summary["exists"]:
        constraint_types.append("io_graph")
    if input_info:
        constraint_types.append("input_info")
    if output_info:
        constraint_types.append("output_info")
    if explain_markdown:
        constraint_types.append("constraint_explain")

    return {
        "version": "constraints.v1",
        "types": as_str_list(constraint_types),
        "cfg": {
            "summary": cfg_summary,
            "input_info_keys": input_info_keys,
            "output_info_keys": output_info_keys,
        },
        "dfg": {
            "summary": dfg_summary,
        },
        "io_graph": {
            "summary": io_summary,
            "inputs": inputs,
            "outputs": outputs,
        },
        "input_info": input_info,
        "output_info": output_info,
        "constraint_explain": {
            "exists": bool(explain_markdown),
            "markdown": explain_markdown,
        },
    }


def _build_structured_constraints_from_skill(skill: dict[str, Any]) -> dict[str, Any]:
    if isinstance(skill.get("constraints_structured"), dict):
        return skill["constraints_structured"]

    inputs = as_str_list(skill.get("inputs"))
    outputs = as_str_list(skill.get("outputs"))
    partition_summary = skill.get("partition_summary") or {}
    has_cfg = bool(partition_summary.get("has_cfg"))
    has_dfg = bool(partition_summary.get("has_dfg"))
    has_io = bool(partition_summary.get("has_io")) or bool(inputs) or bool(outputs)
    types: list[str] = []
    if has_cfg:
        types.append("cfg")
    if has_dfg:
        types.append("dfg")
    if has_io:
        types.append("io_graph")

    return {
        "version": "constraints.v1",
        "types": as_str_list(types),
        "cfg": {"summary": {"exists": has_cfg, "node_count": 0, "edge_count": 0}},
        "dfg": {"summary": {"exists": has_dfg, "node_count": 0, "edge_count": 0}},
        "io_graph": {
            "summary": {"exists": has_io, "node_count": 0, "edge_count": 0},
            "inputs": inputs,
            "outputs": outputs,
        },
        "input_info": {},
        "output_info": {},
        "constraint_explain": {"exists": False, "markdown": ""},
    }


def _path_to_skill(
    project_name: str,
    project_path: str,
    partition_id: str,
    partition_name: str,
    path_payload: dict[str, Any],
    path_index: int,
) -> dict[str, Any]:
    function_chain = as_str_list(path_payload.get("function_chain") or path_payload.get("path"))
    path_name = as_str(path_payload.get("path_name")) or f"路径{path_index + 1}"
    path_description = as_str(path_payload.get("path_description"))
    inputs, outputs = _extract_inputs_outputs(path_payload)
    has_cfg = bool(path_payload.get("cfg"))
    has_dfg = bool(path_payload.get("dfg"))
    has_io = bool(path_payload.get("io_graph")) or bool(inputs) or bool(outputs)

    what = f"该经验库来自项目{project_name}，功能分区“{partition_name}”，路径“{path_name}”"
    if path_description:
        what = f"{what}，能力描述：{path_description}"

    how = _build_how_from_chain(function_chain, inputs, outputs)
    source_locations = _build_source_locations(path_payload, function_chain, project_path)
    constraints_structured = _build_structured_constraints_from_path(path_payload, inputs, outputs)

    return {
        "skill_id": f"experience::{project_name}::{partition_id}::path_{path_index}",
        "partition_id": partition_id,
        "partition_name": partition_name,
        "path_name": path_name,
        "name": f"{project_name}:{partition_id}:{path_name}",
        "summary": path_description or f"{partition_name} 的经验路径 {path_name}",
        "what": what,
        "when_to_use": f"当需求落在 {project_name}/{partition_name}/{path_name} 场景时使用。",
        "how": how,
        "caution": ["优先复用经验库中的 CFG/DFG/IO 证据，不直接跳过中间路径步骤。"],
        "description": path_description,
        "tags": ["experience_store", project_name, partition_name, path_name],
        "inputs": inputs,
        "outputs": outputs,
        "methods": function_chain,
        "source_refs": [project_name, partition_id, as_str(path_payload.get("leaf_node"))],
        "path_refs": [f"{project_name}:{partition_id}:path_{path_index}"],
        "code_refs": function_chain[:24],
        "method_call_chain": function_chain[:24],
        "source_locations": source_locations,
        "evidence_summary": {
            "path_count": 1,
            "code_ref_count": len(function_chain),
            "file_count": 0,
        },
        "partition_summary": {
            "has_cfg": has_cfg,
            "has_dfg": has_dfg,
            "has_io": has_io,
        },
        "constraints_structured": constraints_structured,
        "project_name": project_name,
        "project_path": project_path,
        "usable_for_matching": True,
    }


def _build_project_profiles_from_skills(skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    project_map: dict[str, dict[str, Any]] = {}

    for skill in skills:
        project_name = as_str(skill.get("project_name")) or "unknown_project"
        project_path = as_str(skill.get("project_path"))
        partition_id = as_str(skill.get("partition_id")) or "unknown_partition"
        partition_name = as_str(skill.get("partition_name")) or partition_id
        skill_id = as_str(skill.get("skill_id"))

        project_key = f"{project_name}::{project_path}"
        project_profile = project_map.setdefault(
            project_key,
            {
                "project_name": project_name,
                "project_path": project_path,
                "partition_profiles": {},
                "project_text_chunks": [project_name],
                "path_count": 0,
            },
        )

        partition_profile = project_profile["partition_profiles"].setdefault(
            partition_id,
            {
                "partition_id": partition_id,
                "partition_name": partition_name,
                "path_count": 0,
                "skill_ids": [],
                "partition_text_chunks": [partition_name],
            },
        )

        partition_profile["path_count"] += 1
        project_profile["path_count"] += 1
        if skill_id:
            partition_profile["skill_ids"].append(skill_id)

        partition_profile["partition_text_chunks"].extend(
            [
                as_str(skill.get("summary")),
                as_str(skill.get("what")),
                as_str(skill.get("how")),
                " ".join(as_str_list(skill.get("methods"))[:10]),
            ]
        )
        project_profile["project_text_chunks"].extend(
            [
                partition_name,
                as_str(skill.get("summary")),
                as_str(skill.get("what")),
            ]
        )

    result: list[dict[str, Any]] = []
    for project_profile in project_map.values():
        partitions: list[dict[str, Any]] = []
        for partition_profile in project_profile["partition_profiles"].values():
            partitions.append(
                {
                    "partition_id": partition_profile["partition_id"],
                    "partition_name": partition_profile["partition_name"],
                    "path_count": partition_profile["path_count"],
                    "skill_ids": partition_profile["skill_ids"],
                    "partition_text": _join_unique_text(partition_profile["partition_text_chunks"]),
                }
            )

        result.append(
            {
                "project_name": project_profile["project_name"],
                "project_path": project_profile["project_path"],
                "path_count": project_profile["path_count"],
                "project_text": _join_unique_text(project_profile["project_text_chunks"]),
                "partition_profiles": sorted(
                    partitions,
                    key=lambda item: (-int(item.get("path_count", 0)), as_str(item.get("partition_id"))),
                ),
            }
        )

    result.sort(key=lambda item: (-int(item.get("path_count", 0)), as_str(item.get("project_name"))))
    return result


def _load_experience_skills_payload() -> dict[str, Any]:
    experience_files = sorted(EXPERIENCE_PATHS_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    skills: list[dict[str, Any]] = []

    for exp_file in experience_files:
        payload = read_json(exp_file)
        if not isinstance(payload, dict):
            continue

        project_name = as_str(payload.get("project_name")) or exp_file.stem
        project_path = as_str(payload.get("project_path"))
        partitions = payload.get("partitions") or []

        for partition in partitions:
            if not isinstance(partition, dict):
                continue
            partition_id = as_str(partition.get("partition_id")) or "unknown_partition"
            partition_name = as_str(partition.get("partition_name")) or partition_id
            paths = partition.get("paths") or []

            for path_index, path_payload in enumerate(paths):
                if not isinstance(path_payload, dict):
                    continue
                skills.append(
                    _path_to_skill(
                        project_name,
                        project_path,
                        partition_id,
                        partition_name,
                        path_payload,
                        path_index,
                    )
                )

    projects = _build_project_profiles_from_skills(skills)
    return {
        "source": "experience_paths",
        "experience_files": [str(path) for path in experience_files],
        "skills": skills,
        "projects": projects,
    }


def _load_candidate_skills_payload() -> dict[str, Any]:
    mode = as_str(EXPERIENCE_SOURCE_MODE) or "experience_first"
    if mode in {"experience_first", "experience_only"}:
        experience_payload = _load_experience_skills_payload()
        if experience_payload.get("skills"):
            return experience_payload
        if mode == "experience_only":
            raise ValueError(f"experience store has no available paths: {EXPERIENCE_PATHS_DIR}")

    skills_payload = read_json(SKILLS_FILE)
    if not isinstance(skills_payload, dict):
        raise ValueError(f"invalid skills payload: {SKILLS_FILE}")

    skills = [item for item in (skills_payload.get("skills") or []) if isinstance(item, dict)]
    skills_payload["skills"] = skills
    skills_payload.setdefault("source", "generated_skills")
    skills_payload.setdefault("experience_files", [])
    skills_payload["projects"] = _build_project_profiles_from_skills(skills)
    return skills_payload


def _skill_text(skill: dict[str, Any], fields: tuple[str, ...]) -> str:
    chunks: list[str] = []
    for field in fields:
        value = skill.get(field)
        if isinstance(value, list):
            chunks.extend(as_str_list(value))
        else:
            chunks.append(as_str(value))
    return " ".join(item for item in chunks if item)


def _build_constraints(skill: dict[str, Any]) -> list[str]:
    constraints: list[str] = []
    constraints.extend(as_str_list(skill.get("inputs")))
    constraints.extend(as_str_list(skill.get("outputs")))
    constraints.extend(as_str_list(skill.get("caution")))
    partition_summary = skill.get("partition_summary") or {}
    if bool(partition_summary.get("has_cfg")):
        constraints.append("需要 CFG 约束证据")
    if bool(partition_summary.get("has_dfg")):
        constraints.append("需要 DFG 约束证据")
    if bool(partition_summary.get("has_io")):
        constraints.append("需要输入输出约束")
    return as_str_list(constraints)


def _detect_query_profile(requirement: str) -> dict[str, Any]:
    requirement_text = as_str(requirement)
    broad_hits = [keyword for keyword in BROAD_QUERY_KEYWORDS if keyword in requirement_text]
    specific_hits = [keyword for keyword in SPECIFIC_QUERY_KEYWORDS if keyword in requirement_text]

    scope = "mixed"
    if broad_hits and len(broad_hits) >= len(specific_hits):
        scope = "broad"
    elif specific_hits and len(specific_hits) > len(broad_hits):
        scope = "specific"

    return {
        "scope": scope,
        "broad_hits": broad_hits,
        "specific_hits": specific_hits,
    }


def _parse_priority_libraries(raw_value: Any) -> list[str]:
    if isinstance(raw_value, list):
        items = [as_str(item) for item in raw_value]
    else:
        text = as_str(raw_value)
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            items = [as_str(item) for item in parsed]
        else:
            items = [as_str(item) for item in re.split(r"[,\n\r]+", text)]

    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = as_str(item)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _project_priority_boost(project_profile: dict[str, Any], prioritized_libraries: list[str]) -> dict[str, Any]:
    project_name = as_str(project_profile.get("project_name")).lower()
    project_path = as_str(project_profile.get("project_path")).lower()
    boost = 0.0
    matched_identifiers: list[str] = []

    for index, identifier in enumerate(prioritized_libraries):
        normalized = as_str(identifier).lower()
        if not normalized:
            continue
        if normalized == project_name or normalized in project_name or normalized == project_path or normalized in project_path:
            rank_boost = max(0.12, 0.6 - index * 0.12)
            boost += rank_boost
            matched_identifiers.append(identifier)

    return {
        "priority_boost": round(boost, 4),
        "matched_identifiers": matched_identifiers,
    }


def _score_project(requirement_tokens: set[str], project_profile: dict[str, Any], query_profile: dict[str, Any], prioritized_libraries: list[str]) -> dict[str, Any]:
    project_text = as_str(project_profile.get("project_text"))
    overlap = _overlap_signal(requirement_tokens, project_text, boost=1.8)

    partition_profiles = [item for item in (project_profile.get("partition_profiles") or []) if isinstance(item, dict)]
    partition_hit_count = 0
    for partition in partition_profiles:
        partition_text = as_str(partition.get("partition_text"))
        if _overlap_score(requirement_tokens, partition_text, boost=1.0) > 0:
            partition_hit_count += 1

    scope = as_str(query_profile.get("scope"))
    structure_bonus = min(partition_hit_count, 6) * (0.2 if scope == "broad" else 0.1)
    path_count = int(project_profile.get("path_count") or 0)
    path_scale_bonus = min(path_count, 50) * (0.008 if scope == "broad" else 0.002)

    project_name = as_str(project_profile.get("project_name"))
    name_signal = _overlap_signal(requirement_tokens, project_name, boost=1.3)
    priority_signal = _project_priority_boost(project_profile, prioritized_libraries)

    total_score = overlap["score"] + name_signal["score"] + float(priority_signal.get("priority_boost", 0.0))
    if overlap["hit_count"] > 0 or name_signal["hit_count"] > 0:
        total_score += structure_bonus + path_scale_bonus

    return {
        "project_score": round(total_score, 4),
        "project_overlap_hits": int(overlap.get("hit_count", 0)),
        "project_name_hits": int(name_signal.get("hit_count", 0)),
        "partition_hit_count": partition_hit_count,
        "path_count": path_count,
        "priority_boost": float(priority_signal.get("priority_boost", 0.0)),
        "priority_matches": priority_signal.get("matched_identifiers") or [],
    }


def _score_partition(requirement_tokens: set[str], partition_profile: dict[str, Any], query_profile: dict[str, Any]) -> dict[str, Any]:
    partition_text = as_str(partition_profile.get("partition_text"))
    signal = _overlap_signal(requirement_tokens, partition_text, boost=1.5)
    scope = as_str(query_profile.get("scope"))

    path_count = int(partition_profile.get("path_count") or 0)
    structure_bonus = min(path_count, 12) * (0.03 if scope == "broad" else 0.015)
    score = signal["score"]
    if signal["hit_count"] > 0:
        score += structure_bonus

    return {
        "partition_score": round(score, 4),
        "partition_overlap_hits": int(signal.get("hit_count", 0)),
        "path_count": path_count,
    }


def _agent_scoring_detail(requirement_tokens: set[str], skill: dict[str, Any]) -> dict[str, Any]:
    path_signal = _overlap_signal(
        requirement_tokens,
        _skill_text(skill, ("what", "summary", "method_call_chain", "path_refs")),
        boost=1.2,
    )
    semantic_signal = _overlap_signal(
        requirement_tokens,
        _skill_text(skill, ("name", "partition_name", "what", "how", "description", "tags")),
        boost=1.4,
    )
    code_signal = _overlap_signal(
        requirement_tokens,
        _skill_text(skill, ("methods", "code_refs", "source_refs")),
        boost=1.1,
    )

    total_hits = int(path_signal["hit_count"] + semantic_signal["hit_count"] + code_signal["hit_count"])
    alignment_factor = min(1.0, total_hits / 4.0)

    evidence_summary = skill.get("evidence_summary") or {}
    path_count = int(evidence_summary.get("path_count") or 0)
    code_ref_count = int(evidence_summary.get("code_ref_count") or 0)
    file_count = int(evidence_summary.get("file_count") or 0)

    path_score = float(path_signal["score"])
    semantic_score = float(semantic_signal["score"])
    code_score = float(code_signal["score"])

    # 修复旧逻辑的同分问题：只有发生语义/路径/代码命中时才加证据奖励
    if total_hits > 0:
        path_score += min(path_count, 3) * 0.25 * alignment_factor
        semantic_score += (0.2 if as_str(skill.get("what")) else 0.0) * alignment_factor
        semantic_score += (0.2 if as_str(skill.get("how")) else 0.0) * alignment_factor
        code_score += (min(code_ref_count, 12) * 0.04 + min(file_count, 4) * 0.08) * alignment_factor

    return {
        "scores": {
            "path_matcher": round(path_score, 4),
            "semantic_matcher": round(semantic_score, 4),
            "code_matcher": round(code_score, 4),
        },
        "total_hits": total_hits,
        "alignment_factor": round(alignment_factor, 4),
    }


def _select_top_candidates(path_candidates: list[dict[str, Any]], top_k: int, *, diversify: bool) -> list[dict[str, Any]]:
    if not diversify:
        return path_candidates[:top_k]

    selected: list[dict[str, Any]] = []
    selected_projects: set[str] = set()

    for candidate in path_candidates:
        project_name = as_str((candidate.get("skill") or {}).get("project_name"))
        if not project_name or project_name in selected_projects:
            continue
        selected.append(candidate)
        selected_projects.add(project_name)
        if len(selected) >= top_k:
            return selected

    for candidate in path_candidates:
        if candidate in selected:
            continue
        selected.append(candidate)
        if len(selected) >= top_k:
            break
    return selected


def _resolve_dynamic_match_count(
    path_candidates: list[dict[str, Any]],
    query_profile: dict[str, Any],
    *,
    base_min: int,
) -> dict[str, Any]:
    if not path_candidates:
        return {
            "resolved_top_k": 0,
            "scope": as_str(query_profile.get("scope")) or "mixed",
            "score_ratio": 1.0,
            "hard_min": 0,
            "hard_max": 0,
            "quality_band_count": 0,
            "note": "no candidates",
        }

    scope = as_str(query_profile.get("scope")) or "mixed"
    broad_hits = len(as_str_list(query_profile.get("broad_hits")))
    specific_hits = len(as_str_list(query_profile.get("specific_hits")))

    if scope == "broad":
        hard_min = max(base_min, 6)
        hard_max = 20
        score_ratio = 0.58
    elif scope == "specific":
        hard_min = max(2, min(base_min, 3))
        hard_max = 8
        score_ratio = 0.82
    else:
        hard_min = max(base_min, 4)
        hard_max = 12
        score_ratio = 0.68

    if broad_hits >= 3:
        hard_max += 4
        score_ratio -= 0.03
    if specific_hits >= 2 and scope != "broad":
        score_ratio += 0.03

    top_score = float((path_candidates[0] or {}).get("fused_score") or 0.0)
    threshold = top_score * score_ratio if top_score > 0 else 0.0

    quality_band = [
        item
        for item in path_candidates
        if float(item.get("fused_score", 0.0)) >= threshold and int(item.get("total_hits", 0)) > 0
    ]

    if not quality_band:
        quality_band = path_candidates[: max(base_min, 1)]

    resolved = len(quality_band)
    resolved = max(hard_min, resolved)
    resolved = min(hard_max, resolved)
    resolved = min(resolved, len(path_candidates))

    return {
        "resolved_top_k": resolved,
        "scope": scope,
        "score_ratio": round(score_ratio, 4),
        "hard_min": hard_min,
        "hard_max": hard_max,
        "quality_band_count": len(quality_band),
        "threshold": round(threshold, 4),
    }


def _build_report(
    requirement: str,
    skills_payload: dict[str, Any],
    *,
    run_id: str,
    question_id: str,
    prioritized_libraries: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    skills = [item for item in (skills_payload.get("skills") or []) if isinstance(item, dict)]
    projects = [item for item in (skills_payload.get("projects") or []) if isinstance(item, dict)]
    requirement_tokens = _token_set_from_text(requirement)
    query_profile = _detect_query_profile(requirement)

    skill_map = {as_str(item.get("skill_id")): item for item in skills if as_str(item.get("skill_id"))}

    project_candidates: list[dict[str, Any]] = []
    for project_profile in projects:
        score_detail = _score_project(requirement_tokens, project_profile, query_profile, prioritized_libraries)
        project_candidates.append(
            {
                "project": project_profile,
                "project_score": float(score_detail.get("project_score", 0.0)),
                "score_detail": score_detail,
            }
        )

    project_candidates.sort(
        key=lambda item: (-item["project_score"], -int((item.get("project") or {}).get("path_count") or 0), as_str((item.get("project") or {}).get("project_name")))
    )

    scope = as_str(query_profile.get("scope"))
    top_project_count = 3 if scope in {"broad", "mixed"} else 2
    selected_projects = project_candidates[:top_project_count]

    partition_candidates: list[dict[str, Any]] = []
    for project_item in selected_projects:
        project_profile = project_item["project"]
        project_score = float(project_item.get("project_score", 0.0))
        for partition_profile in project_profile.get("partition_profiles") or []:
            if not isinstance(partition_profile, dict):
                continue
            partition_score_detail = _score_partition(requirement_tokens, partition_profile, query_profile)
            partition_candidates.append(
                {
                    "project": project_profile,
                    "partition": partition_profile,
                    "project_score": project_score,
                    "partition_score": float(partition_score_detail.get("partition_score", 0.0)),
                    "score_detail": partition_score_detail,
                }
            )

    partition_candidates.sort(
        key=lambda item: (
            -float(item.get("project_score", 0.0)),
            -float(item.get("partition_score", 0.0)),
            -int((item.get("partition") or {}).get("path_count") or 0),
            as_str((item.get("partition") or {}).get("partition_id")),
        )
    )

    path_candidates: list[dict[str, Any]] = []
    for partition_item in partition_candidates:
        project_profile = partition_item["project"]
        partition_profile = partition_item["partition"]
        project_score = float(partition_item.get("project_score", 0.0))
        partition_score = float(partition_item.get("partition_score", 0.0))

        for skill_id in partition_profile.get("skill_ids") or []:
            skill = skill_map.get(as_str(skill_id))
            if not isinstance(skill, dict):
                continue

            scoring_detail = _agent_scoring_detail(requirement_tokens, skill)
            scores = scoring_detail["scores"]
            base_fused = float(scores["path_matcher"] + scores["semantic_matcher"] + scores["code_matcher"])

            combined = base_fused + project_score * 0.55 + partition_score * 0.65
            if scope == "broad" and int(scoring_detail.get("total_hits", 0)) == 0:
                combined *= 0.35

            path_candidates.append(
                {
                    "skill": skill,
                    "scores": scores,
                    "fused_score": round(combined, 4),
                    "base_fused_score": round(base_fused, 4),
                    "project_score": round(project_score, 4),
                    "partition_score": round(partition_score, 4),
                    "total_hits": int(scoring_detail.get("total_hits", 0)),
                    "alignment_factor": float(scoring_detail.get("alignment_factor", 0.0)),
                    "project_name": as_str(project_profile.get("project_name")),
                    "partition_id": as_str(partition_profile.get("partition_id")),
                }
            )

    path_candidates.sort(
        key=lambda item: (
            -float(item.get("fused_score", 0.0)),
            -float(item.get("project_score", 0.0)),
            -float(item.get("partition_score", 0.0)),
            -int(item.get("total_hits", 0)),
            as_str((item.get("skill") or {}).get("partition_id")),
        )
    )

    topk_plan = _resolve_dynamic_match_count(path_candidates, query_profile, base_min=max(TOP_MATCH_COUNT, 1))
    resolved_top_k = int(topk_plan.get("resolved_top_k") or 0)
    matched_rows = _select_top_candidates(path_candidates, resolved_top_k, diversify=(scope in {"broad", "mixed"}))

    matched_advisors: list[dict[str, Any]] = []
    for rank, row in enumerate(matched_rows, start=1):
        skill = row["skill"]
        matched_advisors.append(
            {
                "rank": rank,
                "advisor_id": as_str(skill.get("skill_id")),
                "partition_id": as_str(skill.get("partition_id")),
                "advisor_name": as_str(skill.get("name") or skill.get("partition_name")),
                "project_name": as_str(skill.get("project_name")),
                "project_path": as_str(skill.get("project_path")),
                "what": as_str(skill.get("what")),
                "how": as_str(skill.get("how")),
                "constraints": _build_constraints(skill),
                "constraints_structured": _build_structured_constraints_from_skill(skill),
                "agent_scores": row["scores"],
                "fused_score": row["fused_score"],
                "base_fused_score": row["base_fused_score"],
                "project_score": row["project_score"],
                "partition_score": row["partition_score"],
                "total_hits": row["total_hits"],
                "match_reason": as_str(skill.get("summary") or skill.get("description")),
                "method_call_chain": as_str_list(skill.get("method_call_chain"))[:6],
                "source_locations": skill.get("source_locations") or [],
                "path_refs": as_str_list(skill.get("path_refs")),
                "code_refs": as_str_list(skill.get("code_refs"))[:12],
            }
        )

    report = {
        "version": "advisor.lab.v2",
        "step": "match_advisors",
        "generated_at": utc_now(),
        "run_id": run_id,
        "question_id": question_id,
        "input_files": {
            "task_input": str(TASK_INPUT_FILE),
            "skills_source": as_str(skills_payload.get("source")) or "generated_skills",
            "skills_library": str(SKILLS_FILE),
            "experience_store_dir": str(EXPERIENCE_PATHS_DIR),
            "experience_files": as_str_list(skills_payload.get("experience_files")),
        },
        "priority_libraries": prioritized_libraries,
        "priority_library_count": len(prioritized_libraries),
        "requirement": requirement,
        "matcher_agents": ["project_custodian", "path_matcher", "semantic_matcher", "code_matcher"],
        "query_profile": query_profile,
        "constraints_contract": {
            "version": "constraints.v1",
            "description": "Step1输出结构化约束对象并向下游传递",
        },
        "matched_advisors": matched_advisors,
        "match_count": len(matched_advisors),
        "matching_explanation": {
            "policy": "project_partition_path_hierarchical_fusion",
            "notes": [
                "先做 project-level 管家筛选，再进入 partition/path 细化",
                "三匹配分数仍保留（path/semantic/code），但不再允许零命中靠证据分硬抬",
                "按需求粒度和分数分布动态决定匹配数量（不再固定Top3）",
            ],
        },
    }

    project_board = [
        {
            "rank": index,
            "project_name": as_str((item.get("project") or {}).get("project_name")),
            "project_score": round(float(item.get("project_score", 0.0)), 4),
            "detail": item.get("score_detail") or {},
        }
        for index, item in enumerate(project_candidates, start=1)
    ]

    partition_board = [
        {
            "rank": index,
            "project_name": as_str((item.get("project") or {}).get("project_name")),
            "partition_id": as_str((item.get("partition") or {}).get("partition_id")),
            "partition_name": as_str((item.get("partition") or {}).get("partition_name")),
            "project_score": round(float(item.get("project_score", 0.0)), 4),
            "partition_score": round(float(item.get("partition_score", 0.0)), 4),
            "detail": item.get("score_detail") or {},
        }
        for index, item in enumerate(partition_candidates[:120], start=1)
    ]

    path_board = [
        {
            "rank": index,
            "advisor_id": as_str((item.get("skill") or {}).get("skill_id")),
            "advisor_name": as_str((item.get("skill") or {}).get("name") or (item.get("skill") or {}).get("partition_name")),
            "project_name": as_str((item.get("skill") or {}).get("project_name")),
            "partition_id": as_str((item.get("skill") or {}).get("partition_id")),
            "path_matcher": item.get("scores", {}).get("path_matcher", 0),
            "semantic_matcher": item.get("scores", {}).get("semantic_matcher", 0),
            "code_matcher": item.get("scores", {}).get("code_matcher", 0),
            "base_fused_score": item.get("base_fused_score", 0),
            "project_score": item.get("project_score", 0),
            "partition_score": item.get("partition_score", 0),
            "fused_score": item.get("fused_score", 0),
            "total_hits": item.get("total_hits", 0),
        }
        for index, item in enumerate(path_candidates, start=1)
    ]

    process = {
        "version": "advisor.lab.v2",
        "step": "match_advisors_process",
        "generated_at": utc_now(),
        "run_id": run_id,
        "question_id": question_id,
        "requirement": requirement,
        "priority_libraries": prioritized_libraries,
        "priority_library_count": len(prioritized_libraries),
        "phase_traces": [
            {
                "phase": "requirement_understanding",
                "details": {
                    "query_profile": query_profile,
                    "requirement_tokens_count": len(requirement_tokens),
                    "requirement_tokens_preview": sorted(list(requirement_tokens))[:80],
                    "priority_libraries": prioritized_libraries,
                },
            },
            {
                "phase": "source_selection",
                "details": {
                    "source_mode": as_str(EXPERIENCE_SOURCE_MODE),
                    "selected_source": as_str(skills_payload.get("source")) or "generated_skills",
                    "experience_store_dir": str(EXPERIENCE_PATHS_DIR),
                    "experience_file_count": len(as_str_list(skills_payload.get("experience_files"))),
                    "experience_files": as_str_list(skills_payload.get("experience_files")),
                    "candidate_count": len(skills),
                    "project_count": len(projects),
                },
            },
            {
                "phase": "project_screening",
                "details": {
                    "top_project_count": top_project_count,
                    "project_scoreboard": project_board,
                    "selected_projects": [
                        as_str((item.get("project") or {}).get("project_name"))
                        for item in selected_projects
                    ],
                },
            },
            {
                "phase": "partition_refinement",
                "details": {
                    "partition_scoreboard": partition_board,
                },
            },
            {
                "phase": "path_scoring_and_topk",
                "details": {
                    "formula": "fused = base(path/semantic/code) + 0.55*project_score + 0.65*partition_score",
                    "path_scoreboard": path_board,
                    "diversify_topk": scope in {"broad", "mixed"},
                    "topk_plan": topk_plan,
                    "top_match_count": len(matched_advisors),
                    "top_advisors": matched_advisors,
                    "structured_constraints_coverage": {
                        "with_structured_constraints": len(
                            [item for item in matched_advisors if isinstance(item.get("constraints_structured"), dict)]
                        ),
                        "with_cfg": len(
                            [
                                item
                                for item in matched_advisors
                                if bool(((item.get("constraints_structured") or {}).get("cfg") or {}).get("summary", {}).get("exists"))
                            ]
                        ),
                        "with_dfg": len(
                            [
                                item
                                for item in matched_advisors
                                if bool(((item.get("constraints_structured") or {}).get("dfg") or {}).get("summary", {}).get("exists"))
                            ]
                        ),
                        "with_io_graph": len(
                            [
                                item
                                for item in matched_advisors
                                if bool(((item.get("constraints_structured") or {}).get("io_graph") or {}).get("summary", {}).get("exists"))
                            ]
                        ),
                    },
                },
            },
        ],
    }

    return report, process


def main() -> None:
    ensure_runtime(RUNTIME_DIR)
    run_id = as_str(os.environ.get("ADVISOR_RUN_ID")) or "single_run"
    question_id = as_str(os.environ.get("ADVISOR_QUESTION_ID")) or "q00"

    requirement = read_text(TASK_INPUT_FILE).strip()
    if not requirement:
        raise ValueError(f"task input is empty: {TASK_INPUT_FILE}")

    skills_payload = _load_candidate_skills_payload()
    prioritized_libraries = _parse_priority_libraries(os.environ.get("FH_ADVISOR_PRIORITY_LIBRARIES"))
    report, process = _build_report(
        requirement,
        skills_payload,
        run_id=run_id,
        question_id=question_id,
        prioritized_libraries=prioritized_libraries,
    )

    path_scoreboard: list[dict[str, Any]] = []
    for phase in process.get("phase_traces") or []:
        if as_str(phase.get("phase")) != "path_scoring_and_topk":
            continue
        details = phase.get("details") or {}
        raw_scoreboard = details.get("path_scoreboard")
        if isinstance(raw_scoreboard, list):
            path_scoreboard = [item for item in raw_scoreboard if isinstance(item, dict)]
            break

    write_json(STEP1_MATCH_RESULT_FILE, report)
    write_json(STEP1_MATCH_PROCESS_FILE, process)

    append_jsonl(
        STAGE_TRACE_FILE,
        {
            "version": "advisor.lab.v2",
            "run_id": run_id,
            "question_id": question_id,
            "step": "step1",
            "stage": "matching",
            "generated_at": report.get("generated_at"),
            "status": "completed",
            "final_artifact": str(STEP1_MATCH_RESULT_FILE),
            "process_artifact": str(STEP1_MATCH_PROCESS_FILE),
            "summary": {
                "candidate_count": len(path_scoreboard),
                "top_advisor": (report.get("matched_advisors") or [{}])[0].get("advisor_name", ""),
                "query_scope": (report.get("query_profile") or {}).get("scope", "mixed"),
            },
        },
    )

    print(f"[advisor-lab] step1 done: {STEP1_MATCH_RESULT_FILE}")


if __name__ == "__main__":
    main()
