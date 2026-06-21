"""PinnedContext — 关键事实留置，不被上下文截断丢失

参考 Ahy Agent pinned_context.py，轻量版：
工具结果或对话中确认的关键事实，始终注入 system prompt 前面。
"""

from dataclasses import dataclass, field


@dataclass
class PinnedContext:
    facts: list[str] = field(default_factory=list)
    max_facts: int = 10

    def add(self, fact: str):
        fact = fact.strip()[:200]
        if not fact or fact in self.facts:
            return
        self.facts.append(fact)
        while len(self.facts) > self.max_facts:
            self.facts.pop(0)

    def format_for_prompt(self) -> str:
        if not self.facts:
            return ""
        lines = ["【已确认的关键事实】"]
        for i, f in enumerate(self.facts, 1):
            lines.append(f"{i}. {f}")
        lines.append("（以上信息直接采纳，不要质疑或重新搜索）")
        return "\n".join(lines)

    def auto_extract_from_kb(self, query: str, results: list[str]):
        """从知识库检索结果中提取可留置的事实"""
        for r in results[:2]:
            # 取每条结果的前100字作为事实摘要
            snippet = r[:100].replace("\n", " ").strip()
            if snippet and len(snippet) > 10:
                self.add(f"知识库: {snippet}")

    def clear(self):
        self.facts.clear()


# 全局实例
_pinned = None


def get_pinned() -> PinnedContext:
    global _pinned
    if _pinned is None:
        _pinned = PinnedContext()
    return _pinned
