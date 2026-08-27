"""M3 · storage 模块 — 对象存储抽象（MinIO S3 兼容，本地 FS 兜底）（TG-2）。

统一键（key）语义：S3 模式下为对象键；本地模式下为 DATA_DIR 下的相对路径。
本地模式零拷贝（文件本就在 DATA_DIR 下），S3 模式才真正上传 / 下载。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app import config


class Storage:
    """对象存储统一接口。由 `get_storage()` 按配置选择后端。"""

    def __init__(self, s3: bool, endpoint: str = "", bucket: str = "",
                 access_key: str = "", secret_key: str = "", region: str = ""):
        self.s3 = s3
        self.endpoint = endpoint
        self.bucket = bucket
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self._client = None

    # -- S3 客户端（惰性，避免本地模式引入 boto3 开销）--
    def _s3_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
            )
        return self._client

    def _ensure_bucket(self) -> None:
        if not self.s3:
            return
        c = self._s3_client()
        try:
            c.head_bucket(Bucket=self.bucket)
        except Exception:
            c.create_bucket(Bucket=self.bucket)

    # -- 上传 --
    def put_file(self, key: str, local_path: Path) -> str:
        """上传本地文件到 key，返回存储键。本地模式零拷贝（文件须在 DATA_DIR 下）。

        S3 模式启用服务端加密（SSE-AES256）满足 NFR 加密存储（TG-4）。
        """
        key = key.lstrip("/")
        if self.s3:
            self._ensure_bucket()
            if config.S3_SSE_ENABLED:
                self._s3_client().upload_file(
                    str(local_path), self.bucket, key,
                    ExtraArgs={"ServerSideEncryption": "AES256"})
            else:
                self._s3_client().upload_file(
                    str(local_path), self.bucket, key)
        else:
            dst = config.DATA_DIR / key
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(local_path), str(dst))
        return key

    def put_bytes(self, key: str, data: bytes) -> str:
        key = key.lstrip("/")
        if self.s3:
            self._ensure_bucket()
            kwargs = {"Bucket": self.bucket, "Key": key, "Body": data}
            if config.S3_SSE_ENABLED:
                kwargs["ServerSideEncryption"] = "AES256"
            self._s3_client().put_object(**kwargs)
        else:
            path = config.DATA_DIR / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return key

    # -- 读取 --
    def to_local(self, key: str, dst: Path) -> Path:
        """把 key 对应对象落地到本地 dst。本地模式直接返回 DATA_DIR/key。"""
        key = key.lstrip("/")
        if self.s3:
            self._s3_client().download_file(self.bucket, key, str(dst))
            return dst
        return config.DATA_DIR / key

    def local_path(self, key: str) -> Path:
        """本地模式：返回对象在本地的绝对路径。S3 模式不支持（须 to_local 下载）。"""
        key = key.lstrip("/")
        return config.DATA_DIR / key

    def exists(self, key: str) -> bool:
        key = key.lstrip("/")
        if self.s3:
            try:
                self._s3_client().head_object(Bucket=self.bucket, Key=key)
                return True
            except Exception:
                return False
        return (config.DATA_DIR / key).exists()

    def read_bytes(self, key: str) -> bytes | None:
        key = key.lstrip("/")
        if self.s3:
            try:
                obj = self._s3_client().get_object(Bucket=self.bucket, Key=key)
                return obj["Body"].read()
            except Exception:
                return None
        p = config.DATA_DIR / key
        return p.read_bytes() if p.exists() else None

    def presigned_url(self, key: str, expires: int = 3600) -> str | None:
        """S3 模式：生成预签名 GET URL（供云 ASR URL 识别拉取音频）。本地模式返回 None。

        注意：URL 只有公网可达时才可被云 ASR 下载（本地 MinIO/内网地址无效）。
        """
        if not self.s3:
            return None
        key = key.lstrip("/")
        return self._s3_client().generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
        )

    def sync_dir(self, local_dir: Path, prefix: str) -> int:
        """把本地目录所有文件同步到对象存储（S3 模式），返回文件数。本地模式 no-op。"""
        if not self.s3:
            return 0
        local_dir = Path(local_dir)
        n = 0
        for f in local_dir.rglob("*"):
            if f.is_file():
                rel = f.relative_to(local_dir).as_posix()
                self.put_file(f"{prefix.rstrip('/')}/{rel}", f)
                n += 1
        return n


_storage: Storage | None = None


def get_storage() -> Storage:
    """按配置构造（缓存）存储后端。"""
    global _storage
    if _storage is None:
        _storage = Storage(
            s3=bool(config.S3_ENDPOINT),
            endpoint=config.S3_ENDPOINT,
            bucket=config.S3_BUCKET,
            access_key=config.S3_ACCESS_KEY,
            secret_key=config.S3_SECRET_KEY,
            region=config.S3_REGION,
        )
    return _storage


def is_s3() -> bool:
    return bool(config.S3_ENDPOINT)


def copy_local(local_path: Path, key: str) -> str:
    """本地模式下把文件复制到 DATA_DIR/key 下（用于显式落到数据目录）。"""
    key = key.lstrip("/")
    dst = config.DATA_DIR / key
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(local_path), str(dst))
    return key
