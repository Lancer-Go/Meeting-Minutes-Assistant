"""M1 · render 模块 — 纪要 Markdown 渲染（纯函数，可单测）。"""
from __future__ import annotations


def build_minutes_md(meta: dict, body_md: str) -> str:
    """组装最终纪要 Markdown：标题 + 元信息 + 正文。

    meta 可含：title / created_at / duration_min / asr（转写引擎描述）。
    """
    title = meta.get("title") or "会议纪要"
    lines = [f"# {title}", "", "## 会议信息", ""]
    if meta.get("created_at"):
        lines.append(f"- 生成时间：{meta['created_at']}")
    if meta.get("duration_min") is not None:
        lines.append(f"- 会议时长：约 {meta['duration_min']:.1f} 分钟")
    if meta.get("asr"):
        lines.append(f"- 转写引擎：{meta['asr']}")
    lines.append("")
    lines.append(body_md.strip())
    lines.append("")
    return "\n".join(lines)
