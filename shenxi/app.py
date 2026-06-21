import os
import socket
import tempfile
import subprocess
import streamlit as st

import config
from ui.chat import (
    init_chat_state, render_messages,
    add_user_message, add_assistant_message, get_chat_history,
    USER_AVATAR, ASSISTANT_AVATAR, _copy_button,
)
from utils.error_handler import translate_error
from knowledge.obsidian_loader import scan_vault, get_file_count
from chains.thinking_chain import prepare, stream_output
from memory.conversation_db import (
    init_db, create_conversation, save_message, load_messages,
    list_conversations, delete_conversation, update_title, auto_title,
)

st.set_page_config(page_title="深析", page_icon="🔍", layout="centered")

# --- 暗黑高级感主题 ---
st.markdown("""
<style>
    /* 全局暗黑底色 */
    .stApp { background-color: #0d1117; }
    /* 主内容区 */
    .main .block-container {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 2rem;
    }
    /* 标题 */
    h1 { color: #e6edf3; font-weight: 700; }
    h2, h3 { color: #c9d1d9; }
    /* 正文 */
    p, li, label, .stCaption { color: #b0b8c1; }
    /* 侧边栏 */
    [data-testid="stSidebar"] {
        background-color: #0d1117;
        border-right: 1px solid #21262d;
    }
    [data-testid="stSidebar"] * { color: #c9d1d9; }
    /* 聊天框 */
    .stChatMessage {
        background-color: #161b22;
        border: 1px solid #21262d;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    /* 输入框 */
    .stChatInput textarea {
        background-color: #161b22 !important;
        border: 1px solid #30363d !important;
        color: #e6edf3 !important;
    }
    /* 按钮 */
    .stButton > button {
        background-color: #21262d;
        color: #c9d1d9;
        border: 1px solid #30363d;
        border-radius: 6px;
    }
    .stButton > button:hover {
        background-color: #30363d;
        border-color: #58a6ff;
        color: #e6edf3;
    }
    /* 分割线 */
    hr { border-color: #21262d; }
    /* 代码块 */
    code { color: #ffa657; background-color: #1c2128; }
    /* 滚动条 */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #0d1117; }
    ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@st.cache_resource
def init_knowledge_base():
    from knowledge.fts5_store import build_index, get_chunk_count
    docs = scan_vault(config.KB_PATH)
    n_docs = get_file_count(docs)
    existing = get_chunk_count()
    if existing > 0:
        return n_docs, existing
    n_chunks = build_index(docs) if n_docs > 0 else 0
    return n_docs, n_chunks


# --- 全局初始化 ---
init_db()
local_ip = get_local_ip()

if "kb_loaded" not in st.session_state:
    st.session_state.kb_loaded = False
if not st.session_state.kb_loaded:
    with st.spinner("正在加载知识库..."):
        n_docs, n_chunks = init_knowledge_base()
    st.session_state.kb_loaded = True
    st.session_state.kb_docs = n_docs
    st.session_state.kb_chunks = n_chunks

if "conv_id" not in st.session_state:
    convs = list_conversations()
    st.session_state.conv_id = convs[0]["id"] if convs else create_conversation()

if "page" not in st.session_state:
    st.session_state.page = "chat"

if "deep_thinking" not in st.session_state:
    st.session_state.deep_thinking = False


# ============================================================
# 对话管理页
# ============================================================
def conv_manager_page():
    st.title("📋 对话管理")

    if st.button("➕ 新建对话", use_container_width=True):
        st.session_state.conv_id = create_conversation()
        st.session_state.messages = []
        st.session_state.page = "chat"
        st.rerun()

    st.divider()

    convs = list_conversations()
    if not convs:
        st.info("暂无对话")
    else:
        for i, c in enumerate(convs):
            marker = " ✅ 当前" if c["id"] == st.session_state.conv_id else ""
            st.caption(f"{i+1}. {c['title']}{marker}")
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                if st.button("📂 进入", key=f"enter_{c['id']}_{i}", use_container_width=True):
                    st.session_state.conv_id = c["id"]
                    st.session_state.messages = load_messages(c["id"])
                    st.session_state.page = "chat"
                    st.rerun()
            with col2:
                if st.button("✏️", key=f"rn_{c['id']}_{i}", help="重命名"):
                    st.session_state._rename_target = c["id"]
                    st.session_state._rename_old = c["title"]
                    st.rerun()
            with col3:
                if st.button("✕", key=f"dl_{c['id']}_{i}", help="删除"):
                    st.session_state._del_target = c["id"]
                    st.rerun()

    # 重命名
    if st.session_state.get("_rename_target"):
        cid = st.session_state["_rename_target"]
        ctitle = st.session_state.get("_rename_old", "")
        new_name = st.text_input("新标题", value=ctitle, key="rn_input")
        rc1, rc2 = st.columns(2)
        with rc1:
            if st.button("保存", key="rn_save", use_container_width=True):
                if new_name.strip():
                    update_title(cid, new_name.strip())
                st.session_state._rename_target = None
                st.session_state._rename_old = None
                st.rerun()
        with rc2:
            if st.button("取消", key="rn_cancel", use_container_width=True):
                st.session_state._rename_target = None
                st.session_state._rename_old = None
                st.rerun()

    # 删除
    if st.session_state.get("_del_target"):
        cid = st.session_state["_del_target"]
        t = next((c["title"] for c in convs if c["id"] == cid), "")
        st.warning(f"确定删除「{t}」？")
        dc1, dc2 = st.columns(2)
        with dc1:
            if st.button("确认删除", key="dl_confirm", use_container_width=True):
                delete_conversation(cid)
                if cid == st.session_state.conv_id:
                    rem = list_conversations()
                    st.session_state.conv_id = rem[0]["id"] if rem else create_conversation()
                    st.session_state.messages = load_messages(st.session_state.conv_id)
                st.session_state._del_target = None
                st.rerun()
        with dc2:
            if st.button("取消", key="dl_cancel", use_container_width=True):
                st.session_state._del_target = None
                st.rerun()

    st.divider()
    if st.button("⬅️ 返回聊天", use_container_width=True):
        st.session_state.page = "chat"
        st.rerun()


# ============================================================
# 聊天页
# ============================================================
def chat_page():
    st.title("深析")
    st.caption("深度分析 · 可信决策")

    # --- 侧边栏 ---
    with st.sidebar:
        st.info(f"📱 手机访问：http://{local_ip}:{config.APP_PORT}")
        st.divider()

        convs = list_conversations()
        cur_title = next((c["title"] for c in convs if c["id"] == st.session_state.conv_id), "—")
        st.caption(f"当前对话：{cur_title}")

        if st.button("📋 管理对话", use_container_width=True):
            st.session_state.page = "conv"
            st.rerun()

        st.divider()

        deep = st.toggle("🧠 深度思考", value=st.session_state.deep_thinking,
                         help="开启后使用六阶段深度分析框架")
        if deep != st.session_state.deep_thinking:
            st.session_state.deep_thinking = deep
            st.rerun()

        st.divider()

        if st.button("📥 导出当前对话", use_container_width=True):
            msgs = load_messages(st.session_state.conv_id)
            lines = ["# 深析 对话记录\n"]
            for msg in msgs:
                role = "用户" if msg["role"] == "user" else "深析"
                lines.append(f"## {role}\n\n{msg['content']}\n")
            st.download_button(
                "下载 Markdown", "\n".join(lines).encode("utf-8"),
                file_name="深析_对话导出.md", mime="text/markdown",
            )

        st.divider()
        st.subheader("📚 知识库")
        st.metric("文档", f"{st.session_state.kb_docs} 篇")
        st.metric("索引块", f"{st.session_state.kb_chunks} 个")

        kb_file = st.file_uploader(
            "➕ 添加知识", type=["md", "txt", "pdf", "docx"],
            key=f"kb_{st.session_state.get('_kb_key', 0)}",
        )
        if kb_file:
            kb_path = os.path.join(config.KB_PATH, kb_file.name)
            with open(kb_path, "wb") as f:
                f.write(kb_file.read())
            from knowledge.fts5_store import clear_index, build_index
            clear_index()
            st.cache_resource.clear()
            docs = scan_vault(config.KB_PATH)
            st.session_state.kb_docs = get_file_count(docs)
            st.session_state.kb_chunks = build_index(docs) if docs else 0
            st.session_state["_kb_key"] = st.session_state.get("_kb_key", 0) + 1
            st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            if st.button("📂 打开", key="open_kb", use_container_width=True):
                import sys
                if sys.platform == "win32":
                    subprocess.Popen(["explorer", config.KB_PATH])
                else:
                    st.info(f"知识库路径：{config.KB_PATH}")
        with c2:
            if st.button("🔄 刷新", key="refresh_kb", use_container_width=True):
                from knowledge.fts5_store import clear_index, build_index
                clear_index()
                st.cache_resource.clear()
                docs = scan_vault(config.KB_PATH)
                st.session_state.kb_docs = get_file_count(docs)
                st.session_state.kb_chunks = build_index(docs) if docs else 0
                st.rerun()

        st.divider()
        uploaded_file = st.file_uploader(
            "📎 上传文件/图片",
            type=["pdf", "docx", "xlsx", "txt", "png", "jpg", "jpeg", "gif", "webp"],
            key=f"up_{st.session_state.get('_upload_key', 0)}",
        )

    # --- 处理上传 ---
    file_content = ""
    image_description = ""
    file_label = ""

    if uploaded_file:
        name = uploaded_file.name
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext in ("png", "jpg", "jpeg", "gif", "webp"):
            from tools.image_analyzer import analyze_image
            with st.spinner("正在分析图片..."):
                image_description = analyze_image(uploaded_file.read(), name)
            file_label = f"🖼 {name}"
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{name}") as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name
            from tools.file_parser import parse_file
            file_content = parse_file(tmp_path)
            os.unlink(tmp_path)
            file_label = f"📎 {name}"

    # --- 对话区 ---
    current_msgs = load_messages(st.session_state.conv_id)
    if st.session_state.get("messages", []) != current_msgs:
        st.session_state.messages = current_msgs
    init_chat_state()
    render_messages()

    if prompt := st.chat_input("输入你的问题..."):
        display_prompt = f"{prompt}\n\n_{file_label}_" if file_label else prompt

        if not load_messages(st.session_state.conv_id):
            update_title(st.session_state.conv_id, auto_title(prompt))

        save_message(st.session_state.conv_id, "user", display_prompt)
        add_user_message(display_prompt)
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(display_prompt)

        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            try:
                history = get_chat_history()[:-1]
                with st.spinner("📚 检索 + 🌐 搜索 + 🧠 推理中..."):
                    final_prompt = prepare(prompt, history, file_content, image_description,
                                           deep_thinking=st.session_state.deep_thinking)
                    full_response = st.write_stream(stream_output(final_prompt, deep=st.session_state.deep_thinking))
                _copy_button(full_response)
                add_assistant_message(full_response)
                save_message(st.session_state.conv_id, "assistant", full_response)
                st.session_state["_upload_key"] = st.session_state.get("_upload_key", 0) + 1
                st.rerun()
            except Exception as e:
                error_msg = translate_error(e)
                st.error(error_msg)
                add_assistant_message(f"⚠️ {error_msg}")
                save_message(st.session_state.conv_id, "assistant", f"⚠️ {error_msg}")

    st.divider()
    st.caption(
        f"深析 v2.0 | FTS5全文检索 | 六阶段思考链 | 知识库 {st.session_state.kb_docs} 篇 | "
        f"DeepSeek V4 | SearXNG | LAN: {local_ip}:{config.APP_PORT}"
    )


# ============================================================
# 路由
# ============================================================
if st.session_state.page == "conv":
    conv_manager_page()
else:
    chat_page()
