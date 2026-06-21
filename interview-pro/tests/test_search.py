"""测试 search 模块 — FTS5 全文搜索。"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from agent.database import init_db
from agent.question_bank import add_question
from agent.search import search_questions, _segment_query, _build_fts_query


@pytest.fixture(autouse=True)
def clean_db(tmp_path):
    """每个测试使用独立数据库。"""
    db_path = str(tmp_path / "test.db")
    os.environ["DATABASE_PATH"] = db_path
    init_db(db_path)
    # 预设测试数据
    add_question(
        "Python 装饰器原理",
        "解释装饰器的工作机制",
        "装饰器是一个接受函数并返回函数的可调用对象...",
        category="Python基础",
    )
    add_question(
        "Docker 容器化部署",
        "如何使用 Docker 部署 Python 应用",
        "编写 Dockerfile...",
        category="DevOps运维",
    )
    add_question(
        "HTTP 与 HTTPS 的区别",
        "解释两者的差异",
        "HTTPS 通过 TLS 加密...",
        category="网络协议",
    )
    yield
    try:
        os.remove(db_path)
    except PermissionError:
        pass


def test_search_by_keyword():
    results = search_questions("装饰器")
    assert len(results) >= 1
    titles = {r["title"] for r in results}
    assert "Python 装饰器原理" in titles


def test_search_english():
    results = search_questions("Docker")
    assert len(results) >= 1
    assert results[0]["title"] == "Docker 容器化部署"


def test_search_no_match():
    results = search_questions("量子计算机")
    assert results == []


def test_search_with_category_filter():
    results = search_questions("装饰器", category="Python基础")
    assert len(results) >= 1
    assert results[0]["category"] == "Python基础"
    results = search_questions("装饰器", category="网络协议")
    assert results == []


def test_search_result_has_no_rank_field():
    results = search_questions("HTTPS")
    assert len(results) >= 1
    assert "rank" not in results[0]


# ═══════════════════════════════════════════════════════════════════════
# _segment_query() tests
# ═══════════════════════════════════════════════════════════════════════

def test_segment_query_with_jieba():
    """jieba 可用时应正确分词中文。"""
    terms = _segment_query("Python装饰器的使用场景")
    assert "Python" in terms
    # jieba 会把"装饰器"切为"装饰"+ "器"
    assert "装饰" in terms
    assert "器" in terms
    assert len(terms) >= 3  # Python + 装饰 + 器 + 的 + 使用 + 场景


def test_segment_query_pure_english():
    """纯英文查询应正确按词返回。"""
    terms = _segment_query("Docker container deploy")
    for word in ["Docker", "container", "deploy"]:
        assert word in terms


def test_segment_query_empty():
    """空查询返回空列表。"""
    assert _segment_query("") == []
    assert _segment_query("   ") == []


# ═══════════════════════════════════════════════════════════════════════
# _build_fts_query() tests
# ═══════════════════════════════════════════════════════════════════════

def test_build_fts_query_single_term():
    result = _build_fts_query("装饰器")
    # "装饰器" → jieba → ["装饰", "器"] → 字符级短语 + 单字前缀
    assert '"' in result
    assert len(result) > 0


def test_build_fts_query_chinese_jieba_prefix():
    """原始查询应作为全词前缀，单字中文被过滤。"""
    result = _build_fts_query("Python 装饰器")
    assert 'AND' in result
    # 原始输入作为第一个 term
    assert result.startswith('"Python 装饰器"*')
    assert '"Python"*' in result
    assert '"装饰"*' in result
    # 单字"器"被过滤，不应出现
    assert '"器"*' not in result


def test_build_fts_query_empty():
    result = _build_fts_query("")
    assert result == '""'
