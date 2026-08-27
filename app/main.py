"""M1 · FastAPI 应用入口与 REST API；M2 扩展编辑/批注/历史检索；M3 生产化（鉴权/指标/成本/存储）。

路由（对应 tech-stack.md B4 + M3 + 需求变更·账号注册管控）：
  认证：  POST /api/auth/login
  管理：  POST /api/admin/users（管理员创建用户，require_admin 鉴权）
  任务：  POST /api/tasks（上传+异步执行）· GET /api/tasks · GET /api/tasks/{id}
          GET  /api/tasks/{id}/transcript · GET|PUT /api/tasks/{id}/minute
  批注：  POST|GET /api/tasks/{id}/comments · DELETE /api/tasks/{id}/comments/{cid}
  检索：  GET  /api/minutes
  成本：  GET  /api/costs
  可观测：GET /metrics（Prometheus）
  健康：  GET /health
  前端：  / · /minute.html · /login.html
"""
from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import audit, config, cost, db, ingestion, rag, storage
from app import metrics as metrics_mod
from app.auth import admin_create_user, ensure_admin_exists, get_current_user, login, require_admin
from app.worker import regen_minute, run_task


class JsonFormatter(logging.Formatter):
    """结构化 JSON 日志（TG-3）。"""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(UTC).isoformat(),
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
    ensure_admin_exists()
    logger.info("服务启动 data_dir=%s", config.DATA_DIR)
    yield


app = FastAPI(title="会议纪要助手", version="0.3.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")


# --------------------------------------------------------------------------- 请求级 trace（TG-3）
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


# --------------------------------------------------------------------------- 前端页面
@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/minute.html")
def minute_page() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "minute.html")


@app.get("/login.html")
def login_page() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "login.html")


# --------------------------------------------------------------------------- 健康与指标
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics")
def metrics_endpoint() -> Response:
    """Prometheus 指标端点（TG-3）。刷新状态 gauge 后输出。"""
    if config.METRICS_ENABLED:
        for status in (db.PENDING, db.RUNNING, db.SUCCEEDED, db.FAILED):
            metrics_mod.set_task_status_gauge(status, db.count_tasks_by_status(status))
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# --------------------------------------------------------------------------- 认证与管理（TG-4；需求变更：禁自助注册，改管理员创建用户）
@app.post("/api/admin/users", status_code=201)
def api_admin_create_user(payload: dict, request: Request,
                          admin: dict | None = Depends(require_admin)) -> dict:
    try:
        user = admin_create_user(payload.get("username", ""),
                                 payload.get("password", ""),
                                 is_admin=bool(payload.get("is_admin", False)))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    audit.log("admin_create_user", admin.get("id") if admin else None,
              user["username"], _ip(request))
    return {"user": user}


@app.post("/api/auth/login")
def api_login(payload: dict, request: Request) -> dict:
    try:
        result = login(payload.get("username", ""), payload.get("password", ""))
    except ValueError as e:
        audit.log("login_failed", None, (payload.get("username") or "")[:64], _ip(request))
        raise HTTPException(status_code=401, detail=str(e)) from e
    audit.log("login_success", result["user"]["id"], result["user"]["username"], _ip(request))
    return result


# --------------------------------------------------------------------------- 任务（TG-0/TG-2/TG-4）
def _enqueue(task_id: str, background_tasks: BackgroundTasks | None) -> None:
    """入队：USE_CELERY 时走 Celery+Redis；否则 FastAPI BackgroundTasks（本地开发）。"""
    if config.USE_CELERY:
        from app.celery_app import process_task
        process_task.delay(task_id)
    elif background_tasks is not None:
        background_tasks.add_task(run_task, task_id)
    else:
        run_task(task_id)


@app.post("/api/tasks", status_code=202)
async def create_task(background_tasks: BackgroundTasks, file: UploadFile,
                      request: Request,
                      user: dict | None = Depends(get_current_user)) -> dict:
    user_id = user["id"] if user else None
    filename = ingestion.sanitize_filename(file.filename or "upload")

    err = ingestion.validate_extension(filename)
    if err:
        raise HTTPException(status_code=400, detail=err)

    # 成本限额（可配置自动暂停新任务，默认关闭，避免误伤）
    if config.COST_AUTO_PAUSE:
        over, spent = cost.check_daily_limit(user_id=user_id)
        if over:
            raise HTTPException(status_code=429,
                                detail=f"当日成本已达限额 ¥{spent:.2f}，暂停新任务")

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

    # TG-4：文件魔数校验（扩展名与实际内容一致性）
    err = ingestion.validate_magic(stored)
    if err:
        stored.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=err)

    err = ingestion.validate_duration(stored)
    if err:
        stored.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=err)

    # TG-2：对象存储（S3 模式下上传，stored_path 存对象键；本地模式存本地路径）
    if storage.is_s3():
        stored_path = storage.get_storage().put_file(f"uploads/{task_id}{ext}", stored)
    else:
        stored_path = str(stored)

    task = db.create_task(task_id, filename, stored_path, user_id=user_id)
    metrics_mod.record_task_created(db.PENDING)
    audit.log("task_create", user_id, task_id, _ip(request))
    _enqueue(task_id, background_tasks)
    logger.info("task=%s 创建 file=%s size=%d user=%s", task_id, filename, size, user_id)
    return task


@app.get("/api/tasks")
def list_tasks(user: dict | None = Depends(get_current_user)) -> list[dict]:
    return db.list_tasks(user_id=user["id"] if user else None)


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, user: dict | None = Depends(get_current_user)) -> dict:
    task = db.get_task(task_id, user_id=user["id"] if user else None)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.get("/api/tasks/{task_id}/transcript")
def get_transcript(task_id: str, user: dict | None = Depends(get_current_user)) -> FileResponse:
    if not db.get_task(task_id, user_id=user["id"] if user else None):
        raise HTTPException(status_code=404, detail="任务不存在")
    p = config.TASK_DIR / task_id / "transcript.txt"
    if not p.exists():
        raise HTTPException(status_code=404, detail="转写文本尚未生成")
    return FileResponse(p, filename=f"{task_id}_transcript.txt", media_type="text/plain")


@app.get("/api/tasks/{task_id}/minute")
def get_minute(task_id: str, user: dict | None = Depends(get_current_user)) -> FileResponse:
    if not db.get_task(task_id, user_id=user["id"] if user else None):
        raise HTTPException(status_code=404, detail="任务不存在")
    task_dir = config.TASK_DIR / task_id
    edited = task_dir / "minutes.edited.md"
    generated = task_dir / "minutes.md"
    p = edited if edited.exists() else generated
    if not p.exists():
        raise HTTPException(status_code=404, detail="纪要尚未生成")
    return FileResponse(p, filename=f"{task_id}_minutes.md", media_type="text/markdown")


@app.put("/api/tasks/{task_id}/minute")
def update_minute(task_id: str, payload: dict,
                  request: Request,
                  user: dict | None = Depends(get_current_user)) -> dict:
    user_id = user["id"] if user else None
    if not db.get_task(task_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    if not db.get_minute(task_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="纪要尚未生成")
    markdown = payload.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise HTTPException(status_code=400, detail="markdown 不能为空")
    db.update_minute_edited(task_id, markdown)
    edited_path = config.TASK_DIR / task_id / "minutes.edited.md"
    edited_path.parent.mkdir(parents=True, exist_ok=True)
    edited_path.write_text(markdown, encoding="utf-8")
    audit.log("minute_edit", user_id, task_id, _ip(request))
    logger.info("task=%s 纪要已人工编辑", task_id)
    return {"task_id": task_id, "edited": True}


# --------------------------------------------------------------------------- 批注（M2/TG-4）
@app.post("/api/tasks/{task_id}/comments", status_code=201)
def add_comment(task_id: str, payload: dict,
                request: Request,
                user: dict | None = Depends(get_current_user)) -> dict:
    user_id = user["id"] if user else None
    if not db.get_task(task_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="批注内容不能为空")
    comment = db.add_comment(task_id, text,
                             author=(payload.get("author") or "").strip(),
                             quote=(payload.get("quote") or "").strip())
    audit.log("comment_add", user_id, comment.get("id", ""), _ip(request))
    return comment


@app.get("/api/tasks/{task_id}/comments")
def list_comments(task_id: str, user: dict | None = Depends(get_current_user)) -> list[dict]:
    if not db.get_task(task_id, user_id=user["id"] if user else None):
        raise HTTPException(status_code=404, detail="任务不存在")
    return db.list_comments(task_id)


@app.delete("/api/tasks/{task_id}/comments/{comment_id}")
def delete_comment(task_id: str, comment_id: str,
                   request: Request,
                   user: dict | None = Depends(get_current_user)) -> dict:
    user_id = user["id"] if user else None
    if not db.get_task(task_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    if not db.delete_comment(comment_id):
        raise HTTPException(status_code=404, detail="批注不存在")
    audit.log("comment_delete", user_id, comment_id, _ip(request))
    return {"deleted": True}


# --------------------------------------------------------------------------- 检索（M2/TG-4）
@app.get("/api/minutes")
def search_minutes(q: str = "", from_: str | None = Query(None, alias="from"),
                   to: str | None = None, topic: str | None = None,
                   user: dict | None = Depends(get_current_user)) -> list[dict]:
    return db.search_minutes(q, from_, to, topic,
                             user_id=user["id"] if user else None)


# --------------------------------------------------------------------------- 成本（TG-6）
@app.get("/api/costs")
def list_costs(day: str | None = None,
               user: dict | None = Depends(get_current_user)) -> dict:
    user_id = user["id"] if user else None
    stats = db.list_cost_stats(user_id=user_id, day=day)
    over, spent_today = cost.check_daily_limit(user_id=user_id)
    return {
        "stats": stats,
        "daily_spent_rmb": spent_today,
        "daily_limit_rmb": config.COST_LIMIT_DAILY_RMB,
        "over_limit": over,
        "per_task_limit_rmb": config.COST_LIMIT_PER_TASK_RMB,
        "auto_pause": config.COST_AUTO_PAUSE,
    }


# --------------------------------------------------------------------------- M4 · 检索问答（TG-3）
@app.post("/api/qa")
def api_qa(payload: dict, request: Request,
           user: dict | None = Depends(get_current_user)) -> dict:
    question = (payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    top_k = int(payload.get("top_k") or config.MMA_RAG_TOP_K)
    model = payload.get("model")  # 可选模型别名（v4-pro / v4-flash / qwen-plus）
    result = rag.answer(question, user_id=user["id"] if user else None,
                        top_k=top_k, model_alias=model)
    audit.log("qa_ask", user["id"] if user else None, question[:64], _ip(request))
    return result


# --------------------------------------------------------------------------- M4 · 重生成（TG-1）
@app.post("/api/tasks/{task_id}/regen")
def api_regen(task_id: str, payload: dict,
              request: Request,
              user: dict | None = Depends(get_current_user)) -> dict:
    user_id = user["id"] if user else None
    task = db.get_task(task_id, user_id=user_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.get("status") != db.SUCCEEDED:
        raise HTTPException(status_code=400, detail="任务尚未完成，无法重生成纪要")
    try:
        minute = regen_minute(task_id,
                              model_alias=payload.get("model"),
                              template=payload.get("template"))
    except (KeyError, RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    audit.log("minute_regen", user_id, task_id, _ip(request))
    return minute


def _ip(request: Request | None) -> str:
    if request is None or request.client is None:
        return ""
    return request.client.host or ""
