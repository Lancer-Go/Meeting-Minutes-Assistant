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


def test_speaker_to_str_keeps_zero():
    from app.asr import _speaker_to_str
    # SpeakerId 为 int，0 是合法说话人，不能被 `or ""` 丢弃
    assert _speaker_to_str(0) == "0"
    assert _speaker_to_str(1) == "1"
    assert _speaker_to_str(None) == ""
    assert _speaker_to_str("") == ""
    assert _speaker_to_str("0") == "0"


def test_tencent_build_request_url_mode():
    from app.asr import TencentASR
    p = TencentASR(secret_id="id", secret_key="key")
    req = p._build_request(source_type=0, url="https://example.com/a.wav")
    assert req.SourceType == 0
    assert req.Url == "https://example.com/a.wav"


def test_tencent_build_request_base64_sets_data(tmp_path):
    from app.asr import TencentASR
    p = TencentASR(secret_id="id", secret_key="key")
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFFxxxx")
    req = p._build_request(source_type=1, wav=wav)
    assert req.SourceType == 1
    assert req.Data  # base64 非空
    assert req.DataLen == 8


def test_tencent_transcribe_url_mode(monkeypatch):
    from app.asr import TencentASR
    p = TencentASR(secret_id="id", secret_key="key")
    calls = []
    monkeypatch.setattr(p, "_recognize_url",
                        lambda url: calls.append(url) or [Segment(0, 1, "你好", speaker="0")])
    t = p.transcribe("unused.wav", url="https://example.com/a.wav")
    assert calls == ["https://example.com/a.wav"]
    assert t.segments[0].speaker == "0"
    assert t.text == "你好"


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


def test_tencent_slice_progress(monkeypatch, tmp_path):
    from app import audio
    from app.asr import TencentASR

    p = TencentASR(secret_id="id", secret_key="key", chunk_seconds=100)
    fake_chunks = [tmp_path / f"c{i}.wav" for i in range(3)]
    for c in fake_chunks:
        c.write_bytes(b"RIFFxxxx")
    monkeypatch.setattr(audio, "get_duration", lambda wav: 350.0)  # > chunk_seconds+5 → 切片
    monkeypatch.setattr(audio, "split_wav", lambda wav, sec, out: fake_chunks)
    monkeypatch.setattr(p, "_recognize_chunk", lambda c: [Segment(0.0, 1.0, "你好")])

    progress = []
    t = p.transcribe(tmp_path / "in.wav",
                     progress_callback=lambda d, total: progress.append((d, total)))
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert t.segments[0].text == "你好"
