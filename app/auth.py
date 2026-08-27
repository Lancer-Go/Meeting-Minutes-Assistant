"""M3 · auth 模块 — 自建账号体系（登录 + JWT）与鉴权依赖（TG-4）。

bcrypt 密码哈希 + PyJWT HS256；无高级 RBAC（mission §3 排除）。
需求变更（禁自助注册）：`register` 收紧为内部 `admin_create_user`，仅管理员/CLI 调用；
新增 `ensure_admin_exists`（启动引导首位管理员）与 `require_admin`（仅管理员依赖）。
`get_current_user`：AUTH_ENABLED=False 时返回 None（本地开发/测试免鉴权）；
否则校验 Bearer JWT，失败抛 401。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt as pyjwt
from fastapi import Depends, HTTPException, Request

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
def admin_create_user(username: str, password: str, is_admin: bool = False) -> dict:
    """管理员创建用户（需求变更：原 `register` 收紧为内部函数，仅管理员/CLI 调用）。

    复用「用户名非空/唯一、密码 ≥6 位」校验，bcrypt 哈希由调用方（admin/CLI）经此函数统一生成。
    """
    username = (username or "").strip()
    if not username:
        raise ValueError("用户名不能为空")
    if len(username) > 64:
        raise ValueError("用户名过长")
    if len(password or "") < MIN_PASSWORD_LEN:
        raise ValueError(f"密码至少 {MIN_PASSWORD_LEN} 位")
    if db.get_user_by_username(username):
        raise ValueError("用户名已存在")
    return db.create_user(username, hash_password(password), is_admin=is_admin)


def ensure_admin_exists() -> bool:
    """启动引导：若配置 MMA_ADMIN_USERNAME/PASSWORD，确保该管理员存在（幂等）。

    - 不存在 → 创建（is_admin=True，bcrypt 哈希）。
    - 已存在但 is_admin=False → 置 True 并告警（管理员账号语义优先）。
    - 两项未配置 → 不触发，返回 False。
    """
    username = (config.MMA_ADMIN_USERNAME or "").strip()
    password = config.MMA_ADMIN_PASSWORD or ""
    if not username or not password:
        return False
    existing = db.get_user_by_username(username)
    if existing is None:
        db.create_user(username, hash_password(password), is_admin=True)
        logger.info("已初始化管理员账号 username=%s", username)
        return True
    if not existing.get("is_admin"):
        db.set_user_admin(existing["id"], True)
        logger.warning("管理员账号已存在但 is_admin=False，已置 True（账号=%s）", username)
    return False


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


def require_admin(request: Request, user: dict | None = Depends(get_current_user)) -> dict | None:
    """FastAPI 依赖：仅管理员放行。

    - AUTH_ENABLED=False（本地开发/测试）→ 放行（返回 user，可能为 None）。
    - AUTH_ENABLED=True：未登录 401 / 非管理员 403 / 管理员放行。
    """
    if not config.AUTH_ENABLED:
        return user
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
