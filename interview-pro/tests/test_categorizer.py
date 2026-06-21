"""测试 categorizer 模块 — 分类体系。"""
import os
import pytest
from agent.database import init_db
from agent.question_bank import add_question
from agent.categorizer import (
    get_categories, get_category_stats, get_all_tags, auto_categorize,
    DIFFICULTY_LEVELS,
)


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


def test_get_categories_default():
    """无数据时返回默认分类。"""
    cats = get_categories()
    assert "Python基础" in cats
    assert "算法与数据结构" in cats


def test_get_categories_from_data():
    """有数据时应包含数据中的分类。"""
    add_question("题1", category="自定义分类")
    cats = get_categories()
    assert "自定义分类" in cats


def test_get_category_stats():
    add_question("题1", category="Python基础", difficulty="初级")
    add_question("题2", category="Python基础", difficulty="中等")
    add_question("题3", category="算法", difficulty="高级")
    stats = get_category_stats()
    py_stats = next(s for s in stats if s["category"] == "Python基础")
    assert py_stats["count"] == 2
    assert py_stats["junior"] >= 1


def test_get_all_tags():
    add_question("题1", tags=["Python", "GIL"])
    add_question("题2", tags=["Python", "装饰器"])
    tags = get_all_tags()
    assert "Python" in tags
    assert "GIL" in tags
    assert "装饰器" in tags


def test_auto_categorize_python():
    result = auto_categorize("Python 装饰器原理", "装饰器用于修改函数行为")
    assert result["category"] == "Python基础"


def test_auto_categorize_algorithm():
    result = auto_categorize("二叉树遍历", "二叉树的先序中序后序遍历")
    assert result["category"] == "算法与数据结构"


def test_auto_categorize_frontend():
    """新增分类：前端开发。"""
    result = auto_categorize("React 组件渲染优化", "使用 memo 和 useMemo 优化渲染性能")
    assert result["category"] == "前端开发"


def test_auto_categorize_devops():
    """新增分类：DevOps运维。"""
    result = auto_categorize("Docker 容器化部署", "使用 Docker Compose 编排微服务")
    assert result["category"] == "DevOps运维"


def test_difficulty_levels():
    assert DIFFICULTY_LEVELS == ["初级", "中等", "高级", "专家"]
