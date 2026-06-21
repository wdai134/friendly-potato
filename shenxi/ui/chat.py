import streamlit as st

USER_AVATAR = "👤"
ASSISTANT_AVATAR = "❄️"


def _copy_button(text: str):
    """在回答底部添加一键复制按钮"""
    import html as _html
    escaped = _html.escape(text)
    st.components.v1.html(f"""
    <button onclick="
        navigator.clipboard.writeText(this.nextElementSibling.textContent);
        this.textContent='✅ 已复制!';
        setTimeout(()=>this.textContent='📋 复制', 2000)
    " style="
        background: #21262d; color: #b0b8c1;
        border: 1px solid #30363d; border-radius: 4px;
        padding: 3px 12px; cursor: pointer; font-size: 12px;
    ">📋 复制</button>
    <pre style="display:none;">{escaped}</pre>
    """, height=34)


def init_chat_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []


def render_messages():
    for msg in st.session_state.messages:
        avatar = USER_AVATAR if msg["role"] == "user" else ASSISTANT_AVATAR
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                _copy_button(msg["content"])


def add_user_message(content: str):
    """添加用户消息到状态"""
    st.session_state.messages.append({"role": "user", "content": content})


def add_assistant_message(content: str):
    """添加助手消息到状态"""
    st.session_state.messages.append({"role": "assistant", "content": content})


def get_chat_history() -> list:
    """获取对话历史"""
    return st.session_state.messages
