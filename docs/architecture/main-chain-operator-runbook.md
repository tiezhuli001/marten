# Main Chain Operator Runbook

> 更新时间：2026-03-23
> 文档角色：主链运行与人工接手说明
> 目标：让 operator 能基于当前 runtime truth 判断主链是否可跑、卡在哪一层、以及该如何 resume / handoff / 人工接管。

## 1. 适用范围

本 runbook 只覆盖当前主链：

`gateway -> canonical session -> main-agent -> control task -> ralph -> review -> delivery`

它不讨论 Milvus / RAG，也不讨论未来扩展式多链编排。

## 2. 先看什么

进入任何故障或验收前，按这个顺序看：

1. `GET /health`
2. `GET /diagnostics/integrations`
3. `GET /control/tasks/{task_id}`
4. `GET /control/tasks/{task_id}/events`
5. `GET /tasks/sleep-coding/{task_id}`
6. `GET /reviews/{review_id}`（如果已经进入 review）

规则：

- `/health` 只回答进程是否活着，不回答主链是否可跑。
- `/diagnostics/integrations` 是 live readiness 的统一事实源。
- `control task` 是 operator 的状态真相入口。
- `sleep_coding task` 和 `review` 只用于看 domain 细节，不取代 control 面判断。

## 3. 如何判断当前是否可以跑 live chain

看 `/diagnostics/integrations` 中的 `main_chain`：

- `ready`: 主链核心可运行性
- `live_ready`: live chain 当前是否可安全执行
- `blocking_components`: 阻断主链的组件
- `live_blocking_components`: 阻断 live 验收的组件
- `next_action`: 当前最先要修的项
- `acceptance_summary`: 给 operator 的验收摘要
- `operator_hint`: 当前优先排查提示

再看各组件项：

- `ready`
- `severity`
- `required_for_live_chain`
- `live_ready`
- `next_action`

解释规则：

- `severity=blocking`：会阻断主链
- `severity=degraded`：主链可继续，但该组件存在降级
- `delivery_status=degraded`：任务可能已完成，但消息投递没有真实送达

## 4. Control Task 字段怎么读

重点字段：

- `status`
- `payload.final_evidence`
- `payload.terminal_evidence`
- `payload.latest_review_status`
- `payload.review_round`
- `payload.delivery_status`
- `payload.delivery_delivered`
- `payload.background_follow_up_status`
- `payload.last_error`

终态解释：

- `completed`
  - 代码链路已完成，且 final delivery gate 已通过
  - 不代表消息一定真实送达，仍需看 `delivery_status`
- `failed`
  - 当前链路在确定性边界失败，例如 validation failed
  - 优先看 `terminal_evidence.last_error` 和 validation 状态
- `needs_attention`
  - 需要人工接手
  - 常见原因是 review 多轮阻塞、follow-up failure、外部依赖异常

## 5. 几个常见场景怎么判断

### 场景 A：主链 blocked，不能跑 live

看：

- `/diagnostics/integrations.main_chain.live_ready = false`
- `/diagnostics/integrations.main_chain.live_blocking_components`
- `/diagnostics/integrations.main_chain.next_action`

处理：

- 先修 `next_action` 指向的 blocking component
- 不要直接用人工绕过 gate 去跑 live chain

### 场景 B：task `failed`

看：

- `payload.terminal_evidence.validation_status`
- `payload.terminal_evidence.last_error`
- domain task 的 `validation` payload

处理：

- 这是确定性失败，不应伪装成 `needs_attention`
- 优先修验证或执行前置，不要强行推进到 review/delivery

### 场景 C：task `needs_attention`

看：

- `payload.review_round`
- `payload.review_summary`
- `payload.repair_strategy`
- `/control/tasks/{task_id}/events`

处理：

- 如果是 review 三轮阻塞，按 repair context 人工接手
- 如果是 `follow_up.failed`，优先看根因事件，而不是只看终态

### 场景 D：task `completed`，但 delivery degraded

看：

- `payload.delivery_status`
- `payload.delivery_delivered`
- `payload.final_evidence`

处理：

- 代码链路完成，不要误报为失败
- 这是 delivery 通道问题，不是 coding/review 问题
- 若需要人工通知，用现有 final evidence 补发，不要重跑 coding loop

## 6. Resume / Handoff 原则

### Ralph resume

Ralph 现在应从 persisted facts 恢复，不应重新推导整条链。重点看：

- plan 是否已存在
- validation 是否已存在
- PR / review handoff 是否已存在
- `changes_requested` 是否已有 persisted repair context

### Review re-entry

如果已经发生过 review：

- 先读 `latest_review_status`
- 再读 `review_round`
- 再读 `review_summary` / `repair_strategy`

不要只根据“任务现在像不像 in_review”来猜下一步。

### Manual handoff

当状态是 `needs_attention`：

- 先查 control events
- 再查 terminal evidence
- 再决定是 resume 还是人工接管

默认不要手动 patch control 状态去“伪恢复”。

## 7. Failure Drill Baseline

当前建议固定演练这 3 类：

1. validation failure
2. review blocking round exhaustion
3. approved-but-delivery-degraded

演练目标不是看提示词写得多漂亮，而是确认：

- control task 状态是否说真话
- terminal evidence 是否完整
- diagnostics 是否给出一致结论
- operator 是否能知道下一步看哪里

## 8. 什么时候说明方向偏了

如果为了解决不稳定问题，开始出现下面现象，默认视为偏离：

- 为了“让 agent 稳定”不断新增流程 if/else
- 用状态机替代 review / repair 推理
- live readiness 和实际执行前置出现两套真相
- delivery degraded 被误报成 coding failed

这条 runbook 的前提仍然是：

`LLM + MCP + skill first`，控制面只收 deterministic gate、状态投影和 operator evidence。
