# 上传进度实时反馈（已上传 xx% + 速度 + 剩余时间）— 需求 (Requirements)

| 文档类型 | 需求说明 |
| --- | --- |
| 阶段 | 需求变更 · 上传进度实时反馈 |
| 分支 | feat/upload-progress |
| 关联文档 | [plan.md](plan.md) · [validation.md](validation.md) · [roadmap.md](../../docs/roadmap.md) |

## 1. 背景与目标

M1 前端为「极简上传页」（roadmap M1 §🛠「前端：极简 HTML/JS 上传页 + 进度条（先跑通，不追求美观）」）。现有进度条仅反映**任务处理进度**（上传完成返回 202 后，前端轮询 `/api/tasks/{id}` 按状态机更新），上传阶段进度条恒为 0%、状态仅「上传中…」。大文件上传耗时较长且无反馈，用户体感「没反应」。

目标：上传阶段提供**实时上传进度**「已上传 xx% + 实时速度(MB/s) + 剩余时间」，上传完成无缝切换到既有处理进度。纯前端改造，后端零改动。

## 2. 范围

### In Scope
- 上传阶段实时进度：百分比、实时速度（MB/s / KB/s）、剩余时间（x分x秒）。
- 上传完成 → 处理阶段的无缝衔接（状态文字「上传完成，排队处理中…」→ 轮询处理进度）。
- 上传失败 / 网络中断 / 取消的明确错误提示，失败后进度条不残留。
- 进度回调 100ms 节流（避免高频 DOM 重绘）。

### Out of Scope
- **断点续传 / 分片上传**（用户已确认选 XHR onprogress，不做分片）。
- 后端任何改动（`POST /api/tasks` 接口、存储、队列、鉴权均不变）。
- 拖拽上传、多文件/批量上传、上传取消按钮（`onabort` 仅兜底浏览器主动中止）。
- 处理阶段进度展示改造（维持现有轮询逻辑）。

## 3. 决策映射

| 决策点 | 结论 | 依据 |
| --- | --- | --- |
| 实现方案 | **XHR `upload.onprogress`**（前端单点改造，后端零改动，标准做法，无断点续传） | 用户 2026-08-28 咨询确认（备选：分片上传，被否） |
| 展示粒度 | **「已上传 xx%」+ 实时速度(MB/s) + 剩余时间** | 用户 2026-08-28 咨询确认（备选：仅百分比，被否） |
| 是否引入新选型/里程碑 | 否，登记为**需求变更**（复用 M3 前端与鉴权体系，不新增 G/FR） | 同「账号注册管控」变更口径 |

## 4. 约束与上下文

- **鉴权不回归**：上传请求仍须携带 `Authorization: Bearer <JWT>`；401 仍须触发登出跳转（与 `apiFetch` 一致）。改 XHR 后此行为由 `uploadFile` 显式实现。
- **后端零改动**：`POST /api/tasks`（`app/main.py` `create_task`）不动；仅替换前端传输层（`fetch` → `XHR`），请求仍是 `multipart/form-data` 单字段 `file`。
- **兼容**：`xhr.upload.onprogress` 的 `e.total` 含 multipart 边界开销（数百字节），对真实音视频可忽略；`lengthComputable=false`（极端）时静默降级为「上传中…」不崩。
- **衔接**：上传阶段进度条 0→100%；处理阶段沿用轮询，进度条重新映射为任务进度 0→100%，状态文字由「已上传…」切到「排队中/处理中…」。
- **前端技术栈不变**：仍是纯 HTML + 原生 JS（无构建、无框架），新增函数放 `static/auth.js`（与 `apiFetch`/`downloadFile` 并列）与 `static/index.html` 内联脚本。

## 5. 影响面

- 改动文件：`static/auth.js`（新增 `uploadFile`）、`static/index.html`（改 `upload()` + 新增 `fmtSpeed`/`fmtDur`）。
- 不影响：后端、`static/login.html`、`static/minute.html`、`app/` 任何模块、测试（纯前端）。
- 文档回填：`docs/roadmap.md` 底部变更记录、`CHANGELOG.md`。`docs/tech-stack.md` 无选型变化，不涉及回填（M1 前端栈已锁定）。
