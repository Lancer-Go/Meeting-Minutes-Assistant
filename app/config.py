"""M1 MVP 服务集中配置；M3 生产化扩展（存储 / 队列 / 鉴权 / 加密 / 成本 / 可观测）。

从环境变量 / 项目根目录 `.env` 读取密钥、Provider 选择与服务参数。
与 M0 的根目录 `config.py` 独立：本文件供 `app` 包（服务层）使用，M0 CLI 脚本仍用根 config.py。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent  # 项目根目录
load_dotenv(ROOT / ".env")


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- 目录
DATA_DIR = Path(os.getenv("MMA_DATA_DIR", str(ROOT / "data")))
UPLOAD_DIR = DATA_DIR / "uploads"           # 原始上传文件
TASK_DIR = DATA_DIR / "tasks"               # 每任务产物（wav/transcript/minutes/metrics）
DB_PATH = Path(os.getenv("MMA_DB_PATH", str(DATA_DIR / "mma.db")))
STATIC_DIR = ROOT / "static"                # 前端静态文件

# --------------------------------------------------------------------------- 上传校验
# FR-01 格式白名单：MP4 / MKV / WAV / MP3 / M4A
ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".wav", ".mp3", ".m4a"}
MAX_FILE_SIZE_BYTES = int(float(os.getenv("MMA_MAX_FILE_SIZE_MB", "2048")) * 1024 * 1024)  # 默认 2GB
MAX_DURATION_SECONDS = float(os.getenv("MMA_MAX_DURATION_SECONDS", "7200"))               # 单场 ≤ 2 小时

# --------------------------------------------------------------------------- 服务
HOST = os.getenv("MMA_HOST", "127.0.0.1")
PORT = int(os.getenv("MMA_PORT", "8000"))

# --------------------------------------------------------------------------- 云 ASR 密钥
ALIYUN_APP_KEY = os.getenv("ALIYUN_APP_KEY", "")
ALIYUN_ACCESS_KEY_ID = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
ALIYUN_ACCESS_KEY_SECRET = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
ALIYUN_OSS_BUCKET = os.getenv("ALIYUN_OSS_BUCKET", "")
ALIYUN_OSS_ENDPOINT = os.getenv("ALIYUN_OSS_ENDPOINT", "oss-cn-shanghai.aliyuncs.com")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
TENCENT_SECRET_ID = os.getenv("TENCENT_SECRET_ID", "")
TENCENT_SECRET_KEY = os.getenv("TENCENT_SECRET_KEY", "")
XFYUN_APP_ID = os.getenv("XFYUN_APP_ID", "")
XFYUN_API_KEY = os.getenv("XFYUN_API_KEY", "")
XFYUN_API_SECRET = os.getenv("XFYUN_API_SECRET", "")

# --------------------------------------------------------------------------- LLM 密钥
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# --------------------------------------------------------------------------- Provider 默认
DEFAULT_ASR = os.getenv("MMA_ASR", "tencent")            # tencent | aliyun | whisper | iflytek
DEFAULT_LLM = os.getenv("MMA_LLM", "deepseek")           # deepseek | qwen | extractive
WHISPER_MODEL = os.getenv("MMA_WHISPER_MODEL", "base")   # tiny/base/small/medium/large-v3
LLM_MAX_CHARS = int(os.getenv("MMA_LLM_MAX_CHARS", "12000"))  # Map-Reduce 分块阈值（字符）
DEEPSEEK_MODEL = os.getenv("MMA_DEEPSEEK_MODEL", "deepseek-v4-pro")  # LLM 主用模型（DeepSeek-V4 Pro）

# --------------------------------------------------------------------------- M2 结构化增强
DEFAULT_EXTRACTOR = os.getenv("MMA_EXTRACTOR", "deepseek")      # deepseek | rule
DEFAULT_DIARIZATION = os.getenv("MMA_DIARIZATION", "placeholder")  # pyannote | placeholder
DEFAULT_TEMPLATE = os.getenv("MMA_TEMPLATE", "standard")        # standard | brief | detailed

# 云端密钥缺失时的离线降级（validation.md 判定规则）
ASR_FALLBACK = "whisper"
LLM_FALLBACK = "extractive"
EXTRACTOR_FALLBACK = "rule"

# --------------------------------------------------------------------------- 腾讯云切片
# 录音文件识别 base64 ≤5MB（≈2min 16kHz WAV），长音频按此切片逐段识别再合并。
ASR_CHUNK_SECONDS = float(os.getenv("MMA_ASR_CHUNK_SECONDS", "100"))
# 云 ASR URL 识别（SourceType=0）：音频落在公网可下载的对象存储时，整段一次提交（无切片、
# 全局话者分离，避免切片导致的说话人过度切分）。需同时配置 S3_ENDPOINT 且其地址公网可达
# （生产 COS/S3 或公网 MinIO）；本地 MinIO/localhost 不可达，保持关闭走 base64 切片。
ASR_URL_ENABLED = _bool("MMA_ASR_URL_ENABLED", "false")

# --------------------------------------------------------------------------- M3 · 存储（TG-2）
# DATABASE_URL 驱动 SQLAlchemy：空 = 沿用 SQLite DB_PATH（本地开发）；postgresql:// 生产。
DATABASE_URL = os.getenv("DATABASE_URL", "")
# 对象存储：S3_ENDPOINT 为空时用本地 FS 兜底（stored_path 存对象键 / 相对路径）。
# 支持 S3 兼容（MinIO）与腾讯云 COS（endpoint 指向 cos.<region>.myqcloud.com）。
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "")
S3_BUCKET = os.getenv("S3_BUCKET", "mma")
# S3/COS 凭证：未显式配置时回退到腾讯云 TENCENT_SECRET_ID/KEY（COS 与云 ASR 同账号通用）。
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "") or TENCENT_SECRET_ID
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "") or TENCENT_SECRET_KEY
S3_REGION = os.getenv("S3_REGION", "us-east-1")
# 寻址风格：auto（默认，MinIO/本地）/ virtual（腾讯云 COS 强制 virtual，path 报 PathStyleDomainForbidden）。
S3_ADDRESSING_STYLE = os.getenv("MMA_S3_ADDRESSING_STYLE", "auto")
# 服务端加密（SSE-AES256，TG-4 加密存储）：生产 COS/S3 开启；本地 MinIO 无 KES(KMS) 时须关闭，
# 否则 boto3 上传报 "KMS is not configured"。本地 compose 默认已设 false。
S3_SSE_ENABLED = _bool("S3_SSE_ENABLED", "true")

# --------------------------------------------------------------------------- M3 · 队列（TG-0）
# Celery + Redis 生产队列；本地开发默认关闭，回退 FastAPI BackgroundTasks（不破坏 M1/M2 体验）。
USE_CELERY = _bool("MMA_USE_CELERY", "false")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_TASK_NAME = "app.celery_app.process_task"

# --------------------------------------------------------------------------- M3 · 鉴权（TG-4）
# 自建账号体系基础版：注册 / 登录 + JWT（PyJWT HS256）。AUTH_ENABLED=False 时业务接口免鉴权（本地开发/测试）。
AUTH_ENABLED = _bool("MMA_AUTH_ENABLED", "true")
# ⚠️ 生产必须用 `JWT_SECRET` 环境变量覆盖此开发默认值（HS256 建议 ≥ 32 字节）。
JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", str(7 * 24 * 60)))  # 默认 7 天
PASSWORD_BCRYPT_ROUNDS = int(os.getenv("PASSWORD_BCRYPT_ROUNDS", "12"))

# --------------------------------------------------------------------------- M3 · 加密（TG-4）
# AES-256-GCM 应用层加密（敏感字段/纪要内容）。空则从 JWT_SECRET 派生（开发默认）。
AES_KEY = os.getenv("AES_KEY", "")

# --------------------------------------------------------------------------- M3 · 成本（TG-6）
COST_LIMIT_DAILY_RMB = float(os.getenv("COST_LIMIT_DAILY_RMB", "5.0"))       # 日成本限额
COST_LIMIT_PER_TASK_RMB = float(os.getenv("COST_LIMIT_PER_TASK_RMB", "1.0"))  # 单场超预算阈值
COST_AUTO_PAUSE = _bool("COST_AUTO_PAUSE", "false")                          # 超限自动暂停新任务（默认关闭）

# --------------------------------------------------------------------------- M3 · 可观测（TG-3）
METRICS_ENABLED = _bool("MMA_METRICS_ENABLED", "true")

# --------------------------------------------------------------------------- M4 · 智能化（TG-0~TG-3）
# 模型注册表：MMA_LLM_ALIAS 指定当前云端 LLM 模型别名（v4-pro 主 / v4-flash 降本 / qwen-plus 备选）。
# 改此环境变量即可热切换 summary 与 extractor 的模型，无需改代码（ASR 维持现状）。
MMA_LLM_ALIAS = os.getenv("MMA_LLM_ALIAS", "v4-pro")
MMA_LLM_MODEL = os.getenv("MMA_LLM_MODEL", "")          # 覆盖注册表具体模型名（空 = 用注册表默认）
MMA_QWEN_MODEL = os.getenv("MMA_QWEN_MODEL", "qwen-plus")

# Embedding（TG-2）：OpenAI 兼容云 API（如 bge-m3）。base_url 与 api_key 均配置才启用；
# 缺任一 → 纪要向量化跳过、RAG 降级关键词检索（不阻断主链路）。
MMA_EMBEDDING_BASE_URL = os.getenv("MMA_EMBEDDING_BASE_URL", "")
MMA_EMBEDDING_API_KEY = os.getenv("MMA_EMBEDDING_API_KEY", "")
MMA_EMBEDDING_MODEL = os.getenv("MMA_EMBEDDING_MODEL", "bge-m3")
MMA_EMBEDDING_DIM = int(os.getenv("MMA_EMBEDDING_DIM", "1024"))

# RAG（TG-3）
MMA_RAG_TOP_K = int(os.getenv("MMA_RAG_TOP_K", "5"))
MMA_RAG_CHUNK_CHARS = int(os.getenv("MMA_RAG_CHUNK_CHARS", "800"))
MMA_RAG_CHUNK_OVERLAP = int(os.getenv("MMA_RAG_CHUNK_OVERLAP", "200"))
