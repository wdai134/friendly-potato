"""知识库管理 — 项目事实存储与检索。

将项目经验、决策、踩坑记录等结构化存储于 SQLite + FTS5，
与 profile.yaml 身份层解耦，支持 CRUD、分类浏览、全文搜索。
"""

import json
from agent.database import get_kb_connection
from agent.search import _segment_query


# ── CRUD ──


def add_knowledge(
    title: str,
    category: str,
    content: str,
    tech_stack: str = "",
    tags: list[str] | None = None,
    roles: list[str] | None = None,
    source: str = "manual",
) -> int:
    """添加知识条目，返回 ID。"""
    conn = get_kb_connection()
    cursor = conn.execute(
        """INSERT INTO knowledge_base (title, category, tech_stack, content, tags, roles, source)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (title, category, tech_stack, content,
         json.dumps(tags or [], ensure_ascii=False),
         json.dumps(roles or ["全部"], ensure_ascii=False),
         source),
    )
    conn.commit()
    conn.close()
    return cursor.lastrowid


def update_knowledge(knowledge_id: int, **kwargs) -> bool:
    """更新知识条目，只更新传入的字段。"""
    allowed = {"title", "category", "tech_stack", "content", "tags", "roles", "source"}
    fields = []
    values = []

    for key, val in kwargs.items():
        if key not in allowed or val is None:
            continue
        if key in ("tags", "roles") and isinstance(val, list):
            val = json.dumps(val, ensure_ascii=False)
        fields.append(f"{key} = ?")
        values.append(val)

    if not fields:
        return False

    fields.append("updated_at = datetime('now','localtime')")
    values.append(knowledge_id)

    conn = get_kb_connection()
    conn.execute(
        f"UPDATE knowledge_base SET {', '.join(fields)} WHERE id = ?", values
    )
    conn.commit()
    conn.close()
    return True


def delete_knowledge(knowledge_id: int) -> bool:
    """删除知识条目。FTS5 通过触发器同步。"""
    conn = get_kb_connection()
    conn.execute("DELETE FROM knowledge_base WHERE id = ?", (knowledge_id,))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def get_knowledge(knowledge_id: int) -> dict | None:
    """获取单条知识。"""
    conn = get_kb_connection()
    row = conn.execute(
        "SELECT * FROM knowledge_base WHERE id = ?", (knowledge_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_dict(row)


def list_knowledge(
    category: str | None = None,
    role: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """分页列出知识条目，可按分类/岗位筛选。"""
    conn = get_kb_connection()
    query = "SELECT * FROM knowledge_base WHERE 1=1"
    params: list = []

    if category:
        query += " AND category = ?"
        params.append(category)
    if role:
        query += " AND (roles LIKE ? OR roles LIKE '%\"全部\"%')"
        params.append(f'%"{role}"%')

    query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def count_knowledge(category: str | None = None, role: str | None = None) -> int:
    """统计条目数量。"""
    conn = get_kb_connection()
    query = "SELECT COUNT(*) as cnt FROM knowledge_base WHERE 1=1"
    params: list = []
    if category:
        query += " AND category = ?"
        params.append(category)
    if role:
        query += " AND (roles LIKE ? OR roles LIKE '%\"全部\"%')"
        params.append(f'%"{role}"%')
    row = conn.execute(query, params).fetchone()
    conn.close()
    return row["cnt"]


# ── Search ──


def search_knowledge(query: str, role: str | None = None, limit: int = 20) -> list[dict]:
    """FTS5 全文搜索知识库，jieba 分词 + 前缀匹配 + 岗位过滤。"""
    terms = _segment_query(query)
    if not terms:
        return []

    # 过滤单字中文碎片（同 search.py 逻辑）
    is_single_cjk = lambda t: len(t) == 1 and '一' <= t <= '鿿'
    terms = [t for t in terms if not is_single_cjk(t)]
    if not terms:
        terms = [query.strip()]

    # 原始输入作为全词前缀追加到首位
    text = query.strip()
    if text not in terms:
        terms.insert(0, text)

    fts_terms = [f'"{t}"*' for t in terms]
    fts_query = " AND ".join(fts_terms)

    conn = get_kb_connection()
    sql = """
        SELECT kb.*, rank
        FROM knowledge_base_fts
        JOIN knowledge_base kb ON kb.id = knowledge_base_fts.rowid
        WHERE knowledge_base_fts MATCH ?
    """
    params: list = [fts_query]
    if role:
        sql += " AND (kb.roles LIKE ? OR kb.roles LIKE '%\"全部\"%')"
        params.append(f'%"{role}"%')
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict(r)
        d.pop("rank", None)
        d = _row_to_dict(d)
        results.append(d)
    return results


# ── Categories ──


def get_categories() -> list[str]:
    """获取当前知识库中所有分类。"""
    conn = get_kb_connection()
    rows = conn.execute(
        "SELECT DISTINCT category FROM knowledge_base ORDER BY category"
    ).fetchall()
    conn.close()
    cats = [r["category"] for r in rows]
    return cats or ["project", "experience", "pitfall", "decision", "narrative"]


# ── Helpers ──


def _row_to_dict(row) -> dict:
    """sqlite3.Row → dict，反序列化 tags。"""
    d = dict(row)
    try:
        d["tags"] = json.loads(d.get("tags", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    return d
