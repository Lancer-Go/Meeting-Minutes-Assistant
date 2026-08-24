"""M1 · FastAPI 应用入口与 REST API。

路由（对应 tech-stack.md B4）：
  POST /api/tasks                上传文件并创建任务（异步执行全链路）
  GET  /api/tasks                任务列表
  GET  /api/tasks/{id}           任务状态与进度
  GET  /api/tasks/{id}/transcript 转写文本下载
  GET  /api/tasks/{id}/minute     纪要 Markdown 下载
  GET  /health                   健康检查
  GET  /                         极简前端
"""
from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config, db, ingestion
from app.worker import run_task


class JsonFormatter(logging.Formatter):
    """结构化 JSON 日志（TG-7）。"""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def setup_logging() -> None:
    logger = logging.getLogger("mma")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(JsonFormatter())
        logger.addHandler(h)


setup_logging()
logger = logging.getLogger("mma.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    config.TASK_DIR.mkdir(parents=True, exist_ok=True)
    db.init_db()
    logger.info("服务启动 data_dir=%s", config.DATA_DIR)
    yield


app = FastAPI(title="会议纪要助手", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/tasks", status_code=202)
async def create_task(background_tasks: BackgroundTasks, file: UploadFile) -> dict:
    filename = file.filename or "upload"

    err = ingestion.validate_extension(filename)
    if err:
        raise HTTPException(status_code=400, detail=err)

    task_id = uuid.uuid4().hex
    ext = Path(filename).suffix.lower()
    stored = config.UPLOAD_DIR / f"{task_id}{ext}"

    # 流式写盘，累计大小校验（避免大文件占满内存）
    size = 0
    try:
        with stored.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > config.MAX_FILE_SIZE_BYTES:
                    raise HTTPException(status_code=400, detail=ingestion.validate_size(size))
                f.write(chunk)
    except HTTPException:
        stored.unlink(missing_ok=True)
        raise

    err = ingestion.validate_size(size)
    if err:
        stored.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=err)

    err = ingestion.validate_duration(stored)
    if err:
        stored.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=err)

    task = db.create_task(task_id, filename, str(stored))
    background_tasks.add_task(run_task, task_id)
    logger.info("task=%s 创建 file=%s size=%d", task_id, filename, size)
    return task


@app.get("/api/tasks")
def list_tasks() -> list[dict]:
    return db.list_tasks()


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.get("/api/tasks/{task_id}/transcript")
def get_transcript(task_id: str) -> FileResponse:
    if not db.get_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    p = config.TASK_DIR / task_id / "transcript.txt"
    if not p.exists():
        raise HTTPException(status_code=404, detail="转写文本尚未生成")
    return FileResponse(p, filename=f"{task_id}_transcript.txt", media_type="text/plain")


@app.get("/api/tasks/{task_id}/minute")
def get_minute(task_id: str) -> FileResponse:
    if not db.get_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    p = config.TASK_DIR / task_id / "minutes.md"
    if not p.exists():
        raise HTTPException(status_code=404, detail="纪要尚未生成")
    return FileResponse(p, filename=f"{task_id}_minutes.md", media_type="text/markdown")
