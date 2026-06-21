"""题库管理 — 面试题目 CRUD。

提供题目增删改查 + 批量导入导出。
所有操作返回 dict（Row 转换为 dict），与 Streamlit UI 解耦。
"""

import json
from agent.database import get_connection


def add_question(
    title: str,
    role: str = "数据标注",
    content: str = "",
    answer: str = "",
    category: str = "未分类",
    difficulty: str = "中等",
    tags: list[str] | None = None,
    source: str = "",
) -> int:
    """添加题目，返回新题目 ID。"""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO questions (title, role, content, answer, category, difficulty, tags, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, role, content, answer, category, difficulty, json.dumps(tags or [], ensure_ascii=False), source),
    )
    conn.commit()
    conn.close()
    return cursor.lastrowid


def update_question(
    question_id: int,
    title: str | None = None,
    role: str | None = None,
    content: str | None = None,
    answer: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    tags: list[str] | None = None,
    source: str | None = None,
) -> bool:
    """更新题目，只更新传入的非 None 字段。返回是否成功。"""
    conn = get_connection()
    fields = []
    values = []

    for key, val in [
        ("title", title), ("role", role), ("content", content), ("answer", answer),
        ("category", category), ("difficulty", difficulty), ("source", source),
    ]:
        if val is not None:
            fields.append(f"{key} = ?")
            values.append(val)

    if tags is not None:
        fields.append("tags = ?")
        values.append(json.dumps(tags, ensure_ascii=False))

    if not fields:
        conn.close()
        return False

    fields.append("updated_at = datetime('now','localtime')")
    values.append(question_id)

    conn.execute(f"UPDATE questions SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def delete_question(question_id: int) -> bool:
    """删除题目。先清理关联答案，FTS5 索引通过触发器自动同步。"""
    conn = get_connection()
    # 先删除关联的答题记录（FK 约束）
    conn.execute("DELETE FROM answers WHERE question_id = ?", (question_id,))
    conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def get_question(question_id: int) -> dict | None:
    """获取单道题目。"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_dict(row)


def list_questions(
    role: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """分页列出题目，支持按岗位/分类/难度筛选。"""
    conn = get_connection()
    query = "SELECT * FROM questions WHERE 1=1"
    params: list = []

    if role:
        query += " AND role = ?"
        params.append(role)
    if category:
        query += " AND category = ?"
        params.append(category)
    if difficulty:
        query += " AND difficulty = ?"
        params.append(difficulty)

    query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def count_questions(role: str | None = None, category: str | None = None, difficulty: str | None = None) -> int:
    """统计题目数量。"""
    conn = get_connection()
    query = "SELECT COUNT(*) as cnt FROM questions WHERE 1=1"
    params: list = []
    if role:
        query += " AND role = ?"
        params.append(role)
    if category:
        query += " AND category = ?"
        params.append(category)
    if difficulty:
        query += " AND difficulty = ?"
        params.append(difficulty)

    row = conn.execute(query, params).fetchone()
    conn.close()
    return row["cnt"]


def import_questions(questions: list[dict]) -> tuple[int, list[dict]]:
    """批量导入题目。

    Returns:
        (成功数量, 失败列表)。失败列表每项包含 index/title/error。
    """
    count = 0
    errors: list[dict] = []
    for i, q in enumerate(questions):
        try:
            add_question(
                title=q.get("title", ""),
                role=q.get("role", "数据标注"),
                content=q.get("content", ""),
                answer=q.get("answer", ""),
                category=q.get("category", "未分类"),
                difficulty=q.get("difficulty", "中等"),
                tags=q.get("tags", []),
                source=q.get("source", ""),
            )
            count += 1
        except Exception as e:
            errors.append({
                "index": i,
                "title": q.get("title", "")[:50],
                "error": str(e),
            })
    return count, errors


def export_questions(
    role: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
) -> list[dict]:
    """导出题目为 dict 列表。"""
    return list_questions(role=role, category=category, difficulty=difficulty, limit=10000, offset=0)


def _row_to_dict(row) -> dict:
    """sqlite3.Row → dict，tags 字段 JSON 反序列化。"""
    d = dict(row)
    try:
        d["tags"] = json.loads(d.get("tags", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    return d
