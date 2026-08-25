"""M2 · 生成种子样例的 predicted 产物（TG-7 演示用）。

从 eval/golden/*.json 读取种子任务，用离线模块（规则抽取 + 占位话者 + 角色 + Jinja2 渲染）
生成对应的 pipeline 产物（structured_minute.json / transcript.json / minutes*.md），
写入 --task-dir，供 `python -m eval.eval_quality` 跑通评测闭环。

用法（演示评测流程，非真实指标）：
    python -m eval.make_seed_predicted --task-dir data/tasks
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.asr import Segment, Transcript  # noqa: E402
from app.extractor import RuleExtractor  # noqa: E402
from app.render import render_minutes  # noqa: E402
from app.role import identify_roles  # noqa: E402
from app.schemas import StructuredMinute  # noqa: E402


def _build_transcript(speaker_segments: list[dict]) -> Transcript:
    segs = []
    for i, sp in enumerate(speaker_segments):
        segs.append(Segment(sp["start"], sp["end"], f"发言人讨论要点 {i + 1}", speaker=sp["speaker"]))
    return Transcript(segments=segs, text="".join(s.text for s in segs),
                      provider="seed", model="seed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden-dir", type=Path, default=Path("eval/golden"))
    ap.add_argument("--task-dir", type=Path, default=Path("data/tasks"))
    args = ap.parse_args()

    for gf in sorted(args.golden_dir.glob("*.json")):
        golden = json.loads(gf.read_text(encoding="utf-8"))
        task_id = golden.get("task_id", gf.stem)
        out = args.task_dir / task_id
        out.mkdir(parents=True, exist_ok=True)

        transcript = _build_transcript(golden.get("speaker_segments", []))
        speakers = identify_roles(transcript.segments)
        extracted = RuleExtractor().extract(transcript)

        # 用 golden actions 作为“预测结果”的近似，保证演示有完整三要素（真实场景应由 extractor 产生）
        from app.schemas import ActionItem
        predicted_actions = extracted.actions or [
            ActionItem(description=a["description"], owner=a["owner"], due=a["due"],
                       priority=a.get("priority", "中"), status=a.get("status", "待办"))
            for a in golden.get("actions", [])
        ]
        structured = StructuredMinute(
            title=golden.get("title", task_id),
            summary_md=golden.get("minutes_md", ""),
            actions=predicted_actions,
            speakers=speakers,
        )
        (out / "structured_minute.json").write_text(
            json.dumps(structured.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "transcript.json").write_text(
            json.dumps(transcript.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        meta = {"title": structured.title, "asr": "seed / demo"}
        tt = transcript.to_timestamped_text(with_speaker=True)
        (out / "minutes.md").write_text(
            render_minutes(structured, "standard", meta, tt), encoding="utf-8")
        (out / "minutes.brief.md").write_text(
            render_minutes(structured, "brief", meta, tt), encoding="utf-8")
        (out / "minutes.detailed.md").write_text(
            render_minutes(structured, "detailed", meta, tt), encoding="utf-8")
        print(f"生成 {task_id} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
