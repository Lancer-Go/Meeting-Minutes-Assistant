# Meeting Minutes Assistant / 会议纪要助手

将会议录音/录像自动转写为文字，并生成结构化 Markdown 会议纪要。

> 当前进度：**M0 · 概念验证 (PoC)** —— 打通「音频 → 转写 → 纪要」最小闭环，用实测数据锁定云 ASR 厂商与 LLM 选型。详见 `specs/` 与 `docs/roadmap.md`。

## 快速开始

```bash
# 1. 环境（Python 3.11）
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt

# 2.（可选）生成一段合成中文会议样例（需联网；真实音频请直接放入 samples/）
./venv/Scripts/python.exe make_sample.py samples/meeting-001.mp3

# 3. 一键跑通端到端（离线：本地 whisper + 抽取式纪要，无需任何密钥）
./venv/Scripts/python.exe pipeline.py samples/meeting-001.mp3
```

## 任务组（M0）

| 任务组 | 脚本 | 说明 |
| --- | --- | --- |
| TG-0 环境 | `requirements.txt` + `venv` | Python 3.11 + FFmpeg（缺系统 FFmpeg 时用 `static-ffmpeg` 兜底） |
| TG-1 样例 | `make_sample.py` → `samples/` | 合成占位样例；真实音频由用户替换 |
| TG-2 音频 | `audio.py` | FFmpeg 抽音轨，标准化 16kHz 单声道 WAV |
| TG-3 转写 | `asr.py` | `ASRProvider` 抽象 + 本地 whisper / 阿里云 / 腾讯云 / 讯飞 |
| TG-4 纪要 | `summarize.py` | `LLMProvider` 抽象 + DeepSeek / Qwen / 本地抽取式基线 |
| TG-5 串联 | `pipeline.py` | 一键串联，记录耗时/成本/转写字符数 |
| TG-6 评测 | `eval_cer.py` + 《选型决策记录》 | CER 计算与选型结论 |

## 使用云端 ASR / LLM

复制 `.env.example` 为 `.env`，填入对应密钥，然后：

```bash
./venv/Scripts/python.exe pipeline.py samples/meeting-001.mp3 --asr aliyun --llm deepseek
```

不填密钥时，`--asr whisper --llm extractive` 可离线跑通全链路（仅用于链路验证，质量非生产级）。

## 目录结构

```
audio.py / asr.py / summarize.py / pipeline.py / eval_cer.py   # 核心脚本
config.py        # 集中配置（读 .env）
make_sample.py   # 合成样例音频
samples/         # 会议音频（gitignore，需自备真实数据）
out/             # 运行产物（transcript.json / minutes.md / metrics.json）
specs/           # 阶段执行文档（plan / requirements / validation）
docs/            # mission / roadmap / tech-stack 源文档
```
