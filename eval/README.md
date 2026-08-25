# M2 质量评测（TG-7）

本目录承载 M2 的**黄金基准集（Eval 集）与质量评测脚本**，用于回填 validation.md 的退出指标。

## 指标（对应 mission.md KPI）

| 指标 | 阈值 | 说明 |
| --- | --- | --- |
| 行动项三要素完整率 | ≥ 85% | 描述 / 负责人 / 截止时间 三要素均非空且非「待定」的行动项占比 |
| 说话人正确率 | ≥ 80% | 按时间重叠对齐，比较 speaker 标签一致的比例（时长加权） |
| 纪要返工率 | ≤ 20% | 人工编辑稿相对生成稿的改动比例（1 − SequenceMatcher 相似度） |

## 目录结构

```
eval/
  metrics.py          # 纯指标函数（可单测）
  eval_quality.py     # 评测脚本（对比 golden vs pipeline 产物）
  golden/             # 黄金基准集（人工标注，JSON）
```

## 黄金基准文件结构（`golden/*.json`）

```json
{
  "task_id": "<对应 data/tasks/<task_id>>",
  "title": "会议标题",
  "actions": [{"description": "...", "owner": "...", "due": "...", "priority": "高", "status": "待办"}],
  "speaker_segments": [{"start": 0.0, "end": 5.0, "speaker": "S1"}],
  "minutes_md": "人工标注的黄金纪要全文（Markdown）"
}
```

## 评测流程

1. 准备 ≥3 场真实会议样例，人工标注黄金纪要（决议 / 行动项 / 负责人 / 截止 / 说话人）。
2. 跑 pipeline 生成 `structured_minute.json` / `transcript.json` / `minutes.md`。
3. 执行评测：

```bash
./venv/Scripts/python.exe -m eval.eval_quality --golden-dir eval/golden --task-dir data/tasks
# 输出 JSON：
./venv/Scripts/python.exe -m eval.eval_quality --golden-dir eval/golden --task-dir data/tasks --json
```

## 状态与缺口

- 当前 `golden/` 内为**种子样例**（标注为「待人工复核」），用于验证评测脚本可跑通，
  不作为最终指标依据。真实黄金基准需人工标注后替换。
- 说话人正确率依赖 `transcript.json` 内逐段 speaker 标签：云端腾讯云话者分离（`SpeakerDiarization`）
  或本地 pyannote / placeholder 兜底均会回填。
- 返工率依赖 `minutes.edited.md`（人工编辑稿）；未编辑时按 0 计。
- 云端密钥缺失时抽取走 rule 兜底、话者分离走 placeholder 兜底——此场景指标会偏低，
  应按 validation.md §5 判定规则如实记录「话者分离方案由云 ASR 降级为本地兜底」。
