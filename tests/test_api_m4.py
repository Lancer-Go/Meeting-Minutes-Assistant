"""M4 · /api/qa 与 /api/tasks/{id}/regen 接口集成测试（TG-1/TG-3）。"""
import json

from fastapi.testclient import TestClient

from app import config, db
from app.main import app


# --------------------------------------------------------------------------- /api/qa
def test_qa_empty_question(tmp_data_dir):
    with TestClient(app) as client:
        r = client.post("/api/qa", json={"question": ""})
        assert r.status_code == 400


def test_qa_keyword_mode(tmp_data_dir, monkeypatch):
    """无 embedding 密钥 → 关键词检索兜底，返回带来源的答案。"""
    db.init_db()
    db.save_minute("t1", title="产品评审", summary_md="产品评审决定上线 2.0",
                   structured_json="{}", user_id=None)
    monkeypatch.setattr("app.rag._generate_answer", lambda q, s, a: "答案")
    with TestClient(app) as client:
        r = client.post("/api/qa", json={"question": "产品评审"})
        assert r.status_code == 200
        data = r.json()
        assert data["mode"] == "keyword"
        assert data["answer"]
        assert data["sources"][0]["task_id"] == "t1"


def test_qa_disabled(tmp_data_dir):
    db.init_db()
    with TestClient(app) as client:
        r = client.post("/api/qa", json={"question": "无纪要时的提问"})
        assert r.status_code == 200
        assert r.json()["mode"] == "disabled"


# --------------------------------------------------------------------------- /api/tasks/{id}/regen
def _mk_succeeded_task(task_id):
    db.init_db()
    db.create_task(task_id, "meeting.mp4", "", user_id=None)
    db.set_status(task_id, "running")
    db.set_status(task_id, "succeeded")
    tr = config.TASK_DIR / task_id / "transcript.json"
    tr.parent.mkdir(parents=True, exist_ok=True)
    tr.write_text(json.dumps({
        "provider": "tencent", "model": "16k_zh",
        "segments": [{"start": 0.0, "end": 1.0, "text": "决定上线", "speaker": "S1"}],
        "text": "决定上线", "speakers": ["S1"],
    }), encoding="utf-8")


def test_regen_missing_task(tmp_data_dir):
    with TestClient(app) as client:
        r = client.post("/api/tasks/nope/regen", json={})
        assert r.status_code == 404


def test_regen_not_succeeded(tmp_data_dir):
    db.init_db()
    db.create_task("t-pending", "m.mp4", "", user_id=None)
    with TestClient(app) as client:
        r = client.post("/api/tasks/t-pending/regen", json={})
        assert r.status_code == 400


def test_regen_success(tmp_data_dir, monkeypatch):
    _mk_succeeded_task("t-regen")
    from app.extractor import RuleExtractor
    from app.summary import ExtractiveLLM
    monkeypatch.setattr("app.summary.get_llm_provider", lambda alias: ExtractiveLLM())
    monkeypatch.setattr("app.extractor.get_extractor_provider", lambda alias: RuleExtractor())

    with TestClient(app) as client:
        r = client.post("/api/tasks/t-regen/regen", json={"template": "brief"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("task_id") == "t-regen" or data.get("template") == "brief"
    # 重生成后纪要已落库、文件已更新
    assert db.get_minute("t-regen") is not None
    assert (config.TASK_DIR / "t-regen" / "minutes.md").exists()
    assert (config.TASK_DIR / "t-regen" / "structured_minute.json").exists()
