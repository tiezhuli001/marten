# MVP Repo Slimming Checklist

> 更新时间：2026-03-20
> 目标：先把 `Marten` 收口成更小、更稳、更易维护的 MVP 主链仓库，再继续迭代。
> 当前分支建议：`codex/mvp-slimming-checklist`

## 一、目标边界

这轮瘦身不是“重写架构”，而是继续围绕当前已验证主链做减法：

`Feishu inbound -> gateway -> issue -> claim -> coding -> review -> final delivery`

本轮判断标准只有三个：

1. 是否减少主链无关模块和历史残留。
2. 是否减少多层重复编排和重复状态真相源。
3. 是否在不破坏当前 mock e2e / live-chain 能力的前提下，让仓库更接近一个最小 agent-first MVP。

## 二、最终收口方向

目标不是把目录完全推倒重来，而是把仓库逐步压回这条更小的主骨架：

```text
app/
  channel/   # 入站标准化、出站通知
  control/   # 唯一 orchestration 层
  runtime/   # llm / mcp / skills / token
  agents/    # main-agent / ralph / code-review-agent
  infra/     # 调度、git workspace、sqlite、诊断
  models/    # schema
  ledger/    # token ledger
```

明确方向：

- `app/services/` 不再作为独立编排层长期存在。
- `app/control/` 成为唯一控制面。
- `app/agents/` 只保留 agent-specific cognition 和平台动作。
- `sleep_coding_tasks`、`review_runs` 逐步降为 artifact/projection，不再和 control task 并列争夺主状态真相。

## 三、执行顺序

建议分 4 批做，不要一口气大改。

### Batch 0：立即删除的低风险残留

这批改动应该优先落地，风险最低，收益直接。

- 删除空壳目录 [app/graph](/Users/litiezhu/workspace/github/marten/app/graph)
  - 当前只剩 `__pycache__`，没有有效源码，也没有任何引用。
- 清理仓库内各级 `__pycache__/` 生成物
  - 这些不是源码，不应参与架构判断。
- 继续保持历史归档文档不回流
  - 不恢复 `plans/`、`requirements/`、review 产物、阶段性草稿。

完成标准：

- `rg "app\\.graph" /Users/litiezhu/workspace/github/marten` 无有效源码依赖。
- `git status` 中不再出现缓存生成物。

### Batch 1：文档瘦身

先把“仓库怎么理解”收口，不然之后继续删代码时，文档会反向制造噪音。

- 从公开仓库语义中移除内部 handoff 文档的权威性：
  - [docs/internal/session-handoff.md](/Users/litiezhu/workspace/github/marten/docs/internal/session-handoff.md)
  - [docs/internal/current-status.md](/Users/litiezhu/workspace/github/marten/docs/internal/current-status.md)
  - [docs/internal/roadmap-next-agent.md](/Users/litiezhu/workspace/github/marten/docs/internal/roadmap-next-agent.md)
- 将内部状态文档收口为一份主文档
  - 避免 `status + roadmap + handoff` 三份内部真相并存。
- 收口配置说明
  - 以 `*.json.example` 为唯一结构权威。
  - README 只说明职责，不再嵌入另一套字段命名风格。
- 合并低信息密度 agent 文档
  - 将 `agents/*/SOUL.md` 并回对应的 `AGENTS.md`，或明确降级为内部 prompt 片段。

完成标准：

- 仓库外部读者只需看 [README.md](/Users/litiezhu/workspace/github/marten/README.md)、[docs/README.md](/Users/litiezhu/workspace/github/marten/docs/README.md)、架构文档和演进文档即可理解当前方向。
- 不再存在多份相互漂移的内部状态说明。

### Batch 2：先合并再删的薄包装层

这一批不追求改变行为，目标是减少跳转层级。

- 将 [app/control/follow_up.py](/Users/litiezhu/workspace/github/marten/app/control/follow_up.py) 下沉回控制面主流程
  - 当前基本只服务 [app/services/automation.py](/Users/litiezhu/workspace/github/marten/app/services/automation.py)。
- 将 [app/control/review_loop.py](/Users/litiezhu/workspace/github/marten/app/control/review_loop.py) 的状态判定并回主编排处
  - 它现在更像一个局部 helper，不需要单独成层。
- 合并上下文组装逻辑：
  - [app/control/context.py](/Users/litiezhu/workspace/github/marten/app/control/context.py)
  - [app/control/session_memory.py](/Users/litiezhu/workspace/github/marten/app/control/session_memory.py)
- 评估并压缩 registry/store 双层包装：
  - [app/services/task_registry.py](/Users/litiezhu/workspace/github/marten/app/services/task_registry.py)
  - [app/control/task_store.py](/Users/litiezhu/workspace/github/marten/app/control/task_store.py)
  - [app/control/task_events.py](/Users/litiezhu/workspace/github/marten/app/control/task_events.py)
  - [app/services/session_registry.py](/Users/litiezhu/workspace/github/marten/app/services/session_registry.py)
  - [app/control/session_store.py](/Users/litiezhu/workspace/github/marten/app/control/session_store.py)
- 将 [app/services/observability.py](/Users/litiezhu/workspace/github/marten/app/services/observability.py) 移到更合适的位置
  - 更像 `infra`，不像领域 service。

完成标准：

- `app/services/` 不再承担主流程 orchestration。
- 主链关键路径阅读跳转次数明显下降。

### Batch 3：消掉 `app/services` 这一层

这是第一轮真正的结构瘦身重点。

建议目标：

- 删除 [app/services/automation.py](/Users/litiezhu/workspace/github/marten/app/services/automation.py)
  - 将 worker poll、review loop、follow-up、delivery orchestration 收回 `control`。
- 将 `task_registry` / `session_registry` 并到 `control/state.py` 或同等位置
  - 不再保留一个“服务层 facade”。
- 更新 API 依赖注入
  - [app/api/routes.py](/Users/litiezhu/workspace/github/marten/app/api/routes.py) 不再直接拼装 `AutomationService`。
- 清理 channel 层越界编排
  - [app/channel/feishu.py](/Users/litiezhu/workspace/github/marten/app/channel/feishu.py) 只负责协议转换，不再继续驱动 workflow。

完成标准：

- `app/services/` 可以为空或仅保留极少数真正稳定的横切能力。
- `channel -> control -> agents/runtime` 成为清晰单核主链。

### Batch 4：收口 review 子系统到 MVP 主链

这是改动最大的一批，需要明确接受取舍后再做。

当前问题：

- review 子系统仍保留了泛化入口和平台化能力：
  - `sleep_coding_task`
  - `github_pr`
  - `gitlab_mr`
  - `local_code`
- 这让 [app/agents/code_review_agent](/Users/litiezhu/workspace/github/marten/app/agents/code_review_agent) 的复杂度明显高于当前 MVP 需要。

建议方向：

- 先把 Review Agent 收口为只服务 Ralph 主链。
- 保留 task-based review 主路径。
- 逐步退出 GitLab MR / 泛化 remote materialization / 非主链 source support。
- 让 Review Agent 只产出 review result，不再自己反向总控 sleep coding 状态机。

优先处理文件：

- [app/agents/code_review_agent/application.py](/Users/litiezhu/workspace/github/marten/app/agents/code_review_agent/application.py)
- [app/agents/code_review_agent/context.py](/Users/litiezhu/workspace/github/marten/app/agents/code_review_agent/context.py)
- [app/agents/code_review_agent/materializer.py](/Users/litiezhu/workspace/github/marten/app/agents/code_review_agent/materializer.py)
- [app/agents/code_review_agent/bridge.py](/Users/litiezhu/workspace/github/marten/app/agents/code_review_agent/bridge.py)
- [app/agents/code_review_agent/gitlab.py](/Users/litiezhu/workspace/github/marten/app/agents/code_review_agent/gitlab.py)
- [app/agents/code_review_agent/store.py](/Users/litiezhu/workspace/github/marten/app/agents/code_review_agent/store.py)

完成标准：

- Review Agent 只围绕 `sleep_coding_task -> review result` 工作。
- review 状态不再和 control task / sleep coding task 构成三套并行真相。

## 四、关键架构改造点

### 1. 控制权必须收回 `control`

当前最大冗余不是类太多，而是 orchestration 分散：

- `channel` 在继续 workflow
- `gateway` 能直接起 Ralph
- `worker` 也能直接起 Ralph
- `automation` 在驱动 review loop
- `review agent` 又能反向改变 sleep coding task

目标状态：

- `control` 是唯一 orchestration 层。
- `agents` 只负责本 agent 的认知与动作。
- `channel` 只做协议和通知。

### 2. 状态真相源必须收口

当前至少有三套主状态参与决策：

- `control_tasks`
- `sleep_coding_tasks`
- `review_runs`

建议目标：

- `control_tasks` 是唯一主状态机。
- `sleep_coding_tasks` 只保留 Ralph 执行 artifact。
- `review_runs` 只保留 review artifact 和轮次记录。

### 3. API 旁路必须继续减少

需要评估并逐步降级这些 direct-task 入口：

- [POST /tasks/sleep-coding](/Users/litiezhu/workspace/github/marten/app/api/routes.py#L188)
- [POST /tasks/sleep-coding/{task_id}/actions](/Users/litiezhu/workspace/github/marten/app/api/routes.py#L236)

这些接口虽然便于调试，但会稀释 handoff 已明确的单入口主链。

## 五、每批改动后的最低验证

每完成一批，都至少跑：

```bash
python -m unittest discover -s tests
python -m unittest tests.test_mvp_e2e
```

如果改到 worker / review / follow-up，追加：

```bash
python -m unittest tests.test_sleep_coding tests.test_automation tests.test_review tests.test_sleep_coding_worker
```

如果改到真实链路入口或 request/session 追踪，追加：

```bash
python -m unittest tests.test_gateway tests.test_feishu tests.test_main_agent
```

如果改到 live path 行为，再按需执行：

```bash
python -m unittest tests.test_live_chain -v
```

## 六、不做事项

这轮不要做下面这些事：

- 不回摆 GitHub REST。
- 不重新强化 env-first 配置叙事。
- 不把瘦身变成“全面重写 agent runtime”。
- 不在未确认 review 收口方向前，直接大删 code review 子系统。
- 不为了抽象干净，再新加一层 facade。

## 七、建议落地顺序

推荐实际执行顺序：

1. Batch 0：删空壳目录、删缓存生成物。
2. Batch 1：文档收口，先统一仓库叙事。
3. Batch 2：合并 `follow_up/review_loop/context` 这类薄层。
4. Batch 3：消掉 `app/services/automation.py`，把 orchestration 收回 `control`。
5. Batch 4：确认 review 只服务 Ralph 后，再清 review 泛化能力。
6. 最后再继续收紧 `app/core/config.py` 的历史 env-first 残留。

## 八、下一步建议

如果下一轮开始动代码，建议先只做一个可控切片：

- 第一刀只做 `Batch 0 + Batch 1`
- 第二刀只做 `Batch 2`
- 第三刀单独处理 `AutomationService`
- 第四刀再动 review 子系统

这样每轮都能保持回归范围清晰，也方便观察哪一刀真正降低了复杂度。
