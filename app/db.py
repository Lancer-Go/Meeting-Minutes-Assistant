"""M1 · storage 模块 — SQLite Task 数据模型与状态机。

FR-07：任务持久化与状态追踪。状态机：pending → running → succeeded / failed。
使用标准库 sqlite3（MVP 足够），短连接 + WAL。
"""
from __future__ import annotations

import sqlite3
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
    error TEXT,
    audio_duration_min REAL,
    transcript_chars INTEGER,
    cost_rmb REAL,
    created_at TEXT,
    started_at TEXT,
    finished_at TEXT
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
    """建表（幂等）。"""
    conn = _connect(db_path)
    try:
        conn.executescript(_SCHEMA)
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


def set_progress(task_id: str, progress: float, db_path: Path | None = None) -> None:
    progress = max(0.0, min(100.0, float(progress)))
    conn = _connect(db_path)
    try:
        conn.execute("UPDATE tasks SET progress = ? WHERE id = ?", (progress, task_id))
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
