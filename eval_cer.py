"""TG-6 · 转写准确率评测（CER，字符错误率）。

CER = (替换 + 删除 + 插入) / 参考字符数。中文按字符（字）计算。

用法:
    python eval_cer.py <参考文本.txt> <转写文本.txt>
    python eval_cer.py <参考文本.txt> <转写.json>   # 自动取 text 字段
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def normalize(text: str) -> str:
    """去空白与标点（仅按字符比较，标点计入参考时可选去重）。"""
    return re.sub(r"\s+", "", text)


def edit_distance(a: str, b: str) -> int:
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev = dp[0]
        dp[0] = i
        for j, cb in enumerate(b, 1):
            old = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (ca != cb))
            prev = old
    return dp[-1]


def cer(reference: str, hypothesis: str) -> dict:
    ref = normalize(reference)
    hyp = normalize(hypothesis)
    if not ref:
        return {"cer": None, "ref_chars": 0, "hyp_chars": len(hyp), "distance": len(hyp),
                "note": "参考文本为空"}
    dist = edit_distance(ref, hyp)
    return {"cer": round(dist / len(ref), 4), "ref_chars": len(ref),
            "hyp_chars": len(hyp), "distance": dist}


def read_text(path: Path) -> str:
    p = Path(path)
    if p.suffix == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("text", "")
    return p.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TG-6 转写 CER 评测")
    ap.add_argument("reference", help="参考文本（人工校对）")
    ap.add_argument("hypothesis", help="转写文本（txt 或 asr.py 的 json）")
    args = ap.parse_args(argv)

    ref = read_text(Path(args.reference))
    hyp = read_text(Path(args.hypothesis))
    r = cer(ref, hyp)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if r["cer"] is not None:
        acc = (1 - r["cer"]) * 100
        print(f"字符错误率 CER = {r['cer']:.2%}  →  准确率 ≈ {acc:.2f}%")
        print(f"参考 {r['ref_chars']} 字 / 转写 {r['hyp_chars']} 字 / 编辑距离 {r['distance']}")
        print("✅ 达标 (CER ≤ 8%)" if r["cer"] <= 0.08 else "❌ 未达标 (目标 CER ≤ 8%，即准确率 ≥ 92%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
