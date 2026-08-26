"""M3 · Celery 应用与任务（TG-0）。

生产队列：API 入队、worker 消费、复用 `app/worker.run_task` 执行全链路。
仅当 `config.USE_CELERY` 为 True 时接入；本地开发回退 FastAPI BackgroundTasks。
"""
from __future__ import annotations

from celery import Celery

from app import config


def make_celery() -> Celery:
    c = Celery("mma", broker=config.REDIS_URL, backend=config.REDIS_URL)
    c.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        task_acks_late=True,           # 任务完成后才 ack，避免 worker 崩溃丢任务
        worker_prefetch_multiplier=1,  # 公平调度，长任务不独占
        task_time_limit=config.MAX_DURATION_SECONDS * 3 + 600,
    )
    return c


celery = make_celery()


@celery.task(name=config.CELERY_TASK_NAME, bind=True, max_retries=0)
def process_task(self, task_id: str) -> dict:
    """Celery 任务入口：执行单个任务完整链路（状态回写由 run_task 完成）。"""
    from app.worker import run_task
    run_task(task_id)
    return {"task_id": task_id}
