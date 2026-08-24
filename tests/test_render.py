"""render 模块单元测试。"""
from app.render import build_minutes_md


def test_build_minutes_md_basic():
    md = build_minutes_md({"title": "测试会议"}, "# 正文\n内容")
    assert md.startswith("# 测试会议")
    assert "## 会议信息" in md
    assert "# 正文" in md


def test_build_minutes_md_full_meta():
    meta = {
        "title": "T",
        "created_at": "2026-08-24T00:00:00",
        "duration_min": 30.0,
        "asr": "tencent / 16k_zh",
    }
    md = build_minutes_md(meta, "body")
    assert "2026-08-24" in md
    assert "30.0 分钟" in md
    assert "tencent / 16k_zh" in md
    assert md.strip().endswith("body")


def test_build_minutes_md_default_title():
    md = build_minutes_md({}, "body")
    assert md.startswith("# 会议纪要")
