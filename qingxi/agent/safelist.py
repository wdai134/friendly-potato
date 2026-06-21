"""安全白名单 — 三色分级保护，与 executor 对接。

三色体系：
  🟢 green  — 白名单：明确保护，永远不清理
  🟡 yellow — 谨慎：清理前需额外人工确认
  🔴 red    — 封锁：executor 必须拒绝，绝不触碰

匹配优先级：🔴 > 🟢 > 🟡
  一个文件先查是否命中 red → 再查 green → 最后 yellow。
  未命中任何规则返回 "none"（无保护，正常清理流程）。

使用方式：
  safelist = SafeList.from_config("config/safelist.yaml")
  tier = safelist.check("C:/Users/john/doc.pdf")  # → "green" | "yellow" | "red" | "none"
"""

import fnmatch
import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger("file-cleaner.safelist")


# ── 三色常量 ──────────────────────────────────────────────────

GREEN = "green"    # 白名单 — 永远不清理
YELLOW = "yellow"  # 谨慎 — 需额外确认
RED = "red"        # 封锁 — executor 拒绝触碰
NONE = "none"      # 未命中任何规则

TIER_EMOJI = {
    GREEN: "🟢",
    YELLOW: "🟡",
    RED: "🔴",
    NONE: "⚪",
}


@dataclass
class SafeListEntry:
    """白名单中的一条规则。"""
    pattern: str
    tier: str      # green | yellow | red
    reason: str


class SafeList:
    """安全白名单管理器。

    从 YAML 配置加载规则，提供文件路径的三色分级查询。
    与 executor 对接：executor 在执行清理前调用 check()，
    如果返回 "red"，executor 必须跳过该文件。
    """

    def __init__(self, entries: list[SafeListEntry] | None = None) -> None:
        self._entries: list[SafeListEntry] = list(entries) if entries else []

    @classmethod
    def from_config(cls, config_path: str) -> "SafeList":
        """从 YAML 配置文件加载白名单。"""
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        entries = []
        for item in config.get("safelist", []):
            entries.append(SafeListEntry(
                pattern=item["pattern"],
                tier=item["tier"],
                reason=item.get("reason", ""),
            ))

        logger.info("白名单加载完成: %d 条规则", len(entries))
        return cls(entries)

    @classmethod
    def empty(cls) -> "SafeList":
        """空白名单（check() 始终返回 none）。"""
        return cls([])

    # ── 核心查询 ──────────────────────────────────────────────

    def check(self, file_path: str) -> str:
        """查询文件的三色分级。

        按优先级 RED > GREEN > YELLOW 匹配，命中即返回。
        未命中任何规则返回 "none"。
        """
        matched_tier = NONE
        matched_reason = ""

        for entry in self._entries:
            if self._match(file_path, entry.pattern):
                if entry.tier == RED:
                    logger.debug("🔴 封锁: %s → %s", file_path, entry.reason)
                    return RED
                if entry.tier == GREEN and matched_tier not in (RED,):
                    matched_tier = GREEN
                    matched_reason = entry.reason
                elif entry.tier == YELLOW and matched_tier not in (RED, GREEN):
                    matched_tier = YELLOW
                    matched_reason = entry.reason

        if matched_tier != NONE:
            logger.debug(
                "%s %s: %s → %s",
                TIER_EMOJI[matched_tier], matched_tier, file_path, matched_reason,
            )
        return matched_tier

    def is_blocked(self, file_path: str) -> bool:
        """文件是否被封锁（executor 不能碰）。"""
        return self.check(file_path) == RED

    def is_protected(self, file_path: str) -> bool:
        """文件是否在白名单保护中。"""
        return self.check(file_path) == GREEN

    def get_tier_summary(self, file_path: str) -> dict[str, str]:
        """返回文件的分级摘要（供 dashboard 显示）。"""
        tier = self.check(file_path)
        return {
            "path": file_path,
            "name": Path(file_path).name,
            "tier": tier,
            "emoji": TIER_EMOJI.get(tier, "⚪"),
        }

    # ── 匹配逻辑 ──────────────────────────────────────────────

    @staticmethod
    def _match(file_path: str, pattern: str) -> bool:
        """判断文件路径是否匹配白名单规则。

        支持：精确路径、通配符(*.exe)、递归通配符(C:/Windows/**)
        """
        normalized = file_path.replace("\\", "/")

        # 精确路径（大小写不敏感）
        if normalized.lower() == pattern.lower():
            return True

        # ** 递归通配符
        if "**" in pattern:
            parts = pattern.split("**")
            prefix, suffix = parts[0], parts[1] if len(parts) > 1 else ""
            prefix = prefix.rstrip("/")
            suffix = suffix.lstrip("/")
            prefix_match = (
                not prefix
                or normalized.startswith(prefix)
                or f"/{prefix}/" in normalized
            )
            suffix_match = (
                not suffix
                or normalized.endswith(suffix)
                or normalized.endswith(f"/{suffix}")
                or f"/{suffix}/" in normalized
            )
            if prefix_match and suffix_match:
                return True

        # fnmatch 通配符
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if fnmatch.fnmatch(Path(file_path).name, pattern):
            return True

        # 扩展名匹配 (*.exe)
        if pattern.startswith("*.") and normalized.endswith(pattern[1:]):
            return True

        return False

    # ── 动态管理接口（V2 用户习惯学习预留）───────────────────

    def add(self, pattern: str, tier: str, reason: str = "") -> "SafeList":
        """运行时添加一条白名单规则。去重：同名 pattern 会被替换。

        V2 场景：用户反复保留某类文件，系统自动学习并加入白名单。
        """
        self.remove(pattern)
        self._entries.append(SafeListEntry(pattern=pattern, tier=tier, reason=reason))
        logger.info("白名单新增: %s [%s] %s", pattern, tier, reason)
        return self

    def remove(self, pattern: str) -> bool:
        """按 pattern 移除一条白名单规则。返回是否成功移除。"""
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.pattern != pattern]
        removed = len(self._entries) < before
        if removed:
            logger.info("白名单移除: %s", pattern)
        return removed

    def save(self, config_path: str) -> None:
        """将当前白名单规则持久化到 YAML 配置文件。

        V2 场景：动态学习后的规则需要保存，下次启动时生效。
        """
        data = {
            "safelist": [
                {"pattern": e.pattern, "tier": e.tier, "reason": e.reason}
                for e in self._entries
            ]
        }
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        logger.info("白名单已保存: %s (%d 条规则)", config_path, len(self._entries))

    def get_entries(self) -> list[SafeListEntry]:
        """返回所有白名单规则的只读副本。"""
        return list(self._entries)

    # ── 查询接口 ──────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return len(self._entries) > 0


# ── 关联文件 ──────────────────────────────────────────────────
# [[agent/executor.py]] — execute_cleanup 调用 safelist.check() 拦截 🔴 文件
# [[config/safelist.yaml]] — 默认白名单配置文件
# [[dashboard/app.py]] — dashboard 用 get_tier_summary() 显示三色标签
# V2 预留：add/remove 供用户习惯学习，save 持久化学习结果
