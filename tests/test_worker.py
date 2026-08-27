"""worker 异步执行单元测试（mock pipeline）。"""
from app import db, worker


def _mk_task(task_id, stored):
    db.init_db()
    db.create_task(task_id, "meeting.wav", str(stored))


def test_run_task_success(tmp_data_dir, monkeypatch):
    _mk_task("t1", tmp_data_dir / "meeting.wav")
    (tmp_data_dir / "meeting.wav").write_bytes(b"x")
    monkeypatch.setattr(
        "app.worker.pipeline.run",
        lambda *a, **kw: {"audio_duration_min": 1.0, "transcript_chars": 10,
                          "total_cost_rmb": 0.01},
    )
    worker.run_task("t1")
    t = db.get_task("t1")
    assert t["status"] == db.SUCCEEDED
    assert t["cost_rmb"] == 0.01
    assert t["transcript_chars"] == 10
    assert t["progress"] == 100


def test_run_task_failure(tmp_data_dir, monkeypatch):
    monkeypatch.setattr("app.worker.time.sleep", lambda s: None)  # 跳过退避
    _mk_task("t2", tmp_data_dir / "meeting.wav")
    (tmp_data_dir / "meeting.wav").write_bytes(b"x")

    def boom(*a, **kw):
        raise RuntimeError("模拟失败")

    monkeypatch.setattr("app.worker.pipeline.run", boom)
    worker.run_task("t2")
    t = db.get_task("t2")
    assert t["status"] == db.FAILED
    assert "模拟失败" in t["error"]


def test_run_task_missing(tmp_data_dir):
    db.init_db()
    worker.run_task("nonexistent")  # 不应抛异常


def test_run_task_progress_callback(tmp_data_dir, monkeypatch):
    _mk_task("t3", tmp_data_dir / "meeting.wav")
    (tmp_data_dir / "meeting.wav").write_bytes(b"x")

    def fake_run(*a, progress_callback=None, **kw):
        progress_callback(50, "中间")
        return {"audio_duration_min": 1.0, "transcript_chars": 10, "total_cost_rmb": 0}

    monkeypatch.setattr("app.worker.pipeline.run", fake_run)
    worker.run_task("t3")
    t = db.get_task("t3")
    assert t["status"] == db.SUCCEEDED
