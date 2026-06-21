import os
import pickle
from langchain_text_splitters import RecursiveCharacterTextSplitter
import config

_INDEX_FILE = os.path.join(config.DATA_DIR, "kb_index.pkl")
_index_cache = None


def build_index(docs: list[dict]) -> int:
    """构建简单的文本块索引（不依赖嵌入模型，零下载）"""
    if not docs:
        return 0

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n", "。", ".", " "],
    )

    chunks = []
    for doc in docs:
        for chunk in splitter.split_text(doc["content"]):
            chunks.append({"text": chunk, "source": doc["name"]})

    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(_INDEX_FILE, "wb") as f:
        pickle.dump(chunks, f)

    global _index_cache
    _index_cache = chunks
    return len(chunks)


def load_index() -> list[dict]:
    """加载已保存的索引"""
    global _index_cache
    if _index_cache is not None:
        return _index_cache
    if os.path.exists(_INDEX_FILE):
        with open(_INDEX_FILE, "rb") as f:
            _index_cache = pickle.load(f)
        return _index_cache
    return []


def search(query: str) -> list[str]:
    """简单的关键词匹配搜索（BM25 风格）"""
    chunks = load_index()
    if not chunks:
        return []

    keywords = set(query.lower().split())
    scored = []
    for chunk in chunks:
        text_lower = chunk["text"].lower()
        score = 0
        for kw in keywords:
            if kw in text_lower:
                score += 1
        if score > 0:
            scored.append((score, chunk["text"]))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:config.TOP_K_RETRIEVAL]]


def clear_index():
    global _index_cache
    _index_cache = None
    if os.path.exists(_INDEX_FILE):
        os.remove(_INDEX_FILE)
