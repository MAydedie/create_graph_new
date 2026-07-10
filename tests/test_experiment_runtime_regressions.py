import hashlib

from analysis.path_semantic_analyzer import PathSemanticAnalyzer
from llm.code_understanding_agent import CodeUnderstandingAgent


class _FakeLlmHelper:
    def __init__(self):
        self.calls = []

    def call(self, **kwargs):
        self.calls.append(kwargs)
        assert '"nodes"' in kwargs["user_prompt"]
        return '{"nodes": [], "edges": []}'


def test_path_semantic_analyzer_exposes_helper_methods():
    analyzer = PathSemanticAnalyzer(project_path="/repo")

    result = analyzer.extract_path_semantics("/repo/tests/code_parser.py")

    assert result["path_tokens"] == ["tests", "code", "parser"]
    assert result["is_test"] is True
    assert "解析" in result["suggested_functions"]


def test_path_semantic_analyzer_handles_camel_case():
    analyzer = PathSemanticAnalyzer(project_path="/repo")

    result = analyzer.extract_path_semantics("/repo/services/myParserService.py")

    assert result["path_tokens"] == ["services", "my", "parser", "service"]
    assert result["naming_style"] == "camelCase"


def test_path_io_prompt_formats_and_uses_stable_cache_key():
    agent = CodeUnderstandingAgent(api_key="test-key")
    fake_helper = _FakeLlmHelper()
    object.__setattr__(agent, "llm_helper", fake_helper)

    result = agent.generate_path_input_output_graph(["module.entry"], analyzer_report=None)

    assert result == {"nodes": [], "edges": []}
    expected_digest = hashlib.sha256(b"module.entry").hexdigest()
    assert fake_helper.calls[0]["cache_key"] == f"io_graph::{expected_digest}"
