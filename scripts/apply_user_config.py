#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
example = ROOT / "config" / "user_runtime_config.example.json"
config_file = ROOT / "config" / "user_runtime_config.json"


def _get(obj, path, default=""):
    cur = obj
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


if not config_file.exists():
    raise SystemExit(f"Missing {config_file}. Copy from {example.name} and fill your values first.")

cfg = json.loads(config_file.read_text(encoding="utf-8"))

provider = str(_get(cfg, ["llm", "provider"], "minimax")).strip().lower()
api_key = str(_get(cfg, ["llm", "api_key"], "")).strip()
base_url = str(_get(cfg, ["llm", "base_url"], "")).strip()
model = str(_get(cfg, ["llm", "model"], "")).strip()

openai_api_key = str(_get(cfg, ["fallback", "openai_api_key"], "")).strip()
openai_base_url = str(_get(cfg, ["fallback", "openai_base_url"], "https://api.openai.com/v1")).strip()
deepseek_api_key = str(_get(cfg, ["fallback", "deepseek_api_key"], "")).strip()
deepseek_base_url = str(_get(cfg, ["fallback", "deepseek_base_url"], "https://api.deepseek.com/v1")).strip()

enable_opencode = bool(_get(cfg, ["opencode", "enable_opencode_kernel"], True))
opencode_bin = str(_get(cfg, ["opencode", "opencode_bin"], "opencode")).strip()
opencode_model = str(_get(cfg, ["opencode", "opencode_model"], "")).strip()
opencode_agent = str(_get(cfg, ["opencode", "opencode_agent"], "")).strip()
opencode_timeout = int(_get(cfg, ["opencode", "opencode_timeout_seconds"], 300))

enable_advisor = bool(_get(cfg, ["advisor", "enable_advisor_sidecar"], True))
advisor_timeout = int(_get(cfg, ["advisor", "advisor_pipeline_timeout_seconds"], 120))
advisor_reuse = bool(_get(cfg, ["advisor", "advisor_reuse_runtime"], True))

lines = ["# Generated from config/user_runtime_config.json"]

if provider == "minimax":
    lines.append(f"MINIMAX_API_KEY={api_key}")
    lines.append(f"MINIMAX_BASE_URL={base_url}")
    lines.append(f"MINIMAX_MODEL={model}")
elif provider == "openai":
    lines.append(f"OPENAI_API_KEY={api_key}")
    lines.append(f"OPENAI_BASE_URL={base_url}")
    lines.append(f"OPENAI_MODEL={model}")
elif provider == "deepseek":
    lines.append(f"DEEPSEEK_API_KEY={api_key}")
    lines.append(f"DEEPSEEK_BASE_URL={base_url}")
    lines.append(f"DEEPSEEK_MODEL={model}")

if openai_api_key:
    lines.append(f"OPENAI_API_KEY={openai_api_key}")
if openai_base_url:
    lines.append(f"OPENAI_BASE_URL={openai_base_url}")
if deepseek_api_key:
    lines.append(f"DEEPSEEK_API_KEY={deepseek_api_key}")
if deepseek_base_url:
    lines.append(f"DEEPSEEK_BASE_URL={deepseek_base_url}")

lines.append(f"FH_ENABLE_OPENCODE_KERNEL={'1' if enable_opencode else '0'}")
if opencode_bin:
    lines.append(f"FH_OPENCODE_BIN={opencode_bin}")
if opencode_model:
    lines.append(f"FH_OPENCODE_MODEL={opencode_model}")
if opencode_agent:
    lines.append(f"FH_OPENCODE_AGENT={opencode_agent}")
lines.append(f"FH_OPENCODE_KERNEL_TIMEOUT_SECONDS={opencode_timeout}")

lines.append(f"FH_ENABLE_ADVISOR_SIDECAR={'1' if enable_advisor else '0'}")
lines.append(f"FH_ADVISOR_PIPELINE_TIMEOUT_SECONDS={advisor_timeout}")
lines.append(f"FH_ADVISOR_REUSE_RUNTIME={'1' if advisor_reuse else '0'}")

env_path = ROOT / '.env'
env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f"Wrote {env_path}")
