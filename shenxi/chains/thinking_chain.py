from langchain_core.messages import HumanMessage
from langchain_deepseek import ChatDeepSeek
import config
from knowledge.fts5_store import search as kb_search
from utils.pinned_context import get_pinned


def _is_thinking_mode(query: str) -> bool:
    q = query.strip()
    return q.startswith('/think ') or q.startswith('/deep ')


def _extract_query(query: str) -> str:
    q = query.strip()
    if ' ' in q:
        return q.split(' ', 1)[1].strip()
    return q


def prepare(user_query: str, chat_history: list,
            file_content: str = "", image_description: str = "",
            deep_thinking: bool = False) -> str:
    from datetime import datetime
    history_text = _format_history(chat_history)
    today = datetime.now().strftime("%Y年%m月%d日")

    pinned = get_pinned()
    pinned_text = pinned.format_for_prompt()

    extra_context = ""
    if file_content:
        extra_context += f"\n\n【上传文件内容】\n{file_content[:8000]}"
    if image_description:
        extra_context += f"\n\n【上传图片描述】\n{image_description}"

    # 深度思考模式：开关开启 或 /think /deep 文字触发
    if deep_thinking or _is_thinking_mode(user_query):
        real_question = _extract_query(user_query)
        kb_results = kb_search(real_question)
        pinned.auto_extract_from_kb(real_question, kb_results)
        kb_text = "\n---\n".join(kb_results) if kb_results else "（暂无相关知识库内容）"
        from tools.web_search import agentic_search, format_results
        web_result = agentic_search(real_question, deep=True)
        web_text = format_results(web_result) if web_result.get("success") else ""

        llm = ChatDeepSeek(
            model=config.DEEPSEEK_MODEL,
            api_key=config.DEEPSEEK_API_KEY,
            api_base=config.DEEPSEEK_BASE_URL,
            temperature=0.3,
        )
        reasoning = _call_llm(llm, _build_thinking_prompt(
            real_question, kb_text, web_text, extra_context, history_text, today, pinned_text))
        return _build_thinking_output(reasoning)

    # 默认模式：轻量一步直达
    kb_results = kb_search(user_query)
    pinned.auto_extract_from_kb(user_query, kb_results)
    kb_text = "\n---\n".join(kb_results) if kb_results else "（暂无相关知识库内容）"

    from tools.web_search import agentic_search, format_results
    web_result = agentic_search(user_query)
    web_text = format_results(web_result) if web_result.get("success") else ""

    if kb_text == "（暂无相关知识库内容）" and not web_text:
        search_note = "（未找到相关信息，请基于通用知识直接回答）"
    elif not web_text:
        search_note = f"## 知识库参考资料\n{kb_text}"
    elif kb_text == "（暂无相关知识库内容）":
        search_note = f"## 联网搜索结果\n{web_text}"
    else:
        search_note = f"## 知识库参考资料\n{kb_text}\n## 联网搜索结果\n{web_text}"

    return f"""当前日期：{today}
{pinned_text}
## 用户问题
{user_query}
{search_note}
{extra_context}
## 对话历史
{history_text}

请直接回答用户的问题。规则：
- 联网搜索结果不相关或为空时，诚实说"未找到相关信息"，绝不编造
- 只基于训练知识时，开头标注"以下基于通用知识，非实时信息："
- 数字/价格/数据必须标注来源，没有来源就不要编
- 避免输出大段空泛的分析框架，紧扣用户问题给出实质内容
- 根据问题类型自动切换风格：闲聊用自然语气，分析用结构化格式，事实问题简洁直接"""


def _build_thinking_prompt(question, kb_text, web_text, extra, history, today, pinned_text=""):
    return f"""当前日期：{today}
{pinned_text}

请严格按照以下六阶段框架，对问题进行深度分析：

## 第一阶段：问题理解
- 用自己的话重新描述核心问题
- 识别背景和上下文
- 明确已知条件和未知要素

## 第二阶段：问题空间探索
- 将复杂问题拆解为多个子问题
- 理解每个子问题的需求和限制
- 建立问题之间的关联性

## 第三阶段：假设生成
- 提出至少3种不同的解决思路
- 从技术、业务、成本等多个视角评估
- 初步判断每种思路的可行性

## 第四阶段：深度推理
- 逐步深入每个子问题
- 记录推理过程中的关键发现
- 形成初步结论

## 第五阶段：自我验证
- 检查推理过程的逻辑一致性
- 寻找可能的漏洞和反例
- 修正不完善的思考

## 第六阶段：知识整合
- 将分散的结论整合成完整答案
- 用清晰的层次结构呈现
- **关键结论用粗体标注**
- 明确标注不确定或有待验证的部分

## 参考资料
### 知识库
{kb_text}
### 联网搜索
{web_text}
### 对话历史
{history}
{extra}

## 用户问题
{question}

## 关键规则
- 外部事实（公司、股价、新闻、行业数据）→ 必须基于搜索结果，搜到了引用来源，没搜到说"未搜索到相关信息"
- 不要搜不到就给一堆废话框架，搜不到就简短说明
- 股票/金融数据绝对不要编造，只引用搜索结果中的实际数据并标注日期
- 不要预测未来价格走势

请严格按照上述六阶段框架输出分析报告，每个阶段使用二级标题（##）。最后给出明确的最终结论。"""


def _build_thinking_output(reasoning):
    return f"""基于深度思考框架的六阶段分析结果：

{reasoning}

---
> 本分析使用六阶段深度思考框架生成"""


def stream_output(prompt: str, deep: bool = False):
    """流式生成最终输出"""
    llm = ChatDeepSeek(
        model=config.DEEPSEEK_MODEL,
        api_key=config.DEEPSEEK_API_KEY,
        api_base=config.DEEPSEEK_BASE_URL,
        temperature=0.3,
    )
    try:
        for chunk in llm.stream([HumanMessage(content=prompt)]):
            if chunk.content:
                yield chunk.content
    except Exception:
        yield "（生成中断，请重试）"


def _call_llm(llm, prompt: str) -> str:
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        return resp.content.strip()
    except Exception:
        return "（分析超时）"


def _format_history(history: list) -> str:
    if not history:
        return "（新对话）"
    lines = []
    for msg in history[-6:]:
        role = "用户" if msg["role"] == "user" else "助手"
        lines.append(f"{role}: {msg['content'][:300]}")
    return "\n".join(lines)
