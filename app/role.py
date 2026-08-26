"""M2 · role 模块 — 说话人角色识别（TG-3）。

标注主持人 / 汇报人 / 参会者（FR-11）：
- 规则层：按说话频次 / 开场顺序 / 「下面请 XX 汇报」等句式启发式判定。
- LLM 辅助：对 speaker 摘要做角色分类（需密钥时启用，可选）。

输出 speaker → role 映射，回填 `StructuredMinute.speakers[]`（TG-4 模板渲染使用）。
"""
from __future__ import annotations

import re

from app.asr import Segment
from app.schemas import ROLE_HOST, ROLE_PARTICIPANT, ROLE_PRESENTER, Speaker

# 汇报人提示句式
_PRESENTER_RE = re.compile(r"(下面|接下来)?(请|由|我)?(给?大家)?(汇报|介绍|说明|讲解)")
# 主持人开场 / 收尾句式
_HOST_RE = re.compile(r"(开会|开始|结束|总结一下|大家|今天|本次|会议|下面请|接下来)")

# 单说话人时作为主持人；否则按启发式判定


def _speaker_stats(segments: list[Segment]) -> dict[str, dict]:
    """按 speaker 聚合：出现次数、字符数、首句起始时间、文本。"""
    stats: dict[str, dict] = {}
    for s in segments:
        sp = getattr(s, "speaker", "") or "S1"
        st = stats.setdefault(sp, {"count": 0, "chars": 0, "start": float("inf"), "text": ""})
        st["count"] += 1
        st["chars"] += len(s.text)
        st["start"] = min(st["start"], s.start)
        st["text"] += s.text
    return stats


def identify_roles(segments: list[Segment]) -> list[Speaker]:
    """规则式角色识别：返回按首现顺序排列的 speaker → role 列表。"""
    if not segments:
        return []
    stats = _speaker_stats(segments)
    names = [sp for sp in _ordered_names(segments) if sp in stats]

    if len(names) == 1:
        return [Speaker(name=names[0], role=ROLE_HOST)]

    # 主持人：出现次数最多（或命中开场/收尾句式）
    host = max(names, key=lambda n: (stats[n]["count"], -stats[n]["start"]))

    # 汇报人：剩余中命中「汇报」句式或字符数最多者
    rest = [n for n in names if n != host]
    presenter = None
    for n in rest:
        if _PRESENTER_RE.search(stats[n]["text"]):
            presenter = n
            break
    if presenter is None and rest:
        presenter = max(rest, key=lambda n: stats[n]["chars"])

    out: list[Speaker] = []
    for n in names:
        role = ROLE_HOST if n == host else (ROLE_PRESENTER if n == presenter else ROLE_PARTICIPANT)
        out.append(Speaker(name=n, role=role))
    return out


def _ordered_names(segments: list[Segment]) -> list[str]:
    seen: list[str] = []
    for s in segments:
        sp = getattr(s, "speaker", "") or "S1"
        if sp not in seen:
            seen.append(sp)
    return seen


def summarize_by_speaker(segments: list[Segment]) -> dict[str, str]:
    """为每个 speaker 生成简短文本摘要（供 LLM 角色分类）。"""
    stats = _speaker_stats(segments)
    return {n: st["text"][:500] for n, st in stats.items()}


def identify_roles_llm(segments: list[Segment], llm) -> list[Speaker]:
    """LLM 辅助角色分类（需密钥）。llm 需提供 summarize(transcript) 或 _chat 接口。

    简单实现：复用规则结果作为兜底；若传入的 llm 提供 `classify_roles(text)->dict` 则用之。
    """
    # 默认退回规则式结果（LLM 细分类留作后续增强，保持可运行）。
    rules = identify_roles(segments)
    if not hasattr(llm, "classify_roles"):
        return rules
    try:
        mapping = llm.classify_roles(summarize_by_speaker(segments))
        if isinstance(mapping, dict):
            return [Speaker(name=s.name, role=mapping.get(s.name, s.role)) for s in rules]
    except Exception:  # noqa: BLE001 — 任何异常回落规则
        pass
    return rules
