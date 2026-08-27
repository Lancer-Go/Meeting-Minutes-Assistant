# 账号注册管控（禁自助注册 + 管理员/数据库加用户）— 验收标准 (Validation)

| 文档类型 | 验收标准 |
| --- | --- |
| 阶段 | 需求变更 · 账号注册管控 |
| 分支 | feat/registration-control |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文定义本需求变更的**可交付物、验收标准与退出条件**，用于判断「禁止自助注册 + 管理员/数据库加用户」是否落地完成。验收口径 = mission §8 决策 8 + 用户 2026-08-28 确认的五项实现决策（requirements.md §4）+ M3 自建账号体系延续。

## 1. 可交付物

| # | 交付物 | 说明 |
| --- | --- | --- |
| D1 | `is_admin` 数据模型 | `User` 加 `is_admin`（默认 False）+ `_MISSING_COLUMNS` 迁移补列 + `create_user` 扩展 + `to_dict` 返回 |
| D2 | 管理员初始化 | `MMA_ADMIN_USERNAME` / `MMA_ADMIN_PASSWORD` 环境变量 + 启动「确保管理员存在」（幂等，bcrypt） |
| D3 | `require_admin` 依赖 | `get_current_user` 后校验 `is_admin`，未登录 401 / 非管理员 403 / 鉴权关闭放行 |
| D4 | 关闭自助注册 | 删除 `POST /api/auth/register` + `/register.html`；登录页移除注册入口 |
| D5 | 管理员创建用户接口 | `POST /api/admin/users`（`require_admin` 鉴权，入参 username/password/可选 is_admin）+ 审计 |
| D6 | CLI 创建用户 | `python -m app.cli create-user --username --password [--admin]` + 使用文档 |
| D7 | 测试与文档回填 | 鉴权/迁移/CLI 测试 + 回归 + tech-stack/roadmap 回填 |

## 2. 验收标准

| # | 标准 | 判据 | 数据来源 |
| --- | --- | --- | --- |
| V1 | 公开注册关闭 | `POST /api/auth/register` 无匹配路由（404）；无自助注册入口残留 | TG-2 / TG-4 |
| V2 | 管理员加用户 | 管理员 token 调 `POST /api/admin/users` 创建用户成功（201），新用户可登录 | TG-2 |
| V3 | 鉴权隔离 | 未登录访问 `/api/admin/users` → 401；非管理员 token → 403；管理员 → 200 | TG-2 |
| V4 | `is_admin` 迁移 | 旧库迁移后 `users` 表补 `is_admin`（默认 False），历史用户登录不受影响 | TG-0 |
| V5 | 管理员初始化幂等 | 配置后首次启动生成管理员（`is_admin=True`）；重复启动不重复建、不覆盖密码；未配置不报错 | TG-1 |
| V6 | CLI 加用户 | `create-user` 创建普通/管理员成功；重复用户名/短密码报错并退出非零 | TG-3 |
| V7 | 回归与覆盖率 | M1~M4 全量回归通过；单元测试覆盖率 ≥ 70%（新增逻辑计入） | TG-4 |
| V8 | 审计留痕 | 管理员创建用户写 `audit_logs`（action=`admin_create_user`，含 actor 与 target） | TG-2 |

## 3. 退出条件（判定本变更完成）

- ✅ 公开注册接口不可用，前端无自助注册入口。
- ✅ 管理员可经 `POST /api/admin/users` 新增用户（含可选 `is_admin`），非管理员被 403 拒绝。
- ✅ `users` 表含 `is_admin` 且旧库迁移无损。
- ✅ 首位管理员由环境变量启动时确保存在（幂等）。
- ✅ CLI `create-user` 可经数据库直接新增用户，文档可照做。
- ✅ 审计留痕，越权隔离（user_id）不受影响。
- ✅ M1~M4 回归通过，覆盖率 ≥ 70%，docs（tech-stack v0.11 / roadmap 变更记录）回填为「已落地」。

## 4. 数据采集模板（供 TG-0~4 记录）

| 验证项 | 样例 | 目标 | 实测 |
| --- | --- | --- | --- |
| 公开注册 | `curl -X POST /api/auth/register` | 404（无路由） | |
| 管理员创建用户 | 管理员 token 建 `alice` → `alice` 登录 | 201 + 可登录 | |
| 非管理员拒绝 | 普通用户 token 调 `/api/admin/users` | 403 | |
| 未登录拒绝 | 无 token 调 `/api/admin/users` | 401 | |
| 迁移无损 | 旧库启动后 `PRAGMA table_info(users)` / PG `\d users` | 含 `is_admin` 默认 False | |
| 管理员幂等 | 重复启动两次 | 不重复建、密码不变 | |
| CLI 加用户 | `python -m app.cli create-user --username bob --password x --admin` | 成功；重复报错 | |
| 单元测试覆盖率 | `pytest --cov=app` | ≥ 70% | |
| 回归 | M1~M4 功能集 | 全部通过 | |

## 5. 判定规则

- 「公开注册关闭 且 管理员加用户可用 且 鉴权隔离通过 且 迁移无损 且 管理员/CLI 通道就绪 且 回归通过 + 覆盖率 ≥ 70%」→ 本变更通过，docs 回填「已落地」。
- 任一指标不达标 → 定位到对应任务组补齐（数据模型 → TG-0、管理员引导/鉴权 → TG-1、管理接口/审计 → TG-2、CLI → TG-3、前端/测试/文档 → TG-4），回归验证直至达标。
- `AUTH_ENABLED=false`（本地开发/测试）时 `require_admin` 按 requirements.md §5 口径放行 —— 该放行仅限本地，生产 `AUTH_ENABLED=true` 必须严格校验；验收以生产口径（`AUTH_ENABLED=true`）为准。
- 管理员创建用户走与注册同源的 bcrypt 哈希（`auth.hash_password`），确保登录校验一致；禁止出现明文/弱哈希。
