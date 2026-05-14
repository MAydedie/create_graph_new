from llm.agent.utils.question_detector import QuestionDetector
from app import create_app
from app.services import conversation_service
from app.services import multi_agent_service


def _stub_conversation_turn_infra(monkeypatch):
    finalized = {}
    events = []

    monkeypatch.setattr(conversation_service, "_update_conversation_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(conversation_service, "_emit_conversation_event", lambda conversation_id, event_name, payload: events.append((event_name, payload)))
    monkeypatch.setattr(conversation_service, "_post_turn_housekeeping", lambda *args, **kwargs: {"keyFacts": {}, "compaction": None})
    monkeypatch.setattr(conversation_service, "_finalize_conversation_session", lambda session_id, result: finalized.setdefault("result", result))
    monkeypatch.setattr(conversation_service.data_accessor, "ensure_conversation", lambda *args, **kwargs: None)
    monkeypatch.setattr(conversation_service.data_accessor, "append_conversation_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(conversation_service.data_accessor, "append_conversation_part", lambda *args, **kwargs: None)

    return finalized, events


def test_followup_question_after_clarification_falls_back_to_general_chat():
    result = QuestionDetector.assess_clarification_need(
        "帮我改一下登录流程",
        clarification_context={
            "round": 1,
            "originalQuery": "帮我改一下登录流程",
            "latestUserReply": "为什么这里会一直卡住？",
        },
    )

    assert result["route"] == "general_chat"
    assert result["task_mode"] == "none"
    assert result["clarification_round"] == 1


def test_followup_ambiguous_requirement_falls_back_to_retrieval():
    result = QuestionDetector.assess_clarification_need(
        "帮我改一下登录流程",
        clarification_context={
            "round": 1,
            "originalQuery": "帮我改一下登录流程",
            "latestUserReply": "修改认证流程，保持最小改动并补齐异常处理",
        },
    )

    assert result["route"] == "run_retrieval"
    assert result["task_mode"] == "modify_existing"
    assert result["clarification_round"] == 1


def test_normalize_action_decision_uses_general_chat_fallback_after_clarification(monkeypatch):
    monkeypatch.setattr(
        conversation_service,
        "_llm_decide_next_action",
        lambda *args, **kwargs: {
            "action": "clarify",
            "task_mode": "modify_existing",
            "reason": "llm chose clarify",
            "confidence": 0.51,
        },
    )

    result = conversation_service._normalize_action_decision(
        user_query="为什么这里会一直卡住？",
        conversation_id="cid",
        project_path="D:/tmp",
        heuristic_decision={
            "route": "general_chat",
            "task_mode": "none",
            "reason": "澄清后应转普通问答",
            "confidence": 0.82,
            "clarification_round": 1,
        },
    )

    assert result["action"] == "general_chat"
    assert result["task_mode"] == "none"
    assert result["reason"] == "澄清后应转普通问答"


def test_normalize_action_decision_uses_retrieval_fallback_after_clarification(monkeypatch):
    monkeypatch.setattr(
        conversation_service,
        "_llm_decide_next_action",
        lambda *args, **kwargs: {
            "action": "clarify",
            "task_mode": "modify_existing",
            "reason": "llm chose clarify",
            "confidence": 0.49,
        },
    )

    result = conversation_service._normalize_action_decision(
        user_query="先给我一个稳妥方案",
        conversation_id="cid",
        project_path="D:/tmp",
        heuristic_decision={
            "route": "run_retrieval",
            "task_mode": "modify_existing",
            "reason": "澄清后先给证据化建议",
            "confidence": 0.74,
            "clarification_round": 1,
        },
    )

    assert result["action"] == "run_retrieval"
    assert result["task_mode"] == "modify_existing"
    assert result["reason"] == "澄清后先给证据化建议"


def test_codebase_fact_question_routes_to_retrieval_on_first_turn():
    result = QuestionDetector.assess_clarification_need(
        "metric.py 这个节点有多少个类，多少个方法？最重要的方法被谁调用，又调用了谁？",
    )

    assert result["route"] == "run_retrieval"
    assert result["task_mode"] == "none"
    assert result["clarity_level"] == "codebase_fact_question"


def test_normalize_action_decision_keeps_codebase_fact_questions_on_retrieval(monkeypatch):
    monkeypatch.setattr(
        conversation_service,
        "_llm_decide_next_action",
        lambda *args, **kwargs: {
            "action": "general_chat",
            "task_mode": "none",
            "reason": "llm downgraded to general chat",
            "confidence": 0.41,
        },
    )

    result = conversation_service._normalize_action_decision(
        user_query="metric.py 这个节点有多少个类，多少个方法？",
        conversation_id="cid",
        project_path="D:/tmp",
        heuristic_decision={
            "route": "run_retrieval",
            "task_mode": "none",
            "clarity_level": "codebase_fact_question",
            "reason": "命中特定文件/节点的代码事实问答，优先进入检索回答而不是普通闲聊",
            "confidence": 0.82,
            "clarification_round": 0,
        },
    )

    assert result["action"] == "run_retrieval"
    assert result["task_mode"] == "none"


def test_generate_retrieval_answer_for_codebase_fact_question_avoids_edit_template(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation_service, "_create_deepseek_client", lambda llm_config=None: None)

    metric_file = tmp_path / "metric.py"
    metric_file.write_text(
        """class Metrics:
    \"\"\"计算语义分割评估指标。\"\"\"

    def __init__(self):
        self.values = []

    def add(self, value):
        self.values.append(value)

    def value(self):
        return len(self.values)

    def scores(self):
        total = self.value()
        if total == 0:
            return {}
        return {\"total\": total}
""",
        encoding="utf-8",
    )

    answer = conversation_service._generate_retrieval_answer(
        user_query="metric.py 这个节点有多少个类，多少个方法？其中选取出一个最重要的方法，告诉我它主要是干嘛的。",
        conversation_id="cid",
        project_path=str(tmp_path),
        highlights=[{"file": "metric.py", "label": "metric.py:1", "score": 0.99, "lineStart": 1, "lineEnd": 15}],
        validation_commands=[],
        llm_config=None,
        task_mode="none",
    )

    assert "1 个类" in answer
    assert "4 个方法" in answer
    assert "scores" in answer
    assert "建议改动步骤" not in answer
    assert "建议验证命令" not in answer


def test_generate_retrieval_answer_for_codebase_fact_question_counts_top_level_functions(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation_service, "_create_deepseek_client", lambda llm_config=None: None)

    metric_file = tmp_path / "metric.py"
    metric_file.write_text(
        '''"""统计指标计算模块。"""

def _fast_hist(pred, target):
    """计算混淆矩阵。"""
    return zip(pred, target)


def evaluate(pred, target):
    """汇总指标结果。"""
    pairs = _fast_hist(pred, target)
    return {"count": len(list(pairs))}
''',
        encoding="utf-8",
    )

    answer = conversation_service._generate_retrieval_answer(
        user_query="metric.py 这个节点有多少个类，多少个方法？最重要的方法被谁调用，又调用了谁？",
        conversation_id="cid",
        project_path=str(tmp_path),
        highlights=[{"file": "metric.py", "label": "metric.py:1", "score": 0.99, "lineStart": 1, "lineEnd": 10}],
        validation_commands=[],
        llm_config=None,
        task_mode="none",
    )

    assert "0 个类" in answer
    assert "2 个方法" in answer
    assert "evaluate" in answer or "_fast_hist" in answer
    assert "调用" in answer
    assert "_fast_hist" in answer
    assert "建议改动步骤" not in answer
    assert "建议验证命令" not in answer


def test_generate_retrieval_answer_for_direct_qa_without_fact_mode_avoids_template(monkeypatch):
    monkeypatch.setattr(conversation_service, "_create_deepseek_client", lambda llm_config=None: None)
    monkeypatch.setattr(conversation_service, "run_opencode_qa", lambda **kwargs: None)

    user_query = "这个模块主要做什么？"
    highlights = [{"file": "src/module.py", "label": "src/module.py:10", "score": 0.9, "lineStart": 10, "lineEnd": 18, "snippet": "def run(): pass"}]

    answer = conversation_service._generate_retrieval_answer(
        user_query=user_query,
        conversation_id="cid",
        project_path="D:/tmp",
        highlights=highlights,
        validation_commands=["pytest -q"],
        llm_config=None,
        task_mode="none",
    )

    assert answer == conversation_service._build_direct_qa_fallback_answer(user_query, highlights)
    assert "建议改动步骤" not in answer
    assert "建议验证命令" not in answer


def test_normalize_action_decision_keeps_codebase_fact_question_task_mode_none_even_when_llm_returns_retrieval(monkeypatch):
    monkeypatch.setattr(
        conversation_service,
        "_llm_decide_next_action",
        lambda *args, **kwargs: {
            "action": "run_retrieval",
            "task_mode": "modify_existing",
            "reason": "llm incorrectly treated it as code modification",
            "confidence": 0.67,
        },
    )

    result = conversation_service._normalize_action_decision(
        user_query="metric.py 这个节点有多少个类，多少个方法？",
        conversation_id="cid",
        project_path="D:/tmp",
        heuristic_decision={
            "route": "run_retrieval",
            "task_mode": "none",
            "clarity_level": "codebase_fact_question",
            "reason": "命中特定文件/节点的代码事实问答，优先进入检索回答而不是普通闲聊",
            "confidence": 0.82,
            "clarification_round": 0,
        },
    )

    assert result["action"] == "run_retrieval"
    assert result["task_mode"] == "none"


def test_run_conversation_turn_keeps_codebase_fact_questions_on_retrieval_when_auto_start_enabled(monkeypatch):
    finalized, events = _stub_conversation_turn_infra(monkeypatch)

    monkeypatch.setattr(
        conversation_service,
        "_normalize_action_decision",
        lambda *args, **kwargs: {"action": "run_retrieval", "task_mode": "none", "reason": "fact qa", "confidence": 0.91},
    )
    monkeypatch.setattr(conversation_service, "_find_cached_retrieval", lambda *args, **kwargs: None)
    monkeypatch.setattr(conversation_service, "_run_retrieval_tool", lambda *args, **kwargs: {"ok": True, "error": None, "highlights": [{"file": "metric.py"}]})
    monkeypatch.setattr(conversation_service, "_hydrate_highlights_with_snippets", lambda *args, **kwargs: [{"file": "metric.py"}])
    monkeypatch.setattr(conversation_service, "_suggest_validation_commands", lambda *args, **kwargs: [])
    monkeypatch.setattr(conversation_service, "_is_project_purpose_query", lambda *args, **kwargs: False)
    monkeypatch.setattr(conversation_service, "_generate_retrieval_answer", lambda *args, **kwargs: "retrieval answer")
    monkeypatch.setattr(conversation_service, "_build_retrieval_search_summary", lambda *args, **kwargs: {})
    monkeypatch.setattr(conversation_service, "_build_retrieval_decision_trace", lambda **kwargs: [])
    monkeypatch.setattr(conversation_service, "_remember_retrieval_cache", lambda *args, **kwargs: None)

    conversation_service._run_conversation_turn(
        session_id="sid-retrieval",
        project_path="D:/tmp",
        user_query="metric.py 这个节点有多少个类，多少个方法？",
        conversation_id="cid-retrieval",
        auto_start_multi_agent=True,
    )

    assert finalized["result"]["nextStep"] == "retrieval_answer"
    assert finalized["result"]["safeToCodegen"] is False
    assert any(event_name == "turn.decided" and payload.get("action") == "run_retrieval" for event_name, payload in events)


def test_run_conversation_turn_keeps_general_chat_on_chat_path_when_auto_start_enabled(monkeypatch):
    finalized, events = _stub_conversation_turn_infra(monkeypatch)

    monkeypatch.setattr(
        conversation_service,
        "_normalize_action_decision",
        lambda *args, **kwargs: {"action": "general_chat", "task_mode": "none", "reason": "chat qa", "confidence": 0.88},
    )
    monkeypatch.setattr(conversation_service, "_generate_chat_answer", lambda *args, **kwargs: "chat answer")

    conversation_service._run_conversation_turn(
        session_id="sid-chat",
        project_path="D:/tmp",
        user_query="这个项目主要做什么？",
        conversation_id="cid-chat",
        auto_start_multi_agent=True,
    )

    assert finalized["result"]["nextStep"] == "send_chat"
    assert finalized["result"]["safeToCodegen"] is False
    assert finalized["result"]["answer"] == "chat answer"
    assert any(event_name == "turn.decided" and payload.get("action") == "general_chat" for event_name, payload in events)


def test_run_conversation_turn_still_escalates_real_modification_requests_when_auto_start_enabled(monkeypatch):
    finalized, events = _stub_conversation_turn_infra(monkeypatch)

    monkeypatch.setattr(
        conversation_service,
        "_normalize_action_decision",
        lambda *args, **kwargs: {"action": "run_retrieval", "task_mode": "modify_existing", "reason": "needs code change", "confidence": 0.93},
    )
    monkeypatch.setattr(
        conversation_service,
        "_try_inline_codegen_result",
        lambda **kwargs: {
            "session": {"sessionId": "inline-session-1"},
            "result": {
                "solution_packet": {},
                "output_protocol": {},
                "evidence_verdict": {},
                "opencode_kernel": {},
                "swarm_packet": {},
                "output_write": {},
            },
        },
    )
    monkeypatch.setattr(conversation_service, "_build_inline_codegen_answer", lambda *args, **kwargs: "inline answer")

    conversation_service._run_conversation_turn(
        session_id="sid-codegen",
        project_path="D:/tmp",
        user_query="帮我修改 metric.py 里的统计逻辑",
        conversation_id="cid-codegen",
        auto_start_multi_agent=True,
    )

    assert finalized["result"]["safeToCodegen"] is True
    assert finalized["result"]["answer"] == "inline answer"
    assert any(event_name == "turn.decided" and payload.get("action") == "start_multi_agent" for event_name, payload in events)


def test_generate_chat_answer_uses_opencode_qa_bridge_with_conversation_continuity(monkeypatch, tmp_path):
    recorded = {}
    saved_memory = {}

    monkeypatch.setattr(conversation_service.data_accessor, "get_conversation_key_facts_memory", lambda conversation_id: dict(saved_memory.get(conversation_id, {})))

    def _fake_save_memory(conversation_id, memory, merge=False):
        saved_memory[conversation_id] = dict(memory)
        return memory

    monkeypatch.setattr(conversation_service.data_accessor, "save_conversation_key_facts_memory", _fake_save_memory)

    def _fake_run_opencode_qa(**kwargs):
        recorded["kwargs"] = kwargs
        return {"status": "ready", "session_id": "oc-session-chat-1", "text": "OpenCode QA answer"}

    monkeypatch.setattr(conversation_service, "run_opencode_qa", _fake_run_opencode_qa)

    answer = conversation_service._generate_chat_answer(
        user_query="继续解释这个项目的用途",
        conversation_id="conv-qa-1",
        project_path=str(tmp_path),
        opencode_enabled=True,
    )

    assert answer == "OpenCode QA answer"
    assert recorded["kwargs"]["conversation_id"] == "conv-qa-1"
    assert recorded["kwargs"]["opencode_session_id"] == ""
    assert recorded["kwargs"]["project_path"] == str(tmp_path)
    assert recorded["kwargs"]["enabled"] is True
    assert saved_memory["conv-qa-1"]["opencodeQa"]["sessionId"] == "oc-session-chat-1"


def test_generate_chat_answer_reuses_stored_opencode_session_id(monkeypatch, tmp_path):
    recorded = {}
    monkeypatch.setattr(
        conversation_service.data_accessor,
        "get_conversation_key_facts_memory",
        lambda conversation_id: {"opencodeQa": {"sessionId": "oc-session-chat-2"}},
    )

    def _fake_run_opencode_qa(**kwargs):
        recorded["kwargs"] = kwargs
        return {"status": "ready", "session_id": "oc-session-chat-2", "text": "OpenCode QA answer"}

    monkeypatch.setattr(conversation_service, "run_opencode_qa", _fake_run_opencode_qa)

    answer = conversation_service._generate_chat_answer(
        user_query="继续解释这个项目的用途",
        conversation_id="conv-qa-2b",
        project_path=str(tmp_path),
        opencode_enabled=True,
    )

    assert answer == "OpenCode QA answer"
    assert recorded["kwargs"]["opencode_session_id"] == "oc-session-chat-2"


def test_run_conversation_turn_general_chat_adds_heavy_qa_context(monkeypatch):
    finalized, _ = _stub_conversation_turn_infra(monkeypatch)
    captured = {}
    qa_calls = {"count": 0}

    monkeypatch.setattr(
        conversation_service,
        "_normalize_action_decision",
        lambda *args, **kwargs: {"action": "general_chat", "task_mode": "none", "reason": "heavy qa", "confidence": 0.86},
    )
    monkeypatch.setattr(
        multi_agent_service,
        "build_qa_context_bundle",
        lambda **kwargs: qa_calls.__setitem__("count", qa_calls["count"] + 1) or {
            "qa_route": kwargs.get("qa_route"),
            "task_weight": kwargs.get("task_weight"),
            "selection_mode": "path_analyses",
            "selected_path": {"path_name": "metric flow"},
        },
    )

    def _fake_generate_chat_answer(*args, **kwargs):
        captured["qa_context"] = kwargs.get("qa_context")
        return "chat answer"

    monkeypatch.setattr(conversation_service, "_generate_chat_answer", _fake_generate_chat_answer)

    selected_node = {
        "id": "node-metrics-run",
        "name": "run",
        "file_path": "src/metric.py",
        "method_signature": "pkg.metrics.run",
        "fqmn": "pkg.metrics.run",
        "function_chain": ["pkg.entry.main", "pkg.metrics.run"],
    }

    conversation_service._run_conversation_turn(
        session_id="sid-chat-heavy",
        project_path="D:/tmp",
        user_query="请结合 metric.py 的调用链和架构关系说明证据",
        conversation_id="cid-chat-heavy",
        partition_id="partition-metrics",
        selected_node=selected_node,
        auto_start_multi_agent=True,
    )

    assert finalized["result"]["nextStep"] == "send_chat"
    assert finalized["result"]["answer"] == "chat answer"
    assert qa_calls["count"] == 1
    assert captured["qa_context"]["qa_route"] == "general_chat"
    assert captured["qa_context"]["task_weight"] == "heavy"
    assert captured["qa_context"]["selected_path"]["path_name"] == "metric flow"


def test_generate_retrieval_answer_uses_opencode_qa_bridge_for_grounded_edit_answer(monkeypatch, tmp_path):
    recorded = {}
    saved_memory = {}

    monkeypatch.setattr(conversation_service.data_accessor, "get_conversation_key_facts_memory", lambda conversation_id: dict(saved_memory.get(conversation_id, {})))

    def _fake_save_memory(conversation_id, memory, merge=False):
        saved_memory[conversation_id] = dict(memory)
        return memory

    monkeypatch.setattr(conversation_service.data_accessor, "save_conversation_key_facts_memory", _fake_save_memory)

    def _fake_run_opencode_qa(**kwargs):
        recorded["kwargs"] = kwargs
        return {
            "status": "ready",
            "session_id": "oc-session-retrieval-1",
            "text": "### 定位结论\n- 命中 metric.py\n\n### 关键证据\n- metric.py:1-15\n\n### 建议改动步骤\n- 调整实现\n\n### 建议验证命令\n- pytest -q",
        }

    monkeypatch.setattr(conversation_service, "run_opencode_qa", _fake_run_opencode_qa)

    answer = conversation_service._generate_retrieval_answer(
        user_query="帮我基于证据给出修改方案",
        conversation_id="conv-qa-2",
        project_path=str(tmp_path),
        highlights=[{"file": "metric.py", "label": "metric.py:1", "score": 0.99, "lineStart": 1, "lineEnd": 15}],
        validation_commands=["pytest -q"],
        task_mode="modify_existing",
        opencode_enabled=True,
    )

    assert answer.startswith("### 定位结论")
    assert recorded["kwargs"]["conversation_id"] == "conv-qa-2"
    assert recorded["kwargs"]["opencode_session_id"] == ""
    assert recorded["kwargs"]["project_path"] == str(tmp_path)
    assert recorded["kwargs"]["context_payload"]["retrieval_highlights"][0]["file"] == "metric.py"
    assert saved_memory["conv-qa-2"]["opencodeQa"]["sessionId"] == "oc-session-retrieval-1"


def test_generate_retrieval_answer_for_fact_qa_merges_qa_context_with_facts(monkeypatch, tmp_path):
    recorded = {}
    saved_memory = {}

    monkeypatch.setattr(conversation_service.data_accessor, "get_conversation_key_facts_memory", lambda conversation_id: dict(saved_memory.get(conversation_id, {})))
    monkeypatch.setattr(
        conversation_service.data_accessor,
        "save_conversation_key_facts_memory",
        lambda conversation_id, memory, merge=False: saved_memory.setdefault(conversation_id, dict(memory)),
    )
    monkeypatch.setattr(
        conversation_service,
        "_build_python_file_fact_payload",
        lambda *args, **kwargs: {
            "file_path": "metric.py",
            "class_count": 1,
            "method_count": 4,
            "file_purpose": "统计指标",
            "top_method": {"name": "scores", "callers": [], "callees": []},
        },
    )

    def _fake_run_opencode_qa(**kwargs):
        recorded["kwargs"] = kwargs
        return {"status": "ready", "session_id": "oc-session-fact-qa-1", "text": "fact answer"}

    monkeypatch.setattr(conversation_service, "run_opencode_qa", _fake_run_opencode_qa)

    answer = conversation_service._generate_retrieval_answer(
        user_query="metric.py 这个节点有多少个类，多少个方法？最重要的方法主要是干嘛的？",
        conversation_id="conv-fact-qa-1",
        project_path=str(tmp_path),
        highlights=[{"file": "metric.py", "label": "metric.py:1", "score": 0.99, "lineStart": 1, "lineEnd": 15}],
        validation_commands=[],
        task_mode="none",
        opencode_enabled=True,
        qa_context={"qa_route": "run_retrieval", "task_weight": "heavy", "selection_mode": "path_analyses"},
    )

    assert answer == "fact answer"
    assert recorded["kwargs"]["context_payload"]["facts"]["file_path"] == "metric.py"
    assert recorded["kwargs"]["context_payload"]["qa_context"]["task_weight"] == "heavy"
    assert recorded["kwargs"]["context_payload"]["qa_context"]["qa_route"] == "run_retrieval"


def test_generate_retrieval_answer_for_fact_qa_rejects_process_text(monkeypatch, tmp_path):
    monkeypatch.setattr(
        conversation_service,
        "_build_python_file_fact_payload",
        lambda *args, **kwargs: {
            "file_path": "metric.py",
            "class_count": 0,
            "method_count": 2,
            "file_purpose": "统计指标",
            "top_level_functions": [
                {"qualified_name": "evaluate", "docstring": "汇总指标结果。", "callers": [], "callees": []},
                {"qualified_name": "_fast_hist", "docstring": "计算混淆矩阵。", "callers": [{"label": "evaluate", "relation": "LOCAL_CALL"}], "callees": []},
            ],
            "top_method": {"name": "evaluate", "callers": [], "callees": [{"label": "_fast_hist", "relation": "LOCAL_CALL"}]},
        },
    )
    monkeypatch.setattr(
        conversation_service,
        "run_opencode_qa",
        lambda **kwargs: {"status": "ready", "text": "I’m gathering evidence and waiting for parallel explore-agent results."},
    )

    answer = conversation_service._generate_retrieval_answer(
        user_query="metric.py 这个节点有多少个类，多少个方法？最重要的方法被谁调用，又调用了谁？",
        conversation_id="conv-fact-qa-process",
        project_path=str(tmp_path),
        highlights=[{"file": "metric.py", "label": "metric.py:1", "score": 0.99, "lineStart": 1, "lineEnd": 15}],
        validation_commands=[],
        task_mode="none",
        opencode_enabled=True,
    )

    assert "0 个类" in answer
    assert "2 个方法" in answer
    assert "_fast_hist" in answer
    assert "waiting for parallel" not in answer.lower()


def test_build_python_file_fact_payload_prefers_selected_node_file_and_enriches_function_summaries(tmp_path):
    metric_file = tmp_path / "metric.py"
    metric_file.write_text(
        '''"""统计指标计算模块。"""

def _fast_hist(pred, target):
    """计算混淆矩阵。"""
    return list(zip(pred, target))


def evaluate(pred, target):
    """汇总指标结果。"""
    pairs = _fast_hist(pred, target)
    return {"count": len(list(pairs))}
''',
        encoding="utf-8",
    )

    payload = conversation_service._build_python_file_fact_payload(
        str(tmp_path),
        "请解释 evaluate 的作用以及调用关系",
        [{"file": "other.py", "label": "other.py:1", "score": 0.99}],
        qa_context={"selected_node": {"file_path": "metric.py", "method_signature": "evaluate"}},
    )

    assert payload is not None
    assert payload["file_path"] == "metric.py"
    assert payload["top_method"]["name"] == "evaluate"
    assert any(item["qualified_name"] == "evaluate" for item in payload["top_level_functions"])
    assert any(item["label"] == "_fast_hist" for item in payload["top_method"]["callees"])


def test_generate_retrieval_answer_prefers_graph_grounded_qa_over_fact_mode_when_qa_context_is_rich(monkeypatch):
    captured = {}

    def _fake_direct_answer(*args, **kwargs):
        captured["qa_context"] = kwargs.get("qa_context")
        return "direct graph qa"

    monkeypatch.setattr(
        conversation_service,
        "_generate_direct_retrieval_answer",
        _fake_direct_answer,
    )
    monkeypatch.setattr(
        conversation_service,
        "_generate_codebase_fact_answer",
        lambda *args, **kwargs: "fact qa should not win",
    )

    answer = conversation_service._generate_retrieval_answer(
        user_query="请基于调用链证据说明 pkg.metrics.run 的 caller-callee 关系和 FQN",
        conversation_id="conv-graph-qa-1",
        project_path="D:/tmp",
        highlights=[{"file": "metric.py", "label": "metric.py:1", "score": 0.99, "lineStart": 1, "lineEnd": 15}],
        validation_commands=[],
        task_mode="none",
        qa_context={
            "qa_route": "run_retrieval",
            "task_weight": "heavy",
            "selection_mode": "path_analyses",
            "selected_path": {"path_name": "metric flow"},
            "selected_node": {
                "fqmn": "pkg.metrics.run",
                "function_chain": ["pkg.entry.main", "pkg.metrics.run"],
            },
        },
    )

    assert answer == "direct graph qa"
    assert captured["qa_context"]["selection_mode"] == "path_analyses"
    assert captured["qa_context"]["selected_node"]["fqmn"] == "pkg.metrics.run"


def test_generate_retrieval_answer_keeps_plain_fact_questions_on_fact_mode(monkeypatch):
    monkeypatch.setattr(
        conversation_service,
        "_generate_direct_retrieval_answer",
        lambda *args, **kwargs: "direct qa should not win",
    )
    monkeypatch.setattr(
        conversation_service,
        "_generate_codebase_fact_answer",
        lambda *args, **kwargs: "fact qa wins",
    )

    answer = conversation_service._generate_retrieval_answer(
        user_query="metric.py 这个节点有多少个类，多少个方法？",
        conversation_id="conv-fact-qa-plain",
        project_path="D:/tmp",
        highlights=[{"file": "metric.py", "label": "metric.py:1", "score": 0.99, "lineStart": 1, "lineEnd": 15}],
        validation_commands=[],
        task_mode="none",
        qa_context={"qa_route": "run_retrieval", "task_weight": "heavy"},
    )

    assert answer == "fact qa wins"


def test_generate_retrieval_answer_uses_opencode_qa_bridge_for_direct_qa(monkeypatch, tmp_path):
    recorded = {}

    def _fake_run_opencode_qa(**kwargs):
        recorded["kwargs"] = kwargs
        return {"status": "ready", "text": "metric.py 主要负责指标统计。"}

    monkeypatch.setattr(conversation_service, "run_opencode_qa", _fake_run_opencode_qa)

    answer = conversation_service._generate_retrieval_answer(
        user_query="这个模块主要做什么？",
        conversation_id="conv-qa-3",
        project_path=str(tmp_path),
        highlights=[{"file": "metric.py", "label": "metric.py:1", "score": 0.9, "lineStart": 1, "lineEnd": 18, "snippet": "def run(): pass"}],
        validation_commands=["pytest -q"],
        task_mode="none",
        opencode_enabled=True,
    )

    assert answer == "metric.py 主要负责指标统计。"
    assert recorded["kwargs"]["conversation_id"] == "conv-qa-3"
    assert recorded["kwargs"]["context_payload"]["answer_style"] == "direct_qa"


def test_run_conversation_turn_light_general_chat_skips_heavy_qa_enrichment(monkeypatch):
    finalized, _ = _stub_conversation_turn_infra(monkeypatch)
    captured = {}
    qa_calls = {"count": 0}

    monkeypatch.setattr(
        conversation_service,
        "_normalize_action_decision",
        lambda *args, **kwargs: {"action": "general_chat", "task_mode": "none", "reason": "light qa", "confidence": 0.88},
    )
    monkeypatch.setattr(
        multi_agent_service,
        "build_qa_context_bundle",
        lambda **kwargs: qa_calls.__setitem__("count", qa_calls["count"] + 1) or {"task_weight": "heavy"},
    )

    def _fake_generate_chat_answer(*args, **kwargs):
        captured["qa_context"] = kwargs.get("qa_context")
        return "chat answer"

    monkeypatch.setattr(conversation_service, "_generate_chat_answer", _fake_generate_chat_answer)

    conversation_service._run_conversation_turn(
        session_id="sid-chat-light",
        project_path="D:/tmp",
        user_query="这个项目主要做什么？",
        conversation_id="cid-chat-light",
        auto_start_multi_agent=True,
    )

    assert finalized["result"]["nextStep"] == "send_chat"
    assert finalized["result"]["answer"] == "chat answer"
    assert qa_calls["count"] == 0
    assert captured["qa_context"] is None


def test_update_key_facts_memory_preserves_existing_opencode_qa_metadata(monkeypatch):
    saved = {}

    existing_memory = {
        "pathHints": ["src/old.py"],
        "selectedOptionLabels": ["保守方案"],
        "decisions": [{"action": "general_chat", "taskMode": "none", "reason": "old", "at": "2026-01-01T00:00:00Z"}],
        "retrievalCache": [{"query": "old question", "answer": "cached"}],
        "opencodeQa": {
            "sessionId": "oc-session-preserved",
            "updatedAt": "2026-01-02T00:00:00Z",
            "status": "ready",
            "lastQuestion": "Explain this module",
        },
        "opencodeQaSessionId": "oc-session-preserved",
    }

    monkeypatch.setattr(
        conversation_service.data_accessor,
        "get_conversation_key_facts_memory",
        lambda conversation_id: dict(existing_memory),
    )

    def _fake_save_memory(conversation_id, memory, merge=False):
        saved["conversation_id"] = conversation_id
        saved["memory"] = dict(memory)
        saved["merge"] = merge
        return memory

    monkeypatch.setattr(conversation_service.data_accessor, "save_conversation_key_facts_memory", _fake_save_memory)

    result = conversation_service._update_key_facts_memory(
        "conv-qa-preserve",
        user_query="请继续分析 src/new.py",
        project_path="D:/tmp/project",
        action="run_retrieval",
        task_mode="modify_existing",
        reason="需要补充证据",
        clarification_context={"selectedOptionLabels": ["稳妥修复"]},
    )

    assert saved["conversation_id"] == "conv-qa-preserve"
    assert saved["merge"] is False
    assert result["opencodeQa"]["sessionId"] == "oc-session-preserved"
    assert result["opencodeQa"]["status"] == "ready"
    assert result["opencodeQa"]["lastQuestion"] == "Explain this module"
    assert result["opencodeQaSessionId"] == "oc-session-preserved"
    assert result["retrievalCache"] == [{"query": "old question", "answer": "cached"}]
    assert result["selectedOptionLabels"] == ["保守方案", "稳妥修复"]
    assert result["pathHints"] == ["src/old.py", "src/new.py"]
    assert result["decisions"][-1]["action"] == "run_retrieval"


def test_run_conversation_turn_modify_existing_stays_unchanged_without_qa_context(monkeypatch):
    finalized, events = _stub_conversation_turn_infra(monkeypatch)
    qa_calls = {"count": 0}

    monkeypatch.setattr(
        conversation_service,
        "_normalize_action_decision",
        lambda *args, **kwargs: {"action": "run_retrieval", "task_mode": "modify_existing", "reason": "needs code change", "confidence": 0.93},
    )
    monkeypatch.setattr(
        multi_agent_service,
        "build_qa_context_bundle",
        lambda **kwargs: qa_calls.__setitem__("count", qa_calls["count"] + 1) or {"task_weight": "heavy"},
    )
    monkeypatch.setattr(
        conversation_service,
        "_try_inline_codegen_result",
        lambda **kwargs: {
            "session": {"sessionId": "inline-session-qa-guard"},
            "result": {
                "solution_packet": {},
                "output_protocol": {},
                "evidence_verdict": {},
                "opencode_kernel": {},
                "swarm_packet": {},
                "output_write": {},
            },
        },
    )
    monkeypatch.setattr(conversation_service, "_build_inline_codegen_answer", lambda *args, **kwargs: "inline answer")

    conversation_service._run_conversation_turn(
        session_id="sid-codegen-qa-guard",
        project_path="D:/tmp",
        user_query="帮我修改 metric.py 里的统计逻辑",
        conversation_id="cid-codegen-qa-guard",
        auto_start_multi_agent=True,
    )

    assert finalized["result"]["safeToCodegen"] is True
    assert finalized["result"]["answer"] == "inline answer"
    assert qa_calls["count"] == 0
    assert any(event_name == "turn.decided" and payload.get("action") == "start_multi_agent" for event_name, payload in events)


def test_run_conversation_turn_passes_rich_selected_node_into_heavy_qa_context(monkeypatch):
    finalized, _ = _stub_conversation_turn_infra(monkeypatch)
    captured = {}

    monkeypatch.setattr(
        conversation_service,
        "_normalize_action_decision",
        lambda *args, **kwargs: {"action": "run_retrieval", "task_mode": "none", "reason": "heavy qa", "confidence": 0.91},
    )
    monkeypatch.setattr(
        conversation_service,
        "_run_retrieval_tool",
        lambda *args, **kwargs: {
            "ok": True,
            "error": None,
            "highlights": [{"file": "metric.py", "label": "metric.py:1", "lineStart": 1, "lineEnd": 5}],
        },
    )
    monkeypatch.setattr(conversation_service, "_hydrate_highlights_with_snippets", lambda *args, **kwargs: [{"file": "metric.py"}])
    monkeypatch.setattr(conversation_service, "_suggest_validation_commands", lambda *args, **kwargs: [])
    monkeypatch.setattr(conversation_service, "_remember_retrieval_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(conversation_service, "_build_retrieval_search_summary", lambda *args, **kwargs: {})
    monkeypatch.setattr(conversation_service, "_build_retrieval_decision_trace", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        multi_agent_service,
        "build_qa_context_bundle",
        lambda **kwargs: captured.setdefault("qa_kwargs", kwargs) or {
            "qa_route": kwargs.get("qa_route"),
            "task_weight": kwargs.get("task_weight"),
        },
    )
    monkeypatch.setattr(conversation_service, "_generate_retrieval_answer", lambda *args, **kwargs: "retrieval answer")

    selected_node = {
        "id": "node-metrics-run",
        "name": "run",
        "method_signature": "pkg.metrics.run",
        "fqmn": "pkg.metrics.run",
        "signature": "pkg.metrics.run(self, data)",
        "function_chain": ["pkg.entry.main", "pkg.metrics.prepare", "pkg.metrics.run"],
        "main_method": "pkg.entry.main",
        "intermediate_methods": ["pkg.metrics.prepare"],
    }

    conversation_service._run_conversation_turn(
        session_id="sid-retrieval-heavy",
        project_path="D:/tmp",
        user_query="谁调用了 pkg.metrics.run，调用链证据是什么？",
        conversation_id="cid-retrieval-heavy",
        partition_id="partition-metrics",
        selected_node=selected_node,
        auto_start_multi_agent=False,
    )

    assert finalized["result"]["nextStep"] == "retrieval_answer"
    assert captured["qa_kwargs"]["preferred_partition_id"] == "partition-metrics"
    assert captured["qa_kwargs"]["selected_node"]["method_signature"] == "pkg.metrics.run"
    assert captured["qa_kwargs"]["selected_node"]["function_chain"] == [
        "pkg.entry.main",
        "pkg.metrics.prepare",
        "pkg.metrics.run",
    ]


def test_run_conversation_turn_keeps_codegen_selected_node_legacy_shape(monkeypatch):
    finalized, _ = _stub_conversation_turn_infra(monkeypatch)
    captured = {}

    monkeypatch.setattr(
        conversation_service,
        "_normalize_action_decision",
        lambda *args, **kwargs: {"action": "start_multi_agent", "task_mode": "modify_existing", "reason": "needs codegen", "confidence": 0.95},
    )

    def _fake_inline_codegen(**kwargs):
        captured["selected_node"] = kwargs.get("selected_node")
        return {
            "session": {"sessionId": "inline-session-codegen-shape"},
            "result": {
                "solution_packet": {},
                "output_protocol": {},
                "evidence_verdict": {},
                "opencode_kernel": {},
                "swarm_packet": {},
                "output_write": {},
            },
        }

    monkeypatch.setattr(conversation_service, "_try_inline_codegen_result", _fake_inline_codegen)
    monkeypatch.setattr(conversation_service, "_build_inline_codegen_answer", lambda *args, **kwargs: "inline answer")

    conversation_service._run_conversation_turn(
        session_id="sid-codegen-shape",
        project_path="D:/tmp",
        user_query="帮我修改 metric.py 里的统计逻辑",
        conversation_id="cid-codegen-shape",
        partition_id="partition-metrics",
        selected_node={
            "id": "node-metrics-run",
            "name": "run",
            "label": "run",
            "type": "Method",
            "file_path": "src/metric.py",
            "start_line": 12,
            "end_line": 28,
            "method_signature": "pkg.metrics.run",
            "fqmn": "pkg.metrics.run",
            "function_chain": ["pkg.entry.main", "pkg.metrics.run"],
            "main_method": "pkg.entry.main",
        },
        auto_start_multi_agent=True,
    )

    assert finalized["result"]["safeToCodegen"] is True
    assert captured["selected_node"] == {
        "id": "node-metrics-run",
        "name": "run",
        "label": "run",
        "type": "Method",
        "file_path": "src/metric.py",
        "start_line": 12,
        "end_line": 28,
    }


def test_api_conversation_reply_preserves_selected_node_and_partition_id(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(
        conversation_service.data_accessor,
        "get_conversation",
        lambda conversation_id: {
            "conversationId": conversation_id,
            "projectPath": str(tmp_path),
            "pendingQuestion": {"questionId": "q-1"},
            "originalQuery": "原始问题",
        },
    )
    monkeypatch.setattr(
        conversation_service,
        "_create_conversation_session",
        lambda *args, **kwargs: {"sessionId": "sid-reply", "status": "queued", "stage": "queued", "message": "ok"},
    )
    monkeypatch.setattr(conversation_service, "_emit_conversation_event", lambda *args, **kwargs: None)

    class _FakeThread:
        def __init__(self, *, target, args=(), daemon=None, **kwargs):
            captured["target"] = target
            captured["args"] = args

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(conversation_service.threading, "Thread", _FakeThread)

    client = create_app().test_client()
    response = client.post(
        "/api/conversations/conversation-1/reply",
        json={
            "project_path": str(tmp_path),
            "answer": "继续分析调用链",
            "partition_id": "partition-metrics",
            "selected_node": {
                "id": "node-metrics-run",
                "method_signature": "pkg.metrics.run",
                "fqmn": "pkg.metrics.run",
                "function_chain": ["pkg.entry.main", "pkg.metrics.run"],
            },
        },
    )

    assert response.status_code == 200
    assert captured["started"] is True
    assert captured["args"][4] == {
        "id": "node-metrics-run",
        "method_signature": "pkg.metrics.run",
        "fqmn": "pkg.metrics.run",
        "function_chain": ["pkg.entry.main", "pkg.metrics.run"],
    }
    assert captured["args"][5] == "partition-metrics"
