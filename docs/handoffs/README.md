# Handoffs

本目录只定义 `Marten` 当前正式 handoff 规则与模板。

目标只有一个：

> 任何 agent 接手任务时，不需要额外口头上下文，也不需要回忆“上一轮是怎么聊出来的”。

边界约束：

- `docs/handoffs/` 只放规则文档和模板
- 具体 handoff / 交接草稿 / 会话交接记录，统一放到 `docs/internal/`
- `docs/internal/` 只用于本地开发，不提交远程仓库
- 如果某份 handoff 里的内容需要长期保留，必须提炼到 `docs/architecture/`、`docs/evolution/`、`docs/plans/` 或 `STATUS.md`，而不是继续把具体 handoff 当公开真相文档

## 一、什么时候必须写 handoff

下面这些情况必须有 handoff：

- `main-agent` 交给 `ralph`
- `ralph` 交给 `code-review-agent`
- `code-review-agent` 把 blocking finding 交回 `ralph`
- 人工或新 agent 接手未完成任务
- 任务跨 session、跨轮次、跨工作区继续

## 二、handoff 的最小字段

每份 handoff 至少包含：

- `Goal`
- `Current State`
- `Source Of Truth`
- `Completed`
- `In Progress`
- `Next Step`
- `Acceptance / Validation`
- `Risks / Blockers`
- `Immediate First Action`

## 三、source of truth 规则

handoff 中必须明确列出当前真相来源，至少包括：

- 当前 architecture 文档
- 当前 relevant plan
- 受影响 repo / workspace
- 当前 task / issue / PR / review run

禁止只写“见上文”或“按之前讨论继续”。

## 四、handoff 的质量标准

合格 handoff 必须满足：

1. 下一个 agent 能在 5 分钟内知道现在做到哪里
2. 下一个 agent 能在 10 分钟内开始第一步执行
3. 不依赖隐藏上下文
4. 不混入已经过期的历史设计
5. 明确当前计划，而不是模糊建议

## 五、与 plan 的关系

handoff 不是 plan 的替代。

规则如下：

- architecture 文档定义稳定边界
- plan 定义执行拆分
- handoff 记录“这一次具体做到哪一步”

任何 agent 继续工作时，至少要同时读：

- relevant architecture doc
- `agent-first-implementation-principles.md`
- relevant plan
- local latest handoff（若存在，位于 `docs/internal/`）

## 六、模板

统一模板见：

- [templates/agent-handoff-template.md](templates/agent-handoff-template.md)

## 七、当前本地 handoff 约定

具体 handoff 一律放在本地目录：

- `docs/internal/handoffs/`

建议命名：

- `YYYY-MM-DD-<topic>-handoff.md`

接手时优先读取该目录中与当前任务最相关、日期最新的 handoff。

## 八、推荐阅读顺序

推荐给下一位 agent 的最小阅读顺序：

1. `docs/architecture/agent-first-implementation-principles.md`
2. `docs/architecture/agent-system-overview.md`
3. `docs/architecture/agent-runtime-contracts.md`
4. `docs/internal/handoffs/` 下当前任务相关的 latest handoff（若存在）
5. 当前 continuity / status 文档
