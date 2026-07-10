from __future__ import annotations

import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


FORMAL_DATA = PROJECT_ROOT / "formal_data"
READINESS_INDEX = {"NOT_PROVIDED": 0, "PRESENT": 1, "FORMAT_VERIFIED": 2, "LOADER_READY": 3, "GOLD_READY": 4, "PROTOCOL_READY": 5}
SUSPICIOUS_FIELD_RE = re.compile(r"(password|secret|token|api[_-]?key|credential)", re.IGNORECASE)
MODEL_NETWORK_RE = re.compile(r"(openai|deepseek|embedding|reranker|judge|benchmark|network|http://|https://api\.)", re.IGNORECASE)


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_readiness_ordering_and_split_agreement() -> None:
    manifest = _load_json(FORMAL_DATA / "dataset_manifest.json")
    assert isinstance(manifest, dict)
    datasets = manifest["datasets"]
    assert isinstance(datasets, list)
    assert manifest["overall_stage1_status"] == "READY_FOR_STAGE2"
    for dataset in datasets:
        readiness = dataset["readiness"]
        split = _load_json(FORMAL_DATA / str(dataset["split_file"]))
        assert isinstance(split, dict)
        for unit in split["formal_units"]:
            assert READINESS_INDEX[unit["readiness"]] <= READINESS_INDEX[readiness]
            if unit["formal"] is True:
                assert unit["readiness"] in {"GOLD_READY", "PROTOCOL_READY"}


def test_no_credential_like_fields_or_values_in_optional_records() -> None:
    paths = [
        FORMAL_DATA / "holdout_repositories.json",
        FORMAL_DATA / "annotation_audit.jsonl",
        FORMAL_DATA / "annotation_queue_template.json",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        assert "ssh_run.ps1" not in lowered
        assert not re.search(r"x-access-token", lowered)
        for match in SUSPICIOUS_FIELD_RE.finditer(text):
            raise AssertionError(f"credential-like field/value found in {path}: {match.group(0)}")


def test_manifest_declares_no_model_or_network_use() -> None:
    manifest = _load_json(FORMAL_DATA / "dataset_manifest.json")
    assert isinstance(manifest, dict)
    assert manifest["model_network_benchmark_use"] == "NONE"
    assert manifest["gate_rationale"]
    for dataset in manifest["datasets"]:
        assert "http" not in dataset["loader"].lower()
        note_blob = " ".join([dataset["task_notes"], dataset["split_gold_metric_or_harness"], *dataset["deviations"]])
        if dataset["id"] in {"crosscodeeval", "repoqa", "codesearchnet", "repobench_r", "repobench_v11", "repoeval", "fea_bench", "swe_bench_verified"}:
            assert "download" not in note_blob.lower()
        if dataset["id"] not in {"crosscodeeval", "codesearchnet", "repoqa", "repoeval", "fea_bench", "swe_bench_verified", "repobench_r", "repobench_v11"}:
            assert not MODEL_NETWORK_RE.search(note_blob)


def test_no_duplicate_split_ids_within_each_file() -> None:
    split_dir = FORMAL_DATA / "splits"
    for split_path in split_dir.glob("*.json"):
        payload = _load_json(split_path)
        assert isinstance(payload, dict)
        ids = [unit["id"] for unit in payload["formal_units"]]
        assert len(ids) == len(set(ids)), split_path
