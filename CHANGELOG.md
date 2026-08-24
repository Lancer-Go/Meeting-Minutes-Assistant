# 更新日志 (Changelog)

本文件记录项目的所有重要变更。**每次提交（commit）都必须在此登记一条记录**，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范。

## 分类约定

| 分类 | 含义 |
| --- | --- |
| `新增` | 新功能 / 新文件 |
| `变更` | 对现有功能的修改 |
| `修复` | Bug 修复 |
| `文档` | 文档相关变更 |
| `移除` | 删除的功能 / 文件 |
| `杂项` | 其他无法归类的变更 |

> 每条记录末尾附提交哈希前 7 位（如 `6d15d7c`），便于回溯。

## [Unreleased]

<!-- ⬇️ 新提交在此登记，格式：
### 分类
- 变更说明（提交哈希前 7 位）
-->

### 新增
- 实现 M1 MVP：FastAPI 服务 + 异步全链路（app/ 包 TG-0~TG-7：上传校验/音频提取/腾讯云切片转写/DeepSeek 纪要/Markdown 导出/任务状态机/极简前端/重试与结构化日志），含 Docker Compose 一键启动与单测覆盖率 78%（9b99e1e）
- 新增 M1 MVP 任务准备（plan / requirements / validation 三文档）（042548b）
- 新增 M0 概念验证任务准备（plan / requirements / validation 三文档）（605e4a3）
- 实现 M0 任务组 TG-0~TG-6：环境脚手架、音频提取、语音转写、纪要生成、端到端流水线、CER 评测（audio / asr / summarize / pipeline / eval_cer / config / make_sample + requirements.txt）（3e1f442）
- 新增《选型决策记录》初稿（含本地离线实测 CER / 耗时 / 成本）（3e1f442）
- 接入云 ASR 实测：阿里云 NLS 实时语音转写 + 腾讯云录音文件识别（b3499f0）

### 变更
- 阶段执行文档目录迁移至 specs/ 下（3e1f442）
- 用真实会议（80min）完成三家 ASR 对比与 DeepSeek 端到端纪要，锁定选型（ASR 腾讯云 16k_zh / LLM DeepSeek-chat），回填《选型决策记录》（b3499f0）

### 文档
- tech-stack 更新至 v0.3，回填 M0 实测锁定厂商（ASR 腾讯云 16k_zh / LLM DeepSeek-chat），关联《选型决策记录》（a2ada36）

## [0.2.0] - 2026-08-24

### 文档
- 新增 CHANGELOG.md，建立每次提交登记变更的规范（c72a725）
- 确认关键决策（云端 SaaS 优先 / 云 ASR / 中文为主 / ≤2h / 利润 0），三文档更新至 v0.2（6d15d7c）
- 收敛为 mission / roadmap / tech-stack 三文件，roadmap 重写为详细实现路线图（afd32d6）
- 按 SDD 规范拆分文档目录（mission / roadmap / tech-stack 等 12 个文件）（f8a6f4f）

## [0.1.0] - 2026-08-23

### 新增
- 新增项目总章程与 SDD 软件设计文档（3488dcc）
- 会议纪要助手项目初始化（fddfdc9）
