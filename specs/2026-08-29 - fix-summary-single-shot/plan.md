# fix-summary-single-shot · 执行计划（plan）

> 纪要质量修正：去掉 Map-Reduce 分块与 extractor 硬截断，改为**全文单次调用**；上传时长上限 2h → 5h。
> 起因：用户反馈「deepseek-v4-pro 纪要质量低」。诊断结论（见 validation.md 背景）为 **pipeline 瓶颈而非模型本身**：
> 1h 会议转写 ~19K 字符 > 旧阈值 12000 → 触发 Map-Reduce（跨块信息丢失）+ extractor 硬截断丢尾部（决议/行动项偏少）。

## 目标

- 纪要生成（summary）与结构化抽取（extractor）**恒为单次调用全文**（deepseek-v4-pro 1M 上下文，5h 会议 ≈ ≤24 万 token，占 1M 的 12%~24%，无需分块）。
- 上传时长上限由 2 小时提高到 5 小时（腾讯云 ASR 支持 5h，mission §8-4 决策同步更新）。

## 任务组与依赖

- **TG-0** 纪要单次调用化：`app/summary.py` 删 `_chunk_text` / `MAP_PROMPT` / `REDUCE_PROMPT` / `max_chars`。
- **TG-1** 抽取器去截断：`app/extractor.py` 删 `max_chars` 与 `text[:max_chars]` 硬截断。
- **TG-2** 配置与 M0 CLI 同步：`app/config.py` + 根 `config.py` 删 `LLM_MAX_CHARS`；根 `summarize.py` 同步删分块。
- **TG-3** 时长上限 2h→5h：`app/config.py`（`MAX_DURATION_SECONDS`）、`app/ingestion.py`（提示文案）、`.env.example`、`docs/mission.md`。
- **TG-4** 测试更新：`tests/test_summary.py` 删 chunk 测试，补「长文本单次调用」测试。
- **TG-5** 文档同步：`docs/mission.md`（§5/§6/§7/§8 + 版本号）、`docs/tech-stack.md`（A6 成本 / B3 方案 + 版本号）。
- **TG-6** 本地验证：全量 pytest + 生产 19218 字会议 A/B 对比。

依赖：TG-0/TG-1 独立可并行；TG-2 依赖 TG-0/TG-1（删 `max_chars` 后同步删配置）；TG-3 独立；TG-4/TG-5 依赖前三组；TG-6 收尾。
