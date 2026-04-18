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
