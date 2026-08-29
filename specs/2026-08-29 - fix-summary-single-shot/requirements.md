# fix-summary-single-shot · 需求（requirements）

## In Scope

- 删除纪要生成的 Map-Reduce 分块逻辑（`app/summary.py`、根 `summarize.py`）：`_chunk_text`、`MAP_PROMPT`/`REDUCE_PROMPT`、`max_chars` 参数。
- 删除结构化抽取器的硬截断（`app/extractor.py` 的 `text[:max_chars]`）：恒全量抽取。
- 删除 `LLM_MAX_CHARS` 配置与 `MMA_LLM_MAX_CHARS` 环境变量（`app/config.py`、根 `config.py`、`.env.example`）。
- 上传时长上限 `MMA_MAX_DURATION_SECONDS` 7200 → 18000（5 小时）。
- 同步 `docs/mission.md`（§5 约束、§6 KPI、§7 风险、§8-4 决策、版本号）与 `docs/tech-stack.md`（A6 成本、B3 方案、版本号）。
- 更新测试与 skill reference（`meeting-minutes-assistant/references/summary-quality-debugging.md`）。

## Out of Scope

- 不改 ASR 选型与流程（腾讯云 16k_zh 维持现状）。
- 不改模型本身（仍 deepseek-v4-pro）。
- 不部署生产（先本地验证质量，生产变更另行执行）。
- 不引入新的分块 / 层级摘要算法（1M 上下文已够用）。

## 决策映射（用户确认，2026-08-29）

| 决策点 | 结论 |
| --- | --- |
| 纪要分块阈值 | 不需要——彻底删除，恒单次调用全文 |
| extractor 硬截断 bug | 修——恒全量抽取 |
| Map-Reduce 兜底 | 不需要——彻底删除（git 历史可恢复） |
| 上传时长上限 | 一并 2h → 5h（同步改 mission §8-4 + 成本 KPI 说明） |
| 验证顺序 | 先本地验证质量，再上生产 |

## 选型

- 已定：deepseek-v4-pro **1M 上下文**（tech-stack.md A1/A6）→ 单次调用承载 5h 会议（约 6~9 万字 ≈ ≤24 万 token，占 1M 上下文的 12%~24%）。
- 无待锁定项。
