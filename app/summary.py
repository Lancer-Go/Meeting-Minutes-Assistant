"""M1 · summary 模块 — 纪要生成（可插拔 LLM Provider）。

抽象 `LLMProvider`：deepseek / qwen 走 OpenAI 兼容接口（需密钥），全文单次调用（1M 上下文，无需分块）；
extractive 为本地抽取式基线（离线兜底）。主用 DeepSeek-V4 Pro（deepseek-v4-pro，由 M0 锁定的 DeepSeek-V3 升级）。
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from app import llm_registry as registry
from app.asr import Transcript
from app.security import guard_prompt

SYSTEM_PROMPT = (
    "你是会议纪要助手。请根据下面的会议转写内容生成会议纪要的正文，用中文输出 Markdown，"
    "包含「## 会议主题与基本信息」和「## 讨论要点」两个章节：\n"
    "1) 会议主题与基本信息（主题、形式、参与人、日期）；\n"
    "2) 讨论要点（按议题组织，忠实概括各议题的讨论内容）。\n"
    "忠实转写内容，不要臆造原文没有的信息。\n"
    "注意：核心决议、行动项、待跟进问题由结构化抽取器单独生成，正文无需重复输出。"
)


class LLMProvider(ABC):
    name = "base"
    model = ""

    @abstractmethod
    def summarize(self, transcript: Transcript) -> str:
        ...


# ---------------------------------------------------------------- 云 LLM
class OpenAILikeLLM(LLMProvider):
    """OpenAI 兼容接口（DeepSeek / Qwen / OpenAI）。全文单次调用（1M 上下文，无需分块）。"""

    def __init__(self, name: str, base_url: str, api_key: str, model: str,
                 temperature: float = 0.2):
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self._last_usage: dict[str, int] = {}
        if not self.api_key:
            raise RuntimeError(f"缺少 {name.upper()}_API_KEY。请在 .env 配置后重试。")

    @property
    def last_usage(self) -> dict[str, int]:
        """最近一次调用的 token 用量（TG-6 成本采集）。"""
        return self._last_usage

    @staticmethod
    def _usage_from_resp(usage) -> dict[str, int]:
        """从 OpenAI 兼容响应提取 input/output/cache token。"""
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", 0) or 0
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "cached_tokens": cached,
        }

    def _chat(self, system: str, user: str) -> str:
        from openai import OpenAI  # lazy import
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=self.temperature,
        )
        usage = getattr(resp, "usage", None)
        self._last_usage = self._usage_from_resp(usage) if usage else {}
        return resp.choices[0].message.content or ""

    def chat(self, system: str, user: str) -> str:
        """单轮对话（供 RAG 问答等复用）。"""
        return self._chat(system, user)

    def summarize(self, transcript: Transcript) -> str:
        """单次调用全文生成纪要（deepseek-v4-pro 1M 上下文，无需分块）。"""
        t0 = time.time()
        result = self._chat(SYSTEM_PROMPT, guard_prompt(transcript.text))
        self.last_elapsed = time.time() - t0
        return result


class DeepSeekLLM(OpenAILikeLLM):
    name = "deepseek"

    def __init__(self, api_key: str = "", model: str = ""):
        spec = registry.resolve("v4-pro")
        super().__init__("deepseek", spec.base_url,
                         api_key or spec.api_key,
                         model or spec.model)


class QwenLLM(OpenAILikeLLM):
    name = "qwen"

    def __init__(self, api_key: str = "", model: str = ""):
        spec = registry.resolve("qwen-plus")
        super().__init__("qwen", spec.base_url,
                         api_key or spec.api_key,
                         model or spec.model)


# ---------------------------------------------------------------- 本地基线
class ExtractiveLLM(LLMProvider):
    """本地抽取式基线（无需密钥/联网）：按时间窗挑代表性片段组织成纪要。

    用于离线跑通 pipeline，质量低于 LLM；接入密钥后自动升级为 LLM 纪要。
    """

    name = "extractive"
    model = "extractive-baseline"

    def __init__(self, window_s: float = 120.0):
        self.window_s = window_s

    def summarize(self, transcript: Transcript) -> str:
        t0 = time.time()
        segs = transcript.segments
        dur = segs[-1].end - segs[0].start if segs else 0.0
        lines = [
            "# 会议纪要（抽取式基线）",
            "",
            "> ⚠️ 本纪要由**本地抽取式算法**生成（未调用 LLM）。",
            "> 接入 `DEEPSEEK_API_KEY` 或 `QWEN_API_KEY` 后重跑即可升级为 LLM 纪要。",
            "",
            "## 会议基本信息",
            "",
            f"- 转写引擎：{transcript.provider} / {transcript.model}",
            f"- 会议时长：约 {dur / 60:.1f} 分钟",
            f"- 转写字符数：{transcript.char_count}",
            "",
            "## 讨论要点（按时间）",
            "",
        ]
        buckets: dict[int, object] = {}
        for s in segs:
            key = int(s.start // self.window_s)
            if s.text.strip() and (key not in buckets or len(s.text) > len(buckets[key].text)):
                buckets[key] = s
        for key in sorted(buckets):
            s = buckets[key]
            mm, ss = int(s.start // 60), s.start % 60
            lines.append(f"- **[{mm:02d}:{ss:05.2f}]** {s.text.strip()}")
        lines += [
            "",
            "## 全文转写（带时间戳附录）",
            "",
            "```text",
            transcript.to_timestamped_text(),
            "```",
        ]
        self.last_elapsed = time.time() - t0
        return "\n".join(lines)


LLM_PROVIDERS = {
    "deepseek": DeepSeekLLM,
    "qwen": QwenLLM,
    "extractive": ExtractiveLLM,
}


def get_llm_provider(name: str, **kwargs) -> LLMProvider:
    if name in LLM_PROVIDERS:
        return LLM_PROVIDERS[name](**kwargs)
    # 未登记的别名 → 走模型注册表（支持经 MMA_LLM_ALIASES 扩展的任意 OpenAI 兼容模型，如 GPT/GLM/Kimi）
    spec = registry.resolve(name)  # 未知别名抛 ValueError
    return OpenAILikeLLM(spec.provider, spec.base_url,
                         kwargs.get("api_key", "") or spec.api_key,
                         kwargs.get("model", "") or spec.model)


def has_cloud_credentials(name: str) -> bool:
    """判断指定 LLM 是否已配置密钥（供降级判断）。extractive 本地无需密钥。"""
    if name == "extractive":
        return True
    try:
        return registry.resolve(name).available()
    except ValueError:
        return True
