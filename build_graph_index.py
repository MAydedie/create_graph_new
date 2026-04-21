
import os
import sys
import argparse
from pathlib import Path
import logging

# Add project root to path (Ensure this is robust)
# Use the directory of this script as base
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from llm.capability.graph_loader import GraphKnowledgeLoader
from llm.rag_core.vector_db import FAISSVectorDB
from llm.rag_core.embedding_model import EmbeddingModel
from config.config import EMBEDDING_CONFIG, VECTOR_DB_CONFIG


def build_index(project_name: str = None, output_dir: str = None, experience_paths_dir: str = None):
    """
    构建 RAG 索引
    
    Args:
        project_name: 项目名称，用于创建独立索引目录。如 'catnet' -> data/catnet_index/
        output_dir: 自定义分析输出目录（可选）
        experience_paths_dir: 自定义经验路径目录（可选）
    """
    # Setup simple logging to console
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("GraphIndexBuilder")
    
    print(f"[build_graph_index] Starting RAG index build...", flush=True)
    if project_name:
        print(f"[build_graph_index] 📁 Project: {project_name}", flush=True)
    
    # 1. 确定数据目录
    if output_dir is None:
        if project_name and project_name != 'self':
            output_dir = os.path.join(BASE_DIR, f"output_{project_name}_analysis")
        else:
            output_dir = os.path.join(BASE_DIR, "output_self_analysis")
    
    if experience_paths_dir is None:
        if project_name and project_name != 'self':
            experience_paths_dir = os.path.join(BASE_DIR, f"output_{project_name}_analysis", "experience_paths")
        else:
            experience_paths_dir = os.path.join(BASE_DIR, "output_analysis", "experience_paths")
    
    # 2. Load Data (including experience paths / functional paths)
    loader = GraphKnowledgeLoader(output_dir=output_dir)
    logger.info("Loading graph data and experience paths...")
    print(f"[build_graph_index] Loading data from {output_dir} and {experience_paths_dir}...", flush=True)
    
    chunks = loader.load_all(
        experience_paths_dir=experience_paths_dir
    )
    logger.info(f"Loaded {len(chunks)} total chunks.")
    print(f"[build_graph_index] Loaded {len(chunks)} chunks.", flush=True)
    
    if not chunks:
        logger.error("No chunks loaded. Aborting.")
        print(f"[build_graph_index] ❌ No chunks loaded. Aborting.", flush=True)
        return

    # 3. Initialize Embedding Model
    logger.info("Initializing Embedding Model...")
    print(f"[build_graph_index] Initializing Embedding Model...", flush=True)
    embedding_model = EmbeddingModel(model_name=EMBEDDING_CONFIG["model_name"])
    
    # 4. Vectorize
    logger.info("Vectorizing chunks...")
    print(f"[build_graph_index] Vectorizing {len(chunks)} chunks...", flush=True)
    texts = [c["content"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    
    # Fix: encode_chunks expects list of dicts with 'content'
    chunk_list = [{"content": t} for t in texts]
    
    try:
        embeddings, _ = embedding_model.encode_chunks(
            chunk_list, 
            text_key="content",
            batch_size=32
        )
    except Exception as e:
        logger.error(f"Vectorization failed: {e}")
        print(f"[build_graph_index] ❌ Vectorization failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return
    
    # 5. Build Vector DB
    logger.info("Building FAISS Index...")
    print(f"[build_graph_index] Building FAISS Index...", flush=True)
    vector_db = FAISSVectorDB(
        embedding_dim=VECTOR_DB_CONFIG["embedding_dim"],
        index_type=VECTOR_DB_CONFIG["index_type"]
    )
    vector_db.add_vectors(embeddings, texts, metadatas)
    
    # 6. Save - 根据项目名确定保存目录
    if project_name and project_name != 'self':
        save_dir = os.path.join(BASE_DIR, "data", f"{project_name}_index")
    else:
        save_dir = os.path.join(BASE_DIR, "data", "graph_index")
    
    os.makedirs(save_dir, exist_ok=True)
    
    index_path = os.path.join(save_dir, "faiss.bin")
    meta_path = os.path.join(save_dir, "meta.pkl")
    
    vector_db.save(index_path, meta_path)
    logger.info(f"Index saved to {save_dir}")
    print(f"[build_graph_index] ✅ RAG Index saved to {save_dir}", flush=True)
    
    # 7. Export Preview (Natural Language Text)
    print(f"[build_graph_index] Exporting preview to {save_dir}...", flush=True)
    try:
        from export_knowledge_base import export_to_markdown
        preview_path = os.path.join(save_dir, "knowledge_base_preview.md")
        result = export_to_markdown(meta_path, preview_path)
        if result:
             print(f"[build_graph_index] ✅ Knowledge base preview exported to: {result}", flush=True)
        else:
             print(f"[build_graph_index] ⚠️ Knowledge base preview export returned None.", flush=True)
    except Exception as e:
        logger.warning(f"Failed to export preview: {e}")
        print(f"[build_graph_index] ❌ Failed to export preview: {e}", flush=True)
        import traceback
        traceback.print_exc()
    
    return save_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build RAG index for code analysis")
    parser.add_argument('--project', '-p', default=None, 
                        help='Project name for independent index (e.g., catnet)')
    parser.add_argument('--output-dir', '-o', default=None,
                        help='Custom output directory for analysis results')
    parser.add_argument('--exp-paths-dir', '-e', default=None,
                        help='Custom experience paths directory')
    
    args = parser.parse_args()
    
    build_index(
        project_name=args.project,
        output_dir=args.output_dir,
        experience_paths_dir=args.exp_paths_dir
    )
