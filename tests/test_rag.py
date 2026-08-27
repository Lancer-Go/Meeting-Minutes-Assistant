"""M4 · rag 模块单元测试（TG-3）。"""
import pytest

from app import db, rag


def test_cosine():
    assert rag._cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert rag._cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert rag._cosine([], [1]) == 0.0
    assert rag._cosine([1, 0], [1]) == 0.0  # 维度不一致


def test_parse_vector():
    assert rag._parse_vector("[0.1, 0.2]") == [0.1, 0.2]
    assert rag._parse_vector("") == []
    assert rag._parse_vector("not-json") == []


def _seed(tmp_data_dir):
    db.init_db()
    db.save_minute("t1", title="支付评审", summary_md="支付压测由张三负责",
                   structured_json="{}", user_id="u1")
    db.save_minute("t2", title="登录优化", summary_md="登录缓慢待修复",
                   structured_json="{}", user_id="u2")
    db.replace_embeddings("t1", "u1", [{"text": "支付压测", "vector": [1.0, 0.0, 0.0]}])
    db.replace_embeddings("t2", "u2", [{"text": "登录缓慢", "vector": [0.0, 1.0, 0.0]}])


def test_retrieve_ordering_and_isolation(tmp_data_dir):
    _seed(tmp_data_dir)
    hits = rag.retrieve([1.0, 0.0, 0.0], "u1", top_k=5)
    assert hits and hits[0]["task_id"] == "t1"
    assert all(h["user_id"] == "u1" for h in hits)  # 越权隔离


def test_retrieve_empty_user(tmp_data_dir):
    _seed(tmp_data_dir)
    assert rag.retrieve([1.0, 0.0, 0.0], "nobody", top_k=5) == []


def test_keyword_search(tmp_data_dir):
    _seed(tmp_data_dir)
    hits = rag.keyword_search("支付", "u1", top_k=5)
    assert hits and hits[0]["task_id"] == "t1"


def test_answer_disabled(tmp_data_dir):
    db.init_db()
    res = rag.answer("随便问", "u1", top_k=3)
    assert res["mode"] == "disabled"
    assert res["degraded"] is True


def test_answer_keyword_mode(tmp_data_dir, monkeypatch):
    _seed(tmp_data_dir)
    monkeypatch.setattr("app.rag._generate_answer", lambda q, s, a: "答案")
    res = rag.answer("支付", "u1", top_k=3)
    assert res["mode"] == "keyword"
    assert res["sources"]
    assert res["sources"][0]["task_id"] == "t1"


def test_answer_vector_mode(tmp_data_dir, monkeypatch):
    _seed(tmp_data_dir)

    class FakeEmbedder:
        def embed(self, texts):
            return [[1.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr("app.rag.embedding_enabled", lambda: True)
    monkeypatch.setattr("app.rag.get_embedding_provider", lambda: FakeEmbedder())
    monkeypatch.setattr("app.rag._generate_answer", lambda q, s, a: "答案：张三负责")

    res = rag.answer("谁负责支付", "u1", top_k=3)
    assert res["mode"] == "vector"
    assert res["degraded"] is False
    assert res["sources"][0]["task_id"] == "t1"
