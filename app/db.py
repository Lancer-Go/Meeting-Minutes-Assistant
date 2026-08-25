"""M1 · storage 模块 — SQLite 数据模型与状态机；M2 扩展 minutes / comments 表（TG-0/TG-5/TG-6）。

FR-07：任务持久化与状态追踪。状态机：pending → running → succeeded / failed。
M2：纪要持久化（minutes 表）与批注（comments 表），支撑编辑与历史检索。
使用标准库 sqlite3（MVP 足够），短连接 + WAL。
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    stored_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    progress REAL NOT NULL DEFAULT 0,
    progress_message TEXT,
    error TEXT,
    audio_duration_min REAL,
    transcript_chars INTEGER,
    cost_rmb REAL,
    created_at TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS minutes (
    task_id TEXT PRIMARY KEY,
    title TEXT,
    template TEXT DEFAULT 'standard',
    summary_md TEXT,
    structured_json TEXT,
    edited_md TEXT,
    updated_at TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    author TEXT,
    text TEXT NOT NULL,
    quote TEXT,
    created_at TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);
"""


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(db_path: Path | None = None) -> None:
    """建表（幂等），并为旧库补充新增列（轻量迁移）。"""
    conn = _connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
        if "progress_message" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN progress_message TEXT")
        conn.commit()
    finally:
        conn.close()


def create_task(task_id: str, source_file: str, stored_path: str = "",
                db_path: Path | None = None) -> dict:
    conn = _connect(db_path)
    try:
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO tasks (id, source_file, stored_path, status, progress, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (task_id, source_file, stored_path, PENDING, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_task(task_id, db_path) or {}


def get_task(task_id: str, db_path: Path | None = None) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_tasks(db_path: Path | None = None) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _set_status(conn: sqlite3.Connection, task_id: str, new_status: str) -> None:
    row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise KeyError(f"任务不存在: {task_id}")
    cur = row["status"]
    if new_status != cur and new_status not in VALID_TRANSITIONS.get(cur, set()):
        raise ValueError(f"非法状态流转: {cur} → {new_status}")
    conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))


def set_status(task_id: str, new_status: str, db_path: Path | None = None) -> dict:
    """按状态机更新任务状态，并自动填 started_at / finished_at。"""
    conn = _connect(db_path)
    try:
        _set_status(conn, task_id, new_status)
        now = datetime.now().isoformat(timespec="seconds")
        if new_status == RUNNING:
            conn.execute("UPDATE tasks SET started_at = COALESCE(started_at, ?) WHERE id = ?",
                         (now, task_id))
        elif new_status in (SUCCEEDED, FAILED):
            conn.execute("UPDATE tasks SET finished_at = ? WHERE id = ?", (now, task_id))
        conn.commit()
    finally:
        conn.close()
    return get_task(task_id, db_path) or {}


def set_progress(task_id: str, progress: float, message: str | None = None,
                 db_path: Path | None = None) -> None:
    """更新任务进度（0–100），可选附带进度说明（如「第 12/48 段已完成」）。"""
    progress = max(0.0, min(100.0, float(progress)))
    conn = _connect(db_path)
    try:
        if message is None:
            conn.execute("UPDATE tasks SET progress = ? WHERE id = ?", (progress, task_id))
        else:
            conn.execute("UPDATE tasks SET progress = ?, progress_message = ? WHERE id = ?",
                         (progress, message, task_id))
        conn.commit()
    finally:
        conn.close()


def update_fields(task_id: str, db_path: Path | None = None, **fields) -> dict:
    """更新任意字段（白名单内）。"""
    allowed = {"error", "audio_duration_min", "transcript_chars", "cost_rmb", "stored_path"}
    cols = {k: v for k, v in fields.items() if k in allowed}
    if not cols:
        return get_task(task_id, db_path) or {}
    conn = _connect(db_path)
    try:
        sets = ", ".join(f"{k} = ?" for k in cols)
        conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", (*cols.values(), task_id))
        conn.commit()
    finally:
        conn.close()
    return get_task(task_id, db_path) or {}


# --------------------------------------------------------------------------- M2 · minutes 表（TG-0/TG-5/TG-6）
def save_minute(task_id: str, title: str = "", template: str = "standard",
                summary_md: str = "", structured_json: str = "",
                edited_md: str | None = None, db_path: Path | None = None) -> dict:
    """UPSERT 一条纪要记录。edited_md 为 None 时保留原值。"""
    conn = _connect(db_path)
    try:
        now = datetime.now().isoformat(timespec="seconds")
        existing = conn.execute(
            "SELECT edited_md FROM minutes WHERE task_id = ?", (task_id,)).fetchone()
        if edited_md is None:
            edited_md = existing["edited_md"] if existing else None
        conn.execute(
            "INSERT INTO minutes (task_id, title, template, summary_md, structured_json, edited_md, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(task_id) DO UPDATE SET title=excluded.title, template=excluded.template, "
            "summary_md=excluded.summary_md, structured_json=excluded.structured_json, "
            "edited_md=excluded.edited_md, updated_at=excluded.updated_at",
            (task_id, title, template, summary_md, structured_json, edited_md, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_minute(task_id, db_path) or {}


def get_minute(task_id: str, db_path: Path | None = None) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM minutes WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_minute_edited(task_id: str, edited_md: str, db_path: Path | None = None) -> dict:
    """保存人工编辑后的纪要 Markdown（TG-5）。"""
    conn = _connect(db_path)
    try:
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "UPDATE minutes SET edited_md = ?, updated_at = ? WHERE task_id = ?",
            (edited_md, now, task_id),
        )
        if conn.total_changes == 0:
            raise KeyError(f"纪要不存在: {task_id}")
        conn.commit()
    finally:
        conn.close()
    return get_minute(task_id, db_path) or {}


def list_minutes(db_path: Path | None = None) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM minutes ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_minutes(q: str = "", from_: str | None = None, to: str | None = None,
                   topic: str | None = None, db_path: Path | None = None) -> list[dict]:
    """按关键词 / 时间范围 / 主题检索纪要（TG-6，SQLite LIKE）。"""
    clauses: list[str] = []
    params: list = []
    if q:
        like = f"%{q}%"
        clauses.append("(title LIKE ? OR summary_md LIKE ? OR edited_md LIKE ? OR structured_json LIKE ?)")
        params += [like, like, like, like]
    if topic:
        clauses.append("title LIKE ?")
        params.append(f"%{topic}%")
    if from_:
        clauses.append("updated_at >= ?")
        params.append(from_)
    if to:
        clauses.append("updated_at <= ?")
        params.append(to)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT * FROM minutes{where} ORDER BY updated_at DESC", params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# --------------------------------------------------------------------------- M2 · comments 表（TG-5）
def add_comment(task_id: str, text: str, author: str = "", quote: str = "",
                db_path: Path | None = None) -> dict:
    conn = _connect(db_path)
    try:
        cid = uuid.uuid4().hex
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO comments (id, task_id, author, text, quote, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cid, task_id, author, text, quote, now),
        )
        conn.commit()
    finally:
        conn.close()
    row = _get_comment(cid, db_path)
    return row or {}


def _get_comment(comment_id: str, db_path: Path | None = None) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_comments(task_id: str, db_path: Path | None = None) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM comments WHERE task_id = ? ORDER BY created_at ASC", (task_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_comment(comment_id: str, db_path: Path | None = None) -> bool:
    conn = _connect(db_path)
    try:
        cur = conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
