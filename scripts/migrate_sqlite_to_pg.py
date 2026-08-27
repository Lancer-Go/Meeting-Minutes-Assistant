"""SQLite → PostgreSQL 数据迁移脚本（M3 TG-2）。

把现有本地 SQLite（data/mma.db）的 tasks / minutes / comments（及 users / audit_logs /
cost_stats）迁移到 PostgreSQL。迁移前请先备份。

用法：
    # 目标库从 DATABASE_URL 环境变量读取（或 --target 指定）
    python scripts/migrate_sqlite_to_pg.py --target postgresql://mma:mma@localhost:5432/mma

    # 指定来源（默认 config.DB_PATH，即 data/mma.db）
    python scripts/migrate_sqlite_to_pg.py --source sqlite:///data/mma.db --target postgresql://...

    # 仅试运行（只统计不写入）
    python scripts/migrate_sqlite_to_pg.py --target ... --dry-run

脚本同时支持 sqlite→sqlite 复制（用于本地演练验证逻辑）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, inspect, select

from app import config
from app.db import Base

MIGRATE_MODELS = ["tasks", "minutes", "comments", "users", "audit_logs", "cost_stats"]


def _resolve_url(args) -> str:
    if args.source:
        return args.source
    if args.source_path:
        return "sqlite:///" + str(Path(args.source_path).resolve()).replace("\\", "/")
    return "sqlite:///" + str(Path(config.DB_PATH).resolve()).replace("\\", "/")


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL 数据迁移")
    parser.add_argument("--source", help="来源数据库 URL（覆盖默认 SQLite）")
    parser.add_argument("--source-path", help="来源 SQLite 文件路径")
    parser.add_argument("--target", help="目标数据库 URL（默认 DATABASE_URL）",
                        default=config.DATABASE_URL or None)
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()

    source_url = _resolve_url(args)
    target_url = args.target or config.DATABASE_URL
    if not target_url:
        print("错误：未指定目标数据库。请设置 DATABASE_URL 或传 --target。")
        return 1

    src = create_engine(source_url)
    tgt = create_engine(target_url)
    insp = inspect(src)
    tgt_insp = inspect(tgt)

    print(f"来源: {source_url}")
    print(f"目标: {target_url}")
    if args.dry_run:
        print("（--dry-run：只统计不写入）\n")

    if not args.dry_run:
        Base.metadata.create_all(tgt)

    total = 0
    for table_name in MIGRATE_MODELS:
        if table_name not in insp.get_table_names():
            continue
        table = Base.metadata.tables[table_name]
        pk = next(iter(table.primary_key.columns)).name

        with src.connect() as sc:
            rows = [dict(r) for r in sc.execute(select(table)).mappings()]
        if not rows:
            continue

        existing = set()
        with tgt.connect() as tc:
            if table_name in tgt_insp.get_table_names():
                existing = {r[0] for r in tc.execute(
                    select(table.c[pk])).all()}

        written = 0
        if not args.dry_run:
            with tgt.begin() as tc:
                for r in rows:
                    if r[pk] in existing:
                        continue
                    tc.execute(table.insert().values(**r))
                    written += 1
        else:
            written = sum(1 for r in rows if r[pk] not in existing)

        total += written
        print(f"  {table_name}: {len(rows)} 行，写入 {written} 行")

    print(f"\n完成：共写入 {total} 行。")
    print("提示：文件产物（音频/纪要）迁移至 MinIO 由应用侧 storage 层在 S3 模式下按需上传，")
    print("      或将本地 data/ 目录手动同步至对象存储 bucket。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
