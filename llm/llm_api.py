from llm.rag_core.llm_api import DeepSeekAPI

class LLMApi(DeepSeekAPI):
    """
    Unified LLM API wrapper for Agent tools.
    Inherits from DeepSeekAPI for compatibility.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # Can add standardized methods here if needed, 
    # but DeepSeekAPI.chat(messages=...) is sufficient for now.
