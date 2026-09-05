"""M3 · cost 模块 — LLM/ASR 用量采集、成本统计与限额判定（TG-6）。

成本模型见 docs/tech-stack.md A6（DeepSeek 官方价格，空闲档为默认）。
"""
from __future__ import annotations

from datetime import date

from app import config, db, metrics

# DeepSeek 价格（元 / 千 token，空闲档；A6 官方价 ÷1000）
DEEPSEEK_PRICE_PER_1K: dict[str, dict[str, float]] = {
    "deepseek-v4-pro": {"in": 0.0045, "out": 0.0135, "cache": 0.00015},
    "deepseek-v4-flash": {"in": 0.0015, "out": 0.0045, "cache": 0.00005},
}
_DEFAULT_PRICE = DEEPSEEK_PRICE_PER_1K["deepseek-v4-pro"]

# Qwen 价格（元 / 千 token）：qwen3.8-max 按阿里云百炼牌价 ÷1000（输入 12 / 输出 36 / 缓存命中 1.5，元/百万 tokens）；
# 2026-09-05 起为线上主模型（MMA_LLM_ALIAS=qwen3.8-max）。其他 qwen 型号牌价未核实前不在此登记（将回落默认价）。
QWEN_PRICE_PER_1K: dict[str, dict[str, float]] = {
    "qwen3.8-max": {"in": 0.012, "out": 0.036, "cache": 0.0015},
}

_ALL_LLM_PRICE_PER_1K: dict[str, dict[str, float]] = {**DEEPSEEK_PRICE_PER_1K, **QWEN_PRICE_PER_1K}

# ASR 价格（元 / 分钟）：腾讯云 16k_zh ~¥1.75/h
ASR_PRICE_PER_MIN = 1.75 / 60


def llm_cost_rmb(model: str, tokens_in: int, tokens_out: int,
                 tokens_cache: int = 0) -> float:
    """按 token 用量计算 LLM 成本（元）。按具体模型名单价查表（DeepSeek / Qwen），未知模型回落 DeepSeek 默认价。"""
    p = _ALL_LLM_PRICE_PER_1K.get(model, _DEFAULT_PRICE)
    return round(tokens_in * p["in"] / 1000.0
                 + tokens_out * p["out"] / 1000.0
                 + tokens_cache * p["cache"] / 1000.0, 6)


def asr_cost_rmb(audio_minutes: float) -> float:
    """按音频时长计算 ASR 成本（元）。"""
    return round(audio_minutes * ASR_PRICE_PER_MIN, 6)


def record_cost(task_id: str, user_id: str | None = None,
                llm_tokens_in: int = 0, llm_tokens_out: int = 0,
                llm_tokens_cache: int = 0, llm_cost: float = 0.0,
                asr_cost: float = 0.0, model: str = "") -> dict:
    """落一条成本记录到 cost_stats，并回填 metrics counter。"""
    stat = db.add_cost_stat(
        task_id=task_id, user_id=user_id,
        llm_tokens_in=llm_tokens_in, llm_tokens_out=llm_tokens_out,
        llm_tokens_cache=llm_tokens_cache,
        llm_cost_rmb=llm_cost, asr_cost_rmb=asr_cost)
    metrics.add_llm_tokens("input", llm_tokens_in)
    metrics.add_llm_tokens("output", llm_tokens_out)
    metrics.add_llm_tokens("cache", llm_tokens_cache)
    metrics.add_llm_cost(llm_cost)
    metrics.add_asr_cost(asr_cost)
    return stat


def check_daily_limit(user_id: str | None = None) -> tuple[bool, float]:
    """检查日成本是否超限。返回 (是否超限, 当日累计成本)。"""
    spent = db.daily_cost_rmb(user_id=user_id)
    return spent >= config.COST_LIMIT_DAILY_RMB, spent


def check_per_task_limit(cost_rmb: float) -> tuple[bool, float]:
    """检查单场成本是否超预算。返回 (是否超限, 阈值)。"""
    return cost_rmb > config.COST_LIMIT_PER_TASK_RMB, config.COST_LIMIT_PER_TASK_RMB


def today_key() -> str:
    return date.today().isoformat()
