"""M2 · extractor 模块 — 行动项 / 决议 / 未决问题结构化抽取（TG-1）。

抽象 `ExtractorProvider`：
- `DeepSeekExtractor`：主用 DeepSeek-V4 Pro（deepseek-v4-pro）走 Function-Calling / JSON Schema
  约束输出（对应 tech-stack.md A2「结构化输出」）。
- `RuleExtractor`：本地规则兜底（正则匹配「负责人 / 截止 / 待办 / 决议」关键词），
  无密钥时保证链路可跑通。

抽取结果解析为 Python 对象；非法 JSON / 缺字段时兜底重试或标「待定」（TG-1 / V7）。
"""
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod

from app import llm_registry as registry
from app.asr import Transcript
from app.schemas import (
    ActionItem,
    Decision,
    OpenQuestion,
    StructuredMinute,
    build_tool_schemas,
)
from app.security import guard_prompt

SYSTEM_PROMPT = (
    "你是会议纪要助手的结构化抽取器。请根据会议转写内容，用提供的函数抽取"
    "核心决议（extract_decisions）、行动项（extract_actions，含负责人/截止时间/优先级/状态，"
    "缺失字段填「待定」）与未决问题（extract_questions）。"
    "忠实转写内容，不要臆造原文没有的信息；无法确定时返回空数组。"
)

# 本地规则兜底用的关键词
_OWNER_RE = re.compile(r"(?:负责人|责任人|owner)[:：]?\s*([^\s，。；;,、:：]{1,10})")  # 负责人：张三
_OWNER_PREFIX_RE = re.compile(r"([^\s，。；;,、:：]{1,6}?)\s*(?:负责|跟进|牵头|主办)")  # 张三负责…
_DUE_RE = re.compile(r"(截止|截止时间|deadline|ddl|本周|下周|月底|月底前|今天|明天|后天)[:：]?\s*([^\s，。；;,、]{1,20})")
_DECISION_RE = re.compile(r"(决定|决议|确定|敲定|达成一致|结论|定了)[:：]?\s*(.{0,50})")
_QUESTION_RE = re.compile(r"(待定|待确认|未决|待跟进|再看|后面再|留待|后续)[:：]?\s*(.{0,50})")


def _parse_json_robust(text: str) -> dict | None:
    """尽力把一段文本解析为 JSON 对象。失败返回 None。"""
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass
    # 提取首个 {...} 块（容错 fenced / 前缀说明）
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


class ExtractorProvider(ABC):
    name = "base"
    model = ""

    @abstractmethod
    def extract(self, transcript: Transcript) -> StructuredMinute:
        """从转写内容抽取结构化纪要（决议 / 行动项 / 未决问题）。"""
        ...


# --------------------------------------------------------------------------- 云端（Function-Calling）
class OpenAILikeExtractor(ExtractorProvider):
    """OpenAI 兼容 Function-Calling 抽取（DeepSeek / Qwen 通用，注册表驱动）。"""

    def __init__(self, name: str, base_url: str, api_key: str, model: str):
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self._last_usage: dict[str, int] = {}
        if not self.api_key:
            raise RuntimeError(
                f"缺少 {name.upper()}_API_KEY。请在 .env 配置后重试（或改用 rule 兜底）。")

    @property
    def last_usage(self) -> dict[str, int]:
        """最近一次抽取的 token 用量（TG-6 成本采集）。"""
        return self._last_usage

    def _call_tools(self, text: str) -> dict:
        """一次 chat completion 携带三个抽取 tool，收集所有 tool call 参数。"""
        from openai import OpenAI  # lazy import

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": guard_prompt(text)},
            ],
            tools=build_tool_schemas(),
            tool_choice="auto",
            temperature=0.0,
        )
        usage = getattr(resp, "usage", None)
        if usage:
            from app.summary import OpenAILikeLLM
            self._last_usage = OpenAILikeLLM._usage_from_resp(usage)
        merged: dict = {"decisions": [], "actions": [], "open_questions": []}
        message = resp.choices[0].message
        for call in message.tool_calls or []:
            args = _parse_json_robust(getattr(call.function, "arguments", "") or "") or {}
            name = getattr(call.function, "name", "")
            if name == "extract_decisions":
                merged["decisions"] += args.get("decisions", [])
            elif name == "extract_actions":
                merged["actions"] += args.get("actions", [])
            elif name == "extract_questions":
                merged["open_questions"] += args.get("open_questions", [])
        return merged

    def extract(self, transcript: Transcript) -> StructuredMinute:
        t0 = time.time()
        text = transcript.text

        merged: dict = {"decisions": [], "actions": [], "open_questions": []}
        try:
            merged = self._call_tools(text)
        except Exception:  # noqa: BLE001 — 网络/接口异常时重试一次
            try:
                merged = self._call_tools(text)
            except Exception:
                merged = {"decisions": [], "actions": [], "open_questions": []}

        def _coerce_action(a) -> ActionItem:
            if isinstance(a, ActionItem):
                return a
            d = a if isinstance(a, dict) else {}
            return ActionItem(
                description=str(d.get("description", "")).strip(),
                owner=str(d.get("owner", "")).strip() or "待定",
                due=str(d.get("due", "")).strip() or "待定",
                priority=str(d.get("priority", "中")).strip() or "中",
                status=str(d.get("status", "待办")).strip() or "待办",
            )

        self.last_elapsed = time.time() - t0
        return StructuredMinute(
            title="",
            summary_md="",
            decisions=[Decision(**d) if isinstance(d, dict) else d
                       for d in merged.get("decisions", [])],
            actions=[_coerce_action(a) for a in merged.get("actions", [])],
            open_questions=[OpenQuestion(**q) if isinstance(q, dict) else q
                            for q in merged.get("open_questions", [])],
        )


class DeepSeekExtractor(OpenAILikeExtractor):
    name = "deepseek"

    def __init__(self, api_key: str = "", model: str = ""):
        spec = registry.resolve("v4-pro")
        super().__init__("deepseek", spec.base_url, api_key or spec.api_key,
                         model or spec.model)


class QwenExtractor(OpenAILikeExtractor):
    """Qwen 抽取（Function-Calling，注册表驱动）。"""

    name = "qwen"

    def __init__(self, api_key: str = "", model: str = ""):
        spec = registry.resolve("qwen-plus")
        super().__init__("qwen", spec.base_url, api_key or spec.api_key,
                         model or spec.model)


# --------------------------------------------------------------------------- 本地规则兜底
class RuleExtractor(ExtractorProvider):
    """本地规则抽取（无需密钥/联网）：按行正则匹配负责人 / 截止 / 决议 / 待办关键词。"""

    name = "rule"
    model = "rule-baseline"

    def extract(self, transcript: Transcript) -> StructuredMinute:
        t0 = time.time()
        text = transcript.text
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        decisions: list[Decision] = []
        actions: list[ActionItem] = []
        questions: list[OpenQuestion] = []

        for ln in lines:
            dm = _DECISION_RE.search(ln)
            if dm:
                decisions.append(Decision(conclusion=dm.group(1).strip() or "（未指明）"))
            om = _OWNER_RE.search(ln)
            if om:
                owner = om.group(1).strip()
            else:
                pm = _OWNER_PREFIX_RE.search(ln)
                owner = pm.group(1).strip() if pm else ""
            if owner:
                due_m = _DUE_RE.search(ln)
                due = (due_m.group(2).strip() if due_m else "待定")
                actions.append(ActionItem(description=ln, owner=owner, due=due))
            qm = _QUESTION_RE.search(ln)
            if qm:
                questions.append(OpenQuestion(question=qm.group(1).strip() or ln))

        self.last_elapsed = time.time() - t0
        return StructuredMinute(decisions=decisions, actions=actions, open_questions=questions)


EXTRACTORS = {
    "deepseek": DeepSeekExtractor,
    "qwen": QwenExtractor,
    "rule": RuleExtractor,
}


def get_extractor_provider(name: str, **kwargs) -> ExtractorProvider:
    if name in EXTRACTORS:
        return EXTRACTORS[name](**kwargs)
    # 未登记的别名 → 走模型注册表（支持任意 OpenAI 兼容 Function-Calling 模型，如 GPT/GLM/Kimi）
    spec = registry.resolve(name)  # 未知别名抛 ValueError
    return OpenAILikeExtractor(spec.provider, spec.base_url,
                               kwargs.get("api_key", "") or spec.api_key,
                               kwargs.get("model", "") or spec.model)


def has_cloud_credentials(name: str) -> bool:
    """判断抽取器是否已配置密钥（供降级判断）。rule 本地无需密钥。"""
    if name == "rule":
        return True
    try:
        return registry.resolve(name).available()
    except ValueError:
        return True
