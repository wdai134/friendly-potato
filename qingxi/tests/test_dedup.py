"""测试 agent/dedup.py — 重复文件检测模块。"""

from pathlib import Path

import pytest

from agent.dedup import DedupFinder, DedupResult, DuplicateGroup, format_dedup_report


# ════════════════════════════════════════════════════════════════
# 核心检测逻辑
# ════════════════════════════════════════════════════════════════

class TestFindDuplicates:
    def test_empty_directory(self, tmp_path):
        finder = DedupFinder()
        result = finder.find_duplicates(str(tmp_path))
        assert result.total_files == 0
        assert result.groups == []

    def test_no_duplicates(self, tmp_path):
        (tmp_path / "a.txt").write_text("unique A")
        (tmp_path / "b.txt").write_text("unique B")
        (tmp_path / "c.txt").write_text("unique C")

        finder = DedupFinder()
        result = finder.find_duplicates(str(tmp_path))

        assert result.total_files == 3
        assert result.group_count == 0
        assert result.duplicate_count == 0

    def test_single_duplicate_pair(self, tmp_path):
        (tmp_path / "original.txt").write_text("same content")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "copy.txt").write_text("same content")

        finder = DedupFinder()
        result = finder.find_duplicates(str(tmp_path))

        assert result.total_files == 2
        assert result.group_count == 1
        assert result.duplicate_count == 1
        # 验证 primary + duplicates 覆盖两个文件（不假设哪个是 primary）
        g = result.groups[0]
        all_files = {g.primary, *g.duplicates}
        assert all_files == {
            str(tmp_path / "original.txt"),
            str(tmp_path / "sub" / "copy.txt"),
        }

    def test_multiple_duplicate_groups(self, tmp_path):
        (tmp_path / "a1.txt").write_text("AAA")
        (tmp_path / "a2.txt").write_text("AAA")
        (tmp_path / "b1.txt").write_text("BBB")
        (tmp_path / "b2.txt").write_text("BBB")
        (tmp_path / "b3.txt").write_text("BBB")

        finder = DedupFinder()
        result = finder.find_duplicates(str(tmp_path))

        assert result.group_count == 2
        assert result.duplicate_count == 3  # 1 for A group + 2 for B group

    def test_same_name_different_content(self, tmp_path):
        (tmp_path / "file.txt").write_text("content A")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "file.txt").write_text("content B")

        finder = DedupFinder()
        result = finder.find_duplicates(str(tmp_path))

        assert result.group_count == 0  # 不同内容，不是重复

    def test_same_content_different_name(self, tmp_path):
        (tmp_path / "report.pdf").write_text("DATA")
        (tmp_path / "copy_backup.pdf").write_text("DATA")

        finder = DedupFinder()
        result = finder.find_duplicates(str(tmp_path))

        assert result.group_count == 1

    def test_empty_files_are_duplicates(self, tmp_path):
        (tmp_path / "empty1.txt").write_text("")
        (tmp_path / "empty2.txt").write_text("")

        finder = DedupFinder(min_size=0)
        result = finder.find_duplicates(str(tmp_path))

        assert result.group_count == 1

    def test_min_size_filter(self, tmp_path):
        (tmp_path / "small1.txt").write_text("x")
        (tmp_path / "small2.txt").write_text("x")
        (tmp_path / "big.txt").write_text("bigger content here")

        finder = DedupFinder(min_size=5)
        result = finder.find_duplicates(str(tmp_path))

        # small1 和 small2 小于 5 字节被跳过，只剩 big.txt 不构成重复组
        assert result.group_count == 0

    def test_large_files_streaming(self, tmp_path):
        content = "A" * 100_000  # ~100KB，测试流式读取
        (tmp_path / "large1.bin").write_text(content)
        (tmp_path / "large2.bin").write_text(content)

        finder = DedupFinder()
        result = finder.find_duplicates(str(tmp_path))

        assert result.group_count == 1
        assert result.wasted_bytes == 100_000

    def test_three_way_duplicate(self, tmp_path):
        content = "triple"
        (tmp_path / "a.txt").write_text(content)
        (tmp_path / "b.txt").write_text(content)
        (tmp_path / "c.txt").write_text(content)

        finder = DedupFinder()
        result = finder.find_duplicates(str(tmp_path))

        assert result.group_count == 1
        assert result.duplicate_count == 2  # 3 files, 1 primary, 2 dupes

    def test_scan_dir_not_exists(self):
        finder = DedupFinder()
        with pytest.raises(FileNotFoundError, match="扫描目录不存在"):
            finder.find_duplicates("/nonexistent/xyz")

    def test_nested_directories(self, tmp_path):
        (tmp_path / "level1").mkdir()
        (tmp_path / "level1" / "level2").mkdir()
        (tmp_path / "level1" / "level2" / "level3").mkdir()
        (tmp_path / "root.txt").write_text("X")
        (tmp_path / "level1" / "a.txt").write_text("X")
        (tmp_path / "level1" / "level2" / "b.txt").write_text("X")
        (tmp_path / "level1" / "level2" / "level3" / "c.txt").write_text("X")

        finder = DedupFinder()
        result = finder.find_duplicates(str(tmp_path))

        assert result.group_count == 1
        assert result.duplicate_count == 3
        assert result.groups[0].primary == str(tmp_path / "root.txt")


# ════════════════════════════════════════════════════════════════
# Primary 选择策略
# ════════════════════════════════════════════════════════════════

class TestPickPrimary:
    def test_shortest_path_wins(self):
        paths = [
            "/a/very/long/path/to/file.txt",
            "/short/file.txt",
            "/medium/path/file.txt",
        ]
        result = DedupFinder._pick_primary(paths)
        assert result == "/short/file.txt"

    def test_same_length_name_wins(self):
        paths = [
            "/x/abcdefghij.txt",
            "/x/abc.txt",
        ]
        result = DedupFinder._pick_primary(paths)
        assert result == "/x/abc.txt"


# ════════════════════════════════════════════════════════════════
# DedupResult
# ════════════════════════════════════════════════════════════════

class TestDedupResult:
    def test_empty(self):
        r = DedupResult(scan_dir="/tmp", total_files=10, total_size_bytes=100)
        assert r.group_count == 0
        assert r.duplicate_count == 0
        assert r.wasted_bytes == 0

    def test_with_groups(self):
        g = DuplicateGroup(
            hash_value="abc123",
            primary="/a.txt",
            duplicates=["/b.txt", "/c.txt"],
            wasted_bytes=200,
        )
        r = DedupResult(
            scan_dir="/tmp", total_files=5, total_size_bytes=500, groups=[g]
        )
        assert r.group_count == 1
        assert r.duplicate_count == 2
        assert r.wasted_bytes == 200


# ════════════════════════════════════════════════════════════════
# 报告格式化
# ════════════════════════════════════════════════════════════════

class TestFormatReport:
    def test_no_duplicates(self):
        r = DedupResult(scan_dir="/tmp", total_files=5, total_size_bytes=100)
        report = format_dedup_report(r)
        assert "未发现重复文件" in report

    def test_with_duplicates(self):
        g = DuplicateGroup(
            hash_value="deadbeef12345678",
            primary="/data/original.txt",
            duplicates=["/backup/copy.txt"],
            wasted_bytes=1024,
        )
        r = DedupResult(
            scan_dir="/data", total_files=2, total_size_bytes=2048, groups=[g]
        )
        report = format_dedup_report(r)
        assert "重复文件检测报告" in report
        assert "[保留]" in report
        assert "[重复]" in report
        assert "/backup/copy.txt" in report
