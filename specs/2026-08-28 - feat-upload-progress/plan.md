# 上传进度实时反馈（已上传 xx% + 速度 + 剩余时间）— 执行计划 (Plan)

| 文档类型 | 执行计划 |
| --- | --- |
| 阶段 | 需求变更 · 上传进度实时反馈 |
| 分支 | feat/upload-progress |
| 关联文档 | [roadmap.md](../../docs/roadmap.md) · [mission.md](../../docs/mission.md) · [tech-stack.md](../../docs/tech-stack.md) |

> 本文把「上传大文件时展示『已上传 xx% + 实时速度 + 剩余时间』」这一需求变更组织为可执行的**任务组**。M1 前端是「极简上传页，先跑通不追求美观」，进度条只做了**任务处理进度**（上传完成后轮询 `/api/tasks/{id}`），上传阶段进度条一直停在 0%、状态文字只有「上传中…」，大文件上传时无反馈、看起来像卡死。本变更**仅前端单点改造**（`fetch` 换 `XMLHttpRequest`，用 `xhr.upload.onprogress` 拿真实字节进度），**后端零改动**（`POST /api/tasks` 接口、存储、队列、鉴权均不变），不引入新选型、不新增产品目标（G）或需求组（FR），故登记为**需求变更**而非新里程碑。两项关键决策已由用户 2026-08-28 咨询确认（见 requirements.md §4）。

## 任务组总览

| 任务组 | 内容 | 产出 | 依赖 |
| --- | --- | --- | --- |
| TG-0 | 上传改 XHR + 进度采集 | `auth.js` 新增 `uploadFile`（XHR，带鉴权头/401/错误处理 + `upload.onprogress` 回调）；`index.html` 的 `upload()` 改用 `uploadFile` | — |
| TG-1 | 进度展示 + 测试 + 收口 | 百分比/速度/剩余时间格式化与节流、上传→处理阶段衔接、错误提示；JS 语法校验 + 浏览器冒烟验证；CHANGELOG + roadmap 变更记录 + 部署 | TG-0 |

## 任务组明细

### TG-0 · 上传改 XHR + 进度采集
- **目标**：用 `XMLHttpRequest` 替换 `fetch` 上传，采集 `xhr.upload.onprogress` 的真实字节进度（`fetch` 无上传进度能力，这是该需求的唯一技术手段）。
- **任务项**：
  - `static/auth.js` 新增 `window.uploadFile(url, file, onProgress)`：`Promise` 包装 XHR；`xhr.open('POST', url)`；带 `Authorization: Bearer <token>`（`getToken()`）；`xhr.upload.onprogress` 在 `e.lengthComputable` 时回调 `onProgress(e.loaded, e.total)`；`onload` 解析 JSON 并 `resolve({status, ok, data})`，401 时 `logout()` 并 `reject`（与 `apiFetch` 语义一致）；`onerror`/`onabort` 分别 `reject` 网络错误/取消。
  - `static/index.html` 的 `upload()` 改用 `await uploadFile('/api/tasks', file, onProgress)`，去掉原 `FormData` + `apiFetch` 写法。
- **产出**：`static/auth.js` + `static/index.html`。
- **验收**：上传请求仍携带 Bearer token（鉴权不回归）；401 仍触发登出跳转；进度回调收到 `loaded/total`；后端 `POST /api/tasks` 无任何改动；M1~M4 后端测试不受影响（纯前端改动）。

### TG-1 · 进度展示 + 测试 + 收口
- **目标**：把采集到的字节进度渲染为「已上传 xx%（xx MB/s，剩余 x分x秒）」，上传完成无缝衔接既有处理阶段，失败有明确提示；并完成验证与文档收口。
- **任务项**：
  - `index.html` 新增 `fmtSpeed(bps)`（B/s → KB/s / MB/s）与 `fmtDur(sec)`（秒 → x分x秒）格式化函数。
  - 进度回调内做 **100ms 节流**（避免高频重绘），计算 `pct = loaded/total`、`speed = loaded/elapsed`、`eta = (total-loaded)/speed`，更新进度条宽度与状态文字「已上传 xx%（速度，剩余时间）」。
  - 上传完成（202）后置「上传完成，排队处理中…」状态，再进入 `poll(data.id)`（处理阶段仍用原轮询进度，二者无缝衔接）。
  - 非 2xx：`setStatus('上传失败：' + (data.detail || status), 'err')` 并隐藏进度条；`onerror`/`onabort` 明确提示「网络错误，上传中断」/「上传已取消」。
  - 验证：`node --check` 校验 `auth.js` 与 `index.html` 内联脚本语法；浏览器冒烟（页面加载、上传函数存在、无控制台报错）；生产部署后用真实文件回归。
  - 收口：`CHANGELOG.md` 登记（两次提交模式）；`docs/roadmap.md` 底部变更记录补「已落地」条目。
- **产出**：完整前端改动 + 验证结果 + CHANGELOG + roadmap 变更记录。
- **验收**：大文件上传时进度条与状态文字实时更新（含速度/剩余时间）；小文件快速上传不报错；上传失败/中断有明确提示且进度条不残留 0%；生产环境实测通过；CHANGELOG 与 roadmap 已登记。

## 依赖关系

```
TG-0 ──► TG-1
```

> TG-0（XHR 进度采集）是 TG-1（展示与收口）的前置；两任务组均纯前端，可在一个改动内连续完成。无后端改动、无跨服务依赖，故不设并行组。
