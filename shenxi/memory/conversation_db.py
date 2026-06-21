import os
import sqlite3
import time
import config


def _db_path():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    return os.path.join(config.DATA_DIR, "conversations.db")


def _conn():
    return sqlite3.connect(_db_path())


def init_db():
    with _conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT DEFAULT '新对话',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)
        db.commit()


def create_conversation(title: str = "新对话") -> int:
    now = time.time()
    with _conn() as db:
        cur = db.execute(
            "INSERT INTO conversations (title, created_at, updated_at) VALUES (?, ?, ?)",
            (title, now, now),
        )
        db.commit()
        return cur.lastrowid


def save_message(conversation_id: int, role: str, content: str):
    with _conn() as db:
        db.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, time.time()),
        )
        db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (time.time(), conversation_id),
        )
        db.commit()


def load_messages(conversation_id: int) -> list[dict]:
    with _conn() as db:
        rows = db.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [{"role": r, "content": c} for r, c in rows]


def list_conversations() -> list[dict]:
    with _conn() as db:
        rows = db.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]}
        for r in rows
    ]


def update_title(conversation_id: int, title: str):
    with _conn() as db:
        db.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))
        db.commit()


def delete_conversation(conversation_id: int):
    with _conn() as db:
        db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        db.commit()


def auto_title(first_message: str) -> str:
    return first_message[:30] + ("..." if len(first_message) > 30 else "")
