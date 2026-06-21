"""模拟面试引擎 — 面试会话管理。

管理一轮面试的生命周期：
  开始 → 抽题 → 逐题作答 → AI 评分 → 结束报告

会话状态通过 sessions + answers 表持久化，支持中断恢复。
"""

import random
from agent.database import get_connection


def start_session(mode: str = "practice", question_ids: list[int] | None = None) -> int:
    """创建新面试会话，返回 session_id。

    Args:
        mode: practice(练习) / mock(模拟面试) / quiz(知识测验)
        question_ids: 指定题目列表，None 则后续手动抽题
    """
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO sessions (mode, total_questions) VALUES (?, ?)",
        (mode, len(question_ids) if question_ids else 0),
    )
    session_id = cursor.lastrowid

    # 如果指定了题目，预设答题槽位
    if question_ids:
        for qid in question_ids:
            conn.execute(
                "INSERT INTO answers (session_id, question_id) VALUES (?, ?)",
                (session_id, qid),
            )

    conn.commit()
    conn.close()
    return session_id


def get_session(session_id: int) -> dict | None:
    """获取会话信息。"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_sessions(limit: int = 20) -> list[dict]:
    """列出最近的会话记录。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def draw_questions(
    session_id: int,
    count: int = 5,
    role: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    exclude_answered: bool = True,
) -> list[dict]:
    """从题库随机抽题。

    Args:
        session_id: 会话 ID
        count: 抽取数量
        role: 限定岗位
        category: 限定分类
        difficulty: 限定难度
        exclude_answered: 是否排除本会话已答过的题
    """
    conn = get_connection()

    query = "SELECT id, title, content, category, difficulty, tags FROM questions WHERE 1=1"
    params = []

    if role:
        query += " AND role = ?"
        params.append(role)
    if category:
        query += " AND category = ?"
        params.append(category)
    if difficulty:
        query += " AND difficulty = ?"
        params.append(difficulty)
    if exclude_answered:
        query += """
            AND id NOT IN (
                SELECT question_id FROM answers WHERE session_id = ?
            )
        """
        params.append(session_id)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return []

    available = len(rows)
    if available < count:
        import logging
        logger = logging.getLogger("interview-pro")
        logger.warning(
            "draw_questions: 请求 %d 题但题库仅匹配 %d 题 "
            "(session=%d, category=%s, difficulty=%s)",
            count, available, session_id, category, difficulty,
        )

    selected = random.sample(rows, min(count, available))

    # 在 answers 表中预建记录
    conn = get_connection()
    for q in selected:
        conn.execute(
            "INSERT INTO answers (session_id, question_id) VALUES (?, ?)",
            (session_id, q["id"]),
        )
    conn.execute(
        "UPDATE sessions SET total_questions = total_questions + ? WHERE id = ?",
        (len(selected), session_id),
    )
    conn.commit()
    conn.close()

    return [dict(q) for q in selected]


def get_session_questions(session_id: int) -> list[dict]:
    """获取会话中所有题目及其作答情况。"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT q.*, a.user_answer, a.score, a.feedback, a.id as answer_id
        FROM answers a
        JOIN questions q ON q.id = a.question_id
        WHERE a.session_id = ?
        ORDER BY a.id
    """, (session_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def submit_answer(
    session_id: int,
    question_id: int,
    user_answer: str,
    score: float | None = None,
    feedback: str | None = None,
) -> bool:
    """提交作答。AI 评分由 evaluator 模块异步完成。"""
    conn = get_connection()
    conn.execute(
        """UPDATE answers
           SET user_answer = ?, score = ?, feedback = ?
           WHERE session_id = ? AND question_id = ?""",
        (user_answer, score, feedback, session_id, question_id),
    )
    conn.execute(
        "UPDATE sessions SET answered = answered + 1 WHERE id = ?",
        (session_id,),
    )
    conn.commit()
    conn.close()
    return True


def finish_session(session_id: int) -> dict | None:
    """结束会话，计算平均分并更新状态。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT AVG(score) as avg_score, COUNT(*) as cnt FROM answers WHERE session_id = ? AND score IS NOT NULL",
        (session_id,),
    ).fetchone()

    avg = row["avg_score"] if row["cnt"] > 0 else None
    conn.execute(
        "UPDATE sessions SET avg_score = ?, finished_at = datetime('now','localtime') WHERE id = ?",
        (avg, session_id),
    )
    conn.commit()
    conn.close()
    return get_session(session_id)
