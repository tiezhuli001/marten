# Main Chain Engineering Hardening Detailed Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不偏离 `LLM + MCP + skill first` 的前提下，把 `Marten` 主链从入口到交付的工程可用性做硬，并给编码 agent 提供可以逐步执行、逐步验证、逐步交接的细粒度开发计划。

**Architecture:** 以单主链 `Inbound Gateway -> Canonical Session Context -> Main Agent Intake -> Control Task -> Ralph Execution Loop -> Review Loop -> Delivery Gate -> Final Delivery` 为唯一中心。认知逻辑继续优先交给 agent；代码只负责请求标准化、会话与事件、超时与恢复、状态门禁、交付证据。

**Tech Stack:** FastAPI, Python 3.11+, SQLite, builtin agents, MCP, skills, unittest, existing control/session/task stores.

---

## Relationship To Other Docs

- Canonical rollout plan:
  - `docs/plans/2026-03-23-main-chain-engineering-hardening.md`
- Current architecture:
  - `docs/architecture/agent-first-implementation-principles.md`
  - `docs/architecture/agent-system-overview.md`
  - `docs/architecture/agent-runtime-contracts.md`
  - `docs/architecture/current-mvp-status-summary.md`
- Local continuity:
  - `STATUS.md`
  - latest relevant file under `docs/internal/handoffs/`

## Execution Rules

- 每个 task 必须按 `RED -> GREEN -> REFACTOR` 推进。
- 没有先失败的测试，不允许写生产代码。
- 每个 task 结束都要运行该 task 的最小测试集。
- 每个 chunk 结束都要运行该 chunk 的回归包。
- 每次中断前必须更新 `STATUS.md` 和本地 handoff。
- 如果实现过程中发现需要新增状态或分支，先检查是否可以改成：
  - schema
  - event
  - timeout / gate
  - handoff
  而不是新增更多流程代码。

---

## Chunk 1: Gateway / Session / Lane

### Objective

- 把入口处理从“能接消息”收口成“标准化、幂等、同 session 安全串行、可恢复”。

### Success Criteria

- 同一请求在不同入口不会生成割裂的 session / chain identity。
- 重复入站不会重复触发昂贵主链。
- 同一 session 下不会并发跑出相互污染的链路。
- 快速 ack 与后续异步推进之间有稳定任务链接。

### Task 1.1: Audit current identity and session flow

**Files:**
- Read/Modify: `app/control/gateway.py`
- Read/Modify: `app/control/context.py`
- Read/Modify: `app/control/session_registry.py`
- Test: `tests/test_gateway.py`
- Test: `tests/test_control_context.py`
- Test: `tests/test_session_registry.py`

- [ ] Step 1: Map the current identity sources used by:
  - `POST /gateway/message`
  - `POST /main-agent/intake`
  - Feishu webhook flow
- [ ] Step 2: Write down which fields currently participate in:
  - `request_id`
  - `chain_request_id`
  - session external ref
  - session payload continuity
- [ ] Step 3: Add one failing test for the same conversation entering through two adjacent steps of the chain and unexpectedly forking session continuity.
- [ ] Step 4: Run:
  - `python -m unittest tests.test_gateway tests.test_control_context tests.test_session_registry -v`
- [ ] Step 5: Confirm failure reason is session/identity mismatch, not fixture/setup error.

### Task 1.2: Canonicalize session key and chain key derivation

**Files:**
- Modify: `app/control/gateway.py`
- Modify: `app/control/context.py`
- Modify: `app/control/session_registry.py`
- Modify if needed: `app/models/schemas.py`
- Test: `tests/test_gateway.py`
- Test: `tests/test_control_context.py`

- [ ] Step 1: Add a small helper or clear code path that computes canonical identity once per inbound request.
- [ ] Step 2: Ensure the same logical conversation reuses:
  - same user session
  - same chain linkage
  - stable active-agent continuity
- [ ] Step 3: Avoid introducing provider-specific branching beyond the minimum needed to build canonical identity.
- [ ] Step 4: Re-run the failing test from Task 1.1 and confirm green.
- [ ] Step 5: Re-run:
  - `python -m unittest tests.test_gateway tests.test_control_context -v`

### Task 1.3: Add inbound dedupe for repeated delivery

**Files:**
- Modify: `app/control/gateway.py`
- Modify if needed: `app/control/workflow.py`
- Test: `tests/test_gateway.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: Add a failing test for one duplicate inbound message or duplicate gateway request replay.
- [ ] Step 2: Use the smallest dedupe key that can distinguish:
  - provider/surface
  - conversation/session
  - peer/thread where relevant
  - message/request identity
- [ ] Step 3: Store or project enough dedupe state to suppress duplicate execution without suppressing legit new requests.
- [ ] Step 4: Ensure duplicate handling returns a safe, explainable response shape.
- [ ] Step 5: Run:
  - `python -m unittest tests.test_gateway tests.test_mvp_e2e -v`

### Task 1.4: Add same-session lane safety

**Files:**
- Modify: `app/control/gateway.py`
- Modify: `app/control/session_registry.py`
- Modify if needed: `app/infra/scheduler.py`
- Test: `tests/test_gateway.py`
- Test: `tests/test_session_registry.py`

- [ ] Step 1: Add a failing test where two same-session requests would interleave unsafely.
- [ ] Step 2: Implement minimal lane semantics:
  - same session serial
  - different sessions still can proceed independently
- [ ] Step 3: Keep lane logic out of agent reasoning code.
- [ ] Step 4: Expose enough state for observability/debugging if a request is queued by lane protection.
- [ ] Step 5: Run:
  - `python -m unittest tests.test_gateway tests.test_session_registry -v`

### Task 1.5: Harden fast ack and async continuation contract

**Files:**
- Modify: `app/control/workflow.py`
- Modify: `app/channel/feishu.py`
- Modify: `app/api/routes.py`
- Test: `tests/test_feishu.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: Add a failing test requiring:
  - quick acceptance signal
  - concrete task linkage
  - no fake “completed” semantics
- [ ] Step 2: Make ack payload explicitly distinguish:
  - accepted
  - started
  - follow-up triggered
  - final delivery not yet complete
- [ ] Step 3: Ensure async continuation can resume using persisted task/session state only.
- [ ] Step 4: Run:
  - `python -m unittest tests.test_feishu tests.test_mvp_e2e -v`

### Chunk 1 Regression

- [ ] Run:
  - `python -m unittest tests.test_gateway tests.test_control_context tests.test_session_registry tests.test_feishu tests.test_mvp_e2e -v`
- [ ] Update `STATUS.md` with:
  - what changed
  - what still remains inside Chunk 1 or next chunk
- [ ] Write local handoff if you stop here.

---

## Chunk 2: Control Task / Event / Timeout / Recovery

### Objective

- 把 control plane 从“记录状态”收口成“可恢复、可诊断、可失败退出”的单主链骨架。

### Success Criteria

- 控制任务和事件足以重建下一步动作。
- timeout / retry / escalation 行为在 intake / coding / validation / review 上一致。
- `/diagnostics/integrations` 能真实反映主链 readiness。

### Task 2.1: Audit recovery-critical events

**Files:**
- Read/Modify: `app/control/task_registry.py`
- Read/Modify: `app/control/task_store.py`
- Read/Modify: `app/control/task_events.py`
- Test: `tests/test_task_registry.py`
- Test: `tests/test_automation.py`

- [ ] Step 1: Enumerate which events are already emitted for:
  - task created
  - handoff to Ralph
  - review started
  - review returned
  - delivery completed
  - failure/escalation
- [ ] Step 2: Add a failing recovery test for one interrupted chain that cannot reconstruct the next step from persisted state.
- [ ] Step 3: Run:
  - `python -m unittest tests.test_task_registry tests.test_automation -v`

### Task 2.2: Make event payloads sufficient for replay/recovery

**Files:**
- Modify: `app/control/task_events.py`
- Modify: `app/control/task_registry.py`
- Modify if needed: `app/models/schemas.py`
- Test: `tests/test_task_registry.py`
- Test: `tests/test_automation.py`

- [ ] Step 1: Tighten event payload content for handoff/review/delivery/failure events.
- [ ] Step 2: Prefer concise typed facts over copying full task payloads.
- [ ] Step 3: If needed, add typed accessors for event payloads used by recovery paths.
- [ ] Step 4: Re-run the failing recovery test and confirm green.
- [ ] Step 5: Run:
  - `python -m unittest tests.test_task_registry tests.test_automation -v`

### Task 2.3: Unify timeout and retry policy surfaces

**Files:**
- Modify: `app/agents/main_agent/application.py`
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/code_review_agent/application.py`
- Modify: `app/control/automation.py`
- Modify: `app/control/sleep_coding_worker.py`
- Test: `tests/test_main_agent.py`
- Test: `tests/test_sleep_coding.py`
- Test: `tests/test_review.py`
- Test: `tests/test_runtime_components.py`

- [ ] Step 1: Add one failing test for each boundary:
  - intake llm timeout/retry
  - local execution timeout
  - validation timeout
  - review command timeout
- [ ] Step 2: Standardize emitted status and event behavior on timeout/retry exhaustion.
- [ ] Step 3: Ensure the control plane sees explicit terminal or escalation state, not hanging subprocess semantics.
- [ ] Step 4: Run:
  - `python -m unittest tests.test_main_agent tests.test_sleep_coding tests.test_review tests.test_runtime_components -v`

### Task 2.4: Normalize escalation exits

**Files:**
- Modify: `app/control/automation.py`
- Modify: `app/control/sleep_coding_worker.py`
- Test: `tests/test_automation.py`
- Test: `tests/test_sleep_coding_worker.py`

- [ ] Step 1: Add failing tests for repeated failure reaching:
  - `failed`
  - `needs_attention`
  - no silent infinite retry
- [ ] Step 2: Implement consistent escalation projection on both domain task and control task.
- [ ] Step 3: Ensure event log contains enough evidence for operator follow-up.
- [ ] Step 4: Run:
  - `python -m unittest tests.test_automation tests.test_sleep_coding_worker -v`

### Task 2.5: Harden diagnostics and health readiness

**Files:**
- Modify: `app/infra/diagnostics.py`
- Modify: `app/api/routes.py`
- Modify: `app/main.py`
- Test: `tests/test_runtime_components.py`
- Test: `tests/test_live_chain.py`

- [ ] Step 1: Add failing tests for a degraded integration state that should show up in diagnostics.
- [ ] Step 2: Keep `/health` cheap and process-level.
- [ ] Step 3: Make `/diagnostics/integrations` report component readiness for:
  - gateway prerequisites
  - GitHub MCP
  - Ralph execution
  - review skill
  - channel delivery
- [ ] Step 4: Run:
  - `python -m unittest tests.test_runtime_components tests.test_live_chain -v`

### Chunk 2 Regression

- [ ] Run:
  - `python -m unittest tests.test_task_registry tests.test_sleep_coding_worker tests.test_automation tests.test_main_agent tests.test_sleep_coding tests.test_review tests.test_runtime_components -v`
- [ ] Update continuity docs before moving on.

---

## Chunk 3: Main-Agent / Ralph / Review Loop

### Objective

- 把三 agent 主链从“设计上成立”收口成“运行上稳定”，同时守住 agent-first 边界。

### Success Criteria

- `main-agent` 不吞 coding 请求，也不过度硬编码路由。
- Ralph 可以 resume、验证、交 review，不靠隐藏上下文。
- review loop 明确 blocking、round cap、repair return。

### Task 3.1: Tighten main-agent coding-handoff boundary

**Files:**
- Modify: `app/agents/main_agent/application.py`
- Modify: `agents/main-agent/AGENTS.md`
- Test: `tests/test_main_agent.py`
- Test: `tests/test_gateway.py`

- [ ] Step 1: Add failing tests for:
  - swallowed coding request
  - over-eager coding route
  - missing clarification before oversized task
- [ ] Step 2: Fix only the minimal deterministic gate logic.
- [ ] Step 3: Prefer schema-constrained LLM output over new keyword branching.
- [ ] Step 4: Run:
  - `python -m unittest tests.test_main_agent tests.test_gateway -v`

### Task 3.2: Ensure Ralph can resume from persisted facts

**Files:**
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/ralph/workflow.py`
- Modify: `agents/ralph/AGENTS.md`
- Test: `tests/test_sleep_coding.py`
- Test: `tests/test_sleep_coding_worker.py`

- [ ] Step 1: Add failing tests for resume after:
  - task already planned
  - validation already executed
  - PR already exists
  - review return already recorded
- [ ] Step 2: Make resume prefer persisted artifacts/control projection instead of re-deriving from scratch.
- [ ] Step 3: Ensure review handoff remains complete after resume.
- [ ] Step 4: Run:
  - `python -m unittest tests.test_sleep_coding tests.test_sleep_coding_worker -v`

### Task 3.3: Require explicit validation evidence before review

**Files:**
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/ralph/workflow.py`
- Test: `tests/test_sleep_coding.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: Add failing tests for review entry without validation evidence or explicit validation gap.
- [ ] Step 2: Prevent review handoff if neither validation result nor structured gap exists.
- [ ] Step 3: Keep this as a gate, not a reasoning substitution.
- [ ] Step 4: Run:
  - `python -m unittest tests.test_sleep_coding tests.test_mvp_e2e -v`

### Task 3.4: Harden review blocking and repair return contract

**Files:**
- Modify: `app/agents/code_review_agent/application.py`
- Modify: `app/control/automation.py`
- Modify: `agents/code-review-agent/AGENTS.md`
- Test: `tests/test_review.py`
- Test: `tests/test_automation.py`

- [ ] Step 1: Add failing tests for:
  - wrong blocking projection
  - missing repair context on return
  - exceeding max rounds without escalation
- [ ] Step 2: Ensure `P0/P1` stays deterministic at gate level.
- [ ] Step 3: Keep finding generation model-first; do not convert review into hand-coded lint rules.
- [ ] Step 4: Run:
  - `python -m unittest tests.test_review tests.test_automation -v`

### Chunk 3 Regression

- [ ] Run:
  - `python -m unittest tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_sleep_coding_worker tests.test_review tests.test_automation tests.test_mvp_e2e -v`
- [ ] Update continuity docs before moving on.

---

## Chunk 4: Delivery Gate / Evidence / Notifications

### Objective

- 保证“完成”只能在 review 通过且证据充分时对外出现。

### Success Criteria

- 中间通知不伪装成完成。
- final delivery 必须 gated on approved review。
- 用户侧摘要和机器侧证据对齐。

### Task 4.1: Tighten final delivery gate

**Files:**
- Modify: `app/control/automation.py`
- Modify: `app/control/workflow.py`
- Test: `tests/test_automation.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: Add failing tests where coding is done but review or evidence is incomplete.
- [ ] Step 2: Prevent final delivery in those cases.
- [ ] Step 3: Ensure projected status remains truthful.
- [ ] Step 4: Run:
  - `python -m unittest tests.test_automation tests.test_mvp_e2e -v`

### Task 4.2: Standardize final evidence bundle

**Files:**
- Modify: `app/models/schemas.py`
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/code_review_agent/application.py`
- Modify: `app/control/automation.py`
- Test: `tests/test_sleep_coding.py`
- Test: `tests/test_review.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: Add failing tests for missing validation evidence, missing review linkage, or inconsistent token summary.
- [ ] Step 2: Normalize final evidence into one stable bundle reused by delivery and operator flows.
- [ ] Step 3: Reuse existing typed artifacts where possible.
- [ ] Step 4: Run:
  - `python -m unittest tests.test_sleep_coding tests.test_review tests.test_mvp_e2e -v`

### Task 4.3: Clean up notification semantics

**Files:**
- Modify if needed: `app/channel/notifications.py`
- Modify: `app/control/automation.py`
- Test: `tests/test_channel.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: Add failing tests for misleading notification titles/messages during mid-chain stages.
- [ ] Step 2: Make stage notifications clearly stage-scoped:
  - started
  - plan ready
  - review round
  - final delivery
- [ ] Step 3: Run:
  - `python -m unittest tests.test_channel tests.test_mvp_e2e -v`

### Chunk 4 Regression

- [ ] Run:
  - `python -m unittest tests.test_channel tests.test_sleep_coding tests.test_review tests.test_automation tests.test_mvp_e2e -v`
- [ ] Update continuity docs before moving on.

---

## Chunk 5: Live Readiness / Ops Proof / Rollout Discipline

### Objective

- 把“主链可用”变成可验证、可上线前自检、可交接的工程事实。

### Success Criteria

- live chain prerequisites 明确。
- diagnostics 足以支持 operator 判断。
- 每阶段有固定回归包和 handoff discipline。

### Task 5.1: Tighten live prerequisite checks

**Files:**
- Modify: `tests/test_live_chain.py`
- Modify: `app/infra/diagnostics.py`
- Test: `tests/test_live_chain.py`

- [ ] Step 1: Add at least one failing live prerequisite case for degraded integration.
- [ ] Step 2: Ensure skip/fail reasons are exact and actionable.
- [ ] Step 3: Run:
  - `python -m unittest tests.test_live_chain -v`

### Task 5.2: Add operator-focused diagnostics assertions

**Files:**
- Modify: `app/infra/diagnostics.py`
- Modify: `tests/test_runtime_components.py`

- [ ] Step 1: Add failing tests for missing component-level readiness explanations.
- [ ] Step 2: Ensure diagnostics tell an operator:
  - what is ready
  - what is degraded
  - what blocks live chain
- [ ] Step 3: Run:
  - `python -m unittest tests.test_runtime_components -v`

### Task 5.3: Lock rollout discipline into docs

**Files:**
- Modify: `STATUS.md`
- Modify if needed: `docs/architecture/current-mvp-status-summary.md`
- Add local handoff: `docs/internal/handoffs/YYYY-MM-DD-main-chain-hardening-handoff.md`

- [ ] Step 1: After each chunk, record exact completed items and verification output.
- [ ] Step 2: At end of each chunk, write the next starting point explicitly.
- [ ] Step 3: Keep local handoff synchronized with actual code/test state, not planned state.

### Final Regression Pack

- [ ] Run:
  - `python -m unittest tests.test_main_agent tests.test_gateway tests.test_control_context tests.test_session_registry tests.test_task_registry tests.test_sleep_coding_worker tests.test_sleep_coding tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e tests.test_framework_public_surface -v`
- [ ] If live prerequisites are ready, run:
  - `python -m unittest tests.test_live_chain -v`

## Final Done Criteria

- 主链入口具备 canonical identity、dedupe、lane safety。
- control task + event log 足以做恢复与排障。
- intake / coding / validation / review 的 timeout/retry/escalation 行为统一。
- `main-agent -> ralph -> review -> delivery` 在 deterministic gate 上闭环。
- final delivery 只发生在 review approved 之后，且证据完整。
- diagnostics 能支撑真实 operator 判断主链 readiness。
- 后续编码 agent 能逐条照计划执行，而不是依赖隐式上下文。
