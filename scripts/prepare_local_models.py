from __future__ import annotations

import sys
from pathlib import Path

from huggingface_hub import snapshot_download

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import (
    EMBEDDING_MODEL_NAME,
    EMBEDDING_LOCAL_MODEL_DIR,
    RERANKER_MODEL_NAME,
    RERANKER_LOCAL_MODEL_DIR,
)


def _download(repo_id: str, local_dir: str) -> Path:
    target = Path(local_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    print(f"[LocalModel] Downloading {repo_id} -> {target}")
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target),
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    print(f"[LocalModel] Ready: {target}")
    return target


def main() -> None:
    _download(EMBEDDING_MODEL_NAME, EMBEDDING_LOCAL_MODEL_DIR)
    _download(RERANKER_MODEL_NAME, RERANKER_LOCAL_MODEL_DIR)
    print("[LocalModel] All local models prepared.")


if __name__ == "__main__":
    main()
