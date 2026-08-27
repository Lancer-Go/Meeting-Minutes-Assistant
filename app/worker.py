"""M1 · orchestrator 模块 — 异步任务执行与重试；M3 接入存储与成本（TG-0/TG-2/TG-6）。

本地开发供 FastAPI BackgroundTasks 调用；生产由 Celery worker（app/celery_app.py）调用。
拉取任务 → 解析输入（本地路径 / 对象存储键）→ 跑全链路 → 更新状态/进度 → 记录成本/指标。
关键步骤失败做指数退避重试，最终失败标记 failed 并记录 error。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from app import config, cost, db, pipeline, storage
from app import metrics as metrics_mod

logger = logging.getLogger("mma.worker")

MAX_RETRIES = 3
RETRY_BACKOFF_S = [1.0, 2.0, 4.0]


def _index_minute(task_id: str, user_id: str | None, summary_md: str) -> None:
    """M4 TG-2：纪要完成后自动向量化入库（失败不阻断主链路）。"""
    try:
        from app import embedding
        n = embedding.index_minute(task_id, user_id, summary_md)
        if n:
            logger.info("task=%s 纪要向量化 %d 块", task_id, n)
    except Exception:  # noqa: BLE001 — 向量化失败仅告警
        logger.exception("task=%s 纪要向量化失败（不阻断）", task_id)


def _persist_minute(task_id: str, out_dir: Path, title: str, user_id: str | None) -> None:
    """读取 pipeline 产物，持久化结构化纪要到 minutes 表（TG-0/TG-5）+ 向量化（M4 TG-2）。"""
    try:
        sm_path = out_dir / "structured_minute.json"
        structured_json = sm_path.read_text(encoding="utf-8") if sm_path.exists() else "{}"
        md_path = out_dir / "minutes.md"
        summary_md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        db.save_minute(task_id, title=title, template=config.DEFAULT_TEMPLATE,
                       summary_md=summary_md, structured_json=structured_json,
                       user_id=user_id)
        _index_minute(task_id, user_id, summary_md)
    except Exception:
        logger.exception("task=%s 持久化纪要失败（不阻断任务）", task_id)


def _resolve_input(stored_path: str, task_id: str) -> Path:
    """解析输入文件路径：本地绝对路径直接返回；S3 对象键则下载到任务工作目录。"""
    p = Path(stored_path)
    if not config.S3_ENDPOINT or p.is_absolute():
        return p
    dst = config.TASK_DIR / task_id / "input" / (p.name or "input")
    dst.parent.mkdir(parents=True, exist_ok=True)
    return storage.get_storage().to_local(stored_path, dst)


def run_task(task_id: str) -> None:
    """执行单个任务的完整链路（含重试）。"""
    task = db.get_task(task_id)
    if not task:
        logger.error("task=%s 不存在，跳过", task_id)
        return

    user_id = task.get("user_id")
    try:
        stored = _resolve_input(task["stored_path"], task_id)
    except Exception as e:
        logger.exception("task=%s 解析输入失败", task_id)
        db.update_fields(task_id, error=f"输入文件不可用: {e}")
        db.set_status(task_id, db.FAILED)
        return

    out_dir = config.TASK_DIR / task_id
    title = Path(task["source_file"]).stem

    def _progress(pct: int, msg: str) -> None:
        db.set_progress(task_id, pct, msg)

    try:
        db.set_status(task_id, db.RUNNING)
        logger.info("task=%s 开始处理 file=%s", task_id, task["source_file"])
    except Exception as e:
        logger.exception("task=%s 置 RUNNING 失败", task_id)
        db.update_fields(task_id, error=str(e))
        metrics_mod.inc_error("worker")
        return

    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            metrics = pipeline.run(
                stored, out_dir, config.DEFAULT_ASR, config.DEFAULT_LLM,
                title=title, progress_callback=_progress,
            )
            db.update_fields(
                task_id,
                audio_duration_min=metrics.get("audio_duration_min"),
                transcript_chars=metrics.get("transcript_chars"),
                cost_rmb=metrics.get("total_cost_rmb"),
            )
            # M2：持久化结构化纪要（minutes 表），供编辑 / 检索 / 评测使用
            _persist_minute(task_id, out_dir, title, user_id)
            # M3：成本统计（TG-6）+ 指标观测（TG-3）
            cost.record_cost(
                task_id, user_id=user_id,
                llm_tokens_in=metrics.get("llm_tokens_in", 0),
                llm_tokens_out=metrics.get("llm_tokens_out", 0),
                llm_tokens_cache=metrics.get("llm_tokens_cache", 0),
                llm_cost=metrics.get("llm_cost_rmb", 0.0),
                asr_cost=metrics.get("asr_cost_rmb", 0.0),
                model=metrics.get("llm", {}).get("model", ""),
            )
            # M3：对象存储同步（TG-2，S3 模式下上传任务产物）
            storage.get_storage().sync_dir(out_dir, f"tasks/{task_id}")
            db.set_progress(task_id, 100, "完成")
            db.set_status(task_id, db.SUCCEEDED)
            logger.info("task=%s 成功 cost=¥%s", task_id, metrics.get("total_cost_rmb"))
            return
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_S[attempt - 1]
                logger.warning("task=%s 第 %d 次失败，%ds 后重试: %s", task_id, attempt, wait, e)
                time.sleep(wait)
            else:
                logger.exception("task=%s 最终失败", task_id)
                metrics_mod.inc_error("pipeline")

    db.update_fields(task_id, error=str(last_err))
    db.set_status(task_id, db.FAILED)


def regen_minute(task_id: str, model_alias: str | None = None,
                 template: str | None = None) -> dict:
    """M4 TG-1：换模型/模板重生成纪要（summary + extractor + render + 重新向量化）。

    model_alias 为空时用 `config.MMA_LLM_ALIAS`（当前主模型）。返回更新后的纪要 dict。
    """
    from app import embedding
    from app.asr import Transcript
    from app.extractor import get_extractor_provider
    from app.render import render_minutes
    from app.role import identify_roles
    from app.schemas import StructuredMinute
    from app.summary import get_llm_provider

    task = db.get_task(task_id)
    if not task:
        raise KeyError(f"任务不存在: {task_id}")
    out_dir = config.TASK_DIR / task_id
    title = Path(task["source_file"]).stem
    user_id = task.get("user_id")

    tr_path = out_dir / "transcript.json"
    if not tr_path.exists():
        raise RuntimeError("转写尚未生成，无法重生成纪要")
    transcript = Transcript.from_dict(json.loads(tr_path.read_text(encoding="utf-8")))

    alias = model_alias or config.MMA_LLM_ALIAS
    template = template or config.DEFAULT_TEMPLATE

    llm_provider = get_llm_provider(alias)
    body_md = llm_provider.summarize(transcript)

    extractor_provider = get_extractor_provider(alias if alias != "extractive" else "rule")
    extracted = extractor_provider.extract(transcript)

    speakers = identify_roles(transcript.segments)
    structured = StructuredMinute(
        title=title, summary_md=body_md,
        decisions=extracted.decisions, actions=extracted.actions,
        open_questions=extracted.open_questions, speakers=speakers)
    (out_dir / "structured_minute.json").write_text(
        json.dumps(structured.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    meta = {"title": title, "created_at": datetime.now().isoformat(timespec="seconds"),
            "duration_min": task.get("audio_duration_min"),
            "asr": "", "regenerated_with": alias}
    transcript_text = transcript.to_timestamped_text(with_speaker=True)
    summary_md = render_minutes(structured, template, meta, transcript_text)
    (out_dir / "minutes.md").write_text(summary_md, encoding="utf-8")

    db.save_minute(task_id, title=title, template=template,
                   summary_md=summary_md,
                   structured_json=json.dumps(structured.to_dict(), ensure_ascii=False),
                   user_id=user_id)
    try:
        embedding.index_minute(task_id, user_id, summary_md)
    except Exception:  # noqa: BLE001 — 重新向量化失败不阻断
        logger.exception("task=%s regen 向量化失败（不阻断）", task_id)

    logger.info("task=%s regen alias=%s template=%s", task_id, alias, template)
    return db.get_minute(task_id, user_id=user_id) or {"task_id": task_id, "template": template}
