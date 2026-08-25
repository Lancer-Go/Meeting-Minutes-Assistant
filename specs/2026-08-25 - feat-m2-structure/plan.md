# M2 · 结构增强（纪要质量）— 执行计划 (Plan)

| 文档类型 | 执行计划 |
| --- | --- |
| 阶段 | M2 · 结构增强（纪要质量） |
| 分支 | feat/m2-structure |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文把 roadmap.md 中 M2 的 8 步工作顺序组织为可执行的**任务组**。每个任务组含目标、任务项、产出与验收；任务组之间按依赖推进（前一组的验收是后一组的输入）。M2 在 M1「可用完整闭环」基础上做**纪要质量增强**：结构化行动项（FR-05 细化）、说话人角色标注（FR-03 细化）、多模板（FR-08）、可编辑与历史检索（FR-09/FR-10/FR-11）。复用 M0/M1 已锁定选型（ASR 腾讯云 16k_zh / LLM DeepSeek-V4 Pro（deepseek-v4-pro，由 V3 升级）），新增 Function-Calling 结构化输出、说话人分离、角色识别、Jinja2 模板、编辑批注、历史检索与 Eval 集。

## 任务组总览

| 任务组 | 内容 | 产出 | 依赖 |
| --- | --- | --- | --- |
| TG-0 | 结构化 Schema 与数据模型 | `ActionItem / Decision / OpenQuestion` JSON Schema + `minute` 持久化数据模型 | — |
| TG-1 | extractor 模块（行动项抽取） | `extractor` 模块 + Function-Calling 抽取 + 单点评测 | TG-0 |
| TG-2 | 说话人分离 | `Segment.speaker` 标注 + diarization Provider（云 ASR 内置 / pyannote / whisperX 兜底） | TG-0 |
| TG-3 | 角色识别 | 主持人 / 汇报人 / 参会者标注（规则 + LLM 辅助） | TG-2 |
| TG-4 | Jinja2 模板化渲染 | 标准 / 精简 / 详细三套模板 | TG-1, TG-3 |
| TG-5 | 编辑与批注 | 纪要编辑 / 批注接口 + 前端 + 持久化 | TG-4 |
| TG-6 | 历史检索 | 按时间 / 主题 / 关键词检索 | TG-5 |
| TG-7 | Eval 集与质量评测 | 黄金基准集 + 行动项三要素 / 说话人 / 返工率指标回填 | TG-1, TG-3, TG-4 |

## 任务组明细

### TG-0 · 结构化 Schema 与数据模型
- **目标**：定义结构化纪要的稳定契约，作为 extractor / render / 持久化的共同基础。
- **任务项**：
  - 定义 `ActionItem`（决议描述 / 负责人 / 截止时间 / 优先级 / 状态）、`Decision`（结论 / 依据）、`OpenQuestion`（问题 / 待跟进）三个 dataclass + JSON Schema（对应 tech-stack.md B4 `Minute` 实体的 decisions[] / actions[] / open_questions[]）。
  - 定义 `StructuredMinute`（title / summary_md / decisions[] / actions[] / open_questions[] / speakers[]），与现有 `Transcript` 解耦但可互相引用。
  - 扩展 `Segment` / `Transcript`：`Segment` 增 `speaker: str`（默认空，TG-2 回填）；`Transcript` 增 `speakers: list[str]`。
  - 持久化：SQLite 新增 `minutes` 表（task_id, title, template, summary_md, structured_json, edited_md, updated_at），对应纪要可编辑、可检索（TG-5/TG-6）。
- **产出**：Schema 定义文件（如 `app/schemas.py`）+ `minutes` 表 + `Segment.speaker` 字段。
- **验收**：Schema 可被 pydantic/dataclass 校验；`minutes` 表可幂等建表；`Segment` 序列化含 speaker 字段。

### TG-1 · extractor 模块（行动项抽取）
- **目标**：从转写/纪要中抽取结构化决议、行动项、未决问题（FR-05 细化、G3 核心）。
- **任务项**：
  - 实现 `app/extractor.py`：抽象 `ExtractorProvider`，主用 `DeepSeekLLM` 走 Function-Calling / JSON Schema 约束输出（对应 tech-stack.md A2「结构化输出」）。
  - 定义抽取提示词与 `tool_schema`（`extract_actions` / `extract_decisions` / `extract_questions`），返回 `StructuredMinute` 的 decisions/actions/open_questions。
  - 保留 `extractive` 本地降级：无密钥时用规则（正则匹配「负责人 / 截止 / 待办」关键词）抽取，保证链路可跑通。
  - 单点评测：抽取结果解析为 Python 对象，非法 JSON / 缺字段时兜底重试或标「待定」。
- **产出**：`extractor` 模块 + Function-Calling 抽取 + 规则兜底。
- **验收**：给定样例转写文本，能产出含「负责人 / 截止时间」字段的行动项列表；云端无密钥时规则兜底可用。

### TG-2 · 说话人分离
- **目标**：转写文本带 speaker 标注（FR-03 细化），为角色识别与「谁说了什么」式纪要打底。
- **任务项**：
  - 优先接入云 ASR 内置话者分离能力（腾讯云录音文件识别若支持话者分离参数则启用；实测确认 16k_zh 是否返回 speaker 标签）。
  - 兜底：pyannote-audio / whisperX（本地 diarization），对 WAV 输出 `(start, end, speaker)` 段，与 `Segment` 对齐回填 `speaker`。
  - 定义 `DiarizationProvider` 抽象，与 `ASRProvider` 解耦；speaker 缺失时标记 `S1 / S2 / ...` 占位。
  - 中间产物 `transcript.json` 增 speaker 字段。
- **产出**：说话人分离能力 + speaker 标注的转写文本。
- **验收**：样例音频转写段带 speaker 标签；主观正确率基准可测（进入 TG-7 评测）。

### TG-3 · 角色识别
- **目标**：标注主持人 / 汇报人 / 参会者（FR-11），提升纪要的「谁负责什么」清晰度。
- **任务项**：
  - 规则层：按说话频次 / 开场与收尾 / 「下面请 XX 汇报」等句式启发式判定主持人、汇报人。
  - LLM 辅助：对 speaker 摘要做角色分类（主持人 / 汇报人 / 参会者），输出 speaker → role 映射。
  - 角色结果回填 `StructuredMinute.speakers[]`，供模板渲染。
- **产出**：角色识别模块（规则 + LLM 辅助）+ speaker → role 映射。
- **验收**：样例会议能给出合理的角色标注，可人工修正（修正结果进入 Eval 基准）。

### TG-4 · Jinja2 模板化渲染
- **目标**：三套纪要模板（FR-08），从单一 Markdown 升级为模板化渲染。
- **任务项**：
  - 引入 Jinja2，改造 `render` 模块：`render_minutes(structured_minute, template_name)`。
  - 实现三套模板：**标准**（决议 + 讨论要点 + 行动项表 + 未决问题）、**精简**（决议 + 行动项一览）、**详细**（含全文转写附录 + 说话人 + 角色）。
  - 保留 Markdown 原生输出；`minutes.md` 默认渲染「标准」模板，其余模板按参数切换。
  - 模板含结构化行动项表（负责人 / 截止 / 优先级 / 状态）。
- **产出**：Jinja2 渲染 + 三套模板文件。
- **验收**：同一 `StructuredMinute` 可渲染出三套不同的 Markdown；行动项表字段完整。

### TG-5 · 编辑与批注
- **目标**：纪要可人工编辑、批注并持久化（FR-09）。
- **任务项**：
  - 接口：`GET /api/tasks/{id}/minute`（已生成）、`PUT /api/tasks/{id}/minute`（保存编辑后的 Markdown）、`POST /api/tasks/{id}/comments`（批注）、`GET /api/tasks/{id}/comments`（批注列表）。
  - 持久化：编辑结果写入 `minutes.edited_md`；批注写入 `comments` 表（task_id, author, text, quote, created_at）。
  - 前端：纪要编辑页（可改 Markdown + 批注），基于 M1 极简前端扩展。
- **产出**：编辑 / 批注接口 + 前端 + 持久化。
- **验收**：编辑后重新 GET 返回编辑内容；批注增删查可持久化，重启服务不丢失。

### TG-6 · 历史检索
- **目标**：历史纪要按时间 / 主题 / 关键词检索（FR-10）。
- **任务项**：
  - 接口 `GET /api/minutes`（列表 / 搜索，query 参数：`q` 关键词、`from/to` 时间、`topic` 主题）。
  - 关键词检索：SQLite `LIKE`（MVP 足够）匹配 title / summary_md / actions；向量检索留 M4。
  - 前端：历史列表页 + 搜索框。
- **产出**：历史检索接口 + 前端。
- **验收**：按关键词 / 时间范围可检索到对应纪要；空结果返回空列表。

### TG-7 · Eval 集与质量评测
- **目标**：建立黄金基准集，回填 M2 验收指标（行动项三要素完整率、说话人正确率、返工率）。
- **任务项**：
  - 建 Eval 集：选 N（≥3）场真实会议样例，人工标注黄金纪要（决议 / 行动项 / 负责人 / 截止 / 说话人）。
  - 评测脚本：跑 extractor / diarization / role / render，与黄金基准对比，输出行动项三要素完整率、说话人正确率、纪要返工率。
  - 回填数据到 `validation.md` 与 CHANGELOG，作为 M2 退出条件依据。
- **产出**：Eval 集 + 评测脚本 + 指标报告。
- **验收**：指标达到 mission.md KPI（行动项三要素 ≥ 85%、返工率 ≤ 20%、说话人正确率 ≥ 80%）。

## 依赖关系

```
TG-0 ──► TG-1 ──► TG-4 ──► TG-5 ──► TG-6
  │                          │
  ├──► TG-2 ──► TG-3 ─────►┘
  └──────────────────────────► TG-7（贯穿收口，最后跑评测）
```

> TG-7（Eval 集与评测）依赖 TG-1 / TG-3 / TG-4 的产出，最后统一收口验证。任务组按上述依赖串行推进；TG-2 与 TG-1 在 TG-0 之后可并行。
