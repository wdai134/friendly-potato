"""全文搜索 — FTS5 + BM25 排序。

搜索题目 title + content + answer，按 BM25 相关性排序。
支持中文搜索（FTS5 内置 Unicode 分词，配合 jieba 可选加载）。
"""

from agent.database import get_connection


def search_questions(
    query: str,
    category: str | None = None,
    difficulty: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """FTS5 全文搜索，返回按 BM25 排序的题目列表。

    Args:
        query: 搜索关键词
        category: 可选，限定分类
        difficulty: 可选，限定难度
        limit: 返回上限
    """
    conn = get_connection()

    # FTS5 BM25 排序查询
    # 使用 simple 匹配模式，支持多词搜索
    fts_query = _build_fts_query(query)

    sql = """
        SELECT q.*, rank
        FROM questions_fts
        JOIN questions q ON q.id = questions_fts.rowid
        WHERE questions_fts MATCH ?
    """
    params = [fts_query]

    if category:
        sql += " AND q.category = ?"
        params.append(category)
    if difficulty:
        sql += " AND q.difficulty = ?"
        params.append(difficulty)

    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict(r)
        # rank 仅用于排序，不暴露给前端
        d.pop("rank", None)
        results.append(d)

    return results


def _segment_query(raw: str) -> list[str]:
    """对查询语句分词，jieba 优先（中文），失败时降级为 split。

    Returns:
        分词后的词语列表，不含空白项。
    """
    text = raw.strip()
    if not text:
        return []

    try:
        import jieba
        return [t for t in jieba.cut_for_search(text) if t.strip()]
    except ImportError:
        # jieba 未安装时降级为空格分词
        return text.split()


def _build_fts_query(raw: str) -> str:
    """构建 FTS5 查询字符串。

    jieba 分词后每个词做前缀匹配，多词用 AND 连接。
    FTS5 unicode61 在此 SQLite 版本将连续中文作为整体 token，
    因此额外追加原始输入作为全词前缀，并过滤单字中文碎片。
    """
    text = raw.strip()
    terms = _segment_query(text)
    if not terms:
        return '""'

    # 过滤单字中文（jieba 子词碎片，FTS5 中无法匹配任何 token 前缀）
    is_single_cjk = lambda t: len(t) == 1 and '一' <= t <= '鿿'
    terms = [t for t in terms if not is_single_cjk(t)]
    if not terms:
        # 只剩原始输入兜底
        terms = [text]

    # 原始输入作为全词前缀追加到首位（去重）
    if text not in terms:
        terms.insert(0, text)

    fts_terms = [f'"{t}"*' for t in terms]
    return " AND ".join(fts_terms)
