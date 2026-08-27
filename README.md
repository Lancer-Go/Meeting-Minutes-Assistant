# Meeting Minutes Assistant / 会议纪要助手

将会议录音/录像自动转写为文字，并生成结构化 Markdown 会议纪要。

> 当前进度：**M4 · 智能化** 已完成（多模型热切换 + 检索问答 RAG）；M0–M3 均已落地，M3 已真实上线腾讯云；**需求变更「账号注册管控」**（禁自助注册 + 管理员/数据库加用户）已落地（分支 `feat/registration-control`）。
> 选型已锁定（M0 实测）：ASR **腾讯云 16k_zh**（长音频走 COS URL 识别）；LLM **DeepSeek-V4 Pro**（主）/ **V4 Flash**（降本）/ **Qwen**（备选），经模型注册表 `MMA_LLM_ALIAS` 配置化热切换。详见 `specs/`、`docs/roadmap.md` 与 `docs/tech-stack.md`。

## 快速开始（服务模式）

```bash
# 1. 环境（Python 3.11）
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt

# 2. 配置密钥：复制 .env.example 为 .env，填入腾讯云 / DeepSeek 密钥 + JWT_SECRET
#    （不填密钥也能跑：自动降级为本地 whisper 转写 + 抽取式纪要）

# 3. 启动服务
./venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 4. 浏览器打开 http://127.0.0.1:8000/ （登录 + 上传页 + 进度条 + 结果下载 + 智能问答）
```

> **账号体系（M3 + 需求变更）**：自建账号 + JWT 鉴权 + `user_id` 越权隔离；已**关闭公开注册**，账号仅由管理员（`is_admin`）经 `POST /api/admin/users` 或数据库/CLI（`python -m app.cli create-user`）新增，首位管理员由 `MMA_ADMIN_USERNAME/PASSWORD` 启动时自动创建。详见 `specs/2026-08-28 - feat-registration-control/`。

### Docker Compose 一键启动（需本机 Docker）

```bash
cp .env.example .env   # 填云密钥 + JWT_SECRET
docker compose up -d    # api / worker / redis / postgres(pgvector) / minio / prometheus / grafana
```

生产部署（已上线腾讯云）见 `deploy/README.md`。

## REST API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录，返回 JWT（PyJWT HS256） |
| POST | `/api/admin/users` | 管理员创建用户（`require_admin` 鉴权，入参 username/password/可选 is_admin） |
| POST | `/api/tasks` | 上传文件（multipart `file`），创建任务并异步执行 |
| GET | `/api/tasks` | 任务列表（按 `user_id` 隔离） |
| GET | `/api/tasks/{id}` | 任务状态与进度 |
| GET | `/api/tasks/{id}/transcript` | 转写文本下载 |
| GET | `/api/tasks/{id}/minute` | 纪要 Markdown 下载（编辑后返回编辑内容） |
| PUT | `/api/tasks/{id}/minute` | 保存人工编辑后的纪要（`{"markdown": "..."}`） |
| POST | `/api/tasks/{id}/comments` | 新增批注（`{"text","author","quote"}`） |
| GET | `/api/tasks/{id}/comments` | 批注列表 |
| DELETE | `/api/tasks/{id}/comments/{comment_id}` | 删除批注 |
| GET | `/api/minutes` | 纪要历史列表 / 搜索（`q` / `from` / `to` / `topic`） |
| POST | `/api/tasks/{id}/regen` | 换模型/模板重生成纪要（M4） |
| POST | `/api/qa` | 检索问答 RAG（带来源引用 + 越权隔离 + 降级，M4） |
| GET | `/api/costs` | 成本统计（按日累计 / 明细 / 限额状态） |
| GET | `/metrics` | Prometheus 指标端点 |
| GET | `/health` | 健康检查 |

- 支持格式：MP4 / MKV / WAV / MP3 / M4A，单场 ≤ 2 小时。
- 状态机：`pending → running → succeeded / failed`；进度 0–100，转写阶段按切片推进（「第 x/N 段已完成」）。
- 云端 ASR/LLM 密钥缺失时自动降级（`whisper` / `extractive`），保证链路可跑通。

## 任务组（M1 · MVP）

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

## 任务组（M2 · 结构增强）

| 任务组 | 模块 | 说明 |
| --- | --- | --- |
| TG-0 结构化 Schema | `app/schemas.py` + `app/db.py` + `app/asr.py` | `ActionItem / Decision / OpenQuestion / StructuredMinute`；`Segment.speaker`；`minutes` / `comments` 表 |
| TG-1 行动项抽取 | `app/extractor.py` | Function-Calling 抽取（DeepSeek）+ 规则兜底（无密钥可跑通） |
| TG-2 说话人分离 | `app/diarization.py` + `app/asr.py` | 腾讯云 `SpeakerDiarization` 内置 + pyannote 兜底 + 占位 S1/S2 |
| TG-3 角色识别 | `app/role.py` | 主持人 / 汇报人 / 参会者（规则 + LLM 辅助） |
| TG-4 三模板 | `app/render.py` + `app/templates/` | Jinja2 标准 / 精简 / 详细 |
| TG-5 编辑批注 | `app/main.py` + `static/minute.html` | 编辑 / 批注接口 + 前端 + 持久化 |
| TG-6 历史检索 | `app/main.py` + `static/index.html` | `GET /api/minutes`（关键词 / 时间 / 主题） |
| TG-7 Eval 集 | `eval/` | 黄金基准集 + 评测脚本 + 三项指标 |

## 任务组（M3 · 生产化）

| 任务组 | 模块 | 说明 |
| --- | --- | --- |
| TG-0 服务拆分/队列 | `app/celery_app.py` + `docker-compose.yml` | Celery + Redis 队列，api/worker 独立容器可 `--scale` 扩缩 |
| TG-1 质量 | `pyproject.toml` + `ruff` + `pytest-cov` | lint + 覆盖率门槛 |
| TG-2 生产存储 | `app/db.py` + `app/storage.py` + `scripts/migrate_sqlite_to_pg.py` | SQLAlchemy 双模式（SQLite/PostgreSQL）+ S3 兼容对象存储（MinIO/腾讯云 COS） |
| TG-3 可观测 | `app/metrics.py` + `prometheus/` + `grafana/` | `/metrics` + 面板 + 告警规则 + request_id 中间件 |
| TG-4 安全 | `app/auth.py` + `app/security.py` + `app/crypto.py` + `app/audit.py` | 自建账号 + JWT + 越权隔离 + 魔数校验 + 提示词注入缓解 + AES-256 + 审计 |
| TG-5 性能测试 | `locustfile.py` | 大文件 / 长会议 / 并发压测 |
| TG-6 成本监控 | `app/cost.py` | cost_stats 按场/按日统计 + 限额告警 |
| TG-7 灰度上线 | `deploy/` | Caddy TLS + 回滚方案 + 观察报告（已上线腾讯云） |

## 任务组（M4 · 智能化）

| 任务组 | 模块 | 说明 |
| --- | --- | --- |
| TG-0 模型注册表 | `app/llm_registry.py` | 别名 → provider/base_url/model/api_key，`MMA_LLM_ALIAS` 热切换（v4-pro / v4-flash / qwen-plus） |
| TG-1 重生成 | `app/worker.py` + `app/main.py` | `POST /api/tasks/{id}/regen` 换模型/模板重生成 |
| TG-2 向量化 | `app/embedding.py` + `app/db.py` | pgvector + 云 embedding，纪要自动向量化（失败不阻断） |
| TG-3 检索问答 | `app/rag.py` + `app/main.py` | `POST /api/qa` 余弦 top-k + 来源引用 + 越权隔离 + 降级 |
| TG-4 评测 | `scripts/compare_models.py` + `scripts/eval_rag.py` + `eval/rag_eval.json` | 多模型对比 + RAG Eval 集 |

## 需求变更（进行中 · 账号注册管控）

| 任务组 | 内容 | 状态 |
| --- | --- | --- |
| TG-0 | `users` 表加 `is_admin` + 迁移 | ⏳ 待实现 |
| TG-1 | 管理员初始化（`MMA_ADMIN_USERNAME/PASSWORD`）+ `require_admin` 依赖 | ⏳ 待实现 |
| TG-2 | 关闭 `POST /api/auth/register` + 新增 `POST /api/admin/users` | ⏳ 待实现 |
| TG-3 | CLI `python -m app.cli create-user` + 文档 | ⏳ 待实现 |
| TG-4 | 前端收敛（删 `register.html`）+ 测试 + 收口 | ⏳ 待实现 |

## 测试

```bash
./venv/Scripts/python.exe -m pytest tests/ --cov=app
```

覆盖率：M1 78% → M2 82% → M3 81% → M4 82%。

## 质量评测（Eval）

```bash
# 演示评测流程（种子样例）：生成 predicted 产物 → 跑评测脚本
./venv/Scripts/python.exe -m eval.make_seed_predicted --task-dir <目录>
./venv/Scripts/python.exe -m eval.eval_quality --golden-dir eval/golden --task-dir <目录>
```

RAG 检索评测（M4）：

```bash
./venv/Scripts/python.exe scripts/eval_rag.py
./venv/Scripts/python.exe scripts/compare_models.py   # 多模型质量/成本/耗时对比
```

真实评测需人工标注黄金基准（`eval/golden/*.json`），跑通 pipeline 后对比。详见 `eval/README.md`。

## 离线 CLI（M0 遗留，链路验证用）

```bash
./venv/Scripts/python.exe pipeline.py samples/meeting-001.mp3 --asr whisper --llm extractive
```

## 目录结构

```
app/             # 服务包（config / audio / asr / summary / render / pipeline / ingestion / db / worker / main
                 #        + schemas / extractor / diarization / role / auth / security / crypto / audit
                 #        + storage / celery_app / metrics / cost / llm_registry / embedding / rag + templates/）
static/          # 前端（index.html 上传+问答 / minute.html 编辑 / login.html / auth.js）
tests/           # 单元与集成测试（覆盖率 M4 82%）
eval/            # 质量评测（黄金基准集 + 评测脚本 + 指标 + RAG Eval 集）
scripts/         # 运维/评测脚本（迁移 / 模型对比 / RAG 评测 / 话者覆盖验证）
deploy/          # 部署（指南 / Caddyfile / 回滚 / 观察报告 / pgvector 初始化）
prometheus/ grafana/   # 可观测（采集配置 + 面板 + 告警规则）
Dockerfile / docker-compose.yml   # 容器化多服务编排（api/worker/redis/postgres/minio/prometheus/grafana）
audio.py / asr.py / summarize.py / pipeline.py / eval_cer.py / make_sample.py  # M0 脚本（离线 CLI）
config.py        # M0 集中配置（根）；服务配置见 app/config.py
samples/         # 会议音频（gitignore，需自备真实数据）
data/            # 服务数据：上传文件 + 任务产物 + SQLite（gitignore）
specs/           # 阶段执行文档（plan / requirements / validation）
docs/            # mission / roadmap / tech-stack 源文档
```
