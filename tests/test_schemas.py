"""schemas 模块（M2 结构化数据模型）单元测试。"""
from app.schemas import (
    ActionItem,
    Decision,
    OpenQuestion,
    Speaker,
    StructuredMinute,
    build_tool_schemas,
)


def test_action_item_defaults():
    a = ActionItem()
    assert a.priority == "中"
    assert a.status == "待办"
    assert a.owner == ""


def test_structured_minute_roundtrip():
    sm = StructuredMinute(
        title="T",
        summary_md="body",
        decisions=[Decision(conclusion="c1", basis="b1")],
        actions=[ActionItem(description="d1", owner="张三", due="明天")],
        open_questions=[OpenQuestion(question="q1", follow_up="f1")],
        speakers=[Speaker(name="S1", role="主持人")],
    )
    d = sm.to_dict()
    assert d["title"] == "T"
    assert d["decisions"][0]["conclusion"] == "c1"
    assert d["actions"][0]["owner"] == "张三"
    assert d["speakers"][0]["role"] == "主持人"

    sm2 = StructuredMinute.from_dict(d)
    assert sm2.actions[0].owner == "张三"
    assert sm2.speakers[0].role == "主持人"


def test_from_dict_empty():
    sm = StructuredMinute.from_dict({})
    assert sm.actions == []
    assert sm.decisions == []


def test_build_tool_schemas():
    tools = build_tool_schemas()
    names = [t["function"]["name"] for t in tools]
    assert names == ["extract_decisions", "extract_actions", "extract_questions"]
    for t in tools:
        assert t["type"] == "function"
        assert "parameters" in t["function"]
