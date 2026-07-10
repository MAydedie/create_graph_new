from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_DIR = PROJECT_ROOT / "formal_protocol"
YAML_FILES = [PROTOCOL_DIR / "protocol.yaml", PROTOCOL_DIR / "method_matrix.yaml"]
JSON_FILES = [PROTOCOL_DIR / "model_lock.json", PROTOCOL_DIR / "code_provenance.json"]
EXPECTED_METHOD_IDS = {"B0", "B1", "B2", "B3", "S0", "S1", "S2", "S3", "S4", "S5"}
REQUIRED_METHOD_FIELDS = {
    "id",
    "name",
    "context_source",
    "retrieval_mode",
    "graph_context",
    "partition_semantics",
    "path_analysis",
    "experience",
    "graph_query",
    "stage8_usage",
    "intended_status",
    "currently_runnable",
    "implementation_status",
}
FORBIDDEN_SECRET_KEYS = {"api_key", "access_token", "password", "secret", "credentials"}
OBVIOUS_CREDENTIAL_PATTERN = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})"
)


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{path} must contain a mapping"
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_nonfinite,
    )
    assert isinstance(payload, dict), f"{path} must contain an object"
    return payload


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key).lower())
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def test_protocol_files_exist_and_parse() -> None:
    expected_files = {
        "protocol.yaml",
        "method_matrix.yaml",
        "model_lock.json",
        "code_provenance.json",
        "fairness_checklist.md",
    }
    assert {path.name for path in PROTOCOL_DIR.iterdir()} == expected_files
    for path in YAML_FILES:
        _load_yaml(path)
    for path in JSON_FILES:
        _load_json(path)


def test_method_matrix_is_complete_unique_and_declarative() -> None:
    matrix = _load_yaml(PROTOCOL_DIR / "method_matrix.yaml")
    methods = matrix["methods"]
    ids = [method["id"] for method in methods]

    assert len(ids) == len(set(ids))
    assert set(ids) == EXPECTED_METHOD_IDS
    assert matrix["protocol_label"] == "formal"
    assert matrix["declaration_scope"] == "semantic_freeze_only"
    assert matrix["formal_runner_implemented"] is False
    for method in methods:
        assert REQUIRED_METHOD_FIELDS <= set(method)
        assert all(method[field] not in (None, "") for field in REQUIRED_METHOD_FIELDS)
        assert method["currently_runnable"] is False
        assert method["implementation_status"] == "pending_stage2_formal_runner"


def test_fair_budget_fields_and_b3_s5_equality() -> None:
    protocol = _load_yaml(PROTOCOL_DIR / "protocol.yaml")
    matrix = _load_yaml(PROTOCOL_DIR / "method_matrix.yaml")
    methods = {method["id"]: method for method in matrix["methods"]}
    retrieval = protocol["retrieval"]
    context_budget = protocol["context_budget"]

    assert protocol["protocol_label"] == "formal"
    assert retrieval["top_k"] > 0
    assert retrieval["candidate_count"] > 0
    assert retrieval["evidence_assembly_token_budget"] > 0
    assert retrieval["max_retrieved_files"] > 0
    assert retrieval["max_retrieved_snippets"] > 0
    assert retrieval["reranker"]["model_identifier"]
    assert retrieval["reranker"]["candidate_limit"] == retrieval["candidate_count"]
    assert retrieval["reranker"]["output_top_k"] == retrieval["top_k"]
    assert context_budget["B3_long_context_token_limit"] == context_budget["S5_final_input_token_limit"]
    assert methods["B3"]["final_input_token_limit"] == methods["S5"]["final_input_token_limit"]
    assert methods["B3"]["final_input_token_limit"] == context_budget["B3_long_context_token_limit"]


def test_protocol_does_not_promote_adapted_runner() -> None:
    protocol = _load_yaml(PROTOCOL_DIR / "protocol.yaml")
    runner = protocol["runner"]

    assert runner["formal_runner_implemented"] is False
    excluded = {entry["path"]: entry for entry in runner["excluded_runners"]}
    adapted = excluded["scripts/pdf_experiment_runner.py"]
    assert adapted["formal_runner"] is False
    assert set(adapted["protocol_labels"]) == {"adapted", "preliminary"}


def test_protocol_files_do_not_store_credentials() -> None:
    for path in YAML_FILES + JSON_FILES:
        text = path.read_text(encoding="utf-8")
        payload = _load_yaml(path) if path.suffix == ".yaml" else _load_json(path)
        assert not (FORBIDDEN_SECRET_KEYS & _walk_keys(payload)), path
        assert OBVIOUS_CREDENTIAL_PATTERN.search(text) is None, path
