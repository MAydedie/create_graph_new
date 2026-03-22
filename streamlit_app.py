#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Graph RAG 代码知识问答系统 - Streamlit 前端
"""

import os
import sys
import streamlit as st
from pathlib import Path

# 设置环境变量
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 设置项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 页面配置
st.set_page_config(
    page_title="Graph RAG 代码知识问答",
    page_icon="🔍",
    layout="wide"
)

# 自定义CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: bold;
        text-align: center;
        margin-bottom: 1rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .user-message {
        background-color: #e3f2fd;
        border-left: 4px solid #2196f3;
    }
    .assistant-message {
        background-color: #f3e5f5;
        border-left: 4px solid #9c27b0;
    }
    .stats-box {
        background-color: #f5f5f5;
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
        font-size: 0.85rem;
        color: #666;
    }
</style>
""", unsafe_allow_html=True)

# 初始化会话状态
if "rag_system" not in st.session_state:
    st.session_state.rag_system = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "initialized" not in st.session_state:
    st.session_state.initialized = False


@st.cache_resource
def load_rag_system():
    """加载 GraphRAGSystem（带缓存）"""
    from llm.capability.graph_rag_system import GraphRAGSystem
    return GraphRAGSystem()


def main():
    # 标题
    st.markdown('<p class="main-header">🔍 Graph RAG 代码知识问答系统</p>', unsafe_allow_html=True)
    
    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 系统设置")
        
        # 参数设置
        retrieval_top_k = st.slider("召回数量 (retrieval_top_k)", 5, 50, 25)
        rerank_top_k = st.slider("重排后数量 (rerank_top_k)", 1, 10, 5)
        show_context = st.checkbox("显示检索上下文", value=False)
        
        st.divider()
        
        # 系统状态
        st.header("📊 系统状态")
        
        if st.session_state.rag_system is not None:
            stats = st.session_state.rag_system.get_statistics()
            st.success("✅ 系统已初始化")
            st.metric("知识块数量", stats["total_vectors"])
            st.text(f"嵌入模型: {stats['embedding_model']}")
        else:
            st.warning("⏳ 系统未初始化")
        
        st.divider()
        
        if st.button("🗑️ 清空对话历史"):
            st.session_state.messages = []
            st.rerun()
    
    # 主区域
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 初始化系统
        if not st.session_state.initialized:
            with st.spinner("正在初始化 Graph RAG 系统，请稍候..."):
                try:
                    st.session_state.rag_system = load_rag_system()
                    st.session_state.initialized = True
                    st.rerun()
                except Exception as e:
                    st.error(f"初始化失败: {e}")
                    return
        
        # 对话历史
        st.subheader("💬 对话")
        
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                st.markdown(f'<div class="chat-message user-message">🧑 **用户**: {msg["content"]}</div>', 
                           unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-message assistant-message">🤖 **助手**: {msg["content"]}</div>', 
                           unsafe_allow_html=True)
                if "stats" in msg:
                    st.markdown(f'<div class="stats-box">召回: {msg["stats"]["retrieval"]} | 重排后: {msg["stats"]["rerank"]}</div>', 
                               unsafe_allow_html=True)
        
        # 用户输入
        user_input = st.chat_input("请输入您的问题（例如：PythonParser类有哪些方法？）")
        
        if user_input:
            # 添加用户消息
            st.session_state.messages.append({"role": "user", "content": user_input})
            
            # 获取回答
            with st.spinner("正在思考..."):
                try:
                    result = st.session_state.rag_system.query(
                        user_input,
                        retrieval_top_k=retrieval_top_k,
                        rerank_top_k=rerank_top_k,
                        return_context=show_context
                    )
                    
                    # 添加助手消息
                    msg = {
                        "role": "assistant",
                        "content": result["answer"],
                        "stats": {
                            "retrieval": result["retrieval_count"],
                            "rerank": result["rerank_count"]
                        }
                    }
                    if show_context and "context" in result:
                        msg["context"] = result["context"]
                    
                    st.session_state.messages.append(msg)
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"查询失败: {e}")
    
    with col2:
        st.subheader("📚 使用说明")
        st.markdown("""
        **常见问题类型**:
        - 🔹 类/方法功能查询
        - 🔹 代码结构分析
        - 🔹 调用链路追踪
        - 🔹 功能路径解释
        
        **示例问题**:
        1. PythonParser 类的主要功能是什么？
        2. 代码分析的入口在哪里？
        3. 图谱是如何生成的？
        
        **知识来源**:
        - 代码图谱分析结果
        - 功能路径数据
        """)


if __name__ == "__main__":
    main()
