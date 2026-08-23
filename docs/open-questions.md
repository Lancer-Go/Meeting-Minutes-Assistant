# 待确认项 (Open Questions)

| 文档类型 | 待确认项 |
| --- | --- |
| 版本 / 状态 | v0.1（草案）🏗️ |
| 关联文档 | [mission](mission.md) · [risks](risks.md) · [tech-stack](tech-stack.md) |

以下决策点需业务侧补充确认，直接影响架构与选型：

1. ❓ 首期形态：本地单机优先，还是云端 SaaS 优先？（影响架构与选型）
2. ❓ ASR 选型：是否接受数据出域走云 API，还是必须本地/私有化？
3. ❓ 主要会议语言：中文为主是否确认？是否需要英文/多语？
4. ❓ 会议时长与文件大小上限？
5. ❓ 利润与成本预算范围？（决定云端模型预算）
6. ❓ 是否需要与已有 IM / 待办系统集成（飞书 / 钉钉 / 企业微信）？
7. ❓ 输出格式除 Markdown，是否必须 PDF / docx / 邮件？

## 附录 (Appendix)

- 相关文档：`IDEA.md`（项目最初想法）、`README.md`（项目简介）。
- 参考工具：FFmpeg、Whisper/faster-whisper、FunASR、pyannote、DeepSeek/Qwen/GPT、Pandoc。
- 后续待补充：技术栈锁定后的详细组件设计、API 详规、数据库 DDL、Eval 集。

---

> 📌 **下一步建议**：优先完成 M0 概念验证 —— 用一份真实的会议录音跑通「FFmpeg + Whisper + LLM 纪要」最小闭环，验证准确率与成本，再据此锁定技术选型。
