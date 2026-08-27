"""M4 · embedding 模块单元测试（TG-2）。"""
from app.embedding import (
    OpenAICompatEmbedding,
    chunk_text,
    embedding_enabled,
    get_embedding_provider,
    index_minute,
)


def test_chunk_text_basic():
    chunks = chunk_text("abcdefghij", size=4, overlap=0)
    assert chunks == ["abcd", "efgh", "ij"]


def test_chunk_text_overlap():
    chunks = chunk_text("abcdef", size=4, overlap=2)
    assert chunks == ["abcd", "cdef", "ef"]


def test_chunk_text_short_and_empty():
    assert chunk_text("abc", size=100) == ["abc"]
    assert chunk_text("", size=100) == []
    assert chunk_text("   ", size=100) == []


def test_embedding_disabled_by_default(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MMA_EMBEDDING_BASE_URL", "")
    monkeypatch.setattr(config, "MMA_EMBEDDING_API_KEY", "")
    assert embedding_enabled() is False
    assert get_embedding_provider() is None


def test_embedding_enabled(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MMA_EMBEDDING_BASE_URL", "https://api.x/v1")
    monkeypatch.setattr(config, "MMA_EMBEDDING_API_KEY", "sk-test")
    assert embedding_enabled() is True
    assert get_embedding_provider() is not None


def test_openai_compat_embed(monkeypatch):
    class FakeEmbedding:
        index = 0
        embedding = [0.1, 0.2, 0.3]

    class FakeResp:
        data = [FakeEmbedding()]

    class FakeEmbeddings:
        def create(self, **kw):
            assert kw["model"] == "bge-m3"
            return FakeResp()

    class FakeClient:
        embeddings = FakeEmbeddings()

    monkeypatch.setattr("openai.OpenAI", lambda *a, **kw: FakeClient())
    p = OpenAICompatEmbedding("https://api.x/v1", "sk-test", "bge-m3", dim=3)
    assert p.embed(["你好"]) == [[0.1, 0.2, 0.3]]


def test_openai_compat_requires_key():
    import pytest
    with pytest.raises(RuntimeError):
        OpenAICompatEmbedding("", "", "bge-m3")


def test_index_minute_without_provider(tmp_data_dir, monkeypatch):
    """无 embedding 密钥时 index_minute 返回 0（不阻断）。"""
    from app import config
    monkeypatch.setattr(config, "MMA_EMBEDDING_BASE_URL", "")
    monkeypatch.setattr(config, "MMA_EMBEDDING_API_KEY", "")
    assert index_minute("t1", "u1", "会议纪要内容") == 0


def test_index_minute_with_provider(tmp_data_dir, monkeypatch):
    from app import config, db

    class FakeProvider:
        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(config, "MMA_EMBEDDING_BASE_URL", "https://api.x/v1")
    monkeypatch.setattr(config, "MMA_EMBEDDING_API_KEY", "sk-test")
    monkeypatch.setattr("app.embedding.get_embedding_provider", lambda: FakeProvider())

    db.init_db()
    n = index_minute("t1", "u1", "这是会议纪要正文，用于向量化测试。" * 20)
    assert n >= 1
    assert db.count_embeddings("t1") == n
