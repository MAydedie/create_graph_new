from __future__ import annotations

from app.services import multi_agent_service as mas


def test_should_invoke_advisor_skips_locator_query_with_anchor() -> None:
    retrieval_bundle = {
        "selected_path": {"function_chain": ["app.services.conversation_service.api"], "path": []},
        "node_details": [{"file_path": "app/services/conversation_service.py"}],
        "candidate_paths": [{"path_id": "p1"}, {"path_id": "p2"}, {"path_id": "p3"}],
        "impacted_files": ["app/services/conversation_service.py"],
        "confidence": "medium",
        "selection_mode": "search_fallback",
    }
    invoke, reason, signals = mas._should_invoke_advisor(
        "conversation session status result 接口在哪里",
        "modify_existing",
        retrieval_bundle,
    )
    assert invoke is False
    assert reason == "locator_query_with_anchor"
    assert signals.get("locator_query_hit") is True


def test_should_invoke_advisor_invokes_high_risk_query() -> None:
    retrieval_bundle = {
        "selected_path": {"function_chain": ["service.entry", "service.apply"], "path": []},
        "node_details": [{"file_path": "app/services/multi_agent_service.py"}],
        "candidate_paths": [{"path_id": "p1"}, {"path_id": "p2"}],
        "impacted_files": ["app/services/multi_agent_service.py"],
        "confidence": "high",
        "selection_mode": "path_analyses",
    }
    invoke, reason, _ = mas._should_invoke_advisor(
        "我要重构多代理架构并提高安全性",
        "modify_existing",
        retrieval_bundle,
    )
    assert invoke is True
    assert reason == "high_risk_query"


def test_build_path_node_details_emits_structured_chain_fields() -> None:
    selected_path = {
        "function_chain": ["pkg.mod.alpha", "pkg.mod.beta"],
        "call_chain_analysis": {
            "main_method": "pkg.mod.alpha",
            "intermediate_methods": ["pkg.mod.beta"],
            "direct_calls": ["pkg.mod.beta"],
            "explanation": "按主链依次调用",
        },
    }

    original = mas._build_node_detail_payload
    try:
        def _fake_detail(_project_path: str, symbol: str):
            return {
                "entity_id": symbol,
                "signature": symbol,
                "display_name": symbol,
                "file_path": f"src/{symbol.split('.')[-1]}.py",
                "line_start": 10,
                "line_end": 20,
                "source": {"file_path": f"src/{symbol.split('.')[-1]}.py", "line_start": 10},
            }

        mas._build_node_detail_payload = _fake_detail  # type: ignore[assignment]
        details = mas._build_path_node_details("D:/repo", selected_path, [])
    finally:
        mas._build_node_detail_payload = original  # type: ignore[assignment]

    assert len(details) == 2
    assert details[0]["step_index"] == 1
    assert details[0]["chain_role"] == "main_method"
    assert "按主链依次调用" in details[0]["call_explanation"]
    assert details[1]["step_index"] == 2
    assert details[1]["chain_role"] in {"intermediate_method", "direct_call"}


def test_build_qa_context_bundle_preserves_structural_graph_and_advisor_evidence(monkeypatch) -> None:
    retrieval_bundle = {
        "selected_partition_id": "partition-metrics",
        "selected_path": {
            "partition_id": "partition-metrics",
            "path_id": "path-1",
            "path_name": "metrics flow",
            "path_description": "entry -> prepare -> run",
            "leaf_node": "pkg.metrics.run",
            "function_chain": ["pkg.entry.main", "pkg.metrics.prepare", "pkg.metrics.run"],
            "selection_score": 0.97,
            "worthiness_score": 0.91,
            "selection_reason": "selected_node_partition_match",
            "call_chain_analysis": {
                "main_method": "pkg.entry.main",
                "intermediate_methods": ["pkg.metrics.prepare"],
                "direct_calls": ["pkg.metrics.run"],
                "explanation": "主入口最终命中 run",
            },
            "highlight_config": {
                "main_method": "pkg.entry.main",
                "intermediate_methods": ["pkg.metrics.prepare"],
                "path_methods": ["pkg.entry.main", "pkg.metrics.prepare", "pkg.metrics.run"],
                "explanation": "高亮主路径",
            },
        },
        "candidate_paths": [
            {
                "partition_id": "partition-metrics",
                "path_id": "path-1",
                "path_name": "metrics flow",
                "path_description": "entry -> prepare -> run",
                "leaf_node": "pkg.metrics.run",
                "function_chain": ["pkg.entry.main", "pkg.metrics.prepare", "pkg.metrics.run"],
                "selection_reason": "selected_node_partition_match",
                "call_chain_analysis": {"main_method": "pkg.entry.main"},
                "highlight_config": {"path_methods": ["pkg.entry.main", "pkg.metrics.prepare", "pkg.metrics.run"]},
            },
            {
                "partition_id": "partition-alt",
                "path_id": "path-2",
                "path_name": "alt flow",
                "path_description": "fallback",
                "leaf_node": "pkg.metrics.helper",
                "function_chain": ["pkg.alt.entry", "pkg.metrics.helper"],
            },
        ],
        "node_details": [
            {
                "entity_id": "pkg.metrics.run",
                "display_name": "Metrics.run",
                "kind": "Method",
                "step_index": 3,
                "chain_role": "leaf_node",
                "reason": "selected leaf",
                "call_explanation": "最终执行点",
                "full_name": "pkg.metrics.run",
                "signature": "pkg.metrics.run(self, data)",
                "method_signature": "pkg.metrics.run",
                "file_path": "src/metric.py",
                "line_start": 12,
                "line_end": 28,
                "source": {
                    "available": True,
                    "language": "python",
                    "file_path": "src/metric.py",
                    "line_start": 12,
                    "line_end": 28,
                    "snippet": "def run(self, data): ...",
                },
            }
        ],
        "impacted_files": ["src/metric.py"],
        "selection_mode": "path_analyses",
        "selection_reason": "selected_node_partition_match",
        "confidence": "high",
        "functional_context": {
            "entry_points_shadow": {"effective_entries": [{"method_signature": "pkg.entry.main"}]},
            "process_shadow": {"processes": [{"entry": "pkg.entry.main", "steps": [{"method_signature": "pkg.metrics.run"}]}]},
            "community_shadow": {"communities": [{"partition_id": "partition-metrics", "methods": ["pkg.metrics.run"]}]},
        },
        "evidence_packet": {
            "summary": {
                "confidence": "high",
                "primary_ids": ["path:path-1"],
                "supporting_ids": ["call_chain:selected", "graph_1"],
                "coverage": {"text": 1, "graph": 1, "functional_path": 2, "call_chain": 2},
            },
            "items": [
                {
                    "id": "path:path-1",
                    "kind": "functional_path",
                    "role": "primary",
                    "grounding": "derived",
                    "claim": "entry -> prepare -> run",
                    "source": {"partition_id": "partition-metrics", "path_id": "path-1", "symbol": "pkg.entry.main"},
                    "trace": ["pkg.entry.main", "pkg.metrics.prepare", "pkg.metrics.run"],
                    "raw_refs": ["path:selected"],
                },
                {
                    "id": "graph_1",
                    "kind": "graph",
                    "role": "supporting",
                    "grounding": "direct",
                    "claim": "Metrics.run",
                    "source": {"file_path": "src/metric.py", "symbol": "pkg.metrics.run", "line_start": 12, "line_end": 28},
                    "snippet": "def run(self, data): ...",
                    "trace": ["pkg.metrics.run"],
                    "raw_refs": ["node_detail"],
                },
            ],
            "functional_context": {
                "entry_points_shadow": {"effective_entries": [{"method_signature": "pkg.entry.main"}]},
                "process_shadow": {"processes": [{"entry": "pkg.entry.main"}]},
            },
            "review": {
                "selected_partition_id": "partition-metrics",
                "selected_path": {"path_id": "path-1", "leaf_node": "pkg.metrics.run", "function_chain": ["pkg.entry.main", "pkg.metrics.prepare", "pkg.metrics.run"]},
                "candidate_paths": [{"partition_id": "partition-metrics", "path_id": "path-1", "leaf_node": "pkg.metrics.run", "function_chain": ["pkg.entry.main", "pkg.metrics.prepare", "pkg.metrics.run"]}],
                "impacted_files": ["src/metric.py"],
                "selection_mode": "path_analyses",
                "selection_reason": "selected_node_partition_match",
                "anchor_ready": True,
            },
        },
    }
    advisor_packet = {
        "enabled": True,
        "status": "ready",
        "mode": "on_demand",
        "reason": "needs_more_context",
        "recommended": {"advisor_id": "advisor-1", "advisor_name": "Metrics Advisor", "partition_id": "partition-metrics"},
        "analysis": {
            "what": "分析 metrics 调用链",
            "how": "沿主路径核对 caller/callee",
            "next_step": "回答 follow-up QA",
            "key_call_chain": ["pkg.entry.main", "pkg.metrics.prepare", "pkg.metrics.run"],
            "key_code_refs": ["src/metric.py:12-28", "src/entry.py:1-10"],
        },
        "constraints": {
            "plain": ["仅基于证据回答"],
            "types": ["grounded_answer", "stable_anchor"],
            "structured_summary": {"needs_anchor": True},
            "structured": {"qa": {"prefer_fqn": True, "prefer_call_chain": True}},
        },
        "source_targets": [
            {
                "advisor_id": "advisor-1",
                "advisor_name": "Metrics Advisor",
                "partition_id": "partition-metrics",
                "reason": "主链命中",
                "source_targets": ["src/metric.py:12-28", "src/entry.py:1-10"],
            }
        ],
        "followup_advisors": [
            {"advisor_id": "advisor-2", "advisor_name": "Entry Advisor", "partition_id": "partition-entry", "fused_score": 0.72}
        ],
    }

    monkeypatch.setattr(mas, '_ensure_workbench_ready', lambda project_path: {})
    monkeypatch.setattr(mas, '_build_retrieval_bundle', lambda *args, **kwargs: retrieval_bundle)
    monkeypatch.setattr(mas, '_is_advisor_sidecar_enabled', lambda payload=None: True)
    monkeypatch.setattr(mas, '_should_invoke_advisor', lambda *args, **kwargs: (True, 'needs_more_context', {'candidate_path_count': 2}))
    monkeypatch.setattr(mas, '_run_advisor_sidecar', lambda *args, **kwargs: advisor_packet)

    result = mas.build_qa_context_bundle(
        project_path='D:/repo',
        user_query='谁调用了 pkg.metrics.run？请给我完整调用链和 FQN 证据',
        task_mode='none',
        preferred_partition_id='partition-metrics',
        selected_node={
            'id': 'node-metrics-run',
            'method_signature': 'pkg.metrics.run',
            'fqmn': 'pkg.metrics.run',
            'signature': 'pkg.metrics.run(self, data)',
            'function_chain': ['pkg.entry.main', 'pkg.metrics.prepare', 'pkg.metrics.run'],
            'main_method': 'pkg.entry.main',
            'intermediate_methods': ['pkg.metrics.prepare'],
        },
        qa_route='run_retrieval',
        task_weight='heavy',
    )

    assert result['partition_id'] == 'partition-metrics'
    assert result['selected_node']['method_signature'] == 'pkg.metrics.run'
    assert result['selected_node']['function_chain'] == ['pkg.entry.main', 'pkg.metrics.prepare', 'pkg.metrics.run']
    assert result['selected_path']['leaf_node'] == 'pkg.metrics.run'
    assert result['selected_path']['call_chain_analysis']['main_method'] == 'pkg.entry.main'
    assert result['selected_path']['highlight_config']['path_methods'] == ['pkg.entry.main', 'pkg.metrics.prepare', 'pkg.metrics.run']
    assert result['candidate_paths'][0]['partition_id'] == 'partition-metrics'
    assert result['candidate_paths'][0]['leaf_node'] == 'pkg.metrics.run'
    assert result['node_details'][0]['display_name'] == 'Metrics.run'
    assert result['node_details'][0]['full_name'] == 'pkg.metrics.run'
    assert result['node_details'][0]['signature'] == 'pkg.metrics.run(self, data)'
    assert result['evidence_packet']['items'][0]['source']['path_id'] == 'path-1'
    assert result['evidence_packet']['functional_context']['entry_points_shadow']['effective_entries'][0]['method_signature'] == 'pkg.entry.main'
    assert result['advisor']['analysis']['key_call_chain'] == ['pkg.entry.main', 'pkg.metrics.prepare', 'pkg.metrics.run']
    assert result['advisor']['analysis']['key_code_refs'] == ['src/metric.py:12-28', 'src/entry.py:1-10']
    assert result['advisor']['source_targets'][0]['source_targets'] == ['src/metric.py:12-28', 'src/entry.py:1-10']
    assert result['advisor']['followup_advisors'][0]['advisor_id'] == 'advisor-2'
    assert result['advisor']['constraints']['structured']['qa']['prefer_fqn'] is True


def test_build_advisor_adoption_summary_detects_output_matches() -> None:
    summary = mas._build_advisor_adoption_summary(
        {
            "status": "ready",
            "invocation": {"decision": "invoked"},
            "source_targets": [
                {"source_targets": ["src/metric.py:12-28", "src/entry.py:1-10"]},
            ],
        },
        [{"file_path": "src/metric.py"}],
        [{"file_path": "src/entry.py"}],
    )

    assert summary["invoked"] is True
    assert summary["merged"] is True
    assert summary["adopted"] is True
    assert summary["matched_file_count"] == 2
