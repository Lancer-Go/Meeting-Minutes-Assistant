"""M2 · 质量评测脚本（TG-7）。

对比黄金基准集与 pipeline 产物，输出三项指标：行动项三要素完整率、说话人正确率、返工率。

用法：
    python -m eval.eval_quality --golden-dir eval/golden --task-dir data/tasks

黄金基准文件（eval/golden/*.json）结构：
    {
      "task_id": "...",           # 对应 data/tasks/<task_id>
      "title": "...",
      "actions": [{"description","owner","due","priority","status"}],   # 黄金行动项
      "speaker_segments": [{"start","end","speaker"}],                   # 黄金说话人标签
      "minutes_md": "黄金纪要全文（人工标注）"
    }
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.metrics import THRESHOLDS, evaluate, passed  # noqa: E402


def load_predicted(task_dir: Path, task_id: str) -> dict | None:
    base = task_dir / task_id
    sm_path = base / "structured_minute.json"
    if not sm_path.exists():
        return None
    sm = json.loads(sm_path.read_text(encoding="utf-8"))
    transcript = {}
    tr_path = base / "transcript.json"
    if tr_path.exists():
        transcript = json.loads(tr_path.read_text(encoding="utf-8"))

    def _read(p: Path) -> str:
        return p.read_text(encoding="utf-8") if p.exists() else ""

    return {
        "actions": sm.get("actions", []),
        "segments": transcript.get("segments", []),
        "minutes_md": _read(base / "minutes.md"),
        "edited_md": _read(base / "minutes.edited.md"),
    }


def run(golden_dir: Path, task_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for gf in sorted(golden_dir.glob("*.json")):
        golden = json.loads(gf.read_text(encoding="utf-8"))
        task_id = golden.get("task_id", gf.stem)
        pred = load_predicted(task_dir, task_id)
        if pred is None:
            print(f"⚠️ 跳过 {gf.name}：未找到 {task_id} 的 pipeline 产物", file=sys.stderr)
            continue
        m = evaluate(golden, pred)
        rows.append({
            "task_id": task_id,
            "title": golden.get("title", ""),
            **m,
            "passed": passed(m),
        })
    return rows


def _fmt_ratio(v: float) -> str:
    return f"{v * 100:6.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description="M2 纪要质量评测")
    ap.add_argument("--golden-dir", type=Path, default=Path("eval/golden"))
    ap.add_argument("--task-dir", type=Path, default=Path("data/tasks"))
    ap.add_argument("--json", action="store_true", help="输出 JSON 报告")
    args = ap.parse_args()

    rows = run(args.golden_dir, args.task_dir)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print("=" * 64)
    print("M2 纪要质量评测报告")
    print("=" * 64)
    print(f"{'任务':<34}{'三要素完整率':>12}{'说话人正确率':>12}{'返工率':>10}")
    for r in rows:
        print(f"{r['task_id']:<34}"
              f"{_fmt_ratio(r['action_item_completeness']):>12}"
              f"{_fmt_ratio(r['speaker_accuracy']):>12}"
              f"{_fmt_ratio(r['rework_rate']):>10}")
    print("-" * 64)
    print("阈值（mission.md KPI）：", " | ".join(
        f"{k}: {v:.0%}" for k, v in THRESHOLDS.items()))
    if rows:
        n_pass = sum(1 for r in rows if r["passed"])
        print(f"达标：{n_pass}/{len(rows)} 场")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
