
import os
import pickle
from pathlib import Path

def export_to_markdown(metadata_path, output_md_path):
    """从 metadata.pkl 导出文本内容到 Markdown"""
    if not os.path.exists(metadata_path):
        print(f"Error: {metadata_path} not found.")
        return

    try:
        with open(metadata_path, 'rb') as f:
            data = pickle.load(f)
        
        id_to_text = data.get('id_to_text', {})
        if not id_to_text:
            print("No text data found in metadata.")
            return

        with open(output_md_path, 'w', encoding='utf-8') as f:
            f.write("# RAG 知识库全量文本预览\n\n")
            f.write(f"此文件包含 RAG Agent 检索使用的所有自然语言知识块（共 {len(id_to_text)} 条）。\n\n")
            f.write("---\n\n")
            
            # 按 ID 排序导出
            for idx in sorted(id_to_text.keys()):
                content = id_to_text[idx]
                f.write(f"## 知识块 ID: {idx}\n\n")
                f.write(content)
                f.write("\n\n---\n\n")
        
        print(f"成功导出知识库预览到: {output_md_path}")
        return output_md_path
    except Exception as e:
        print(f"Export failed: {e}")
        return None

if __name__ == "__main__":
    # 默认路径
    base_dir = r"D:\代码仓库生图\create_graph"
    meta_path = os.path.join(base_dir, "data", "graph_index", "meta.pkl")
    output_path = os.path.join(base_dir, "data", "graph_index", "knowledge_base_preview.md")
    
    export_to_markdown(meta_path, output_path)
