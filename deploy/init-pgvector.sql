-- M4 · 向量检索（TG-2）：PostgreSQL 启用 pgvector 扩展。
-- 仅在数据卷首次初始化（空 /var/lib/postgresql/data）时自动执行；
-- 已有 M3 数据卷需手动执行：
--   docker compose exec postgres psql -U mma -d mma -c "CREATE EXTENSION IF NOT EXISTS vector;"
CREATE EXTENSION IF NOT EXISTS vector;
