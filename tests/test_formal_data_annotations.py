from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


FORMAL_DATA = PROJECT_ROOT / "formal_data"


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_optional_files_have_not_provided_semantics() -> None:
    holdout = _load_json(FORMAL_DATA / "holdout_repositories.json")
    assert isinstance(holdout, dict)
    assert holdout["status"] == "NOT_PROVIDED"
    assert holdout["optional"] is True
    assert holdout["repositories"] == []
    assert len(holdout["activation_requirements"]) >= 1

    assert (FORMAL_DATA / "custom_qa.jsonl").read_text(encoding="utf-8") == ""
    assert (FORMAL_DATA / "custom_c2.jsonl").read_text(encoding="utf-8") == ""


def test_annotation_audit_is_machine_inventory_and_non_human() -> None:
    rows = _load_jsonl(FORMAL_DATA / "annotation_audit.jsonl")
    assert len(rows) == 1
    row = rows[0]
    assert row["audit_id"] == "machine_inventory_stage1_optional_absence"
    assert row["annotation_type"] == "machine_inventory"
    assert row["human_reviewed"] is False
    assert row["human_gold"] is False
    assert row["qa_records"] == 0
    assert row["c2_records"] == 0
    assert row["status"] == "NOT_PROVIDED"
    assert row["optional"] is True


def test_annotation_queue_is_template_not_gold_and_has_unique_ids() -> None:
    queue = _load_json(FORMAL_DATA / "annotation_queue_template.json")
    assert isinstance(queue, dict)
    assert queue["$schema"] == "schema/annotation_queue.schema.json"
    assert queue["status"] == "TEMPLATE_ONLY"
    assert queue["template_not_gold"] is True
    qa_template = queue["qa_template"]
    c2_template = queue["c2_template"]
    assert qa_template["template_not_gold"] is True
    assert c2_template["template_not_gold"] is True
    ids = {qa_template["record_id"], c2_template["record_id"]}
    assert len(ids) == 2
