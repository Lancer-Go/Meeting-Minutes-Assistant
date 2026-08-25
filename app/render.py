"""M2 · render 模块 — Jinja2 模板化纪要渲染（TG-4）。

从单一 Markdown 拼接升级为模板化渲染：`render_minutes(structured_minute, template_name)`。
三套模板：标准（决议 + 讨论要点 + 行动项表 + 未决问题）、精简（决议 + 行动项一览）、
详细（含说话人/角色 + 全文转写附录）。保留 M1 的 `build_minutes_md` 向后兼容。
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.schemas import StructuredMinute

TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2", "md", "txt")),
    keep_trailing_newline=True,
)

# template_name → 模板文件
TEMPLATES = {
    "standard": "standard.md.j2",
    "brief": "brief.md.j2",
    "detailed": "detailed.md.j2",
}
DEFAULT_TEMPLATE = "standard"


def render_minutes(minute: StructuredMinute, template_name: str = DEFAULT_TEMPLATE,
                   meta: dict | None = None, transcript_text: str = "") -> str:
    """按模板名渲染结构化纪要为 Markdown。meta 可含 created_at / duration_min / asr。"""
    if template_name not in TEMPLATES:
        raise ValueError(f"未知模板: {template_name}（可选 {list(TEMPLATES)}）")
    tpl = _env.get_template(TEMPLATES[template_name])
    ctx = {
        "minute": minute,
        "meta": meta or {},
        "transcript_text": transcript_text,
    }
    return tpl.render(**ctx).strip() + "\n"


def build_minutes_md(meta: dict, body_md: str) -> str:
    """M1 兼容入口：标题 + 元信息 + 正文（保留原行为，供既有调用与测试）。"""
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
