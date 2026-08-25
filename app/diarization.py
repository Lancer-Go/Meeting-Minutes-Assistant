"""M2 · diarization 模块 — 说话人分离（TG-2）。

为转写段回填 `speaker` 标注（FR-03 细化）：
- 云 ASR 内置话者分离：优先（腾讯云 `SpeakerDiarization` 已在 asr 模块内启用并回填
  `Segment.speaker`，此处无需重复）。
- `PyannoteDiarization`：本地兜底（pyannote-audio，需 HF token + 下载模型，可选）。
- `PlaceholderDiarization`：speaker 缺失时的占位兜底（按说话轮次标 S1 / S2 / ...）。

`DiarizationProvider` 与 `ASRProvider` 解耦；speaker 缺失时标记 S1 / S2 / ... 占位。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.asr import Segment


@dataclass
class SpeakerSegment:
    """说话人分离结果段。"""

    start: float
    end: float
    speaker: str


class DiarizationProvider(ABC):
    name = "base"

    @abstractmethod
    def diarize(self, wav: Path, segments: list[Segment]) -> list[SpeakerSegment]:
        """对音频做说话人分离，返回 (start, end, speaker) 段列表。"""
        ...


class PyannoteDiarization(DiarizationProvider):
    """pyannote-audio 本地说话人分离（可选依赖）。

    ⚠️ 需额外安装 `pyannote.audio` 与 `torch`，并配置 `HF_TOKEN`（模型需授权下载）。
    未安装 / 未授权时抛 RuntimeError，调用方应降级到占位兜底。
    """

    name = "pyannote"

    def __init__(self, token: str = "", model: str = "pyannote/speaker-diarization-3.1",
                 device: str = "auto"):
        import os

        self.token = token or os.getenv("HF_TOKEN", "")
        self.model_name = model
        self.device = device

    def diarize(self, wav: Path, segments: list[Segment]) -> list[SpeakerSegment]:
        try:
            from pyannote.audio import Pipeline  # lazy import
        except ImportError as e:  # pragma: no cover - 依赖缺失路径
            raise RuntimeError(
                "pyannote-audio 未安装：`pip install pyannote.audio torch` 并配置 HF_TOKEN "
                "后重试，或改用 placeholder 占位兜底。"
            ) from e
        if not self.token:
            raise RuntimeError("缺少 HF_TOKEN：pyannote 模型需授权下载。改用 placeholder 占位兜底。")

        pipeline = Pipeline.from_pretrained(self.model_name, use_auth_token=self.token)
        if self.device != "auto":
            pipeline.to(self.device)
        result = pipeline(str(wav))
        out: list[SpeakerSegment] = []
        for turn, _, speaker in result.itertracks(yield_label=True):
            out.append(SpeakerSegment(float(turn.start), float(turn.end), str(speaker)))
        return out


class PlaceholderDiarization(DiarizationProvider):
    """占位兜底：speaker 缺失时按说话轮次标记 S1 / S2 / ...。

    启发式：把连续段按时间顺序轮替分配说话人；相邻段间隔超过阈值（默认 1.5s）视为新说话轮。
    仅用于保证链路可跑通，正确率进入 TG-7 评测，不代表真实话者分离。
    """

    name = "placeholder"

    def __init__(self, gap_s: float = 1.5, max_speakers: int = 8):
        self.gap_s = gap_s
        self.max_speakers = max_speakers

    def diarize(self, wav: Path, segments: list[Segment]) -> list[SpeakerSegment]:
        if not segments:
            return []
        ordered = sorted(segments, key=lambda s: s.start)
        out: list[SpeakerSegment] = []
        current = 1
        prev_end = None
        for s in ordered:
            if prev_end is not None and (s.start - prev_end) > self.gap_s:
                current = (current % self.max_speakers) + 1  # 轮替到下一个说话人
            out.append(SpeakerSegment(s.start, s.end, f"S{current}"))
            prev_end = max(prev_end or 0.0, s.end)
        return out


def assign_speakers(segments: list[Segment], speaker_segments: list[SpeakerSegment]) -> None:
    """按最大时间重叠，把 SpeakerSegment 的 speaker 回填到 Segment.speaker。"""
    for seg in segments:
        best = ""
        best_overlap = 0.0
        for sp in speaker_segments:
            overlap = max(0.0, min(seg.end, sp.end) - max(seg.start, sp.start))
            if overlap > best_overlap:
                best_overlap = overlap
                best = sp.speaker
        seg.speaker = best


def has_speakers(segments: list[Segment]) -> bool:
    """判断转写段是否已有 speaker 标注。"""
    return any(bool(getattr(s, "speaker", "")) for s in segments)


def distinct_speakers(segments: list[Segment]) -> list[str]:
    """按出现顺序返回去重后的 speaker 列表。"""
    seen: list[str] = []
    for s in segments:
        sp = getattr(s, "speaker", "") or ""
        if sp and sp not in seen:
            seen.append(sp)
    return seen


PROVIDERS = {
    "pyannote": PyannoteDiarization,
    "placeholder": PlaceholderDiarization,
}


def get_diarization_provider(name: str, **kwargs) -> DiarizationProvider:
    if name not in PROVIDERS:
        raise ValueError(f"未知 diarization provider: {name}（可选 {list(PROVIDERS)}）")
    return PROVIDERS[name](**kwargs)
