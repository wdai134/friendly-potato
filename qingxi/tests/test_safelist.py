"""测试 agent/safelist.py + executor 白名单拦截。"""

import pytest

from agent.executor import execute_cleanup
from agent.safelist import SafeList, SafeListEntry, GREEN, YELLOW, RED, NONE


# ════════════════════════════════════════════════════════════════
# SafeList 配置加载
# ════════════════════════════════════════════════════════════════

class TestSafeListLoad:
    def test_from_yaml_config(self, tmp_path):
        config = tmp_path / "safelist.yaml"
        config.write_text("""
safelist:
  - pattern: "*.exe"
    tier: red
    reason: "可执行文件"
  - pattern: "**/Documents/**"
    tier: green
    reason: "文档保护"
  - pattern: "*.pdf"
    tier: yellow
    reason: "PDF确认后清理"
""", encoding="utf-8")

        sl = SafeList.from_config(str(config))
        assert len(sl) == 3

    def test_empty_config(self, tmp_path):
        config = tmp_path / "empty.yaml"
        config.write_text("safelist: []\n", encoding="utf-8")
        sl = SafeList.from_config(str(config))
        assert len(sl) == 0

    def test_empty_factory(self):
        sl = SafeList.empty()
        assert len(sl) == 0
        assert not sl
        assert sl.check("anything.txt") == NONE

    def test_config_not_found(self):
        with pytest.raises(FileNotFoundError):
            SafeList.from_config("/nonexistent/safelist.yaml")


# ════════════════════════════════════════════════════════════════
# 三色匹配
# ════════════════════════════════════════════════════════════════

class TestCheck:
    @pytest.fixture
    def safelist(self):
        return SafeList([
            SafeListEntry("*.exe", RED, "可执行文件"),
            SafeListEntry("*.dll", RED, "系统DLL"),
            SafeListEntry("C:/Windows/**", RED, "Windows系统目录"),
            SafeListEntry("*.psd", GREEN, "设计源文件"),
            SafeListEntry("**/Documents/**", GREEN, "文档目录"),
            SafeListEntry("*.pdf", YELLOW, "PDF确认后清理"),
            SafeListEntry("*.zip", YELLOW, "压缩包确认后清理"),
        ])

    def test_red_match_exe(self, safelist):
        assert safelist.check("C:/tools/hack.exe") == RED

    def test_red_match_dll(self, safelist):
        assert safelist.check("C:/Windows/System32/kernel32.dll") == RED

    def test_red_match_windows_dir(self, safelist):
        assert safelist.check("C:/Windows/System32/drivers/etc/hosts") == RED

    def test_green_match_psd(self, safelist):
        assert safelist.check("C:/projects/logo.psd") == GREEN

    def test_green_match_documents(self, safelist):
        assert safelist.check("C:/Users/john/Documents/tax/2024.pdf") == GREEN

    def test_yellow_match_pdf(self, safelist):
        assert safelist.check("C:/downloads/report.pdf") == YELLOW

    def test_none_no_match(self, safelist):
        assert safelist.check("C:/temp/junk.tmp") == NONE

    def test_red_priority_over_green(self, safelist):
        # .exe 是 red，即使路径在 Documents 下也返回 red
        assert safelist.check("C:/Users/john/Documents/setup.exe") == RED

    def test_green_priority_over_yellow(self, safelist):
        # .pdf 是 yellow，但在 Documents 下匹配 green，返回 green
        assert safelist.check("C:/Users/john/Documents/report.pdf") == GREEN

    def test_is_blocked(self, safelist):
        assert safelist.is_blocked("C:/virus.exe") is True
        assert safelist.is_blocked("C:/doc.pdf") is False

    def test_is_protected(self, safelist):
        assert safelist.is_protected("C:/design/logo.psd") is True
        assert safelist.is_protected("C:/data.csv") is False


# ════════════════════════════════════════════════════════════════
# 通配符匹配
# ════════════════════════════════════════════════════════════════

class TestMatch:
    def test_exact_path_case_insensitive(self):
        assert SafeList._match("C:/Windows/System32", "c:/windows/system32")

    def test_wildcard_extension(self):
        assert SafeList._match("file.pdf", "*.pdf")

    def test_wildcard_name(self):
        assert SafeList._match("backup_2024.bak", "*.bak")

    def test_recursive_wildcard_documents(self):
        assert SafeList._match(
            "C:/Users/john/Documents/deep/nested/file.txt",
            "**/Documents/**",
        )

    def test_recursive_wildcard_windows(self):
        assert SafeList._match(
            "C:/Windows/System32/drivers/file.sys",
            "C:/Windows/**",
        )

    def test_backslash_normalized(self):
        assert SafeList._match(
            "C:\\Users\\john\\Documents\\file.txt",
            "**/Documents/**",
        )

    def test_dot_prefix_git(self):
        assert SafeList._match(
            "C:/project/.git/objects/abc",
            ".git/**",
        )


# ════════════════════════════════════════════════════════════════
# get_tier_summary
# ════════════════════════════════════════════════════════════════

class TestGetTierSummary:
    def test_returns_emoji(self):
        sl = SafeList([SafeListEntry("*.exe", RED, "test")])
        summary = sl.get_tier_summary("app.exe")
        assert summary["tier"] == RED
        assert summary["emoji"] == "🔴"
        assert summary["name"] == "app.exe"


# ════════════════════════════════════════════════════════════════
# executor 白名单拦截
# ════════════════════════════════════════════════════════════════

class TestExecutorWithSafeList:
    def test_red_file_blocked(self, tmp_path):
        """🔴 文件被 executor 拦截，不移动。"""
        from agent.scanner import FileEntry

        src = tmp_path / "setup.exe"
        src.write_text("fake exe")

        quarantine = tmp_path / "quarantine"
        quarantine.mkdir()

        sl = SafeList([SafeListEntry("*.exe", RED, "可执行文件")])
        entry = FileEntry(
            path=str(src), name="setup.exe", extension=".exe",
            size_bytes=9, modified_at="2024-01-01", age_days=999,
            matched_rule="test", action="cleanup",
        )

        result = execute_cleanup([entry], str(quarantine), safelist=sl)
        assert result.success_count == 0
        assert len(result.blocked) == 1
        assert src.exists()

    def test_green_file_skipped(self, tmp_path):
        """🟢 文件被 executor 跳过，不移动。"""
        from agent.scanner import FileEntry

        src = tmp_path / "logo.psd"
        src.write_text("design data")

        quarantine = tmp_path / "quarantine"
        quarantine.mkdir()

        sl = SafeList([SafeListEntry("*.psd", GREEN, "设计源文件")])
        entry = FileEntry(
            path=str(src), name="logo.psd", extension=".psd",
            size_bytes=12, modified_at="2024-01-01", age_days=999,
            matched_rule="test", action="cleanup",
        )

        result = execute_cleanup([entry], str(quarantine), safelist=sl)
        assert result.success_count == 0
        assert len(result.skipped) == 1
        assert src.exists()

    def test_no_safelist_cleans_normally(self, tmp_path):
        """无白名单时正常清理。"""
        from agent.scanner import FileEntry

        src = tmp_path / "junk.tmp"
        src.write_text("trash")

        quarantine = tmp_path / "quarantine"
        quarantine.mkdir()

        entry = FileEntry(
            path=str(src), name="junk.tmp", extension=".tmp",
            size_bytes=5, modified_at="2024-01-01", age_days=999,
            matched_rule="test", action="cleanup",
        )

        result = execute_cleanup([entry], str(quarantine))
        assert result.success_count == 1
        assert not src.exists()

    def test_yellow_file_still_cleaned(self, tmp_path):
        """🟡 文件: executor 放行（黄灯不拦截）。"""
        from agent.scanner import FileEntry

        src = tmp_path / "old_report.pdf"
        src.write_text("pdf content")

        quarantine = tmp_path / "quarantine"
        quarantine.mkdir()

        sl = SafeList([SafeListEntry("*.pdf", YELLOW, "确认后清理")])
        entry = FileEntry(
            path=str(src), name="old_report.pdf", extension=".pdf",
            size_bytes=11, modified_at="2024-01-01", age_days=999,
            matched_rule="test", action="cleanup",
        )

        result = execute_cleanup([entry], str(quarantine), safelist=sl)
        assert result.success_count == 1
        assert not src.exists()

    def test_empty_safelist_has_no_effect(self, tmp_path):
        """空白名单不影响清理。"""
        from agent.scanner import FileEntry

        src = tmp_path / "junk.tmp"
        src.write_text("trash")

        quarantine = tmp_path / "quarantine"
        quarantine.mkdir()

        sl = SafeList.empty()
        entry = FileEntry(
            path=str(src), name="junk.tmp", extension=".tmp",
            size_bytes=5, modified_at="2024-01-01", age_days=999,
            matched_rule="test", action="cleanup",
        )

        result = execute_cleanup([entry], str(quarantine), safelist=sl)
        assert result.success_count == 1
