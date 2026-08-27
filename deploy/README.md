# M3 灰度上线部署指南（TG-7）

> 部署目标：腾讯云服务器 + Docker Compose 单机多服务（用户 2026-08-25 确认）。
> ✅ **已真实上线（2026-08-27）**：腾讯云 2C2G（广州 ap-guangzhou / Ubuntu 24.04）采用**裁剪版**服务集
> （api / worker / redis / postgres，去掉 minio / prometheus / grafana，对象存储直接走腾讯云 COS），
> 配 4G swap + worker 并发=1；升级到 4C8G 后恢复 minio / prometheus / grafana 即可跑全套。

## 1. 服务器准备（腾讯云轻量/云服务器，2C4G 起）

```bash
# 安装 Docker + Compose 插件
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 拉取仓库（或 scp 上传代码）
git clone https://github.com/Lancer-Go/Meeting-Minutes-Assistant.git
cd Meeting-Minutes-Assistant
```

## 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少填写：
#   TENCENT_SECRET_ID / TENCENT_SECRET_KEY   （腾讯云 ASR）
#   DEEPSEEK_API_KEY                         （LLM）
#   JWT_SECRET                               （⚠️ 换成 ≥32 字节随机串）
#   POSTGRES_PASSWORD / GRAFANA_ADMIN_PASSWORD
```

> **对象存储**：生产用腾讯云 COS 时，`.env` 设 `S3_ENDPOINT=https://cos.ap-guangzhou.myqcloud.com`、`S3_BUCKET`、`S3_REGION=ap-guangzhou`、`MMA_S3_ADDRESSING_STYLE=virtual`、`S3_SSE_ENABLED=true`、`MMA_ASR_URL_ENABLED=true`（compose 的 `S3_ENDPOINT` 已改为 `${S3_ENDPOINT:-http://minio:9000}`，`.env` 可覆盖默认 MinIO）。

## 3. 一键拉起

```bash
docker compose up -d                     # api/worker/redis/postgres/minio/prometheus/grafana
docker compose up -d --scale worker=3    # worker 横向扩缩
docker compose ps                        # 确认全部 healthy
curl -f http://localhost:8000/health     # API 探活
```

## 4. TLS 反代（Caddy，有域名自动 HTTPS / 无域名 IP+HTTP）

```bash
# 方式 A：docker compose 内加 Caddy 服务（见 deploy/Caddyfile）
# 方式 B：宿主机装 Caddy
sudo apt-get install -y caddy
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## 5. 数据备份（观察期内每日）

```bash
docker compose exec postgres pg_dump -U mma mma > backup/$(date +%F).sql   # PG
docker compose exec minio mc mirror mma/ s3backup/                         # MinIO 快照
```

## 6. 观察期（7 天）

- 探活：`curl -f http://localhost:8000/health`（接入 uptime 监控）
- 指标：Grafana `:3000`（任务吞吐 / 错误率 / 耗时 / 成本）
- 告警：Prometheus `:9090/alerts`（错误突增 / 积压 / 成本超限 / 宕机）
- 记录：按 `deploy/observation.md` 模板逐日回填，最终输出上线观察报告

## 7. 回滚（见 deploy/rollback.md）

- 保留旧镜像 tag，`docker compose down` 后指定旧版本 up；数据卷外置不受影响。
