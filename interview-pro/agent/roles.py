"""岗位体系 — 读 config/roles.yaml 提供岗位→阶段→分类三层组织。"""

import os
import yaml

_ROLES_CACHE: list[dict] | None = None
_DEFAULT_ROLE = "数据标注"


def _load_roles() -> list[dict]:
    """加载 roles.yaml，结果缓存。"""
    global _ROLES_CACHE
    if _ROLES_CACHE is not None:
        return _ROLES_CACHE

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "roles.yaml",
    )
    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        _ROLES_CACHE = data.get("roles", []) if data else []
    except Exception:
        _ROLES_CACHE = []

    return _ROLES_CACHE


def get_roles() -> list[dict]:
    """所有岗位 name/icon/description/categories/stages。"""
    return _load_roles()


def get_role_names() -> list[str]:
    """所有岗位名称列表。"""
    return [r["name"] for r in _load_roles()]


def get_role(name: str) -> dict | None:
    """获取单个岗位详情。"""
    for r in _load_roles():
        if r["name"] == name:
            return r
    return None


def get_categories_for_role(role: str) -> list[str]:
    """获取某岗位下的所有分类。"""
    r = get_role(role)
    return r["categories"] if r else []


def get_stages_for_role(role: str) -> list[str]:
    """获取某岗位的面试阶段列表。"""
    r = get_role(role)
    return r["stages"] if r else []


def get_default_role() -> str:
    """默认岗位名。"""
    roles = _load_roles()
    return roles[0]["name"] if roles else _DEFAULT_ROLE
