# MVP Evolution

> 更新时间：2026-03-22
> 用途：只保留当前仍有效的演进方向，不重复描述当前架构现状或最终实现计划。

## 文档边界

这份文档不再负责解释：

- 当前架构长什么样
- 当前主链已经收口到什么程度
- 当前阶段验证通过了哪些实现事实
- 某一轮 cleanup 的分批执行计划

这些内容请分别看：

- [current-mvp-status-summary.md](../architecture/current-mvp-status-summary.md)
- [mvp-agent-platform-core.md](../architecture/mvp-agent-platform-core.md)
- [agent-system-overview.md](../architecture/agent-system-overview.md)
- [agent-runtime-contracts.md](../architecture/agent-runtime-contracts.md)
- [rag-provider-surface.md](../architecture/rag-provider-surface.md)
- [agent-system-rollout-plan.md](agent-system-rollout-plan.md)
- [rag-provider-rollout-plan.md](rag-provider-rollout-plan.md)
- `docs/archive/`

这份文档只回答一个问题：

在当前主链已经稳定、且框架分层设计已经完成之后，后续还应该坚持哪些演进方向？

## 演进方向没有变化

后续演进仍然应该围绕一个目标：

> 继续做减法，让 `Marten` 更像一个小而硬的 agent platform core，而不是重新长回大而散的自动化平台。

判断某项工作是否值得推进，优先看它是否强化下面这些方向：

- 是否继续减少 Python orchestration
- 是否继续减少并列真相源和历史兼容层
- 是否继续减少中间态文档和阶段性计划副本
- 是否继续让 agent 通过 prompt / workspace docs / MCP / skill 发挥能力
- 是否继续保护 `gateway -> main-agent -> ralph -> review -> delivery` 这条主链不被稀释

## 必须保留的复杂度

下面这些复杂度仍然是合理且必要的：

- `task / session / event` 控制面
- GitHub / GitLab / Feishu / MCP 集成边界
- worker 调度、幂等、重试、记账
- `review / delivery` 闭环的真实状态写回

## 应继续删除或压缩的复杂度

下面这些仍然应该被持续审查和压缩：

- agent 内部重复的 writeback / notification / formatting
- 只为兼容旧路径存在的 `services/*`
- 工程代码里对 agent 输出做过度兜底
- 历史阶段性需求分析、计划文档、部署草稿

## 当前语境下的演进重点

1. 继续坚持 `prompt + MCP + skill + config` 优先，不把能力过早下沉成工程分支
2. 继续收紧官方内置 agent 的稳定边界，而不是复制实现
3. 继续让多入口、路由、RAG 都保持最小必要工程面
4. 持续审查 `app/services/*`、兼容层和重复编排逻辑
5. 保持公开文档树只表达事实、边界和执行计划，不回到阶段性草稿堆积

## 文档策略

当前仓库文档只保留：

- 架构：长期有效的系统边界和状态模型
- 演进：当前仍有效的收敛方向
- 状态：当前真实实现、当前阶段结论和关键实现对照

以下内容不再保留在主分支：

- 阶段性 requirements 分析
- 临时 execution plan
- 中间产物 review 归档
- 一次性的部署草稿
- 仅面向在地 agent 的 handoff / 临时推演文档
- agent 目录说明这类低信息密度文档

## 当前结论

这份文档现在只承担“长期方向约束”的角色。

如果目标是进入实现，不应再从这里反推任务拆分，而应直接执行：

- [agent-system-rollout-plan.md](agent-system-rollout-plan.md)
- [rag-provider-rollout-plan.md](rag-provider-rollout-plan.md)

上一轮已经完成使命的设计与计划文档已迁入 `docs/archive/`，避免历史推演继续与当前入口混用。
