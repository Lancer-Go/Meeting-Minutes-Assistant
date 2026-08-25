"""M1 · orchestrator 模块 — 异步任务执行与重试。

供 FastAPI BackgroundTasks 调用：拉取任务 → 跑全链路 → 更新状态/进度。
关键步骤失败做指数退避重试，最终失败标记 failed 并记录 error。
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from app import config, db, pipeline

logger = logging.getLogger("mma.worker")

MAX_RETRIES = 3
RETRY_BACKOFF_S = [1.0, 2.0, 4.0]


def _persist_minute(task_id: str, out_dir: Path, title: str) -> None:
    """读取 pipeline 产物，持久化结构化纪要到 minutes 表（TG-0/TG-5）。"""
    try:
        import json
        sm_path = out_dir / "structured_minute.json"
        structured_json = sm_path.read_text(encoding="utf-8") if sm_path.exists() else "{}"
        md_path = out_dir / "minutes.md"
        summary_md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        db.save_minute(task_id, title=title, template=config.DEFAULT_TEMPLATE,
                       summary_md=summary_md, structured_json=structured_json)
    except Exception:  # noqa: BLE001 — 持久化失败不影响任务成功状态
        logger.exception("task=%s 持久化纪要失败（不阻断任务）", task_id)


def run_task(task_id: str) -> None:
    """后台执行单个任务的完整链路（含重试）。"""
    task = db.get_task(task_id)
    if not task:
        logger.error("task=%s 不存在，跳过", task_id)
        return

    stored = Path(task["stored_path"])
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
            _persist_minute(task_id, out_dir, title)
            db.set_progress(task_id, 100, "完成")
            db.set_status(task_id, db.SUCCEEDED)
            logger.info("task=%s 成功 cost=¥%s", task_id, metrics.get("total_cost_rmb"))
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_S[attempt - 1]
                logger.warning("task=%s 第 %d 次失败，%ds 后重试: %s", task_id, attempt, wait, e)
                time.sleep(wait)
            else:
                logger.exception("task=%s 最终失败", task_id)

    db.update_fields(task_id, error=str(last_err))
    db.set_status(task_id, db.FAILED)
