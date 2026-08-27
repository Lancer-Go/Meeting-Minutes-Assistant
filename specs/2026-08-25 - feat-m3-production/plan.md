# M3 · 生产化（稳定可扩展）— 执行计划 (Plan)

| 文档类型 | 执行计划 |
| --- | --- |
| 阶段 | M3 · 生产化（稳定可扩展） |
| 分支 | feat/m3-production |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文把 roadmap.md 中 M3 的 8 步工作顺序组织为可执行的**任务组**。每个任务组含目标、任务项、产出与验收；任务组之间按依赖推进（前一组的验收是后一组的输入）。M3 在 M2「结构化纪要 + 编辑检索」基础上做**生产化**：满足全部非功能需求（NFR），对外提供稳定、合规、可观测的云端 SaaS。复用 M0/M1/M2 已锁定选型（ASR 腾讯云 16k_zh / LLM DeepSeek-V4 Pro（deepseek-v4-pro）/ FastAPI / Docker），本阶段锁定生产基础设施（用户已确认）：**腾讯云服务器 + Docker Compose 单机部署（Worker 独立容器 + 存储外置，预留横向扩缩，K8s 留真实多机需要）**、**自托管 Postgres + MinIO（S3 兼容，预留平滑迁移 COS）**、**自建账号体系基础版（注册/登录 + JWT，无高级 RBAC）**、**Prometheus + Grafana 自建可观测**。

## 任务组总览

| 任务组 | 内容 | 产出 | 依赖 |
| --- | --- | --- | --- |
| TG-0 | 服务拆分与 Docker 全容器化 | 多服务 Compose（api / worker / redis / postgres / minio / prometheus / grafana）+ 配置化改造 | — |
| TG-1 | CI/CD 流水线 | GitHub Actions（lint → test → build → 镜像发布） | TG-0 |
| TG-2 | 生产存储迁移 | PostgreSQL（tasks/minutes/comments/users/audit_logs）+ MinIO 对象存储 + 迁移脚本 | TG-0 |
| TG-3 | 可观测 | `/metrics` 指标端点 + Prometheus 采集 + Grafana 面板 + 告警规则 | TG-0 |
| TG-4 | 安全加固 | 注册/登录 + JWT 鉴权、越权防护、上传校验增强、模型注入防护、AES-256 加密、审计 | TG-2 |
| TG-5 | 性能测试 | Locust 压测 + 大文件/长会议/并发报告（吞吐 ≥ 实时 5 倍） | TG-2 |
| TG-6 | 成本监控与限额告警 | 按场/按量成本统计 + 限额告警 | TG-3, TG-4 |
| TG-7 | 灰度上线与监控观察 | 云端部署 + TLS + 观察期（在线率 ≥ 99%、无 P0/P1） | TG-1, TG-5, TG-6 |

## 任务组明细

### TG-0 · 服务拆分与 Docker 全容器化
- **目标**：从 M1/M2 单服务 `mma` 拆分为 API 与 Worker 独立服务，全部中间件容器化，一键编排（对应 roadmap 工作顺序 1）。
- **任务项**：
  - 拆服务：`mma-api`（FastAPI + 前端静态资源）与 `mma-worker`（任务执行，复用同一代码镜像、不同启动命令 `uvicorn` vs `celery worker`），两者共享 `app/` 包。
  - 引入生产队列：`app/worker.py` 由 BackgroundTasks 直调改造为 **Celery + Redis**（tech-stack A3「FastAPI BackgroundTasks（M1）→ Celery + Redis（M3）」），API 提交任务入队，worker 消费执行全链路并回写状态/进度。
  - 编排 `docker-compose.yml` 多服务：`api` / `worker` / `redis` / `postgres` / `minio` / `prometheus` / `grafana`；数据卷外置；`worker` 可用 `docker compose up --scale worker=N` 横向扩缩（架构预留，单机验证）。
  - 配置化改造 `app/config.py`：新增 `DATABASE_URL` / `REDIS_URL` / `S3_ENDPOINT` / `S3_BUCKET` / `JWT_SECRET` / `COST_LIMIT_DAILY` 等环境变量，全部走 `.env`，本地开发保持默认值（SQLite + 本地 FS）不破坏 M1/M2 体验。
- **产出**：多服务 Compose 编排 + Celery worker 独立容器 + 配置化改造。
- **验收**：`docker compose up -d` 一键拉起全部服务；`--scale worker=2` 可扩缩且任务正常消费；`docker compose down` 不丢数据（卷外置）。

### TG-1 · CI/CD 流水线
- **目标**：代码合入自动过 lint / test / build，镜像可发布（对应 roadmap 工作顺序 2；tech-stack A3「GitHub Actions（🕐 M3）」）。
- **任务项**：
  - 建 `.github/workflows/ci.yml`：`lint`（ruff / flake8 + 编译检查）→ `test`（pytest 全量，含覆盖率报告）→ `build`（docker build 多服务镜像）。
  - 镜像发布 job（tag / main 分支触发）：构建 `mma-api` / `mma-worker` 镜像推送 GHCR（GitHub Container Registry），部署端拉取。
  - 本地等价验证：`ruff check .`、`pytest`、`docker build` 均可在本地跑通后再推送。
- **产出**：GitHub Actions 流水线 + GHCR 镜像发布。
- **验收**：CI yaml 语法正确、本地等价命令全绿；推送后 action 全绿且镜像可拉取。

### TG-2 · 生产存储迁移
- **目标**：SQLite → PostgreSQL，本地文件 → MinIO 对象存储（对应 roadmap 工作顺序 3；tech-stack A3「SQLite → S3 + PostgreSQL（M3）」，用户已确认自托管容器方案）。
- **任务项**：
  - `app/db.py` 改造：标准库 sqlite3 → **SQLAlchemy**（或 psycopg 适配层），`DATABASE_URL` 驱动（`sqlite://` 本地开发兼容 / `postgresql://` 生产）；迁移 `tasks` / `minutes` / `comments` 表 + 数据迁移脚本（SQLite 旧数据导入 PG）。
  - 对象存储：引入 boto3，封装 `app/storage.py`（S3 兼容接口）：上传文件 / 任务产物（`transcript.json`、`structured_minute.json`、`minutes.md`）→ MinIO bucket；`stored_path` 字段改存对象键；保留本地 FS 配置兜底。
  - Compose 增加 `postgres`（含持久卷 + 健康检查）与 `minio`（含初始化 bucket）。
- **产出**：PostgreSQL 版 db 层 + MinIO 存储层 + 迁移脚本。
- **验收**：全链路（上传 → 转写 → 纪要）在 PG + MinIO 下跑通；SQLite 模式仍可本地开发；迁移脚本把现有 `data/` 数据导入 PG/MinIO 成功。

### TG-3 · 可观测
- **目标**：指标、告警、面板可用（对应 roadmap 工作顺序 4；tech-stack B6「Prometheus + Grafana 留 M3」，用户已确认自建）。
- **任务项**：
  - 指标端点：`GET /metrics`（prometheus-client）：任务数 / 状态计数、转写与纪要耗时 histogram、错误率、LLM token 用量与成本 counter（供 TG-6 复用）。
  - Compose 增加 `prometheus`（scrape 配置）与 `grafana`（预置 dashboard JSON：任务吞吐 / 错误率 / 耗时 / 成本）。
  - 告警规则（Alertmanager 或 Grafana Alert）：错误率突增、任务积压、成本超限（与 TG-6 联动）→ webhook / 邮件通知。
  - 结构化日志（M1 `JsonFormatter` 已落地）保持，补充请求级 trace（request_id 贯穿 api → worker）。
- **产出**：`/metrics` + Prometheus 采集 + Grafana 面板 + 告警规则。
- **验收**：`curl /metrics` 返回指标且数值随任务变化；Grafana 面板出图；告警规则可被测试事件触发。

### TG-4 · 安全加固
- **目标**：满足 NFR 安全项（鉴权、加密、越权防护、上传校验、注入防护、审计），通过 OWASP 检查（对应 roadmap 工作顺序 5）。
- **任务项**：
  - **鉴权**（用户已确认：自建账号体系基础版）：`users` 表（PG）+ 注册/登录接口（`POST /api/auth/register`、`POST /api/auth/login`）+ 密码哈希（bcrypt/argon2）+ **JWT**（PyJWT，HS256，过期与刷新策略）+ FastAPI 依赖注入鉴权中间件；前端加登录/注册页，API 请求带 Bearer token。
  - **越权防护**：`tasks` / `minutes` / `comments` 查询全部按 `user_id` 过滤（任务创建者隔离），删除/编辑接口校验归属；历史检索同理。
  - **上传校验增强**：M1 已有格式白名单/大小校验，补文件魔数（magic bytes）校验、文件名消毒、时长上限（≤ 2h）服务端复核。
  - **模型注入防护**：转写文本 / 批注 / 标题等外部输入进 LLM 前做提示词注入缓解（输入边界标记、指令冲突提示、超长截断），输出按 Markdown 转义渲染，不执行任何动态内容。
  - **加密存储**：敏感字段与纪要内容 AES-256（应用层加密或 MinIO SSE 服务端加密）；TLS 全链路（TG-7 Caddy 反代终止 TLS）。
  - **审计**：`audit_logs` 表（或结构化日志）：登录成功/失败、任务创建、纪要编辑、批注增删等关键操作留痕。
- **产出**：鉴权中间件 + users 表 + 越权/注入/上传防护 + AES-256 加密 + 审计日志。
- **验收**：未登录访问业务接口返回 401；用户 A 无法读写用户 B 的任务/纪要；OWASP 检查清单（鉴权 / 越权 / 上传 / 注入 / 加密 / TLS）逐项通过。

### TG-5 · 性能测试
- **目标**：验证吞吐 ≥ 实时 5 倍、定位瓶颈（对应 roadmap 工作顺序 6；tech-stack B5「性能测试 Locust / k6」—— 选 **Locust**，与 Python 生态一致）。
- **任务项**：
  - Locust 压测脚本（`locustfile.py`）：并发上传任务、任务状态轮询、纪要查询混合场景。
  - 边界用例：大文件（2h 会议量级）、长转写（多切片）、并发 N worker 消费。
  - 转写吞吐计算：实时 5 倍 = 处理 2h 音频 ≤ 24min；用 mock ASR（快进模式）+ 抽样真实云 ASR 控制压测成本。
  - 输出性能报告：吞吐 / 延迟 / 资源基线（CPU / 内存 / 队列积压），定位瓶颈并给出结论。
- **产出**：`locustfile.py` + 性能测试报告。
- **验收**：转写吞吐 ≥ 实时 5 倍（mock 与抽样实测口径分别记录）；并发下无任务丢失、无状态错乱。

### TG-6 · 成本监控与限额告警
- **目标**：成本可见可控（对应 roadmap 工作顺序 7；tech-stack A6「正式值待 M3 成本监控落地后重测」）。
- **任务项**：
  - 成本采集：LLM token 用量（input / cache hit / output）与金额、ASR 用量（时长/切片数）入指标与 `tasks.cost_rmb`（已有字段）；新增按日/按场聚合统计（接口 + Grafana 面板）。
  - 限额告警：日成本限额（默认值可配，如 ¥5/日）、单场超预算（> ¥1）告警，联动 TG-3 告警渠道；超限可选暂停新任务（可配置）。
  - 回填 A6 单场成本正式实测值（V4 Pro 空闲/高峰两档）。
- **产出**：成本统计接口/面板 + 限额告警 + A6 实测回填。
- **验收**：跑一场真实会议后成本数据可见且与估算同量级；超限测试触发告警。

### TG-7 · 灰度上线与监控观察
- **目标**：云端真实上线 + 观察期验证（对应 roadmap 工作顺序 8）。
- **任务项**：
  - 部署到腾讯云服务器（用户提供/已有）：`docker compose pull && up -d`，systemd/容器自重启，Caddy 反代 + 自动 HTTPS（域名）/ HTTP（无域名 IP 直连）。
  - 回滚方案：旧镜像 tag 保留，`docker compose down + 指定版本镜像 up`；数据卷备份策略（PG dump + MinIO 快照）。
  - 观察期（如 7 天）：在线率（uptime + 探活）、错误率、告警触发情况、成本日统计；修复观察期问题。
  - 输出上线观察报告，回填验收指标（在线率 ≥ 99%、无 P0/P1）。
- **产出**：生产部署脚本/文档 + TLS + 观察报告。
- **验收**：观察期在线率 ≥ 99%；无 P0/P1 事故；监控/告警/成本面板真实可用。

## 依赖关系

```
TG-0 ──► TG-1 ──────────────► TG-7
  ├──► TG-2 ──► TG-5 ────────┘
  ├──► TG-3 ──► TG-6 ────────┘
  └──► TG-2 ──► TG-4 ──► TG-6┘
```

> TG-0（服务拆分与容器化）是全部后续任务组的基础；TG-2（存储迁移）为 TG-4（用户表/审计在 PG）与 TG-5（生产存储下压测）的前置；TG-6 依赖 TG-3 指标通道与 TG-4 鉴权（成本按用户归属）；TG-7（上线）依赖 TG-1~TG-6 全部收口。任务组按上述依赖串行推进；TG-1 与 TG-2、TG-3 在 TG-0 之后可并行。
