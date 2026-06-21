"""测试 reporter 模块 — 报告生成。"""
import os
import pytest
from agent.database import init_db
from agent.question_bank import add_question
from agent.interviewer import start_session, submit_answer, finish_session
from agent.reporter import session_report, progress_trend, overall_stats


@pytest.fixture(autouse=True)
def clean_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    os.environ["DATABASE_PATH"] = db_path
    init_db(db_path)
    yield
    try:
        os.remove(db_path)
    except PermissionError:
        pass


def test_session_report():
    qid = add_question("测试题", category="Python基础")
    sid = start_session(mode="practice", question_ids=[qid])
    submit_answer(sid, qid, "回答", score=75, feedback="还行")
    finish_session(sid)

    report = session_report(sid)
    assert report is not None
    assert report["avg_score"] == 75
    assert report["total_questions"] == 1
    assert report["answered"] == 1
    assert len(report["answers"]) == 1
    assert report["score_distribution"]["good"] == 1


def test_session_report_not_found():
    assert session_report(99999) is None


def test_progress_trend():
    qid = add_question("题", category="Python基础")
    sid1 = start_session(question_ids=[qid])
    submit_answer(sid1, qid, "答1", score=60)
    finish_session(sid1)

    sid2 = start_session(question_ids=[qid])
    submit_answer(sid2, qid, "答2", score=90)
    finish_session(sid2)

    trend = progress_trend(limit=5)
    assert len(trend) >= 2
    scores = [t["avg_score"] for t in trend]
    assert 90 in scores or 60 in scores


def test_overall_stats():
    add_question("题1", category="Python基础")
    add_question("题2", category="算法")

    stats = overall_stats()
    assert stats["total_questions"] == 2
    assert stats["total_sessions"] >= 0
