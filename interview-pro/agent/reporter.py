"""报告生成器 — 面试成绩报告与统计分析。

产出：
  - 单次面试成绩单
  - 历史进步趋势
  - 薄弱环节识别
"""

from agent.database import get_connection
from datetime import datetime


def session_report(session_id: int) -> dict | None:
    """生成单次面试的完整成绩单。

    Returns:
        dict: session info + questions + stats
    """
    conn = get_connection()
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        conn.close()
        return None

    answers = conn.execute("""
        SELECT q.title, q.category, q.difficulty,
               a.user_answer, a.score, a.feedback
        FROM answers a
        JOIN questions q ON q.id = a.question_id
        WHERE a.session_id = ?
        ORDER BY a.id
    """, (session_id,)).fetchall()

    conn.close()

    answer_list = [dict(a) for a in answers]
    scores = [a["score"] for a in answer_list if a["score"] is not None]

    return {
        "session_id": session_id,
        "mode": session["mode"],
        "started_at": session["started_at"],
        "finished_at": session["finished_at"],
        "total_questions": session["total_questions"],
        "answered": session["answered"],
        "avg_score": session["avg_score"],
        "answers": answer_list,
        "score_distribution": {
            "excellent": sum(1 for s in scores if s >= 85),
            "good": sum(1 for s in scores if 70 <= s < 85),
            "fair": sum(1 for s in scores if 50 <= s < 70),
            "poor": sum(1 for s in scores if s < 50),
        },
    }


def progress_trend(limit: int = 10) -> list[dict]:
    """获取最近 N 次面试的分数趋势。"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, mode, total_questions, answered, avg_score, started_at
        FROM sessions
        WHERE avg_score IS NOT NULL
        ORDER BY started_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def weakness_analysis(session_ids: list[int] | None = None, top_n: int = 5) -> list[dict]:
    """薄弱环节分析：找出得分最低的题目分类。

    Args:
        session_ids: 限定分析哪些会话，None = 全部历史
        top_n: 返回最薄弱的 N 个分类
    """
    conn = get_connection()

    if session_ids:
        placeholders = ",".join("?" * len(session_ids))
        query = f"""
            SELECT q.category, AVG(a.score) as avg_score, COUNT(*) as count
            FROM answers a
            JOIN questions q ON q.id = a.question_id
            WHERE a.score IS NOT NULL AND a.session_id IN ({placeholders})
            GROUP BY q.category
            HAVING count >= 2
            ORDER BY avg_score ASC
            LIMIT ?
        """
        params = [*session_ids, top_n]
    else:
        query = """
            SELECT q.category, AVG(a.score) as avg_score, COUNT(*) as count
            FROM answers a
            JOIN questions q ON q.id = a.question_id
            WHERE a.score IS NOT NULL
            GROUP BY q.category
            HAVING count >= 2
            ORDER BY avg_score ASC
            LIMIT ?
        """
        params = [top_n]

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def overall_stats() -> dict:
    """全局统计数据。"""
    conn = get_connection()
    total_q = conn.execute("SELECT COUNT(*) as cnt FROM questions").fetchone()["cnt"]
    total_s = conn.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()["cnt"]
    total_a = conn.execute("SELECT COUNT(*) as cnt FROM answers WHERE score IS NOT NULL").fetchone()["cnt"]
    overall_avg = conn.execute(
        "SELECT AVG(score) as avg FROM answers WHERE score IS NOT NULL"
    ).fetchone()["avg"]

    cat_stats = conn.execute("""
        SELECT category, COUNT(*) as cnt, AVG(difficulty_rank) as avg_diff
        FROM (
            SELECT category,
                   CASE difficulty
                       WHEN '初级' THEN 1 WHEN '中等' THEN 2
                       WHEN '高级' THEN 3 WHEN '专家' THEN 4
                   END as difficulty_rank
            FROM questions
        )
        GROUP BY category
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    return {
        "total_questions": total_q,
        "total_sessions": total_s,
        "total_answers": total_a,
        "overall_avg_score": round(overall_avg, 1) if overall_avg else None,
        "top_categories": [dict(r) for r in cat_stats],
        "generated_at": datetime.now().isoformat(),
    }
