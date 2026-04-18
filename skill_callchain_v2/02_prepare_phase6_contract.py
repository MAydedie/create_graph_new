from __future__ import annotations

import importlib
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
write_json: Callable[[Path, Any], None] = _load_attr("common", "write_json")
PROJECT_PATH: Path = _load_attr("config", "PROJECT_PATH")
PHASE6_CONTRACT_FILE: Path = _load_attr("config", "PHASE6_CONTRACT_FILE")
load_phase6_contract: Callable[..., dict | None] = _load_attr("adapters.phase6_contract_adapter", "load_phase6_contract")


def main() -> None:
    ensure_runtime()
    contract_payload = load_phase6_contract(str(PROJECT_PATH), include_shadow_results=True)
    if not isinstance(contract_payload, dict):
        raise FileNotFoundError(
            "未找到可用的 phase6/function hierarchy 缓存。请先通过主系统运行一次功能层级/phase6 分析，再重试。"
        )
    write_json(PHASE6_CONTRACT_FILE, contract_payload)
    print_output("phase6 contract 已导出", PHASE6_CONTRACT_FILE)


if __name__ == "__main__":
    main()
