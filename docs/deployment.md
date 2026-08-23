# 部署与运维 (Deployment & Ops)

| 文档类型 | 部署与运维 |
| --- | --- |
| 版本 / 状态 | v0.1（草案）🏗️ |
| 关联文档 | [architecture](architecture.md) · [tech-stack](tech-stack.md) · [testing](testing.md) |

## 1. CI/CD

- **GitHub Actions**：lint → test → build → 镜像发布。
- 每个 PR 跑完整测试 + Eval 集，合并前门禁。

## 2. 容器化与编排

- **Docker Compose**：本地一键起（服务 + Worker + 队列 + 存储）。
- **Kubernetes**：云端集群，Worker 可横向扩缩。

## 3. 运行环境

| 形态 | 说明 |
| --- | --- |
| 云端 | API + 队列 + Worker（可扩缩）；ASR 可走 GPU Node Pool |
| 本地 | Docker Compose + 本地模型，数据不出域 |

## 4. 可观测性

- **结构化日志（JSON）**：请求链路、任务生命周期。
- **指标**：转写时长、错误率、成本、队列积压。
- **告警**：任务失败率、队列阻塞、成本超限。

## 5. 安全与合规

- 数据加密存储（AES-256）、传输 TLS、访问鉴权。
- 本地化部署选项，满足数据不出域要求。

---

> 📌 **下一步**：部署与合规相关的风险清单见 [risks.md](risks.md)。
