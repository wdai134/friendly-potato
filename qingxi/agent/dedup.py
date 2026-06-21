"""重复文件检测器 — 按内容哈希查找目录中的重复文件。

检测流程：
  1. 递归扫描目录，收集所有文件
  2. 按文件大小分组（快速过滤：大小不同一定不是重复）
  3. 对同大小组计算 SHA-256 哈希（流式读取，支持大文件）
  4. 同哈希文件即为重复组

安全原则：
  - 只读文件内容计算哈希，不做任何文件操作
  - 输出是检测报告，交给用户决定如何处理
  - 与现有 scanner → classifier → executor 管道解耦
"""

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("file-cleaner.dedup")


# 流式哈希缓冲区大小：64KB
_HASH_CHUNK = 64 * 1024


@dataclass
class DuplicateGroup:
    """一组重复文件。

    primary: 建议保留的文件（按策略选出）
    duplicates: 重复的文件列表（不含 primary）
    hash_value: 这组文件的 SHA-256 哈希
    wasted_bytes: 重复文件占用的额外空间（不含 primary）
    """

    hash_value: str
    primary: str
    duplicates: list[str]
    wasted_bytes: int = 0


@dataclass
class DedupResult:
    """一次重复文件扫描的完整结果。"""

    scan_dir: str
    total_files: int
    total_size_bytes: int
    groups: list[DuplicateGroup] = field(default_factory=list)

    @property
    def duplicate_count(self) -> int:
        """重复文件总数（不含 primary）。"""
        return sum(len(g.duplicates) for g in self.groups)

    @property
    def wasted_bytes(self) -> int:
        """可释放空间总量。"""
        return sum(g.wasted_bytes for g in self.groups)

    @property
    def group_count(self) -> int:
        return len(self.groups)


class DedupFinder:
    """查找目录中的重复文件。

    使用方式：
        finder = DedupFinder()
        result = finder.find_duplicates("/path/to/scan")

    group_by="content"  按内容哈希（默认，唯一可靠方式）
    min_size=1          跳过小于此大小的文件（字节）
    """

    def __init__(self, min_size: int = 1) -> None:
        self._min_size = min_size

    # ── 主入口 ────────────────────────────────────────────────

    def find_duplicates(self, root_dir: str) -> DedupResult:
        """扫描目录，返回按内容哈希分组的重复文件。"""
        root = Path(root_dir).resolve()
        if not root.exists():
            raise FileNotFoundError(f"扫描目录不存在: {root_dir}")

        # 1. 收集文件，按大小分组
        size_map: dict[int, list[str]] = {}
        total_files = 0
        total_size = 0

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                fsize = file_path.stat().st_size
            except OSError:
                continue

            if fsize < self._min_size:
                continue

            total_files += 1
            total_size += fsize
            size_map.setdefault(fsize, []).append(str(file_path))

        # 2. 对同大小组（≥2 个文件）计算内容哈希
        result = DedupResult(
            scan_dir=str(root),
            total_files=total_files,
            total_size_bytes=total_size,
        )

        for fsize, paths in size_map.items():
            if len(paths) < 2:
                continue  # 单文件不可能是重复

            hash_map: dict[str, list[str]] = {}
            for p in paths:
                try:
                    fhash = self._hash_file(p)
                except OSError as e:
                    logger.warning("无法读取文件 %s: %s", p, e)
                    continue
                hash_map.setdefault(fhash, []).append(p)

            # 3. 同哈希 = 重复组，选出 primary
            for fhash, dup_paths in hash_map.items():
                if len(dup_paths) < 2:
                    continue

                primary = self._pick_primary(dup_paths)
                duplicates = [p for p in dup_paths if p != primary]
                wasted = len(duplicates) * fsize

                result.groups.append(DuplicateGroup(
                    hash_value=fhash,
                    primary=primary,
                    duplicates=duplicates,
                    wasted_bytes=wasted,
                ))

        # 按浪费空间降序排列
        result.groups.sort(key=lambda g: g.wasted_bytes, reverse=True)
        return result

    # ── 哈希计算 ──────────────────────────────────────────────

    @staticmethod
    def _hash_file(file_path: str) -> str:
        """计算文件的 SHA-256 哈希（流式读取，安全处理大文件）。"""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(_HASH_CHUNK)
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()

    # ── primary 选择策略 ──────────────────────────────────────

    @staticmethod
    def _pick_primary(paths: list[str]) -> str:
        """从一组重复文件中选出建议保留的那个。

        策略（按优先级）：
          1. 路径最短的（通常在最外层，最有可能是"正本"）
          2. 路径相同时，文件名最短的
          3. 都不行就取第一个
        """
        return min(paths, key=lambda p: (len(p), len(Path(p).name)))


# ── 便捷函数 ──────────────────────────────────────────────────


def format_dedup_report(result: DedupResult) -> str:
    """将 DedupResult 渲染为可读的文本报告。"""
    lines = [
        "=" * 60,
        "         重复文件检测报告",
        "=" * 60,
        f"扫描目录: {result.scan_dir}",
        f"文件总数: {result.total_files}",
        f"总大小:   {_format_size(result.total_size_bytes)}",
        f"重复组数: {result.group_count}",
        f"重复文件: {result.duplicate_count} 个",
        f"可释放:   {_format_size(result.wasted_bytes)}",
        "",
    ]

    if not result.groups:
        lines.append("  未发现重复文件。")
        return "\n".join(lines)

    for i, group in enumerate(result.groups, 1):
        lines.append(f"[重复组 {i}]  {_format_size(group.wasted_bytes)} 可释放")
        lines.append(f"  哈希: {group.hash_value[:16]}...")
        lines.append(f"  [保留] {group.primary}")
        for dup in group.duplicates:
            lines.append(f"  [重复] {dup}")
        lines.append("")

    return "\n".join(lines)


def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ── 关联文件 ──────────────────────────────────────────────────
# [[agent/scanner.py]] — 文件扫描，dedup 是独立检测通道
# [[agent/executor.py]] — 清理执行，dedup 结果可喂入 executor
# [[agent/reporter.py]] — 报告生成，format_dedup_report 是 dedup 自己的报告
# [[main.py]] — CLI 入口，会集成 --dedup 子命令
