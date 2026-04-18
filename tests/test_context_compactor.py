import pytest
from llm.agent.core.context_compactor import ContextCompactor
from llm.llm_api import LLMApi

def test_should_compact():
    short_msgs = [{"role": "user", "content": "hello"}]
    assert ContextCompactor.should_compact(short_msgs, threshold=100) == False
    
    long_msgs = [{"role": "user", "content": "a" * 101}]
    assert ContextCompactor.should_compact(long_msgs, threshold=100) == True

def test_compact_mock(monkeypatch):
    # Mock LLMApi
    class MockLLM:
        def chat(self, messages, model=None):
            return {"content": "<summary>Compacted Context</summary>"}
            
    monkeypatch.setattr(LLMApi, "chat", lambda self, messages, model=None: MockLLM().chat(messages, model))
    
    msgs = [{"role": "user", "content": "long history"}]
    summary = ContextCompactor.compact(msgs)
    
    assert "<summary>" in summary
    assert "Compacted Context" in summary

if __name__ == "__main__":
    print("Testing Should Compact...")
    if not ContextCompactor.should_compact([{"role":"u", "content":"hi"}], 100): print("PASS")
    else: print("FAIL")
    
    print("Testing Compact (Mock)...")
    # Simple manual mock
    original_chat = LLMApi.chat
    LLMApi.chat = lambda self, m, model=None: {"content": "summary"}
    res = ContextCompactor.compact([])
    if res == "summary": print("PASS")
    else: print(f"FAIL: {res}")
    LLMApi.chat = original_chat
