"""audio 模块集成测试（真实 FFmpeg）。"""
import struct
import wave
from pathlib import Path

import pytest

from app import audio


def make_wav(path, seconds=1.0):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<h", 0) * int(16000 * seconds))
    return path


def test_resolve_ffmpeg():
    ff, fp = audio.resolve_ffmpeg()
    assert ff
    assert fp


def test_extract_audio(tmp_path):
    src = make_wav(tmp_path / "in.wav", 1.0)
    dst = audio.extract_audio(src, tmp_path / "out.wav")
    assert dst.exists()
    assert abs(audio.get_duration(dst) - 1.0) < 0.5


def test_probe(tmp_path):
    src = make_wav(tmp_path / "in.wav", 1.0)
    info = audio.probe(src)
    assert "format" in info
    assert any(s.get("codec_type") == "audio" for s in info.get("streams", []))


def test_get_duration(tmp_path):
    src = make_wav(tmp_path / "in.wav", 2.0)
    assert abs(audio.get_duration(src) - 2.0) < 0.5


def test_split_wav(tmp_path):
    src = make_wav(tmp_path / "in.wav", 2.0)
    chunks = audio.split_wav(src, 1.0, tmp_path / "chunks")
    assert len(chunks) == 2
    assert all(c.exists() for c in chunks)


def test_extract_audio_reject_format(tmp_path):
    bad = tmp_path / "x.exe"
    bad.write_bytes(b"x")
    with pytest.raises(ValueError):
        audio.extract_audio(bad)
