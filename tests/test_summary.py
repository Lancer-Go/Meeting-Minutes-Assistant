"""summary 模块单元测试。"""
import pytest

from app.asr import Segment, Transcript
from app.summary import (
    ExtractiveLLM,
    OpenAILikeLLM,
    get_llm_provider,
    has_cloud_credentials,
)


def make_transcript():
    segs = [Segment(i * 60.0, i * 60 + 30, f"讨论第{i}点") for i in range(5)]
    return Transcript(segments=segs, text="".join(s.text for s in segs),
                      provider="whisper", model="base")


def test_extractive_summarize():
    md = ExtractiveLLM().summarize(make_transcript())
    assert "会议纪要" in md
    assert "讨论第0点" in md
    assert "全文转写" in md


def test_extractive_empty():
    md = ExtractiveLLM().summarize(Transcript())
    assert "会议纪要" in md


def test_openai_like_requires_key():
    with pytest.raises(RuntimeError):
        OpenAILikeLLM("test", "http://x", "", "m")


def test_summarize_single_shot_long(monkeypatch):
    """长文本（超过旧 12000 阈值）仍单次调用 _chat，无分块/截断。"""
    llm = OpenAILikeLLM("test", "http://x", "fake-key", "m")
    long_text = "会议讨论内容" * 4000  # 24000 字符，超过旧阈值
    calls = []

    def fake_chat(system, user):
        calls.append(user)
        return "纪要正文"

    monkeypatch.setattr(llm, "_chat", fake_chat)
    md = llm.summarize(Transcript(text=long_text, provider="whisper", model="base"))
    assert md == "纪要正文"
    assert len(calls) == 1
    assert long_text in calls[0]  # 全文完整传入，未被截断/切块


def test_get_llm_provider():
    assert get_llm_provider("extractive").name == "extractive"


def test_get_unknown_llm():
    with pytest.raises(ValueError):
        get_llm_provider("nope")


def test_has_cloud_credentials_local():
    assert has_cloud_credentials("extractive") is True


def test_deepseek_requires_credentials(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    assert has_cloud_credentials("deepseek") is False
    with pytest.raises(RuntimeError):
        get_llm_provider("deepseek")


def test_deepseek_default_model():
    from app import config
    from app.summary import DeepSeekLLM
    assert config.DEEPSEEK_MODEL == "deepseek-v4-pro"
    assert DeepSeekLLM(api_key="fake-key").model == "deepseek-v4-pro"
