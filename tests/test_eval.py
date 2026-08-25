"""eval 指标（M2 质量评测）单元测试。"""
from eval.metrics import (
    action_item_completeness,
    evaluate,
    passed,
    rework_rate,
    speaker_accuracy,
)


def test_action_item_completeness_full():
    actions = [
        {"description": "做A", "owner": "张三", "due": "明天"},
        {"description": "做B", "owner": "李四", "due": "下周"},
    ]
    assert action_item_completeness(actions) == 1.0


def test_action_item_completeness_partial():
    actions = [
        {"description": "做A", "owner": "张三", "due": "明天"},
        {"description": "做B", "owner": "", "due": "待定"},
    ]
    assert action_item_completeness(actions) == 0.5


def test_action_item_completeness_empty():
    assert action_item_completeness([]) == 0.0


def test_speaker_accuracy_perfect():
    pred = [(0.0, 5.0, "S1"), (5.0, 10.0, "S2")]
    gold = [(0.0, 5.0, "S1"), (5.0, 10.0, "S2")]
    assert speaker_accuracy(pred, gold) == 1.0


def test_speaker_accuracy_half_wrong():
    pred = [(0.0, 5.0, "S1"), (5.0, 10.0, "S1")]
    gold = [(0.0, 5.0, "S1"), (5.0, 10.0, "S2")]
    assert speaker_accuracy(pred, gold) == 0.5


def test_speaker_accuracy_empty():
    assert speaker_accuracy([], [(0, 1, "S1")]) == 0.0
    assert speaker_accuracy([(0, 1, "S1")], []) == 0.0


def test_rework_rate_zero():
    assert rework_rate("abc", "abc") == 0.0


def test_rework_rate_full():
    assert rework_rate("abc", "xyz") > 0.5


def test_evaluate_and_thresholds():
    golden = {
        "actions": [{"description": "a", "owner": "x", "due": "y"}],
        "speaker_segments": [{"start": 0, "end": 5, "speaker": "S1"}],
        "minutes_md": "orig",
    }
    predicted = {
        "actions": [{"description": "a", "owner": "x", "due": "y"}],
        "segments": [{"start": 0, "end": 5, "speaker": "S1"}],
        "minutes_md": "orig",
        "edited_md": "",
    }
    m = evaluate(golden, predicted)
    assert m["action_item_completeness"] == 1.0
    assert m["speaker_accuracy"] == 1.0
    assert m["rework_rate"] == 0.0
    assert passed(m) is True


def test_evaluate_fails_threshold():
    golden = {"actions": [], "speaker_segments": [], "minutes_md": ""}
    predicted = {"actions": [], "segments": [], "minutes_md": "", "edited_md": ""}
    m = evaluate(golden, predicted)
    assert passed(m) is False
