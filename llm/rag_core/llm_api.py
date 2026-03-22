"""
大模型API模块
功能：集成DeepSeek API，实现文本生成功能
"""
import requests
import json
from typing import List, Dict, Optional
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.config import DEEPSEEK_API_KEY, DEEPSEEK_API_BASE, DEEPSEEK_MODEL, RAG_CONFIG


class DeepSeekAPI:
    """DeepSeek API客户端"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, 
                 model: Optional[str] = None, timeout: int = 120):
        """
        初始化DeepSeek API客户端
        
        Args:
            api_key: API密钥，如果为None则从配置文件读取
            base_url: API基础URL，如果为None则从配置文件读取
            model: 模型名称，如果为None则从配置文件读取
            timeout: API请求超时时间（秒），默认120秒
        """
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.base_url = base_url or DEEPSEEK_API_BASE
        self.model = model or DEEPSEEK_MODEL
        self.timeout = timeout
        
        if not self.api_key:
            raise ValueError("API Key未设置！请检查config/config.json或环境变量DEEPSEEK_API_KEY")
        
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        print(f"DeepSeek API客户端初始化成功")
        print(f"  API Base: {self.base_url}")
        print(f"  Model: {self.model}")
        print(f"  Timeout: {self.timeout}s")
    
    def build_prompt(self, query: str, context_chunks: List[Dict], 
                    system_prompt: Optional[str] = None) -> str:
        """
        构建Prompt
        
        Args:
            query: 用户查询
            context_chunks: 上下文片段列表（重排后的结果）
            system_prompt: 系统提示词，如果为None则使用默认提示词
            
        Returns:
            完整的Prompt字符串
        """
        if system_prompt is None:
            system_prompt = """你是一个专业的AI客服助手。请根据提供的知识库内容回答用户的问题。

要求：
1. 基于提供的知识库内容回答问题
2. 如果知识库中没有相关信息，请诚实说明
3. 回答要准确、简洁、友好
4. 如果知识库中有多个相关信息，请综合回答"""
        
        # 构建上下文
        context_text = ""
        for i, chunk in enumerate(context_chunks, 1):
            text = chunk.get("text", "")
            metadata = chunk.get("metadata", {})
            question = metadata.get("question", "")
            answer = metadata.get("answer", "")
            
            context_text += f"\n【参考内容 {i}】\n"
            if question:
                context_text += f"问题：{question}\n"
            if answer:
                context_text += f"答案：{answer}\n"
            elif text:
                context_text += f"{text}\n"
        
        # 构建完整Prompt
        full_prompt = f"""{system_prompt}

## 知识库内容：
{context_text}

## 用户问题：
{query}

## 回答："""
        
        return full_prompt
    
    def chat(self, messages: List[Dict], temperature: float = 0.7, 
            max_tokens: int = 1000, timeout: Optional[int] = None) -> Dict:
        """
        调用Chat API
        
        Args:
            messages: 消息列表，格式：[{"role": "user", "content": "..."}]
            temperature: 生成温度，默认0.7
            max_tokens: 最大生成token数，默认1000
            timeout: 超时时间（秒），如果为None则使用初始化时的设置
            
        Returns:
            API响应字典
        """
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # 使用传入的timeout或默认timeout
        request_timeout = timeout if timeout is not None else self.timeout
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=request_timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"API调用失败: {str(e)}")
    
    def generate_answer(self, query: str, context_chunks: List[Dict], 
                       system_prompt: Optional[str] = None,
                       temperature: Optional[float] = None,
                       max_tokens: Optional[int] = None,
                       timeout: Optional[int] = None) -> str:
        """
        生成答案
        
        Args:
            query: 用户查询
            context_chunks: 上下文片段列表
            system_prompt: 系统提示词
            temperature: 生成温度
            max_tokens: 最大生成token数
            timeout: 超时时间
            
        Returns:
            生成的答案文本
        """
        # 使用配置的默认值
        temperature = temperature if temperature is not None else RAG_CONFIG.get("temperature", 0.7)
        max_tokens = max_tokens if max_tokens is not None else RAG_CONFIG.get("max_tokens", 1000)
        
        # 构建Prompt
        prompt = self.build_prompt(query, context_chunks, system_prompt)
        
        # 构建消息
        messages = [
            {"role": "user", "content": prompt}
        ]
        
        # 调用API
        print(f"正在调用DeepSeek API生成答案...")
        response = self.chat(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
        
        # 提取答案
        if "choices" in response and len(response["choices"]) > 0:
            answer = response["choices"][0]["message"]["content"]
            return answer.strip()
        else:
            raise Exception(f"API返回格式异常: {response}")
    
    def generate_with_retry(self, query: str, context_chunks: List[Dict], 
                           max_retries: int = 3, **kwargs) -> str:
        """
        带重试的生成答案
        
        Args:
            query: 用户查询
            context_chunks: 上下文片段列表
            max_retries: 最大重试次数
            **kwargs: 其他参数传递给generate_answer
            
        Returns:
            生成的答案文本
        """
        for attempt in range(max_retries):
            try:
                return self.generate_answer(query, context_chunks, **kwargs)
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"生成失败，正在重试 ({attempt + 1}/{max_retries})...")
                    import time
                    time.sleep(2 ** attempt)  # 指数退避
                else:
                    raise Exception(f"生成答案失败（已重试{max_retries}次）: {str(e)}")


def create_llm_api(api_key: Optional[str] = None) -> DeepSeekAPI:
    """
    便捷函数：创建LLM API客户端
    
    Args:
        api_key: API密钥，如果为None则从配置文件读取
        
    Returns:
        DeepSeekAPI实例
    """
    return DeepSeekAPI(api_key=api_key, timeout=120)


if __name__ == "__main__":
    # 测试代码
    from retriever import Retriever
    from reranker import Reranker
    from vector_db import FAISSVectorDB
    from embedding_model import EmbeddingModel
    import os
    
    data_dir = "data"
    
    try:
        # 步骤1: 加载索引
        print("=" * 60)
        print("步骤1: 加载索引")
        print("=" * 60)
        index_path = os.path.join(data_dir, "faiss_index.bin")
        metadata_path = os.path.join(data_dir, "metadata.pkl")
        
        if not (os.path.exists(index_path) and os.path.exists(metadata_path)):
            print("索引不存在，请先运行前面的步骤创建索引")
            exit(1)
        
        vector_db = FAISSVectorDB.load(index_path, metadata_path)
        print(f"加载了 {vector_db.get_total_vectors()} 个向量\n")
        
        # 步骤2: 创建召回器和重排器
        print("=" * 60)
        print("步骤2: 创建召回器和重排器")
        print("=" * 60)
        embedding_model = EmbeddingModel()
        retriever = Retriever(vector_db, embedding_model)
        reranker = Reranker()
        
        # 步骤3: 创建LLM API客户端
        print("=" * 60)
        print("步骤3: 创建LLM API客户端")
        print("=" * 60)
        llm_api = DeepSeekAPI()
        
        # 步骤4: 测试完整流程
        print("=" * 60)
        print("步骤4: 测试完整RAG流程")
        print("=" * 60)
        
        test_query = "怎么添加货单订单？"
        print(f"用户查询: {test_query}\n")
        
        # 召回
        print("1. 召回阶段...")
        retrieval_results = retriever.retrieve(test_query, top_k=RAG_CONFIG["retrieval_top_k"])
        print(f"   召回了 {len(retrieval_results)} 个结果")
        
        # 重排
        print("2. 重排阶段...")
        reranked_results = reranker.rerank_with_metadata(
            test_query, 
            retrieval_results, 
            top_k=RAG_CONFIG["rerank_top_k"]
        )
        print(f"   重排后返回 {len(reranked_results)} 个结果")
        
        # 生成
        print("3. 生成阶段...")
        answer = llm_api.generate_answer(test_query, reranked_results)
        
        print("\n" + "=" * 60)
        print("最终答案")
        print("=" * 60)
        print(answer)
        
        # 显示使用的上下文
        print("\n" + "=" * 60)
        print("使用的上下文片段")
        print("=" * 60)
        for i, chunk in enumerate(reranked_results, 1):
            print(f"\n【片段 {i}】")
            print(f"问题: {chunk['metadata'].get('question', 'N/A')}")
            print(f"答案: {chunk['metadata'].get('answer', 'N/A')[:100]}...")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()



