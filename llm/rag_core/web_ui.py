import streamlit as st
import sys
import os
from pathlib import Path

# 添加相关路径
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir))
sys.path.append(str(current_dir.parent))

from rag_system import create_rag_system

# 页面配置
st.set_page_config(
    page_title="RAG 智能问答系统",
    page_icon="🤖",
    layout="centered"
)

st.title("🤖 RAG 智能问答助手")

# 初始化 Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

if "rag_system" not in st.session_state:
    with st.spinner('正在初始化 RAG 系统，请稍候...'):
        try:
            # 尝试加载索引，如果失败则提示需要重建
            st.session_state.rag_system = create_rag_system(rebuild_index=False)
            st.success('RAG 系统加载成功！')
        except Exception as e:
            st.error(f"RAG 系统加载失败: {e}")
            st.warning("提示: 如果是首次运行或数据有更新，请先运行 `python main.py --rebuild` 重建索引。")

# 显示历史消息
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 聊天输入框
if prompt := st.chat_input("请输入您的问题..."):
    # 显示用户消息
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 生成回答
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        if "rag_system" in st.session_state and st.session_state.rag_system:
            try:
                with st.spinner('Thinking...'):
                    result = st.session_state.rag_system.query(prompt, return_context=True)
                    full_response = result['answer']
                    
                    # 可以在这里显示引用来源
                    if result.get('context'):
                        context_info = "\n\n---\n**参考文档片段:**\n"
                        for i, ctx in enumerate(result['context'], 1):
                            context_info += f"{i}. {ctx['question']} (相似度: {ctx['score']:.2f})\n"
                        full_response += context_info
                        
                    message_placeholder.markdown(full_response)
            except Exception as e:
                full_response = f"发生错误: {e}"
                message_placeholder.error(full_response)
        else:
            full_response = "RAG 系统未初始化完成，请检查后台日志。"
            message_placeholder.error(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})

# 侧边栏
with st.sidebar:
    st.header("系统状态")
    if "rag_system" in st.session_state and st.session_state.rag_system:
        stats = st.session_state.rag_system.get_statistics()
        st.write(f"📊 向量总数: {stats['total_vectors']}")
        st.write(f"📏 向量维度: {stats['embedding_dim']}")
    else:
        st.write("⚪ 系统未连接")
    
    st.markdown("---")
    if st.button("清除对话历史"):
        st.session_state.messages = []
        st.experimental_rerun()
