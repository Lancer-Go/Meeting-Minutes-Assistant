# M0 · 概念验证 (PoC) — 执行计划 (Plan)

| 文档类型 | 执行计划 |
| --- | --- |
| 阶段 | M0 · 概念验证 (PoC) |
| 分支 | feat/m0-poc |
| 关联文档 | [roadmap.md](../docs/roadmap.md) · [mission.md](../docs/mission.md) · [tech-stack.md](../docs/tech-stack.md) |

> 本文把 roadmap.md 中 M0 的 7 步工作顺序组织为可执行的**任务组**。每个任务组含目标、任务项、产出与验收；任务组之间有强依赖，必须串行推进（前一组的验收是后一组的输入）。

## 任务组总览

| 任务组 | 内容 | 产出 | 依赖 |
| --- | --- | --- | --- |
| TG-0 | 环境与脚手架 | `venv` + `requirements.txt` | — |
| TG-1 | 样例数据 | 一段 ≥ 10min 真实会议音频 | TG-0 |
| TG-2 | `audio.py` 音频提取 | 标准化 WAV（16kHz / 单声道） | TG-1 |
| TG-3 | `asr.py` 语音转写 | 带时间戳转写文本（对比 1–2 家云 ASR） | TG-2 |
| TG-4 | `summarize.py` 纪要生成 | 结构化 Markdown 纪要 | TG-3 |
| TG-5 | `pipeline.py` 端到端 | 一键串联 + 耗时/成本/字符数 | TG-2~4 |
| TG-6 | 评估与选型决策 | 《选型决策记录》 | TG-5 |

## 任务组明细

### TG-0 · 环境与脚手架
- **目标**：可复现的 Python 3.11 隔离环境。
- **任务项**：
  - 创建 `venv`（Python 3.11）。
  - 安装 `ffmpeg` 并验证 `ffmpeg -version`。
  - 安装云 ASR SDK（阿里云 / 讯飞 / 腾讯云，按需）与 `openai`。
  - 生成 `requirements.txt`（锁定版本）。
- **产出**：`requirements.txt` + 可用 `venv`。
- **验收**：`python --version` = 3.11.x；`ffmpeg -version` 正常；`pip install -r requirements.txt` 无报错。

### TG-1 · 样例数据
- **目标**：一段能代表真实场景的会议音频。
- **任务项**：
  - 录制或获取一段 **≥ 10 分钟**真实会议音频（中文为主，英文术语混用）。
  - 放入 `samples/`，命名规范（如 `samples/meeting-001.mp4`）。
- **产出**：样例音频文件（≥ 10min）。
- **验收**：`ffprobe` 时长 ≥ 10 分钟；内容含中文讨论 + 英文术语。

### TG-2 · `audio.py` 音频提取
- **目标**：把任意音视频统一为标准 WAV。
- **任务项**：
  - 实现 FFmpeg 抽音轨：`ffmpeg -i input -vn -ac 1 -ar 16000 -f wav output.wav`。
  - 支持 MP4 / MKV / WAV / MP3 / M4A。
- **产出**：`audio.py`。
- **验收**：输出 WAV 为 16kHz 单声道、可播放、`ffprobe` 规格正确。

### TG-3 · `asr.py` 语音转写
- **目标**：带时间戳的转写文本，并对比 1–2 家云 ASR。
- **任务项**：
  - 抽象 `ASRProvider` 接口。
  - 接入云 ASR（阿里云 / 讯飞 / 腾讯云：先 1 家跑通，再对比 1 家）。
  - 输出带时间戳分段文本（`segments[]`，含 start/end/text）。
- **产出**：`asr.py` + 转写结果样例。
- **验收**：转写文本完整、含时间戳；记录各厂商 CER / 耗时 / 成本。

### TG-4 · `summarize.py` 纪要生成
- **目标**：转写文本 → 结构化 Markdown 纪要。
- **任务项**：
  - 设计提示词（会议主题 / 核心决议 / 讨论要点 / 行动项 / 待跟进）。
  - 调用 LLM（DeepSeek / Qwen，openai 兼容接口）。
  - 输出 Markdown 纪要（含时间戳全文附录）。
- **产出**：`summarize.py` + 样例纪要。
- **验收**：纪要结构完整、可读；长文本超上下文时走 Map-Reduce 分块。

### TG-5 · `pipeline.py` 端到端
- **目标**：一键「音频 → 转写 → 纪要」，并记录关键指标。
- **任务项**：
  - 串联 audio → asr → summarize。
  - 记录**耗时 / 成本 / 转写字符数**三组实测数据。
- **产出**：`pipeline.py` + 一份完整 Markdown 纪要。
- **验收**：单命令跑通；指标落在 mission.md §6 KPI 量级内（耗时 ≤ 时长 1/3、成本 ≤ ¥1/场）。

### TG-6 · 评估与选型决策
- **目标**：用实测数据锁定选型，供 M1 使用。
- **任务项**：
  - 人工评分纪要质量。
  - 汇总 CER / 耗时 / 成本 三组数据。
  - 输出《选型决策记录》（ASR 厂商 + LLM 型号）。
- **产出**：《选型决策记录》。
- **验收**：结论明确；满足 M0 退出条件。

## 依赖关系

```
TG-0 ──► TG-1 ──► TG-2 ──► TG-3 ──► TG-4 ──► TG-5 ──► TG-6
```

> 任务组必须串行推进；前一组的验收是后一组的输入。
