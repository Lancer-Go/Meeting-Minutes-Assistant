"""db 模块 M2 扩展（minutes / comments / search）单元测试。"""
import pytest

from app import db


@pytest.fixture()
def dbfile(tmp_path):
    p = tmp_path / "test.db"
    db.init_db(p)
    return p


def test_save_and_get_minute(dbfile):
    db.create_task("t1", "a.mp4", "", db_path=dbfile)
    db.save_minute("t1", title="T", summary_md="正文",
                   structured_json='{"actions": []}', db_path=dbfile)
    m = db.get_minute("t1", db_path=dbfile)
    assert m["title"] == "T"
    assert m["summary_md"] == "正文"
    assert m["template"] == "standard"


def test_update_minute_edited(dbfile):
    db.create_task("t1", "a.mp4", "", db_path=dbfile)
    db.save_minute("t1", title="T", summary_md="原稿", db_path=dbfile)
    db.update_minute_edited("t1", "改后", db_path=dbfile)
    m = db.get_minute("t1", db_path=dbfile)
    assert m["edited_md"] == "改后"


def test_update_minute_missing(dbfile):
    with pytest.raises(KeyError):
        db.update_minute_edited("nope", "x", db_path=dbfile)


def test_comments_crud(dbfile):
    db.create_task("t1", "a.mp4", "", db_path=dbfile)
    c = db.add_comment("t1", "这里要改", author="张三", quote="原文", db_path=dbfile)
    assert c["text"] == "这里要改"
    assert c["author"] == "张三"
    assert c["id"]

    comments = db.list_comments("t1", db_path=dbfile)
    assert len(comments) == 1
    assert db.delete_comment(c["id"], db_path=dbfile) is True
    assert db.list_comments("t1", db_path=dbfile) == []
    assert db.delete_comment(c["id"], db_path=dbfile) is False


def test_search_minutes_by_keyword(dbfile):
    db.create_task("t1", "a.mp4", "", db_path=dbfile)
    db.create_task("t2", "b.mp4", "", db_path=dbfile)
    db.save_minute("t1", title="产品评审", summary_md="讨论预算", db_path=dbfile)
    db.save_minute("t2", title="技术例会", summary_md="讨论架构", db_path=dbfile)

    assert len(db.search_minutes(q="预算", db_path=dbfile)) == 1
    assert len(db.search_minutes(q="讨论", db_path=dbfile)) == 2
    assert len(db.search_minutes(q="不存在", db_path=dbfile)) == 0


def test_search_minutes_by_topic(dbfile):
    db.create_task("t1", "a.mp4", "", db_path=dbfile)
    db.save_minute("t1", title="产品评审会", db_path=dbfile)
    assert len(db.search_minutes(topic="产品", db_path=dbfile)) == 1
    assert len(db.search_minutes(topic="技术", db_path=dbfile)) == 0


def test_list_minutes(dbfile):
    db.create_task("t1", "a.mp4", "", db_path=dbfile)
    db.save_minute("t1", title="T", db_path=dbfile)
    assert len(db.list_minutes(db_path=dbfile)) == 1


def test_save_minute_preserves_edited(dbfile):
    db.create_task("t1", "a.mp4", "", db_path=dbfile)
    db.save_minute("t1", title="T", summary_md="原稿", edited_md="改后", db_path=dbfile)
    # 再次 save 不带 edited_md，应保留原 edited_md
    db.save_minute("t1", title="T2", summary_md="新稿", db_path=dbfile)
    m = db.get_minute("t1", db_path=dbfile)
    assert m["edited_md"] == "改后"
    assert m["title"] == "T2"
