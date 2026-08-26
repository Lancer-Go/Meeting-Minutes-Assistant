"""M3 · crypto 模块 — AES-256-GCM 应用层加密（TG-4）。

加密敏感字段与纪要内容。密钥：AES_KEY 环境变量（32 字节建议），
缺失时从 JWT_SECRET 派生（SHA-256 → 32 字节），开发默认可用、生产须显式配置。
"""
from __future__ import annotations

import base64
import hashlib
import os

from app import config


def _key() -> bytes:
    k = config.AES_KEY or config.JWT_SECRET
    return hashlib.sha256(k.encode("utf-8")).digest()  # 32 字节 → AES-256


def encrypt(plaintext: str) -> str:
    """AES-256-GCM 加密，返回 url-safe base64(nonce + ciphertext)。"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt(token: str) -> str:
    """解密 encrypt() 的输出；失败抛异常（调用方决定兜底）。"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(_key()).decrypt(nonce, ct, None).decode("utf-8")


def mask_secret(value: str) -> str:
    """脱敏显示（审计 / 日志用）。"""
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]
