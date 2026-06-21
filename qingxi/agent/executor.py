"""清理执行器 — 在人工确认后执行文件清理。

安全机制：
1. 软删除：文件移至隔离区，不永久删除
2. 同名冲突：自动加时间戳后缀
3. 完整日志：每次操作都有记录
4. 白名单拦截：支持 SafeList，🔴 文件拒绝移动
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from agent.scanner import FileEntry

if TYPE_CHECKING:
    from agent.safelist import SafeList

logger = logging.getLogger("file-cleaner")


class ExecutionResult:
    """一次清理执行的结果。"""

    def __init__(self) -> None:
        self.moved: list[str] = []
        self.skipped: list[str] = []
        self.blocked: list[str] = []   # 被白名单拦截的 🔴 文件
        self.errors: list[tuple[str, str]] = []

    @property
    def success_count(self) -> int:
        return len(self.moved)


def execute_cleanup(
    entries: list[FileEntry],
    quarantine_dir: str,
    dry_run: bool = False,
    safelist: "SafeList | None" = None,
) -> ExecutionResult:
    """执行文件清理，将文件移至隔离区。

    Args:
        entries: 待清理的文件列表
        quarantine_dir: 隔离区目录
        dry_run: True 时只模拟，不实际移动
        safelist: 可选白名单，🔴文件将被拦截跳过

    Returns:
        ExecutionResult 包含执行统计
    """
    result = ExecutionResult()
    quarantine = Path(quarantine_dir)
    quarantine.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        source = Path(entry.path)

        # ── 白名单拦截 ──────────────────────────────────────
        if safelist and safelist:
            tier = safelist.check(str(source))
            if tier == "red":
                msg = f"🔴 白名单封锁，跳过: {source}"
                logger.warning(msg)
                result.blocked.append(str(source))
                continue
            elif tier == "green":
                logger.info("🟢 白名单保护，跳过: %s", source)
                result.skipped.append(str(source))
                continue

        if not source.exists():
            msg = f"文件不存在: {source}"
            logger.warning(msg)
            result.skipped.append(str(source))
            continue

        # 保留原始目录结构以避免同名冲突
        relative = str(source).replace(":", "").replace("\\", "/").lstrip("/")
        dest = quarantine / relative
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            stem = dest.stem
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = dest.parent / f"{stem}_{ts}{dest.suffix}"

        if dry_run:
            logger.info("[DRY RUN] 将移动: %s → %s", source, dest)
            result.moved.append(str(source))
        else:
            try:
                shutil.move(str(source), str(dest))
                logger.info("已移动: %s → %s", source, dest)
                result.moved.append(str(source))
            except OSError as e:
                msg = f"移动失败: {e}"
                logger.error("移动失败: %s — %s", source, e)
                result.errors.append((str(source), msg))

    logger.info(
        "清理完成: 成功 %d, 跳过 %d, 封锁 %d, 失败 %d",
        result.success_count,
        len(result.skipped),
        len(result.blocked),
        len(result.errors),
    )
    return result
