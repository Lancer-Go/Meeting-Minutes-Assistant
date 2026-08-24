"""TG-2 · 音频提取与标准化。

用 FFmpeg 把任意音视频（MP4 / MKV / WAV / MP3 / M4A 等）统一抽取并标准化为
16kHz / 单声道 WAV，供 ASR 使用。

用法:
    python audio.py <输入文件> [输出.wav]
    python audio.py --probe <输入文件>      # 仅打印音频元信息，不转换
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SUPPORTED_EXT = {
    ".mp4", ".mkv", ".mov", ".avi", ".flv", ".ts",
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm",
}


def resolve_ffmpeg() -> tuple[str, str]:
    """返回 (ffmpeg, ffprobe) 可执行路径。

    查找顺序：系统 PATH → 项目 tools/ffmpeg/bin → static-ffmpeg（联网下载）。
    """
    # 1) 系统 PATH
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ff and fp:
        return ff, fp
    # 2) 项目内置 tools/ffmpeg/bin
    local_bin = Path(__file__).resolve().parent / "tools" / "ffmpeg" / "bin"
    ff, fp = local_bin / "ffmpeg.exe", local_bin / "ffprobe.exe"
    if ff.exists() and fp.exists():
        return str(ff), str(fp)
    # 3) static-ffmpeg（pip 兜底，联网下载）
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
    if src.suffix.lower() not in SUPPORTED_EXT:
        raise ValueError(f"不支持的输入格式: {src.suffix}（支持 {sorted(SUPPORTED_EXT)}）")
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


def summarize_probe(src: Path) -> str:
    """把 ffprobe 结果整理为人类可读摘要。"""
    info = probe(src)
    lines = []
    for s in info.get("streams", []):
        if s.get("codec_type") == "audio":
            dur = float(s.get("duration", 0))
            lines.append(
                f"音频流: {s.get('codec_name')} | {s.get('sample_rate', '?')}Hz "
                f"| {s.get('channels', '?')}ch | 时长 {dur / 60:.2f} min ({dur:.2f}s)"
            )
    fmt = info.get("format", {})
    if "duration" in fmt:
        lines.append(f"容器时长: {float(fmt['duration']) / 60:.2f} min")
    return "\n".join(lines) or "（未识别到音频流）"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TG-2 音频提取与标准化")
    ap.add_argument("input", help="输入音视频文件")
    ap.add_argument("output", nargs="?", help="输出 WAV（默认与输入同名 .wav）")
    ap.add_argument("--probe", action="store_true", help="仅打印元信息，不转换")
    ap.add_argument("--sr", type=int, default=16000)
    ap.add_argument("--channels", type=int, default=1)
    args = ap.parse_args(argv)

    src = Path(args.input)
    if not src.exists():
        print(f"错误: 文件不存在 {src}", file=sys.stderr)
        return 1
    if args.probe:
        print(summarize_probe(src))
        return 0
    dst = extract_audio(src, Path(args.output) if args.output else None,
                        args.sr, args.channels)
    print(f"已生成: {dst}")
    print(summarize_probe(dst))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
