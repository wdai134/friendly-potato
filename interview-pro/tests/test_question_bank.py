"""测试 question_bank 模块 — 题目 CRUD。"""
import os
import json
import pytest
from agent.database import init_db, get_connection
from agent.question_bank import (
    add_question, get_question, update_question, delete_question,
    list_questions, count_questions, import_questions, export_questions,
)


@pytest.fixture(autouse=True)
def clean_db(tmp_path):
    """每个测试使用独立数据库，隔离数据泄漏。"""
    db_path = str(tmp_path / "test.db")
    os.environ["DATABASE_PATH"] = db_path
    init_db(db_path)
    yield
    # 清理：关闭所有连接后删除
    try:
        os.remove(db_path)
    except PermissionError:
        pass  # Windows SQLite 锁，测试间不共享不影响


def test_add_and_get_question():
    qid = add_question(
        title="Python GIL 是什么？",
        content="请解释GIL",
        answer="全局解释器锁...",
        category="Python基础",
        difficulty="中等",
        tags=["Python", "GIL"],
        source="LeetCode",
    )
    q = get_question(qid)
    assert q is not None
    assert q["title"] == "Python GIL 是什么？"
    assert q["category"] == "Python基础"
    assert q["difficulty"] == "中等"
    assert isinstance(q["tags"], list)
    assert "Python" in q["tags"]


def test_list_questions():
    add_question("A题")
    add_question("B题")
    add_question("C题")
    results = list_questions(limit=10)
    assert len(results) == 3


def test_count_questions():
    assert count_questions() == 0
    add_question("A题")
    add_question("B题")
    assert count_questions() == 2


def test_update_question():
    qid = add_question("原标题", content="原描述")
    ok = update_question(qid, title="新标题", content="新描述")
    assert ok is True
    q = get_question(qid)
    assert q["title"] == "新标题"
    assert q["content"] == "新描述"


def test_delete_question():
    qid = add_question("待删除")
    assert get_question(qid) is not None
    ok = delete_question(qid)
    assert ok is True
    assert get_question(qid) is None


def test_delete_cascades_answers():
    from agent.interviewer import start_session, submit_answer
    qid = add_question("待删除题目")
    sid = start_session(mode="practice", question_ids=[qid])
    submit_answer(sid, qid, "我的回答", score=80)
    ok = delete_question(qid)
    assert ok is True


def test_import_export_roundtrip():
    qs = [
        {"title": "题1", "content": "描述1", "category": "Python基础", "difficulty": "初级"},
        {"title": "题2", "content": "描述2", "category": "算法", "difficulty": "中等"},
    ]
    count, errors = import_questions(qs)
    assert count == 2
    assert errors == []

    exported = export_questions()
    assert len(exported) == 2
    titles = {q["title"] for q in exported}
    assert titles == {"题1", "题2"}


def test_import_questions_collects_errors():
    """add_question 抛异常时错误应收集到 errors，不中断其余导入。"""
    from unittest.mock import patch

    qs = [
        {"title": "会失败", "content": "x"},
        {"title": "正常题"},
        {"title": "也会失败"},
    ]

    def mock_add(**kwargs):
        if kwargs.get("title") in ("会失败", "也会失败"):
            raise RuntimeError("模拟失败")
        return 42

    with patch("agent.question_bank.add_question", side_effect=mock_add):
        count, errors = import_questions(qs)

    assert count == 1  # 只有"正常题"成功
    assert len(errors) == 2
    assert errors[0]["title"] == "会失败"
    assert errors[0]["error"] == "模拟失败"
    assert errors[1]["title"] == "也会失败"
    assert errors[0]["index"] == 0
    assert errors[1]["index"] == 2
