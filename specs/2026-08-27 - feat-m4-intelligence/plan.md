# M4 · 智能化（生态打通）— 执行计划 (Plan)

| 文档类型 | 执行计划 |
| --- | --- |
| 阶段 | M4 · 智能化（生态打通） |
| 分支 | feat/m4-intelligence |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文把 roadmap.md 中 M4 的工作顺序组织为可执行的**任务组**。每个任务组含目标、任务项、产出与验收；任务组之间按依赖推进（前一组的验收是后一组的输入）。M4 在 M3「云端 SaaS + 生产基础设施」基础上做**智能化**：① LLM 侧多模型可配置热切换（V4 Pro 主 / V4 Flash 降本 / Qwen 备选），② 会议历史向量化 + 检索问答（RAG）。复用 M0~M3 已锁定选型（ASR 腾讯云 16k_zh / LLM DeepSeek-V4 Pro / FastAPI / Docker Compose / PostgreSQL + MinIO / 腾讯云 COS）。本阶段范围与选型已由用户 2026-08-27 确认：**聚焦「多模型切换 + 检索问答」两项（G6/G7 留后期）**、**pgvector（复用 PG）**、**云 Embedding API（OpenAI 兼容如 bge-m3）**、**仅 LLM 侧切换（ASR 维持现状）**。

## 任务组总览

| 任务组 | 内容 | 产出 | 依赖 |
| --- | --- | --- | --- |
| TG-0 | Provider 抽象与模型注册表 | `llm_registry`（别名 → provider/base_url/model/key，配置化热切换）+ summary/extractor 走注册表 | — |
| TG-1 | 多模型切换落地 + 降本通道 | V4 Flash 通道 + Qwen 抽取 + `POST /api/tasks/{id}/regen` + 灰度对比脚本 | TG-0 |
| TG-2 | 历史纪要向量化 + pgvector | `minute_embeddings` 表 + `EmbeddingProvider` + 纪要完成后自动向量化 | — |
| TG-3 | 检索问答 (RAG) | `POST /api/qa`（来源引用 + 越权隔离 + 降级）+ 前端问答入口 | TG-0, TG-2 |
| TG-4 | 评测与验收 | RAG Eval 集 + 多模型对比报告 + 指标回填 + 回归收口 | TG-1, TG-3 |

## 任务组明细

### TG-0 · Provider 抽象与模型注册表
- **目标**：把现有 `LLMProvider` / `ExtractorProvider` 统一到「模型注册表」，实现配置化热切换（对应 roadmap 工作顺序 1「Provider 抽象重构」）。
- **任务项**：
  - 新增 `app/llm_registry.py`：模型别名 → `(provider, base_url, model, api_key)` 映射，从环境变量 / `.env` 读取（如 `v4-pro` → DeepSeek `deepseek-v4-pro`、`v4-flash` → DeepSeek `deepseek-v4-flash`、`qwen-plus` → DashScope 兼容接口）。
  - 改造 `app/summary.py`：`OpenAILikeLLM` 改为从注册表取 `base_url` / `model` / `api_key`（去掉 `DeepSeekLLM` / `QwenLLM` 类内硬编码）；保留 `extractive` 本地兜底。
  - 改造 `app/extractor.py`：`DeepSeekExtractor` 去掉硬编码 `base_url="https://api.deepseek.com"`，改为注册表驱动；抽成可复用的 OpenAI 兼容抽取基类（为 TG-1 的 Qwen 抽取铺路）。
  - 配置扩展 `app/config.py`：新增 `MMA_LLM_ALIAS`（默认 `v4-pro`）、`MMA_LLM_MODEL`（可覆盖具体模型名）、`MMA_QWEN_MODEL`、embedding 相关占位。
- **产出**：`llm_registry` 模块 + summary/extractor 注册表化 + 配置扩展。
- **验收**：改 `MMA_LLM_ALIAS=v4-flash` 或 `qwen-plus` 后无需改代码即可切换模型跑通纪要/抽取；M1/M2/M3 既有测试（144 个）全绿。

### TG-1 · 多模型切换落地 + 降本通道
- **目标**：接入 V4 Flash 降本通道与 Qwen 抽取，落地 per-task 换模型重生成，输出多模型灰度对比（对应 roadmap 工作顺序 1、5）。
- **任务项**：
  - 接入 **deepseek-v4-flash**：注册表加 `v4-flash` 别名；成本模型 `app/cost.py` 已含 flash 价格，联动即可。
  - 新增 **Qwen 抽取**：`app/extractor.py` 用注册表驱动 Function-Calling 抽取（Qwen 兼容 `tools`/`tool_choice`），`has_cloud_credentials` 补 qwen 分支。
  - 落地 `POST /api/tasks/{id}/regen`：换模型/模板重生成纪要（tech-stack B4 原「🕐 后期」转落地），按 user_id 越权校验，重生成后重新向量化（联动 TG-2）。
  - 灰度对比脚本 `scripts/compare_models.py`：同一样例跑 V4 Pro / Flash / Qwen，记录质量（人工评分 + Eval 指标）、成本（token/金额）、耗时，输出对比报告。
- **产出**：Flash 通道 + Qwen 抽取 + regen 接口 + `compare_models.py` + 对比报告。
- **验收**：三模型全链路跑通；regen 换模型后纪要/向量一致刷新；对比报告输出三模型质量/成本/耗时。

### TG-2 · 历史纪要向量化 + pgvector
- **目标**：纪要向量化入库，为 RAG 提供检索底座（对应 roadmap 工作顺序 2「历史纪要向量化」）。
- **任务项**：
  - PostgreSQL 启用 **pgvector**（`CREATE EXTENSION vector`，Compose 的 postgres 镜像换 `pgvector/pgvector` 或初始化脚本启用）。
  - `app/db.py` 新增 `minute_embeddings` 表（minute_id, task_id, user_id, chunk_index, text, embedding `vector(1024)`, created_at）；本地 SQLite 模式建兼容占位表（无向量能力，供降级判断）。
  - 新增 `app/embedding.py`：`EmbeddingProvider` 抽象 + OpenAI 兼容实现（`base_url` / `model` / `api_key` 可配，如 bge-m3）；`embed(texts) -> list[vector]`。
  - 改造 `app/pipeline.py`：纪要完成后按 chunk（如 800 字符 + 200 重叠）切分 → embedding → 写 `minute_embeddings`；失败仅告警不阻断纪要主链路。
- **产出**：pgvector schema + `EmbeddingProvider` + 自动向量化 pipeline。
- **验收**：纪要完成后 `minute_embeddings` 有对应向量；embedding 维度/值正确；无 embedding 密钥时不阻断纪要生成。

### TG-3 · 检索问答 (RAG)
- **目标**：实现「上次会议谁负责 X」式历史问答，带来源引用（对应 roadmap 工作顺序 2、G5）。
- **任务项**：
  - 新增 `app/rag.py`：query → embedding → pgvector 余弦 top-k 检索（按 `user_id` 过滤）→ 拼上下文 → LLM（复用主模型）生成带引用答案；返回来源（task_id / 纪要标题 / 命中片段）。
  - 新增 `POST /api/qa`：入参 `question` / `top_k` / 可选 `model`；鉴权依赖 + `user_id` 越权隔离；答案 Markdown 含 `来源` 列表。
  - 降级：无 pgvector（SQLite 模式）或无 embedding 密钥 → 关键词检索兜底（复用 M2 历史检索）或返回明确的「未启用」提示。
  - 前端 `static/`：历史检索页加问答输入框，展示答案 + 来源链接。
- **产出**：`rag.py` + `/api/qa` + 前端问答入口 + 来源引用。
- **验收**：「上次会议谁负责 X」类提问命中正确纪要并附来源；用户 A 检索不到用户 B 的纪要；降级路径行为明确。

### TG-4 · 评测与验收
- **目标**：以 Eval 集与回归数据证明两项能力达标，回填指标（对应 roadmap 工作顺序 5「多模型灰度验证，输出对比报告」）。
- **任务项**：
  - 建 RAG 检索问答 Eval 集（标注黄金答案与来源，如 20~30 条中文问题），跑命中率（top-k 命中 / 答案正确率）。
  - 建多模型对比 Eval（复用 M2 Eval 集样例）：纪要质量、行动项三要素完整率、成本、耗时，输出对比报告。
  - 回归：M1/M2/M3 全量测试 + 覆盖率 ≥ 70%（新增 registry/embedding/rag 计入）。
  - 回填：命中率数据、单次问答成本估算 → validation.md §4 与 tech-stack.md（v0.10）。
- **产出**：M4 Eval 集 + 多模型对比报告 + 指标回填 + 回归报告。
- **验收**：RAG 命中率达标；三模型对比报告完整；回归通过、覆盖率 ≥ 70%；tech-stack v0.10 回填。

## 依赖关系

```
TG-0 ──► TG-1 ──┐
                 ├──► TG-4
TG-2 ──► TG-3 ──┘
```

> TG-0（模型注册表）是 TG-1 多模型落地的前置；TG-2（向量化）是 TG-3 问答的前置；TG-3 复用 TG-0 注册表生成答案。TG-0 与 TG-2 相互独立，可并行；TG-1（依赖 TG-0）与 TG-3（依赖 TG-2）可并行；TG-4 收口依赖 TG-1 + TG-3。
