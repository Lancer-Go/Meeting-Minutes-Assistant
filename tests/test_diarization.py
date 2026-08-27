"""diarization 模块（M2 说话人分离）单元测试。"""
import pytest

from app.asr import Segment
from app.diarization import (
    PlaceholderDiarization,
    SpeakerSegment,
    assign_speakers,
    distinct_speakers,
    get_diarization_provider,
    has_speakers,
)


def test_placeholder_assigns_alternating():
    segs = [Segment(0.0, 2.0, "a"), Segment(2.1, 4.0, "b"), Segment(4.1, 6.0, "c")]
    out = PlaceholderDiarization().diarize(None, segs)
    assert [s.speaker for s in out] == ["S1", "S1", "S1"]  # 间隔 < 1.5s → 同一说话人


def test_placeholder_new_turn_on_gap():
    segs = [Segment(0.0, 2.0, "a"), Segment(5.0, 7.0, "b")]  # 间隔 3s > 1.5s
    out = PlaceholderDiarization().diarize(None, segs)
    assert [s.speaker for s in out] == ["S1", "S2"]


def test_placeholder_empty():
    assert PlaceholderDiarization().diarize(None, []) == []


def test_assign_speakers_overlap():
    segs = [Segment(0.0, 2.0, "a"), Segment(3.0, 5.0, "b")]
    sps = [SpeakerSegment(0.0, 2.0, "S1"), SpeakerSegment(3.0, 5.0, "S2")]
    assign_speakers(segs, sps)
    assert segs[0].speaker == "S1"
    assert segs[1].speaker == "S2"


def test_has_speakers():
    assert has_speakers([Segment(0, 1, "a", speaker="S1")]) is True
    assert has_speakers([Segment(0, 1, "a")]) is False


def test_speaker_coverage():
    from app.diarization import speaker_coverage
    segs = [Segment(0, 1, "a", speaker="S1"),
            Segment(1, 2, "b"),
            Segment(2, 3, "c", speaker="S2")]
    assert speaker_coverage(segs) == pytest.approx(2 / 3)
    assert speaker_coverage([]) == 0.0
    assert speaker_coverage([Segment(0, 1, "a")]) == 0.0


def test_distinct_speakers():
    segs = [Segment(0, 1, "a", speaker="S1"), Segment(1, 2, "b", speaker="S2"),
            Segment(2, 3, "c", speaker="S1")]
    assert distinct_speakers(segs) == ["S1", "S2"]


def test_get_diarization_provider():
    assert get_diarization_provider("placeholder").name == "placeholder"
    with pytest.raises(ValueError):
        get_diarization_provider("nope")
