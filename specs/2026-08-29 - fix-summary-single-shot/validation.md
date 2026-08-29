# fix-summary-single-shot · 验证（validation）

## 背景（诊断结论）

- 头号质量瓶颈：Map-Reduce 分块（1h 会议 ~19K 字 > 旧阈值 12000），Map 丢跨块信息、Reduce 只合并摘要（合并的是摘要的摘要）。
- 更隐蔽 bug：extractor `text[:max_chars]` 静默截断，1h 会议只看到前 62%，决议/行动项偏少。
- 结论：质量低是 pipeline 问题，不是 deepseek-v4-pro 模型问题。

## 交付物

1. `app/summary.py`：`summarize()` 恒单次调用；无 `_chunk_text` / `MAP_PROMPT` / `REDUCE_PROMPT` / `max_chars`。
2. `app/extractor.py`：`extract()` 恒全量；无 `max_chars` / 截断。
3. 配置：无 `LLM_MAX_CHARS` / `MMA_LLM_MAX_CHARS`；`MAX_DURATION_SECONDS=18000`。
4. docs：`mission.md` v0.4 + `tech-stack.md` v0.12 同步。
5. tests：`test_summary.py` 无 chunk 测试，新增「长文本单次调用」测试。

## 验收标准

- 全量 pytest 通过（原 187 例去除 2 例 chunk 测试后 + 新增用例全绿）。
- 同一场会议（生产 `e2935…`，19218 字）重跑：决议/行动项数量 ≥ 旧 Map-Reduce 结果，纪要正文含旧版遗漏的跨块信息。
- grep 确认仓库内（排除 venv）无 `_chunk_text`（summary 侧）、`max_chars`、`LLM_MAX_CHARS`、`MMA_LLM_MAX_CHARS` 残留；`embedding.chunk_text` 属 RAG 切块，保留。

## 验证步骤

1. `python -m pytest -q`（本地）。
2. 拉生产 `e2935…` 的 `transcript.json` + `minutes.md` 到本地，用新代码重跑 summary+extractor，对比 A/B。
3. 检查 A/B 结果：`n_decisions`/`n_actions` 是否提升、正文是否含旧版遗漏的跨块结论。
4. 通过后提交（两次提交模式），生产变更另行与用户确认执行。
