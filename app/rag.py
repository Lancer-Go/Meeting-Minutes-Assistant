"""M4 · rag 模块 — 检索问答（TG-3）。

query → embedding → 余弦 top-k 检索（按 user_id 越权隔离）→ 拼上下文 → LLM 生成带引用答案。
降级：无 pgvector / 无 embedding 密钥 → 关键词检索兜底（复用 M2 `search_minutes`）；两者皆无 → 明确「未启用」。

检索实现说明：`minute_embeddings.embedding` 以 JSON 文本列存储（跨 SQLite/PG 通用），
相似度用 Python 余弦计算（可移植、可测试）。生产 PG 已启用 pgvector 扩展（compose 初始化），
后续可将此列迁移为原生 `vector(1024)` + HNSW 索引以支撑更大规模，接口不变。
"""
from __future__ import annotations

import json
import math

from app import config, db
from app.embedding import embedding_enabled, get_embedding_provider

QA_SYSTEM_PROMPT = (
    "你是会议纪要助手。请根据提供的会议纪要片段回答用户问题，用中文 Markdown 输出，"
    "并在答案中标注引用来源编号（如 [来源1]）。若片段不足以回答，请明确说明"
    "「现有纪要中未找到相关信息」，不要臆造片段之外的内容。"
)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _parse_vector(s: str) -> list[float]:
    try:
        v = json.loads(s or "[]")
        return [float(x) for x in v] if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def retrieve(query_embedding: list[float], user_id: str | None, top_k: int,
             db_path=None) -> list[dict]:
    """向量相似检索 top-k（按 user_id 隔离），附 similarity 字段。"""
    rows = db.list_embeddings(user_id=user_id, db_path=db_path)
    scored: list[tuple[float, dict]] = []
    for r in rows:
        vec = _parse_vector(r.get("embedding", ""))
        if not vec:
            continue
        scored.append((_cosine(query_embedding, vec), r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [dict(r, similarity=round(s, 4)) for s, r in scored[:top_k]]


def keyword_search(query: str, user_id: str | None, top_k: int,
                   db_path=None) -> list[dict]:
    """关键词兜底检索（无 embedding 密钥 / 无向量命中时）。基于 minutes 表 LIKE。"""
    minutes = db.search_minutes(q=query, user_id=user_id, db_path=db_path)
    return [dict(m, similarity=None) for m in minutes[:top_k]]


def _enrich_sources(sources: list[dict], db_path=None) -> list[dict]:
    """补标题与片段文本：向量命中带 chunk 文本，关键词命中带纪要正文。"""
    out: list[dict] = []
    for s in sources:
        task_id = s.get("task_id") or s.get("minute_id") or ""
        title = s.get("title") or ""
        text = s.get("text") or s.get("summary_md") or ""
        if (not title or not text) and task_id:
            m = db.get_minute(task_id, db_path=db_path) or {}
            title = title or m.get("title") or ""
            text = text or m.get("summary_md") or ""
        out.append(dict(s, title=title, snippet=(text or "").strip()))
    return out


def _generate_answer(question: str, sources: list[dict], model_alias: str | None) -> str:
    """用主模型生成带引用答案；LLM 不可用时回退为原始片段拼接。"""
    context_parts = []
    for i, s in enumerate(sources, 1):
        head = f"[来源{i}] {s.get('title') or '会议纪要'} (task_id={s.get('task_id') or s.get('minute_id')})"
        context_parts.append(f"{head}\n{s.get('snippet', '')}")
    context = "\n\n".join(context_parts)

    try:
        from app.summary import get_llm_provider
        alias = model_alias or config.MMA_LLM_ALIAS
        if alias == "extractive":
            alias = "v4-pro"
        llm = get_llm_provider(alias)
        return llm.chat(QA_SYSTEM_PROMPT, f"问题：{question}\n\n参考纪要片段：\n{context}")
    except Exception:  # noqa: BLE001 — 无密钥/网络异常回退为片段兜底
        return "（无法调用 LLM，以下为检索到的原始纪要片段）\n\n" + "\n\n".join(
            f"[来源{i}] {s.get('snippet', '')}" for i, s in enumerate(sources, 1))


def answer(question: str, user_id: str | None, top_k: int | None = None,
           model_alias: str | None = None, db_path=None) -> dict:
    """检索问答入口。返回 {answer, sources, mode, degraded}。"""
    top_k = top_k or config.MMA_RAG_TOP_K
    sources: list[dict] = []
    mode = "vector"

    if embedding_enabled():
        provider = get_embedding_provider()
        try:
            qvec = provider.embed([question])[0]
            sources = retrieve(qvec, user_id, top_k, db_path=db_path)
        except Exception:  # noqa: BLE001 — embedding 异常回退关键词
            sources = []

    if not sources:
        sources = keyword_search(question, user_id, top_k, db_path=db_path)
        mode = "keyword" if sources else "disabled"

    if not sources:
        return {
            "answer": "（未启用：暂无可检索的纪要，或未配置 embedding / 数据库。上传并生成纪要后即可提问。）",
            "sources": [], "mode": "disabled", "degraded": True,
        }

    sources = _enrich_sources(sources, db_path=db_path)
    answer_md = _generate_answer(question, sources, model_alias)

    source_list = [{
        "task_id": s.get("task_id") or s.get("minute_id"),
        "title": s.get("title") or "",
        "chunk_index": s.get("chunk_index"),
        "snippet": (s.get("snippet") or "")[:200],
        "similarity": s.get("similarity"),
    } for s in sources]

    return {"answer": answer_md, "sources": source_list, "mode": mode,
            "degraded": mode != "vector"}
