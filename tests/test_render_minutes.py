"""render 模块（M2 Jinja2 三模板）单元测试。"""
import pytest

from app.render import DEFAULT_TEMPLATE, TEMPLATES, render_minutes
from app.schemas import (
    ActionItem,
    Decision,
    OpenQuestion,
    Speaker,
    StructuredMinute,
)


def make_minute() -> StructuredMinute:
    return StructuredMinute(
        title="测试会议",
        summary_md="讨论了若干要点。",
        decisions=[Decision(conclusion="上线方案 A", basis="成本更低")],
        actions=[ActionItem(description="实现新功能", owner="张三", due="下周五",
                            priority="高", status="进行中")],
        open_questions=[OpenQuestion(question="预算待确认", follow_up="财务复核")],
        speakers=[Speaker(name="S1", role="主持人"), Speaker(name="S2", role="汇报人")],
    )


def test_three_templates_render():
    m = make_minute()
    meta = {"duration_min": 30.0, "asr": "tencent / 16k_zh"}
    out = {name: render_minutes(m, name, meta, "[00:00.00] 你好") for name in TEMPLATES}
    assert set(out) == {"standard", "brief", "detailed"}

    assert "上线方案 A" in out["standard"]
    assert "行动项" in out["standard"]
    assert "未决问题" in out["standard"]

    # 精简模板：含决议与行动项，但不含讨论要点 / 未决问题标题
    assert "上线方案 A" in out["brief"]
    assert "行动项" in out["brief"]
    assert "讨论要点" not in out["brief"]
    assert "未决问题" not in out["brief"]

    # 详细模板：含说话人 / 角色 + 全文转写附录
    assert "说话人" in out["detailed"]
    assert "汇报人" in out["detailed"]
    assert "全文转写" in out["detailed"]
    assert "你好" in out["detailed"]


def test_standard_action_table_fields():
    m = make_minute()
    md = render_minutes(m, "standard")
    assert "张三" in md
    assert "下周五" in md
    assert "高" in md
    assert "进行中" in md


def test_unknown_template_raises():
    with pytest.raises(ValueError):
        render_minutes(make_minute(), "nope")


def test_default_template():
    assert DEFAULT_TEMPLATE == "standard"


def test_empty_minute_renders():
    md = render_minutes(StructuredMinute(title="空"))
    assert "空" in md
    assert "（无）" in md
