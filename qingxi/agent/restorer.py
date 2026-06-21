"""文件恢复器 — 从隔离区（quarantine）恢复已清理的文件到原始位置。

路径映射：
  清理时：C:/Users/.../foo.txt → quarantine/C/Users/.../foo.txt
  恢复时：逆向操作，还原盘符和路径分隔符

安全机制：
  1. 目标路径已存在同名文件时，自动加 _restored 后缀
  2. 支持 dry-run 预览
  3. 支持恢复到指定目录（不恢复到原始位置）
"""

import fnmatch
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("file-cleaner.restore")


# 匹配 executor 加的时间戳后缀: foo_20260603_151030.txt → foo.txt
_TIMESTAMP_SUFFIX = re.compile(r"^(.+)_(\d{8}_\d{6})(\.[^.]+)?$")


@dataclass
class QuarantineEntry:
    """隔离区中单个文件的描述。"""

    quarantine_path: str      # 文件在隔离区中的完整路径
    original_path: str        # 推断的原始路径
    original_name: str        # 推断的原始文件名（去除时间戳）
    size_bytes: int
    has_timestamp: bool = False  # 文件名是否含时间戳后缀


@dataclass
class RestoreResult:
    """一次恢复操作的结果。"""

    restored: list[str] = field(default_factory=list)    # 成功恢复的文件路径
    skipped: list[str] = field(default_factory=list)     # 跳过的文件
    errors: list[tuple[str, str]] = field(default_factory=list)  # (文件, 错误信息)

    @property
    def success_count(self) -> int:
        return len(self.restored)

    @property
    def total(self) -> int:
        return self.success_count + len(self.skipped) + len(self.errors)


class Restorer:
    """从隔离区恢复已清理的文件。

    使用方式：
        restorer = Restorer("./quarantine")
        entries = restorer.list_quarantined()
        result = restorer.restore(entries, dry_run=False)
    """

    def __init__(self, quarantine_dir: str) -> None:
        self._quarantine = Path(quarantine_dir)
        if not self._quarantine.exists():
            raise FileNotFoundError(f"隔离区不存在: {quarantine_dir}")

    # ── 路径逆向 ──────────────────────────────────────────────

    @staticmethod
    def reverse_path(quarantine_path: str, quarantine_root: str) -> str:
        """从隔离区路径逆向推算原始文件路径。

        清理时的变换规则（见 executor.py）：
            relative = str(source).replace(":", "").replace("\\", "/").lstrip("/")
            dest = quarantine / relative

        逆向规则：
            隔离区路径 = quarantine/C/Users/.../foo.txt
            → 原始路径 = C:\\Users\\...\\foo.txt
        """
        qp = Path(quarantine_path)
        qr = Path(quarantine_root)
        relative = str(qp.relative_to(qr)).replace("\\", "/")

        parts = relative.split("/", 1)
        if len(parts) == 2 and len(parts[0]) == 1:
            # 首段是单字母（盘符），还原为 C:\
            drive = parts[0].upper()
            rest = parts[1]
            return str(Path(f"{drive}:\\{rest}"))
        else:
            # 非标准格式，回退到原路径
            return str(Path(quarantine_path))

    @staticmethod
    def strip_timestamp(name: str) -> tuple[str, bool]:
        """尝试去除文件名中的时间戳后缀。

        匹配 executor 为同名文件添加的时间戳格式：name_YYYYMMDD_HHMMSS.ext
        返回 (清理后的文件名, 是否有时间戳)。
        """
        m = _TIMESTAMP_SUFFIX.match(name)
        if m:
            stem = m.group(1)
            ext = m.group(3) or ""
            return f"{stem}{ext}", True
        return name, False

    # ── 扫描隔离区 ────────────────────────────────────────────

    def list_quarantined(self) -> list[QuarantineEntry]:
        """列出隔离区中所有文件及其原始路径。"""
        entries: list[QuarantineEntry] = []

        for file_path in self._quarantine.rglob("*"):
            if not file_path.is_file():
                continue

            full_path = str(file_path)
            original_full = self.reverse_path(full_path, str(self._quarantine))

            orig_name, has_ts = self.strip_timestamp(file_path.name)

            # 重建去时间戳后的原始完整路径
            if has_ts:
                orig_path = str(Path(original_full).parent / orig_name)
            else:
                orig_path = original_full

            entries.append(QuarantineEntry(
                quarantine_path=full_path,
                original_path=orig_path,
                original_name=orig_name,
                size_bytes=file_path.stat().st_size,
                has_timestamp=has_ts,
            ))

        return entries

    # ── 恢复文件 ──────────────────────────────────────────────

    def restore(
        self,
        entries: list[QuarantineEntry],
        target_dir: Optional[str] = None,
        dry_run: bool = False,
    ) -> RestoreResult:
        """将隔离区文件恢复到原始位置或指定目录。

        Args:
            entries: 待恢复的文件列表（来自 list_quarantined）
            target_dir: 恢复到指定目录（None = 恢复到原始路径）
            dry_run: True 时只模拟，不实际移动

        Returns:
            RestoreResult 包含恢复统计
        """
        result = RestoreResult()

        for entry in entries:
            source = Path(entry.quarantine_path)
            if not source.exists():
                msg = f"文件已在隔离区消失: {source}"
                logger.warning(msg)
                result.skipped.append(entry.original_path)
                continue

            if target_dir:
                dest = Path(target_dir) / entry.original_name
            else:
                dest = Path(entry.original_path)

            dest = self._resolve_conflict(dest)

            if dry_run:
                logger.info("[DRY RUN] 将恢复: %s → %s", source, dest)
                result.restored.append(str(dest))
            else:
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(dest))
                    logger.info("已恢复: %s → %s", source, dest)
                    result.restored.append(str(dest))
                except OSError as e:
                    msg = f"恢复失败: {e}"
                    logger.error("%s — %s", source, e)
                    result.errors.append((entry.original_path, msg))

        logger.info(
            "恢复完成: 成功 %d, 跳过 %d, 失败 %d",
            result.success_count,
            len(result.skipped),
            len(result.errors),
        )
        return result

    def restore_all(
        self, target_dir: Optional[str] = None, dry_run: bool = False
    ) -> RestoreResult:
        """恢复隔离区中所有文件。"""
        entries = self.list_quarantined()
        return self.restore(entries, target_dir, dry_run)

    def restore_by_pattern(
        self,
        pattern: str,
        target_dir: Optional[str] = None,
        dry_run: bool = False,
    ) -> RestoreResult:
        """按文件名模式恢复文件（支持通配符 fnmatch）。"""
        entries = self.list_quarantined()
        matched = [
            e for e in entries
            if fnmatch.fnmatch(e.original_name, pattern)
            or fnmatch.fnmatch(Path(e.quarantine_path).name, pattern)
        ]
        return self.restore(matched, target_dir, dry_run)

    # ── 冲突处理 ──────────────────────────────────────────────

    @staticmethod
    def _resolve_conflict(dest: Path) -> Path:
        """如果目标路径已存在，添加 _restored 后缀避免覆盖。"""
        if not dest.exists():
            return dest

        stem = dest.stem
        ext = dest.suffix
        counter = 1
        while True:
            new_dest = dest.parent / f"{stem}_restored{counter}{ext}"
            if not new_dest.exists():
                logger.info("目标已存在，使用替代名: %s", new_dest)
                return new_dest
            counter += 1


# ── 关联文件 ──────────────────────────────────────────────────
# [[agent/executor.py]] — 文件移动到此，restorer 负责逆向
# [[main.py]] — CLI 入口，会集成 --restore 子命令
