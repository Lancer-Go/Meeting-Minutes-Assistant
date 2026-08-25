"""M2 · eval 质量指标（TG-7）。

纯函数，供评测脚本与单元测试复用。定义三个核心指标：
- 行动项三要素完整率（决议描述 / 负责人 / 截止时间）
- 说话人正确率（按时间重叠对齐比较 speaker 标签）
- 纪要返工率（编辑稿相对原稿的改动比例）

阈值（mission.md KPI / validation.md V1/V2）：三要素 ≥ 85%、说话人 ≥ 80%、返工率 ≤ 20%。
"""
from __future__ import annotations

import difflib


def _s(v) -> str:
    return (v or "").strip()


def action_item_completeness(actions: list) -> float:
    """行动项三要素完整率：描述 / 负责人 / 截止时间 均非空且非「待定」的行动项占比。

    空列表返回 0.0（无行动项视为不完整）。actions 可为 dict 列表或 ActionItem 列表。
    """
    if not actions:
        return 0.0
    complete = 0
    for a in actions:
        d = a if isinstance(a, dict) else a.__dict__
        desc, owner, due = _s(d.get("description")), _s(d.get("owner")), _s(d.get("due"))
        if desc and owner not in ("", "待定") and due not in ("", "待定"):
            complete += 1
    return complete / len(actions)


def _seg_tuple(s) -> tuple[float, float, str]:
    if isinstance(s, dict):
        return float(s.get("start", 0.0)), float(s.get("end", 0.0)), _s(s.get("speaker"))
    return float(s[0]), float(s[1]), _s(s[2])


def speaker_accuracy(pred_segments: list, gold_segments: list) -> float:
    """说话人正确率：对每个预测段按最大时间重叠找到基准段，比较 speaker 标签（时长加权）。

    pred_segments / gold_segments 为 (start, end, speaker) 或含同名字段的 dict 列表。
    无基准时返回 0.0；无预测段返回 0.0。
    """
    pred = [_seg_tuple(s) for s in pred_segments]
    gold = [_seg_tuple(s) for s in gold_segments]
    if not gold or not pred:
        return 0.0
    total = 0.0
    matched = 0.0
    for ps, pe, pl in pred:
        dur = max(0.0, pe - ps)
        if dur <= 0:
            continue
        best_label = ""
        best_overlap = 0.0
        for gs, ge, gl in gold:
            overlap = max(0.0, min(pe, ge) - max(ps, gs))
            if overlap > best_overlap:
                best_overlap = overlap
                best_label = gl
        total += dur
        if best_label == pl:
            matched += dur
    return matched / total if total else 0.0


def rework_rate(original_md: str, edited_md: str) -> float:
    """返工率：编辑稿相对原稿的改动比例（1 − SequenceMatcher 相似度）。

    未编辑（edited_md 为空）视为 0（无返工）；原稿缺失但存在编辑稿视为 1。
    """
    if not edited_md:
        return 0.0
    if not original_md:
        return 1.0
    return 1.0 - difflib.SequenceMatcher(None, original_md, edited_md).ratio()


def evaluate(golden: dict, predicted: dict) -> dict:
    """从 golden / predicted 两份结构化数据计算三项指标。

    golden: {"actions": [...], "speaker_segments": [...], "minutes_md": str}
    predicted: {"actions": [...], "segments": [...], "minutes_md": str, "edited_md": str}
    返回 dict：completeness / speaker_accuracy / rework_rate。
    """
    return {
        "action_item_completeness": round(
            action_item_completeness(predicted.get("actions", [])), 4),
        "speaker_accuracy": round(
            speaker_accuracy(predicted.get("segments", []),
                             golden.get("speaker_segments", [])), 4),
        "rework_rate": round(
            rework_rate(predicted.get("minutes_md", ""),
                        predicted.get("edited_md", "")), 4),
    }


# 验收阈值（mission.md KPI）
THRESHOLDS = {
    "action_item_completeness": 0.85,   # ≥ 85%
    "speaker_accuracy": 0.80,           # ≥ 80%
    "rework_rate": 0.20,                # ≤ 20%
}


def passed(metrics: dict) -> bool:
    """判断三项指标是否达标。"""
    return (
        metrics["action_item_completeness"] >= THRESHOLDS["action_item_completeness"]
        and metrics["speaker_accuracy"] >= THRESHOLDS["speaker_accuracy"]
        and metrics["rework_rate"] <= THRESHOLDS["rework_rate"]
    )
