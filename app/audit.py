"""M3 · audit 模块 — 关键操作审计留痕（TG-4）。

登录成功/失败、任务创建、纪要编辑、批注增删等关键操作写入 audit_logs 表 + 结构化日志。
"""
from __future__ import annotations

import logging

from app import db

logger = logging.getLogger("mma.audit")


def log(action: str, user_id: str | None = None, target: str = "",
        ip: str = "", db_path=None) -> None:
    """留痕（DB 写入失败不抛，仅记日志，避免审计影响主流程）。"""
    try:
        db.add_audit_log(user_id, action, target, ip, db_path=db_path)
    except Exception:
        logger.exception("审计留痕失败 action=%s", action)
    logger.info("audit action=%s user=%s target=%s ip=%s", action, user_id, target, ip)
