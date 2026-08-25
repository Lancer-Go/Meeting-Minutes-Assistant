"""pipeline 编排集成测试（真实 FFmpeg + mock ASR + 离线纪要）。"""
import struct
import wave
from pathlib import Path

from app import pipeline
from app.asr import Segment, Transcript
from app.extractor import RuleExtractor


class FakeASR:
    name = "whisper"
    model = "fake"

    def transcribe(self, wav, progress_callback=None):
        segs = [Segment(0.0, 1.0, "测试内容")]
        return Transcript(segments=segs, text="测试内容", provider=self.name,
                          model=self.model, elapsed_s=0.1)


def make_wav(path, seconds=1.0):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<h", 0) * int(16000 * seconds))
    return path


def _offline(monkeypatch):
    """mock ASR + 抽取器，保证测试全程离线（不触达云端）。"""
    monkeypatch.setattr("app.pipeline.get_asr_provider", lambda name, **kw: FakeASR())
    monkeypatch.setattr("app.pipeline.get_extractor_provider",
                        lambda name, **kw: RuleExtractor())


def test_run_offline(tmp_path, monkeypatch):
    _offline(monkeypatch)
    src = make_wav(tmp_path / "in.wav", 1.0)
    out = tmp_path / "out"
    calls = []

    metrics = pipeline.run(src, out, "whisper", "extractive", title="T",
                           progress_callback=lambda p, m: calls.append((p, m)))

    assert metrics["asr"]["provider"] == "whisper"
    assert metrics["asr"]["model"] == "fake"
    assert metrics["transcript_chars"] == 4
    assert (out / "minutes.md").exists()
    assert (out / "minutes.brief.md").exists()
    assert (out / "minutes.detailed.md").exists()
    assert (out / "structured_minute.json").exists()
    assert (out / "transcript.json").exists()
    assert (out / "transcript.txt").exists()
    assert (out / "metrics.json").exists()
    assert calls[-1] == (100, "完成")
    # 纪要含正文与转写引擎描述
    content = (out / "minutes.md").read_text(encoding="utf-8")
    assert "会议纪要" in content
    assert "行动项" in content


def test_run_with_progress_no_callback(tmp_path, monkeypatch):
    _offline(monkeypatch)
    src = make_wav(tmp_path / "in.wav", 1.0)
    metrics = pipeline.run(src, tmp_path / "out", "whisper", "extractive")
    assert metrics["total_elapsed_s"] >= 0
    assert metrics["structured"]["n_speakers"] >= 1
