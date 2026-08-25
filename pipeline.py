"""TG-5 · 端到端串联。

一键「音频 → 转写 → 纪要」，并记录耗时 / 成本 / 转写字符数三组实测数据。

用法:
    python pipeline.py <输入音视频> [--asr whisper] [--llm extractive] [--out 目录]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import config
import audio
from asr import get_asr_provider
from summarize import get_llm_provider

# 估算价格（2024 列表价，仅作量级估算，实际以账单为准）
ASR_PRICE_RMB_PER_MIN = {
    "whisper": 0.0,        # 本地免费
    "aliyun": 2.5 / 60,    # 阿里云录音文件识别 ~¥2.5/h → 每分钟
    "tencent": 1.75 / 60,  # 腾讯云 16k_zh ~¥1.75/h → 每分钟
    "iflytek": 2.0 / 60,   # 讯飞 ~¥2.0/h → 每分钟
}
LLM_PRICE_RMB_PER_1K_TOKENS = {
    "deepseek": 0.002,     # deepseek-v4-pro 输入 ~¥2/百万 token（估）
    "qwen": 0.002,         # qwen-plus 估
    "extractive": 0.0,
}


def estimate_cost(asr_name: str, audio_minutes: float,
                  llm_name: str, transcript_chars: int) -> tuple[float, float]:
    """估算 ASR 与 LLM 成本（量级，实际以账单为准）。"""
    asr_cost = ASR_PRICE_RMB_PER_MIN.get(asr_name, 0.0) * audio_minutes
    # 中文约 1 字符 ≈ 1 token（估算上限）
    tokens = transcript_chars
    llm_cost = LLM_PRICE_RMB_PER_1K_TOKENS.get(llm_name, 0.0) * tokens / 1000
    return asr_cost, llm_cost


def run(input_path: Path, asr_name: str, llm_name: str, out_dir: Path) -> dict:
    metrics = {"input": str(input_path), "started_at": datetime.now().isoformat(timespec="seconds")}

    # 1) 音频提取
    t0 = time.time()
    wav = audio.extract_audio(input_path, out_dir / "audio.wav")
    metrics["audio_elapsed_s"] = round(time.time() - t0, 2)
    audio_minutes = float(audio.probe(wav)["format"]["duration"]) / 60

    # 2) 转写
    asr_provider = get_asr_provider(asr_name, **({"model": config.WHISPER_MODEL} if asr_name == "whisper" else {}))
    t0 = time.time()
    transcript = asr_provider.transcribe(wav)
    metrics["asr_elapsed_s"] = round(time.time() - t0, 2)

    (out_dir / "transcript.json").write_text(
        json.dumps(transcript.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "transcript.txt").write_text(transcript.to_timestamped_text(), encoding="utf-8")

    # 3) 纪要
    llm_provider = get_llm_provider(llm_name)
    t0 = time.time()
    minutes_md = llm_provider.summarize(transcript)
    llm_elapsed = time.time() - t0
    (out_dir / "minutes.md").write_text(minutes_md, encoding="utf-8")

    # 4) 指标汇总
    asr_cost, llm_cost = estimate_cost(asr_name, audio_minutes, llm_name, transcript.char_count)
    metrics.update({
        "audio_duration_min": round(audio_minutes, 2),
        "asr": {"provider": transcript.provider, "model": transcript.model,
                "elapsed_s": metrics["asr_elapsed_s"], "cost_rmb": round(asr_cost, 4)},
        "llm": {"provider": llm_name, "model": getattr(llm_provider, "model", ""),
                "elapsed_s": round(llm_elapsed, 2), "cost_rmb": round(llm_cost, 4)},
        "transcript_chars": transcript.char_count,
        "total_elapsed_s": round(metrics["audio_elapsed_s"] + metrics["asr_elapsed_s"] + llm_elapsed, 2),
        "total_cost_rmb": round(asr_cost + llm_cost, 4),
        "ratio_elapsed_to_duration": round(
            (metrics["audio_elapsed_s"] + metrics["asr_elapsed_s"] + llm_elapsed)
            / max(audio_minutes * 60, 1e-6), 3),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TG-5 端到端流水线")
    ap.add_argument("input", help="输入音视频文件")
    ap.add_argument("--asr", default=config.DEFAULT_ASR,
                    choices=["whisper", "aliyun", "tencent", "iflytek"])
    ap.add_argument("--llm", default=config.DEFAULT_LLM,
                    choices=["deepseek", "qwen", "extractive"])
    ap.add_argument("--out", default="", help="输出目录（默认 out/<时间戳>/）")
    args = ap.parse_args(argv)

    src = Path(args.input)
    if not src.exists():
        print(f"错误: 文件不存在 {src}", file=sys.stderr)
        return 1

    out_dir = Path(args.out) if args.out else config.OUT_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"▶ 输入: {src}")
    print(f"▶ 输出目录: {out_dir}")
    print(f"▶ ASR={args.asr}  LLM={args.llm}")
    try:
        m = run(src, args.asr, args.llm, out_dir)
    except RuntimeError as e:
        print(f"\n❌ 失败: {e}", file=sys.stderr)
        return 1

    print("\n✅ 流水线完成")
    print(json.dumps({
        "音频时长(min)": m["audio_duration_min"],
        "音频提取(s)": m["audio_elapsed_s"],
        "转写耗时(s)": m["asr_elapsed_s"],
        "纪要耗时(s)": m["llm"]["elapsed_s"],
        "总耗时(s)": m["total_elapsed_s"],
        "耗时/时长比": m["ratio_elapsed_to_duration"],
        "转写字符数": m["transcript_chars"],
        "ASR成本(¥)": m["asr"]["cost_rmb"],
        "LLM成本(¥)": m["llm"]["cost_rmb"],
        "总成本(¥)": m["total_cost_rmb"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
