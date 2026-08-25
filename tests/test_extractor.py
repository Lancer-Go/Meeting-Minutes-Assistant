"""extractor 模块（M2 行动项抽取）单元测试。"""
import pytest

from app.asr import Segment, Transcript
from app.extractor import (
    DeepSeekExtractor,
    RuleExtractor,
    get_extractor_provider,
    has_cloud_credentials,
)


def make_transcript(text: str) -> Transcript:
    return Transcript(segments=[Segment(0.0, 1.0, text)], text=text)


def test_rule_extractor_actions():
    text = "张三负责跟进客户需求，截止本周五。\n我们决定了上线时间。"
    result = RuleExtractor().extract(make_transcript(text))
    assert len(result.actions) >= 1
    assert result.actions[0].owner in ("张三", "待定")
    assert len(result.decisions) >= 1


def test_rule_extractor_empty():
    result = RuleExtractor().extract(Transcript())
    assert result.actions == []
    assert result.decisions == []


def test_deepseek_requires_key(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    with pytest.raises(RuntimeError):
        DeepSeekExtractor()


def test_deepseek_default_model(monkeypatch):
    from app import config
    assert config.DEEPSEEK_MODEL == "deepseek-v4-pro"
    e = DeepSeekExtractor(api_key="fake-key")
    assert e.model == "deepseek-v4-pro"


def test_get_extractor_provider():
    assert get_extractor_provider("rule").name == "rule"


def test_get_unknown_extractor():
    with pytest.raises(ValueError):
        get_extractor_provider("nope")


def test_has_cloud_credentials_rule():
    assert has_cloud_credentials("rule") is True


def test_has_cloud_credentials_deepseek(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "key")
    assert has_cloud_credentials("deepseek") is True
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    assert has_cloud_credentials("deepseek") is False


def test_deepseek_extract_parses_tool_calls(monkeypatch):
    """mock OpenAI 响应，验证 tool_calls 解析为结构化对象。"""
    class FakeFunc:
        name = "extract_actions"
        arguments = '{"actions": [{"description": "做A", "owner": "李四", "due": "下周"}]}'

    class FakeMsg:
        tool_calls = [type("C", (), {"function": FakeFunc()})()]

    class FakeResp:
        choices = [type("C", (), {"message": FakeMsg()})()]

    class FakeCompletions:
        def create(self, **kw):
            return FakeResp()

    class FakeClient:
        chat = type("C", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("openai.OpenAI", lambda *a, **kw: FakeClient())
    e = DeepSeekExtractor(api_key="fake-key")
    result = e.extract(make_transcript("任意转写"))
    assert len(result.actions) == 1
    assert result.actions[0].owner == "李四"
    assert result.actions[0].due == "下周"
