"""验证话者分离效果：URL 模式（SourceType=0）优先，回退 base64 切片。

用法：venv/Scripts/python.exe scripts/verify_speaker_coverage.py
只跑 ASR（不跑 LLM 纪要），用于验证话者分离（覆盖率 / 人数 / 各说话人段数）。
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config
from app.asr import TencentASR
from app.diarization import distinct_speakers, speaker_coverage
from app.storage import get_storage

AUDIO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/verify_第二场会议/audio.wav")
OUT = Path("out/verify_speaker_url")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    provider = TencentASR()

    # 上传音频到对象存储取预签名 URL（URL 模式，需 MMA_ASR_URL_ENABLED=true + 公网可达存储）
    url = None
    if config.ASR_URL_ENABLED:
        storage = get_storage()
        if storage.s3:
            key = f"asr/{AUDIO.name}"
            print(f"[{time.strftime('%H:%M:%S')}] 上传音频到对象存储 {key} ...", flush=True)
            t0 = time.time()
            storage.put_file(key, AUDIO)
            url = storage.presigned_url(key)
            print(f"  上传完成 {time.time() - t0:.1f}s，预签名 URL {'OK' if url else 'FAIL'}", flush=True)

    mode = "URL（整段，全局话者分离）" if url else "base64 切片"
    print(f"[{time.strftime('%H:%M:%S')}] 开始转写（{mode}）...", flush=True)
    t0 = time.time()
    transcript = provider.transcribe(
        AUDIO,
        progress_callback=lambda d, t: print(f"  第 {d}/{t} 段", flush=True),
        url=url,
    )
    elapsed = time.time() - t0

    coverage = speaker_coverage(transcript.segments)
    speakers = distinct_speakers(transcript.segments)
    cnt = Counter((s.speaker or "<空>") for s in transcript.segments)

    print(f"\n=== 结果（{mode}）===", flush=True)
    print(f"总段数: {len(transcript.segments)}", flush=True)
    print(f"转写耗时: {elapsed:.1f}s", flush=True)
    print(f"话者分离覆盖率: {coverage * 100:.1f}%", flush=True)
    print(f"去重说话人: {speakers}", flush=True)
    print(f"各说话人段数: {dict(sorted(cnt.items(), key=lambda x: -x[1]))}", flush=True)

    (OUT / "transcript.json").write_text(
        json.dumps(transcript.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已保存 transcript → {OUT / 'transcript.json'}", flush=True)


if __name__ == "__main__":
    main()
