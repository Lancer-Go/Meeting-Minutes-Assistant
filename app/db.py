"""M1 · storage 模块 — 数据模型与状态机；M2 扩展 minutes / comments 表；M3 迁 SQLAlchemy 双模式。

FR-07：任务持久化与状态追踪。状态机：pending → running → succeeded / failed。
M2：纪要持久化（minutes 表）与批注（comments 表）。
M3（TG-2/TG-4/TG-6）：标准库 sqlite3 → SQLAlchemy 双模式（sqlite:// 本地 / postgresql:// 生产），
新增 users / audit_logs / cost_stats 表，tasks 增 user_id 越权隔离。

对外函数签名与返回 dict 形状保持与 M1/M2 一致（向后兼容，既有测试不改）。
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session

from app import config

PENDING = "pending"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"

VALID_TRANSITIONS: dict[str, set[str]] = {
    PENDING: {RUNNING, FAILED},
    RUNNING: {SUCCEEDED, FAILED},
    SUCCEEDED: set(),
    FAILED: set(),
}


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    source_file = Column(String, nullable=False)
    stored_path = Column(String)
    user_id = Column(String, index=True, nullable=True)  # M3 越权隔离（任务创建者）
    status = Column(String, nullable=False, default=PENDING)
    progress = Column(Float, default=0.0)
    progress_message = Column(Text)
    error = Column(Text)
    audio_duration_min = Column(Float)
    transcript_chars = Column(Integer)
    cost_rmb = Column(Float)
    created_at = Column(String)
    started_at = Column(String)
    finished_at = Column(String)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Minute(Base):
    __tablename__ = "minutes"

    task_id = Column(String, primary_key=True)
    title = Column(String)
    template = Column(String, default="standard")
    summary_md = Column(Text)
    structured_json = Column(Text)
    edited_md = Column(Text)
    updated_at = Column(String)
    user_id = Column(String, index=True, nullable=True)  # M3 归属（冗余，便于按用户检索）

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Comment(Base):
    __tablename__ = "comments"

    id = Column(String, primary_key=True)
    task_id = Column(String, nullable=False, index=True)
    author = Column(String)
    text = Column(Text, nullable=False)
    quote = Column(Text)
    created_at = Column(String)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(String)

    def to_dict(self) -> dict:
        return {"id": self.id, "username": self.username, "created_at": self.created_at}


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=True)
    action = Column(String, nullable=False)
    target = Column(String)
    ip = Column(String)
    created_at = Column(String)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class CostStat(Base):
    __tablename__ = "cost_stats"

    id = Column(String, primary_key=True)
    task_id = Column(String, index=True)
    user_id = Column(String, index=True, nullable=True)
    date = Column(String, index=True)  # YYYY-MM-DD
    llm_tokens_in = Column(Integer, default=0)
    llm_tokens_out = Column(Integer, default=0)
    llm_tokens_cache = Column(Integer, default=0)
    llm_cost_rmb = Column(Float, default=0.0)
    asr_cost_rmb = Column(Float, default=0.0)
    total_cost_rmb = Column(Float, default=0.0)
    created_at = Column(String)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class MinuteEmbedding(Base):
    """M4 · 纪要向量块（TG-2）：纪要正文按 chunk 切分后的向量索引。

    `embedding` 存 JSON 数组文本（跨 SQLite/PG 通用）；生产 PG 已启用 pgvector 扩展，
    检索侧用 Python 余弦计算（见 app/rag.py），可迁移为原生 vector 列提升规模。
    """

    __tablename__ = "minute_embeddings"

    id = Column(String, primary_key=True)
    minute_id = Column(String, index=True)   # = minutes.task_id（本仓库 minutes 主键即 task_id）
    task_id = Column(String, index=True)
    user_id = Column(String, index=True, nullable=True)  # 越权隔离（同 minutes）
    chunk_index = Column(Integer, default=0)
    text = Column(Text)
    embedding = Column(Text)  # JSON 数组字符串，如 "[0.1, 0.2, ...]"
    created_at = Column(String)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


# --------------------------------------------------------------------------- 引擎与会话管理
_engines: dict[str, Engine] = {}


def _db_url(db_path: Path | None = None) -> str:
    """解析数据库 URL：db_path 优先（测试用 sqlite 文件），否则 DATABASE_URL 或默认 SQLite。"""
    if db_path is not None:
        return "sqlite:///" + str(Path(db_path).resolve()).replace("\\", "/")
    if config.DATABASE_URL:
        return config.DATABASE_URL
    return "sqlite:///" + str(Path(config.DB_PATH).resolve()).replace("\\", "/")


def _engine(db_path: Path | None = None) -> Engine:
    url = _db_url(db_path)
    if url not in _engines:
        kwargs: dict = {"future": True}
        if url.startswith("sqlite"):
            db_file = url[len("sqlite:///"):]
            if db_file and db_file != ":memory:":
                Path(db_file).parent.mkdir(parents=True, exist_ok=True)
            kwargs["connect_args"] = {"check_same_thread": False}
        _engines[url] = create_engine(url, **kwargs)
    return _engines[url]


def _session(db_path: Path | None = None) -> Session:
    return Session(_engine(db_path), expire_on_commit=False)


# --------------------------------------------------------------------------- 迁移（轻量补列）
_MISSING_COLUMNS = {
    "tasks": {"user_id": Column("user_id", String)},
    "minutes": {"user_id": Column("user_id", String)},
}


def init_db(db_path: Path | None = None) -> None:
    """建表（幂等），并为旧库补充 M3 新增列（user_id）。"""
    engine = _engine(db_path)
    Base.metadata.create_all(engine)
    # 为既有表补列（SQLite / PG 均支持 ADD COLUMN）
    from sqlalchemy import inspect
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _MISSING_COLUMNS.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, col in cols.items():
                if name not in existing:
                    ddl = f'ALTER TABLE {table} ADD COLUMN {name} {col.type.compile(engine.dialect)}'
                    conn.exec_driver_sql(ddl)


# --------------------------------------------------------------------------- tasks 表
def create_task(task_id: str, source_file: str, stored_path: str = "",
                user_id: str | None = None, db_path: Path | None = None) -> dict:
    with _session(db_path) as s:
        s.add(Task(id=task_id, source_file=source_file, stored_path=stored_path,
                   user_id=user_id, status=PENDING, progress=0.0, created_at=_now()))
        s.commit()
    return get_task(task_id, db_path=db_path) or {}


def get_task(task_id: str, user_id: str | None = None, db_path: Path | None = None) -> dict | None:
    with _session(db_path) as s:
        row = s.get(Task, task_id)
        if row is None:
            return None
        if user_id is not None and row.user_id != user_id:
            return None  # 越权隔离：不属于该用户 → 视为不存在
        return row.to_dict()


def list_tasks(user_id: str | None = None, db_path: Path | None = None) -> list[dict]:
    with _session(db_path) as s:
        stmt = select(Task)
        if user_id is not None:
            stmt = stmt.where(Task.user_id == user_id)
        rows = s.execute(stmt.order_by(Task.created_at.desc())).scalars().all()
        return [r.to_dict() for r in rows]


def count_tasks_by_status(status: str, user_id: str | None = None,
                          db_path: Path | None = None) -> int:
    """按状态统计任务数（供 /metrics 状态 gauge 刷新）。"""
    with _session(db_path) as s:
        stmt = select(func.count()).select_from(Task).where(Task.status == status)
        if user_id is not None:
            stmt = stmt.where(Task.user_id == user_id)
        return int(s.execute(stmt).scalar() or 0)


def _set_status(session: Session, task_id: str, new_status: str) -> None:
    task = session.get(Task, task_id)
    if task is None:
        raise KeyError(f"任务不存在: {task_id}")
    cur = task.status
    if new_status != cur and new_status not in VALID_TRANSITIONS.get(cur, set()):
        raise ValueError(f"非法状态流转: {cur} → {new_status}")
    task.status = new_status


def set_status(task_id: str, new_status: str, db_path: Path | None = None) -> dict:
    """按状态机更新任务状态，并自动填 started_at / finished_at。"""
    with _session(db_path) as s:
        _set_status(s, task_id, new_status)
        task = s.get(Task, task_id)
        now = _now()
        if new_status == RUNNING:
            task.started_at = task.started_at or now
        elif new_status in (SUCCEEDED, FAILED):
            task.finished_at = now
        s.commit()
    return get_task(task_id, db_path=db_path) or {}


def set_progress(task_id: str, progress: float, message: str | None = None,
                 db_path: Path | None = None) -> None:
    """更新任务进度（0–100），可选附带进度说明（如「第 12/48 段已完成」）。"""
    progress = max(0.0, min(100.0, float(progress)))
    with _session(db_path) as s:
        task = s.get(Task, task_id)
        if task is None:
            return
        task.progress = progress
        if message is not None:
            task.progress_message = message
        s.commit()


def update_fields(task_id: str, db_path: Path | None = None, **fields) -> dict:
    """更新任意字段（白名单内）。"""
    allowed = {"error", "audio_duration_min", "transcript_chars", "cost_rmb", "stored_path"}
    cols = {k: v for k, v in fields.items() if k in allowed}
    if not cols:
        return get_task(task_id, db_path=db_path) or {}
    with _session(db_path) as s:
        s.execute(update(Task).where(Task.id == task_id).values(**cols))
        s.commit()
    return get_task(task_id, db_path=db_path) or {}


# --------------------------------------------------------------------------- M2 · minutes 表（TG-0/TG-5/TG-6）
def save_minute(task_id: str, title: str = "", template: str = "standard",
                summary_md: str = "", structured_json: str = "",
                edited_md: str | None = None, user_id: str | None = None,
                db_path: Path | None = None) -> dict:
    """UPSERT 一条纪要记录。edited_md 为 None 时保留原值。"""
    with _session(db_path) as s:
        now = _now()
        m = s.get(Minute, task_id)
        if m is None:
            m = Minute(task_id=task_id)
            s.add(m)
        m.title = title
        m.template = template
        m.summary_md = summary_md
        m.structured_json = structured_json
        if edited_md is not None:
            m.edited_md = edited_md
        if user_id is not None:
            m.user_id = user_id
        m.updated_at = now
        s.commit()
    return get_minute(task_id, db_path=db_path) or {}


def get_minute(task_id: str, user_id: str | None = None, db_path: Path | None = None) -> dict | None:
    with _session(db_path) as s:
        row = s.get(Minute, task_id)
        if row is None:
            return None
        if user_id is not None and row.user_id != user_id:
            return None
        return row.to_dict()


def update_minute_edited(task_id: str, edited_md: str, db_path: Path | None = None) -> dict:
    """保存人工编辑后的纪要 Markdown（TG-5）。"""
    with _session(db_path) as s:
        m = s.get(Minute, task_id)
        if m is None:
            raise KeyError(f"纪要不存在: {task_id}")
        m.edited_md = edited_md
        m.updated_at = _now()
        s.commit()
    return get_minute(task_id, db_path=db_path) or {}


def list_minutes(user_id: str | None = None, db_path: Path | None = None) -> list[dict]:
    with _session(db_path) as s:
        stmt = select(Minute)
        if user_id is not None:
            stmt = stmt.where(Minute.user_id == user_id)
        rows = s.execute(stmt.order_by(Minute.updated_at.desc())).scalars().all()
        return [r.to_dict() for r in rows]


def search_minutes(q: str = "", from_: str | None = None, to: str | None = None,
                   topic: str | None = None, user_id: str | None = None,
                   db_path: Path | None = None) -> list[dict]:
    """按关键词 / 时间范围 / 主题检索纪要（TG-6，LIKE）。"""
    stmt = select(Minute)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            Minute.title.like(like) | Minute.summary_md.like(like)
             | Minute.edited_md.like(like) | Minute.structured_json.like(like))
    if topic:
        stmt = stmt.where(Minute.title.like(f"%{topic}%"))
    if from_:
        stmt = stmt.where(Minute.updated_at >= from_)
    if to:
        stmt = stmt.where(Minute.updated_at <= to)
    if user_id is not None:
        stmt = stmt.where(Minute.user_id == user_id)
    with _session(db_path) as s:
        rows = s.execute(stmt.order_by(Minute.updated_at.desc())).scalars().all()
        return [r.to_dict() for r in rows]


# --------------------------------------------------------------------------- M2 · comments 表（TG-5）
def add_comment(task_id: str, text: str, author: str = "", quote: str = "",
                db_path: Path | None = None) -> dict:
    cid = uuid.uuid4().hex
    with _session(db_path) as s:
        s.add(Comment(id=cid, task_id=task_id, author=author, text=text,
                      quote=quote, created_at=_now()))
        s.commit()
    return _get_comment(cid, db_path) or {}


def _get_comment(comment_id: str, db_path: Path | None = None) -> dict | None:
    with _session(db_path) as s:
        row = s.get(Comment, comment_id)
        return row.to_dict() if row else None


def list_comments(task_id: str, db_path: Path | None = None) -> list[dict]:
    with _session(db_path) as s:
        rows = s.execute(
            select(Comment).where(Comment.task_id == task_id)
            .order_by(Comment.created_at.asc())).scalars().all()
        return [r.to_dict() for r in rows]


def delete_comment(comment_id: str, db_path: Path | None = None) -> bool:
    with _session(db_path) as s:
        res = s.execute(delete(Comment).where(Comment.id == comment_id))
        s.commit()
        return res.rowcount > 0


# --------------------------------------------------------------------------- M3 · users 表（TG-4）
def create_user(username: str, password_hash: str, db_path: Path | None = None) -> dict:
    with _session(db_path) as s:
        u = User(id=uuid.uuid4().hex, username=username,
                 password_hash=password_hash, created_at=_now())
        s.add(u)
        s.commit()
        return u.to_dict()


def get_user_by_username(username: str, db_path: Path | None = None) -> dict | None:
    """按用户名查用户（内部用，含 password_hash；API 层不对外暴露）。"""
    with _session(db_path) as s:
        row = s.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if row is None:
            return None
        return {c.name: getattr(row, c.name) for c in User.__table__.columns}


def get_user(user_id: str, db_path: Path | None = None) -> dict | None:
    with _session(db_path) as s:
        row = s.get(User, user_id)
        return row.to_dict() if row else None


# --------------------------------------------------------------------------- M3 · audit_logs 表（TG-4）
def add_audit_log(user_id: str | None, action: str, target: str = "",
                  ip: str = "", db_path: Path | None = None) -> dict:
    with _session(db_path) as s:
        a = AuditLog(id=uuid.uuid4().hex, user_id=user_id, action=action,
                     target=target, ip=ip, created_at=_now())
        s.add(a)
        s.commit()
        return a.to_dict()


# --------------------------------------------------------------------------- M3 · cost_stats 表（TG-6）
def add_cost_stat(task_id: str, llm_tokens_in: int = 0, llm_tokens_out: int = 0,
                  llm_tokens_cache: int = 0, llm_cost_rmb: float = 0.0,
                  asr_cost_rmb: float = 0.0, user_id: str | None = None,
                  db_path: Path | None = None) -> dict:
    with _session(db_path) as s:
        cs = CostStat(id=uuid.uuid4().hex, task_id=task_id, user_id=user_id,
                      date=date.today().isoformat(),
                      llm_tokens_in=int(llm_tokens_in), llm_tokens_out=int(llm_tokens_out),
                      llm_tokens_cache=int(llm_tokens_cache),
                      llm_cost_rmb=float(llm_cost_rmb), asr_cost_rmb=float(asr_cost_rmb),
                      total_cost_rmb=float(llm_cost_rmb) + float(asr_cost_rmb),
                      created_at=_now())
        s.add(cs)
        s.commit()
        return cs.to_dict()


def daily_cost_rmb(day: str | None = None, user_id: str | None = None,
                   db_path: Path | None = None) -> float:
    """某日（默认今天）累计成本（元）。"""
    day = day or date.today().isoformat()
    with _session(db_path) as s:
        stmt = select(CostStat).where(CostStat.date == day)
        if user_id is not None:
            stmt = stmt.where(CostStat.user_id == user_id)
        rows = s.execute(stmt).scalars().all()
        return round(sum(r.total_cost_rmb for r in rows), 4)


def list_cost_stats(user_id: str | None = None, day: str | None = None,
                    db_path: Path | None = None) -> list[dict]:
    with _session(db_path) as s:
        stmt = select(CostStat)
        if user_id is not None:
            stmt = stmt.where(CostStat.user_id == user_id)
        if day:
            stmt = stmt.where(CostStat.date == day)
        rows = s.execute(stmt.order_by(CostStat.created_at.desc())).scalars().all()
        return [r.to_dict() for r in rows]


# --------------------------------------------------------------------------- M4 · minute_embeddings（TG-2）
def replace_embeddings(task_id: str, user_id: str | None,
                       chunks: list[dict], db_path: Path | None = None) -> int:
    """整表重建某 task 的向量块。chunks: list[dict(text, vector:list[float])]。返回写入条数。"""
    with _session(db_path) as s:
        s.execute(delete(MinuteEmbedding).where(MinuteEmbedding.task_id == task_id))
        for i, c in enumerate(chunks):
            s.add(MinuteEmbedding(
                id=uuid.uuid4().hex,
                minute_id=task_id,
                task_id=task_id,
                user_id=user_id,
                chunk_index=i,
                text=c["text"],
                embedding=json.dumps(c["vector"]),
                created_at=_now(),
            ))
        s.commit()
        return len(chunks)


def list_embeddings(user_id: str | None = None, db_path: Path | None = None) -> list[dict]:
    """列出向量块（可选按 user_id 过滤，供 RAG 检索）。"""
    with _session(db_path) as s:
        stmt = select(MinuteEmbedding)
        if user_id is not None:
            stmt = stmt.where(MinuteEmbedding.user_id == user_id)
        rows = s.execute(stmt.order_by(MinuteEmbedding.created_at.asc())).scalars().all()
        return [r.to_dict() for r in rows]


def count_embeddings(task_id: str, db_path: Path | None = None) -> int:
    """某任务向量块数（验收 V3：纪要完成后有对应向量）。"""
    with _session(db_path) as s:
        stmt = (select(func.count()).select_from(MinuteEmbedding)
                .where(MinuteEmbedding.task_id == task_id))
        return int(s.execute(stmt).scalar() or 0)


def delete_embeddings(task_id: str, db_path: Path | None = None) -> bool:
    with _session(db_path) as s:
        res = s.execute(delete(MinuteEmbedding).where(MinuteEmbedding.task_id == task_id))
        s.commit()
        return res.rowcount > 0
