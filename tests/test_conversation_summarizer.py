import pytest
from llm.agent.core.conversation_summarizer import ConversationSummarizer
from llm.llm_api import LLMApi

def test_summarize_empty():
    assert ConversationSummarizer.summarize([]) == "New Conversation"

def test_summarize_mock(monkeypatch):
    class MockLLM:
        def chat(self, messages, model=None):
            return {"content": "Fixing login bug"}
            
    monkeypatch.setattr(LLMApi, "chat", lambda self, messages, model=None: MockLLM().chat(messages, model))
    
    msgs = [{"role": "user", "content": "help me fix login"}]
    title = ConversationSummarizer.summarize(msgs)
    assert title == "Fixing login bug"
    assert len(title) <= 50

def test_summarize_truncate(monkeypatch):
    long_title = "a" * 100
    class MockLLM:
        def chat(self, messages, model=None):
            return {"content": long_title}
            
    monkeypatch.setattr(LLMApi, "chat", lambda self, messages, model=None: MockLLM().chat(messages, model))
    
    msgs = [{"role": "user", "content": "test"}]
    title = ConversationSummarizer.summarize(msgs)
    assert len(title) == 50

if __name__ == "__main__":
    print("Run via pytest")
