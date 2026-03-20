# MVP Platform Core Execution Plan

> 更新时间：2026-03-20
> 适用分支：`codex/mvp-slimming-checklist`
> 目标：按 [mvp-agent-platform-core.md](/Users/litiezhu/workspace/github/marten/docs/architecture/mvp-agent-platform-core.md) 的收口方向，把当前仓库继续压回一个小而硬的 MVP agent platform core，同时不破坏已验证主链。

## 一、执行原则

这份计划只服务当前 MVP 主链：

`Feishu/Webhook -> main-agent -> task handoff -> ralph -> code-review-agent -> final delivery`

本轮判断标准只有 4 条：

1. 是否继续收口 `control` 为唯一主链控制面。
2. 是否把 `main-agent / ralph / code-review-agent` 统一挂到更清晰的最小 contract 上。
3. 是否把 session / handoff / review repair loop 的状态真相收回到 `control`。
4. 是否在不破坏现有测试与 live chain 的前提下做减法。

明确不做：

- 不做用户自定义 agent 装载。
- 不做多仓库 Ralph 调度系统。
- 不做多 reviewer 平台对象。
- 不做长期记忆 / RAG 平台。
- 不做新的抽象层来“包装抽象”。

## 二、现状判断

当前分支已经完成一轮低风险瘦身：

- `app/services/` 主编排层已被移除。
- `app/control/automation.py`、`app/control/session_registry.py`、`app/control/task_registry.py` 已进入控制面。
- `app/infra/observability.py` 已迁到更合理位置。
- `app/graph/`、`SOUL.md`、部分 review 泛化能力已被删减。
- 测试已通过一次完整回归：
  - `python -m unittest discover -s tests -v`
  - 历史结果：`119 tests, OK`

因此本轮执行重点不再是“继续大删目录”，而是把主链 contract 和 control state 再收紧一层。

## 三、执行分期

建议按 4 个阶段推进，每个阶段都必须可独立验证和提交。

### Phase 1：收口平台最小对象

目标：

- 让当前代码显式体现 `agent registry / route resolver / session manager` 这 3 个最小平台对象。
- 避免总入口路由逻辑继续散落在 `channel`、`gateway`、agent 应用层之间。

改动范围：

- [app/control/gateway.py](/Users/litiezhu/workspace/github/marten/app/control/gateway.py)
- [app/control/session_registry.py](/Users/litiezhu/workspace/github/marten/app/control/session_registry.py)
- [app/control/task_registry.py](/Users/litiezhu/workspace/github/marten/app/control/task_registry.py)
- [app/channel/feishu.py](/Users/litiezhu/workspace/github/marten/app/channel/feishu.py)
- [app/api/routes.py](/Users/litiezhu/workspace/github/marten/app/api/routes.py)

动作：

1. 明确 `main-agent` 是默认入口，`ralph` 是唯一用户可点名的 task agent。
2. 把“文本点名 -> 默认总入口 -> LLM 意图识别”收口到同一处 route 解析路径。
3. 明确 `code-review-agent` 不属于用户直达入口。
4. 确认 `channel` 只做协议转换，不再继续驱动 workflow 分支。

完成标准：

- 用户入口的 agent 选择逻辑只在一条 control 路径上出现。
- `code-review-agent` 不再通过用户入口被直接路由。
- `channel` 不再包含主链编排判断。

验证：

- `python -m unittest tests.test_gateway`
- `python -m unittest tests.test_feishu`
- `python -m unittest tests.test_main_agent`

### Phase 2：补齐主链 handoff contract

目标：

- 让 `main-agent -> ralph -> code-review-agent` 的交接从“隐含约定”变成“control 持有的最小 contract”。

改动范围：

- [app/control/automation.py](/Users/litiezhu/workspace/github/marten/app/control/automation.py)
- [app/control/task_registry.py](/Users/litiezhu/workspace/github/marten/app/control/task_registry.py)
- [app/agents/main_agent/application.py](/Users/litiezhu/workspace/github/marten/app/agents/main_agent/application.py)
- [app/agents/ralph/application.py](/Users/litiezhu/workspace/github/marten/app/agents/ralph/application.py)
- [app/agents/code_review_agent/application.py](/Users/litiezhu/workspace/github/marten/app/agents/code_review_agent/application.py)
- [app/models/](/Users/litiezhu/workspace/github/marten/app/models)

动作：

1. 显式定义 task handoff payload：
   - `task_id`
   - `session_id`
   - `owner_agent`
   - `source`
   - `repo/workspace`
   - `issue/requirement`
   - `acceptance`
   - `status`
2. 显式定义 review handoff payload：
   - `task_id`
   - `session_id`
   - `owner_agent`
   - `source`
   - `workspace_ref`
   - `validation_result`
   - `review_scope`
   - `status`
3. 让 `control` 成为唯一主状态真相源。
4. 让 `ralph` 和 `code-review-agent` 只提交阶段结果，不直接接管主状态机。

完成标准：

- 主链 agent 之间的交接数据可在代码和测试里直接识别。
- `control_tasks` 是唯一主状态机。
- review/coding 子系统不再并列持有决策级主状态。

验证：

- `python -m unittest tests.test_sleep_coding`
- `python -m unittest tests.test_review`
- `python -m unittest tests.test_automation`
- `python -m unittest tests.test_mvp_e2e`

### Phase 3：拆开用户会话归属与内部任务 owner

目标：

- 避免 `code-review-agent` 这种内部阶段 agent 污染用户会话归属。
- 保持总入口上下文短，agent 上下文独立。

改动范围：

- [app/control/context.py](/Users/litiezhu/workspace/github/marten/app/control/context.py)
- [app/control/session_registry.py](/Users/litiezhu/workspace/github/marten/app/control/session_registry.py)
- [app/agents/main_agent/application.py](/Users/litiezhu/workspace/github/marten/app/agents/main_agent/application.py)
- [app/agents/ralph/application.py](/Users/litiezhu/workspace/github/marten/app/agents/ralph/application.py)
- [app/agents/code_review_agent/application.py](/Users/litiezhu/workspace/github/marten/app/agents/code_review_agent/application.py)

动作：

1. 把 `session.active_agent` 与 `task.owner_agent` 明确分开。
2. 用户消息继续归属于 `main-agent` 或用户当前显式交互 agent。
3. `ralph`、`code-review-agent` 只作为内部任务阶段 owner，不直接接管用户对话入口。
4. 保证 review repair loop 回到 `ralph` 时，不会污染用户主会话归属。

完成标准：

- 用户会话层和内部任务层对象分离。
- `code-review-agent` 不会成为用户消息的默认会话 owner。
- repair loop 可以在不改变用户会话归属的前提下闭环。

验证：

- `python -m unittest tests.test_control_context`
- `python -m unittest tests.test_session_registry`
- `python -m unittest tests.test_mvp_e2e`
- `python -m unittest tests.test_live_chain -v`

### Phase 4：落地轻量 memory 策略

目标：

- 用最小工程代价，把 session / agent 两类记忆边界做出来。
- 不引入向量库、embedding、RAG 依赖。

改动范围：

- [app/control/context.py](/Users/litiezhu/workspace/github/marten/app/control/context.py)
- [app/infra/](/Users/litiezhu/workspace/github/marten/app/infra)
- [artifacts/](/Users/litiezhu/workspace/github/marten/artifacts)
- 相关 agent 应用层

动作：

1. 新建或收口 `artifacts/memory/sessions/` 与 `artifacts/memory/agents/`。
2. 总入口只保留短 session 摘要，不持有长专业上下文。
3. agent 侧持有独立记忆文件，并在上下文预算约 60% 时触发摘要压缩。
4. `task memory` 不实现，只在目录和接口上预留未来扩展位时也不要接入主流程。

完成标准：

- session memory 与 agent memory 物理隔离。
- 主入口上下文不会因为 Ralph / review 运行而无限增长。
- 现有主链测试不因 memory 收口而回归。

验证：

- `python -m unittest tests.test_control_context`
- `python -m unittest tests.test_sleep_coding`
- `python -m unittest tests.test_review`
- `python -m unittest tests.test_live_chain -v`

## 四、提交策略

建议每个 Phase 单独提交，不要把所有结构收口压成一个大 commit。

推荐提交顺序：

1. `refactor: centralize mvp route resolution`
2. `refactor: formalize main chain handoff contract`
3. `refactor: split session owner from task owner`
4. `feat: add lightweight markdown memory boundaries`

## 五、测试策略

每个 Phase 至少执行对应最小测试集；Phase 2 之后与 Phase 4 完成后，必须各跑一次完整回归：

```bash
python -m unittest discover -s tests -v
```

如果改动影响真实链路入口或 request/session 跟踪，追加：

```bash
python -m unittest tests.test_live_chain -v
```

## 六、回退原则

如果某个 Phase 出现以下情况，应立即停下，不继续堆改动：

- 需要再引入一层新的 facade / service 才能推进。
- 发现 `control` 之外还有新的主状态真相源。
- 为了兼容旧路径，不得不让 `channel` 或 agent application 重新承担 orchestration。
- 主链测试需要大面积改写而不是局部适配。

遇到这些信号时，优先重新收口边界，而不是继续补层。

## 七、完成定义

本轮计划完成，必须同时满足：

1. 当前主链仍然稳定：
   - `main-agent -> ralph -> code-review-agent -> final delivery`
2. `control` 成为唯一主链控制面。
3. 用户会话与内部任务 owner 明确分离。
4. 轻量 memory 已落地，但未引入重基建。
5. `docs/architecture/mvp-agent-platform-core.md` 中的 MVP 约束，已经能在代码结构中对上号。

如果以上 5 条没有同时满足，就不算完成。
