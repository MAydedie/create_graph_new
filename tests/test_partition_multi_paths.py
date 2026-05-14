#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.analysis_service import _extract_lightweight_partition_paths, _get_partition_path_payload


def test_lightweight_partition_paths_keep_multiple_branches():
    analysis = {
        "call_graph": {
            "nodes": [
                {"id": "Entry.start"},
                {"id": "Branch.left"},
                {"id": "Branch.right"},
                {"id": "Leaf.alpha"},
                {"id": "Leaf.beta"},
            ],
            "edges": [
                {"source": "Entry.start", "target": "Branch.left"},
                {"source": "Entry.start", "target": "Branch.right"},
                {"source": "Branch.left", "target": "Leaf.alpha"},
                {"source": "Branch.right", "target": "Leaf.beta"},
            ],
        },
        "entry_points": [{"method_signature": "Entry.start"}],
    }

    paths = _extract_lightweight_partition_paths(analysis, max_paths=4)
    chains = {tuple(item.get("path") or []) for item in paths}

    assert ("Entry.start", "Branch.left", "Leaf.alpha") in chains
    assert ("Entry.start", "Branch.right", "Leaf.beta") in chains
    assert len(paths) >= 2


def test_partition_payload_supplements_sparse_deep_paths_with_structural_paths():
    analysis = {
        "path_analyses": [
            {
                "path_id": "deep_1",
                "leaf_node": "Leaf.deep",
                "function_chain": ["Entry.start", "Leaf.deep"],
                "path": ["Entry.start", "Leaf.deep"],
                "path_name": "Deep Path 1",
                "path_description": "existing deep path",
            }
        ],
        "path_analysis_info": {
            "max_paths_limit": 4,
            "selected_count": 1,
            "deferred_count": 2,
            "original_total": 3,
        },
        "paths_map": {
            "Leaf.deep": [["Entry.start", "Leaf.deep"]],
            "Leaf.left": [["Entry.start", "Branch.left", "Leaf.left"]],
            "Leaf.right": [["Entry.start", "Branch.right", "Leaf.right"]],
        },
        "fqns": [],
    }

    payload, info = _get_partition_path_payload(analysis)
    chains = {tuple(item.get("function_chain") or item.get("path") or []) for item in payload}

    assert ("Entry.start", "Leaf.deep") in chains
    assert ("Entry.start", "Branch.left", "Leaf.left") in chains
    assert ("Entry.start", "Branch.right", "Leaf.right") in chains
    assert len(payload) >= 3
    assert info.get("selection_policy") == "deep_analysis_supplemented"
