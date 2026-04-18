from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from typing import Any, Callable


BASE_DIR = Path(__file__).resolve().parent
if __package__ in {None, ""}:
    sys.path.insert(0, str(BASE_DIR.parent))
    _MODULE_PREFIX = "skill_callchain_v2"
else:
    _MODULE_PREFIX = __package__


def _load_attr(module_suffix: str, attr_name: str) -> Any:
    module = importlib.import_module(f"{_MODULE_PREFIX}.{module_suffix}")
    return getattr(module, attr_name)


ensure_runtime: Callable[[], Path] = _load_attr("common", "ensure_runtime")
print_output: Callable[[str, Path], None] = _load_attr("common", "print_output")
read_json: Callable[[Path], Any] = _load_attr("common", "read_json")
utc_now: Callable[[], str] = _load_attr("common", "utc_now")
write_json: Callable[[Path, Any], None] = _load_attr("common", "write_json")
write_text: Callable[[Path, str], None] = _load_attr("common", "write_text")
DOT_SKILL_SCENARIO_DIR: Path = _load_attr("config", "DOT_SKILL_SCENARIO_DIR")
GENERATED_SKILLS_FILE: Path = _load_attr("config", "GENERATED_SKILLS_FILE")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _stringify(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_\-]+", "-", _stringify(value).lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "skill"


def _compact_text(value: Any, *, limit: int = 90) -> str:
    text = re.sub(r"\s+", " ", _stringify(value))
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 0)]}..."


def _source_locations_for_display(skill: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_locations = [item for item in (skill.get("source_locations") or []) if isinstance(item, dict)]
    rich = [item for item in all_locations if _stringify(item.get("file_path")) or item.get("line") is not None]
    symbol_only = [item for item in all_locations if not (_stringify(item.get("file_path")) or item.get("line") is not None)]
    return rich, symbol_only


def _markdown_for_skill(skill: dict[str, Any]) -> str:
    summary = _compact_text(skill.get("summary"))
    what = _compact_text(skill.get("what"))
    how = _compact_text(skill.get("how"), limit=120)
    call_chain = _string_list(skill.get("method_call_chain"))
    chain_explanation = _string_list(skill.get("chain_explanation"))
    approach_graph = skill.get("approach_graph") or []
    retrieval_hints = skill.get("retrieval_hints") or {}
    rich_locations, symbol_only_locations = _source_locations_for_display(skill)

    lines = [
        f"# {_stringify(skill.get('name')) or _stringify(skill.get('skill_id'))}",
        "",
        f"- `skill_id`: `{_stringify(skill.get('skill_id'))}`",
        f"- `partition_id`: `{_stringify(skill.get('partition_id'))}`",
        f"- `partition_name`: `{_stringify(skill.get('partition_name'))}`",
        f"- `summary`: {summary}",
        "",
        "## Quick Consumption",
        "- 代码生成优先读取顺序：`Method Call Chain -> Source Locations -> Retrieval Hints -> Approach Graph`",
        f"- 调用链概览：`{' -> '.join(call_chain) if call_chain else '(none)'}`",
        "",
        "## Method Call Chain",
    ]

    if call_chain:
        lines.extend([f"- `{item}`" for item in call_chain])
    else:
        lines.append("- (none)")

    lines.extend(["", "## Chain Explanation"])
    if chain_explanation:
        lines.extend([f"- {item}" for item in chain_explanation])
    else:
        lines.append("- (none)")

    lines.extend(["", "## Source Locations"])
    if rich_locations:
        for item in rich_locations[:5]:
            file_path = _stringify(item.get("file_path"))
            symbol = _stringify(item.get("symbol"))
            line = item.get("line")
            line_text = f":{int(line)}" if isinstance(line, int) and line > 0 else ""
            lines.append(f"- `{file_path}{line_text}` / `{symbol}`")
    elif symbol_only_locations:
        lines.append("- (symbols only, no file mapping)")
        for item in symbol_only_locations[:5]:
            lines.append(f"- `{_stringify(item.get('symbol'))}`")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Retrieval Hints"])
    if isinstance(retrieval_hints, dict) and retrieval_hints:
        lines.append(f"- partition_id: `{_stringify(retrieval_hints.get('partition_id'))}`")
        preferred_files = _string_list(retrieval_hints.get("preferred_files"))
        preferred_symbols = _string_list(retrieval_hints.get("preferred_symbols"))
        preferred_paths = _string_list(retrieval_hints.get("preferred_paths"))
        search_sequence = _string_list(retrieval_hints.get("search_sequence"))
        lines.append(f"- preferred_files: {', '.join(f'`{item}`' for item in preferred_files[:6]) if preferred_files else '(none)'}")
        lines.append(f"- preferred_symbols: {', '.join(f'`{item}`' for item in preferred_symbols[:6]) if preferred_symbols else '(none)'}")
        lines.append(f"- preferred_paths: {', '.join(f'`{item}`' for item in preferred_paths[:4]) if preferred_paths else '(none)'}")
        if search_sequence:
            lines.append(f"- search_sequence: {' | '.join(search_sequence[:3])}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Approach Graph"])
    if isinstance(approach_graph, list) and approach_graph:
        for node in approach_graph[:6]:
            if not isinstance(node, dict):
                continue
            step = int(node.get("step") or 0)
            module = _stringify(node.get("module"))
            node_input = _stringify(node.get("input"))
            node_output = _stringify(node.get("output"))
            next_module = _stringify(node.get("next_module")) or "END"
            lines.append(f"- [{step}] {module}: {node_input} -> {node_output} | next={next_module}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## How", how, "", "## What", what, "", "## Methods"])

    methods = _string_list(skill.get("methods"))
    if methods:
        lines.extend([f"- `{item}`" for item in methods[:12]])
        if len(methods) > 12:
            lines.append(f"- ... ({len(methods) - 12} more)")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Tags"])
    tags = _string_list(skill.get("tags"))
    if tags:
        lines.extend([f"- `{item}`" for item in tags])
    else:
        lines.append("- (none)")

    lines.extend(["", "## Evidence Summary"])
    evidence_summary = skill.get("evidence_summary") or {}
    lines.extend(
        [
            f"- path_count: {int(evidence_summary.get('path_count') or 0)}",
            f"- code_ref_count: {int(evidence_summary.get('code_ref_count') or 0)}",
            f"- file_count: {int(evidence_summary.get('file_count') or 0)}",
        ]
    )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ensure_runtime()
    payload = read_json(GENERATED_SKILLS_FILE)
    if not isinstance(payload, dict):
        raise ValueError("generated_skills.json must be a JSON object")

    skills = [item for item in (payload.get("skills") or []) if isinstance(item, dict)]
    DOT_SKILL_SCENARIO_DIR.mkdir(parents=True, exist_ok=True)

    exported_files: list[str] = []
    for index, skill in enumerate(skills, start=1):
        base_name = _slugify(_stringify(skill.get("partition_id")) or _stringify(skill.get("skill_id")) or f"skill-{index}")
        json_path = DOT_SKILL_SCENARIO_DIR / f"{index:02d}_{base_name}.skill.json"
        md_path = DOT_SKILL_SCENARIO_DIR / f"{index:02d}_{base_name}.skill.md"
        write_json(json_path, skill)
        write_text(md_path, _markdown_for_skill(skill))
        exported_files.append(str(json_path))
        exported_files.append(str(md_path))

    manifest_payload = {
        "generated_at": utc_now(),
        "source_file": str(GENERATED_SKILLS_FILE),
        "skill_count": len(skills),
        "export_dir": str(DOT_SKILL_SCENARIO_DIR),
        "files": exported_files,
    }
    manifest_path = DOT_SKILL_SCENARIO_DIR / "manifest.json"
    write_json(manifest_path, manifest_payload)

    print_output(".skill 导出完成", manifest_path)


if __name__ == "__main__":
    main()
