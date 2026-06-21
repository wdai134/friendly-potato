"""文件扫描器 — 递归扫描目录，按规则匹配文件，输出候选清理列表。

只做两件事：
1. 收集文件元数据（不读文件内容，安全边界）
2. 按 rules.yaml 规则匹配，打上 action 标签

输出交给 classifier（AI 分类器）处理 review 类型的文件。
"""

import fnmatch
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FileEntry:
    """单个文件的扫描结果。只含元数据，不含内容。"""

    path: str
    name: str
    extension: str
    size_bytes: int
    modified_at: str
    age_days: int
    matched_rule: str
    action: str  # cleanup / review / keep


@dataclass
class ScanResult:
    """一次扫描的完整结果。"""

    scan_dir: str
    scan_time: str
    total_files: int
    entries: list[FileEntry] = field(default_factory=list)

    @property
    def cleanup_candidates(self) -> list[FileEntry]:
        return [e for e in self.entries if e.action == "cleanup"]

    @property
    def review_candidates(self) -> list[FileEntry]:
        return [e for e in self.entries if e.action == "review"]

    @property
    def kept_files(self) -> list[FileEntry]:
        return [e for e in self.entries if e.action == "keep"]

    @property
    def total_size_bytes(self) -> int:
        return sum(e.size_bytes for e in self.entries)

    def to_summary(self) -> dict:
        """生成结构化扫描摘要，供深析联动做自然语言解释。

        V2 场景：深析读取此摘要，向用户说"扫描了 500 个文件，
        其中图片占 60%，有 30 个超过 90 天没动过的 PDF 建议清理"。
        """
        action_counts = {"cleanup": 0, "review": 0, "keep": 0}
        for e in self.entries:
            action_counts[e.action] = action_counts.get(e.action, 0) + 1

        ext_counts: dict[str, int] = {}
        ext_sizes: dict[str, int] = {}
        for e in self.entries:
            ext = e.extension or "(无)"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            ext_sizes[ext] = ext_sizes.get(ext, 0) + e.size_bytes

        size_buckets = {"<1KB": 0, "1KB-1MB": 0, "1MB-10MB": 0, "10MB-100MB": 0, ">100MB": 0}
        for e in self.entries:
            kb = e.size_bytes / 1024
            if kb < 1:
                size_buckets["<1KB"] += 1
            elif kb < 1024:
                size_buckets["1KB-1MB"] += 1
            elif kb < 10240:
                size_buckets["1MB-10MB"] += 1
            elif kb < 102400:
                size_buckets["10MB-100MB"] += 1
            else:
                size_buckets[">100MB"] += 1

        age_buckets = {"<7天": 0, "7-30天": 0, "30-90天": 0, "90-365天": 0, ">365天": 0}
        for e in self.entries:
            d = e.age_days
            if d < 7:
                age_buckets["<7天"] += 1
            elif d < 30:
                age_buckets["7-30天"] += 1
            elif d < 90:
                age_buckets["30-90天"] += 1
            elif d < 365:
                age_buckets["90-365天"] += 1
            else:
                age_buckets[">365天"] += 1

        cleanup_top = sorted(
            self.cleanup_candidates,
            key=lambda e: e.size_bytes,
            reverse=True,
        )[:10]

        return {
            "scan_dir": self.scan_dir,
            "scan_time": self.scan_time,
            "total_files": self.total_files,
            "total_size_bytes": self.total_size_bytes,
            "action_breakdown": action_counts,
            "extensions": {
                "counts": dict(sorted(ext_counts.items(), key=lambda x: -x[1])),
                "sizes": dict(sorted(ext_sizes.items(), key=lambda x: -x[1])),
            },
            "size_distribution": size_buckets,
            "age_distribution": age_buckets,
            "top_cleanup_by_size": [
                {
                    "name": e.name,
                    "path": e.path,
                    "size_bytes": e.size_bytes,
                    "age_days": e.age_days,
                    "extension": e.extension,
                }
                for e in cleanup_top
            ],
        }


class FileScanner:
    """文件扫描器。

    使用方式：
        scanner = FileScanner.from_config("config/rules.yaml")
        result = scanner.scan("/path/to/scan")
    """

    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self._rules = rules

    @classmethod
    def from_config(cls, config_path: str) -> "FileScanner":
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls(config["rules"])

    def scan(self, root_dir: str) -> ScanResult:
        root = Path(root_dir).resolve()
        if not root.exists():
            raise FileNotFoundError(f"扫描目录不存在: {root_dir}")

        result = ScanResult(
            scan_dir=str(root),
            scan_time=datetime.now().isoformat(),
            total_files=0,
        )

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            result.total_files += 1
            entry = self._classify_file(file_path)
            if entry is not None:
                result.entries.append(entry)

        return result

    def _classify_file(self, file_path: Path) -> FileEntry | None:
        stat = file_path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        age_days = (datetime.now() - mtime).days

        entry = FileEntry(
            path=str(file_path),
            name=file_path.name,
            extension=file_path.suffix.lower(),
            size_bytes=stat.st_size,
            modified_at=mtime.isoformat(),
            age_days=age_days,
            matched_rule="无匹配规则",
            action="review",
        )

        for rule in self._rules:
            if self._match_rule(entry, rule):
                entry.matched_rule = rule["name"]
                max_age = rule.get("max_age_days", 9999)
                if entry.age_days > max_age:
                    entry.action = rule["action"]
                else:
                    entry.action = "keep"
                return entry

        return entry

    @staticmethod
    def _match_rule(entry: FileEntry, rule: dict[str, Any]) -> bool:
        for pattern in rule.get("patterns", []):
            if fnmatch.fnmatch(entry.name, pattern):
                return True
            if fnmatch.fnmatch(entry.path, f"*{pattern}"):
                return True
            if pattern.startswith("*.") and entry.extension == pattern[1:]:
                return True
        return False
