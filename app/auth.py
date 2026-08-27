"""M3 · auth 模块 — 自建账号体系（注册/登录 + JWT）与鉴权依赖（TG-4）。

bcrypt 密码哈希 + PyJWT HS256；无高级 RBAC（mission §3 排除）。
`get_current_user`：AUTH_ENABLED=False 时返回 None（本地开发/测试免鉴权）；
否则校验 Bearer JWT，失败抛 401。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt as pyjwt
from fastapi import HTTPException, Request

from app import config, db

logger = logging.getLogger("mma.auth")

MIN_PASSWORD_LEN = 6


# --------------------------------------------------------------------------- 密码哈希
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"),
                         bcrypt.gensalt(rounds=config.PASSWORD_BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- JWT
def create_token(user_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=config.JWT_EXPIRE_MINUTES),
    }
    return pyjwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> str | None:
    """解析 JWT，返回 user_id；无效/过期返回 None。"""
    try:
        payload = pyjwt.decode(token, config.JWT_SECRET,
                               algorithms=[config.JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:  # noqa: BLE001 — 任何解析失败都视为未认证
        return None


# --------------------------------------------------------------------------- 业务
def register(username: str, password: str) -> dict:
    username = (username or "").strip()
    if not username:
        raise ValueError("用户名不能为空")
    if len(username) > 64:
        raise ValueError("用户名过长")
    if len(password or "") < MIN_PASSWORD_LEN:
        raise ValueError(f"密码至少 {MIN_PASSWORD_LEN} 位")
    if db.get_user_by_username(username):
        raise ValueError("用户名已存在")
    return db.create_user(username, hash_password(password))


def login(username: str, password: str) -> dict:
    u = db.get_user_by_username((username or "").strip())
    if not u or not verify_password(password or "", u["password_hash"]):
        raise ValueError("用户名或密码错误")
    return {
        "token": create_token(u["id"]),
        "token_type": "bearer",
        "expires_in": config.JWT_EXPIRE_MINUTES * 60,
        "user": {"id": u["id"], "username": u["username"]},
    }


# --------------------------------------------------------------------------- 鉴权依赖
def get_current_user(request: Request) -> dict | None:
    """FastAPI 依赖：返回当前用户 dict（含 id/username），或 None（鉴权关闭时）。"""
    if not config.AUTH_ENABLED:
        return None
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    user_id = decode_token(auth[len("Bearer "):].strip())
    if not user_id:
        raise HTTPException(status_code=401, detail="无效或过期的令牌")
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user
