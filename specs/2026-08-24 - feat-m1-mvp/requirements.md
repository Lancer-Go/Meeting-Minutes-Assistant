# M1 · MVP（可用闭环 · 云 API）— 需求与范围说明 (Requirements)

| 文档类型 | 需求与范围说明 |
| --- | --- |
| 阶段 | M1 · MVP（可用闭环 · 云 API） |
| 分支 | feat/m1-mvp |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文说明 M1 的**范围、已定决策与上下文**，作为 plan.md 的依据与 validation.md 的对照。M1 复用 M0 已锁定选型（ASR 腾讯云 16k_zh / LLM DeepSeek-chat，见 [选型决策记录](../../docs/decisions/选型决策记录.md)），不再重复选型。

## 1. 目标（一句话）

交付可用的完整闭环（本地开发环境，ASR/LLM 走云 API），满足 FR-01~07，无技术背景用户可自助「上传 → 得到纪要」。

## 2. 范围

### 范围内 (In Scope) — 对应 FR-01~07

| FR | 需求 | M1 交付 |
| --- | --- | --- |
| FR-01 | 文件上传 | `ingestion` 上传接口 + 格式白名单/大小/时长校验 |
| FR-02 | 音频提取 | `audio` 模块（FFmpeg 抽音轨、标准化） |
| FR-03 | 语音转写 | `asr` 模块（腾讯云 16k_zh，带时间戳） |
| FR-04 | 纪要生成 | `summary` 模块（DeepSeek-chat，结构化 Markdown） |
| FR-05 | 行动项提取 | 纪要中含行动项清单（结构化抽取细化留 M2） |
| FR-06 | 输出导出 | `render` 输出 Markdown + 下载接口 |
| FR-07 | 任务状态 | Task 状态机 + 进度 + 运行日志 |

- 后端：FastAPI（异步、类型友好）。
- 任务队列：MVP 用轻量方案（FastAPI BackgroundTasks，预留 Celery+Redis 切换点）。
- 存储：本地文件系统 + SQLite。
- 前端：极简 HTML/JS 上传页 + 进度条（先跑通，不追求美观）。
- 复用 M0：`pipeline.py` 重构为 `ingestion / audio / asr / summary / render` 模块。

### 范围外 (Out of Scope) — M1

- ❌ 结构化行动项抽取（ActionItem/Decision JSON Schema、Function-Calling 评测）—— M2。
- ❌ 说话人分离 / 角色标注（主持人/汇报人/参会者）—— M2。
- ❌ 纪要多模板（标准/精简/详细）、人工编辑与批注、历史检索 —— M2。
- ❌ 生产化部署（K8s、PostgreSQL、对象存储、可观测面板、CI/CD）—— M3。
- ❌ 安全合规（鉴权、AES-256 加密、审计、越权防护）—— M3。
- ❌ 多模型热切换 / RAG 检索问答 / 实时转写 —— M4。
- ❌ PDF / docx 导出（Markdown 即可，mission §8 决策 7）—— 后期。

## 3. 关键决策（沿用 mission.md §8，逐条映射到 M1 影响）

| # | 决策点 | 结论 | 对 M1 的影响 |
| --- | --- | --- | --- |
| 1 | 首期形态 | ✅ 云端 SaaS 优先 | M1 以本地开发环境交付服务形态，云端部署留 M3 |
| 2 | ASR 选型 | ✅ 走云 API（接受数据出域） | 复用腾讯云 16k_zh（M0 已锁定），无需本地 GPU |
| 3 | 主要语言 | ✅ 中文为主，英文术语混用 | 转写/纪要链路按中文为主处理 |
| 4 | 会议时长 | ✅ 单场 ≤ 2 小时 | 上传校验时长上限 ≤ 2h，文件大小相应控制 |
| 5 | 成本预算 | ✅ 利润 0，性价比优先 | 沿用 DeepSeek-chat（单场 ¥0.045）+ 腾讯云 ASR，目标 ≤ ¥1/场 |
| 6 | IM/待办集成 | 🕐 暂不需要 | M1 不做第三方集成 |
| 7 | 输出格式 | ✅ Markdown 即可 | 纪要/转写均 Markdown 输出，不做 PDF/docx |

## 4. 技术选型（沿用 tech-stack.md A5，M0 已锁定）

| 决策点 | 已定方向 | 锁定结论 | M1 用法 |
| --- | --- | --- | --- |
| ASR 主方案 | ✅ 云 API | ✅ 腾讯云 16k_zh（备选阿里云 NLS，本地兜底 faster-whisper） | `asr` 模块 `ASRProvider` 默认实现 |
| LLM 主方案 | ✅ 性价比高 | ✅ DeepSeek-V3（deepseek-chat）（备选 Qwen） | `summary` 模块 `LLMProvider` 默认实现 |
| Web 框架 | 🔶 FastAPI | — | 服务层 |
| 任务队列 | 🔶 Celery+Redis / BackgroundTasks | M1 用轻量方案，预留切换点 | `orchestrator` |
| 存储 | 🔶 S3+PostgreSQL / 本地+SQLite | M1 用本地 FS + SQLite | `storage` |
| 部署形态 | ✅ 云端 SaaS 优先 | 🕐 云平台选型留 M1+ 落地 | M1 本地 Docker Compose 一键起 |

## 5. 约束与假设

- 运行环境：Python 3.11 + FastAPI + FFmpeg + SQLite，`venv` 隔离；ASR/LLM 走云 API（需 `.env` 密钥，M0 已配置）。
- 数据隐私：首期接受云 API 处理（数据出域），本地化部署留作后期选项。
- 形态：本地开发环境可运行的服务（Docker Compose 一键启动），非生产部署。
- 单机假设：MVP 用单机 BackgroundTasks，不引入分布式队列；后续 M3 迁移 Celery+Redis。
- 长文本：纪要生成沿用 M0 的 Map-Reduce 分块总结（应对 mission §7「长会议超上下文」风险）。

## 6. 上下文（链路与模块）

M1 落地的是 tech-stack.md B2 中**处理流水线 + 基础设施的最小闭环**：

```
ingestion（上传/校验）
   → audio（FFmpeg 抽音轨）
   → asr（腾讯云 16k_zh 转写）
   → summary（DeepSeek-chat 纪要）
   → render（Markdown 渲染）
   ⇅ storage（本地 FS + SQLite 持久化）
   ⇅ orchestrator（任务状态机 + 队列调度）
```

- M0 已验证 `audio → asr → summary` 核心链路可行、选型锁定；M1 将其模块化并套上「上传 + 任务管理 + 导出 + 前端」外壳。
- M1 不涉及 `extractor`（行动项结构化抽取，M2）、`nlp`（角色标注，M2）。
- 数据模型沿用 tech-stack.md B4：`Task` / `Transcript`(segments) / `Minute`；API 沿用 B4 的 RESTful 设计（`POST /api/tasks`、`GET /api/tasks/{id}` 等）。
