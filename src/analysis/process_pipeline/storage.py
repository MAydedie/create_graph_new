from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class ProcessShadowStorage:
    def __init__(self, storage_dir: str = "output_analysis/process_shadow") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _build_filepath(self, project_path: str) -> Path:
        normalized_path = os.path.normpath(project_path or "")
        project_name = os.path.basename(normalized_path) or "unknown_project"
        project_hash = hashlib.md5(normalized_path.encode("utf-8")).hexdigest()[:8]
        return self.storage_dir / f"{project_name}_{project_hash}.json"

    def save(self, project_path: str, process_shadow: Dict[str, Any]) -> Path:
        filepath = self._build_filepath(project_path)
        payload = dict(process_shadow)
        payload["project_path"] = os.path.normpath(project_path or "")
        with filepath.open("w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, indent=2, ensure_ascii=False)
        return filepath

    def load(self, project_path: str) -> Optional[Dict[str, Any]]:
        filepath = self._build_filepath(project_path)
        if not filepath.exists():
            return None
        try:
            with filepath.open("r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
            if os.path.normpath(payload.get("project_path", "")) != os.path.normpath(project_path or ""):
                return None
            return payload
        except Exception:
            return None
