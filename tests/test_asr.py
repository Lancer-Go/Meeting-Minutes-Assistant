"""asr 模块单元测试（数据结构 / Provider 工厂 / 凭证判断）。"""
import pytest

from app.asr import Segment, Transcript, get_asr_provider, has_cloud_credentials


def test_timestamped_text():
    t = Transcript(segments=[Segment(0.0, 2.0, "你好"),
                             Segment(65.5, 70.0, "世界")], text="你好世界")
    out = t.to_timestamped_text()
    assert "[00:00.00] 你好" in out
    assert "[01:05.50] 世界" in out


def test_to_dict():
    t = Transcript(segments=[Segment(1.0, 2.0, "x")], text="x",
                   provider="whisper", model="base")
    d = t.to_dict()
    assert d["provider"] == "whisper"
    assert d["model"] == "base"
    assert d["char_count"] == 1
    assert d["segments"][0]["start"] == 1.0


def test_char_count():
    assert Transcript(text="你好世界").char_count == 4


def test_get_provider_whisper():
    assert get_asr_provider("whisper").name == "whisper"


def test_get_unknown_provider():
    with pytest.raises(ValueError):
        get_asr_provider("nope")


def test_has_cloud_credentials_local():
    assert has_cloud_credentials("whisper") is True


def test_tencent_requires_credentials(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "TENCENT_SECRET_ID", "")
    monkeypatch.setattr(config, "TENCENT_SECRET_KEY", "")
    assert has_cloud_credentials("tencent") is False
    with pytest.raises(RuntimeError):
        get_asr_provider("tencent")


def test_has_cloud_credentials_aliyun_iflytek(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "ALIYUN_APP_KEY", "")
    monkeypatch.setattr(config, "ALIYUN_ACCESS_KEY_ID", "")
    monkeypatch.setattr(config, "ALIYUN_ACCESS_KEY_SECRET", "")
    assert has_cloud_credentials("aliyun") is False
    monkeypatch.setattr(config, "XFYUN_APP_ID", "")
    monkeypatch.setattr(config, "XFYUN_API_KEY", "")
    monkeypatch.setattr(config, "XFYUN_API_SECRET", "")
    assert has_cloud_credentials("iflytek") is False


def test_has_cloud_credentials_tencent_configured(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "TENCENT_SECRET_ID", "id")
    monkeypatch.setattr(config, "TENCENT_SECRET_KEY", "key")
    assert has_cloud_credentials("tencent") is True


def test_tencent_constructs_with_credentials(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "TENCENT_SECRET_ID", "id")
    monkeypatch.setattr(config, "TENCENT_SECRET_KEY", "key")
    p = get_asr_provider("tencent")
    assert p.name == "tencent"
    assert p.engine == "16k_zh"


def test_aliyun_requires_credentials(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "ALIYUN_APP_KEY", "")
    monkeypatch.setattr(config, "ALIYUN_ACCESS_KEY_ID", "")
    monkeypatch.setattr(config, "ALIYUN_ACCESS_KEY_SECRET", "")
    with pytest.raises(RuntimeError):
        get_asr_provider("aliyun")


def test_iflytek_requires_credentials(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "XFYUN_APP_ID", "")
    monkeypatch.setattr(config, "XFYUN_API_KEY", "")
    monkeypatch.setattr(config, "XFYUN_API_SECRET", "")
    with pytest.raises(RuntimeError):
        get_asr_provider("iflytek")
