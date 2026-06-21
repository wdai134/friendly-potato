"""测试 database 模块 — 建表和连接。"""
import os
import pytest
from agent.database import init_db, get_connection


@pytest.fixture
def test_db(tmp_path):
    """创建独立测试数据库。"""
    db_path = str(tmp_path / "test.db")
    yield db_path
    try:
        os.remove(db_path)
    except (PermissionError, FileNotFoundError):
        pass


def test_init_db_creates_tables(test_db):
    """init_db 应该创建 questions / sessions / answers / questions_fts 表。"""
    conn = init_db(test_db)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {t["name"] for t in tables}
    assert "questions" in names
    assert "sessions" in names
    assert "answers" in names
    assert "questions_fts" in names
    conn.close()


def test_init_db_is_idempotent(test_db):
    """多次调用 init_db 不应报错。"""
    conn1 = init_db(test_db)
    conn2 = init_db(test_db)
    conn1.close()
    conn2.close()


def test_wal_mode_enabled(test_db):
    """get_connection 应自动开启 WAL 模式。"""
    init_db(test_db)
    conn = get_connection(test_db)
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0].upper() == "WAL"
    conn.close()
