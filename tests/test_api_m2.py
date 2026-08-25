"""FastAPI M2 接口（编辑 / 批注 / 历史检索）集成测试。"""
from fastapi.testclient import TestClient

from app import db
from app.main import app


def _mk_task(task_id, title="T"):
    db.init_db()
    db.create_task(task_id, "a.mp4", "")
    db.save_minute(task_id, title=title, summary_md="原稿", structured_json="{}")


def test_put_minute_missing_task(tmp_data_dir):
    with TestClient(app) as client:
        r = client.put("/api/tasks/nonexistent/minute", json={"markdown": "x"})
        assert r.status_code == 404


def test_put_minute_no_generated(tmp_data_dir):
    db.init_db()
    db.create_task("t2", "a.mp4", "")
    with TestClient(app) as client:
        r = client.put("/api/tasks/t2/minute", json={"markdown": "x"})
        assert r.status_code == 404  # 纪要尚未生成


def test_put_and_get_edited_minute(tmp_data_dir):
    _mk_task("t1")
    with TestClient(app) as client:
        r = client.put("/api/tasks/t1/minute", json={"markdown": "# 改后内容"})
        assert r.status_code == 200
        assert r.json()["edited"] is True
        r2 = client.get("/api/tasks/t1/minute")
        assert r2.status_code == 200
        assert "# 改后内容" in r2.text


def test_put_minute_empty_markdown(tmp_data_dir):
    _mk_task("t1")
    with TestClient(app) as client:
        r = client.put("/api/tasks/t1/minute", json={"markdown": "   "})
        assert r.status_code == 400


def test_comments_crud(tmp_data_dir):
    _mk_task("t1")
    with TestClient(app) as client:
        r = client.post("/api/tasks/t1/comments",
                        json={"text": "这里要改", "author": "张三", "quote": "原文"})
        assert r.status_code == 201
        cid = r.json()["id"]
        r2 = client.get("/api/tasks/t1/comments")
        assert len(r2.json()) == 1
        r3 = client.delete(f"/api/tasks/t1/comments/{cid}")
        assert r3.status_code == 200
        assert client.get("/api/tasks/t1/comments").json() == []


def test_add_comment_empty(tmp_data_dir):
    _mk_task("t1")
    with TestClient(app) as client:
        r = client.post("/api/tasks/t1/comments", json={"text": ""})
        assert r.status_code == 400


def test_search_minutes(tmp_data_dir):
    _mk_task("t1", title="产品评审")
    _mk_task("t2", title="技术例会")
    with TestClient(app) as client:
        r = client.get("/api/minutes", params={"q": "产品"})
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["title"] == "产品评审"

    with TestClient(app) as client:
        r = client.get("/api/minutes")
        assert len(r.json()) == 2


def test_search_minutes_empty_result(tmp_data_dir):
    _mk_task("t1", title="产品评审")
    with TestClient(app) as client:
        r = client.get("/api/minutes", params={"q": "不存在"})
        assert r.status_code == 200
        assert r.json() == []
