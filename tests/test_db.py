"""db 模块（SQLite 任务模型与状态机）单元测试。"""
import pytest

from app import db


@pytest.fixture()
def dbfile(tmp_path):
    p = tmp_path / "test.db"
    db.init_db(p)
    return p


def test_create_and_get(dbfile):
    db.create_task("t1", "meeting.mp4", "stored/path", db_path=dbfile)
    t = db.get_task("t1", db_path=dbfile)
    assert t["id"] == "t1"
    assert t["source_file"] == "meeting.mp4"
    assert t["status"] == db.PENDING
    assert t["progress"] == 0


def test_state_machine_happy_path(dbfile):
    db.create_task("t1", "a", "", db_path=dbfile)
    db.set_status("t1", db.RUNNING, db_path=dbfile)
    assert db.get_task("t1", db_path=dbfile)["status"] == db.RUNNING
    db.set_status("t1", db.SUCCEEDED, db_path=dbfile)
    t = db.get_task("t1", db_path=dbfile)
    assert t["status"] == db.SUCCEEDED
    assert t["started_at"] is not None
    assert t["finished_at"] is not None


def test_pending_to_failed(dbfile):
    db.create_task("t1", "a", "", db_path=dbfile)
    db.set_status("t1", db.FAILED, db_path=dbfile)
    assert db.get_task("t1", db_path=dbfile)["status"] == db.FAILED


def test_illegal_transition(dbfile):
    db.create_task("t1", "a", "", db_path=dbfile)
    db.set_status("t1", db.RUNNING, db_path=dbfile)
    db.set_status("t1", db.SUCCEEDED, db_path=dbfile)
    with pytest.raises(ValueError):
        db.set_status("t1", db.RUNNING, db_path=dbfile)  # succeeded → running 非法


def test_progress_clamp(dbfile):
    db.create_task("t1", "a", "", db_path=dbfile)
    db.set_progress("t1", 50, db_path=dbfile)
    assert db.get_task("t1", db_path=dbfile)["progress"] == 50
    db.set_progress("t1", 150, db_path=dbfile)
    assert db.get_task("t1", db_path=dbfile)["progress"] == 100
    db.set_progress("t1", -10, db_path=dbfile)
    assert db.get_task("t1", db_path=dbfile)["progress"] == 0


def test_set_progress_message(dbfile):
    db.create_task("t1", "a", "", db_path=dbfile)
    db.set_progress("t1", 48, "语音转写：第 12/48 段已完成", db_path=dbfile)
    t = db.get_task("t1", db_path=dbfile)
    assert t["progress"] == 48
    assert t["progress_message"] == "语音转写：第 12/48 段已完成"


def test_update_fields(dbfile):
    db.create_task("t1", "a", "", db_path=dbfile)
    db.update_fields("t1", db_path=dbfile, error="boom", cost_rmb=0.5,
                     transcript_chars=123)
    t = db.get_task("t1", db_path=dbfile)
    assert t["error"] == "boom"
    assert t["cost_rmb"] == 0.5
    assert t["transcript_chars"] == 123


def test_update_fields_ignores_unknown(dbfile):
    db.create_task("t1", "a", "", db_path=dbfile)
    db.update_fields("t1", db_path=dbfile, not_a_field=1)
    assert "not_a_field" not in db.get_task("t1", db_path=dbfile)


def test_get_missing(dbfile):
    assert db.get_task("nope", db_path=dbfile) is None


def test_list_tasks(dbfile):
    db.create_task("t1", "a", "", db_path=dbfile)
    db.create_task("t2", "b", "", db_path=dbfile)
    tasks = db.list_tasks(db_path=dbfile)
    assert len(tasks) == 2


def test_set_status_missing(dbfile):
    with pytest.raises(KeyError):
        db.set_status("nope", db.RUNNING, db_path=dbfile)
