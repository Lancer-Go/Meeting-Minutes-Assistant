"""FastAPI 应用集成测试（校验、任务创建、状态查询）。"""
import struct
import wave

from fastapi.testclient import TestClient

from app.main import app


def _make_wav(path, seconds=1):
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<h", 0) * 16000 * seconds)


def test_health(tmp_data_dir):
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_upload_reject_format(tmp_data_dir, monkeypatch):
    monkeypatch.setattr("app.main.run_task", lambda task_id: None)
    with TestClient(app) as client:
        r = client.post("/api/tasks",
                        files={"file": ("evil.exe", b"xxx", "application/octet-stream")})
        assert r.status_code == 400


def test_upload_empty_file(tmp_data_dir, monkeypatch):
    monkeypatch.setattr("app.main.run_task", lambda task_id: None)
    with TestClient(app) as client:
        r = client.post("/api/tasks", files={"file": ("a.wav", b"", "audio/wav")})
        assert r.status_code == 400


def test_upload_ok_and_query(tmp_data_dir, monkeypatch, tmp_path):
    monkeypatch.setattr("app.main.run_task", lambda task_id: None)
    wav = tmp_path / "meeting.wav"
    _make_wav(wav, seconds=1)
    with TestClient(app) as client:
        with open(wav, "rb") as f:
            r = client.post("/api/tasks",
                            files={"file": ("meeting.wav", f.read(), "audio/wav")})
        assert r.status_code == 202
        data = r.json()
        assert data["id"]
        assert data["status"] == "pending"
        assert data["source_file"] == "meeting.wav"

        r2 = client.get(f"/api/tasks/{data['id']}")
        assert r2.status_code == 200
        assert r2.json()["status"] == "pending"


def test_get_task_missing(tmp_data_dir):
    with TestClient(app) as client:
        r = client.get("/api/tasks/nonexistent")
        assert r.status_code == 404


def test_minute_not_ready(tmp_data_dir):
    from app import db
    db.init_db()
    db.create_task("t1", "a.mp4", "")
    with TestClient(app) as client:
        r = client.get("/api/tasks/t1/minute")
        assert r.status_code == 404


def test_list_tasks(tmp_data_dir):
    with TestClient(app) as client:
        r = client.get("/api/tasks")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
