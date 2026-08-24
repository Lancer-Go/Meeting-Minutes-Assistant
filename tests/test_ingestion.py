"""ingestion 上传校验单元测试。"""
from pathlib import Path

from app import config
from app.ingestion import validate_duration, validate_extension, validate_size


def test_validate_extension_ok():
    for f in ["a.mp4", "b.MKV", "c.wav", "d.mp3", "e.m4a"]:
        assert validate_extension(f) is None


def test_validate_extension_reject():
    assert validate_extension("a.exe") is not None
    assert validate_extension("a.txt") is not None
    assert validate_extension("noext") is not None


def test_validate_size_ok():
    assert validate_size(1000) is None
    assert validate_size(config.MAX_FILE_SIZE_BYTES) is None


def test_validate_size_empty():
    assert validate_size(0) is not None
    assert validate_size(-1) is not None


def test_validate_size_too_big():
    assert validate_size(config.MAX_FILE_SIZE_BYTES + 1) is not None


def test_validate_duration_ok(monkeypatch):
    monkeypatch.setattr("app.ingestion.audio.get_duration", lambda p: 60.0)
    assert validate_duration(Path("x.wav")) is None


def test_validate_duration_too_long(monkeypatch):
    monkeypatch.setattr("app.ingestion.audio.get_duration",
                        lambda p: config.MAX_DURATION_SECONDS + 1)
    assert validate_duration(Path("x.wav")) is not None


def test_validate_duration_bad_file(monkeypatch):
    monkeypatch.setattr("app.ingestion.audio.get_duration", lambda p: 0.0)
    assert validate_duration(Path("x.wav")) is not None
