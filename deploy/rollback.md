# 回滚方案（TG-7）

## 原则
- 镜像不可变：每次发布打新 tag（CI 已推 `ghcr.io/<owner>/mma:<sha>` 与 `:latest`）。
- 数据外置：PG / MinIO / Redis 数据都在独立 volume，回滚**不影响数据**。
- 回滚 = 换回旧镜像 tag + 重启，秒级完成。

## 镜像回滚

```bash
# 当前版本记录
docker compose images

# 回滚到上一版（把 <old-sha> 换成上一次的镜像 tag）
docker compose down
MMA_IMAGE_TAG=<old-sha> docker compose up -d
# 或在 compose 里指定 image: ghcr.io/<owner>/mma:<old-sha>
```

## 数据回滚（若迁移/结构变更需回退）

```bash
# PostgreSQL：恢复备份
docker compose exec -T postgres psql -U mma mma < backup/2026-08-XX.sql

# MinIO：恢复快照
docker compose exec minio mc mirror --overwrite s3backup/ mma/
```

## 回滚决策标准
| 级别 | 触发条件 | 动作 |
| --- | --- | --- |
| P0 | 全站宕机 / 数据损坏 | 立即回滚镜像 + 恢复数据 |
| P1 | 核心链路（转写/纪要）不可用 | 15 分钟内回滚镜像 |
| P2 | 非核心功能异常 | 记录后修复，观察期顺延 |

## 回滚演练（本地模拟生产）
```bash
docker compose up -d --scale worker=2   # 扩缩验证
docker compose down && docker compose up -d  # 重启演练（验证数据不丢）
```
