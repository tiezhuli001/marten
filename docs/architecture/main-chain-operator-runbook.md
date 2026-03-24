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
3. `GET /control/operator/state`
4. `GET /control/tasks/{task_id}`
5. `GET /control/tasks/{task_id}/events`
6. `GET /tasks/sleep-coding/{task_id}`
7. `GET /reviews/{review_id}`（如果已经进入 review）

规则：

- `/health` 只回答进程是否活着，不回答主链是否可跑。
- `/diagnostics/integrations` 是 live readiness 的统一事实源。
- `/control/operator/state` 是单任务运行态、排队态和最近失败项的聚合入口。
- `control task` 是 operator 的状态真相入口。
- `sleep_coding task` 和 `review` 只用于看 domain 细节，不取代 control 面判断。

## 2.1 私有服务器自用阶段的运行约束

当前第一阶段按“单租户、单用户、单任务执行槽”运行：

- `Feishu` 是默认入口
- `Web/API` 是诊断、运维和备用入口
- 同一时刻只允许一个 active 主任务
- 新请求要么进入队列，要么收到明确 busy 语义

operator 在日常值守时，应优先确认：

1. 当前 active task 是谁
2. 是否还有 queued task 等待进入主链
3. 最近失败或 `needs_attention` 的任务是哪一个

不要把多个主任务并发跑起来做验收；这不属于当前阶段支持范围。

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

对 `feishu` 组件，额外看：

- `inbound_status`
- `delivery_status`

对 `self_host_boot`，额外看：

- `ready`
- `process_model`
- `api_process`
- `worker_process`
- `embedded_scheduler`
- `next_action`

解释规则：

- `severity=blocking`：会阻断主链
- `severity=degraded`：主链可继续，但该组件存在降级
- `delivery_status=degraded`：任务可能已完成，但消息投递没有真实送达
- `self_host_boot.process_model=split_process`：API 和 scheduler/worker 必须分进程拉起
- `self_host_boot.embedded_scheduler=false`：`app.main` 进程不应再偷偷启动 worker loop

额外规则：

- builtin `ralph` coding capability 缺失：按 `blocking` 处理
- builtin `code-review-agent` review capability 缺失：按 `blocking` 处理
- review runtime failure 不是 degraded success，而是主链失败或 `needs_attention`

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
- `payload.queue_status`（若当前实现已投影）
- `payload.active_task_id` / `payload.queued_task_ids`（若当前实现已投影）

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
- 如果失败原因是 builtin coding/review/runtime capability 缺失，先恢复 runtime 能力，不要试图用宽松 fallback 继续推进

### 场景 C：task `needs_attention`

看：

- `payload.review_round`
- `payload.review_summary`
- `payload.repair_strategy`
- `/control/tasks/{task_id}/events`

处理：

- 如果是 review 三轮阻塞，按 repair context 人工接手
- 如果是 `follow_up.failed`，优先看根因事件，而不是只看终态
- 如果是 runtime/context/structured-output 失败，优先确认 builtin agent 是否还能构造真实 coding/review truth

### 场景 D：task `completed`，但 delivery degraded

看：

- `payload.delivery_status`
- `payload.delivery_delivered`
- `payload.final_evidence`

处理：

- 代码链路完成，不要误报为失败
- 这是 delivery 通道问题，不是 coding/review 问题
- 若需要人工通知，用现有 final evidence 补发，不要重跑 coding loop

### 场景 E：系统忙碌或存在排队任务

看：

- 当前 active task 的 `status`
- `/control/tasks/{task_id}` 是否已投影 queue / busy truth
- `/control/tasks/{task_id}/events` 是否记录 queued / resumed / claimed

处理：

- 第二个请求不应静默丢失
- 若系统返回 busy/queued，先确认它是否被如实记录
- 若需要人工恢复，优先 resume queued task，而不是手工重建 issue

### 场景 F：Feishu 看起来能收消息，但主入口行为不稳定

看：

- `/diagnostics/integrations.feishu.inbound_status`
- `/diagnostics/integrations.feishu.delivery_status`
- 同一 `chat_id` 下连续两条请求是否复用了同一 session
- control task 的 `payload.source_endpoint_id` / `payload.delivery_endpoint_id`

处理：

- 若 `inbound_status != ready`，先修 webhook 凭据或签名配置
- 若 `delivery_status != ready`，先修 channel webhook，再判断是否只是 delivery degraded
- 若同一 chat 的状态查询和 coding 请求落在不同 endpoint，先修 endpoint external ref 绑定，不要直接怀疑 agent 推理

## 6. Resume / Handoff 原则

### Ralph resume

Ralph 现在应从 persisted facts 恢复，不应重新推导整条链。重点看：

- plan 是否已存在
- validation 是否已存在
- PR / review handoff 是否已存在
- `changes_requested` 是否已有 persisted repair context

前提：

- resume 依赖 builtin Ralph runtime 仍然可用
- 若 builtin runtime 不可用，应显式停止，不做“伪恢复”

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
- 为了“支持更多入口”把 `API` 做成第二套业务编排面
- 为了“看起来能并发”提前引入复杂调度器和多执行槽

这条 runbook 的前提仍然是：

`LLM + MCP + skill first`，控制面只收 deterministic gate、状态投影和 operator evidence。

补充前提：

- builtin `ralph` 和 builtin `code-review-agent` 是标准主链执行 owner
- 外部 command 不应作为默认成功路径掩盖 coding/review runtime 缺口
