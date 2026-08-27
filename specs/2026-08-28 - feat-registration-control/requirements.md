# 账号注册管控（禁自助注册 + 管理员/数据库加用户）— 需求与范围说明 (Requirements)

| 文档类型 | 需求与范围说明 |
| --- | --- |
| 阶段 | 需求变更 · 账号注册管控 |
| 分支 | feat/registration-control |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文说明本需求变更的**范围、已定决策与上下文**，作为 plan.md 的依据与 validation.md 的对照。本变更**不引入新选型、不新增产品目标/需求组**，是对 M3 已落地「自建账号体系」的收紧：复用 bcrypt + PyJWT HS256 + `user_id` 越权隔离（见 `app/auth.py`、tech-stack B4/B6），仅改变「账号如何产生」。五项实现决策已由用户 2026-08-28 咨询确认（见 §4）。

## 1. 目标（一句话）

把「任何人可自助注册」收紧为「**禁止自助注册，仅管理员（`is_admin`）或通过数据库直接新增用户**」，落地为 mission §8 新增的决策 8。

## 2. 范围

### 范围内 (In Scope)

| 维度 | 需求 | 交付 |
| --- | --- | --- |
| 关闭自助注册 | 移除 `POST /api/auth/register` | 公开注册接口不可用；前端 `register.html` 删除、登录页去注册入口 |
| 管理员加用户 | 管理员可新增账号 | `POST /api/admin/users`（受 `require_admin` 鉴权，入参 username/password/可选 is_admin） |
| 管理员标记 | 数据模型区分管理员 | `users` 表加 `is_admin`（默认 False）+ 迁移 + `create_user` 扩展 |
| 管理员初始化 | 首位管理员来源 | 环境变量 `MMA_ADMIN_USERNAME` / `MMA_ADMIN_PASSWORD`，启动时确保存在（`is_admin=True`） |
| 数据库加用户 | 运维途径 | CLI `python -m app.cli create-user --username --password [--admin]` + 使用文档 |
| 测试与收口 | 覆盖与回填 | 鉴权/迁移/CLI 测试 + 回归 + docs 回填 |

### 范围外 (Out of Scope) — 本次不做（用户确认「最小集」）

- ❌ 禁用/删除用户、重置密码、列出用户等完整用户管理。
- ❌ 管理界面（Web 管理页）—— 仅 REST 接口 + CLI。
- ❌ 多管理员 / 角色层级（RBAC）、跨组织协作高级权限体系 —— mission §3 延续排除；本次仅单一 `is_admin` 布尔标记。
- ❌ 第三方 OAuth / SSO 登录。
- ❌ 开放自助注册的限流/邀请码等折中方案 —— 明确关闭。

## 3. 关键决策（映射 mission.md §8）

| # | 决策点 | 结论 | 对本变更的影响 |
| --- | --- | --- | --- |
| 1 | 首期形态 | ✅ 云端 SaaS 优先 | 在现有 FastAPI + PostgreSQL/SQLite 服务内实现，不新增部署形态 |
| 5 | 利润与成本预算 | ✅ 利润 0，性价比优先 | 纯本地逻辑改动，无新增云成本 |
| 7 | 输出格式 | ✅ Markdown 即可 | 不影响纪要链路 |
| 8 | 账号注册方式（新增） | ✅ 禁止自助注册；仅管理员（`is_admin`）或数据库直接新增用户 | 本变更的直接依据（mission v0.3 新增） |

> 说明：决策 2/3/4/6 与本变更无关（ASR/语言/时长/IM 集成），不在此逐条映射。

## 4. 实现决策（用户 2026-08-28 咨询确认）

| # | 决策点 | 结论 |
| --- | --- | --- |
| D1 | 首位管理员初始化 | ✅ 环境变量 `MMA_ADMIN_USERNAME` / `MMA_ADMIN_PASSWORD`，启动时确保存在（bcrypt 哈希，已存在则跳过） |
| D2 | 公开注册接口处理 | ✅ 彻底关闭 `POST /api/auth/register`，新增受管理员 JWT 保护的 `POST /api/admin/users` |
| D3 | 数据库加用户形式 | ✅ CLI 脚本 `python -m app.cli create-user`（+ 使用文档） |
| D4 | 用户管理范围 | ✅ 最小集：关闭自助注册 + 管理员可加用户（`users` 表加 `is_admin`），不做禁用/删除/重置密码/列用户 |
| D5 | 前端注册页处理 | ✅ 删除 `register.html`，只保留登录页（注册入口移除） |

## 5. 约束与假设

- **公开注册的「关闭」语义**：删除路由后 `POST /api/auth/register` 自然返回 404（FastAPI 无匹配路由）；如后续需要更明确信号可返回 403/410，本次以「路由不存在」为准（与 D2「彻底关闭」一致）。
- **管理员初始化幂等**：启动时「确保存在」需幂等——重复启动不重复建、不覆盖已有密码；`MMA_ADMIN_USERNAME` 已存在但 `is_admin=False` 时的处理口径：置为 True（管理员账号语义优先），并在日志告警（防止环境变量与库不一致）。
- **`AUTH_ENABLED=False` 兼容**：`require_admin` 复用 `get_current_user`，鉴权关闭时 `get_current_user` 返回 `None` —— 需在 `require_admin` 中明确「鉴权关闭时是否放行」。默认口径：鉴权关闭（本地开发/测试）时 `require_admin` **放行**（保持既有本地免鉴权体验）；生产 `AUTH_ENABLED=true` 时严格校验 `is_admin`。
- **CLI 与数据库指向**：`create-user` 直接写库，生产需指向 `DATABASE_URL`（PostgreSQL）；本地默认 SQLite。CLI 复用 `auth.hash_password`（bcrypt）与 `db.create_user`，与 HTTP 接口同源，避免两套哈希逻辑。
- **越权隔离不变**：业务路由的 `user_id` 隔离逻辑不受本变更影响；`is_admin` 仅用于「加用户」这一处权限判断，不改变纪要/任务的归属隔离。
- **兼容性**：本地 SQLite + 本地 FS 模式不破坏；M1~M4 既有测试全量可跑；`users` 旧库经 `_MISSING_COLUMNS` 迁移补 `is_admin`（默认 False），历史用户不受影响。

## 6. 上下文（链路与模块）

本变更集中在**认证层**，业务链路（ingestion → audio → asr → diarization → summary → extractor → role → render）不动：

```
（M3 已落地，复用）
app/auth.py      : bcrypt 哈希 + JWT + get_current_user（user_id 越权隔离）
app/db.py        : User 表（id/username/password_hash/created_at）+ create_user/get_user/get_user_by_username

（本次变更）
app/db.py        : 改造 — User 加 is_admin；create_user 扩展 is_admin；_MISSING_COLUMNS 迁移补列
app/auth.py      : 改造 — register() 重构为内部 admin_create_user；新增 require_admin 依赖
app/main.py      : 改造 — 删除 POST /api/auth/register 与 /register.html；新增 POST /api/admin/users
app/config.py    : 新增 MMA_ADMIN_USERNAME / MMA_ADMIN_PASSWORD + 启动确保管理员存在（lifespan）
app/cli.py       : 新增 — create-user 子命令（数据库直接加用户）
app/audit.py     : 复用 — admin_create_user 审计留痕
static/          : 删除 register.html；login.html / auth.js 移除注册入口
```

- 数据模型对齐 tech-stack B4：`User` 增加 `is_admin`（Boolean，默认 False）；ER 关系不变。
- API 变更对齐 tech-stack B4：`POST /api/auth/register` → 移除；新增 `POST /api/admin/users`（`require_admin` 鉴权）。
- 安全对齐 tech-stack B6：禁自助注册（关闭 `/api/auth/register`），仅管理员（`is_admin`）或数据库/CLI 新增用户。
