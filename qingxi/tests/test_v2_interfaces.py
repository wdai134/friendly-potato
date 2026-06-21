"""测试 V2 预留接口 — safelist 动态管理 + scanner 摘要 + audit 审计。"""

import json

import pytest

from agent.safelist import SafeList, SafeListEntry, GREEN, RED, YELLOW
from agent.scanner import ScanResult


# ════════════════════════════════════════════════════════════════
# safelist 动态管理 API
# ════════════════════════════════════════════════════════════════

class TestSafeListDynamicAPI:
    def test_add_new_rule(self):
        sl = SafeList.empty()
        sl.add("*.exe", RED, "可执行文件")
        assert len(sl) == 1
        assert sl.check("app.exe") == RED

    def test_add_replace_duplicate(self):
        sl = SafeList.empty()
        sl.add("*.pdf", YELLOW, "PDF确认")
        sl.add("*.pdf", GREEN, "PDF改为保护")
        assert len(sl) == 1
        assert sl.check("doc.pdf") == GREEN

    def test_remove_existing(self):
        sl = SafeList([SafeListEntry("*.exe", RED, "")])
        assert sl.remove("*.exe") is True
        assert len(sl) == 0

    def test_remove_nonexistent(self):
        sl = SafeList([SafeListEntry("*.exe", RED, "")])
        assert sl.remove("*.dll") is False

    def test_save_and_reload(self, tmp_path):
        config = tmp_path / "safelist.yaml"
        sl = SafeList.empty()
        sl.add("*.exe", RED, "可执行").add("*.psd", GREEN, "源文件")
        sl.save(str(config))
        assert config.exists()

        sl2 = SafeList.from_config(str(config))
        assert len(sl2) == 2
        assert sl2.check("app.exe") == RED
        assert sl2.check("logo.psd") == GREEN

    def test_get_entries(self):
        sl = SafeList([
            SafeListEntry("*.exe", RED, "a"),
            SafeListEntry("*.psd", GREEN, "b"),
        ])
        entries = sl.get_entries()
        assert len(entries) == 2

    def test_chaining_add(self):
        sl = SafeList.empty()
        sl.add("*.exe", RED).add("*.psd", GREEN).add("*.pdf", YELLOW)
        assert len(sl) == 3

    def test_add_then_check_priority(self):
        sl = SafeList.empty()
        sl.add("*.exe", RED, "")
        sl.add("*.psd", GREEN, "")
        assert sl.check("C:/system/app.exe") == RED


# ════════════════════════════════════════════════════════════════
# scanner.to_summary()
# ════════════════════════════════════════════════════════════════

class TestScanResultSummary:
    def test_empty_result(self):
        r = ScanResult("/tmp", "2026-06-03", 0)
        s = r.to_summary()
        assert s["total_files"] == 0
        assert s["total_size_bytes"] == 0
        assert s["action_breakdown"] == {"cleanup": 0, "review": 0, "keep": 0}

    def test_with_files(self):
        from agent.scanner import FileEntry
        entries = [
            FileEntry("a.tmp", "a.tmp", ".tmp", 500, "", 999, "", "cleanup"),
            FileEntry("b.psd", "b.psd", ".psd", 2_000_000, "", 10, "", "keep"),
            FileEntry("c.pdf", "c.pdf", ".pdf", 500_000, "", 200, "", "review"),
        ]
        r = ScanResult("/tmp", "", 3, entries)
        s = r.to_summary()

        assert s["total_files"] == 3
        assert s["total_size_bytes"] == 2_500_500
        assert s["action_breakdown"]["cleanup"] == 1
        assert s["action_breakdown"]["keep"] == 1
        assert s["extensions"]["counts"][".tmp"] == 1
        assert s["size_distribution"]["<1KB"] == 1
        assert s["size_distribution"]["1MB-10MB"] == 1
        assert s["age_distribution"]["7-30天"] == 1
        assert s["age_distribution"][">365天"] == 1
        assert len(s["top_cleanup_by_size"]) == 1

    def test_json_serializable(self):
        r = ScanResult("/tmp", "2026-06-03", 0)
        s = r.to_summary()
        json.dumps(s, ensure_ascii=False)  # 不抛异常即通过

    def test_total_size_bytes_property(self):
        from agent.scanner import FileEntry
        entries = [
            FileEntry("a", "a", "", 100, "", 0, "", "keep"),
            FileEntry("b", "b", "", 200, "", 0, "", "cleanup"),
        ]
        r = ScanResult("/tmp", "", 2, entries)
        assert r.total_size_bytes == 300


# ════════════════════════════════════════════════════════════════
# audit 审计查询
# ════════════════════════════════════════════════════════════════

class TestAuditParseLine:
    def test_moved(self):
        from agent.audit import AuditTrail
        e = AuditTrail._parse_line(
            "2026-06-03 15:22:15 [INFO] 已移动: C:\\a.txt → D:\\q\\a.txt"
        )
        assert e is not None and e.operation == "moved"

    def test_blocked(self):
        from agent.audit import AuditTrail
        e = AuditTrail._parse_line(
            "2026-06-03 15:22:15 [WARNING] 🔴 白名单封锁，跳过: C:\\sys.exe"
        )
        assert e is not None and e.operation == "blocked"

    def test_restored(self):
        from agent.audit import AuditTrail
        e = AuditTrail._parse_line(
            "2026-06-03 15:22:15 [INFO] 已恢复: D:\\q\\a.txt → C:\\a.txt"
        )
        assert e is not None and e.operation == "restored"

    def test_error(self):
        from agent.audit import AuditTrail
        e = AuditTrail._parse_line(
            "2026-06-03 15:22:15 [ERROR] 移动失败: Permission denied"
        )
        assert e is not None and e.operation == "error"

    def test_non_operation_line(self):
        from agent.audit import AuditTrail
        assert AuditTrail._parse_line(
            "2026-06-03 15:22:15 [INFO] 扫描完成: 100 个文件"
        ) is None


class TestAuditTrail:
    def test_empty_log_dir(self, tmp_path):
        from agent.audit import AuditTrail
        audit = AuditTrail(str(tmp_path))
        assert audit.recent(days=7) == []
        assert audit.last_run_summary() is None

    def test_recent_with_logs(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "cleanup_test.log").write_text(
            "2026-06-03 15:22:16 [INFO] 已移动: C:\\junk.tmp → D:\\q\\junk.tmp\n"
            "2026-06-03 15:22:18 [WARNING] 🔴 白名单封锁，跳过: C:\\setup.exe\n"
            "2026-06-03 15:22:19 [INFO] 清理完成: 成功 1, 跳过 0, 封锁 1, 失败 0\n",
            encoding="utf-8",
        )
        from agent.audit import AuditTrail
        audit = AuditTrail(str(log_dir))
        recent = audit.recent(days=1)
        assert sum(1 for e in recent if e.operation == "moved") == 1
        assert sum(1 for e in recent if e.operation == "blocked") == 1

    def test_summarize(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "cleanup_test.log").write_text(
            "2026-06-03 15:22:16 [INFO] 已移动: C:\\a → D:\\q\\a\n"
            "2026-06-03 15:22:18 [WARNING] 🔴 白名单封锁，跳过: C:\\x.exe\n"
            "2026-06-03 15:22:19 [INFO] 清理完成: 成功 1, 跳过 0, 封锁 1, 失败 0\n",
            encoding="utf-8",
        )
        from agent.audit import AuditTrail
        audit = AuditTrail(str(log_dir))
        s = audit.summarize(days=1)
        assert s.total_moved == 1
        assert s.total_blocked == 1

    def test_last_run_summary(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "cleanup_test.log").write_text(
            "2026-06-03 15:22:19 [INFO] 清理完成: 成功 5, 跳过 2, 封锁 1, 失败 0\n",
            encoding="utf-8",
        )
        from agent.audit import AuditTrail
        audit = AuditTrail(str(log_dir))
        last = audit.last_run_summary()
        assert last is not None
        assert last["success"] == 5
        assert last["blocked"] == 1
