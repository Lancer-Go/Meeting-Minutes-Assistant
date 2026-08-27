# M4 · 智能化（生态打通）— 需求与范围说明 (Requirements)

| 文档类型 | 需求与范围说明 |
| --- | --- |
| 阶段 | M4 · 智能化（生态打通） |
| 分支 | feat/m4-intelligence |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文说明 M4 的**范围、已定决策与上下文**，作为 plan.md 的依据与 validation.md 的对照。M4 复用 M0~M3 已锁定选型（ASR 腾讯云 16k_zh / LLM DeepSeek-V4 Pro（deepseek-v4-pro）/ FastAPI / Docker Compose / PostgreSQL + MinIO / 腾讯云 COS，见 [选型决策记录](../../docs/decisions/选型决策记录.md)），新增**多模型切换（LLM 侧）**与**检索问答（RAG）**两项能力，不重复 ASR 与基础设施选型。四项关键选型已由用户 2026-08-27 咨询确认（见 §4）。

## 1. 目标（一句话）

在 M3「稳定可扩展的云端 SaaS」基础上补齐**智能化**：① 实现 LLM 侧多模型可配置热切换（DeepSeek-V4 Pro 主 / V4 Flash 降本 / Qwen 备选），② 实现会议历史向量化 + 检索问答（RAG，支持「上次会议谁负责 X」式提问），对应 FR-12 与 G5；G6（IM/待办同步）与 G7（实时转写）维持 mission §8-6 / §3 的「🕐 暂不需要」，留后期。

## 2. 范围

### 范围内 (In Scope) — 对应 FR-12 + G5

| 维度 | 需求 | M4 交付 |
| --- | --- | --- |
| 多模型切换 | FR-12（切换 LLM 模型） | LLM Provider 统一注册表 + 配置化热切换（V4 Pro 主 / V4 Flash 降本 / Qwen 备选），summary 与 extractor 走同一注册表，per-task 换模型重生成 |
| 检索问答 | G5（历史检索 + 智能问答） | 纪要向量化（pgvector）+ 云 embedding + 问答接口（带来源引用、越权隔离、降级兜底） |

### 范围外 (Out of Scope) — M4

- ❌ 生态打通（G6，行动项同步飞书 / 钉钉 / 企业微信 / 待办）—— mission §8-6「🕐 暂不需要」，留后期。
- ❌ 实时转写（G7，流式 ASR）—— mission §3 Out of Scope「后期再看」，留后期。
- ❌ ASR 侧多模型热切换（阿里云 NLS / faster-whisper 本地兜底）—— 用户确认 ASR 维持现状（M0 已锁腾讯云 16k_zh；`ASRProvider` 抽象已存在，本次不扩展）。
- ❌ 多模态 / 视频画面分析、会议室硬件集成、跨组织高级权限体系（RBAC）、本地私有化部署 —— mission §3 延续排除。
- ❌ PDF / docx 导出 —— mission §8-7，Markdown 即可。

## 3. 关键决策（沿用 mission.md §8，逐条映射到 M4 影响）

| # | 决策点 | 结论 | 对 M4 的影响 |
| --- | --- | --- | --- |
| 1 | 首期形态 | ✅ 云端 SaaS 优先 | M4 能力在现有云端服务内实现（FastAPI + Celery + PostgreSQL），不新增部署形态 |
| 2 | ASR 选型 | ✅ 走云 API（接受数据出域） | M4 不动 ASR（用户确认维持现状）；embedding 走云 API，沿用出域策略 |
| 3 | 主要语言 | ✅ 中文为主，英文术语混用 | embedding 选中文友好的 bge-m3 类；检索问答、Eval 集均按中文设计 |
| 4 | 会议时长 | ✅ 单场 ≤ 2 小时 | 纪要 chunk 大小按单场纪要量级设计（summary_md 通常数 KB~数十 KB） |
| 5 | 成本预算 | ✅ 利润 0，性价比优先 | pgvector 复用 PostgreSQL 零新增服务；云 embedding 按量计费；V4 Flash 作降本通道；灰度对比控成本 |
| 6 | IM/待办集成 | 🕐 暂不需要 | M4 不做 G6，留后期（用户确认） |
| 7 | 输出格式 | ✅ Markdown 即可 | 纪要渲染链路不变；问答答案输出 Markdown（带来源引用） |

## 4. 技术选型（沿用 tech-stack.md A2/A4/B4 + 用户确认）

| 决策点 | 已定方向 | 锁定结论 | M4 用法 |
| --- | --- | --- | --- |
| M4 范围 | 🔶 四项能力（roadmap） | ✅ **聚焦「多模型切换 + 检索问答(RAG)」两项**，G6/G7 留后期（用户 2026-08-27 确认） | 全文 |
| 向量存储 | 🔶 pgvector / Milvus（tech-stack A2） | ✅ **pgvector**（复用现有 PostgreSQL，零新增服务，与 M3 生产存储一致；用户确认） | TG-2 / TG-3 |
| Embedding 模型 | 🔶 未定 | ✅ **云 Embedding API**（OpenAI 兼容接口，如 bge-m3；按量计费、免运维；用户确认） | TG-2 / TG-3 |
| 多模型切换范围 | 🔶 Provider 可插拔（A4 原则 1） | ✅ **仅 LLM 侧**（V4 Pro 主 + V4 Flash 降本 + Qwen 备选）；ASR 维持现状（用户确认） | TG-0 / TG-1 |
| LLM 模型集 | ✅ DeepSeek-V4 Pro 已锁（A5） | 新增 **deepseek-v4-flash**（降本，价格约 Pro 1/3）+ **qwen-plus**（备选，已抽象未落地抽取） | TG-1 |
| 向量扩展 | — | **pgvector**（PostgreSQL 扩展，`CREATE EXTENSION vector`） | TG-2 |
| 问答生成模型 | ✅ DeepSeek-V4 Pro | 复用主模型生成带引用的答案 | TG-3 |

## 5. 约束与假设

- pgvector 仅生产 PostgreSQL 模式启用（需 `CREATE EXTENSION vector`）；本地 SQLite 开发模式无向量能力 → RAG 降级为关键词检索兜底（复用 M2 历史检索）或明确返回「未启用」。
- embedding 走 OpenAI 兼容接口（`base_url` / `model` / `api_key` 均可配），按量计费；密钥缺失 → RAG 降级（同上），不阻断纪要主链路。
- 越权隔离：问答 / 检索只查当前 `user_id` 归属的纪要（沿用 M3 user_id 隔离），用户 A 无法检索用户 B 的会议。
- 成本：embedding 按 token 计费 + 问答 LLM 生成按量计费；单次问答成本纳入 cost_stats 或单独估算，受 M3 日限额约束。
- 兼容性：本地开发保留 SQLite + 本地 FS 模式不破坏；M1/M2/M3 的 144 个既有测试全量可跑。
- 质量判定：RAG 命中率与多模型对比以 Eval 集为准，不达标不发版（tech-stack B5「质量底线」）。

## 6. 上下文（链路与模块）

M4 在 M3「处理流水线 + 生产基础设施」基础上，**改造 LLM Provider 层并新增检索问答层**：

```
（业务链路不变，M1/M2/M3 复用）
ingestion → audio → asr → diarization → summary → extractor → role → render
                    （summary / extractor 的 LLM 由硬编码 Provider 改为走模型注册表）

（M4 改造 / 新增）
llm_registry.py  : 新增（模型注册表：别名 → provider/base_url/model/api_key，配置化热切换）
summary.py       : 改造（LLMProvider 走注册表；新增 Flash 模型别名；去掉类内硬编码）
extractor.py     : 改造（ExtractorProvider 走注册表；新增 Qwen 抽取；去掉硬编码 base_url）
embedding.py     : 新增（EmbeddingProvider 抽象：OpenAI 兼容云 API，如 bge-m3）
rag.py           : 新增（向量检索 + 问答组装 + 来源引用）
db.py            : 改造（minute_embeddings 表 + pgvector；生产 PG 启用扩展）
main.py          : 新增 POST /api/qa、POST /api/tasks/{id}/regen；问答鉴权 + user_id 隔离
pipeline.py      : 改造（纪要完成后自动向量化入库，失败不阻断主链路）
config.py        : 新增 MMA_LLM_MODEL / MMA_LLM_ALIAS / MMA_EMBEDDING_* / MMA_RAG_* 等
```

- 数据模型对齐 tech-stack.md B4：新增 `MinuteEmbedding`（minute_id, task_id, user_id, chunk_index, text, embedding vector, created_at），复用 `minutes` 表；ER 关系 `MINUTE 1—N EMBEDDING_CHUNK`。
- API 新增：`POST /api/tasks/{id}/regen`（换模型/模板重生成，由 tech-stack B4「🕐 后期」转落地）、`POST /api/qa`（提问，返回带来源引用的答案）。
- 多模型切换（用户确认范围）：summary 与 extractor 均走 `llm_registry`，模型别名（如 `v4-pro` / `v4-flash` / `qwen-plus`）由配置决定，改配置/环境变量即可切换，无需改代码；ASR 维持现状。
