"""TG-4 · 纪要生成。

转写文本 → 结构化 Markdown 纪要。抽象 `LLMProvider`：
- `deepseek` / `qwen`：OpenAI 兼容接口（需密钥），全文单次调用。
- `extractive`：本地抽取式基线（无需密钥、无需联网），用于离线跑通。

用法:
    python summarize.py <transcript.json> [--llm deepseek|qwen|extractive] [--out minutes.md]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path

from asr import Segment, Transcript

SYSTEM_PROMPT = (
    "你是会议纪要助手。请根据下面的会议转写内容生成结构化会议纪要，用中文输出 Markdown，包含：\n"
    "1) 会议主题与基本信息；2) 核心结论/决议；3) 讨论要点摘要；\n"
    "4) 行动项清单（负责人、事项、优先级、截止时间，缺失则标注「待定」）；5) 待跟进/未决问题。\n"
    "忠实转写内容，不要臆造原文没有的信息。"
)


class LLMProvider(ABC):
    name = "base"
    model = ""

    @abstractmethod
    def summarize(self, transcript: Transcript) -> str:
        ...


# ---------------------------------------------------------------- 云 LLM
class OpenAILikeLLM(LLMProvider):
    """OpenAI 兼容接口（DeepSeek / Qwen / OpenAI）。全文单次调用。"""

    def __init__(self, name: str, base_url: str, api_key: str, model: str,
                 temperature: float = 0.2):
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        if not self.api_key:
            raise RuntimeError(f"缺少 {name.upper()}_API_KEY。请在 .env 配置后重试。")

    def _chat(self, system: str, user: str) -> str:
        from openai import OpenAI  # lazy import
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=self.temperature,
        )
        return resp.choices[0].message.content or ""

    def summarize(self, transcript: Transcript) -> str:
        t0 = time.time()
        result = self._chat(SYSTEM_PROMPT, transcript.text)
        self.last_elapsed = time.time() - t0
        return result


class DeepSeekLLM(OpenAILikeLLM):
    name = "deepseek"

    def __init__(self, api_key: str = "", model: str = ""):
        import config
        super().__init__("deepseek", "https://api.deepseek.com",
                         api_key or config.DEEPSEEK_API_KEY,
                         model or config.DEEPSEEK_MODEL)


class QwenLLM(OpenAILikeLLM):
    name = "qwen"

    def __init__(self, api_key: str = "", model: str = "qwen-plus"):
        import config
        super().__init__("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1",
                         api_key or config.QWEN_API_KEY, model)


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
        # 按时间窗挑选最长的一句作为代表
        buckets: dict[int, Segment] = {}
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
    if name not in LLM_PROVIDERS:
        raise ValueError(f"未知 LLM provider: {name}（可选 {list(LLM_PROVIDERS)}）")
    return LLM_PROVIDERS[name](**kwargs)


def load_transcript(path: Path) -> Transcript:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    segs = [Segment(s["start"], s["end"], s["text"]) for s in data.get("segments", [])]
    return Transcript(segments=segs, text=data.get("text", ""),
                      provider=data.get("provider", ""), model=data.get("model", ""))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TG-4 纪要生成")
    ap.add_argument("transcript", help="转写 JSON（asr.py 输出）")
    ap.add_argument("--llm", default="extractive", choices=list(LLM_PROVIDERS))
    ap.add_argument("--out", default="", help="输出 Markdown 路径（默认打印到 stdout）")
    args = ap.parse_args(argv)

    t = load_transcript(Path(args.transcript))
    provider = get_llm_provider(args.llm)
    try:
        md = provider.summarize(t)
    except RuntimeError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"已写入: {args.out}")
    else:
        print(md)
    print(f"[{provider.name}/{provider.model}] 耗时 {getattr(provider, 'last_elapsed', 0):.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
