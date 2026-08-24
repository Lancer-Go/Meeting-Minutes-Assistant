"""M0 PoC 集中配置。

从环境变量 / 项目根目录 `.env` 读取云服务密钥与 Provider 选择。
复制 `.env.example` 为 `.env` 并填入密钥即可启用云端 ASR / LLM。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# ---- 目录 ----
SAMPLES_DIR = ROOT / "samples"
OUT_DIR = ROOT / "out"

# ---- 云 ASR 密钥 ----
# 阿里云智能语音交互（NLS）录音文件识别：AppKey + AccessKey + OSS 桶
ALIYUN_APP_KEY = os.getenv("ALIYUN_APP_KEY", "")
ALIYUN_ACCESS_KEY_ID = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
ALIYUN_ACCESS_KEY_SECRET = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
ALIYUN_OSS_BUCKET = os.getenv("ALIYUN_OSS_BUCKET", "")
ALIYUN_OSS_ENDPOINT = os.getenv("ALIYUN_OSS_ENDPOINT", "oss-cn-shanghai.aliyuncs.com")
# 阿里云 DashScope（备选，需 sk- 开头的 DashScope API Key）
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
# 腾讯云（录音文件识别）
TENCENT_SECRET_ID = os.getenv("TENCENT_SECRET_ID", "")
TENCENT_SECRET_KEY = os.getenv("TENCENT_SECRET_KEY", "")
# 讯飞（占位，见 asr.py IFlytekASR 说明）
XFYUN_APP_ID = os.getenv("XFYUN_APP_ID", "")
XFYUN_API_KEY = os.getenv("XFYUN_API_KEY", "")
XFYUN_API_SECRET = os.getenv("XFYUN_API_SECRET", "")

# ---- LLM 密钥 ----
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")      # 阿里云 DashScope 兼容 OpenAI 接口
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ---- Provider 默认选择 ----
DEFAULT_ASR = os.getenv("MMA_ASR", "whisper")            # whisper | aliyun | tencent | iflytek
DEFAULT_LLM = os.getenv("MMA_LLM", "extractive")         # deepseek | qwen | extractive
WHISPER_MODEL = os.getenv("MMA_WHISPER_MODEL", "base")   # tiny/base/small/medium/large-v3
LLM_MAX_CHARS = int(os.getenv("MMA_LLM_MAX_CHARS", "12000"))  # Map-Reduce 分块阈值（字符）
