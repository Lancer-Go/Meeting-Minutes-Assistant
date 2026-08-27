"""M4 · embedding 模块 — 文本向量化与纪要索引（TG-2）。

`EmbeddingProvider` 抽象 + OpenAI 兼容实现（如 bge-m3 / text-embedding-*）。
纪要完成后调用 `index_minute` 切块 → 向量化 → 写入 `minute_embeddings`；
无 embedding 密钥时返回 0（不阻断主链路，RAG 侧降级关键词检索）。
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app import config, db


def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    """按固定字符窗口切分文本（含重叠），供纪要向量化（默认 800 字符 + 200 重叠）。"""
    size = size or config.MMA_RAG_CHUNK_CHARS
    overlap = overlap if overlap is not None else config.MMA_RAG_CHUNK_OVERLAP
    text = text or ""
    if not text.strip():
        return []
    if size <= 0 or len(text) <= size:
        return [text]
    overlap = min(overlap, size - 1)
    step = max(1, size - overlap)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += step
    return chunks


class EmbeddingProvider(ABC):
    """向量化 Provider 抽象。"""

    name = "base"
    model = ""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """文本列表 → 向量列表（顺序一致）。"""
        ...


class OpenAICompatEmbedding(EmbeddingProvider):
    """OpenAI 兼容 Embedding API（bge-m3 / text-embedding-*）。"""

    name = "openai-compat"

    def __init__(self, base_url: str, api_key: str, model: str,
                 dim: int | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = dim or config.MMA_EMBEDDING_DIM
        if not (self.base_url and self.api_key):
            raise RuntimeError("缺少 embedding base_url / api_key，无法构造向量化 Provider。")

    def embed(self, texts: list[str]) -> list[list[float]]:
        from openai import OpenAI  # lazy import

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        resp = client.embeddings.create(model=self.model, input=texts)
        data = sorted(resp.data, key=lambda d: getattr(d, "index", 0))
        return [list(d.embedding) for d in data]


def embedding_enabled() -> bool:
    """embedding 是否已配置（base_url 与 api_key 均非空）。"""
    return bool(config.MMA_EMBEDDING_BASE_URL and config.MMA_EMBEDDING_API_KEY)


def get_embedding_provider() -> EmbeddingProvider | None:
    if not embedding_enabled():
        return None
    return OpenAICompatEmbedding(config.MMA_EMBEDDING_BASE_URL,
                                 config.MMA_EMBEDDING_API_KEY,
                                 config.MMA_EMBEDDING_MODEL,
                                 config.MMA_EMBEDDING_DIM)


def index_minute(task_id: str, user_id: str | None, text: str,
                 db_path=None) -> int:
    """纪要正文切块 → 向量化 → 写入 minute_embeddings。返回写入的块数（无密钥时 0）。"""
    provider = get_embedding_provider()
    if provider is None:
        return 0
    chunks = chunk_text(text)
    if not chunks:
        return 0
    vectors = provider.embed(chunks)
    if len(vectors) != len(chunks):
        raise RuntimeError(f"embedding 返回条数 {len(vectors)} 与输入 {len(chunks)} 不一致")
    return db.replace_embeddings(
        task_id, user_id,
        [{"text": c, "vector": json.loads(json.dumps(v))} for c, v in zip(chunks, vectors, strict=True)],
        db_path=db_path)
