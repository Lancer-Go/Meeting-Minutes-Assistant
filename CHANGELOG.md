# 更新日志 (Changelog)

本文件记录项目的所有重要变更。**每次提交（commit）都必须在此登记一条记录**，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范。

## 分类约定

| 分类 | 含义 |
| --- | --- |
| `新增` | 新功能 / 新文件 |
| `变更` | 对现有功能的修改 |
| `修复` | Bug 修复 |
| `文档` | 文档相关变更 |
| `移除` | 删除的功能 / 文件 |
| `杂项` | 其他无法归类的变更 |

> 每条记录末尾附提交哈希前 7 位（如 `6d15d7c`），便于回溯。

## [Unreleased]

<!-- ⬇️ 新提交在此登记，格式：
### 分类
- 变更说明（提交哈希前 7 位）
-->

### 新增
- 新增 M3 生产化任务准备（plan / requirements / validation 三文档）：云端部署（腾讯云服务器 + Docker Compose 单机多服务，Worker 独立容器预留扩缩）、生产存储（PostgreSQL + MinIO，S3 兼容预留迁 COS）、自建账号体系基础版（注册/登录 + JWT）、Prometheus + Grafana 可观测、CI/CD、成本监控、灰度上线（42a77f6）
- 实现 M2 结构化 Schema 与数据模型：`ActionItem / Decision / OpenQuestion / StructuredMinute`（`app/schemas.py`，含 Function-Calling JSON Schema）+ `Segment.speaker` / `Transcript.speakers` + SQLite `minutes` / `comments` 表（4e9351c）
- 实现 M2 行动项抽取 `app/extractor.py`：DeepSeek-V4 Pro 走 Function-Calling（`extract_decisions/actions/questions` tool_schema）+ 本地规则兜底（负责人/截止/待办正则，无密钥可跑通）（4e9351c）
- 实现 M2 说话人分离 `app/diarization.py` 与角色识别 `app/role.py`：腾讯云 `SpeakerDiarization` 内置 + pyannote 兜底 + 占位 S1/S2；主持人/汇报人/参会者（规则 + LLM 辅助）（4e9351c）
- 实现 M2 Jinja2 三模板渲染（标准/精简/详细，`app/templates/`）+ 编辑批注接口（`PUT /api/tasks/{id}/minute`、`POST|GET|DELETE .../comments`）+ 历史检索（`GET /api/minutes`）+ 前端编辑页 `minute.html` 与搜索框（4e9351c）
- 实现 M2 Eval 集与评测脚本（`eval/`）：黄金基准集 + 三项指标（行动项三要素完整率 / 说话人正确率 / 返工率），`make_seed_predicted` 可离线演示评测闭环（4e9351c）
- 转写阶段按切片推进进度「第 x/N 段已完成」：`ASRProvider.transcribe` 增加 progress_callback（腾讯云逐段回调、本地 whisper 按已处理时长），`tasks` 表新增 progress_message 列（含旧库迁移），前端状态行展示进度说明（2a7c296）
- 新增 M2 结构增强任务准备（plan / requirements / validation 三文档）（9f7040e）
- 实现 M1 MVP：FastAPI 服务 + 异步全链路（app/ 包 TG-0~TG-7：上传校验/音频提取/腾讯云切片转写/DeepSeek 纪要/Markdown 导出/任务状态机/极简前端/重试与结构化日志），含 Docker Compose 一键启动与单测覆盖率 78%（9b99e1e）
- 新增 M1 MVP 任务准备（plan / requirements / validation 三文档）（042548b）
- 新增 M0 概念验证任务准备（plan / requirements / validation 三文档）（605e4a3）
- 实现 M0 任务组 TG-0~TG-6：环境脚手架、音频提取、语音转写、纪要生成、端到端流水线、CER 评测（audio / asr / summarize / pipeline / eval_cer / config / make_sample + requirements.txt）（3e1f442）
- 新增《选型决策记录》初稿（含本地离线实测 CER / 耗时 / 成本）（3e1f442）
- 接入云 ASR 实测：阿里云 NLS 实时语音转写 + 腾讯云录音文件识别（b3499f0）

### 变更
- `render` 由纯字符串拼接升级为 Jinja2 模板化渲染（新增 `render_minutes`，保留 `build_minutes_md` 向后兼容）；依赖新增 `jinja2==3.1.6`（4e9351c）
- `pipeline` 全链路扩展：转写 → 说话人分离 → 角色识别 → 纪要 + 结构化抽取 → 三模板渲染；新增 `structured_minute.json` / `minutes.brief.md` / `minutes.detailed.md` 产物与 structured 统计（4e9351c）
- `asr` 的 `Segment` 增 `speaker` 字段、`Transcript` 增 `speakers`；腾讯云启用 `SpeakerDiarization` 话者分离（结果读取 `SpeakerId`）（4e9351c）
- `db` 新增 `minutes` / `comments` 表及 `save_minute` / `search_minutes` / `add_comment` 等函数；`main` 新增编辑/批注/检索路由；`worker` 成功后回写 minutes 表（4e9351c）
- LLM 主方案由 DeepSeek-V3（deepseek-chat）升级为 DeepSeek-V4 Pro（deepseek-v4-pro，新增 `MMA_DEEPSEEK_MODEL` 配置项）提升会议总结质量；同步更新 tech-stack v0.5、选型决策记录、roadmap 与 M0-M2 specs（2a7c296）
- 阶段执行文档目录迁移至 specs/ 下（3e1f442）
- 用真实会议（80min）完成三家 ASR 对比与 DeepSeek 端到端纪要，锁定选型（ASR 腾讯云 16k_zh / LLM DeepSeek-chat），回填《选型决策记录》（b3499f0）

### 文档
- tech-stack 更新至 v0.7，新增 A6「成本模型与计费参考」：DeepSeek 2026-08 官方价格表（V4 Pro / Flash / Vision-Exp，含高峰/空闲与缓存命中价）、扣费规则、V4 Pro 单场成本估算（推算 ≈ ¥0.2~0.8/场·空闲，标注假设待 M3 重测）、flash 降本备选；选型决策记录补 V4 Pro 价格备注（5e774e8）
- tech-stack 更新至 v0.6，回填 M2 实际选型（Jinja2 三模板 / 腾讯云 SpeakerDiarization / 占位话者兜底 / minutes-comments 表 / M2 REST 路由 / 覆盖率 82%）；roadmap「下一步」由推进 M2 更正为推进 M3；README 补充 M2 任务组与 Eval 用法（4e9351c）
- tech-stack 更新至 v0.4，回填 M1 实际选型（FastAPI / BackgroundTasks / SQLite+本地FS / Docker Compose 落地；B4 数据模型与 REST API 对齐 M1 实现）；roadmap「下一步」由启动 M0 更正为推进 M2（0c13169）
- tech-stack 更新至 v0.3，回填 M0 实测锁定厂商（ASR 腾讯云 16k_zh / LLM DeepSeek-chat），关联《选型决策记录》（a2ada36）

## [0.2.0] - 2026-08-24

### 文档
- 新增 CHANGELOG.md，建立每次提交登记变更的规范（c72a725）
- 确认关键决策（云端 SaaS 优先 / 云 ASR / 中文为主 / ≤2h / 利润 0），三文档更新至 v0.2（6d15d7c）
- 收敛为 mission / roadmap / tech-stack 三文件，roadmap 重写为详细实现路线图（afd32d6）
- 按 SDD 规范拆分文档目录（mission / roadmap / tech-stack 等 12 个文件）（f8a6f4f）

## [0.1.0] - 2026-08-23

### 新增
- 新增项目总章程与 SDD 软件设计文档（3488dcc）
- 会议纪要助手项目初始化（fddfdc9）
