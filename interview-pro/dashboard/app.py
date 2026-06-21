"""面试官Pro — Streamlit Web 面板。

四页面架构（使用 st.Page 原生多页）：
  1. 题库管理：浏览、搜索、添加、编辑、删除题目
  2. 模拟面试：开始面试 → 逐题作答 → AI 评分 → 成绩单
  3. 统计分析：进步趋势、薄弱环节、全局统计
  4. 模拟模式：AI 代入刘一鸣人设生成面试回答 + 自动评分

启动方式：
  streamlit run dashboard/app.py
  访问 http://localhost:8501
"""

import streamlit as st
import sys
import os

# 确保 agent 模块可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.database import init_db, init_kb_db
from agent.question_bank import (
    list_questions, add_question, delete_question, update_question,
    get_question, count_questions,
)
from agent.search import search_questions
from agent.interviewer import (
    start_session, get_session, draw_questions,
    get_session_questions, submit_answer, finish_session, list_sessions,
)
from agent.evaluator import evaluate_answer
from agent.categorizer import get_categories, get_category_stats, DIFFICULTY_LEVELS
from agent.roles import get_roles, get_role_names, get_categories_for_role, get_stages_for_role, get_default_role
from agent.reporter import session_report, progress_trend, weakness_analysis, overall_stats
from agent.mocker import generate_mock_answer
from agent.knowledge_base import (
    list_knowledge, search_knowledge, get_knowledge,
    add_knowledge, update_knowledge, delete_knowledge, count_knowledge,
)


# ── 页面配置 ──
st.set_page_config(
    page_title="面试官Pro",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 数据库初始化 ──
init_db()
init_kb_db()

# ── 侧边栏导航 ──
st.sidebar.title("🎯 面试官Pro")
st.sidebar.caption("🏋️ 训练区  ·  📊 数据区")
page = st.sidebar.radio(
    "导航",
    ["🎤 模拟面试", "🎭 模拟模式", "📚 题库管理", "📊 统计分析", "📖 知识库"],
    label_visibility="collapsed",
)


# ═══════════════════════════════════════════════
# 页面1：题库管理
# ═══════════════════════════════════════════════
if page == "📚 题库管理":
    st.title("📚 题库管理")

    # 三层级联筛选：岗位 → 阶段 → 分类
    role_names = get_role_names()
    filter_role = st.selectbox("岗位", ["全部"] + role_names, key="qb_role")
    role_cats = get_categories_for_role(filter_role) if filter_role != "全部" else get_categories()
    role_stages = get_stages_for_role(filter_role) if filter_role != "全部" else []

    col1, col2, col3 = st.columns(3)
    with col1:
        if role_stages:
            filter_stage = st.selectbox("阶段", ["全部"] + role_stages, key="qb_stage")
        else:
            filter_stage = "全部"
    with col2:
        filter_cat = st.selectbox("分类", ["全部"] + role_cats)
    with col3:
        filter_diff = st.selectbox("难度", ["全部"] + DIFFICULTY_LEVELS)

    # 搜索栏
    search_query = st.text_input("搜索题目（FTS5 全文检索）", placeholder="输入关键词...")

    # 搜索 or 列表
    if search_query:
        results = search_questions(
            search_query,
            category=None if filter_cat == "全部" else filter_cat,
            difficulty=None if filter_diff == "全部" else filter_diff,
        )
        st.info(f"搜索「{search_query}」— 找到 {len(results)} 道题目")
    else:
        results = list_questions(
            role=None if filter_role == "全部" else filter_role,
            category=None if filter_cat == "全部" else filter_cat,
            difficulty=None if filter_diff == "全部" else filter_diff,
        )
        st.caption(f"共 {count_questions(role=None if filter_role == '全部' else filter_role)} 道题目")

    # 添加题目按钮
    with st.expander("➕ 添加新题目"):
        with st.form("add_question"):
            q_title = st.text_input("题目标题*", placeholder="例：Python 中 GIL 是什么？")
            c_role, c_cat, c_diff = st.columns(3)
            with c_role:
                q_role = st.selectbox("岗位", role_names)
            with c_cat:
                q_cat = st.selectbox("分类", get_categories_for_role(q_role) or get_categories())
            with c_diff:
                q_diff = st.selectbox("难度", DIFFICULTY_LEVELS)
            q_content = st.text_area("题目描述", placeholder="详细的题目背景和具体问题...", height=100)
            q_answer = st.text_area("参考答案", placeholder="标准答案或答题要点...", height=150)
            c1, c2 = st.columns(2)
            with c1:
                q_tags = st.text_input("标签（逗号分隔）", placeholder="Python, GIL, 并发")
            with c2:
                q_stage = st.selectbox("阶段", ["未指定"] + role_stages if role_stages else ["未指定"])
            q_source = st.text_input("来源", placeholder="LeetCode / 牛客 / 真实面试...")

            if st.form_submit_button("✅ 添加"):
                if q_title.strip():
                    tags = [t.strip() for t in q_tags.split(",") if t.strip()]
                    # 将阶段信息嵌入 tags
                    if q_stage and q_stage != "未指定":
                        tags.insert(0, f"stage:{q_stage}")
                    qid = add_question(
                        title=q_title, role=q_role, content=q_content, answer=q_answer,
                        category=q_cat, difficulty=q_diff, tags=tags, source=q_source,
                    )
                    st.success(f"已添加题目 #{qid}")
                    st.rerun()
                else:
                    st.error("标题不能为空")

    # 题目列表
    for q in results:
        role_label = f" {q.get('role', '')} ·" if q.get("role") else ""
        with st.expander(f"{q['title']}  [{q.get('role', '')} · {q['category']} · {q['difficulty']}]"):
            if q.get("content"):
                st.markdown(f"**题目描述：** {q['content']}")
            if q.get("answer"):
                st.markdown(f"**参考答案：** {q['answer']}")
            if q.get("tags"):
                tags = q["tags"] if isinstance(q["tags"], list) else []
                st.caption("🏷️ " + " · ".join(tags))
            if q.get("source"):
                st.caption(f"📎 来源：{q['source']}")

            # 操作按钮
            c1, c2 = st.columns([1, 1])
            with c1:
                pending_key = f"pending_delete_{q['id']}"
                if st.session_state.get(pending_key):
                    # 二次确认
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        if st.button(f"⚠️ 确认删除 #{q['id']}", key=f"confirm_del_{q['id']}"):
                            delete_question(q["id"])
                            st.session_state[pending_key] = False
                            st.success(f"已删除 #{q['id']}")
                            st.rerun()
                    with cc2:
                        if st.button("取消", key=f"cancel_del_{q['id']}"):
                            st.session_state[pending_key] = False
                            st.rerun()
                else:
                    if st.button(f"🗑️ 删除 #{q['id']}", key=f"del_{q['id']}"):
                        st.session_state[pending_key] = True
                        st.rerun()
            with c2:
                st.caption(f"ID: {q['id']} | {q.get('updated_at', '')[:10]}")


# ═══════════════════════════════════════════════
# 页面2：模拟面试
# ═══════════════════════════════════════════════
elif page == "🎤 模拟面试":
    st.title("🎤 模拟面试")

    # 会话状态管理
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "current_question_idx" not in st.session_state:
        st.session_state.current_question_idx = 0

    # 开始新面试
    if st.session_state.session_id is None:
        st.markdown("### 开始一场新的模拟面试")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            mode = st.selectbox("面试模式", ["practice", "mock", "quiz"])
        with col2:
            interview_role = st.selectbox("岗位", role_names, key="interview_role")
        with col3:
            q_count = st.number_input("题目数量", min_value=1, max_value=20, value=5)
        with col4:
            role_only_cats = get_categories_for_role(interview_role)
            q_cat = st.selectbox("限定分类", ["不限"] + (role_only_cats or get_categories()))

        if st.button("🚀 开始面试", type="primary"):
            sid = start_session(mode=mode)
            questions = draw_questions(
                sid, count=q_count,
                role=interview_role,
                category=None if q_cat == "不限" else q_cat,
            )
            if not questions:
                st.error("题库中没有符合条件的题目，请先添加题目")
            else:
                if len(questions) < q_count:
                    st.warning(f"题库中仅匹配 {len(questions)} 题（请求 {q_count} 题），已用全部可用题目")
                st.session_state.session_id = sid
                st.session_state.questions = questions
                st.session_state.current_question_idx = 0
                st.rerun()

        # 历史会话
        st.markdown("---")
        st.markdown("### 📜 历史面试")
        sessions = list_sessions(limit=10)
        for s in sessions:
            status = "✅" if s["finished_at"] else "🔄"
            avg = f"平均分 {s['avg_score']:.0f}" if s["avg_score"] else "未评分"
            st.caption(
                f"{status} {s['started_at'][:16]} | {s['mode']} | "
                f"{s['answered']}/{s['total_questions']}题 | {avg}"
            )
            if st.button(f"📋 查看成绩单 #{s['id']}", key=f"report_{s['id']}"):
                st.session_state.view_report = s["id"]
                st.rerun()

    # 进行中的面试
    else:
        questions = st.session_state.get("questions", [])
        idx = st.session_state.current_question_idx

        if idx < len(questions):
            q = questions[idx]
            st.progress(idx / len(questions), f"第 {idx+1}/{len(questions)} 题")

            st.markdown(f"### 📝 第 {idx+1} 题")
            st.markdown(f"**{q['title']}**")
            if q.get("content"):
                st.info(q["content"])
            st.caption(f"分类: {q['category']} | 难度: {q['difficulty']}")

            user_answer = st.text_area("你的回答", height=200, key=f"answer_{q['id']}")

            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("⏭️ 跳过"):
                    submit_answer(st.session_state.session_id, q["id"], "(跳过)")
                    st.session_state.current_question_idx += 1
                    st.rerun()
            with col2:
                if st.button("✅ 提交", type="primary"):
                    if user_answer.strip():
                        # AI 评分
                        with st.spinner("AI 正在评分..."):
                            evaluation = evaluate_answer(
                                question=q["title"] + "\n" + q.get("content", ""),
                                answer=user_answer,
                                reference_answer=q.get("answer", ""),
                            )
                        submit_answer(
                            st.session_state.session_id, q["id"],
                            user_answer,
                            score=evaluation.get("score"),
                            feedback=evaluation.get("feedback"),
                        )
                        st.success(f"评分: {evaluation.get('score', '?')}/100")
                        if evaluation.get("strengths"):
                            st.caption("👍 " + " · ".join(evaluation["strengths"]))
                        if evaluation.get("improvements"):
                            st.caption("💡 " + " · ".join(evaluation["improvements"]))

                        st.session_state.current_question_idx += 1
                        st.rerun()
                    else:
                        st.error("请输入你的回答")
        else:
            # 面试结束
            st.balloons()
            st.success("🎉 面试完成！")
            finish_session(st.session_state.session_id)
            report = session_report(st.session_state.session_id)
            if report:
                st.markdown(f"### 📊 成绩单")
                st.metric("平均分", f"{report['avg_score']:.0f}/100" if report["avg_score"] else "未评分")
                st.metric("完成率", f"{report['answered']}/{report['total_questions']}")

                if report.get("score_distribution"):
                    dist = report["score_distribution"]
                    st.markdown(f"""
                    | 等级 | 题数 |
                    |------|------|
                    | 🟢 优秀 (85+) | {dist['excellent']} |
                    | 🔵 良好 (70-84) | {dist['good']} |
                    | 🟡 一般 (50-69) | {dist['fair']} |
                    | 🔴 需改进 (<50) | {dist['poor']} |
                    """)

                # 逐题反馈
                st.markdown("### 📋 逐题反馈")
                for i, a in enumerate(report["answers"], 1):
                    with st.expander(f"第{i}题: {a['title']} [{a.get('score', '?')}/100]"):
                        st.caption(f"分类: {a['category']} | 难度: {a['difficulty']}")
                        if a.get("feedback"):
                            st.info(a["feedback"])
                        if a.get("user_answer"):
                            st.markdown(f"**你的回答：** {a['user_answer'][:300]}")

            if st.button("🔄 开始新一轮面试"):
                st.session_state.session_id = None
                st.session_state.questions = []
                st.session_state.current_question_idx = 0
                st.rerun()


# ═══════════════════════════════════════════════
# 页面3：统计分析
# ═══════════════════════════════════════════════
elif page == "📊 统计分析":
    st.title("📊 统计分析")

    # 全局统计
    stats = overall_stats()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("题库总量", stats["total_questions"])
    with col2:
        st.metric("面试次数", stats["total_sessions"])
    with col3:
        st.metric("已评分数", stats["total_answers"])
    with col4:
        st.metric("历史均分", f"{stats['overall_avg_score']}/100" if stats["overall_avg_score"] else "--")

    # 分类分布
    st.markdown("### 📂 题库分类分布")
    cat_stats = get_category_stats()
    if cat_stats:
        cols = st.columns(3)
        for i, cs in enumerate(cat_stats[:9]):
            with cols[i % 3]:
                st.metric(cs["category"], cs["count"])
    else:
        st.caption("暂无数据，先添加一些题目吧")

    # 进步趋势
    st.markdown("### 📈 进步趋势")
    trend = progress_trend(limit=10)
    if trend:
        chart_data = [
            {
                "面试": f"#{t['id']}",
                "平均分": t["avg_score"] or 0,
                "题数": t["answered"],
            }
            for t in reversed(trend)
        ]
        st.line_chart(chart_data, x="面试", y=["平均分"])
    else:
        st.caption("暂无评分数据，完成几轮面试后查看趋势")

    # 薄弱环节
    st.markdown("### 🎯 薄弱环节")
    weaknesses = weakness_analysis()
    if weaknesses:
        for w in weaknesses:
            emoji = "🔴" if w["avg_score"] < 50 else "🟡" if w["avg_score"] < 70 else "🟢"
            st.markdown(f"{emoji} **{w['category']}**: 均分 {w['avg_score']:.0f} (共{w['count']}题)")
    else:
        st.caption("暂无足够数据，至少完成2次评分后显示")


# ═══════════════════════════════════════════════
# 页面4：模拟模式 — AI 代入刘一鸣人设生成回答
# ═══════════════════════════════════════════════
elif page == "🎭 模拟模式":
    st.title("🎭 模拟模式")
    st.caption("AI 代入刘一鸣人设实时生成面试回答，并自动评分。用于检验「蒸馏画像」的生成质量。")

    # ── 模式说明 ──
    with st.expander("ℹ️ 模式说明", expanded=False):
        st.markdown("""
        **这是什么？**
        系统读取刘一鸣的完整蒸馏画像（身份 + 项目经历 + 表达风格 + 决策模式），
        加上相关经验上下文，调用 DeepSeek 生成一段"像是刘一鸣本人会说出来的"面试回答。

        **和「模拟面试」页面的区别？**
        - 模拟面试：**你** 输入回答 → AI 评分（训练模式）
        - 模拟模式：**AI 替你** 生成回答 → AI 评分（检验模式）

        **用途：**
        - 验证蒸馏画像是否准确（生成的回答有没有"刘一鸣味"）
        - 快速生成大量面试回答 → 审查质量 → 迭代画像
        - 面试前快速过一遍高频问题的生成效果
        """)

    # ── 自由提问 ──
    st.markdown("### 💬 自由提问")
    st.caption("输入任意面试问题，AI 代入刘一鸣人设生成回答。无需从题库抽题。")
    free_col1, free_col2, free_col3 = st.columns([3, 1, 1])
    with free_col1:
        free_question = st.text_input(
            "输入你的问题",
            placeholder="例：你为什么要从机械转行做AI？",
            key="free_question_input",
            label_visibility="collapsed",
        )
    with free_col2:
        free_role = st.selectbox("岗位", role_names, key="free_role")
    with free_col3:
        free_submit = st.button("🤖 生成回答", key="free_submit", use_container_width=True)

    if free_submit and free_question.strip():
        with st.spinner("AI 正在代入刘一鸣人设生成回答..."):
            result = generate_mock_answer(
                question=free_question.strip(),
                category="未分类",
                difficulty="",
                role=free_role,
            )
        st.session_state.free_result = result
        st.session_state.free_question_text = free_question.strip()
        st.rerun()

    # 展示自由提问结果（复用已有评分/回答展示模式）
    if st.session_state.get("free_result"):
        st.markdown("---")
        st.markdown(f"**💬 问题：** {st.session_state.free_question_text}")
        result = st.session_state.free_result
        if result.get("error"):
            st.error(f"生成失败: {result['error']}")
        else:
            st.markdown("**🤖 AI 生成的回答（代入刘一鸣）：**")
            st.success(result.get("answer", "（无内容）"))
            score = result.get("score") or {}
            if score:
                st.markdown("**📊 自动评分：**")
                sm1, sm2, sm3, sm4 = st.columns(4)
                with sm1:
                    st.metric("总分", f"{score.get('score', '?')}/100")
                with sm2:
                    st.metric("准确性", f"{score.get('accuracy', '?')}/30")
                with sm3:
                    st.metric("深度", f"{score.get('depth', '?')}/30")
                with sm4:
                    st.metric("表达", f"{score.get('expression', '?')}/20")
                if score.get("feedback"):
                    st.caption(f"💬 {score['feedback']}")
                if score.get("strengths"):
                    st.caption("👍 " + " · ".join(score["strengths"]))
                if score.get("improvements"):
                    st.caption("💡 " + " · ".join(score["improvements"]))
            with st.expander("🔍 调试信息（注入的上下文）", expanded=False):
                st.caption(f"生成耗时: {result.get('generation_time', 0):.1f}s")
                st.markdown("**注入的身份骨架：**")
                st.text(result.get("skeleton", "")[:500])
                st.markdown("**注入的经验上下文：**")
                st.text(result.get("context", "")[:500])
            if st.button("🔄 清除", key="clear_free_result"):
                st.session_state.free_result = None
                st.session_state.free_question_text = ""
                st.rerun()

    st.markdown("---")

    # ── 筛选器 ──
    st.markdown("### 🎯 抽题设置")
    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
    with col1:
        mock_cat = st.selectbox("限定分类", ["全部"] + get_categories(), key="mock_cat")
    with col2:
        mock_diff = st.selectbox("限定难度", ["全部"] + DIFFICULTY_LEVELS, key="mock_diff")
    with col3:
        mock_count = st.number_input("抽取数量", min_value=1, max_value=10, value=3, key="mock_count")
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        draw_btn = st.button("🎲 抽题", type="primary", use_container_width=True)

    # ── 抽题逻辑 ──
    if draw_btn:
        st.session_state.mock_drawn = list_questions(
            category=None if mock_cat == "全部" else mock_cat,
            difficulty=None if mock_diff == "全部" else mock_diff,
            limit=mock_count,
        )
        st.session_state.mock_generated = {}  # question_id → result
        st.rerun()

    if "mock_drawn" not in st.session_state:
        st.session_state.mock_drawn = []
    if "mock_generated" not in st.session_state:
        st.session_state.mock_generated = {}

    questions = st.session_state.mock_drawn

    if not questions:
        st.info("👆 点击「🎲 抽题」随机抽取题目，或先在题库管理页面添加一些题目")
    else:
        st.markdown(f"---")
        st.markdown(f"### 📋 已抽取 {len(questions)} 道题目")

        for i, q in enumerate(questions):
            qid = q["id"]
            with st.expander(
                f"第{i+1}题: {q['title']}  [{q.get('category', '?')} · {q.get('difficulty', '?')}]",
                expanded=(i == 0),
            ):
                if q.get("content"):
                    st.info(q["content"])

                # 生成按钮
                gen_col1, gen_col2 = st.columns([1, 3])
                with gen_col1:
                    gen_btn = st.button(
                        f"🤖 生成回答",
                        key=f"mock_gen_{qid}",
                        type="primary",
                        disabled=(qid in st.session_state.mock_generated),
                    )
                with gen_col2:
                    if qid in st.session_state.mock_generated:
                        prev = st.session_state.mock_generated[qid]
                        gen_time = prev.get("generation_time", 0)
                        score_info = prev.get("score") or {}
                        st.caption(
                            f"已生成 ({gen_time:.1f}s) | "
                            f"评分: {score_info.get('score', '?')}/100"
                        )

                if gen_btn:
                    with st.spinner(f"AI 正在代入刘一鸣人设生成回答..."):
                        result = generate_mock_answer(
                            question=q["title"] + "\n" + q.get("content", ""),
                            category=q.get("category", "未分类"),
                            role=q.get("role", "全部"),
                            difficulty=q.get("difficulty", ""),
                        )
                    st.session_state.mock_generated[qid] = result
                    st.rerun()

                # 展示结果
                if qid in st.session_state.mock_generated:
                    result = st.session_state.mock_generated[qid]

                    if result.get("error"):
                        st.error(f"生成失败: {result['error']}")
                    else:
                        # 生成的回答
                        st.markdown("**🤖 AI 生成的回答（代入刘一鸣）：**")
                        st.success(result.get("answer", "（无内容）"))

                        # 自动评分
                        score = result.get("score") or {}
                        if score:
                            st.markdown("**📊 自动评分：**")
                            sm1, sm2, sm3, sm4 = st.columns(4)
                            with sm1:
                                st.metric("总分", f"{score.get('score', '?')}/100")
                            with sm2:
                                st.metric("准确性", f"{score.get('accuracy', '?')}/30")
                            with sm3:
                                st.metric("深度", f"{score.get('depth', '?')}/30")
                            with sm4:
                                st.metric("表达", f"{score.get('expression', '?')}/20")

                            if score.get("feedback"):
                                st.caption(f"💬 {score['feedback']}")
                            if score.get("strengths"):
                                st.caption("👍 " + " · ".join(score["strengths"]))
                            if score.get("improvements"):
                                st.caption("💡 " + " · ".join(score["improvements"]))

                        # 技术细节（折叠）
                        with st.expander("🔍 调试信息（注入的上下文）", expanded=False):
                            st.caption(f"生成耗时: {result.get('generation_time', 0):.1f}s")
                            st.markdown("**注入的身份骨架：**")
                            st.text(result.get("skeleton", "")[:500])
                            st.markdown("**注入的经验上下文：**")
                            st.text(result.get("context", "")[:500])

        # ── 批量操作 ──
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 清除结果重新开始"):
                st.session_state.mock_drawn = []
                st.session_state.mock_generated = {}
                st.rerun()
        with col2:
            generated_count = len(st.session_state.mock_generated)
            total = len(questions)
            st.caption(f"已生成: {generated_count}/{total}")


# ═══════════════════════════════════════════════
# 页面5：知识库 — 项目事实存储与检索
# ═══════════════════════════════════════════════
elif page == "📖 知识库":
    st.title("📖 知识库")
    st.caption("项目事实、经验、决策记录。与身份画像（profile.yaml）解耦，可独立维护。")

    # 分类列表
    kb_categories = ["全部"] + sorted(set(
        r["category"] for r in list_knowledge(limit=1000)
    ))
    if not kb_categories or kb_categories == ["全部"]:
        kb_categories = ["全部", "project", "narrative", "decision", "pitfall"]

    # 筛选栏
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        kb_query = st.text_input("搜索知识库（FTS5 全文检索）", placeholder="输入关键词...", key="kb_search")
    with col2:
        kb_role = st.selectbox("岗位", ["全部"] + get_role_names(), key="kb_role_filter")
    with col3:
        kb_cat = st.selectbox("分类", kb_categories, key="kb_cat_filter")
    st.caption(f"共 {count_knowledge(role=None if kb_role == '全部' else kb_role)} 条")

    # 搜索 or 列表
    if kb_query:
        results = search_knowledge(kb_query, role=None if kb_role == "全部" else kb_role)
        st.info(f"搜索「{kb_query}」— 找到 {len(results)} 条")
    else:
        results = list_knowledge(
            category=None if kb_cat == "全部" else kb_cat,
            role=None if kb_role == "全部" else kb_role,
            limit=100,
        )

    # 添加条目
    with st.expander("➕ 添加知识条目"):
        with st.form("add_kb"):
            kb_title = st.text_input("标题*", placeholder="例：深析AI助手", key="kb_title")
            kb_cat_new = st.selectbox("分类", ["project", "experience", "pitfall", "decision", "narrative"], key="kb_cat_new")
            kb_content = st.text_area("内容*", placeholder="详细描述...", height=150, key="kb_content")
            c1, c2 = st.columns(2)
            with c1:
                kb_tech = st.text_input("技术栈（逗号分隔）", placeholder="LangChain, DeepSeek", key="kb_tech")
            with c2:
                kb_tags = st.text_input("标签（逗号分隔）", placeholder="shenxi, agent, rag", key="kb_tags")
            if st.form_submit_button("✅ 添加"):
                if kb_title.strip() and kb_content.strip():
                    tags = [t.strip() for t in kb_tags.split(",") if t.strip()]
                    kid = add_knowledge(
                        title=kb_title.strip(), category=kb_cat_new,
                        content=kb_content.strip(), tech_stack=kb_tech.strip(),
                        tags=tags,
                    )
                    st.success(f"已添加 #{kid}")
                    st.rerun()
                else:
                    st.error("标题和内容不能为空")

    # 列表
    for item in results:
        tags_display = " · ".join(item.get("tags", [])) if item.get("tags") else ""
        tech_display = item.get("tech_stack", "") or ""
        with st.expander(
            f"{item['title']}  [{item['category']}]{' — ' + tech_display if tech_display else ''}"
        ):
            st.markdown(item.get("content", ""))
            if tags_display:
                st.caption(f"🏷️ {tags_display}")
            st.caption(
                f"来源: {item.get('source', 'manual')} | "
                f"更新: {item.get('updated_at', '')[:10]} | ID: {item['id']}"
            )

            # 操作按钮
            c1, c2 = st.columns([1, 1])
            with c1:
                pending_key = f"kb_pending_del_{item['id']}"
                if st.session_state.get(pending_key):
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        if st.button(f"⚠️ 确认删除", key=f"kb_confirm_{item['id']}"):
                            delete_knowledge(item["id"])
                            st.session_state[pending_key] = False
                            st.success(f"已删除 #{item['id']}")
                            st.rerun()
                    with cc2:
                        if st.button("取消", key=f"kb_cancel_{item['id']}"):
                            st.session_state[pending_key] = False
                            st.rerun()
                else:
                    if st.button(f"🗑️ 删除 #{item['id']}", key=f"kb_del_{item['id']}"):
                        st.session_state[pending_key] = True
                        st.rerun()
            with c2:
                if st.button(f"✏️ 编辑 #{item['id']}", key=f"kb_edit_{item['id']}"):
                    st.session_state.kb_editing = item["id"]
                    st.rerun()

            # 编辑表单
            if st.session_state.get("kb_editing") == item["id"]:
                with st.form(f"edit_kb_{item['id']}"):
                    st.markdown("**编辑知识条目**")
                    new_title = st.text_input("标题", value=item["title"], key=f"kb_etitle_{item['id']}")
                    new_cat = st.selectbox(
                        "分类", ["project", "experience", "pitfall", "decision", "narrative"],
                        index=["project", "experience", "pitfall", "decision", "narrative"].index(item["category"])
                        if item["category"] in ["project", "experience", "pitfall", "decision", "narrative"] else 0,
                        key=f"kb_ecat_{item['id']}",
                    )
                    new_content = st.text_area("内容", value=item["content"], height=150, key=f"kb_econtent_{item['id']}")
                    c1, c2 = st.columns(2)
                    with c1:
                        new_tech = st.text_input("技术栈", value=item.get("tech_stack", ""), key=f"kb_etech_{item['id']}")
                    with c2:
                        new_tags = st.text_input(
                            "标签（逗号分隔）",
                            value=", ".join(item.get("tags", [])),
                            key=f"kb_etags_{item['id']}",
                        )
                    sc1, sc2 = st.columns(2)
                    with sc1:
                        if st.form_submit_button("💾 保存"):
                            tags = [t.strip() for t in new_tags.split(",") if t.strip()]
                            update_knowledge(
                                item["id"], title=new_title, category=new_cat,
                                content=new_content, tech_stack=new_tech, tags=tags,
                            )
                            st.session_state.kb_editing = None
                            st.success("已保存")
                            st.rerun()
                    with sc2:
                        if st.form_submit_button("❌ 取消"):
                            st.session_state.kb_editing = None
                            st.rerun()
