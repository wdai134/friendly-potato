import streamlit as st

STAGES = [
    ("understand", "理解问题"),
    ("retrieve", "检索知识"),
    ("reason", "深度推理"),
    ("output", "生成结论"),
]

STAGE_DONE = {}


def show_thinking_status():
    cols = st.columns(4)
    for i, (stage_id, label) in enumerate(STAGES):
        with cols[i]:
            if stage_id in STAGE_DONE:
                st.success(f"✅ {label}")
            else:
                st.info(f"⏳ {label}")


def mark_stage(stage_id: str):
    STAGE_DONE[stage_id] = True
