# 2026-03-21 Post-MVP Iteration Closure Plan

> 状态：已完成
> 目标：完成当前 `Marten` 主架构收口后的第一轮 closure sprint，把仍然悬空的控制面 owner、状态真相依赖和公开架构文档口径一起收紧。

## 一、为什么开这一轮

`main-agent -> ralph -> code-review-agent` 的 MVP 主链已经稳定，也已经通过 live chain 和全量回归验证。

当前剩余问题不再是“主链能不能跑”，而是：

- Feishu webhook 还要同时知道 `GatewayControlPlaneService` 和 `AutomationService`，控制面 owner 边界不够清晰。
- worker 在“issue 是否已有活跃任务”上仍然直接查 `sleep_coding_tasks`，和“`control_tasks` 是控制真相”的方向不完全一致。
- 公开架构文档里虽然描述了当前边界，但还缺少更明确的“canonical / historical”口径。

这轮不做大而全重构，只完成能直接降低复杂度、且能用测试闭环的收口项。

## 二、本轮范围

### 1. 控制面 owner 收口

- 新增单一 workflow owner，接管 `gateway run + automation follow-up` 组合流程。
- Feishu channel 不再自己拼接多个控制面 service。
- 保持现有 `gateway/message` 与 worker poll contract 不变，不破坏主链。

### 2. 状态真相源收紧

- worker 判断 issue 是否已有活跃任务时，优先基于 `control_tasks` 查询。
- 降低 `sleep_coding_tasks` 在主编排判定中的控制权。
- 保持 `sleep_coding_tasks` 继续承担 Ralph 领域 artifact 存储，不在本轮强做表结构大改。

### 3. 文档口径归一

- 在 `docs/architecture` 明确：
  - `mvp-agent-platform-core` 是 canonical 文档
  - `mvp-agent-first-architecture` 是过渡/历史说明文档
- 把这轮计划归档到 `docs/archive/plans/`，避免内部 handoff 承担公开规划职责。

## 三、本轮不做

- 不重写 Ralph / Review 持久化模型
- 不做并发调度系统
- 不引入新的 agent registry / plugin 平台
- 不做数据库迁移到 PostgreSQL
- 不把 `sleep_coding_tasks` / `review_runs` 全量废弃

## 四、完成标准

只有同时满足下面四项，这轮才算完成：

1. Feishu webhook 已通过新的 workflow owner 走完整主链 follow-up。
2. worker 活跃任务检测已新增基于 `control_tasks` 的查询与测试覆盖。
3. 公开架构文档已标明 canonical / historical 边界。
4. 以下验证全部通过：
   - `python -m unittest tests/test_feishu.py tests/test_gateway.py tests/test_sleep_coding_worker.py -v`
   - `python -m unittest tests/test_mvp_e2e.py tests/test_live_chain.py -v`
   - `python -m unittest discover -s tests -v`

## 五、执行顺序

1. 增加 control workflow owner，并迁移 Feishu 调用。
2. 增加 control task 级活跃 issue 查询，并让 worker 使用。
3. 更新架构文档口径。
4. 跑定向测试。
5. 跑主链测试。
6. 跑全量回归。

## 六、验收口径

这轮交付后，`Marten` 的判断应该是：

> MVP 主架构已经完成，当前仓库进入“持续做减法”的 closure 阶段；控制面、状态真相源和公开文档边界进一步一致，不再留明显的 owner 歧义。

## 七、执行结果

- 已新增 `GatewayWorkflowService`，把 `gateway run + automation follow-up` 收到单一 owner。
- `FeishuWebhookService` 已切换到 workflow owner，不再直接拼接 `GatewayControlPlaneService + AutomationService`。
- worker 对 issue 活跃任务的判定已新增基于 `control_tasks` 的查询，减少继续依赖 `sleep_coding_tasks` 做控制真相。
- 公开架构文档已明确：
  - `mvp-agent-platform-core` 是 canonical
  - `mvp-agent-first-architecture` 是历史/过渡文档
- `TokenLedgerService` 已补 sqlite `database is locked` 写入重试，避免并发写入时直接炸链。

## 八、最终验证

- `python -m compileall app tests`
  - 结果：通过
- `python -m unittest tests/test_feishu.py tests/test_gateway.py tests/test_sleep_coding_worker.py -v`
  - 结果：`Ran 19 tests ... OK`
- `python -m unittest tests/test_mvp_e2e.py -v`
  - 结果：`Ran 5 tests ... OK`
- `python -m unittest tests/test_token_ledger.py -v`
  - 结果：`Ran 7 tests ... OK`
- `python -m unittest tests/test_live_chain.py -v`
  - 结果：`Ran 1 test in 174.249s OK`
- `python -m unittest discover -s tests -v`
  - 结果：`Ran 128 tests in 120.559s OK`
