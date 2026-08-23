# 技术栈与选型 (Tech Stack)

| 文档类型 | 技术栈与选型 |
| --- | --- |
| 版本 / 状态 | v0.1（草案）🏗️ |
| 关联文档 | [architecture](architecture.md) · [technical-solution](technical-solution.md) · [roadmap](roadmap.md) |

> 说明：本文汇总项目各模块的候选技术栈。标记 🔶【建议】为倾向方案，✅【已定】为已决项，其余为候选。最终以 M0 实测数据锁定。

## 1. 编程语言与运行时

| 层 | 选型 🔶建议 | 说明 |
| --- | --- | --- |
| 后端 / 服务 | **Python 3.11+** | AI 生态最全（ASR/LLM/NLP 库丰富） |
| Web / CLI | Python（FastAPI）或 TypeScript | 后端为 Python 时优先 FastAPI |
| 脚本 / 工具 | Bash / Python | FFmpeg 封装、批处理 |

## 2. 核心处理链路选型

### 2.1 音频处理（视频抽音轨 / 预处理）

| 方案 | 说明 | 建议 |
| --- | --- | --- |
| **FFmpeg** ✅ | 视频抽音轨、采样率/声道归一化、静音检测 | 已定（业界标准） |
| pydub / librosa | Python 侧音频处理封装 | 🔶 需要轻量处理时使用 |

### 2.2 语音转文字 (ASR)

| 方案 | 类型 | 优点 | 缺点 | 适用 |
| --- | --- | --- | --- | --- |
| **Whisper / faster-whisper** | 开源 | 中英强、可离线、免费 | 需 GPU / 相对慢 | 🔶本地/私有化首选 |
| **FunASR（阿里开源）** | 开源 | 中文口语极佳、带说话人分离 | 生态较小 | 中文会议候选 |
| 阿里云 / 讯飞 / 腾讯云 ASR | 云API | 准确率高、省心、标点好 | 按量收费、数据出域 | 云端 SaaS |
| Azure / Google / OpenAI whisper-api | 云API | 多语言、省心 | 外资云、成本 | 对标外企 |

### 2.3 说话人分离 (Diarization)

| 方案 | 说明 | 建议 |
| --- | --- | --- |
| **pyannote-audio** | 业界主流说话人分离 | 🔶 首选 |
| **whisperX（di-art）** | 对齐 whisper 的时间戳 + 说话人 | 🔶 备选 |

### 2.4 文本预处理与角色标注

| 方案 | 说明 |
| --- | --- |
| 规则 + 正则 | 分句、去重、合并碎句 |
| LLM 辅助 | 角色识别（主持人/汇报人/参会者）、关键词提取 |
| spaCy / jieba | 中文分词、实体识别（可选） |

### 2.5 LLM 纪要生成

| 方案 | 特点 | 建议 |
| --- | --- | --- |
| **DeepSeek-V3 / R1** | 中文强、性价比高 | 🔶 首选 |
| Qwen（通义千问） | 中文好、可本地化 | 私有化候选 |
| GLM / Kimi | 国产、长文本友好 | 候选 |
| GPT-4o / Claude | 通用能力强、成本较高 | 候选 |

### 2.6 结构化输出与抽取

| 方案 | 说明 |
| --- | --- |
| **Function-Calling / JSON Schema** ✅ | 约束 LLM 输出为稳定结构 |
| response_format（JSON mode） | 备选，兼容性依供应商而定 |

### 2.7 渲染与导出

| 方案 | 说明 |
| --- | --- |
| Markdown（原生） | 纪要主格式 |
| **Pandoc** | MD → PDF / docx |
| Jinja2 模板 | 模板化渲染 |

## 3. 基础设施选型

| 模块 | 方案 🔶建议 | 说明 |
| --- | --- | --- |
| Web 框架 | **FastAPI** | 异步、类型友好、生态好 |
| 任务队列 | **Celery + Redis** 或 RQ | 异步长任务调度、重试 |
| 存储 | S3 兼容对象存储 + PostgreSQL | 原始文件 + 纪要/任务元数据 |
| 容器化 | **Docker / Docker Compose** | 本地一键起 |
| 编排（云端） | Kubernetes | Worker 可扩缩 |
| 可观测 | 结构化日志 + Prometheus + Grafana | 指标与告警 |
| CI/CD | GitHub Actions | lint → test → build → 镜像发布 |

## 4. 选型原则

1. **可插拔 (Provider 抽象)**：ASR 与 LLM 均通过统一接口接入，可随时切换本地/云端、开源/商业。
2. **成本可控**：优先开源可离线方案，云端按量作为兜底与加速。
3. **中文优先**：所有模型选型以中文（普通话）效果为第一判据。
4. **数据不出域**：为满足隐私合规，默认保留本地化路径。
5. **先验证后锁定**：M0 用实测准确率/成本/耗时数据做最终决策，不做纸上选型。

## 5. 待锁定决策（依赖 M0）

| 决策点 | 候选 | 决策依据 |
| --- | --- | --- |
| ASR 主方案 | Whisper / FunASR / 云API | 中文准确率、成本、数据出域 |
| LLM 主方案 | DeepSeek / Qwen / GPT | 纪要质量、成本、私有化 |
| 部署形态 | 本地 / 云端 | 目标用户与合规要求 |

---

> 📌 **下一步**：各模块如何组合成系统，见 [architecture.md](architecture.md)；具体链路处理细节见 [technical-solution.md](technical-solution.md)。
