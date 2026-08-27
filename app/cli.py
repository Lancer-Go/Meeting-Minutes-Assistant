"""需求变更 · 账号注册管控 — CLI：数据库直接新增用户（等价于管理员之外的运维加人方式）。

用法（与 HTTP 接口同源，复用 `auth.hash_password` + `db.create_user`，避免两套哈希逻辑）：

    python -m app.cli create-user --username alice --password secret123
    python -m app.cli create-user --username admin --password secret123 --admin

⚠️ 生产环境（PostgreSQL）需先设置 `DATABASE_URL` 环境变量（或写入 .env）再运行，
   否则默认写入本地 SQLite（`MMA_DB_PATH` / `data/mma.db`）。
"""
from __future__ import annotations

import argparse
import sys

from app import auth, db


def _cmd_create_user(args: argparse.Namespace) -> int:
    db.init_db()  # 确保建表（幂等），否则全新库报 no such table
    try:
        user = auth.admin_create_user(args.username, args.password, is_admin=args.admin)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    role = "管理员" if user.get("is_admin") else "普通用户"
    print(f"已创建{role}：{user['username']}（id={user['id']}）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="app.cli",
        description="会议纪要助手 CLI（数据库直接新增用户）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-user", help="新增用户（数据库直接写入，禁自助注册后唯一运维加人方式）")
    p.add_argument("--username", required=True, help="用户名")
    p.add_argument("--password", required=True, help="密码（≥ 6 位）")
    p.add_argument("--admin", action="store_true", help="设为管理员（is_admin=True）")
    p.set_defaults(func=_cmd_create_user)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
