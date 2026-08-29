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

    # 标准 / 精简模板：也含说话人 / 角色（M2 修复：默认纪要应可见角色识别）
    assert "说话人" in out["standard"]
    assert "汇报人" in out["standard"]
    assert "说话人" in out["brief"]
    assert "汇报人" in out["brief"]

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


def test_standard_no_duplicate_sections():
    """正文（summary_md）不含决议/行动项时，标准模板各结构化区块只渲染一次，避免重复。"""
    m = make_minute()
    m.summary_md = "## 会议主题与基本信息\n讨论 AI 工具选型。\n\n## 讨论要点\n- 要点一\n- 要点二"
    md = render_minutes(m, "standard")
    assert md.count("## 核心决议") == 1
    assert md.count("## 行动项") == 1
    assert md.count("## 未决问题") == 1
    assert md.count("## 讨论要点") == 1  # 仅来自 summary_md 自身


def test_unknown_template_raises():
    with pytest.raises(ValueError):
        render_minutes(make_minute(), "nope")


def test_default_template():
    assert DEFAULT_TEMPLATE == "standard"


def test_empty_minute_renders():
    md = render_minutes(StructuredMinute(title="空"))
    assert "空" in md
    assert "（无）" in md
