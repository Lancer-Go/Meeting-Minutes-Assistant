"""M1 · FastAPI 应用入口与 REST API；M2 扩展编辑/批注/历史检索。

路由（对应 tech-stack.md B4）：
  POST /api/tasks                上传文件并创建任务（异步执行全链路）
  GET  /api/tasks                任务列表
  GET  /api/tasks/{id}           任务状态与进度
  GET  /api/tasks/{id}/transcript 转写文本下载
  GET  /api/tasks/{id}/minute     纪要 Markdown 下载（编辑后返回编辑内容）
  PUT  /api/tasks/{id}/minute     保存人工编辑后的纪要（M2 TG-5）
  POST /api/tasks/{id}/comments   新增批注（M2 TG-5）
  GET  /api/tasks/{id}/comments   批注列表（M2 TG-5）
  DELETE /api/tasks/{id}/comments/{comment_id} 删除批注（M2 TG-5）
  GET  /api/minutes              纪要历史列表 / 搜索（M2 TG-6）
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

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
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


@app.get("/minute.html")
def minute_page() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "minute.html")


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
    task_dir = config.TASK_DIR / task_id
    edited = task_dir / "minutes.edited.md"
    generated = task_dir / "minutes.md"
    p = edited if edited.exists() else generated
    if not p.exists():
        raise HTTPException(status_code=404, detail="纪要尚未生成")
    return FileResponse(p, filename=f"{task_id}_minutes.md", media_type="text/markdown")


@app.put("/api/tasks/{task_id}/minute")
def update_minute(task_id: str, payload: dict) -> dict:
    """保存人工编辑后的纪要 Markdown（TG-5）。"""
    if not db.get_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    if not db.get_minute(task_id):
        raise HTTPException(status_code=404, detail="纪要尚未生成")
    markdown = payload.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise HTTPException(status_code=400, detail="markdown 不能为空")
    db.update_minute_edited(task_id, markdown)
    edited_path = config.TASK_DIR / task_id / "minutes.edited.md"
    edited_path.parent.mkdir(parents=True, exist_ok=True)
    edited_path.write_text(markdown, encoding="utf-8")
    logger.info("task=%s 纪要已人工编辑", task_id)
    return {"task_id": task_id, "edited": True}


@app.post("/api/tasks/{task_id}/comments", status_code=201)
def add_comment(task_id: str, payload: dict) -> dict:
    if not db.get_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="批注内容不能为空")
    return db.add_comment(task_id, text,
                          author=(payload.get("author") or "").strip(),
                          quote=(payload.get("quote") or "").strip())


@app.get("/api/tasks/{task_id}/comments")
def list_comments(task_id: str) -> list[dict]:
    if not db.get_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return db.list_comments(task_id)


@app.delete("/api/tasks/{task_id}/comments/{comment_id}")
def delete_comment(task_id: str, comment_id: str) -> dict:
    if not db.get_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    if not db.delete_comment(comment_id):
        raise HTTPException(status_code=404, detail="批注不存在")
    return {"deleted": True}


@app.get("/api/minutes")
def search_minutes(q: str = "", from_: str | None = Query(None, alias="from"),
                   to: str | None = None, topic: str | None = None) -> list[dict]:
    """纪要历史列表 / 搜索（TG-6）：q 关键词、from/to 时间、topic 主题。"""
    return db.search_minutes(q, from_, to, topic)
