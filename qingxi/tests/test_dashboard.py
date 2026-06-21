"""测试 dashboard/app.py — 模块导入和结构验证。"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestDashboardImports:
    """验证 dashboard 模块可导入且语法正确。"""

    def test_module_loads_without_streamlit_runtime(self):
        """语法验证：模块可被 Python 解析，import 无不存在的依赖。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "dashboard_app",
            PROJECT_ROOT / "dashboard" / "app.py",
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)

        try:
            spec.loader.exec_module(module)
        except ModuleNotFoundError as e:
            if "streamlit" in str(e).lower():
                pytest.skip("Streamlit 未安装（非阻塞，CLI 测试通过即交付）")
            raise

    def test_format_size(self):
        """工具函数 format_size 逻辑正确。"""
        from dashboard.app import format_size
        assert format_size(0) == "0.0 B"
        assert format_size(1024) == "1.0 KB"
        assert format_size(1024 * 1024) == "1.0 MB"


class TestDashboardStructure:
    """验证页面函数完整性。"""

    def test_page_functions_exist(self):
        """三个页面 + main 入口都已定义。"""
        import dashboard.app as app
        assert callable(app.page_scan)
        assert callable(app.page_dedup)
        assert callable(app.page_restore)
        assert callable(app.main)

    def test_state_init_exists(self):
        """会话状态管理函数存在。"""
        import dashboard.app as app
        assert callable(app.init_state)
        assert callable(app.load_safelist)
