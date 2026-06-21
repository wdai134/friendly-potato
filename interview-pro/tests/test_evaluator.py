"""测试 evaluator 模块 — AI 四维评分引擎。"""
import pytest
from unittest.mock import patch, MagicMock, mock_open
from agent.evaluator import (
    _load_prompts,
    _get_system_prompt,
    _validate_result,
    evaluate_answer,
)

# ═══════════════════════════════════════════════════════════════════════
# _load_prompts() tests
# ═══════════════════════════════════════════════════════════════════════

def test_load_prompts_returns_dict():
    """正常加载 prompts.yaml 应返回非空 dict。"""
    with patch("builtins.open", mock_open(read_data="evaluator:\n  system: 'test prompt'")):
        with patch("yaml.safe_load", return_value={"evaluator": {"system": "test prompt"}}):
            result = _load_prompts()
            assert isinstance(result, dict)
            assert "evaluator" in result


def test_load_prompts_is_cached():
    """第一次加载后应缓存，第二次不重新读文件。"""
    # 清除缓存（模块级变量）
    import agent.evaluator as ev
    ev._PROMPTS_CACHE = None

    with patch("builtins.open", mock_open(read_data="evaluator:\n  system: 'test'")):
        with patch("yaml.safe_load", return_value={"evaluator": {"system": "test"}}):
            r1 = _load_prompts()
            # 再次调用不应再 open
            r2 = _load_prompts()
            assert r1 is r2


def test_load_prompts_file_not_found():
    """文件不存在时应返回空 dict 而非崩溃。"""
    import agent.evaluator as ev
    ev._PROMPTS_CACHE = None

    with patch("builtins.open", side_effect=FileNotFoundError("no file")):
        result = _load_prompts()
        assert result == {}


def test_load_prompts_yaml_error():
    """YAML 解析失败时应返回空 dict。"""
    import agent.evaluator as ev
    ev._PROMPTS_CACHE = None

    with patch("builtins.open", mock_open(read_data="bad: [unclosed")):
        with patch("yaml.safe_load", side_effect=Exception("parse error")):
            result = _load_prompts()
            assert result == {}


# ═══════════════════════════════════════════════════════════════════════
# _get_system_prompt() tests
# ═══════════════════════════════════════════════════════════════════════

def test_get_system_prompt_returns_string():
    """正常情况应返回 evaluator.system 内容。"""
    import agent.evaluator as ev
    ev._PROMPTS_CACHE = {"evaluator": {"system": "你是一位资深技术面试官..."}}

    result = _get_system_prompt()
    assert isinstance(result, str)
    assert "面试官" in result


def test_get_system_prompt_missing_key():
    """evaluator key 缺失时返回空字符串。"""
    import agent.evaluator as ev
    ev._PROMPTS_CACHE = {}

    result = _get_system_prompt()
    assert result == ""


def test_get_system_prompt_none_cache():
    """缓存为空时应触发加载（mock 掉 open 避免真实 IO）。"""
    import agent.evaluator as ev
    ev._PROMPTS_CACHE = None

    mock_yaml = {"evaluator": {"system": "从文件加载的提示词"}}
    with patch("builtins.open", mock_open()):
        with patch("yaml.safe_load", return_value=mock_yaml):
            result = _get_system_prompt()
            assert "从文件加载的提示词" in result


# ═══════════════════════════════════════════════════════════════════════
# evaluate_answer() tests
# ═══════════════════════════════════════════════════════════════════════

def test_evaluate_empty_answer():
    """空答案应返回 0 分 + 特殊提示，不走 AI。"""
    result = evaluate_answer("什么是 Python GIL？", "")
    assert result["score"] == 0
    assert result["accuracy"] == 0
    assert result["depth"] == 0
    assert result["expression"] == 0
    assert result["relevance"] == 0
    assert result["feedback"] == "未作答"
    assert "请尝试回答此问题" in result["improvements"]


def test_evaluate_whitespace_only_answer():
    """纯空格答案也视为空答案。"""
    result = evaluate_answer("题目", "   \n  ")
    assert result["score"] == 0
    assert result["feedback"] == "未作答"


def test_evaluate_normal_answer():
    """正常答案应调 AI 并返回四维评分。"""
    mock_response = MagicMock()
    mock_response.content = (
        '{"score": 82, "accuracy": 25, "depth": 22, '
        '"expression": 18, "relevance": 17, '
        '"feedback": "回答准确且有实际经验支撑", '
        '"strengths": ["有项目经验", "逻辑清晰"], '
        '"improvements": ["可以更深入"]}'
    )

    with patch("agent.evaluator.ChatDeepSeek") as mock_llm:
        mock_llm.return_value.invoke.return_value = mock_response
        result = evaluate_answer("Python GIL 是什么？", "GIL 是全局解释器锁...")

    assert result["score"] == 82
    assert result["accuracy"] == 25
    assert result["depth"] == 22
    assert result["expression"] == 18
    assert result["relevance"] == 17
    assert result["feedback"] == "回答准确且有实际经验支撑"
    assert len(result["strengths"]) == 2
    assert len(result["improvements"]) == 1


def test_evaluate_answer_with_reference():
    """有参考答案时也应正常评分。"""
    mock_response = MagicMock()
    mock_response.content = (
        '{"score": 90, "accuracy": 28, "depth": 26, '
        '"expression": 19, "relevance": 17, '
        '"feedback": "与参考答案高度一致", '
        '"strengths": ["全面"], "improvements": []}'
    )

    with patch("agent.evaluator.ChatDeepSeek") as mock_llm:
        mock_llm.return_value.invoke.return_value = mock_response
        result = evaluate_answer(
            "题目", "回答",
            reference_answer="参考答案内容",
        )

    assert result["score"] == 90


def test_evaluate_answer_json_with_markdown_wrapper():
    """AI 返回 markdown 代码块包裹的 JSON 时应正确解析。"""
    mock_response = MagicMock()
    mock_response.content = (
        '```json\n'
        '{"score": 75, "accuracy": 22, "depth": 20, '
        '"expression": 17, "relevance": 16, '
        '"feedback": "不错", '
        '"strengths": ["有见解"], "improvements": ["加实例"]}\n'
        '```'
    )

    with patch("agent.evaluator.ChatDeepSeek") as mock_llm:
        mock_llm.return_value.invoke.return_value = mock_response
        result = evaluate_answer("题目", "回答")

    assert result["score"] == 75
    assert result["accuracy"] == 22


def test_evaluate_answer_json_markdown_no_newlines():
    """```json{...}``` 无换行的紧凑格式也应正确解析。"""
    mock_response = MagicMock()
    mock_response.content = (
        '```json{"score": 80, "accuracy": 24, "depth": 22, '
        '"expression": 18, "relevance": 16, '
        '"feedback": "不错", "strengths": ["有见解"], "improvements": ["加实例"]}```'
    )

    with patch("agent.evaluator.ChatDeepSeek") as mock_llm:
        mock_llm.return_value.invoke.return_value = mock_response
        result = evaluate_answer("题目", "回答")

    assert result["score"] == 80


def test_evaluate_answer_json_markdown_with_surrounding_text():
    """代码块前后有额外文字时，应提取出 JSON。"""
    mock_response = MagicMock()
    mock_response.content = (
        '以下是评分结果：\n'
        '```json\n'
        '{"score": 70, "accuracy": 20, "depth": 18, '
        '"expression": 16, "relevance": 16, '
        '"feedback": "还行", "strengths": [], "improvements": ["加深"]}\n'
        '```\n'
        '希望以上反馈对你有帮助。'
    )

    with patch("agent.evaluator.ChatDeepSeek") as mock_llm:
        mock_llm.return_value.invoke.return_value = mock_response
        result = evaluate_answer("题目", "回答")

    assert result["score"] == 70


def test_evaluate_answer_json_markdown_no_lang_tag():
    """不带语言标签的 ``` ``` 代码块也应正确解析。"""
    mock_response = MagicMock()
    mock_response.content = (
        '```\n'
        '{"score": 85, "accuracy": 26, "depth": 24, '
        '"expression": 19, "relevance": 16, '
        '"feedback": "优秀", "strengths": ["很好"], "improvements": []}\n'
        '```'
    )

    with patch("agent.evaluator.ChatDeepSeek") as mock_llm:
        mock_llm.return_value.invoke.return_value = mock_response
        result = evaluate_answer("题目", "回答")

    assert result["score"] == 85


def test_evaluate_answer_api_error_fallback():
    """API 调用失败时返回 50 分降级值 + 错误信息。"""
    with patch("agent.evaluator.ChatDeepSeek") as mock_llm:
        mock_llm.return_value.invoke.side_effect = Exception("Network error")

        result = evaluate_answer("题目", "正常回答")

    assert result["score"] == 50
    assert result["accuracy"] == 15
    assert result["depth"] == 15
    assert result["expression"] == 10
    assert result["relevance"] == 10
    assert "Network error" in result["feedback"]
    assert "已提交作答" in result["strengths"]


def test_evaluate_answer_json_parse_error():
    """AI 返回非法 JSON 时触发降级。"""
    mock_response = MagicMock()
    mock_response.content = "这不是合法的 JSON 格式"

    with patch("agent.evaluator.ChatDeepSeek") as mock_llm:
        mock_llm.return_value.invoke.return_value = mock_response
        result = evaluate_answer("题目", "回答")

    assert result["score"] == 50
    assert "AI 评分暂时不可用" in result["feedback"]


def test_evaluate_answer_missing_api_key():
    """未设置 API key 时触发降级。"""
    with patch("agent.evaluator.ChatDeepSeek") as mock_llm:
        mock_llm.return_value.invoke.side_effect = Exception("No API key")

        result = evaluate_answer("题目", "回答")

    assert result["score"] == 50


# ═══════════════════════════════════════════════════════════════════════
# _validate_result() tests
# ═══════════════════════════════════════════════════════════════════════

VALID_RESULT = {
    "score": 82, "accuracy": 25, "depth": 22,
    "expression": 18, "relevance": 17,
    "feedback": "不错", "strengths": ["有见解"], "improvements": ["加实例"],
}


def test_validate_result_valid():
    """完整字段应无异常。"""
    _validate_result(VALID_RESULT)  # 不抛异常即通过


def test_validate_result_missing_field():
    """缺少必填字段应抛 ValueError。"""
    incomplete = {"score": 80, "feedback": "缺了很多"}
    with pytest.raises(ValueError, match="Missing required field"):
        _validate_result(incomplete)


def test_validate_result_wrong_type():
    """字段类型错误应抛 ValueError。"""
    bad_type = {**VALID_RESULT, "strengths": "不是列表"}
    with pytest.raises(ValueError, match="wrong type"):
        _validate_result(bad_type)


def test_validate_result_not_dict():
    """非 dict 输入应抛 ValueError。"""
    with pytest.raises(ValueError, match="must be dict"):
        _validate_result(["not", "a", "dict"])


def test_evaluate_answer_partial_json_triggers_fallback():
    """LLM 返回 JSON 缺字段 → _validate_result 抛异常 → 返回 50 分降级。"""
    mock_response = MagicMock()
    mock_response.content = '{"score": 70}'  # 缺 7 个必填字段

    with patch("agent.evaluator.ChatDeepSeek") as mock_llm:
        mock_llm.return_value.invoke.return_value = mock_response
        result = evaluate_answer("题目", "回答")

    assert result["score"] == 50
    assert "AI 评分暂时不可用" in result["feedback"]


def test_evaluate_answer_json_with_wrong_type_triggers_fallback():
    """LLM 返回 JSON 但 score 是字符串 → 返回 50 分降级。"""
    mock_response = MagicMock()
    mock_response.content = (
        '{"score": "八十五", "accuracy": 25, "depth": 22, '
        '"expression": 18, "relevance": 17, '
        '"feedback": "不错", "strengths": [], "improvements": []}'
    )

    with patch("agent.evaluator.ChatDeepSeek") as mock_llm:
        mock_llm.return_value.invoke.return_value = mock_response
        result = evaluate_answer("题目", "回答")

    assert result["score"] == 50
