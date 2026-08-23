# 会议纪要助手 · 项目文档

> **Meeting Minutes Assistant** —— 会议视频 → 语音 → 文字 → 结构化会议纪要

本目录按 **SDD（软件设计文档）规范** 拆分，是项目的权威规划与设计来源。各文档职责单一、互相引用。

## 文档导航

| 文档 | 说明 | 状态 |
| --- | --- | --- |
| [mission.md](mission.md) | 项目使命与章程（愿景、目标、范围、干系人、KPI） | 🏗️ 草案 |
| [roadmap.md](roadmap.md) | 路线图与里程碑（M0→M4） | 🏗️ 草案 |
| [tech-stack.md](tech-stack.md) | 技术栈与选型（含对比与建议） | 🏗️ 草案 |
| [requirements.md](requirements.md) | 需求分析（功能 FR + 非功能 NFR） | 🏗️ 草案 |
| [architecture.md](architecture.md) | 总体架构（架构图、数据流、模块、部署） | 🏗️ 草案 |
| [technical-solution.md](technical-solution.md) | 关键技术方案（视频→语音→文字→纪要链路） | 🏗️ 草案 |
| [data-model.md](data-model.md) | 数据与接口设计（数据模型、ER、API） | 🏗️ 草案 |
| [testing.md](testing.md) | 测试策略 | 🏗️ 草案 |
| [deployment.md](deployment.md) | 部署与运维（CI/CD、容器、可观测） | 🏗️ 草案 |
| [risks.md](risks.md) | 风险与应对 | 🏗️ 草案 |
| [open-questions.md](open-questions.md) | 待确认项（Open Questions） | 🏗️ 草案 |

## 推荐阅读顺序

1. 先读 [mission.md](mission.md) 了解"做什么、为什么做、边界在哪"。
2. 再读 [roadmap.md](roadmap.md) 了解"分几步走"。
3. 技术侧读 [tech-stack.md](tech-stack.md) → [architecture.md](architecture.md) → [technical-solution.md](technical-solution.md)。
4. 落地侧读 [requirements.md](requirements.md) → [data-model.md](data-model.md) → [testing.md](testing.md) → [deployment.md](deployment.md)。

## 文档约定

| 标记 | 含义 |
| --- | --- |
| ✅【已定】 | 已拍板的决策 / 约束 |
| 🔶【建议】 | 技术选型候选方案，待验证 |
| ❓【待确认】 | 需业务侧补充确认 |

> 版本统一为 **v0.1（草案）**，随各文档独立演进。
