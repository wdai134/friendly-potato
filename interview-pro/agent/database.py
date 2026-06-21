"""数据库层 — SQLite + FTS5 全文检索。

两个独立数据库：
  interview.db — questions / sessions / answers / questions_fts
  knowledge.db — knowledge_base / knowledge_base_fts
"""

import sqlite3
import os


DB_PATH = os.getenv("DATABASE_PATH", "./interview.db")
KB_DB_PATH = os.getenv("KNOWLEDGE_DB_PATH", "./knowledge.db")


# ═══════════════════════════════════════════════════════
# interview.db — 题目 / 面试 / 答题
# ═══════════════════════════════════════════════════════


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """获取 interview.db 连接。"""
    target = db_path or os.getenv("DATABASE_PATH", "./interview.db")
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str | None = None) -> sqlite3.Connection:
    """初始化 interview.db：建表 + FTS5 索引 + 触发器。"""
    conn = get_connection(db_path)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT '数据标注',
            content TEXT NOT NULL DEFAULT '',
            answer TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '未分类',
            difficulty TEXT NOT NULL DEFAULT '中等' CHECK(difficulty IN ('初级','中等','高级','专家')),
            tags TEXT NOT NULL DEFAULT '[]',
            source TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL DEFAULT 'practice' CHECK(mode IN ('practice','mock','quiz')),
            total_questions INTEGER NOT NULL DEFAULT 0,
            answered INTEGER NOT NULL DEFAULT 0,
            avg_score REAL,
            started_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            user_answer TEXT NOT NULL DEFAULT '',
            score REAL,
            feedback TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            FOREIGN KEY (question_id) REFERENCES questions(id)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS questions_fts USING fts5(
            title, content, answer,
            content='questions',
            content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS questions_ai AFTER INSERT ON questions BEGIN
            INSERT INTO questions_fts(rowid, title, content, answer)
            VALUES (new.id, new.title, new.content, new.answer);
        END;

        CREATE TRIGGER IF NOT EXISTS questions_ad AFTER DELETE ON questions BEGIN
            INSERT INTO questions_fts(questions_fts, rowid, title, content, answer)
            VALUES ('delete', old.id, old.title, old.content, old.answer);
        END;

        CREATE TRIGGER IF NOT EXISTS questions_au AFTER UPDATE ON questions BEGIN
            INSERT INTO questions_fts(questions_fts, rowid, title, content, answer)
            VALUES ('delete', old.id, old.title, old.content, old.answer);
            INSERT INTO questions_fts(rowid, title, content, answer)
            VALUES (new.id, new.title, new.content, new.answer);
        END;
    """)

    # 迁移：对已有数据库补 role 列（SQLite ALTER TABLE 幂等）
    try:
        conn.execute("ALTER TABLE questions ADD COLUMN role TEXT NOT NULL DEFAULT '数据标注'")
    except Exception:
        pass  # 列已存在

    conn.commit()
    return conn


# ═══════════════════════════════════════════════════════
# knowledge.db — 知识库
# ═══════════════════════════════════════════════════════


def get_kb_connection(db_path: str | None = None) -> sqlite3.Connection:
    """获取 knowledge.db 连接。"""
    target = db_path or os.getenv("KNOWLEDGE_DB_PATH", "./knowledge.db")
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_kb_db(db_path: str | None = None) -> sqlite3.Connection:
    """初始化 knowledge.db：建表 + FTS5 + 触发器。"""
    conn = get_kb_connection(db_path)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            tech_stack TEXT DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            source TEXT NOT NULL DEFAULT 'manual',
            roles TEXT NOT NULL DEFAULT '["全部"]',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_base_fts USING fts5(
            title, content, tech_stack, tags,
            content='knowledge_base',
            content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS kb_ai AFTER INSERT ON knowledge_base BEGIN
            INSERT INTO knowledge_base_fts(rowid, title, content, tech_stack, tags)
            VALUES (new.id, new.title, new.content, new.tech_stack, new.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS kb_ad AFTER DELETE ON knowledge_base BEGIN
            INSERT INTO knowledge_base_fts(knowledge_base_fts, rowid, title, content, tech_stack, tags)
            VALUES ('delete', old.id, old.title, old.content, old.tech_stack, old.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS kb_au AFTER UPDATE ON knowledge_base BEGIN
            INSERT INTO knowledge_base_fts(knowledge_base_fts, rowid, title, content, tech_stack, tags)
            VALUES ('delete', old.id, old.title, old.content, old.tech_stack, old.tags);
            INSERT INTO knowledge_base_fts(rowid, title, content, tech_stack, tags)
            VALUES (new.id, new.title, new.content, new.tech_stack, new.tags);
        END;
    """)

    # 迁移：对已有 knowledge.db 补 roles 列
    try:
        conn.execute("ALTER TABLE knowledge_base ADD COLUMN roles TEXT NOT NULL DEFAULT '[\"全部\"]'")
    except Exception:
        pass

    conn.commit()
    return conn
