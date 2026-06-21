"""操作审计 — 查询历史清理记录，供深析联动做自然语言回溯。

V2 场景：用户问"上周清理了什么？"，深析调用 AuditTrail 查询，
回答"清理了 30 个临时文件，释放了 500MB，其中最大的是一年前的备份包"。

数据来源：logs/ 目录下的 cleanup_*.log 文件。
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("file-cleaner.audit")


# ── 日志解析正则 ──────────────────────────────────────────────

_RE_LOG_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "  # 时间戳
    r"\[(\w+)\] "                                    # 级别
    r"(.*)"                                           # 消息
)

_RE_MOVED = re.compile(r"已移动: (.+?) → (.+)")
_RE_BLOCKED = re.compile(r"🔴 白名单封锁，跳过: (.+)")
_RE_RESTORED = re.compile(r"已恢复: (.+?) → (.+)")
_RE_CLEANUP_DONE = re.compile(
    r"清理完成: 成功 (\d+), 跳过 (\d+), 封锁 (\d+), 失败 (\d+)"
)


@dataclass
class AuditEntry:
    """一条操作审计记录。"""
    timestamp: str
    operation: str        # "moved" | "blocked" | "restored" | "error"
    source: str
    destination: str = ""
    detail: str = ""


@dataclass
class AuditSummary:
    """一段时间内的操作摘要。"""
    period_start: str
    period_end: str
    total_moved: int
    total_blocked: int
    total_restored: int
    total_errors: int
    entries: list[AuditEntry] = field(default_factory=list)


class AuditTrail:
    """查询历史操作记录。

    使用方式：
        audit = AuditTrail("logs/")
        recent = audit.recent(days=7)         # 最近 7 天
        summary = audit.summarize(days=30)     # 30 天摘要
        last = audit.last_run_summary()        # 最近一次清理统计
    """

    def __init__(self, log_dir: str = "logs") -> None:
        self._log_dir = Path(log_dir)

    def _iter_log_files(self) -> list[Path]:
        """按文件名降序的日志文件列表。"""
        if not self._log_dir.exists():
            return []
        return sorted(
            self._log_dir.glob("cleanup_*.log"),
            key=lambda p: p.name,
            reverse=True,
        )

    def _parse_log(self, file_path: Path) -> list[AuditEntry]:
        """解析单个日志文件，提取操作记录。"""
        entries: list[AuditEntry] = []
        try:
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    entry = self._parse_line(line)
                    if entry:
                        entries.append(entry)
        except OSError:
            pass
        return entries

    @staticmethod
    def _parse_line(line: str) -> Optional[AuditEntry]:
        """解析单行日志为 AuditEntry。"""
        m = _RE_LOG_LINE.match(line.strip())
        if not m:
            return None

        ts, level, msg = m.group(1), m.group(2), m.group(3)

        mm = _RE_MOVED.match(msg)
        if mm:
            return AuditEntry(
                timestamp=ts, operation="moved",
                source=mm.group(1).strip(),
                destination=mm.group(2).strip(),
            )

        bm = _RE_BLOCKED.match(msg)
        if bm:
            return AuditEntry(
                timestamp=ts, operation="blocked",
                source=bm.group(1).strip(),
                detail="白名单封锁",
            )

        rm = _RE_RESTORED.match(msg)
        if rm:
            return AuditEntry(
                timestamp=ts, operation="restored",
                source=rm.group(1).strip(),
                destination=rm.group(2).strip(),
            )

        if level == "ERROR":
            return AuditEntry(
                timestamp=ts, operation="error",
                source="", detail=msg,
            )

        return None

    # ── 查询接口 ──────────────────────────────────────────────

    def recent(self, days: int = 7) -> list[AuditEntry]:
        """查询最近 N 天的操作记录。"""
        cutoff = datetime.now() - timedelta(days=days)
        results: list[AuditEntry] = []

        for log_file in self._iter_log_files():
            for e in self._parse_log(log_file):
                try:
                    ts = datetime.strptime(e.timestamp, "%Y-%m-%d %H:%M:%S")
                    if ts >= cutoff:
                        results.append(e)
                except ValueError:
                    continue

        return results

    def summarize(self, days: int = 30) -> AuditSummary:
        """生成一段时间内的操作摘要。

        V2 场景：深析调用此方法，向用户说"这个月清理了
        200 个文件，拦截了 3 个系统文件，没有出错"。
        """
        entries = self.recent(days)
        now = datetime.now()
        return AuditSummary(
            period_start=(now - timedelta(days=days)).strftime("%Y-%m-%d"),
            period_end=now.strftime("%Y-%m-%d"),
            total_moved=sum(1 for e in entries if e.operation == "moved"),
            total_blocked=sum(1 for e in entries if e.operation == "blocked"),
            total_restored=sum(1 for e in entries if e.operation == "restored"),
            total_errors=sum(1 for e in entries if e.operation == "error"),
            entries=entries,
        )

    def last_run_summary(self) -> Optional[dict]:
        """返回最近一次清理的统计信息。"""
        for log_file in self._iter_log_files():
            try:
                with open(log_file, encoding="utf-8") as f:
                    content = f.read()
            except OSError:
                continue

            m = _RE_CLEANUP_DONE.search(content)
            if m:
                return {
                    "success": int(m.group(1)),
                    "skipped": int(m.group(2)),
                    "blocked": int(m.group(3)),
                    "errors": int(m.group(4)),
                    "log_file": log_file.name,
                }
        return None


# ── 关联文件 ──────────────────────────────────────────────────
# [[agent/logger.py]] — 日志写入端，audit 是读取端
# [[agent/executor.py]] — 产生 moved/blocked 日志
# [[agent/restorer.py]] — 产生 restored 日志
# V2 预留：深析调用 AuditTrail 实现自然语言回溯
