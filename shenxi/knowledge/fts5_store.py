"""SQLite FTS5 全文检索 — 替代 pickle 关键词匹配

参考 Ahy Agent sqlite_memory.py 的 FTS5 模式：
- 自动建 FTS5 虚拟表 + 触发器同步
- jieba 中文分词
- 混合检索：FTS5 全文 + LIKE 兜底
"""

import os
import sqlite3
import time
import re
from langchain_text_splitters import RecursiveCharacterTextSplitter
import config

DB_PATH = os.path.join(config.DATA_DIR, "knowledge.db")

# jieba 分词（延迟加载）
_jieba = None


def _get_jieba():
    global _jieba
    if _jieba is None:
        try:
            import jieba
            _jieba = jieba
        except ImportError:
            _jieba = False
    return _jieba


def _tokenize(text: str) -> str:
    """中文分词：jieba 可用就用，否则按字符切"""
    jb = _get_jieba()
    if jb:
        return " ".join(jb.cut(text))
    # fallback: 中文按字切，英文按词切
    tokens = []
    for seg in re.findall(r'[一-鿿]|[a-zA-Z0-9]+', text):
        tokens.append(seg)
    return " ".join(tokens)


def _connect() -> sqlite3.Connection:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            source TEXT DEFAULT '',
            created_at REAL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text, source,
            content='chunks', content_rowid='id',
            tokenize='unicode61'
        );
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, text, source)
            VALUES (new.id, new.text, new.source);
        END;
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text, source)
            VALUES ('delete', old.id, old.text, old.source);
        END;
    """)


def build_index(docs: list[dict]) -> int:
    """构建 FTS5 索引"""
    if not docs:
        return 0

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n", "。", ".", " "],
    )

    chunks = []
    for doc in docs:
        for chunk in splitter.split_text(doc["content"]):
            tokenized = _tokenize(chunk)
            chunks.append({"text": tokenized, "source": doc["name"]})

    with _connect() as conn:
        _init_db(conn)
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM chunks_fts")
        conn.executemany(
            "INSERT INTO chunks (text, source, created_at) VALUES (?, ?, ?)",
            [(c["text"], c["source"], time.time()) for c in chunks],
        )
        conn.commit()

    return len(chunks)


def search(query: str, top_k: int = None) -> list[str]:
    """FTS5 全文检索 + LIKE 兜底"""
    if top_k is None:
        top_k = config.TOP_K_RETRIEVAL

    if not os.path.exists(DB_PATH):
        return []

    tokenized_query = _tokenize(query)

    with _connect() as conn:
        _init_db(conn)

        # FTS5 检索
        try:
            rows = conn.execute(
                "SELECT text FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                (tokenized_query, top_k),
            ).fetchall()
            results = [r[0] for r in rows]
        except sqlite3.OperationalError:
            results = []

        # FTS5 没结果时用 LIKE 兜底
        if not results:
            keywords = [kw for kw in re.findall(r'[一-鿿]+|[a-zA-Z0-9]+', query) if len(kw) > 1]
            if keywords:
                conditions = " OR ".join(["text LIKE ?"] * len(keywords))
                params = [f"%{kw}%" for kw in keywords]
                rows = conn.execute(
                    f"SELECT text FROM chunks WHERE {conditions} LIMIT ?",
                    params + [top_k],
                ).fetchall()
                results = [r[0] for r in rows]

    return results


def get_chunk_count() -> int:
    if not os.path.exists(DB_PATH):
        return 0
    with _connect() as conn:
        _init_db(conn)
        return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]


def clear_index():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
