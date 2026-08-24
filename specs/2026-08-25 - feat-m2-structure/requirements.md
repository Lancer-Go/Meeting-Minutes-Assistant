# M2 · 结构增强（纪要质量）— 需求与范围说明 (Requirements)

| 文档类型 | 需求与范围说明 |
| --- | --- |
| 阶段 | M2 · 结构增强（纪要质量） |
| 分支 | feat/m2-structure |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文说明 M2 的**范围、已定决策与上下文**，作为 plan.md 的依据与 validation.md 的对照。M2 复用 M0 已锁定选型（ASR 腾讯云 16k_zh / LLM DeepSeek-chat，见 [选型决策记录](../../docs/decisions/选型决策记录.md)），新增结构化输出（Function-Calling）、说话人分离、角色识别、模板渲染与编辑检索，不重复 ASR/LLM 主方案选型。

## 1. 目标（一句话）

提升纪要质量与可用性，满足 FR-08~11、G3：结构化行动项（决议/负责人/截止）、说话人角色标注、多模板（标准/精简/详细）、可编辑与历史检索。

## 2. 范围

### 范围内 (In Scope) — 对应 FR-03/FR-05 细化 + FR-08~11

| FR | 需求 | M2 交付 |
| --- | --- | --- |
| FR-05 | 行动项提取（细化） | `extractor` 模块：Function-Calling 抽取 `ActionItem / Decision / OpenQuestion`（负责人/截止时间/优先级/状态） |
| FR-03 | 语音转写（细化） | `Segment.speaker` 标注 + 说话人分离（云 ASR 内置 / pyannote / whisperX 兜底） |
| FR-11 | 角色标注 | 主持人 / 汇报人 / 参会者（规则 + LLM 辅助） |
| FR-08 | 纪要模板 | 标准 / 精简 / 详细三套（Jinja2） |
| FR-09 | 编辑批注 | 纪要人工编辑、批注并持久化 |
| FR-10 | 历史管理 | 按时间 / 主题 / 关键词检索 |

- 结构化输出：定义 `ActionItem / Decision / OpenQuestion` JSON Schema，用 Function-Calling 约束 LLM。
- 说话人分离：优先云 ASR 内置话者分离，pyannote-audio / whisperX 兜底。
- 角色识别：规则（句式/频次启发式）+ LLM 辅助。
- 模板引擎：Jinja2 渲染三套模板。
- 前端：纪要编辑页（可改可批注）+ 历史列表与搜索。

### 范围外 (Out of Scope) — M2

- ❌ 多模型热切换 / RAG 向量检索问答 / 实时转写 —— M4（历史检索 M2 用 SQLite LIKE，向量化留 M4）。
- ❌ 行动项同步到 IM / 待办（飞书 / 钉钉）—— G6，后期再看。
- ❌ 生产化部署（K8s、PostgreSQL、对象存储、可观测面板、CI/CD）—— M3。
- ❌ 安全合规（鉴权、AES-256 加密、审计、越权防护）—— M3。
- ❌ PDF / docx 导出（Markdown 即可，mission §8 决策 7）—— 后期。
- ❌ 视频画面分析 / 会议室硬件集成 / 跨组织高级权限 —— mission §3 Out of Scope。

## 3. 关键决策（沿用 mission.md §8，逐条映射到 M2 影响）

| # | 决策点 | 结论 | 对 M2 的影响 |
| --- | --- | --- | --- |
| 1 | 首期形态 | ✅ 云端 SaaS 优先 | M2 仍本地开发环境交付，云端部署留 M3 |
| 2 | ASR 选型 | ✅ 走云 API（接受数据出域） | 说话人分离优先用云 ASR 内置能力；本地兜底仅评测/降本场景 |
| 3 | 主要语言 | ✅ 中文为主，英文术语混用 | 抽取/角色识别提示词按中文为主设计 |
| 4 | 会议时长 | ✅ 单场 ≤ 2 小时 | 长文本抽取沿用 Map-Reduce 分块，避免超上下文 |
| 5 | 成本预算 | ✅ 利润 0，性价比优先 | Function-Calling 复用 DeepSeek-chat，抽取增量成本计入单场成本估算 |
| 6 | IM/待办集成 | 🕐 暂不需要 | M2 不做第三方集成，行动项仅结构化存储 |
| 7 | 输出格式 | ✅ Markdown 即可 | 三套模板均输出 Markdown，不做 PDF/docx |

## 4. 技术选型（沿用 tech-stack.md A2/A5，M0 已锁定主方案）

| 决策点 | 已定方向 | 锁定结论 | M2 用法 |
| --- | --- | --- | --- |
| ASR 主方案 | ✅ 云 API | ✅ 腾讯云 16k_zh（备选阿里云 NLS，本地兜底 faster-whisper） | 复用 `asr` 模块；新增话者分离能力 |
| LLM 主方案 | ✅ 性价比高 | ✅ DeepSeek-V3（deepseek-chat）（备选 Qwen） | `extractor` 走 Function-Calling；`summary` 复用 |
| 说话人分离 | 🔶 云 ASR 内置（首选）/ pyannote（兜底）/ whisperX（备选） | M2 实测确认腾讯云话者分离，pyannote 兜底 | `DiarizationProvider` 抽象 |
| 结构化输出 | ✅ Function-Calling / JSON Schema | — | `extractor` 的 `tool_schema` |
| 模板渲染 | 🔶 Jinja2 | — | `render` 三套模板 |
| 角色标注 | 🔶 规则 + LLM 辅助 | — | `role` 标注 |
| 存储 | 🔶 本地 FS + SQLite（M1 沿用） | — | 新增 `minutes` / `comments` 表 |

## 5. 约束与假设

- 运行环境：Python 3.11 + FastAPI + FFmpeg + SQLite，`venv` 隔离；ASR/LLM 走云 API（`.env` 密钥，M0/M1 已配置）。
- 单机假设：沿用 M1 的 BackgroundTasks + SQLite，不引入分布式队列 / 向量库。
- 说话人分离风险：腾讯云 16k_zh 是否稳定返回 speaker 标签需实测；若不支持，pyannote-audio 本地兜底（新增依赖，首次需下载模型）。
- 长文本：抽取与角色识别沿用 Map-Reduce 分块，避免超上下文（mission §7 风险）。
- 数据隐私：首期接受云 API 处理（数据出域），本地化部署留作后期选项。
- 质量判定：M2 退出以 Eval 集实测指标为准，不达标不发版（tech-stack B5「质量底线」）。

## 6. 上下文（链路与模块）

M2 在 M1「处理流水线 + 基础设施」基础上，**扩展纪要质量链路**：

```
ingestion（上传/校验，M1 复用）
   → audio（FFmpeg 抽音轨，M1 复用）
   → asr（腾讯云 16k_zh 转写，M1 复用）
   → diarization（说话人分离，M2 新增）──┐
   → summary（DeepSeek 纪要，M1 复用）    │
   → extractor（行动项结构化抽取，M2 新增）┤
   → role（角色识别，M2 新增）────────────┘
   → render（Jinja2 三模板，M2 改造）
   ⇅ storage（本地 FS + SQLite：minutes / comments 表，M2 扩展）
   ⇅ api（编辑 / 批注 / 历史检索接口，M2 扩展）
```

- M1 已落地模块：`ingestion / audio / asr / summary / render / db(storage) / pipeline / worker / main`（`app/` 包），其中 `asr.Segment` 无 speaker、`summary` 输出自由文本 Markdown、`render` 为纯字符串拼接、`db` 仅 `tasks` 表。
- M2 新增 / 改造：`schemas.py`（结构化 Schema）、`extractor.py`（抽取）、`diarization.py`（说话人）、`role.py`（角色）、`render.py` 改造（Jinja2 三模板）、`db.py` 扩展（minutes / comments 表）、`main.py` 扩展（编辑 / 批注 / 历史检索路由）。
- 数据模型对齐 tech-stack.md B4：`Transcript`(segments[+speaker]) / `Minute`(title, summary_md, decisions[], actions[], open_questions[], speakers[])；API 新增 `PUT /api/tasks/{id}/minute`、`POST|GET /api/tasks/{id}/comments`、`GET /api/minutes`。
