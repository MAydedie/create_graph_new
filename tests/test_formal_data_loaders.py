from __future__ import annotations

import gzip
import json
import pickle
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from formal_data.loaders import inspect_path
from formal_data.loaders.codesearchnet import validate_codesearchnet
from formal_data.loaders.crosscodeeval import inspect_crosscodeeval
from formal_data.loaders.fea_bench import inspect_fea_bench
from formal_data.loaders.repobench_r import inspect_repobench_r
from formal_data.loaders.repobench_v11 import inspect_repobench_v11
from formal_data.loaders.repoeval import inspect_repoeval
from formal_data.loaders.repoqa import inspect_repoqa, validate_repoqa
from formal_data.loaders.swe_bench_verified import inspect_swe_bench_verified, validate_swe_bench_verified


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _write_parquet(path: Path, rows: list[Mapping[str, object]]) -> None:
    pq.write_table(pa.Table.from_pylist(rows), path)


def _repoqa_row(repo: str = "r") -> dict[str, object]:
    return {"repo": repo, "commit_sha": "abc", "content": "body", "functions": ["f"], "needles": ["needle"]}


def test_repoqa_json_and_gzip_are_deterministic(tmp_path: Path) -> None:
    payload = {"python": [_repoqa_row("r1")], "java": [_repoqa_row("r2")]}
    json_path = tmp_path / "repoqa.json"
    gz_path = tmp_path / "repoqa.json.gz"
    _write_json(json_path, payload)
    with gzip.open(gz_path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)

    first = inspect_repoqa(json_path)
    second = inspect_repoqa(json_path)
    gz_result = inspect_path(gz_path, dataset="repoqa")

    assert first == second
    assert first["counts"] == {"languages": 2, "needles": 2, "repos": 2, "samples": 2}
    assert first["gold"]["has_needle_gold"] is True
    assert gz_result["counts"]["samples"] == 2


def test_codesearchnet_zip_streams_nested_test_jsonl_gz(tmp_path: Path) -> None:
    zip_path = tmp_path / "codesearchnet_python.zip"
    row = {
        "code": "def f(): pass",
        "docstring": "docs",
        "func_name": "f",
        "language": "python",
        "repo": "owner/repo",
        "sha": "abc",
        "path": "a.py",
        "url": "https://example.invalid/a.py",
    }
    encoded = gzip.compress((json.dumps(row, sort_keys=True) + "\n").encode("utf-8"))
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("python/final/jsonl/test/python_test_0.jsonl.gz", encoded)
        archive.writestr("python/final/jsonl/train/ignored.jsonl.gz", encoded)

    result = inspect_path(zip_path, dataset="codesearchnet")

    assert result["counts"]["test_rows"] == 1
    assert result["readiness"]["split"] == "test"
    assert result["gold"]["pair_target"] == "docstring"
    assert result["gold"]["official_relevance_gold"] is False
    assert result["gold"]["has_official_gold"] is False


def test_repobench_r_trusted_pickle_normalizes_gold_typo(tmp_path: Path) -> None:
    path = tmp_path / "repobench_r.pkl.gz"
    row = {
        "repo_name": "repo",
        "file_path": "a.py",
        "context": ["ctx"],
        "import_statement": "import os",
        "code": "x = 1",
        "next_line": "x",
        "golden_snippet_index": 0,
    }
    payload = {"train": {"easy": [row], "hard": [row]}, "test": {"easy": [row], "hard": [row]}}
    with gzip.open(path, "wb") as handle:
        pickle.dump(payload, handle)

    result = inspect_repobench_r(path)

    assert result["counts"]["rows"] == 4
    assert result["gold"]["accepts_source_typo"] is True
    assert result["gold"]["has_gold"] is True


def test_repobench_v11_parquet_metadata(tmp_path: Path) -> None:
    path = tmp_path / "repobench_v11.parquet"
    row = {
        "repo_name": "repo",
        "file_path": "a.py",
        "context": ["ctx"],
        "import_statement": "import os",
        "token_num": 3,
        "cropped_code": "x",
        "all_code": "x = 1",
        "next_line": "x",
        "gold_snippet_index": 0,
        "created_at": "2026-01-01",
        "level": "easy",
    }
    _write_parquet(path, [row, row])

    result = inspect_repobench_v11(path)

    assert result["counts"]["rows"] == 2
    assert result["gold"]["gold_snippet_index"] == "present"


def test_crosscodeeval_variant_and_context_shapes(tmp_path: Path) -> None:
    path = tmp_path / "crosscodeeval_rg1_openai_cosine_sim.jsonl"
    _write_jsonl(
        path,
        [
            {
                "prompt": "p",
                "groundtruth": "g",
                "metadata": {"task_id": "t1"},
                "crossfile_context": {"list": ["a"], "text": "ctx"},
            },
            {
                "prompt": "p",
                "groundtruth": "g",
                "metadata": {"task_id": "t2"},
                "crossfile_context": {"list": [], "text": ""},
            },
        ],
    )

    result = inspect_crosscodeeval(path)

    assert result["readiness"]["variant"] == "rg1_openai_cosine_sim"
    assert result["counts"]["context_dict_rows"] == 2
    assert result["counts"]["context_list_rows"] == 2
    assert result["counts"]["context_text_rows"] == 2


def test_repoeval_datasets_zip_member_kinds(tmp_path: Path) -> None:
    path = tmp_path / "datasets.zip"
    base = {
        "prompt": "p",
        "metadata": {"task_id": "t", "ground_truth": "g", "fpath_tuple": ["a.py"], "context_start_lineno": 1},
    }
    rows = {
        "line.jsonl": {"prompt": "p", "metadata": {**base["metadata"], "line_no": 3}},
        "api.jsonl": base,
        "function.jsonl": {"prompt": "p", "metadata": {**base["metadata"], "lineno": 4, "function_name": "f"}},
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, row in rows.items():
            archive.writestr(name, json.dumps(row, sort_keys=True) + "\n")

    result = inspect_repoeval(path)

    assert result["counts"]["line_rows"] == 1
    assert result["counts"]["api_rows"] == 1
    assert result["counts"]["function_rows"] == 1
    assert result["readiness"]["extracted"] is False


def test_fea_bench_public_parquet_and_enriched_jsonl(tmp_path: Path) -> None:
    parquet_path = tmp_path / "fea_public.parquet"
    metadata_row = {
        "instance_id": "i",
        "repo": "r",
        "base_commit": "b",
        "FAIL_TO_PASS": ["t"],
        "PASS_TO_PASS": ["p"],
        "environment_setup_commit": "e",
    }
    _write_parquet(parquet_path, [metadata_row for _ in range(1401)])
    jsonl_path = tmp_path / "fea_enriched.jsonl"
    enriched = {**metadata_row, "patch": "diff", "test_patch": "test diff"}
    _write_jsonl(jsonl_path, [enriched, enriched])

    public_result = inspect_fea_bench(parquet_path)
    enriched_result = inspect_fea_bench(jsonl_path)

    assert public_result["readiness"]["dataset_shape"] == "public_essential_parquet"
    assert public_result["readiness"]["patch_ready"] is False
    assert public_result["readiness"]["metadata_ready"] is True
    assert public_result["readiness"]["repository_checkout_ready"] is False
    assert public_result["readiness"]["test_environment_ready"] is False
    assert enriched_result["readiness"]["patch_ready"] is True
    assert enriched_result["readiness"]["test_patch_ready"] is True
    assert enriched_result["counts"]["environment_setup_commit_rows"] == 2


def test_swe_bench_verified_expected_count_is_configurable(tmp_path: Path) -> None:
    path = tmp_path / "swe_bench_verified.parquet"
    row = {
        "repo": "r",
        "instance_id": "i",
        "base_commit": "b",
        "patch": "diff",
        "test_patch": "test diff",
        "problem_statement": "problem",
        "version": "1",
        "FAIL_TO_PASS": json.dumps(["t"]),
        "PASS_TO_PASS": json.dumps(["p"]),
        "environment_setup_commit": "e",
        "difficulty": "easy",
    }
    _write_parquet(path, [row, row])

    result = inspect_swe_bench_verified(path, expected_count=2)
    failed = validate_swe_bench_verified(path, expected_count=500)

    assert result["counts"]["expected_rows"] == 2
    assert result["readiness"]["metadata_ready"] is True
    assert result["readiness"]["docker_ready"] is False
    assert result["gold"]["serialization_types"] == {"FAIL_TO_PASS": ["str"], "PASS_TO_PASS": ["str"]}
    assert failed["status"] == "partial"


def test_missing_malformed_and_partial_inputs_are_structured(tmp_path: Path) -> None:
    missing = validate_repoqa(tmp_path / "missing.json")
    malformed_zip = tmp_path / "bad_codesearchnet.zip"
    malformed_zip.write_bytes(b"not a zip")
    malformed = validate_codesearchnet(malformed_zip)
    partial_path = tmp_path / "repoqa_partial.json"
    _write_json(partial_path, {"python": [{"repo": "r"}]})
    partial = validate_repoqa(partial_path)

    assert missing["status"] == "missing"
    assert malformed["status"] == "malformed"
    assert partial["status"] == "partial"
    assert missing["errors"][0]["code"] == "missing"
    assert partial["errors"][0]["evidence"]["missing"]
