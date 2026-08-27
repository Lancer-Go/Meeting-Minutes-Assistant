"""M1 · pipeline 模块 — 全链路编排与成本估算；M2 扩展结构化抽取 / 说话人 / 角色 / 模板渲染。

「音频提取 → 转写 → 说话人分离 → 角色识别 → 纪要 + 结构化抽取 → 模板渲染」端到端串联，
记录耗时/成本/字符数。云端密钥缺失时自动降级到离线兜底（whisper / extractive / rule），
保证链路可跑通。
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from app import audio, config, cost
from app import metrics as metrics_mod
from app.asr import get_asr_provider
from app.asr import has_cloud_credentials as asr_has_creds
from app.diarization import (
    assign_speakers,
    distinct_speakers,
    get_diarization_provider,
    has_speakers,
)
from app.extractor import get_extractor_provider
from app.extractor import has_cloud_credentials as extractor_has_creds
from app.render import render_minutes
from app.role import identify_roles
from app.schemas import StructuredMinute
from app.summary import get_llm_provider
from app.summary import has_cloud_credentials as llm_has_creds

# 估算价格（列表价，仅作量级估算，实际以账单为准）
ASR_PRICE_RMB_PER_MIN = {
    "whisper": 0.0,        # 本地免费
    "aliyun": 2.5 / 60,    # 阿里云录音文件识别 ~¥2.5/h → 每分钟
    "tencent": 1.75 / 60,  # 腾讯云 16k_zh ~¥1.75/h → 每分钟
    "iflytek": 2.0 / 60,   # 讯飞 ~¥2.0/h → 每分钟
}
LLM_PRICE_RMB_PER_1K_TOKENS = {
    "deepseek": 0.002,     # deepseek-v4-pro 输入 ~¥2/百万 token（估）
    "qwen": 0.002,         # qwen-plus 估
    "extractive": 0.0,
}


def estimate_cost(asr_name: str, audio_minutes: float,
                  llm_name: str, transcript_chars: int) -> tuple[float, float]:
    """估算 ASR 与 LLM 成本（量级，实际以账单为准）。返回 (asr_cost, llm_cost)。"""
    asr_cost = ASR_PRICE_RMB_PER_MIN.get(asr_name, 0.0) * audio_minutes
    # 中文约 1 字符 ≈ 1 token（估算上限）
    tokens = transcript_chars
    llm_cost = LLM_PRICE_RMB_PER_1K_TOKENS.get(llm_name, 0.0) * tokens / 1000
    return asr_cost, llm_cost


def resolve_asr_name(requested: str) -> str:
    """云端 ASR 无密钥时降级到本地 whisper。"""
    if requested != "whisper" and not asr_has_creds(requested):
        return config.ASR_FALLBACK
    return requested


def resolve_llm_name(requested: str) -> str:
    """云端 LLM 无密钥时降级到本地抽取式基线。"""
    if requested != "extractive" and not llm_has_creds(requested):
        return config.LLM_FALLBACK
    return requested


def resolve_extractor_name(requested: str) -> str:
    """云端抽取器无密钥时降级到本地规则兜底。"""
    if requested != "rule" and not extractor_has_creds(requested):
        return config.EXTRACTOR_FALLBACK
    return requested


def run(input_path: Path, out_dir: Path, asr_name: str, llm_name: str,
        title: str = "会议纪要", progress_callback=None,
        extractor_name: str | None = None, diarization_name: str | None = None,
        template_name: str | None = None) -> dict:
    """端到端跑通全链路，产物写入 out_dir，返回 metrics。

    progress_callback(percent: int, message: str) 在各阶段回调，用于进度展示。
    extractor_name / diarization_name / template_name 为空时取 config 默认。
    """
    asr_name = resolve_asr_name(asr_name)
    llm_name = resolve_llm_name(llm_name)
    extractor_name = resolve_extractor_name(extractor_name or config.DEFAULT_EXTRACTOR)
    diarization_name = diarization_name or config.DEFAULT_DIARIZATION
    template_name = template_name or config.DEFAULT_TEMPLATE
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def _report(pct: int, msg: str) -> None:
        if progress_callback:
            progress_callback(pct, msg)

    metrics = {"input": str(input_path), "started_at": datetime.now().isoformat(timespec="seconds")}

    # 1) 音频提取
    _report(5, "提取音频")
    t0 = time.time()
    wav = audio.extract_audio(input_path, out_dir / "audio.wav")
    metrics["audio_elapsed_s"] = round(time.time() - t0, 2)
    audio_minutes = audio.get_duration(wav) / 60

    # 2) 转写（按切片推进进度：腾讯云逐段识别，本地 whisper 按已处理时长）
    _report(20, "语音转写")
    asr_kwargs = {"model": config.WHISPER_MODEL} if asr_name == "whisper" else {}
    asr_provider = get_asr_provider(asr_name, **asr_kwargs)

    def _asr_progress(done: int, total: int) -> None:
        pct = 20 + int(60 * done / max(total, 1))
        if asr_name == "tencent":
            _report(pct, f"语音转写：第 {done}/{total} 段已完成")
        else:
            _report(pct, f"语音转写：已处理 {done}/{total} 秒")

    t0 = time.time()
    transcript = asr_provider.transcribe(wav, progress_callback=_asr_progress)
    metrics["asr_elapsed_s"] = round(time.time() - t0, 2)
    metrics_mod.observe_asr(metrics["asr_elapsed_s"])
    metrics_mod.add_asr_seconds(audio_minutes * 60)

    # 3) 说话人分离（M2）：云 ASR 未返回 speaker 时，走 diarization provider 兜底
    if not has_speakers(transcript.segments):
        try:
            diar = get_diarization_provider(diarization_name)
            assign_speakers(transcript.segments, diar.diarize(wav, transcript.segments))
            metrics["diarization"] = diarization_name
        except Exception as e:  # noqa: BLE001 — 兜底失败则占位标记 S1/S2/...
            from app.diarization import PlaceholderDiarization
            assign_speakers(transcript.segments,
                            PlaceholderDiarization().diarize(wav, transcript.segments))
            metrics["diarization"] = f"{diarization_name}(降级 placeholder): {e}"
    else:
        metrics["diarization"] = "cloud-asr-builtin"
    transcript.speakers = distinct_speakers(transcript.segments)

    (out_dir / "transcript.json").write_text(
        json.dumps(transcript.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "transcript.txt").write_text(transcript.to_timestamped_text(), encoding="utf-8")

    # 4) 角色识别（M2）
    speakers = identify_roles(transcript.segments)

    # 5) 纪要 + 结构化抽取（M2）
    _report(80, "生成纪要")
    llm_provider = get_llm_provider(llm_name)
    t0 = time.time()
    body_md = llm_provider.summarize(transcript)
    llm_elapsed = time.time() - t0

    extractor_provider = get_extractor_provider(extractor_name)
    t0 = time.time()
    extracted = extractor_provider.extract(transcript)
    extractor_elapsed = time.time() - t0

    # M3（TG-6）：采集 LLM / 抽取器 token 用量
    llm_usage = getattr(llm_provider, "last_usage", {}) or {}
    ext_usage = getattr(extractor_provider, "last_usage", {}) or {}
    tokens_in = llm_usage.get("prompt_tokens", 0) + ext_usage.get("prompt_tokens", 0)
    tokens_out = llm_usage.get("completion_tokens", 0) + ext_usage.get("completion_tokens", 0)
    tokens_cache = llm_usage.get("cached_tokens", 0) + ext_usage.get("cached_tokens", 0)
    metrics_mod.observe_minute(llm_elapsed + extractor_elapsed)

    structured = StructuredMinute(
        title=title,
        summary_md=body_md,
        decisions=extracted.decisions,
        actions=extracted.actions,
        open_questions=extracted.open_questions,
        speakers=speakers,
    )
    (out_dir / "structured_minute.json").write_text(
        json.dumps(structured.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    # 6) 模板渲染（M2）：默认「标准」，另输出精简/详细便于验收
    meta = {
        "title": title,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "duration_min": audio_minutes,
        "asr": f"{transcript.provider} / {transcript.model}",
    }
    transcript_text = transcript.to_timestamped_text(with_speaker=True)
    (out_dir / "minutes.md").write_text(
        render_minutes(structured, template_name, meta, transcript_text), encoding="utf-8")
    for tname in ("brief", "detailed"):
        (out_dir / f"minutes.{tname}.md").write_text(
            render_minutes(structured, tname, meta, transcript_text), encoding="utf-8")

    # 7) 指标汇总
    _, llm_cost_est = estimate_cost(asr_name, audio_minutes, llm_name, transcript.char_count)
    # M3（TG-6）：真实 token 成本（有 usage 时按 A6 价），否则沿用估算
    llm_model = getattr(llm_provider, "model", "") or ""
    if tokens_in or tokens_out or tokens_cache:
        llm_cost_real = cost.llm_cost_rmb(llm_model, tokens_in, tokens_out, tokens_cache)
    else:
        llm_cost_real = llm_cost_est
    asr_cost_real = cost.asr_cost_rmb(audio_minutes) if asr_name in ("tencent", "aliyun", "iflytek") else 0.0
    total_cost = round(llm_cost_real + asr_cost_real, 4)
    metrics.update({
        "audio_duration_min": round(audio_minutes, 2),
        "asr": {"provider": transcript.provider, "model": transcript.model,
                "elapsed_s": metrics["asr_elapsed_s"], "cost_rmb": round(asr_cost_real, 4)},
        "llm": {"provider": llm_name, "model": llm_model,
                "elapsed_s": round(llm_elapsed, 2), "cost_rmb": round(llm_cost_real, 4)},
        "extractor": {"provider": extractor_name,
                      "model": getattr(extractor_provider, "model", ""),
                      "elapsed_s": round(extractor_elapsed, 2)},
        "transcript_chars": transcript.char_count,
        "structured": {
            "n_decisions": len(structured.decisions),
            "n_actions": len(structured.actions),
            "n_open_questions": len(structured.open_questions),
            "n_speakers": len(structured.speakers),
        },
        "total_elapsed_s": round(metrics["audio_elapsed_s"] + metrics["asr_elapsed_s"]
                                 + llm_elapsed + extractor_elapsed, 2),
        "total_cost_rmb": total_cost,
        "llm_tokens_in": tokens_in,
        "llm_tokens_out": tokens_out,
        "llm_tokens_cache": tokens_cache,
        "llm_cost_rmb": round(llm_cost_real, 6),
        "asr_cost_rmb": round(asr_cost_real, 6),
        "ratio_elapsed_to_duration": round(
            (metrics["audio_elapsed_s"] + metrics["asr_elapsed_s"] + llm_elapsed + extractor_elapsed)
            / max(audio_minutes * 60, 1e-6), 3),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    _report(100, "完成")
    return metrics
