"""M1 MVP 服务集中配置。

从环境变量 / 项目根目录 `.env` 读取密钥、Provider 选择与服务参数。
与 M0 的根目录 `config.py` 独立：本文件供 `app` 包（服务层）使用，M0 CLI 脚本仍用根 config.py。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent  # 项目根目录
load_dotenv(ROOT / ".env")

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
