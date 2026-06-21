"""测试 agent/restorer.py — 文件恢复模块。"""

import shutil
from pathlib import Path

import pytest

from agent.restorer import QuarantineEntry, RestoreResult, Restorer


# ════════════════════════════════════════════════════════════════
# 路径逆向
# ════════════════════════════════════════════════════════════════

class TestReversePath:
    def test_windows_path_with_drive_letter(self):
        result = Restorer.reverse_path(
            "quarantine/C/Users/john/file.txt",
            "quarantine",
        )
        assert result == str(Path("C:\\Users\\john\\file.txt"))

    def test_deeply_nested_path(self):
        result = Restorer.reverse_path(
            "quarantine/D/projects/data/sub/deep/file.log",
            "quarantine",
        )
        assert result == str(Path("D:\\projects\\data\\sub\\deep\\file.log"))

    def test_non_standard_no_drive_letter(self):
        result = Restorer.reverse_path(
            "quarantine/home/user/docs/report.pdf",
            "quarantine",
        )
        # 首段不是单字母，回退到原路径
        assert "quarantine" in result


class TestStripTimestamp:
    def test_with_timestamp(self):
        name, has_ts = Restorer.strip_timestamp("report_20260603_151030.pdf")
        assert name == "report.pdf"
        assert has_ts is True

    def test_without_timestamp(self):
        name, has_ts = Restorer.strip_timestamp("normal_file.txt")
        assert name == "normal_file.txt"
        assert has_ts is False

    def test_no_extension(self):
        name, has_ts = Restorer.strip_timestamp("backup_20251225_000000")
        assert name == "backup"
        assert has_ts is True

    def test_only_underscore_number_not_timestamp(self):
        name, has_ts = Restorer.strip_timestamp("file_123.txt")
        assert name == "file_123.txt"
        assert has_ts is False


# ════════════════════════════════════════════════════════════════
# 隔离区扫描
# ════════════════════════════════════════════════════════════════

class TestListQuarantined:
    def test_empty_quarantine(self, tmp_path):
        quarantine = tmp_path / "empty_quarantine"
        quarantine.mkdir()
        restorer = Restorer(str(quarantine))
        assert restorer.list_quarantined() == []

    def test_single_file(self, tmp_path):
        quarantine = tmp_path / "q"
        quarantine.mkdir()
        (quarantine / "C" / "Users" / "test").mkdir(parents=True)
        (quarantine / "C" / "Users" / "test" / "doc.txt").write_text("hello")

        restorer = Restorer(str(quarantine))
        entries = restorer.list_quarantined()

        assert len(entries) == 1
        assert entries[0].original_name == "doc.txt"
        assert entries[0].has_timestamp is False
        assert "C:\\Users\\test\\doc.txt" in entries[0].original_path

    def test_multiple_files(self, tmp_path):
        quarantine = tmp_path / "q"
        quarantine.mkdir()
        (quarantine / "C" / "data").mkdir(parents=True)
        (quarantine / "C" / "data" / "a.txt").write_text("a")
        (quarantine / "C" / "data" / "b.log").write_text("b")
        (quarantine / "C" / "data" / "sub").mkdir(parents=True)
        (quarantine / "C" / "data" / "sub" / "c.pdf").write_text("c")

        restorer = Restorer(str(quarantine))
        entries = restorer.list_quarantined()

        assert len(entries) == 3

    def test_file_with_timestamp(self, tmp_path):
        quarantine = tmp_path / "q"
        quarantine.mkdir()
        (quarantine / "C" / "tmp").mkdir(parents=True)
        (quarantine / "C" / "tmp" / "log_20260101_120000.txt").write_text("data")

        restorer = Restorer(str(quarantine))
        entries = restorer.list_quarantined()

        assert len(entries) == 1
        assert entries[0].has_timestamp is True
        assert entries[0].original_name == "log.txt"

    def test_quarantine_not_exists(self):
        with pytest.raises(FileNotFoundError, match="隔离区不存在"):
            Restorer("/nonexistent/path/12345")


# ════════════════════════════════════════════════════════════════
# 恢复操作
# ════════════════════════════════════════════════════════════════

class TestRestore:
    def test_dry_run_does_not_move(self, tmp_path):
        quarantine = tmp_path / "q"
        quarantine.mkdir()
        (quarantine / "C" / "tmp").mkdir(parents=True)
        src = quarantine / "C" / "tmp" / "file.txt"
        src.write_text("content")

        restorer = Restorer(str(quarantine))
        entries = restorer.list_quarantined()
        result = restorer.restore(entries, dry_run=True)

        assert result.success_count == 1
        assert src.exists()  # 文件未被移动

    def test_restore_to_original_location(self, tmp_path):
        quarantine = tmp_path / "q"
        quarantine.mkdir()
        (quarantine / "C" / "target").mkdir(parents=True)
        src = quarantine / "C" / "target" / "file.txt"
        src.write_text("restore me")

        restorer = Restorer(str(quarantine))
        entries = restorer.list_quarantined()
        result = restorer.restore(entries, dry_run=False)

        assert result.success_count == 1
        assert not src.exists()  # 已从隔离区移除

    def test_restore_to_custom_target_dir(self, tmp_path):
        quarantine = tmp_path / "q"
        quarantine.mkdir()
        (quarantine / "C" / "old").mkdir(parents=True)
        (quarantine / "C" / "old" / "data.txt").write_text("data")

        target = tmp_path / "restored"
        target.mkdir()

        restorer = Restorer(str(quarantine))
        entries = restorer.list_quarantined()
        result = restorer.restore(entries, target_dir=str(target))

        assert result.success_count == 1
        assert (target / "data.txt").exists()

    def test_conflict_adds_suffix(self, tmp_path):
        quarantine = tmp_path / "q"
        quarantine.mkdir()
        (quarantine / "C" / "place").mkdir(parents=True)
        (quarantine / "C" / "place" / "file.txt").write_text("quarantined")

        target = tmp_path / "target"
        target.mkdir()
        (target / "file.txt").write_text("existing")

        restorer = Restorer(str(quarantine))
        entries = restorer.list_quarantined()
        result = restorer.restore(entries, target_dir=str(target))
        assert result.success_count == 1
        # 应该以 _restored1 后缀恢复
        restored_files = list(target.glob("file*.txt"))
        names = {f.name for f in restored_files}
        assert "file_restored1.txt" in names or len(restored_files) >= 2

    def test_skip_missing_source(self, tmp_path):
        quarantine = tmp_path / "q"
        quarantine.mkdir()

        entry = QuarantineEntry(
            quarantine_path=str(quarantine / "gone.txt"),
            original_path="C:\\gone.txt",
            original_name="gone.txt",
            size_bytes=0,
        )
        restorer = Restorer(str(quarantine))
        result = restorer.restore([entry])

        assert result.success_count == 0
        assert len(result.skipped) == 1


class TestRestoreAll:
    def test_restore_all_files(self, tmp_path):
        quarantine = tmp_path / "q"
        quarantine.mkdir()
        (quarantine / "C" / "stuff").mkdir(parents=True)
        (quarantine / "C" / "stuff" / "a.txt").write_text("a")
        (quarantine / "C" / "stuff" / "b.txt").write_text("b")

        target = tmp_path / "out"
        target.mkdir()
        restorer = Restorer(str(quarantine))
        result = restorer.restore_all(target_dir=str(target))

        assert result.success_count == 2
        assert (target / "a.txt").exists()
        assert (target / "b.txt").exists()


class TestRestoreByPattern:
    def test_pattern_matching(self, tmp_path):
        quarantine = tmp_path / "q"
        quarantine.mkdir()
        (quarantine / "C" / "x").mkdir(parents=True)
        (quarantine / "C" / "x" / "report.pdf").write_text("r")
        (quarantine / "C" / "x" / "image.png").write_text("i")

        target = tmp_path / "out"
        target.mkdir()
        restorer = Restorer(str(quarantine))
        result = restorer.restore_by_pattern("*.pdf", target_dir=str(target))

        assert result.success_count == 1
        assert (target / "report.pdf").exists()
        assert not (target / "image.png").exists()


# ════════════════════════════════════════════════════════════════
# RestoreResult
# ════════════════════════════════════════════════════════════════

class TestRestoreResult:
    def test_empty_result(self):
        r = RestoreResult()
        assert r.success_count == 0
        assert r.total == 0

    def test_counts(self):
        r = RestoreResult(
            restored=["a", "b"],
            skipped=["c"],
            errors=[("d", "fail")],
        )
        assert r.success_count == 2
        assert r.total == 4
