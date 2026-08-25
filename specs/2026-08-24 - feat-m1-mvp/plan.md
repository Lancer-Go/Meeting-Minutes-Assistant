# M1 · MVP（可用闭环 · 云 API）— 执行计划 (Plan)

| 文档类型 | 执行计划 |
| --- | --- |
| 阶段 | M1 · MVP（可用闭环 · 云 API） |
| 分支 | feat/m1-mvp |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文把 roadmap.md 中 M1 的 8 步工作顺序组织为可执行的**任务组**。每个任务组含目标、任务项、产出与验收；任务组之间按依赖推进（前一组的验收是后一组的输入）。M1 复用 M0 已锁定选型（ASR 腾讯云 16k_zh / LLM DeepSeek-V4 Pro（deepseek-v4-pro，由 V3 升级）），从脚本式 `pipeline.py` 升级为 FastAPI 服务 + 异步全链路。

## 任务组总览

| 任务组 | 内容 | 产出 | 依赖 |
| --- | --- | --- | --- |
| TG-0 | 项目骨架 | 目录结构 + 配置管理 + 依赖锁定 | — |
| TG-1 | 模块化重构 | `audio / asr / summary / render` 四模块 | TG-0 |
| TG-2 | 上传接口 | `ingestion` 上传 + 格式/大小/时长校验 | TG-1 |
| TG-3 | Task 数据模型与状态机 | SQLite Task 表 + 状态机 | TG-2 |
| TG-4 | 任务队列异步执行 | 上传后自动全链路异步执行 | TG-3 |
| TG-5 | Markdown 导出与下载 | 纪要导出 + 下载接口 | TG-4 |
| TG-6 | 极简前端 | 上传页 + 进度展示 + 结果下载 | TG-5 |
| TG-7 | 错误处理与日志 | 重试 + 结构化日志 | TG-1~6 |

## 任务组明细

### TG-0 · 项目骨架
- **目标**：可复现、可配置的项目结构。
- **任务项**：
  - 建立服务目录结构（`app/` 或 `src/` 分层：`ingestion / audio / asr / summary / render / orchestrator / storage / api`）。
  - 配置管理：沿用 M0 的 `config.py` + `.env`（补服务端口、存储路径、队列配置项）。
  - 依赖锁定：更新 `requirements.txt`（FastAPI、uvicorn、SQLAlchemy 或纯 sqlite3、队列相关）。
- **产出**：完整目录骨架 + `requirements.txt` + `config.py`。
- **验收**：`pip install -r requirements.txt` 无报错；服务能 `uvicorn` 启动返回健康检查。

### TG-1 · 模块化重构
- **目标**：把 M0 脚本式写法重构为可复用模块，去掉 `pipeline.py` 的脚本式串联。
- **任务项**：
  - 拆出 `audio`（FFmpeg 抽音轨/归一化）、`asr`（`ASRProvider` 抽象，主用腾讯云 16k_zh）、`summary`（`LLMProvider` 抽象，主用 DeepSeek-V4 Pro）、`render`（Markdown 渲染）。
  - 保留 M0 的 Provider 抽象与 Map-Reduce 长文本逻辑，改为模块函数可被服务调用。
- **产出**：四模块可独立导入、单元可测。
- **验收**：`pipeline.py` 语义可由模块组合重现；四模块各含纯逻辑可单测。

### TG-2 · 上传接口
- **目标**：接收文件上传并做合法校验。
- **任务项**：
  - 实现 `ingestion` 上传接口 `POST /api/tasks`（multipart 文件）。
  - 格式白名单：MP4 / MKV / WAV / MP3 / M4A。
  - 大小校验（单场 ≤ 2 小时对应大小上限）与时长校验（`ffprobe` 读时长）。
  - 文件落盘到本地存储目录，生成唯一 task 标识。
- **产出**：上传接口 + 校验逻辑 + 落盘。
- **验收**：合法文件上传成功、非法格式/超大小/超时长被拒绝并返回明确错误。

### TG-3 · Task 数据模型与状态机
- **目标**：任务可持久化、可追踪状态。
- **任务项**：
  - SQLite 建 `Task` 表（id, source_file, status, progress, created_at, error 等，对应 tech-stack B4）。
  - 状态机：`pending → running → succeeded / failed`。
  - 提供状态查询接口 `GET /api/tasks/{id}`。
- **产出**：Task 数据模型 + 状态机 + 状态查询接口。
- **验收**：任务状态流转正确；重启服务后任务仍可查询（持久化）。

### TG-4 · 任务队列异步执行
- **目标**：上传后异步跑全链路，不阻塞请求。
- **任务项**：
  - 接入轻量队列：优先 FastAPI `BackgroundTasks`（单机足够），预留 Celery+Redis 切换点。
  - 异步执行 `audio → asr → summary → render` 全链路，逐段更新 `progress`（转写阶段按切片推进「第 x/N 段已完成」）。
  - 中间产物（transcript / minute）持久化到 SQLite / 本地文件。
- **产出**：异步任务编排 + 进度更新。
- **验收**：上传后立即返回 task id，后台自动完成全链路；进度可查询。

### TG-5 · Markdown 导出与下载
- **目标**：纪要可下载。
- **任务项**：
  - 实现 `render` 输出 Markdown 纪要文件落盘。
  - 下载接口 `GET /api/tasks/{id}/minute`（返回 Markdown 内容/文件）。
  - 转写文本接口 `GET /api/tasks/{id}/transcript`。
- **产出**：纪要/转写下载接口。
- **验收**：任务完成后可下载标准 Markdown 纪要与转写文本。

### TG-6 · 极简前端
- **目标**：无技术背景用户可自助「上传 → 得到纪要」。
- **任务项**：
  - 极简 HTML/JS 上传页（文件选择 + 上传按钮）。
  - 进度展示（轮询 `GET /api/tasks/{id}` 状态与进度，含转写切片进度说明）。
  - 结果下载（完成后提供纪要下载链接）。
- **产出**：可用的上传页 + 进度条 + 下载。
- **验收**：浏览器端完整走通「上传 → 等待 → 下载纪要」且状态/进度可见。

### TG-7 · 错误处理、重试、结构化日志
- **目标**：链路稳健、可观测、可排障。
- **任务项**：
  - 全链路错误捕获与失败状态回写（`failed` + error 信息）。
  - 关键步骤（ASR/LLM）失败重试（指数退避）。
  - 结构化日志（JSON），记录任务 id / 耗时 / 错误 / 成本。
- **产出**：错误处理 + 重试 + 结构化日志。
- **验收**：注入故障（断网/密钥错）能被捕获、重试并最终标记 failed，日志可定位。

## 依赖关系

```
TG-0 ──► TG-1 ──► TG-2 ──► TG-3 ──► TG-4 ──► TG-5 ──► TG-6
                                        │
                                        └──────────────────► TG-7
```

> TG-7（错误处理/日志）贯穿 TG-1~6，最后统一收口验证。任务组按上述依赖串行推进。
