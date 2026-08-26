"""M2 · schemas 模块 — 结构化纪要数据模型（TG-0）。

定义结构化纪要的稳定契约，作为 extractor / render / 持久化的共同基础：
- `ActionItem`（决议描述 / 负责人 / 截止时间 / 优先级 / 状态）
- `Decision`（结论 / 依据）
- `OpenQuestion`（问题 / 待跟进）
- `Speaker`（说话人标识 / 角色）
- `StructuredMinute`（title / summary_md / decisions[] / actions[] / open_questions[] / speakers[]）

对应 tech-stack.md B4 `Minute` 实体。同时提供 Function-Calling 所需的 JSON Schema。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# 优先级 / 状态 / 角色 枚举值
PRIORITY_HIGH = "高"
PRIORITY_MEDIUM = "中"
PRIORITY_LOW = "低"
PRIORITIES = (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)

STATUS_TODO = "待办"
STATUS_DOING = "进行中"
STATUS_DONE = "已完成"
STATUSES = (STATUS_TODO, STATUS_DOING, STATUS_DONE)

ROLE_HOST = "主持人"
ROLE_PRESENTER = "汇报人"
ROLE_PARTICIPANT = "参会者"
ROLES = (ROLE_HOST, ROLE_PRESENTER, ROLE_PARTICIPANT)


@dataclass
class ActionItem:
    """行动项 / 决议事项（FR-05 细化）。缺失字段用「待定」占位。"""

    description: str = ""   # 事项 / 决议描述
    owner: str = ""         # 负责人
    due: str = ""           # 截止时间
    priority: str = PRIORITY_MEDIUM   # 优先级：高 / 中 / 低
    status: str = STATUS_TODO          # 状态：待办 / 进行中 / 已完成


@dataclass
class Decision:
    """核心决议 / 结论。"""

    conclusion: str = ""    # 结论
    basis: str = ""         # 依据（可选）


@dataclass
class OpenQuestion:
    """未决问题 / 待跟进事项。"""

    question: str = ""      # 问题
    follow_up: str = ""     # 待跟进（可选）


@dataclass
class Speaker:
    """说话人及其角色标注。"""

    name: str = ""          # 说话人标识（S1/S2 或真实姓名）
    role: str = ROLE_PARTICIPANT   # 主持人 / 汇报人 / 参会者


@dataclass
class StructuredMinute:
    """结构化纪要：与 `Transcript` 解耦但可互相引用。"""

    title: str = ""
    summary_md: str = ""                    # 纪要正文（讨论要点等）
    decisions: list[Decision] = field(default_factory=list)
    actions: list[ActionItem] = field(default_factory=list)
    open_questions: list[OpenQuestion] = field(default_factory=list)
    speakers: list[Speaker] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "summary_md": self.summary_md,
            "decisions": [asdict(d) for d in self.decisions],
            "actions": [asdict(a) for a in self.actions],
            "open_questions": [asdict(q) for q in self.open_questions],
            "speakers": [asdict(s) for s in self.speakers],
        }

    @classmethod
    def from_dict(cls, data: dict) -> StructuredMinute:
        d = data or {}
        return cls(
            title=d.get("title", ""),
            summary_md=d.get("summary_md", ""),
            decisions=[Decision(**x) for x in d.get("decisions", [])],
            actions=[ActionItem(**x) for x in d.get("actions", [])],
            open_questions=[OpenQuestion(**x) for x in d.get("open_questions", [])],
            speakers=[Speaker(**x) for x in d.get("speakers", [])],
        )


# --------------------------------------------------------------------------- Function-Calling JSON Schema
ACTION_ITEM_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "description": "行动项 / 决议事项描述"},
        "owner": {"type": "string", "description": "负责人，缺失填「待定」"},
        "due": {"type": "string", "description": "截止时间，缺失填「待定」"},
        "priority": {"type": "string", "enum": list(PRIORITIES), "description": "优先级"},
        "status": {"type": "string", "enum": list(STATUSES), "description": "状态"},
    },
    "required": ["description"],
}

DECISION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "conclusion": {"type": "string", "description": "结论内容"},
        "basis": {"type": "string", "description": "依据，可空"},
    },
    "required": ["conclusion"],
}

OPEN_QUESTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "未决问题"},
        "follow_up": {"type": "string", "description": "待跟进事项，可空"},
    },
    "required": ["question"],
}


def build_tool_schemas() -> list[dict]:
    """构建 extractor 用的 Function-Calling tool 定义（OpenAI 兼容）。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "extract_decisions",
                "description": "抽取会议的核心决议 / 结论",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "decisions": {"type": "array", "items": DECISION_JSON_SCHEMA},
                    },
                    "required": ["decisions"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "extract_actions",
                "description": "抽取会议的行动项（事项 / 负责人 / 截止时间 / 优先级 / 状态）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "actions": {"type": "array", "items": ACTION_ITEM_JSON_SCHEMA},
                    },
                    "required": ["actions"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "extract_questions",
                "description": "抽取会议的未决问题 / 待跟进事项",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "open_questions": {"type": "array", "items": OPEN_QUESTION_JSON_SCHEMA},
                    },
                    "required": ["open_questions"],
                },
            },
        },
    ]
