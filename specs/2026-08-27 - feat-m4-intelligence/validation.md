# M4 · 智能化（生态打通）— 验收标准 (Validation)

| 文档类型 | 验收标准 |
| --- | --- |
| 阶段 | M4 · 智能化（生态打通） |
| 分支 | feat/m4-intelligence |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文定义 M4 的**可交付物、验收标准与退出条件**，用于判断 M4 是否完成、能否进入后续（G6 生态打通 / G7 实时转写，留后期）。验收口径 = roadmap M4 验收标准（多模型热切换 / RAG 命中率）+ mission KPI 延续 + 用户 2026-08-27 确认的范围与选型（聚焦两项、pgvector、云 embedding、仅 LLM 侧切换）。

## 1. 可交付物

| # | 交付物 | 说明 |
| --- | --- | --- |
| D1 | 模型注册表 | `llm_registry`（别名 → provider/base_url/model/api_key）+ summary/extractor 注册表化，改配置即可热切换 |
| D2 | 多模型切换 | V4 Pro 主 / V4 Flash 降本 / Qwen 备选三通道，含 Qwen Function-Calling 抽取 |
| D3 | 重生成接口 | `POST /api/tasks/{id}/regen`（换模型/模板重生成，越权校验，重生成后重新向量化） |
| D4 | 向量化底座 | pgvector（PG 扩展）+ `minute_embeddings` 表 + `EmbeddingProvider`（OpenAI 兼容云 API）+ 纪要自动向量化 |
| D5 | 检索问答 | `POST /api/qa`（来源引用 + user_id 越权隔离 + 降级兜底）+ 前端问答入口 |
| D6 | 多模型对比报告 | `compare_models.py` 跑三模型，输出质量 / 成本 / 耗时对比 |
| D7 | Eval 集与指标回填 | RAG 问答 Eval 集（黄金答案 + 来源）+ 命中率数据 + 单次问答成本估算 + tech-stack v0.10 回填 |

## 2. 验收标准

| # | 标准 | 判据 | 数据来源 |
| --- | --- | --- | --- |
| V1 | 多模型可配置热切换 | 改 `MMA_LLM_ALIAS` / regen 换模型即可切换，无需改代码；三模型全链路跑通 | TG-0 / TG-1 |
| V2 | 多模型对比 | 三模型质量 / 成本 / 耗时对比报告完整，Flash 成本显著低于 Pro（约 1/3，A6） | TG-1 |
| V3 | 纪要自动向量化 | 纪要完成后 `minute_embeddings` 有对应向量；无 embedding 密钥不阻断纪要主链路 | TG-2 |
| V4 | RAG 命中率 | Eval 集 top-k 命中达标（目标 ≥ 80%，以黄金来源判定；实测值回填 validation §4） | TG-3 / TG-4 |
| V5 | 越权隔离 | 用户 A 的问答/检索无法命中用户 B 的纪要 | TG-3 |
| V6 | 降级兜底 | SQLite 模式 / 无 embedding 密钥时，问答走关键词检索兜底或明确返回「未启用」，不报错崩溃 | TG-3 |
| V7 | 回归与覆盖率 | M1/M2/M3 全量回归通过；单元测试覆盖率 ≥ 70%（新增 registry/embedding/rag 计入） | TG-4 |
| V8 | 成本可控 | embedding 按量计费、问答 LLM 按量计费；单次问答成本估算在 mission KPI 量级内（≤ ¥1/场口径） | TG-3 / TG-4 |

## 3. 退出条件（进入后续 G6/G7 的门槛）

- ✅ 多模型可配置热切换可用（改配置即可切换，无需改代码）。
- ✅ 三模型（V4 Pro / Flash / Qwen）全链路跑通并输出对比报告。
- ✅ 纪要完成后自动向量化入库，pgvector 检索可用。
- ✅ 检索问答命中率达标（Eval 集衡量），答案带来源引用，越权隔离通过。
- ✅ 降级路径明确（无 pgvector / 无 embedding 密钥时行为可预期）。
- ✅ M1/M2/M3 回归通过，单元测试覆盖率 ≥ 70%。
- ✅ 指标回填（命中率、单次问答成本），tech-stack v0.10 更新。

## 4. 数据采集模板（供 TG-0~4 记录）

| 验证项 | 样例 | 目标 | 实测 |
| --- | --- | --- | --- |
| 多模型热切换 | 改配置切 V4 Flash / Qwen | 无需改代码即生效 | |
| 三模型对比 | 同一样例跑 V4 Pro / Flash / Qwen | 质量/成本/耗时三列可比较 | |
| RAG 命中率 | 20~30 条中文问题 Eval 集 | top-k 命中 ≥ 80% | |
| 单次问答成本 | embedding + LLM 生成 token/金额 | ≤ ¥1/场量级 | |
| 越权隔离 | 用户 A 检索用户 B 纪要 | 不命中 / 空结果 | |
| 自动向量化 | 纪要完成后查 minute_embeddings | 有向量、维度正确 | |
| 单元测试覆盖率 | pytest --cov | ≥ 70% | |
| 回归 | M1/M2/M3 功能集 | 全部通过 | |

## 5. 判定规则

- 多模型热切换可用 且 RAG 命中率达标 且 越权隔离/降级通过 且 回归通过 + 覆盖率 ≥ 70% → M4 通过，可进入 G6/G7 后续。
- 任一指标不达标 → 定位到对应任务组补齐（热切换 → TG-0/TG-1、向量化 → TG-2、命中率/越权/降级 → TG-3、对比/回归 → TG-4），回归验证直至达标。
- 若无 embedding 密钥 / 无生产 PostgreSQL（pgvector 未启用）→ RAG 降级为关键词检索兜底，命中率按「关键词检索」口径单独记录，如实标注为降级档，不作为达标档；密钥/生产库就绪后回填向量检索实测命中率。
- 多模型灰度对比以 mock / 现有 Eval 样例为主控费（mission §5 利润 0），真实云调用仅抽样，避免对比实验烧钱。
- 成本口径沿用 M3：单次问答成本 = embedding 费用 + LLM 生成费用，联动 `cost_stats` 与日限额告警。
