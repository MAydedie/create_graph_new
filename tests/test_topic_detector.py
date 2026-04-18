import pytest
from llm.agent.core.topic_detector import TopicDetector
from llm.llm_api import LLMApi
import json

def test_detect_new_topic(monkeypatch):
    class MockLLM:
        def chat(self, messages, model=None):
            return {"content": json.dumps({"isNewTopic": True, "title": "New App"})}
            
    monkeypatch.setattr(LLMApi, "chat", lambda self, messages, model=None: MockLLM().chat(messages, model))
    
    result = TopicDetector.detect("Start a new project", "Old context")
    assert result["isNewTopic"] == True
    assert result["title"] == "New App"

def test_detect_same_topic(monkeypatch):
    class MockLLM:
        def chat(self, messages, model=None):
            return {"content": json.dumps({"isNewTopic": False, "title": None})}
            
    monkeypatch.setattr(LLMApi, "chat", lambda self, messages, model=None: MockLLM().chat(messages, model))
    
    result = TopicDetector.detect("Continue this", "Old context")
    assert result["isNewTopic"] == False

def test_json_parse_error(monkeypatch):
    class MockLLM:
        def chat(self, messages, model=None):
            return {"content": "Not JSON"}
            
    monkeypatch.setattr(LLMApi, "chat", lambda self, messages, model=None: MockLLM().chat(messages, model))
    
    result = TopicDetector.detect("msg")
    # Should default to False on error
    assert result["isNewTopic"] == False
    assert "error" in result or result["title"] is None

if __name__ == "__main__":
    print("Run via pytest")
