# Handoffs

本目录定义 `Marten` 当前正式 handoff 规则。

目标只有一个：

> 任何 agent 接手任务时，不需要额外口头上下文，也不需要回忆“上一轮是怎么聊出来的”。

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
- relevant plan
- latest handoff

## 六、模板

统一模板见：

- [templates/agent-handoff-template.md](templates/agent-handoff-template.md)

## 七、当前最新 handoff

当前继续执行 RAG / provider 工作时，优先读取：

- [2026-03-23-rag-provider-runtime-handoff.md](2026-03-23-rag-provider-runtime-handoff.md)
