# Private Server Self-Host Rollout Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `Marten` 收口成“私有服务器自用”的单租户产品：`Feishu` 为主入口，`Web/API` 为辅，按配置选择任意单个有权限的 GitHub 仓库，单用户单任务稳定运行。

**Architecture:** 保持唯一主链 `Feishu/API -> main-agent -> ralph -> code-review-agent -> delivery`。坚持 `LLM + MCP + skill first`，让 agent 负责理解、规划、编码、review、修复；工程代码只负责单任务队列、配置解析、权限与状态真相、超时、诊断和交付 gate。第一阶段只支持单活执行槽，不做多主任务并发，但必须保留后续多 agent / 子 agent 隔离所需的 session、task、handoff 边界。

**Tech Stack:** FastAPI, Python 3.11+, SQLite, builtin agents, MCP, skills, local git worktrees, unittest, Feishu webhook, JSON-first config (`platform.json`, `models.json`, `mcp.json`, `agents.json`).

**Implementation Start Point:** 下一个 agent 直接从 `Chunk 1` 开始实施，不需要重新做产品方向判断。本计划已经固定运行模型、入口优先级、repo 语义和单任务约束。

---

## User Requirement Lock

本计划严格服务于下面这个产品目标，不允许在执行中偏离：

1. 部署目标是固定私有服务器，不是本机开发态脚本集合。
2. 使用形态是单租户自用，不是多租户 SaaS。
3. `Feishu` 是主入口，`Web/API` 是诊断、运维和备用入口。
4. 任意可访问仓库由配置与 GitHub MCP token 权限决定，不把仓库写死在工程代码里。
5. 第一阶段优先单用户单任务稳定跑通，新的任务必须排队或明确返回忙碌状态。
6. 必须坚持 `LLM + MCP + skill first`，避免退回“重工程编排、弱 agent”。

## Non-Negotiable Principles

- 不用大量关键词路由或硬编码规则取代 `main-agent` 的理解和 handoff。
- 不把 Ralph 退化成 command orchestrator；仍由 builtin agent 对本地 worktree 编码负责。
- 不把 code-review-agent 退化成规则引擎；review 结论仍由模型生成，工程层只做 blocking gate。
- 不新增第二条并行主链或通用多 agent 平台外壳。
- 不为“看起来稳定”恢复 permissive fallback、伪成功交付、或隐式降级。
- 工程代码只保留：
  - 单任务队列与 lane
  - 配置与仓库选择
  - control task / event / session 真相
  - timeout / retry / escalation
  - diagnostics / health / operator evidence
  - delivery gate

## Fixed Decisions For The Next Agent

- 运行模型已定稿：
  - `API/webhook` 使用一个独立进程
  - `scheduler/worker` 使用一个独立进程
  - 第一阶段不采用“单进程内挂 scheduler”
- 主入口优先级已定稿：
  - `Feishu` 是默认用户入口
  - `Web/API` 只承担诊断、运维、备用触发和最小人工接管
- 执行模型已定稿：
  - 单用户单任务优先
  - 同时只允许一个 active 主任务
  - 后续任务必须进入队列或收到明确 busy 语义
- repo 语义已定稿：
  - 一个任务只绑定一个 repo
  - repo 来源遵循“请求优先，否则配置默认”
  - control task、worker、issue、PR、review、delivery 必须使用同一个 repo truth
- agent 边界已定稿：
  - 不把队列、仓库选择、人工接管做成第二套业务编排系统
  - 未来多 agent / 子 agent 只保留边界，不在第一阶段实现新的 runtime orchestration

## Scope

### In Scope

- 私有服务器单实例运行方式
- `Feishu` 主入口 + `Web/API` 辅助入口
- 单用户单任务队列化
- 配置驱动目标仓库选择
- operator 基础能力：健康检查、诊断、任务查看、失败恢复入口
- 启动方式、配置模板、上线 SOP
- 与上面行为直接相关的测试与文档同步

### Out Of Scope

- 多租户
- 同时运行多个主任务
- UI 控制台
- 完整权限系统
- 通用多 agent marketplace
- 一开始就支持“多个 agent 同时并发长期工作”

## File / Module Responsibility Map

### Config / Product Surface

- Modify: `app/core/config.py`
  - 增加或收紧私有服务器运行所需配置解析
- Modify: `platform.json`
  - 提供私有服务器推荐配置样例
- Modify if needed: `agents.json`
  - 固化 builtin agent 运行配置
- Modify if needed: `.env.example`
  - 明确服务器部署期环境变量

### Inbound / Queue / Single-Flight

- Modify: `app/control/gateway.py`
- Modify: `app/control/workflow.py`
- Modify: `app/control/context.py`
- Modify: `app/control/session_registry.py`
- Modify: `app/control/automation.py`
- Modify if needed: `app/infra/scheduler.py`
- Modify if needed: `app/models/schemas.py`

### Repo Selection / Task Creation

- Modify: `app/agents/main_agent/application.py`
- Modify: `app/agents/ralph/workflow.py`
- Modify if needed: `app/control/task_registry.py`
- Modify if needed: `app/models/schemas.py`

### Diagnostics / Operator Surface

- Modify: `app/api/routes.py`
- Modify: `app/main.py`
- Modify: `app/infra/diagnostics.py`
- Modify if needed: `app/channel/feishu.py`

### Deployment / Ops

- Add or modify: `README.md`
- Add or modify: `docs/architecture/main-chain-operator-runbook.md`
- Add: `deploy/` or `ops/` files only if really required by the chosen deployment shape
- Add if needed: `scripts/` startup or validation helpers

### Tests

- Modify: `tests/test_gateway.py`
- Modify: `tests/test_control_context.py`
- Modify: `tests/test_session_registry.py`
- Modify: `tests/test_main_agent.py`
- Modify: `tests/test_sleep_coding_worker.py`
- Modify: `tests/test_automation.py`
- Modify: `tests/test_runtime_components.py`
- Modify: `tests/test_mvp_e2e.py`
- Modify: `tests/test_live_chain.py`

### Continuity

- Modify: `STATUS.md`
- Modify: latest relevant file under `docs/internal/handoffs/`

---

## Chunk 1: Define Self-Host Product Boundary

### Objective

- 把“开发态可跑”收口成“私有服务器自用产品”的明确边界和配置语义。

### Success Criteria

- 文档明确第一阶段只支持单租户、单任务执行槽、`Feishu` 主入口。
- 目标仓库由请求 + 配置决定，不写死当前仓库。
- 计划后续实现时不需要再争论“要不要做成通用平台”。

### Task 1.1: Write down self-host product assumptions in code-facing docs

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture/main-chain-operator-runbook.md`
- Modify: `STATUS.md`

- [ ] Step 1: 在 `README.md` 增加“私有服务器自用”运行形态说明，明确主入口、辅助入口、单任务约束。
- [ ] Step 2: 在 runbook 中增加“单任务队列 / 当前忙碌 / 如何查看排队任务”的 operator 说明。
- [ ] Step 3: 在 `STATUS.md` 记录当前产品化目标与完成标准。
- [ ] Step 4: Run:
  - `rg -n "self-host|single-flight|Feishu|single tenant|single task" README.md docs STATUS.md`
- [ ] Step 5: 确认文档中的部署目标与当前产品目标一致，而不是泛化成平台叙事。

### Task 1.2: Define repo-selection product contract

**Files:**
- Modify: `app/models/schemas.py`
- Modify: `app/agents/main_agent/application.py`
- Modify if needed: `app/control/task_registry.py`
- Test: `tests/test_main_agent.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: 写 failing test，要求任务请求中可以显式指定目标 repo，且该 repo 会进入 issue 创建和后续 control task truth。
- [ ] Step 2: Run:
  - `python -m unittest tests.test_main_agent tests.test_mvp_e2e -v`
- [ ] Step 3: 若当前 schema / task payload 仍不足，补最小字段，而不是加自由 dict 分支。
- [ ] Step 4: 确保 repo 选择逻辑遵循“请求优先，否则配置默认”，并且不把 token 权限检查写成业务规则引擎。
- [ ] Step 5: Re-run:
  - `python -m unittest tests.test_main_agent tests.test_mvp_e2e -v`

---

## Chunk 2: Single-Task Queue And Lane Hardening

### Objective

- 保证私有服务器自用阶段“同一时刻只跑一个主任务”，新请求明确进入排队或返回忙碌状态。

### Success Criteria

- 同时到来的两个 coding 请求不会并发执行。
- 第二个请求不会静默丢失。
- operator 能看出当前 active task 和待处理任务。

### Task 2.1: Add failing single-flight tests at gateway/control-plane level

**Files:**
- Modify: `tests/test_gateway.py`
- Modify: `tests/test_control_context.py`
- Modify: `tests/test_session_registry.py`

- [ ] Step 1: 写 failing test，模拟两个接近同时到来的 coding 请求。
- [ ] Step 2: 断言第一个请求进入主链，第二个请求被队列化或收到明确 “busy/queued” 语义，而不是也直接启动 Ralph。
- [ ] Step 3: Run:
  - `python -m unittest tests.test_gateway tests.test_control_context tests.test_session_registry -v`
- [ ] Step 4: 确认失败原因是当前没有单活门禁，而不是测试夹具错误。

### Task 2.2: Implement single active execution lane

**Files:**
- Modify: `app/control/gateway.py`
- Modify: `app/control/workflow.py`
- Modify: `app/control/session_registry.py`
- Modify: `app/control/task_registry.py`
- Modify if needed: `app/models/schemas.py`
- Test: `tests/test_gateway.py`

- [ ] Step 1: 增加一个最小的 single-flight 判定点，优先放在 control-plane，而不是 agent prompt 里。
- [ ] Step 2: 保持“队列状态 / 忙碌状态 / 当前运行 task_id”可持久化或可诊断。
- [ ] Step 3: 避免引入复杂调度器；第一阶段只需要单执行槽。
- [ ] Step 4: Re-run:
  - `python -m unittest tests.test_gateway tests.test_control_context tests.test_session_registry -v`

### Task 2.3: Add explicit queued/busy response semantics

**Files:**
- Modify: `app/control/workflow.py`
- Modify: `app/channel/feishu.py`
- Modify: `app/api/routes.py`
- Modify if needed: `app/models/schemas.py`
- Test: `tests/test_gateway.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: 写 failing test，要求当系统忙碌时，Feishu/API 返回明确的接收结果，而不是伪装已完成。
- [ ] Step 2: Run:
  - `python -m unittest tests.test_gateway tests.test_mvp_e2e -v`
- [ ] Step 3: 输出语义至少区分：
  - `accepted`
  - `queued`
  - `running`
  - `completed`（仅 final delivery 后）
- [ ] Step 4: Re-run:
  - `python -m unittest tests.test_gateway tests.test_mvp_e2e -v`

---

## Chunk 3: Feishu-First Self-Host Inbound Hardening

### Objective

- 让 `Feishu` 真正成为私有服务器自用的稳定主入口，而不是开发测试入口。

### Success Criteria

- Feishu 入站请求能稳定进入主链。
- 同一会话下的状态解释和任务创建行为一致。
- delivery endpoint 与 source endpoint 语义清楚。

### Task 3.1: Harden Feishu inbound session continuity and task linkage

**Files:**
- Modify: `app/channel/feishu.py`
- Modify: `app/control/gateway.py`
- Modify: `app/control/context.py`
- Modify: `app/control/session_registry.py`
- Test: `tests/test_gateway.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: 写 failing test，覆盖同一 Feishu 用户连续发起状态查询和 coding 请求时 session continuity 不断裂。
- [ ] Step 2: Run:
  - `python -m unittest tests.test_gateway tests.test_mvp_e2e -v`
- [ ] Step 3: 修正 source/session/delivery endpoint 绑定逻辑。
- [ ] Step 4: 确保 `main-agent` 的聊天回复不会吞掉真实 coding 请求。
- [ ] Step 5: Re-run:
  - `python -m unittest tests.test_gateway tests.test_mvp_e2e -v`

### Task 3.2: Add Feishu-first smoke path documentation and diagnostics

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture/main-chain-operator-runbook.md`
- Modify: `app/infra/diagnostics.py`
- Test: `tests/test_runtime_components.py`

- [ ] Step 1: 写 failing test，要求 diagnostics 能指出 Feishu webhook/delivery readiness。
- [ ] Step 2: Run:
  - `python -m unittest tests.test_runtime_components -v`
- [ ] Step 3: 在 diagnostics 中补充 Feishu 入口和投递状态。
- [ ] Step 4: README 增加“服务器自用启动后最先检查什么”的清单。
- [ ] Step 5: Re-run:
  - `python -m unittest tests.test_runtime_components -v`

---

## Chunk 4: API As Operator Surface, Not Second Control Plane

### Objective

- API 只承担诊断、查看、人工接管和备用触发入口，不发展成第二套业务编排。

### Success Criteria

- API 能查当前 active task、排队任务、control task、events、review。
- 可以通过 API 触发最小必要的 resume / approve / retry。
- 不新增复杂面板协议或重复状态机。

### Task 4.1: Audit and tighten operator endpoints

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/main.py`
- Modify: `app/control/task_registry.py`
- Test: `tests/test_runtime_components.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: 写 failing test，要求 API 能返回单任务运行态、排队态和最近失败信息。
- [ ] Step 2: Run:
  - `python -m unittest tests.test_runtime_components tests.test_mvp_e2e -v`
- [ ] Step 3: 只暴露必要 operator 数据，不复制新的 domain projection。
- [ ] Step 4: Re-run:
  - `python -m unittest tests.test_runtime_components tests.test_mvp_e2e -v`

### Task 4.2: Add minimal manual-intervention actions

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/control/automation.py`
- Modify if needed: `app/models/schemas.py`
- Test: `tests/test_automation.py`

- [ ] Step 1: 写 failing test，覆盖最小人工动作：
  - 查看当前任务
  - approve plan
  - resume queued task
  - 标记或读取 `needs_attention`
- [ ] Step 2: Run:
  - `python -m unittest tests.test_automation -v`
- [ ] Step 3: 仅增加 deterministic operator actions，不把 review/coding 推理搬进 API。
- [ ] Step 4: Re-run:
  - `python -m unittest tests.test_automation -v`

---

## Chunk 5: Config-Driven Single-Repo-At-A-Time Execution

### Objective

- 让“任意单个可访问仓库”成为稳定产品行为，而不是 demo 行为。

### Success Criteria

- 一个任务明确绑定一个 repo。
- 所有 issue / PR / worker / review / delivery truth 都使用同一个 repo。
- 不发生“默认仓库”和“请求仓库”混淆。

### Task 5.1: Add failing tests for repo continuity through the whole chain

**Files:**
- Modify: `tests/test_main_agent.py`
- Modify: `tests/test_sleep_coding_worker.py`
- Modify: `tests/test_mvp_e2e.py`

- [ ] Step 1: 写 failing tests，要求从 intake 到 PR/review/delivery 都保持同一个 repo。
- [ ] Step 2: Run:
  - `python -m unittest tests.test_main_agent tests.test_sleep_coding_worker tests.test_mvp_e2e -v`
- [ ] Step 3: 确认失败点属于 repo continuity，而不是 fake MCP 夹具问题。

### Task 5.2: Implement repo continuity without adding branching sprawl

**Files:**
- Modify: `app/agents/main_agent/application.py`
- Modify: `app/agents/ralph/workflow.py`
- Modify: `app/control/sleep_coding_worker.py`
- Modify if needed: `app/models/schemas.py`
- Test: `tests/test_main_agent.py`
- Test: `tests/test_sleep_coding_worker.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: 统一 repo 的来源和继承链。
- [ ] Step 2: 不允许 worker 在 claim / resume / rerun 时掉回默认仓库。
- [ ] Step 3: 保持 repo 是 control task 和 domain task 的一等事实字段。
- [ ] Step 4: Re-run:
  - `python -m unittest tests.test_main_agent tests.test_sleep_coding_worker tests.test_mvp_e2e -v`

---

## Chunk 6: Server Deployment Baseline

### Objective

- 把当前仓库从“开发态命令集合”推进到“固定服务器可稳定拉起”的基线。

### Success Criteria

- 服务启动方式清晰。
- 配置文件模板清晰。
- 服务器重启后能恢复。
- 你可以用一套 SOP 完成部署、升级和回滚。

### Task 6.1: Define process model and startup contract

**Files:**
- Modify: `README.md`
- Add or Modify: deployment helper files under `scripts/`, `deploy/`, or `ops/`
- Modify if needed: `app/main.py`

- [ ] Step 1: 按已固定的最小运行模型落文档和启动契约：
  - `API/webhook` 独立进程
  - `scheduler/worker` 独立进程
  - 第一阶段不采用单进程内挂 scheduler
- [ ] Step 2: 写部署文档，不要先写复杂脚本。
- [ ] Step 3: 如果需要脚本，只加最小启动/检查脚本，不引入新的部署框架。
- [ ] Step 4: Run:
  - `python -m unittest tests.test_runtime_components -v`
- [ ] Step 5: 确认运行模型不破坏现有 main chain。

### Task 6.2: Add configuration validation for self-host boot

**Files:**
- Modify: `app/infra/diagnostics.py`
- Modify if needed: `app/core/config.py`
- Modify: `README.md`
- Test: `tests/test_runtime_components.py`
- Test: `tests/test_live_chain.py`

- [ ] Step 1: 写 failing test，要求启动前能判断：
  - GitHub MCP 是否可写
  - LLM provider 是否可用
  - Feishu webhook / delivery 基本配置是否存在
  - 默认 repo 或请求 repo 能否被接受
- [ ] Step 2: Run:
  - `python -m unittest tests.test_runtime_components tests.test_live_chain -v`
- [ ] Step 3: diagnostics 给出 `next_action`，而不是只说某组件 unavailable。
- [ ] Step 4: Re-run:
  - `python -m unittest tests.test_runtime_components tests.test_live_chain -v`

---

## Chunk 7: Preserve LLM-First Agent Boundaries While Productizing

### Objective

- 在“自用上线”过程中守住 `LLM + MCP + skill first`，不让产品化把系统改回工程编排平台。

### Success Criteria

- `main-agent` 仍负责理解与 handoff，不新增大规模规则分发。
- `ralph` 仍负责 worktree 编码与验证，不回退 command-heavy 逻辑。
- `code-review-agent` 仍负责 review 结论，不把判断迁成 if/else。

### Task 7.1: Audit and reduce productization-driven orchestration growth

**Files:**
- Modify if needed: `app/agents/main_agent/application.py`
- Modify if needed: `app/control/automation.py`
- Modify if needed: `app/control/workflow.py`
- Modify if needed: `docs/architecture/agent-first-implementation-principles.md`
- Test: `tests/test_main_agent.py`
- Test: `tests/test_review.py`

- [ ] Step 1: 在本 chunk 开始前 grep 新增的 routing / orchestration 分支，确认是否有明显偏离。
- [ ] Step 2: Run:
  - `rg -n "if .*coding|if .*review|should_route|fallback|queued|busy" app`
- [ ] Step 3: 若发现为了产品化新增了不必要的规则分支，优先把语义收回 schema、task payload、prompt policy，而不是继续长 if/else。
- [ ] Step 4: Re-run:
  - `python -m unittest tests.test_main_agent tests.test_review -v`

### Task 7.2: Keep future multi-agent expansion as boundary, not implementation now

**Files:**
- Modify: `docs/architecture/agent-system-overview.md`
- Modify: `docs/architecture/agent-runtime-contracts.md`
- Modify: `STATUS.md`

- [ ] Step 1: 文档明确：
  - 第一阶段只支持单活主任务
  - 但 session/task/handoff 边界必须允许未来多 agent / 子 agent 扩展
- [ ] Step 2: 不实现多 agent runtime orchestration，只固化边界。
- [ ] Step 3: Run:
  - `rg -n "sub-agent|child agent|single-flight|single task" docs STATUS.md`

---

## Chunk 8: Final Verification And Continuity Sync

### Objective

- 用 fresh evidence 证明“私有服务器自用第一阶段”达到可上线基线，并同步所有连续性文档。

### Success Criteria

- 关键回归通过。
- live chain fresh 通过。
- 文档、状态和 handoff 没有继续描述已修复项为 pending。

### Task 8.1: Run staged verification

**Files:**
- Modify if needed: `STATUS.md`
- Modify latest relevant file under `docs/internal/handoffs/`

- [ ] Step 1: Run:
  - `python -m unittest tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_review tests.test_runtime_components tests.test_test_suites -v`
- [ ] Step 2: Run:
  - `python -m unittest tests.test_sleep_coding_worker tests.test_automation tests.test_mvp_e2e -v`
- [ ] Step 3: Run:
  - `command time -lp python scripts/run_test_suites.py quick`
- [ ] Step 4: Run:
  - `command time -lp python scripts/run_test_suites.py regression`
- [ ] Step 5: Run:
  - `command time -lp python scripts/run_test_suites.py live`
- [ ] Step 6: 如果 live 失败，记录第一真实失败点，回到对应 chunk 修复，不准跳过。

### Task 8.2: Sync docs and handoff to reality

**Files:**
- Modify: `STATUS.md`
- Modify: latest relevant local handoff under `docs/internal/handoffs/`
- Modify if needed: `README.md`
- Modify if needed: `docs/architecture/current-mvp-status-summary.md`

- [ ] Step 1: 更新 `STATUS.md`：
  - 当前阶段
  - 当前目标
  - 已完成项
  - 下一步
  - blockers
  - latest verification
- [ ] Step 2: 更新本地 handoff，写清楚：
  - 服务器自用部署方式
  - 主入口和备用入口
  - 单任务队列语义
  - repo 选择语义
  - 最新验证结果
- [ ] Step 3: 如 README / architecture 文档仍把系统描述成“开发态”或“live 未分层”，同步改正。

---

## Recommended Execution Order

1. Chunk 1: Define Self-Host Product Boundary
2. Chunk 2: Single-Task Queue And Lane Hardening
3. Chunk 3: Feishu-First Self-Host Inbound Hardening
4. Chunk 5: Config-Driven Single-Repo-At-A-Time Execution
5. Chunk 4: API As Operator Surface, Not Second Control Plane
6. Chunk 6: Server Deployment Baseline
7. Chunk 7: Preserve LLM-First Agent Boundaries While Productizing
8. Chunk 8: Final Verification And Continuity Sync

执行要求：

- 默认直接开始编码，不再回到“需求是否明确”的讨论阶段。
- 每个 chunk 必须先写 failing test，再做最小实现。
- 每个 chunk 结束后更新 `STATUS.md` 和最新本地 handoff。

---

## Done Criteria

当下面条件同时成立，本计划可视为第一阶段完成：

1. 私有服务器运行形态已在 README / runbook 中明确。
2. `Feishu` 能作为主入口稳定创建并驱动任务。
3. API 能查看 active task、queued/busy 状态、control task、events、review。
4. 同一时刻只跑一个主任务，后续请求不会并发污染。
5. 目标 GitHub 仓库可以按请求/配置选择，并贯穿全链路。
6. 最新 `quick / regression / live` fresh 验证均通过。
7. 产品化过程中没有引入明显偏离 `LLM + MCP + skill first` 的重编排代码。

## Recommended Execution Order

1. Chunk 1
2. Chunk 2
3. Chunk 3
4. Chunk 5
5. Chunk 4
6. Chunk 6
7. Chunk 7
8. Chunk 8

## Notes For The Next Agent

- 第一优先级不是“加更多功能”，而是把现有单主链稳定包装成服务器自用产品。
- 任何想新增的逻辑，先判断是不是其实应该交给 agent prompt / MCP / skill / schema。
- 如果为了“更像产品”开始长出大量状态机和规则分支，说明方向偏了。
- live-chain 仍然是最终裁判，不准用 readiness 代替真实执行。
