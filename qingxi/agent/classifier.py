"""AI 分类器 — 用 LangChain + DeepSeek 对 review 类型文件做语义分类。

核心安全原则：
- LLM 只收到文件元数据（文件名、路径、大小、修改时间、扩展名）
- 绝不读取文件内容传给云端 API
- LLM 输出只是分类建议，不直接触发文件操作

工作流程：
  scanner 输出 review_candidates → classifier 调用 LLM 分类 → 返回清理/保留决策
"""

import json
import os
from typing import Any

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_deepseek import ChatDeepSeek

from agent.scanner import FileEntry


# ── 工具定义 ──────────────────────────────────────────────
# LangChain 用 @tool 装饰器把普通函数注册为 Agent 可调用的工具。
# Agent 会根据用户指令自行决定何时调用这些工具。


@tool
def get_file_info(file_name: str, files_json: str) -> str:
    """根据文件名查找文件的元数据信息。

    Args:
        file_name: 要查找的文件名
        files_json: 所有待分类文件的 JSON 字符串

    Returns:
        该文件的元数据 JSON，或 "未找到该文件"
    """
    files = json.loads(files_json)
    for f in files:
        if f["name"] == file_name:
            return json.dumps(f, ensure_ascii=False, indent=2)
    return f"未找到文件: {file_name}"


@tool
def list_file_extensions(files_json: str) -> str:
    """列出待分类文件中所有的文件扩展名及数量统计。

    Args:
        files_json: 所有待分类文件的 JSON 字符串

    Returns:
        扩展名统计的 JSON 字符串
    """
    files = json.loads(files_json)
    ext_counts: dict[str, int] = {}
    for f in files:
        ext = f.get("extension", "无扩展名")
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    return json.dumps(ext_counts, ensure_ascii=False, indent=2)


@tool
def get_large_files(files_json: str, min_size_mb: float = 10.0) -> str:
    """筛出大于指定大小的文件。

    Args:
        files_json: 所有待分类文件的 JSON 字符串
        min_size_mb: 最小文件大小（MB），默认 10MB

    Returns:
        大文件列表的 JSON
    """
    files = json.loads(files_json)
    min_bytes = min_size_mb * 1024 * 1024
    large = [f for f in files if f.get("size_bytes", 0) > min_bytes]
    return json.dumps(large, ensure_ascii=False, indent=2)


# ── 分类器 ────────────────────────────────────────────────


class FileClassifier:
    """用 LLM 对文件进行语义分类。

    使用方式：
        classifier = FileClassifier()
        decisions = classifier.classify(review_files)
    """

    SYSTEM_PROMPT = """你是一个文件管理系统专家。你的任务是分析一批文件的元数据，判断每个文件应该"保留(keep)"还是"清理(cleanup)"。

## 判断原则

1. **设计源文件优先保留**：.psd, .ai, .cdr, .eps, .sketch 等设计源文件几乎总是保留
2. **导出文件可清理**：.png, .jpg, .pdf 等导出格式，超过 30 天大概率是废稿
3. **看文件名语义**：文件名含 "定稿" "最终版" "确认稿" "生产版" 保留
4. **看文件名语义**：文件名含 "测试" "草稿" "副本" "未命名" "test" "draft" "copy" 清理
5. **临时文件和缓存直接清理**：.tmp, .cache, .bak, ~ 结尾的文件
6. **特大文件优先清理**：超过 50MB 且是导出或备份文件
7. **不确定时保守**：拿不准就保留

## 输出格式

返回一个 JSON 数组，每个元素包含：
- "name": 文件名
- "action": "keep" 或 "cleanup"
- "reason": 理由（10个字以内）

只返回 JSON 数组，不要任何其他文字。
示例：[{"name": "定稿.psd", "action": "keep", "reason": "设计源文件"}, ...]"""

    def __init__(
        self, api_key: str | None = None, base_url: str | None = None
    ) -> None:
        api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        base_url = base_url or os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )

        self._llm = ChatDeepSeek(
            model="deepseek-chat",
            api_key=api_key,
            api_base=base_url,
            temperature=0.1,
        )
        self._agent = create_agent(
            model=self._llm,
            tools=[get_file_info, list_file_extensions, get_large_files],
            system_prompt=self.SYSTEM_PROMPT,
        )

    def classify(self, files: list[FileEntry]) -> list[dict[str, str]]:
        """对一批文件进行分类，返回每个文件的决策。"""
        if not files:
            return []

        files_data = [
            {
                "name": f.name,
                "extension": f.extension,
                "size_bytes": f.size_bytes,
                "size_mb": round(f.size_bytes / (1024 * 1024), 2),
                "age_days": f.age_days,
                "modified_at": f.modified_at,
                "matched_rule": f.matched_rule,
            }
            for f in files
        ]
        files_json = json.dumps(files_data, ensure_ascii=False)

        task = f"""请分析以下 {len(files_data)} 个文件，判断每个文件应该保留还是清理。

文件列表（JSON）：
{files_json}

请逐个分析每个文件，返回分类结果。你可以用工具辅助分析。
记住：只返回 JSON 数组，格式为 [{{"name": "...", "action": "keep|cleanup", "reason": "..."}}, ...]"""

        result = self._agent.invoke({
            "messages": [{"role": "user", "content": task}],
        })

        return self._parse_response(result)

    def _parse_response(self, result: dict[str, Any]) -> list[dict[str, str]]:
        """从 Agent 返回中提取 JSON 分类结果。"""
        messages = result.get("messages", [])
        for msg in reversed(messages):
            content = getattr(msg, "content", "")
            if not content:
                continue
            try:
                start = content.index("[")
                end = content.rindex("]") + 1
                return json.loads(content[start:end])
            except (ValueError, json.JSONDecodeError):
                continue
        return []
