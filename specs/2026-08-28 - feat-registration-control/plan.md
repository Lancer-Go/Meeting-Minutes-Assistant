# 账号注册管控（禁自助注册 + 管理员/数据库加用户）— 执行计划 (Plan)

| 文档类型 | 执行计划 |
| --- | --- |
| 阶段 | 需求变更 · 账号注册管控 |
| 分支 | feat/registration-control |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文把「禁止自助注册，仅管理员或数据库直接新增用户」这一需求变更组织为可执行的**任务组**。每个任务组含目标、任务项、产出与验收；任务组之间按依赖推进。本变更**复用 M3 已落地的自建账号体系**（bcrypt 密码哈希 + PyJWT HS256 + `user_id` 越权隔离，见 tech-stack B4/B6 与 `app/auth.py`），不引入新选型、不新增产品目标（G）或需求组（FR），故登记为**需求变更**而非新里程碑（M5 留待 mission 的 G6/G7）。范围与五项决策已由用户 2026-08-28 咨询确认（见 requirements.md §4）。

## 任务组总览

| 任务组 | 内容 | 产出 | 依赖 |
| --- | --- | --- | --- |
| TG-0 | users 表加 `is_admin` + 迁移 | `User` 模型 + 轻量迁移补列 + `create_user` 扩展 | — |
| TG-1 | 管理员初始化 + `require_admin` 依赖 | config 管理员环境变量 + 启动引导 + `auth.require_admin` | TG-0 |
| TG-2 | 关闭注册 + 管理员创建用户接口 | 移除 `POST /api/auth/register` + 新增 `POST /api/admin/users` | TG-1 |
| TG-3 | CLI 创建用户 + 文档 | `app/cli.py create-user` + 使用文档 | TG-0 |
| TG-4 | 前端收敛 + 测试 + 收口 | 删 `register.html` + 测试 + 回归 + 指标回填 | TG-2, TG-3 |

## 任务组明细

### TG-0 · users 表加 `is_admin` + 迁移
- **目标**：数据模型支持「管理员」标记，作为管理员鉴权与最小权限控制的底座（对应 tech-stack B4 User 表回填）。
- **任务项**：
  - `app/db.py` 的 `User` 模型新增 `is_admin = Column(Boolean, default=False, nullable=False)`（需确认 `Boolean` 已从 SQLAlchemy 导入）。
  - `User.to_dict()` 返回增加 `is_admin` 字段。
  - `_MISSING_COLUMNS` 增加 `"users": {"is_admin": Column("is_admin", Boolean, default=False)}`，复用既有轻量补列迁移逻辑（覆盖 SQLite / PostgreSQL 双模式旧库）。
  - `create_user(username, password_hash, db_path=None, is_admin=False)` 扩展入参，写入 `is_admin`。
- **产出**：`User` 模型 + `is_admin` 迁移 + `create_user` 扩展。
- **验收**：新库建表含 `is_admin`（默认 False）；旧库迁移后 `users` 表补出该列且历史用户不受影响；`get_user`/`get_user_by_username` 返回含 `is_admin`；M1~M4 既有测试不破。

### TG-1 · 管理员初始化 + `require_admin` 依赖
- **目标**：提供首位管理员的初始化通道与「仅管理员」鉴权依赖。
- **任务项**：
  - `app/config.py` 新增 `MMA_ADMIN_USERNAME` / `MMA_ADMIN_PASSWORD`（默认空，未配置不触发初始化）。
  - 应用启动时（FastAPI lifespan / startup hook）执行「确保管理员存在」：若两项均配置，查 `db.get_user_by_username(MMA_ADMIN_USERNAME)`，不存在则 `create_user(..., is_admin=True)`（bcrypt 哈希）；已存在且 `is_admin=False` 则置为 True（或告警，口径见 requirements.md §5）。
  - `app/auth.py` 新增 `require_admin` 依赖：`get_current_user` 之后校验 `user["is_admin"]`，未登录 → 401、非管理员 → 403。
  - `app/auth.py` 的 `register()` 业务函数改名/重构为内部 `admin_create_user()`（或保留但不再被公开路由调用），复用「用户名非空/唯一/密码长度 ≥6」校验。
- **产出**：管理员环境变量 + 启动引导 + `require_admin` 依赖。
- **验收**：配置后首次启动自动生成 `is_admin=True` 的管理员；重复启动不重复建、不破坏已有密码；未配置时服务照常启动且无管理员；`require_admin` 对非管理员返回 403。

### TG-2 · 关闭注册 + 管理员创建用户接口
- **目标**：移除自助注册入口，管理员可通过受保护接口新增用户。
- **任务项**：
  - `app/main.py` 删除 `POST /api/auth/register` 路由（及 `/register.html` 页面路由，归 TG-4）；公开注册请求返回 404/403（口径见 requirements.md §5）。
  - `app/main.py` 新增 `POST /api/admin/users`：依赖 `require_admin`，入参 `username` / `password` / 可选 `is_admin`，调用 TG-1 的管理员创建逻辑，返回 `{"user": ...}`。
  - `app/audit.py` 记录 `admin_create_user` 审计（actor = 当前管理员、target = 新用户）。
- **产出**：注册接口关闭 + `POST /api/admin/users` + 审计。
- **验收**：无 token / 非管理员访问 `POST /api/admin/users` 分别返回 401 / 403；公开注册接口不可用；管理员可创建普通用户与管理员；重复用户名返回 400；审计日志留痕。

### TG-3 · CLI 创建用户 + 文档
- **目标**：提供「通过数据库直接新增用户」的运维途径（等价于管理员之外的第二种加人方式）。
- **任务项**：
  - 新增 `app/cli.py`：`argparse` 子命令 `create-user --username X --password Y [--admin]`，调用 `auth.hash_password` + `db.create_user(..., is_admin=...)`。
  - 错误处理：用户名已存在 / 密码 <6 位 → 明确报错并退出非零；成功打印用户名 + 是否管理员。
  - 使用文档：README 或 docs 补充 `python -m app.cli create-user ...` 用法与注意事项（生产库需指向 `DATABASE_URL`）。
- **产出**：`app/cli.py` + 使用文档。
- **验收**：CLI 创建普通用户 / 管理员均成功；重复用户名 / 短密码报错；文档可照做。

### TG-4 · 前端收敛 + 测试 + 收口
- **目标**：移除自助注册前端入口，补齐测试，回填文档收口。
- **任务项**：
  - 删除 `static/register.html` 与 `main.py` 的 `/register.html` 路由；`static/login.html` / `static/auth.js` 移除「注册」入口/链接。
  - 测试补充（`tests/`）：① 公开注册接口不可用；② `POST /api/admin/users` 鉴权（未登录 401 / 非管理员 403 / 管理员 200）；③ 管理员创建的用户可正常登录；④ `is_admin` 迁移后历史用户不受影响；⑤ CLI `create-user` 成功与失败路径。
  - 回归：M1~M4 全量测试 + 覆盖率 ≥ 70%（新增逻辑计入）。
  - 回填：`docs/tech-stack.md` B4 User 表 `is_admin`、B4 API 表 `/api/auth/register` → 移除、`/api/admin/users` → 落地、B6 安全；`docs/roadmap.md` 变更记录状态由「规划」转「已落地」；`docs/mission.md` 决策 8 保持。
- **产出**：前端收敛 + 测试 + 回归报告 + 文档回填。
- **验收**：全量测试绿、覆盖率 ≥ 70%；全库无自助注册入口残留；文档回填一致。

## 依赖关系

```
TG-0 ──► TG-1 ──► TG-2 ──┐
TG-0 ──► TG-3             ├──► TG-4
                          ┘
```

> TG-0（`is_admin` 字段）是 TG-1/TG-3 的前置；TG-1（管理员引导 + `require_admin`）是 TG-2（管理接口）的前置；TG-2 与 TG-3 相互独立可并行；TG-4 收口（前端 + 测试 + 文档）依赖 TG-2 + TG-3 全部落地。
