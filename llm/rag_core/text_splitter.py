"""
文本分片模块
功能：将Q&A对格式化为适合向量化的文本片段
"""
from typing import List, Dict, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter


class QATextSplitter:
    """Q&A文本分片器"""
    
    def __init__(self, chunk_format: str = "qa_pair"):
        """
        初始化文本分片器
        
        Args:
            chunk_format: 分片格式
                - "qa_pair": 问题-答案对作为完整单元（推荐）
                - "separate": 问题和答案分别分片
        """
        self.chunk_format = chunk_format
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,  # 增加分片大小以保留更多上下文 (was 500)
            chunk_overlap=100, # 稍微增加重叠 (was 50)
            length_function=len,
        )
    
    def format_qa_pair(self, question: str, answer: str) -> str:
        """
        格式化问题-答案对为文本片段
        
        Args:
            question: 问题文本
            answer: 答案文本
            
        Returns:
            格式化后的文本片段
        """
        # 清理文本
        question = question.strip() if question else ""
        answer = answer.strip() if answer else ""
        
        # 格式化：问题-答案对作为完整单元
        if question and answer:
            return f"问题：{question}\n答案：{answer}"
        elif question:
            return f"问题：{question}"
        elif answer:
            return f"答案：{answer}"
        else:
            return ""
    
    def split_qa_pairs(self, qa_pairs: List[Dict[str, str]]) -> List[Dict[str, any]]:
        """
        将Q&A对列表转换为分片列表
        
        Args:
            qa_pairs: Q&A对列表，格式：[{"question": "...", "answer": "...", "row_id": 2, ...}, ...]
            
        Returns:
            分片列表，格式：[{"text": "问题：...\n答案：...", "metadata": {...}}, ...]
        """
        chunks = []
        
        for qa_pair in qa_pairs:
            question = qa_pair.get("question", "")
            answer = qa_pair.get("answer", "")
            
            if self.chunk_format == "qa_pair":
                # 方案1：问题-答案对作为完整单元（推荐）
                chunk_text = self.format_qa_pair(question, answer)
                
                if chunk_text:  # 只添加非空片段
                    chunk = {
                        "text": chunk_text,
                        "metadata": {
                            "question": question,
                            "answer": answer,
                            "row_id": qa_pair.get("row_id", 0),
                            "source": qa_pair.get("source", ""),
                            "chunk_type": "qa_pair",
                            "chunk_index": len(chunks)  # 当前分片的索引
                        }
                    }
                    chunks.append(chunk)
            
            elif self.chunk_format == "separate":
                # 方案2：问题和答案分别分片（可选，暂不使用）
                if question:
                    chunk = {
                        "text": f"问题：{question}",
                        "metadata": {
                            "question": question,
                            "answer": "",
                            "row_id": qa_pair.get("row_id", 0),
                            "source": qa_pair.get("source", ""),
                            "chunk_type": "question",
                            "chunk_index": len(chunks)
                        }
                    }
                    chunks.append(chunk)
                
                if answer:
                    # 答案片段保留问题作为上下文
                    chunk_text = self.format_qa_pair(question, answer)
                    chunk = {
                        "text": chunk_text,
                        "metadata": {
                            "question": question,
                            "answer": answer,
                            "row_id": qa_pair.get("row_id", 0),
                            "source": qa_pair.get("source", ""),
                            "chunk_type": "answer",
                            "chunk_index": len(chunks)
                        }
                    }
                    chunks.append(chunk)
        
        return chunks
    
    def split_long_text(self, text: str, max_length: int = 500) -> List[str]:
        """
        切分超长文本（如果需要）
        
        Args:
            text: 要切分的文本
            max_length: 最大长度
            
        Returns:
            切分后的文本列表
        """
        if len(text) <= max_length:
            return [text]
        
        # 使用langchain的文本分片器
        chunks = self.text_splitter.split_text(text)
        return chunks


def split_qa_data(qa_pairs: List[Dict[str, str]], format_type: str = "qa_pair") -> List[Dict[str, any]]:
    """
    便捷函数：将Q&A对列表转换为分片列表
    
    Args:
        qa_pairs: Q&A对列表
        format_type: 分片格式，"qa_pair" 或 "separate"
        
    Returns:
        分片列表
    """
    splitter = QATextSplitter(chunk_format=format_type)
    return splitter.split_qa_pairs(qa_pairs)


if __name__ == "__main__":
    # 测试代码
    from data_loader import load_qa_data
    
    file_path = r"资料\喜哥帮AI客服Q&A【知识库】20260119.xlsx"
    
    try:
        # 加载数据
        print("=" * 60)
        print("步骤1: 加载数据")
        print("=" * 60)
        qa_pairs = load_qa_data(file_path)
        print(f"加载了 {len(qa_pairs)} 条Q&A对\n")
        
        # 分片
        print("=" * 60)
        print("步骤2: 文本分片")
        print("=" * 60)
        splitter = QATextSplitter(chunk_format="qa_pair")
        chunks = splitter.split_qa_pairs(qa_pairs)
        print(f"生成了 {len(chunks)} 个文本片段\n")
        
        # 显示统计信息
        print("=" * 60)
        print("分片统计信息")
        print("=" * 60)
        chunk_lengths = [len(chunk["text"]) for chunk in chunks]
        if chunk_lengths:
            print(f"片段总数: {len(chunks)}")
            print(f"平均长度: {sum(chunk_lengths) / len(chunk_lengths):.2f} 字符")
            print(f"最小长度: {min(chunk_lengths)} 字符")
            print(f"最大长度: {max(chunk_lengths)} 字符")
        
        # 显示前3个分片示例
        print("\n" + "=" * 60)
        print("前3个分片示例")
        print("=" * 60)
        for i, chunk in enumerate(chunks[:3], 1):
            print(f"\n【分片 {i}】")
            print(f"行号: {chunk['metadata']['row_id']}")
            print(f"类型: {chunk['metadata']['chunk_type']}")
            print(f"文本长度: {len(chunk['text'])} 字符")
            print(f"文本内容:\n{chunk['text'][:200]}..." if len(chunk['text']) > 200 else f"文本内容:\n{chunk['text']}")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()



