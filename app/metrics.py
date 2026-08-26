"""M3 · metrics 模块 — Prometheus 指标（TG-3）。

任务数 / 状态计数、转写与纪要耗时 histogram、错误率、LLM token 用量与成本 counter
（供 TG-6 复用）。由 `app/main.py` 暴露 `GET /metrics`。
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

TASKS_CREATED = Counter(
    "mma_tasks_created_total", "任务创建总数", ["status"])
TASKS_STATUS = Gauge(
    "mma_tasks_status", "当前各状态任务数", ["status"])
ASR_DURATION = Histogram(
    "mma_asr_duration_seconds", "语音转写耗时（秒）",
    buckets=[1, 5, 15, 30, 60, 120, 300, 600, 1200, 2400])
MINUTE_DURATION = Histogram(
    "mma_minute_duration_seconds", "纪要生成耗时（秒）",
    buckets=[1, 5, 15, 30, 60, 120, 300, 600])
ERRORS = Counter(
    "mma_errors_total", "错误总数", ["stage"])
LLM_TOKENS = Counter(
    "mma_llm_tokens_total", "LLM token 用量", ["kind"])  # input / output / cache
LLM_COST = Counter(
    "mma_llm_cost_rmb_total", "LLM 成本（元）")
ASR_COST = Counter(
    "mma_asr_cost_rmb_total", "ASR 成本（元）")
ASR_AUDIO_SECONDS = Counter(
    "mma_asr_audio_seconds_total", "转写音频秒数")
QUEUE_DEPTH = Gauge(
    "mma_queue_depth", "队列积压任务数")


# --------------------------------------------------------------------------- 记录辅助
def record_task_created(status: str) -> None:
    TASKS_CREATED.labels(status=status).inc()


def set_task_status_gauge(status: str, count: int) -> None:
    TASKS_STATUS.labels(status=status).set(count)


def observe_asr(seconds: float) -> None:
    ASR_DURATION.observe(seconds)


def observe_minute(seconds: float) -> None:
    MINUTE_DURATION.observe(seconds)


def inc_error(stage: str) -> None:
    ERRORS.labels(stage=stage).inc()


def add_llm_tokens(kind: str, n: int) -> None:
    if n:
        LLM_TOKENS.labels(kind=kind).inc(n)


def add_llm_cost(rmb: float) -> None:
    LLM_COST.inc(rmb)


def add_asr_cost(rmb: float) -> None:
    ASR_COST.inc(rmb)


def add_asr_seconds(seconds: float) -> None:
    ASR_AUDIO_SECONDS.inc(seconds)
