"""role 模块（M2 角色识别）单元测试。"""
from app.asr import Segment
from app.role import identify_roles
from app.schemas import ROLE_HOST, ROLE_PARTICIPANT, ROLE_PRESENTER


def test_single_speaker_is_host():
    segs = [Segment(0, 1, "大家好，开会了"), Segment(1, 2, "继续")]
    roles = identify_roles(segs)
    assert len(roles) == 1
    assert roles[0].role == ROLE_HOST


def test_multi_speaker_roles():
    # S1 说话最多 → 主持人；S2 命中「汇报」句式 → 汇报人；其余 → 参会者
    segs = [
        Segment(0, 1, "大家好，会议开始", speaker="S1"),
        Segment(1, 2, "下面我给大家汇报一下进度", speaker="S2"),
        Segment(2, 3, "我来补充一下", speaker="S3"),
        Segment(3, 4, "好，接下来", speaker="S1"),
        Segment(4, 5, "继续汇报", speaker="S2"),
    ]
    roles = {s.name: s.role for s in identify_roles(segs)}
    assert roles["S1"] == ROLE_HOST
    assert roles["S2"] == ROLE_PRESENTER
    assert roles["S3"] == ROLE_PARTICIPANT


def test_empty():
    assert identify_roles([]) == []
