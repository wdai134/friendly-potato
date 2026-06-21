"""测试 interviewer 模块 — 面试会话管理。"""
import os
import pytest
from agent.database import init_db
from agent.question_bank import add_question
from agent.interviewer import (
    start_session, get_session, list_sessions,
    draw_questions, get_session_questions, submit_answer, finish_session,
)


@pytest.fixture(autouse=True)
def clean_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    os.environ["DATABASE_PATH"] = db_path
    init_db(db_path)
    # 预设题目
    add_question("题1", category="Python基础", difficulty="初级")
    add_question("题2", category="Python基础", difficulty="中等")
    add_question("题3", category="算法", difficulty="中等")
    add_question("题4", category="数据库", difficulty="高级")
    yield
    try:
        os.remove(db_path)
    except PermissionError:
        pass


def test_start_session_basic():
    sid = start_session(mode="practice")
    assert sid > 0
    s = get_session(sid)
    assert s["mode"] == "practice"
    assert s["total_questions"] == 0


def test_start_session_with_questions():
    sid = start_session(mode="mock", question_ids=[1, 2])
    s = get_session(sid)
    assert s["total_questions"] == 2


def test_list_sessions():
    start_session()
    start_session()
    sessions = list_sessions()
    assert len(sessions) >= 2


def test_draw_questions():
    sid = start_session(mode="practice")
    questions = draw_questions(sid, count=2)
    assert len(questions) == 2
    questions2 = draw_questions(sid, count=2)
    # 不应重复抽取已答题目
    ids1 = {q["id"] for q in questions}
    ids2 = {q["id"] for q in questions2}
    assert ids1.isdisjoint(ids2)


def test_draw_questions_by_category():
    sid = start_session()
    questions = draw_questions(sid, count=5, category="Python基础")
    assert len(questions) > 0
    for q in questions:
        assert q["category"] == "Python基础"


def test_submit_answer_and_finish():
    sid = start_session(mode="practice", question_ids=[1])
    submit_answer(sid, 1, "我的回答", score=85, feedback="不错")
    qs = get_session_questions(sid)
    assert len(qs) == 1
    assert qs[0]["score"] == 85
    assert qs[0]["user_answer"] == "我的回答"

    session = finish_session(sid)
    assert session["avg_score"] == 85
    assert session["answered"] == 1
    assert session["finished_at"] is not None


def test_draw_questions_shortfall():
    """题库不足时应降级返回可用题目，不抛异常。"""
    sid = start_session()
    # 题库仅 4 题，请求 10 题
    questions = draw_questions(sid, count=10)
    assert len(questions) <= 4  # 返回所有可用
    assert len(questions) > 0
