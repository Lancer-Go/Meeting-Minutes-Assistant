# Meeting Minutes Assistant / 会议纪要助手

将会议录音/录像自动转写为文字，并生成结构化 Markdown 会议纪要。

> 当前进度：**M1 · MVP（可用闭环 · 云 API）** —— FastAPI 服务 + 异步全链路，无技术背景用户可自助「上传 → 得到纪要」。
> 选型已锁定（M0 实测）：ASR 腾讯云 16k_zh / LLM DeepSeek-V4 Pro（deepseek-v4-pro，由 V3 升级）。详见 `specs/` 与 `docs/roadmap.md`。

## 快速开始（服务模式）

```bash
# 1. 环境（Python 3.11）
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt

# 2. 配置密钥：复制 .env.example 为 .env，填入腾讯云 / DeepSeek 密钥
#    （不填密钥也能跑：自动降级为本地 whisper 转写 + 抽取式纪要）

# 3. 启动服务
./venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 4. 浏览器打开 http://127.0.0.1:8000/ （上传页 + 进度条 + 结果下载）
```

### Docker Compose 一键启动（需本机 Docker）

```bash
docker compose up --build
```

## REST API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/tasks` | 上传文件（multipart `file`），创建任务并异步执行 |
| GET | `/api/tasks` | 任务列表 |
| GET | `/api/tasks/{id}` | 任务状态与进度 |
| GET | `/api/tasks/{id}/transcript` | 转写文本下载 |
| GET | `/api/tasks/{id}/minute` | 纪要 Markdown 下载 |
| GET | `/health` | 健康检查 |

- 支持格式：MP4 / MKV / WAV / MP3 / M4A，单场 ≤ 2 小时。
- 状态机：`pending → running → succeeded / failed`；进度 0–100，转写阶段按切片推进（「第 x/N 段已完成」）。
- 云端 ASR/LLM 密钥缺失时自动降级（`whisper` / `extractive`），保证链路可跑通。

## 任务组（M1）

| 任务组 | 模块 | 说明 |
| --- | --- | --- |
| TG-0 骨架 | `app/config.py` + `requirements.txt` | 配置管理 + 依赖锁定 |
| TG-1 模块化重构 | `app/audio` · `app/asr` · `app/summary` · `app/render` | 四模块，去 M0 脚本式 |
| TG-2 上传 | `app/ingestion.py` | 格式白名单 / 大小 / 时长校验 |
| TG-3 任务模型 | `app/db.py` | SQLite Task + 状态机 |
| TG-4 队列 | `app/worker.py` + FastAPI BackgroundTasks | 异步全链路 |
| TG-5 导出 | `app/main.py` | Markdown 导出与下载接口 |
| TG-6 前端 | `static/index.html` | 上传页 + 进度 + 下载 |
| TG-7 容错 | `app/worker.py` + `app/main.py` | 重试 + 结构化日志 |

## 测试

```bash
./venv/Scripts/python.exe -m pytest tests/ --cov=app
```

## 离线 CLI（M0 遗留，链路验证用）

```bash
./venv/Scripts/python.exe pipeline.py samples/meeting-001.mp3 --asr whisper --llm extractive
```

## 目录结构

```
app/             # M1 服务包（config / audio / asr / summary / render / pipeline / ingestion / db / worker / main）
static/          # 极简前端（index.html）
tests/           # 单元与集成测试（覆盖率 ≥ 70%）
Dockerfile / docker-compose.yml   # 容器化交付
audio.py / asr.py / summarize.py / pipeline.py / eval_cer.py / make_sample.py  # M0 脚本（离线 CLI）
config.py        # M0 集中配置（根）；服务配置见 app/config.py
samples/         # 会议音频（gitignore，需自备真实数据）
data/            # 服务数据：上传文件 + 任务产物 + SQLite（gitignore）
specs/           # 阶段执行文档（plan / requirements / validation）
docs/            # mission / roadmap / tech-stack 源文档
```
