"""M4 · 多模型灰度对比（TG-1）。

同一样例（转写文本）跑 v4-pro / v4-flash / qwen-plus，记录质量（人工评分占位）、
成本（token/金额）、耗时，输出对比报告 JSON。

用法：
    python scripts/compare_models.py samples/transcript.txt [--aliases v4-pro,v4-flash,qwen-plus]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.asr import Segment, Transcript  # noqa: E402
from app.cost import llm_cost_rmb  # noqa: E402
from app.llm_registry import build_specs, resolve  # noqa: E402
from app.summary import get_llm_provider  # noqa: E402


def run_one(alias: str, transcript: Transcript) -> dict:
    spec = resolve(alias)
    if not spec.available():
        return {"alias": alias, "model": spec.model, "status": "未配置密钥，跳过"}

    t0 = time.time()
    try:
        llm = get_llm_provider(alias)
        md = llm.summarize(transcript)
        elapsed = round(time.time() - t0, 2)
        usage = getattr(llm, "last_usage", {}) or {}
        pin = usage.get("prompt_tokens", 0)
        pout = usage.get("completion_tokens", 0)
        pcache = usage.get("cached_tokens", 0)
        rmb = llm_cost_rmb(spec.model, pin, pout, pcache)
        return {
            "alias": alias,
            "model": spec.model,
            "status": "ok",
            "elapsed_s": elapsed,
            "tokens_in": pin,
            "tokens_out": pout,
            "tokens_cache": pcache,
            "cost_rmb": round(rmb, 6),
            "output_chars": len(md),
            "quality_score": None,  # 人工评分占位（0~10）
            "sample": md[:120],
        }
    except Exception as e:  # noqa: BLE001
        return {"alias": alias, "model": spec.model,
                "status": f"失败: {e}", "elapsed_s": round(time.time() - t0, 2)}


def main() -> int:
    p = argparse.ArgumentParser(description="多模型灰度对比")
    p.add_argument("transcript", help="转写文本文件路径")
    p.add_argument("--aliases", default="v4-pro,v4-flash,qwen-plus",
                   help="逗号分隔的模型别名（默认三模型）")
    args = p.parse_args()

    text = Path(args.transcript).read_text(encoding="utf-8")
    transcript = Transcript(segments=[Segment(0.0, 1.0, text)], text=text,
                            provider="compare", model="")

    report = []
    for alias in args.aliases.split(","):
        alias = alias.strip()
        if alias:
            report.append(run_one(alias, transcript))

    print(json.dumps({
        "sample_chars": transcript.char_count,
        "available_aliases": sorted(build_specs()),
        "results": report,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
