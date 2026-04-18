from llm.rag_core.rag_system import RAGSystem
from config.config import DEEPSEEK_API_KEY, RAG_CONFIG

print("Import Successful!")
print(f"DeepSeek Configured: {bool(DEEPSEEK_API_KEY)}")
print(f"RAG Top K: {RAG_CONFIG['retrieval_top_k']}")

try:
    rag = RAGSystem(rebuild_index=False)
    print("RAG System Initialized (Mock check)")
except Exception as e:
    print(f"RAG Init Error (Expected if data missing, but imports work): {e}")
