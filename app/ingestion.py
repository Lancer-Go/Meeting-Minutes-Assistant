"""M1 · ingestion 模块 — 上传校验（格式白名单 / 大小 / 时长）。

纯函数，可单测。FR-01 上传校验与 FR-02 输入约束。
"""
from __future__ import annotations

from pathlib import Path

from app import audio, config


def validate_extension(filename: str) -> str | None:
    """校验文件扩展名是否在白名单内。返回错误信息，None 表示通过。"""
    ext = Path(filename).suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(config.ALLOWED_EXTENSIONS))
        return f"不支持的格式 {ext or '（无扩展名）'}，支持 {allowed}"
    return None


def validate_size(size_bytes: int) -> str | None:
    """校验文件大小是否超上限。"""
    if size_bytes <= 0:
        return "空文件"
    if size_bytes > config.MAX_FILE_SIZE_BYTES:
        mb = size_bytes / 1024 / 1024
        limit = config.MAX_FILE_SIZE_BYTES / 1024 / 1024
        return f"文件过大（{mb:.0f}MB，上限 {limit:.0f}MB）"
    return None


def validate_duration(path: Path) -> str | None:
    """校验音视频时长是否 ≤ 2 小时（ffprobe）。"""
    dur = audio.get_duration(path)
    if dur <= 0:
        return "无法读取音频时长（文件可能损坏或非音视频）"
    if dur > config.MAX_DURATION_SECONDS:
        return f"会议时长 {dur / 60:.0f} 分钟，超过上限 2 小时"
    return None
