"""M1 · audio 模块 — 音频提取、探测与切片。

用 FFmpeg 把任意音视频统一为 16kHz / 单声道 WAV，并提供 ffprobe 探测（时长/规格）
与切片能力（腾讯云录音文件识别 base64 ≤5MB 的长音频分段）。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from app import config

# 输入格式白名单（FR-01）：MP4 / MKV / WAV / MP3 / M4A
ALLOWED_EXTENSIONS = config.ALLOWED_EXTENSIONS


def resolve_ffmpeg() -> tuple[str, str]:
    """返回 (ffmpeg, ffprobe) 可执行路径。

    查找顺序：系统 PATH → 项目 tools/ffmpeg/bin → static-ffmpeg（联网下载）。
    """
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ff and fp:
        return ff, fp
    local_bin = config.ROOT / "tools" / "ffmpeg" / "bin"
    ff, fp = local_bin / "ffmpeg.exe", local_bin / "ffprobe.exe"
    if ff.exists() and fp.exists():
        return str(ff), str(fp)
    try:
        import static_ffmpeg  # type: ignore
        static_ffmpeg.add_paths()
        ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
        if ff and fp:
            return ff, fp
    except Exception:
        pass
    raise RuntimeError(
        "未找到 ffmpeg/ffprobe。请安装 FFmpeg（加入 PATH）、放到 tools/ffmpeg/bin/，"
        "或执行 `pip install static-ffmpeg`。"
    )


def extract_audio(src: Path, dst: Path | None = None,
                  sample_rate: int = 16000, channels: int = 1) -> Path:
    """抽音轨并标准化为 16kHz 单声道 WAV，返回输出路径。"""
    src = Path(src)
    if src.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"不支持的输入格式: {src.suffix}（支持 {sorted(ALLOWED_EXTENSIONS)}）")
    if dst is None:
        dst = src.with_suffix(".wav")
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg, _ = resolve_ffmpeg()
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(src), "-vn", "-ac", str(channels), "-ar", str(sample_rate),
           "-f", "wav", str(dst)]
    subprocess.run(cmd, check=True)
    return dst


def probe(src: Path) -> dict:
    """用 ffprobe 读取音视频元信息（时长 / 编码 / 采样率 / 声道）。"""
    _, ffprobe = resolve_ffmpeg()
    cmd = [ffprobe, "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", str(src)]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def get_duration(src: Path) -> float:
    """返回音视频时长（秒）。取容器时长，缺失时取音频流时长。"""
    info = probe(src)
    fmt_dur = info.get("format", {}).get("duration")
    if fmt_dur:
        return float(fmt_dur)
    for s in info.get("streams", []):
        if s.get("codec_type") == "audio" and s.get("duration"):
            return float(s["duration"])
    return 0.0


def split_wav(src: Path, chunk_seconds: float, out_dir: Path) -> list[Path]:
    """把 WAV 按固定时长切成多段，返回切片段路径列表（按时间顺序）。

    用于腾讯云录音文件识别（base64 ≤5MB ≈2min），逐段识别后按偏移合并。
    """
    ffmpeg, _ = resolve_ffmpeg()
    total = get_duration(src)
    if total <= 0:
        raise RuntimeError(f"无法读取音频时长: {src}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[Path] = []
    offset = 0.0
    idx = 0
    while offset < total:
        idx += 1
        dst = out_dir / f"chunk_{idx:03d}.wav"
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
               "-ss", f"{offset:.3f}", "-t", f"{chunk_seconds:.3f}",
               "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
               "-f", "wav", str(dst)]
        subprocess.run(cmd, check=True)
        if not dst.exists() or dst.stat().st_size < 44:  # 空 WAV（44 字节头）
            dst.unlink(missing_ok=True)
            break
        chunks.append(dst)
        offset += chunk_seconds
    if not chunks:
        raise RuntimeError(f"切片失败: {src}")
    return chunks
