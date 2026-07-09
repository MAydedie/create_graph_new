from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import jsonify, request


_APP_ROOT = Path(__file__).resolve().parents[2]
_PERSONA_ROOT = _APP_ROOT / "data" / "personas"
_STATE_FILE = _APP_ROOT / "data" / "persona_state.json"
_SKILL_FILE_NAME = "SKILL.md"
_EXIT_MARKERS = (
    "退出",
    "切回正常",
    "不用扮演了",
    "退出角色",
    "恢复默认",
    "exit persona",
    "disable persona",
    "back to normal",
)


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _ensure_storage_dirs() -> None:
    _PERSONA_ROOT.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json_file(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_slug(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", "_", text)
    text = text.strip("_")
    if text:
        return text[:64]
    digest = hashlib.md5(str(value or "persona").encode("utf-8")).hexdigest()[:8]
    return f"persona_{digest}"


def _split_front_matter(content: str) -> Tuple[List[str], str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return [], content

    closing_index = -1
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break

    if closing_index <= 0:
        return [], content

    front_lines = lines[1:closing_index]
    body = "\n".join(lines[closing_index + 1 :]).strip()
    return front_lines, body


def _parse_front_matter(front_lines: List[str]) -> Dict[str, str]:
    payload: Dict[str, str] = {}
    index = 0
    while index < len(front_lines):
        line = front_lines[index]
        match = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if not match:
            index += 1
            continue

        key = match.group(1)
        value = (match.group(2) or "").strip()
        if value == "|":
            index += 1
            block_lines: List[str] = []
            while index < len(front_lines):
                raw = front_lines[index]
                if raw.startswith("  "):
                    block_lines.append(raw[2:])
                    index += 1
                    continue
                if raw.strip() == "":
                    block_lines.append("")
                    index += 1
                    continue
                break
            payload[key] = "\n".join(block_lines).strip()
            continue

        payload[key] = value.strip('"\'')
        index += 1

    return payload


def _extract_markdown_sections(body: str) -> List[Tuple[str, str]]:
    sections: List[Tuple[str, str]] = []
    if not body:
        return sections

    current_title = ""
    current_lines: List[str] = []
    for line in body.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            if current_title:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = heading.group(1).strip()
            current_lines = []
            continue
        if current_title:
            current_lines.append(line)

    if current_title:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return sections


def _find_section(sections: List[Tuple[str, str]], candidates: List[str]) -> str:
    if not sections:
        return ""
    normalized_candidates = [item.lower() for item in candidates]
    for title, content in sections:
        title_lower = title.lower().replace(" ", "")
        if any(candidate in title_lower for candidate in normalized_candidates):
            return content.strip()
    return ""


def _summarize_mental_models(content: str) -> List[str]:
    if not content:
        return []

    lines = content.splitlines()
    model_name = ""
    summaries: List[str] = []
    for line in lines:
        heading = re.match(r"^###\s+(.+?)\s*$", line)
        if heading:
            model_name = heading.group(1).strip()
            continue
        if "一句话" in line and "：" in line:
            summary = line.split("：", 1)[1].strip()
            if summary:
                label = model_name or f"模型{len(summaries) + 1}"
                summaries.append(f"- {label}: {summary}")
        if len(summaries) >= 6:
            break

    return summaries


def _trim_text(text: str, max_chars: int) -> str:
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _build_persona_prompt_block(skill_markdown: str, persona_name: str, description: str) -> str:
    _front, body = _split_front_matter(skill_markdown)
    sections = _extract_markdown_sections(body)

    role_rules = _find_section(sections, ["角色扮演规则"])
    identity = _find_section(sections, ["身份卡"])
    style_dna = _find_section(sections, ["表达dna", "表达 dna", "表达_dna"])
    if not style_dna:
        style_dna = _find_section(sections, ["表达"])
    mental_models = _find_section(sections, ["核心心智模型"])

    model_summaries = _summarize_mental_models(mental_models)
    chunks: List[str] = [
        f"== Persona 模式：{persona_name} ==",
    ]
    if description:
        chunks.append(_trim_text(description, 500))

    if role_rules:
        chunks.append("【角色扮演规则】")
        chunks.append(_trim_text(role_rules, 2600))

    if identity:
        chunks.append("【身份卡】")
        chunks.append(_trim_text(identity, 1500))

    if style_dna:
        chunks.append("【表达 DNA】")
        chunks.append(_trim_text(style_dna, 1500))

    if model_summaries:
        chunks.append("【心智模型一句话】")
        chunks.append("\n".join(model_summaries[:6]))

    chunks.append("【退出角色】")
    chunks.append("当用户说‘退出/切回正常/不用扮演了/退出角色’时，立即恢复默认助手语气。")
    chunks.append("==")

    prompt = "\n\n".join(item for item in chunks if item.strip())
    return _trim_text(prompt, 12000)


def _resolve_skill_md_path(skill_path: str) -> Path:
    raw = str(skill_path or "").strip()
    if not raw:
        raise ValueError("skill_path 不能为空")

    candidate = Path(raw)
    if not candidate.is_absolute():
        raise ValueError("skill_path 必须是绝对路径")

    normalized = candidate.resolve()
    if normalized.is_dir():
        skill_md = normalized / _SKILL_FILE_NAME
        if not skill_md.exists():
            raise ValueError(f"未找到 SKILL.md: {skill_md}")
        return skill_md

    if normalized.is_file() and normalized.name.lower() == _SKILL_FILE_NAME.lower():
        return normalized

    raise ValueError("skill_path 必须指向 skill 目录或 SKILL.md 文件")


def _load_persona_meta(persona_id: str) -> Optional[Dict[str, Any]]:
    persona_dir = _PERSONA_ROOT / str(persona_id or "")
    meta_file = persona_dir / "meta.json"
    payload = _read_json_file(meta_file, None)
    if not isinstance(payload, dict):
        return None
    return payload


def _serialize_persona(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "personaId": str(meta.get("personaId") or "").strip(),
        "name": str(meta.get("name") or "").strip(),
        "description": str(meta.get("description") or "").strip(),
        "sourcePath": str(meta.get("sourcePath") or "").strip(),
        "importedAt": str(meta.get("importedAt") or "").strip(),
        "updatedAt": str(meta.get("updatedAt") or "").strip(),
        "temperatureOverride": meta.get("temperatureOverride"),
    }


def _activation_disclaimer(persona: Dict[str, Any]) -> str:
    name = str(persona.get("name") or persona.get("personaId") or "该角色").strip() or "该角色"
    return f"我将以{name}的视角和你聊，基于公开资料推断，非本人原话。"


def import_persona_skill(skill_path: str) -> Dict[str, Any]:
    _ensure_storage_dirs()
    skill_md_path = _resolve_skill_md_path(skill_path)
    content = skill_md_path.read_text(encoding="utf-8")
    front_lines, _body = _split_front_matter(content)
    front_matter = _parse_front_matter(front_lines)

    name = str(front_matter.get("name") or skill_md_path.parent.name).strip() or skill_md_path.parent.name
    description = str(front_matter.get("description") or "").strip()
    persona_id = _safe_slug(name)

    persona_dir = _PERSONA_ROOT / persona_id
    created = not persona_dir.exists()
    persona_dir.mkdir(parents=True, exist_ok=True)

    skill_dest = persona_dir / _SKILL_FILE_NAME
    skill_dest.write_text(content, encoding="utf-8")

    old_meta = _load_persona_meta(persona_id) or {}
    now = _utcnow_iso()
    prompt_block = _build_persona_prompt_block(content, name, description)
    meta = {
        "personaId": persona_id,
        "name": name,
        "description": description,
        "sourcePath": str(skill_md_path.parent),
        "importedAt": str(old_meta.get("importedAt") or now),
        "updatedAt": now,
        "temperatureOverride": float(old_meta.get("temperatureOverride") or 0.62),
        "promptBlock": prompt_block,
    }
    _write_json_file(persona_dir / "meta.json", meta)

    return {
        "ok": True,
        "created": created,
        "persona": _serialize_persona(meta),
    }


def list_persona_skills() -> List[Dict[str, Any]]:
    _ensure_storage_dirs()
    items: List[Dict[str, Any]] = []
    for persona_dir in _PERSONA_ROOT.iterdir():
        if not persona_dir.is_dir():
            continue
        meta = _load_persona_meta(persona_dir.name)
        if not isinstance(meta, dict):
            continue
        serialized = _serialize_persona(meta)
        if serialized.get("personaId"):
            items.append(serialized)
    items.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    return items


def get_active_persona_state() -> Dict[str, Any]:
    _ensure_storage_dirs()
    state = _read_json_file(_STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}

    active_persona_id = str(state.get("active_persona_id") or "").strip()
    disclaimer_pending = bool(state.get("disclaimer_pending", False))
    if not active_persona_id:
        return {
            "activePersonaId": "",
            "persona": None,
            "disclaimerPending": False,
        }

    meta = _load_persona_meta(active_persona_id)
    if not isinstance(meta, dict):
        _write_json_file(
            _STATE_FILE,
            {
                "active_persona_id": "",
                "activated_at": "",
                "disclaimer_pending": False,
            },
        )
        return {
            "activePersonaId": "",
            "persona": None,
            "disclaimerPending": False,
        }

    return {
        "activePersonaId": active_persona_id,
        "persona": _serialize_persona(meta),
        "disclaimerPending": disclaimer_pending,
    }


def activate_persona_skill(persona_id: str) -> Dict[str, Any]:
    _ensure_storage_dirs()
    normalized_id = str(persona_id or "").strip()
    if not normalized_id:
        raise ValueError("persona_id 不能为空")

    meta = _load_persona_meta(normalized_id)
    if not isinstance(meta, dict):
        raise ValueError(f"未找到 persona: {normalized_id}")

    _write_json_file(
        _STATE_FILE,
        {
            "active_persona_id": normalized_id,
            "activated_at": _utcnow_iso(),
            "disclaimer_pending": True,
        },
    )
    return {
        "ok": True,
        "activePersonaId": normalized_id,
        "persona": _serialize_persona(meta),
    }


def deactivate_persona_skill() -> Dict[str, Any]:
    current = get_active_persona_state()
    _write_json_file(
        _STATE_FILE,
        {
            "active_persona_id": "",
            "activated_at": "",
            "disclaimer_pending": False,
        },
    )
    return {
        "ok": True,
        "deactivated": bool(current.get("persona")),
        "persona": current.get("persona"),
    }


def delete_persona_skill(persona_id: str) -> Dict[str, Any]:
    _ensure_storage_dirs()
    normalized_id = str(persona_id or "").strip()
    if not normalized_id:
        raise ValueError("persona_id 不能为空")

    persona_dir = _PERSONA_ROOT / normalized_id
    if not persona_dir.exists() or not persona_dir.is_dir():
        raise ValueError(f"未找到 persona: {normalized_id}")

    active = get_active_persona_state()
    if str(active.get("activePersonaId") or "") == normalized_id:
        deactivate_persona_skill()

    shutil.rmtree(persona_dir, ignore_errors=False)
    return {"ok": True, "personaId": normalized_id}


def _load_prompt_block(meta: Dict[str, Any]) -> str:
    prompt_block = str(meta.get("promptBlock") or "").strip()
    if prompt_block:
        return prompt_block

    persona_id = str(meta.get("personaId") or "").strip()
    if not persona_id:
        return ""

    skill_md_file = _PERSONA_ROOT / persona_id / _SKILL_FILE_NAME
    if not skill_md_file.exists():
        return ""

    try:
        skill_content = skill_md_file.read_text(encoding="utf-8")
    except Exception:
        return ""

    prompt_block = _build_persona_prompt_block(
        skill_content,
        str(meta.get("name") or persona_id),
        str(meta.get("description") or ""),
    )
    if prompt_block:
        meta_with_prompt = dict(meta)
        meta_with_prompt["promptBlock"] = prompt_block
        _write_json_file(_PERSONA_ROOT / persona_id / "meta.json", meta_with_prompt)
    return prompt_block


def compose_system_prompt(base_prompt: str) -> Dict[str, Any]:
    active = get_active_persona_state()
    persona_raw = active.get("persona")
    persona = persona_raw if isinstance(persona_raw, dict) else None
    if not isinstance(persona, dict):
        return {
            "systemPrompt": str(base_prompt or ""),
            "temperature": None,
            "activePersona": None,
        }

    persona_id = str(persona.get("personaId") or "").strip()
    meta = _load_persona_meta(persona_id)
    prompt_block = _load_prompt_block(meta) if isinstance(meta, dict) else ""
    merged_prompt = str(base_prompt or "")
    if prompt_block:
        merged_prompt = f"{prompt_block}\n\n---\n\n{merged_prompt}"

    temperature = None
    raw_temp = persona.get("temperatureOverride")
    try:
        parsed = float(raw_temp)
        if 0 <= parsed <= 1.5:
            temperature = parsed
    except (TypeError, ValueError):
        temperature = None

    return {
        "systemPrompt": merged_prompt,
        "temperature": temperature,
        "activePersona": persona,
    }


def resolve_temperature(default_temperature: float) -> float:
    composed = compose_system_prompt("")
    override = composed.get("temperature")
    try:
        parsed = float(override)
        if 0 <= parsed <= 1.5:
            return parsed
    except (TypeError, ValueError):
        pass
    return float(default_temperature)


def consume_pending_disclaimer() -> str:
    active = get_active_persona_state()
    persona_raw = active.get("persona")
    if not isinstance(persona_raw, dict):
        return ""
    if not bool(active.get("disclaimerPending", False)):
        return ""

    state = _read_json_file(_STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}
    state["disclaimer_pending"] = False
    _write_json_file(_STATE_FILE, state)

    return _activation_disclaimer(persona_raw)


def is_persona_exit_command(user_query: str) -> bool:
    normalized = str(user_query or "").strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _EXIT_MARKERS)


def api_persona_skill_import():
    payload = request.json or {}
    skill_path = str(payload.get("skill_path") or "").strip()
    if not skill_path:
        return jsonify({"error": "skill_path 不能为空"}), 400

    try:
        result = import_persona_skill(skill_path)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"导入 persona skill 失败: {exc}"}), 500


def api_persona_skill_list():
    try:
        return jsonify(list_persona_skills())
    except Exception as exc:
        return jsonify({"error": f"读取 persona 列表失败: {exc}"}), 500


def api_persona_skill_activate():
    payload = request.json or {}
    persona_id = str(payload.get("persona_id") or "").strip()
    if not persona_id:
        return jsonify({"error": "persona_id 不能为空"}), 400

    try:
        return jsonify(activate_persona_skill(persona_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"激活 persona 失败: {exc}"}), 500


def api_persona_skill_deactivate():
    try:
        return jsonify(deactivate_persona_skill())
    except Exception as exc:
        return jsonify({"error": f"退出 persona 失败: {exc}"}), 500


def api_persona_skill_delete(persona_id: str):
    try:
        return jsonify(delete_persona_skill(persona_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": f"删除 persona 失败: {exc}"}), 500


def api_persona_skill_active():
    try:
        return jsonify(get_active_persona_state())
    except Exception as exc:
        return jsonify({"error": f"读取激活 persona 失败: {exc}"}), 500
