"""AI 评分引擎 — 基于 DeepSeek 对用户作答进行打分和反馈。

评估维度：
  - 准确性：回答是否正确、完整
  - 深度：是否有细节展开和独到见解
  - 表达：逻辑是否清晰、语言是否流畅
  - 匹配度：是否切中面试官问题要点

评分区间：0-100 分
"""

import os
import yaml
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import SystemMessage, HumanMessage

_PROMPTS_CACHE: dict | None = None


def _load_prompts() -> dict:
    """加载 config/prompts.yaml，结果缓存避免重复 IO。"""
    global _PROMPTS_CACHE
    if _PROMPTS_CACHE is not None:
        return _PROMPTS_CACHE

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "prompts.yaml",
    )
    try:
        with open(config_path, encoding="utf-8") as f:
            _PROMPTS_CACHE = yaml.safe_load(f)
    except Exception:
        _PROMPTS_CACHE = {}

    return _PROMPTS_CACHE


def _get_system_prompt() -> str:
    """从配置文件读取 evaluator.system 提示词。"""
    prompts = _load_prompts()
    evaluator_cfg = prompts.get("evaluator", {}) if prompts else {}
    return evaluator_cfg.get("system", "").strip()


# evaluator 必须返回的字段及其类型
_REQUIRED_FIELDS: dict[str, tuple] = {
    "score": (int, float),
    "accuracy": (int, float),
    "depth": (int, float),
    "expression": (int, float),
    "relevance": (int, float),
    "feedback": (str,),
    "strengths": (list,),
    "improvements": (list,),
}


def _validate_result(data: dict) -> None:
    """校验 AI 返回的 JSON 是否包含所有必填字段且类型正确。

    任一不满足即抛 ValueError，由 evaluate_answer 的 except 捕获后返回 50 分降级值。
    """
    if not isinstance(data, dict):
        raise ValueError(f"Result must be dict, got {type(data).__name__}")

    for key, expected_types in _REQUIRED_FIELDS.items():
        if key not in data:
            raise ValueError(f"Missing required field: {key}")
        if not isinstance(data[key], expected_types):
            raise ValueError(
                f"Field {key} has wrong type: expected {expected_types}, "
                f"got {type(data[key]).__name__}"
            )


def evaluate_answer(question: str, answer: str, reference_answer: str = "") -> dict:
    """使用 AI 评估用户答案。

    Args:
        question: 面试题目
        answer: 用户作答
        reference_answer: 参考答案（可选，用于对比评分）

    Returns:
        评分 dict，包含 score / accuracy / depth / expression / relevance / feedback / strengths / improvements
    """
    if not answer.strip():
        return {
            "score": 0,
            "accuracy": 0,
            "depth": 0,
            "expression": 0,
            "relevance": 0,
            "feedback": "未作答",
            "strengths": [],
            "improvements": ["请尝试回答此问题"],
        }

    user_prompt = f"""面试题目：
{question}

参考答案（供你参考，非标准答案）：
{reference_answer or "无参考答案"}

候选人回答：
{answer}

请评估以上回答质量，按 JSON 格式输出。"""

    try:
        llm = ChatDeepSeek(
            model="deepseek-v4-flash",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0.3,
        )
        response = llm.invoke([
            SystemMessage(content=_get_system_prompt()),
            HumanMessage(content=user_prompt),
        ])
        content = response.content.strip()

        # 尝试解析 JSON
        import json
        import re
        # 处理可能的 markdown 代码块包裹：```json ... ``` 或 ``` ... ```
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', content, re.DOTALL)
        if match:
            content = match.group(1).strip()

        result = json.loads(content)
        _validate_result(result)
        return result

    except Exception as e:
        # AI 不可用时的降级方案
        return {
            "score": 50,
            "accuracy": 15,
            "depth": 15,
            "expression": 10,
            "relevance": 10,
            "feedback": f"AI 评分暂时不可用: {e}",
            "strengths": ["已提交作答"],
            "improvements": ["AI 评分服务恢复后将自动评估"],
        }
