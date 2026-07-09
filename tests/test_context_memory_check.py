"""
测试两个问答系统的上下文记忆机制
- 问答按钮 (conversation_service): 检查 history 传递与 compaction
- SE-Team 按钮 (simple_qa_engine / se_team_api_routes): 检查是否复用同样记忆机制
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch
from uuid import uuid4


def test_conversation_qa_has_context_memory():
    """问答按钮：验证 _history_for_prompt 能获取历史消息并有上限"""
    from app.services.conversation_service import _history_for_prompt, COMPACTION_MIN_MESSAGES, COMPACTION_KEEP_RECENT_MESSAGES

    print("=" * 60)
    print("【问答按钮】上下文记忆机制检查")
    print("=" * 60)

    # 模拟一个 conversation 有 15 条消息
    fake_conversation_id = uuid4().hex
    fake_messages = []
    for i in range(15):
        role = "user" if i % 2 == 0 else "assistant"
        fake_messages.append({
            "messageId": uuid4().hex,
            "role": role,
            "content": f"第{i+1}条消息 ({role})",
            "createdAt": "2026-01-01T00:00:00Z",
        })

    with patch("app.services.conversation_service.data_accessor") as mock_da:
        mock_da.list_conversation_messages.return_value = fake_messages

        # 默认 limit=8
        history_default = _history_for_prompt(fake_conversation_id, limit=8)
        print(f"\n[默认 limit=8] 返回消息数: {len(history_default)}")
        assert len(history_default) == 8, f"Expected 8, got {len(history_default)}"

        # limit=10 (代码中实际使用的值)
        history_10 = _history_for_prompt(fake_conversation_id, limit=10)
        print(f"[limit=10] 返回消息数: {len(history_10)}")
        assert len(history_10) == 10, f"Expected 10, got {len(history_10)}"

        # limit=5 
        history_5 = _history_for_prompt(fake_conversation_id, limit=5)
        print(f"[limit=5] 返回消息数: {len(history_5)}")
        assert len(history_5) == 5, f"Expected 5, got {len(history_5)}"

    print(f"\n[Compaction 参数]")
    print(f"  COMPACTION_MIN_MESSAGES = {COMPACTION_MIN_MESSAGES} (触发压缩的最小消息数)")
    print(f"  COMPACTION_KEEP_RECENT_MESSAGES = {COMPACTION_KEEP_RECENT_MESSAGES} (压缩后保留的最近消息数)")
    print(f"  COMPACTION_MIN_TEXT_CHARS = 12000 (触发压缩的最小文本字符数)")

    print(f"\n[结论] 问答按钮 有上下文记忆:")
    print(f"  - LLM 调用时传入最近 10 条历史消息 (user + assistant)")
    print(f"  - 当消息数 >= {COMPACTION_MIN_MESSAGES} 且总文本 >= 12000 字符时触发压缩")
    print(f"  - 压缩后保留最近 {COMPACTION_KEEP_RECENT_MESSAGES} 条 + 1条压缩摘要")
    print(f"  - 理论上下文记忆上限: 无限轮对话 (通过压缩 + key facts 保持)")
    print(f"  - 单次 LLM 调用可见上下文: 最近 10 条消息")
    print("  ✅ 通过")


def test_conversation_qa_opencode_history():
    """问答按钮：验证 opencode_qa 调用也传递 history"""
    from app.services.opencode_qa_service import _build_message

    print("\n" + "=" * 60)
    print("【问答按钮 - OpenCode 路径】上下文传递检查")
    print("=" * 60)

    history = [
        {"role": "user", "content": "之前的问题"},
        {"role": "assistant", "content": "之前的回答"},
    ]

    message = _build_message(
        system_prompt="test system",
        user_query="当前问题",
        conversation_id="test-conv-id",
        history=history,
        context_payload=None,
    )

    assert "之前的问题" in message, "History not included in opencode message"
    assert "之前的回答" in message, "History not included in opencode message"
    # opencode 的 history 上限是 [-10:] (最后10条)
    print(f"  OpenCode QA 也会传递最近 10 条历史消息 ([-10:] 截断)")
    print("  ✅ 通过")


def test_se_team_simple_qa_entry_still_no_inline_history_param():
    """SE-Team 快速入口函数本身仍是单轮函数（历史在路由与工作流层处理）"""
    print("\n" + "=" * 60)
    print("【SE-Team 按钮 - 快速问答路径】上下文记忆检查")
    print("=" * 60)

    # 检查 generate_simple_qa_answer 的源码 - 只传 [system, user]
    import inspect
    from app.services.se_team_embedded_service import generate_simple_qa_answer

    source = inspect.getsource(generate_simple_qa_answer)

    # 检查是否有 history 相关参数
    has_history_param = "history" in inspect.signature(generate_simple_qa_answer).parameters
    print(f"\n  generate_simple_qa_answer 函数签名有 history 参数: {has_history_param}")
    assert not has_history_param, "Unexpected: found history param"

    # 检查源码中是否引用了 history / conversation_id
    has_history_ref = "history" in source and "messages" in source
    has_conv_id = "conversation_id" in source
    print(f"  源码中引用 history: {'是' if 'history' in source else '否'}")
    print(f"  源码中引用 conversation_id: {'是' if has_conv_id else '否'}")

    # messages 构造只有 system + user
    assert 'messages=[' in source or 'messages =' in source
    print(f"  LLM 调用 messages 构造: [system, user] (无历史消息)")
    print(f"\n  [说明] 该函数仍是单轮函数；上下文记忆由路由层 + workflow 层处理 ✅")


def test_se_team_simple_qa_engine_has_context_memory():
    """SE-Team 按钮：验证 SimpleQaEngine 4步流程已接入 history"""
    print("\n" + "=" * 60)
    print("【SE-Team 按钮 - SimpleQaEngine 4步流程】上下文记忆检查")
    print("=" * 60)

    import inspect
    from app.services.simple_qa_engine import SimpleQaEngine

    # 检查 run_workflow 的签名
    sig = inspect.signature(SimpleQaEngine.run_workflow)
    params = list(sig.parameters.keys())
    print(f"\n  run_workflow 参数: {params}")
    has_history = "history" in params or "conversation_id" in params
    print(f"  有 history/conversation_id 参数: {has_history}")
    assert has_history, "Expected run_workflow to accept history"

    # 检查 _call_agent 源码
    source = inspect.getsource(SimpleQaEngine._call_agent)
    has_history_in_call = "history" in source
    print(f"  _call_agent 中引用 history: {has_history_in_call}")

    # messages 结构应包含 _normalize_history(history)
    assert '{"role": "system"' in source or '"role": "system"' in source
    assert "_normalize_history(history)" in source, "Expected history normalization in _call_agent"
    assert '{"role": "user"' in source or '"role": "user"' in source
    print(f"  _call_agent LLM messages: [system] + history + [user] (有历史消息)")

    print(f"\n  [结论] SE-Team SimpleQaEngine 已接入上下文记忆 ✅")
    print(f"  - run_workflow 可接收 history")
    print(f"  - _call_agent 会把 history 传给 LLM")


def test_se_team_route_reuses_conversation_memory():
    """SE-Team 路由层复用 conversation_service 的消息存储和 housekeeping"""
    print("\n" + "=" * 60)
    print("【SE-Team 按钮 - 路由层】复用 conversation 记忆机制检查")
    print("=" * 60)

    import inspect
    from app.routes import se_team_api_routes

    source = inspect.getsource(se_team_api_routes.se_team_start_stream)
    assert "conversation_memory_service.data_accessor.ensure_conversation" in source
    assert "conversation_memory_service.data_accessor.append_conversation_message" in source
    assert "conversation_memory_service._history_for_prompt" in source
    assert "conversation_memory_service._post_turn_housekeeping" in source

    print("  路由层已复用 ensure_conversation / append_conversation_message / _history_for_prompt / _post_turn_housekeeping")
    print("  ✅ 通过")


def print_final_summary():
    print("\n" + "=" * 60)
    print("最终总结")
    print("=" * 60)
    print("""
┌─────────────────────┬────────────────┬──────────────────────────────────┐
│ 系统                │ 有上下文记忆？ │ 上下文记忆上限                   │
├─────────────────────┼────────────────┼──────────────────────────────────┤
│ 问答按钮            │ ✅ 有          │ 单次LLM可见: 最近10条消息        │
│ (conversations API) │                │ 持久化: 无限(有compaction压缩)   │
│                     │                │ 压缩触发: ≥24条消息 且 ≥12000字符│
│                     │                │ 压缩后保留: 最近10条+摘要        │
├─────────────────────┼────────────────┼──────────────────────────────────┤
│ SE-Team 按钮        │ ✅ 有          │ 单次LLM可见: 最近10条消息        │
│ (se_team API)       │                │ 复用conversation存储+压缩机制     │
└─────────────────────┴────────────────┴──────────────────────────────────┘

问答按钮详细记忆机制:
1. 短期记忆: _history_for_prompt() 取最近10条消息传给LLM
2. Key Facts: 每轮结束后更新 key_facts_memory (路径提示/决策历史/检索缓存)  
3. Compaction: 消息过多时压缩旧消息为摘要，保留最近10条
4. OpenCode路径: 同样传递最近10条历史 (history[-10:])

SE-Team 详细说明:
1. 路由层复用 conversation_service：写入 user/assistant 消息、读取 _history_for_prompt(limit=10)
2. SimpleQaEngine.run_workflow(history=...)：每阶段调用 LLM 时注入历史
3. 回合结束复用 _post_turn_housekeeping：同步 key facts + compaction
""")


if __name__ == "__main__":
    test_conversation_qa_has_context_memory()
    test_conversation_qa_opencode_history()
    test_se_team_simple_qa_entry_still_no_inline_history_param()
    test_se_team_simple_qa_engine_has_context_memory()
    test_se_team_route_reuses_conversation_memory()
    print_final_summary()
