# M3 · 生产化（稳定可扩展）— 需求与范围说明 (Requirements)

| 文档类型 | 需求与范围说明 |
| --- | --- |
| 阶段 | M3 · 生产化（稳定可扩展） |
| 分支 | feat/m3-production |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文说明 M3 的**范围、已定决策与上下文**，作为 plan.md 的依据与 validation.md 的对照。M3 复用 M0/M1/M2 已锁定选型（ASR 腾讯云 16k_zh / LLM DeepSeek-V4 Pro（deepseek-v4-pro），见 [选型决策记录](../../docs/decisions/选型决策记录.md)），新增生产基础设施（队列 / 存储 / 可观测 / CI/CD / 安全 / 成本），不重复业务链路选型。生产化四项关键选型已由用户 2026-08-25 咨询确认（见 §4）。

## 1. 目标（一句话）

满足全部非功能需求（NFR），把现有本地闭环升级为**稳定、合规、可观测的云端 SaaS**：云端部署（API + 队列 + Worker 可扩缩）、可观测（日志/指标/告警）、安全合规（加密/鉴权/审计/越权防护）、成本监控（按场/按量统计与限额告警）。

## 2. 范围

### 范围内 (In Scope) — 对应 NFR 全量 + FR 支撑

| 维度 | 需求 | M3 交付 |
| --- | --- | --- |
| 部署 | 云端 SaaS 形态（mission §8-1） | 腾讯云服务器 + Docker Compose 单机多服务编排；Worker 独立容器可横向扩缩（架构预留，K8s 留真实多机需要） |
| 队列 | 生产级任务队列 | Celery + Redis（替换 M1 BackgroundTasks） |
| 存储 | 生产存储 | SQLite → PostgreSQL；本地文件 → MinIO 对象存储（S3 兼容，预留平滑迁移 COS）+ 迁移脚本 |
| 可观测 | 指标 / 告警 | `/metrics`（prometheus-client）+ Prometheus + Grafana 面板 + 告警规则；结构化日志沿用（M1 JsonFormatter）+ request_id 贯穿 |
| CI/CD | 自动化交付 | GitHub Actions（lint → test → build → GHCR 镜像发布） |
| 安全合规 | NFR 安全项 | 自建账号体系基础版（注册/登录 + JWT）、越权防护（user_id 隔离）、上传校验增强（魔数/消毒/时长复核）、模型注入防护、AES-256 加密存储、审计日志、TLS（Caddy 反代） |
| 性能 | 吞吐 ≥ 实时 5 倍 | Locust 压测 + 大文件/长会议/并发报告 |
| 成本 | 成本可见可控 | 按场/按量成本统计（LLM token + ASR 用量）+ 限额告警（联动可观测）+ A6 单场成本实测回填 |
| 上线 | 灰度上线 | 云端部署 + TLS + 观察期（在线率 ≥ 99%、无 P0/P1）+ 回滚方案 |

### 范围外 (Out of Scope) — M3

- ❌ 完整 Kubernetes 编排（TKE / k3s）—— 本次单机 Docker Compose，横向扩缩仅架构预留；K8s 留真实多机需要时。
- ❌ 多模型热切换 / RAG 向量检索问答 / 实时转写 / 行动项同步 IM 待办 —— M4（FR-12~14，G5~G7）。
- ❌ 跨组织高级权限体系（RBAC / 细粒度 ACL）—— mission §3 Out of Scope，本次仅基础账号 + 用户隔离。
- ❌ 本地化 / 私有化部署选项 —— 后期合规选项，本期不做。
- ❌ PDF / docx 导出 —— mission §8 决策 7，Markdown 即可。
- ❌ 视频画面分析 / 会议室硬件集成 —— mission §3 Out of Scope。

## 3. 关键决策（沿用 mission.md §8，逐条映射到 M3 影响）

| # | 决策点 | 结论 | 对 M3 的影响 |
| --- | --- | --- | --- |
| 1 | 首期形态 | ✅ 云端 SaaS 优先 | M3 真实云端部署（腾讯云服务器单机 Compose）；K8s 留后期 |
| 2 | ASR 选型 | ✅ 走云 API（接受数据出域） | 生产环境密钥进 `.env`/secret 管理；出域策略不变；加密/审计覆盖数据生命周期 |
| 3 | 主要语言 | ✅ 中文为主，英文术语混用 | 性能测试用中文样例；注入防护提示词按中文设计 |
| 4 | 会议时长 | ✅ 单场 ≤ 2 小时 | 性能测试边界 = 2h 大文件；上传时长服务端复核 |
| 5 | 成本预算 | ✅ 利润 0，性价比优先 | 单机 Compose + 自托管 PG/MinIO 控成本；限额告警防成本失控（A6 已给降本手段） |
| 6 | IM/待办集成 | 🕐 暂不需要 | M3 不做第三方集成，成本告警走 webhook/邮件 |
| 7 | 输出格式 | ✅ Markdown 即可 | 渲染链路不变，仅存储/导出通道迁移 |

## 4. 技术选型（沿用 tech-stack.md A3/A5/B6 + 用户确认）

| 决策点 | 已定方向 | 锁定结论 | M3 用法 |
| --- | --- | --- | --- |
| 部署形态 | 🔶 K8s / 云托管（roadmap） | ✅ **腾讯云服务器 + Docker Compose 单机**（用户 2026-08-25 确认）：Worker 独立容器 + 存储外置预留扩缩；K8s 留真实多机需要 | TG-0 / TG-7 |
| 任务队列 | 🔶 Celery + Redis（A3 建议） | ✅ Celery + Redis（生产级，替换 BackgroundTasks） | TG-0 |
| 存储 | 🔶 S3 + PostgreSQL（A3 建议） | ✅ **自托管 Postgres + MinIO 容器**（用户确认）：S3 兼容接口，预留平滑迁移腾讯云 COS | TG-2 |
| 可观测 | 🔶 Prometheus + Grafana（B6 建议） | ✅ **Prometheus + Grafana 自建**（用户确认），随服务容器化；告警走 webhook/邮件 | TG-3 |
| 鉴权 | 🔶 JWT / OAuth（B6 建议） | ✅ **自建账号体系基础版：注册/登录 + JWT**（用户确认，无高级 RBAC） | TG-4 |
| CI/CD | 🔶 GitHub Actions（A3 建议） | ✅ GitHub Actions（lint → test → build → GHCR 镜像发布） | TG-1 |
| 性能测试 | 🔶 Locust / k6（B5 建议） | ✅ **Locust**（Python 生态一致） | TG-5 |
| TLS | — | Caddy 反代（自动 HTTPS，有域名）/ IP 直连 HTTP（无域名） | TG-7 |
| 加密 | AES-256（NFR） | 应用层加密敏感字段 / MinIO SSE；TLS 全链路 | TG-4 |
| 密码哈希 / JWT | — | bcrypt / argon2 + PyJWT（HS256） | TG-4 |
| ORM / S3 SDK | — | SQLAlchemy（兼容 sqlite + postgresql）+ boto3（S3 兼容） | TG-2 |

## 5. 约束与假设

- 部署目标：腾讯云轻量/云服务器（用户提供/已有账号）；域名可选（Caddy 自动 HTTPS 需要域名，否则 IP + HTTP）。
- 兼容性：本地开发保留 SQLite + 本地 FS 模式（`DATABASE_URL` / `S3_ENDPOINT` 配置切换），不破坏 M1/M2 的开发与测试体验；`pytest` 全量在两种模式下可跑。
- 数据迁移：SQLite 现有 `data/`（tasks/minutes/comments + 文件产物）需迁移脚本导入 PG + MinIO，迁移前备份。
- 成本：单机 2C4G 起（估算）；PG / MinIO / Prometheus / Grafana 同机容器，资源开销纳入 TG-5 基线。
- 压测成本控制：性能测试以 mock ASR（快进）为主，真实云 ASR 仅抽样，避免压测产生高额 API 费用（mission §5 利润 0）。
- 在线率口径：观察期（7 天）uptime / 探活成功率 ≥ 99%，含计划内维护窗口说明。
- 上线依赖：TG-7 需要云服务器就绪；若用户云服务器未就绪，降级为「本地模拟生产环境部署演练」，如实记录阻塞与缺口指标，服务器就绪后回填。
- 安全基线：OWASP 检查以「基础账号 + 用户隔离」范围执行，不含高级权限体系（mission §3 排除项）。
- 质量判定：M3 退出以观察期实测指标为准，不达标不发版（tech-stack B5「质量底线」）。

## 6. 上下文（链路与模块）

M3 在 M2「处理流水线 + 业务数据模型」基础上，**改造基础设施层**：

```
（业务链路不变，M1/M2 复用）
ingestion → audio → asr → diarization → summary → extractor → role → render
                    （在 worker 内执行，M3 由 BackgroundTasks 改 Celery 消费）

（基础设施层，M3 改造）
config.py      ：新增 DATABASE_URL / REDIS_URL / S3_ENDPOINT / JWT_SECRET / COST_LIMIT_* 等
db.py          ：sqlite3 → SQLAlchemy（sqlite/postgresql 双模式）；新增 users / audit_logs / cost_stats 表
worker.py      ：BackgroundTasks 直调 → Celery task（api 入队、worker 消费）
ingestion/pipeline：文件产物 → storage.py（MinIO S3，本地 FS 兜底）
main.py        ：新增 /api/auth/register、/api/auth/login、/metrics；业务路由加鉴权依赖 + user_id 隔离
storage.py     ：新增（S3 封装，boto3）
auth.py        ：新增（注册/登录/JWT/密码哈希/鉴权依赖）
metrics.py     ：新增（prometheus-client 指标）
cost.py        ：新增（token/ASR 用量采集与限额判定）
audit.py       ：新增（关键操作审计留痕）
static/        ：前端新增登录/注册页，API 请求带 Bearer token
docker-compose.yml：单服务 → 多服务（api / worker / redis / postgres / minio / prometheus / grafana）
.github/workflows/ci.yml：新增（lint → test → build → GHCR）
locustfile.py  ：新增（性能压测）
```

- 数据模型对齐 tech-stack.md B4：`Task` 增 `user_id`（越权隔离）；新增 `User`（id, username, password_hash, created_at）、`AuditLog`（user, action, target, ip, at）、`CostStat`（date, task_id, llm_tokens_in/out/cache, llm_cost, asr_cost, total_cost）。
- API 新增：`POST /api/auth/register`、`POST /api/auth/login`、`GET /api/costs`（成本统计）、`GET /metrics`；既有路由（任务 / 纪要 / 批注 / 历史检索）全部加鉴权与用户隔离。
- 部署形态（用户已确认）：腾讯云服务器 + Docker Compose 单机；`worker` 独立容器可用 `--scale worker=N` 扩缩；存储外置（PG / MinIO 独立卷），K8s 留真实多机需要时再上。
