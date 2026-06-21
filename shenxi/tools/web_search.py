"""智能搜索 — LLM驱动多轮并行搜索 + SearXNG + DuckDuckGo 兜底

策略：
1. LLM分析用户问题，生成多个搜索关键词
2. 并行执行所有关键词搜索（SearXNG→DDG双引擎降级）
3. URL去重后返回
4. LLM评估结果是否足够，不够则生成新关键词再搜
5. 硬上限：最多3轮（深度5轮），最多30条结果（深度50条）
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import config

# ── 搜索缓存 ─────────────────────────────────────────────────────
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 1800  # 30分钟


def _cache_key(query: str, count: int) -> str:
    return f"{query.strip().lower()}|{count}"


def _cache_get(query: str, count: int) -> dict | None:
    key = _cache_key(query, count)
    entry = _CACHE.get(key)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(query: str, count: int, result: dict):
    key = _cache_key(query, count)
    _CACHE[key] = (time.time(), result)
    if len(_CACHE) > 200:
        now = time.time()
        expired = [k for k, v in _CACHE.items() if now - v[0] >= _CACHE_TTL]
        for k in expired:
            del _CACHE[k]


# ── 硬上限 ─────────────────────────────────────────────────────
MAX_ROUNDS = 3
MAX_RESULTS = 30
PER_QUERY_COUNT = 20
MIN_RESULTS = 5


# ── SearXNG 搜索 (主力) ──────────────────────────────────────────

def _searxng_search(query: str, count: int = 20) -> list[dict]:
    """SearXNG 聚合搜索"""
    if not config.SEARXNG_URL:
        return []
    try:
        resp = requests.get(
            f"{config.SEARXNG_URL}/search",
            params={
                "q": query,
                "format": "json",
                "engines": config.SEARXNG_ENGINES,
                "pageno": 1,
            },
            timeout=config.SEARCH_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for r in data.get("results", [])[:count]:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": (r.get("content") or r.get("snippet", ""))[:300],
            })
        return results
    except Exception:
        return []


# ── DuckDuckGo 搜索 (回退) ───────────────────────────────────────

def _ddg_search(query: str, count: int = 5) -> list[dict]:
    """DuckDuckGo 搜索"""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = []
            for r in ddgs.text(query, max_results=count):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")[:300],
                })
            if results:
                return results
    except Exception:
        pass
    # HTML 解析兜底
    try:
        from urllib.request import Request, urlopen
        from urllib.parse import quote
        req = Request(
            "https://html.duckduckgo.com/html/",
            data=f"q={quote(query)}".encode(),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urlopen(req, timeout=8) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        results = []
        for m in re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            text, re.DOTALL,
        ):
            results.append({
                "title": re.sub(r'<[^>]+>', '', m.group(2)).strip(),
                "url": m.group(1),
                "snippet": re.sub(r'<[^>]+>', '', m.group(3)).strip()[:300],
            })
            if len(results) >= count:
                break
        return results
    except Exception:
        return []


# ── 相关性过滤 ─────────────────────────────────────────────────

def _extract_keywords(query: str) -> list[str]:
    tokens = re.split(r'[\s,，。、；：""''（）()\\[\\]【】!?？！]+', query)
    stopwords = {"的","了","是","在","和","有","不","人","这","中",
                 "大","为","上","个","到","说","要","就","与","也",
                 "可","会","对","能","着","把","那","它","及","或",
                 "请","帮","我","查","搜","找","一下","什么","怎么",
                 "如何","哪些","哪个","多少","the","a","an","is","are",
                 "was","were","be","been","being","have","has","had",
                 "do","does","did","will","would","could","should",
                 "may","might","shall","can","need","dare","ought",
                 "used","to","of","in","for","on","with","at","by",
                 "from","as","into","through","during","before","after",
                 "above","below","between","out","off","over","under",
                 "again","further","then","once","and","but","or","nor",
                 "not","so","very","just","about","than","too","also"}
    return [t for t in tokens if len(t) >= 2 and t.lower() not in stopwords]


def _filter_relevant(query: str, results: list[dict], min_ratio: float = 0.3) -> list[dict]:
    if not results:
        return []
    keywords = _extract_keywords(query)
    if not keywords:
        return results
    relevant = []
    for r in results:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        if any(kw.lower() in text for kw in keywords):
            relevant.append(r)
    if len(relevant) / len(results) < min_ratio:
        return []
    return relevant


# ── 单次搜索 ─────────────────────────────────────────────────────

def search(query: str, count: int = 20) -> dict:
    """单次搜索 — SearXNG 优先，DuckDuckGo 回退

    返回: {"success": True/False, "results": [...], "engine": "searxng"|"ddg", "query": "..."}
    """
    cached = _cache_get(query, count)
    if cached is not None:
        return cached

    # 重试机制
    for attempt in range(config.SEARCH_RETRY):
        results = _searxng_search(query, count)
        results = _filter_relevant(query, results)
        if results:
            r = {"success": True, "results": results[:count], "query": query, "engine": "searxng"}
            _cache_set(query, count, r)
            return r
        if attempt < config.SEARCH_RETRY - 1:
            time.sleep(1.5)

    results = _ddg_search(query, count)
    results = _filter_relevant(query, results)
    if results:
        r = {"success": True, "results": results[:count], "query": query, "engine": "ddg"}
        _cache_set(query, count, r)
        return r

    r = {"success": False, "error": "搜索无结果", "query": query}
    _cache_set(query, count, r)
    return r


# ── 并行多关键词搜索 ─────────────────────────────────────────────

def _parallel_search(queries: list[str], count: int = PER_QUERY_COUNT) -> list[dict]:
    """并行执行多个关键词搜索，返回去重后的结果"""
    all_results = []
    seen_urls = set()
    with ThreadPoolExecutor(max_workers=min(len(queries), 4)) as pool:
        futures = {pool.submit(search, q, count): q for q in queries}
        for future in as_completed(futures):
            try:
                r = future.result()
            except Exception:
                continue
            if r.get("success"):
                for item in r["results"]:
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(item)
    return all_results


# ── LLM驱动的智能搜索 ────────────────────────────────────────────

def _get_search_llm(temperature: float = 0.3):
    from langchain_deepseek import ChatDeepSeek
    return ChatDeepSeek(
        model=config.DEEPSEEK_MODEL,
        api_key=config.DEEPSEEK_API_KEY,
        api_base=config.DEEPSEEK_BASE_URL,
        temperature=temperature,
    )


def _extract_json_array(text: str) -> list | None:
    start = text.find('[')
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '[': depth += 1
        elif text[i] == ']':
            depth -= 1
            if depth == 0:
                try: return json.loads(text[start:i+1])
                except json.JSONDecodeError: return None
    return None


def _extract_json_object(text: str) -> dict | None:
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{': depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                try: return json.loads(text[start:i+1])
                except json.JSONDecodeError: return None
    return None


def _llm_plan_queries(user_query: str, already_searched: list[str],
                      existing_results: list[dict], round_num: int,
                      llm=None) -> list[str]:
    from langchain_core.messages import HumanMessage
    if llm is None:
        llm = _get_search_llm(0.3)

    already_text = "\n".join(f"- {q}" for q in already_searched) if already_searched else "（无）"
    results_text = f"已有{len(existing_results)}条结果" if existing_results else "暂无结果"

    prompt = f"""你是一个搜索策略专家。根据用户问题，生成搜索关键词。

## 用户问题
{user_query}

## 当前状态
- 第{round_num}轮搜索
- 已搜索过的关键词（不要重复）：
{already_text}
- {results_text}

## 要求
1. 生成3-5个不同角度的搜索关键词
2. 不要和已搜索的关键词重复
3. 覆盖不同维度：行业术语、技术原理、最新动态、实际案例、对比分析等
4. 每个关键词控制在10-30字

## 输出格式（严格JSON数组，不要输出其他内容）
["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]"""

    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = resp.content.strip()
        queries = _extract_json_array(text)
        if queries and isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            return [q for q in queries if q.strip()][:5]
    except Exception:
        pass
    return [user_query]


def _llm_evaluate(user_query: str, results: list[dict], round_num: int, llm=None) -> bool:
    from langchain_core.messages import HumanMessage
    if llm is None:
        llm = _get_search_llm(0.1)

    results_summary = "\n".join(
        f"{i+1}. [{r.get('title', '')}] {r.get('snippet', '')[:80]}"
        for i, r in enumerate(results[:10])
    )

    prompt = f"""判断搜索结果是否足够回答用户问题。

## 用户问题
{user_query}

## 当前结果（共{len(results)}条）
{results_summary}

## 判断标准
- 结果能覆盖问题的主要方面 → 足够
- 结果明显偏题或信息太少 → 不足

## 输出（严格JSON，不要输出其他内容）
{{"sufficient": true/false, "reason": "一句话原因"}}"""

    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = resp.content.strip()
        data = _extract_json_object(text)
        if data:
            return bool(data.get("sufficient", False))
    except Exception:
        pass
    return len(results) >= MIN_RESULTS


def agentic_search(user_query: str, deep: bool = False) -> dict:
    """LLM驱动的多轮并行搜索

    流程：
    1. LLM生成初始关键词 → 并行搜索 → 去重
    2. LLM评估是否足够 → 不够则生成新关键词再搜
    3. 最多3轮（深度5轮），最多30条结果（深度50条）
    4. 总限时30秒（深度60秒），超时降级到简单并行搜索

    返回：
        {"success": True, "results": [...], "rounds": N, "total_queries": M, "elapsed": S}
        {"success": False, "error": "...", "rounds": N}
    """
    start_time = time.time()

    if deep:
        max_rounds, max_results, per_query, min_results, timeout = 5, 50, 25, 8, 60
    else:
        max_rounds, max_results, per_query, min_results, timeout = MAX_ROUNDS, MAX_RESULTS, PER_QUERY_COUNT, MIN_RESULTS, 30

    all_results, seen_urls, all_queries = [], set(), []
    llm = _get_search_llm(0.3)

    for round_num in range(1, max_rounds + 1):
        if time.time() - start_time > timeout:
            break

        try:
            queries = _llm_plan_queries(user_query, all_queries, all_results, round_num, llm=llm)
        except Exception:
            queries = [user_query]

        if not queries:
            break
        all_queries.extend(queries)

        round_results = _parallel_search(queries, per_query)
        new_count = 0
        for item in round_results:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(item)
                new_count += 1

        if len(all_results) >= max_results:
            all_results = all_results[:max_results]
            break

        if new_count == 0 and round_num > 1:
            break

        if round_num < max_rounds:
            if time.time() - start_time > timeout:
                break
            try:
                if _llm_evaluate(user_query, all_results, round_num, llm=llm):
                    break
            except Exception:
                if len(all_results) >= min_results:
                    break

    if all_results:
        return {
            "success": True, "results": all_results[:max_results],
            "query": user_query, "engine": "agentic",
            "rounds": round_num, "total_queries": len(all_queries),
            "elapsed": round(time.time() - start_time, 1),
        }

    fallback = search(user_query, max_results)
    if fallback.get("success"):
        fallback["engine"] = "fallback"
        fallback["rounds"] = round_num
        fallback["total_queries"] = len(all_queries)
        fallback["elapsed"] = round(time.time() - start_time, 1)
        return fallback

    return {
        "success": False, "error": "搜索无结果", "query": user_query,
        "rounds": round_num, "total_queries": len(all_queries),
        "elapsed": round(time.time() - start_time, 1),
    }


# ── 格式化 ─────────────────────────────────────────────────────

def format_results(search_result: dict) -> str:
    if not search_result.get("success"):
        return ""
    lines = []
    for i, r in enumerate(search_result["results"], 1):
        lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   {r['url']}")
    return "\n\n".join(lines)
