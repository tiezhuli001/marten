# Main Chain Phase 5B Failure Drills And Live Readiness Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前主链从“架构上已收口”推进到“运行上可验收”，补齐 failure drill、live readiness matrix、主链闭环验收用例与 operator runbook。

**Architecture:** 继续坚持单主链和 `LLM + MCP + skill first`。代码只补 deterministic readiness、failure projection、operator evidence 和 live 验收 contract；不把 agent 的理解、规划、review 推理改写成流程 if/else。新增内容围绕 `diagnostics -> failure drill -> live acceptance -> operator runbook` 收口。

**Tech Stack:** FastAPI, Python 3.11+, unittest, current control/session/task stores, diagnostics service, builtin agents, MCP, skills.

---

## Relationship To Existing Docs

- Current continuity:
  - `STATUS.md`
  - `docs/internal/handoffs/2026-03-23-main-chain-phase-2-handoff.md`
- Current main-chain plans:
  - `docs/plans/2026-03-23-main-chain-engineering-hardening-detailed.md`
  - `docs/plans/2026-03-23-main-chain-phase-2-resume-and-ops-hardening.md`
- Relevant architecture:
  - `docs/architecture/agent-first-implementation-principles.md`
  - `docs/architecture/agent-runtime-contracts.md`
  - `docs/architecture/current-mvp-status-summary.md`

## Execution Rules

- 每个 task 必须按 `RED -> GREEN -> REFACTOR` 推进。
- 没有先失败的测试，不允许写生产代码。
- 每个 task 结束都要运行该 task 的最小测试集。
- 每个 chunk 结束都要运行该 chunk 的回归包。
- 每个 chunk 结束都要检查：
  - 主链目标是否偏移
  - 是否引入了替代 agent 推理的硬编码编排
  - 主链 E2E / live readiness 是否仍然完整
- 每次中断前必须更新 `STATUS.md` 和本地 handoff。

---

## Chunk 1: Live Readiness Matrix Hardening

### Objective

- 把 `/diagnostics/integrations` 从“组件状态列表”升级成真正可供 operator 判断的 live readiness matrix。

### Success Criteria

- diagnostics 能明确回答：
  - 哪些主链前置项是 blocking
  - 哪些是 degraded 但不阻断主链
  - 每个前置项的配置来源、检查方式、下一步动作
- live test 的 prerequisite skip 原因与 diagnostics 输出一致。

### Task 1.1: Tighten diagnostics component payloads for operator use

**Files:**
- Modify: `app/infra/diagnostics.py`
- Test: `tests/test_runtime_components.py`

- [x] Step 1: Write a failing diagnostics test that requires component payloads to include stable operator-facing fields for readiness inspection.
- [x] Step 2: Run:
  - `python -m unittest tests.test_runtime_components.IntegrationDiagnosticsTests -v`
- [x] Step 3: Confirm failure is due to missing readiness details rather than fixture setup.
- [x] Step 4: Add the minimal per-component readiness metadata needed by operators without turning diagnostics into orchestration logic.
- [x] Step 5: Re-run the targeted test and confirm green.

### Task 1.2: Align live prerequisite checks with diagnostics matrix

**Files:**
- Modify: `tests/test_live_chain.py`
- Modify if needed: `app/infra/diagnostics.py`
- Test: `tests/test_live_chain.py`

- [x] Step 1: Write a failing live prerequisite test requiring skip reasons to point back to explicit diagnostics components and actions.
- [x] Step 2: Run:
  - `python -m unittest tests.test_live_chain.LiveChainIntegrationTests -v`
- [x] Step 3: Confirm failure is caused by vague prerequisite reporting.
- [x] Step 4: Make live prerequisite gating consume the same readiness truth exposed by diagnostics.
- [x] Step 5: Re-run the targeted test and confirm green.

### Task 1.3: Expose main-chain acceptance summary in diagnostics

**Files:**
- Modify: `app/infra/diagnostics.py`
- Test: `tests/test_runtime_components.py`

- [x] Step 1: Write a failing test requiring `main_chain` diagnostics to expose an acceptance-oriented summary for operators.
- [x] Step 2: Run:
  - `python -m unittest tests.test_runtime_components.IntegrationDiagnosticsTests -v`
- [x] Step 3: Implement the smallest summary fields that answer “can I run live chain now and why”.
- [x] Step 4: Re-run the targeted test and confirm green.

### Chunk 1 Regression

- [x] Run:
  - `python -m unittest tests.test_runtime_components tests.test_live_chain -v`
- [x] Check drift:
  - diagnostics remain factual rather than aspirational
  - readiness logic did not duplicate agent reasoning
  - main-chain live prerequisite semantics are consistent
- [x] Update `STATUS.md`.
- [x] Update local handoff if stopping here.

---

## Chunk 2: Failure Drill Coverage On The Main Chain

### Objective

- 为主链关键失败面建立可重复验证的 failure drill，确保 control state、delivery semantics 和 diagnostics 能在失败场景下说真话。

### Success Criteria

- 至少覆盖以下失败面：
  - coding validation failure
  - blocking review exhaustion / `needs_attention`
  - delivery degraded but chain otherwise complete
- 每个 drill 都能从 task/control/diagnostics 看到一致的结论。

### Task 2.1: Add validation-failure drill assertions

**Files:**
- Modify: `tests/test_automation.py`
- Modify if needed: `app/control/automation.py`
- Test: `tests/test_automation.py`

- [x] Step 1: Write a failing test for a validation failure drill requiring consistent `failed` or `needs_attention` evidence across control and task payloads.
- [x] Step 2: Run:
  - `python -m unittest tests.test_automation.AutomationServiceTests -v`
- [x] Step 3: Confirm failure is due to missing or inconsistent failure-drill evidence.
- [x] Step 4: Tighten the minimal evidence / projection path without adding extra workflow states.
- [x] Step 5: Re-run the targeted test and confirm green.

### Task 2.2: Add review-exhaustion drill assertions

**Files:**
- Modify: `tests/test_automation.py`
- Modify if needed: `app/control/automation.py`
- Modify if needed: `app/control/task_registry.py`
- Test: `tests/test_automation.py`

- [x] Step 1: Write a failing test for a three-round blocking review drill that must end in truthful `needs_attention`.
- [x] Step 2: Run:
  - `python -m unittest tests.test_automation.AutomationServiceTests -v`
- [x] Step 3: Confirm failure is due to operator-facing drift, not test setup.
- [x] Step 4: Normalize the smallest control/task evidence needed for repeatable drill verification.
- [x] Step 5: Re-run the targeted test and confirm green.

### Task 2.3: Add degraded-delivery drill assertions

**Files:**
- Modify: `tests/test_automation.py`
- Modify if needed: `app/control/automation.py`
- Modify if needed: `app/infra/diagnostics.py`
- Test: `tests/test_automation.py`
- Test: `tests/test_runtime_components.py`

- [x] Step 1: Write a failing test for a chain that is otherwise complete but has degraded outbound delivery.
- [x] Step 2: Assert the drill distinguishes “task approved” from “channel degraded” without false failure semantics.
- [x] Step 3: Run:
  - `python -m unittest tests.test_automation tests.test_runtime_components -v`
- [x] Step 4: Implement the minimal truthful projection for degraded delivery.
- [x] Step 5: Re-run the targeted tests and confirm green.

### Chunk 2 Regression

- [x] Run:
  - `python -m unittest tests.test_automation tests.test_runtime_components tests.test_mvp_e2e -v`
- [x] Check drift:
  - failure drills validate deterministic boundaries, not agent cognition
  - no fake success or fake failure semantics were introduced
  - main chain still resolves to a single truthful terminal state
- [x] Update `STATUS.md`.
- [x] Update local handoff if stopping here.

---

## Chunk 3: Main-Chain Closed-Loop Acceptance And Operator Runbook

### Objective

- 把主链闭环验收和 operator re-entry 路径写实，形成“能跑、能看、能接手”的工程交付面。

### Success Criteria

- 形成覆盖 `request -> coding -> review changes requested -> repair resume -> approve -> delivery` 的闭环验收测试或夹具。
- operator runbook 能回答：
  - 看哪个 endpoint / task payload
  - 如何区分 blocked、degraded、needs_attention、completed
  - 从哪里 resume / handoff / 人工接管

### Task 3.1: Add a closed-loop repair-resume acceptance test

**Files:**
- Modify: `tests/test_mvp_e2e.py`
- Modify if needed: `tests/test_automation.py`
- Modify if needed: `app/control/automation.py`
- Test: `tests/test_mvp_e2e.py`

- [x] Step 1: Write a failing end-to-end test covering review changes requested followed by repair resume and final approval.
- [x] Step 2: Run:
  - `python -m unittest tests.test_mvp_e2e -v`
- [x] Step 3: Confirm failure is a real main-chain gap rather than fixture mismatch.
- [x] Step 4: Implement the smallest safe repair needed for the closed-loop acceptance path.
- [x] Step 5: Re-run the targeted test and confirm green.

### Task 3.2: Write an operator-facing runbook from the current runtime truth

**Files:**
- Create: `docs/architecture/main-chain-operator-runbook.md`
- Modify if needed: `docs/README.md`
- Modify if needed: `docs/architecture/current-mvp-status-summary.md`

- [x] Step 1: Draft the runbook around current runtime truth, not aspirational future design.
- [x] Step 2: Include concrete sections for readiness check, failure drill reading, resume paths, manual handoff, and live-chain prerequisites.
- [x] Step 3: Link the runbook from the appropriate docs entry points.
- [x] Step 4: Re-read the linked docs and confirm they are consistent with implementation.

### Task 3.3: Record main-chain failure-drill baseline in local continuity docs

**Files:**
- Modify: `STATUS.md`
- Modify: `docs/internal/handoffs/YYYY-MM-DD-main-chain-phase-5b-handoff.md`

- [x] Step 1: Update continuity docs with implemented drills, operator surfaces, and re-entry commands.
- [x] Step 2: Verify completed work is not still described as pending.

### Chunk 3 Regression

- [x] Run:
  - `python -m unittest tests.test_automation tests.test_runtime_components tests.test_mvp_e2e -v`
- [x] If live prerequisites are ready, run:
  - `python -m unittest tests.test_live_chain -v`
- [x] Check drift:
  - closed-loop acceptance still preserves `LLM + MCP + skill first`
  - runbook matches current runtime truth
  - live chain remains green when prerequisites are available
- [x] Update `STATUS.md`.
- [x] Update local handoff.

---

## Final Regression Pack

- [x] Run:
  - `python -m unittest tests.test_main_agent tests.test_gateway tests.test_control_context tests.test_session_registry tests.test_task_registry tests.test_sleep_coding_worker tests.test_sleep_coding tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e tests.test_framework_public_surface -v`
- [x] If live prerequisites are ready, run:
  - `python -m unittest tests.test_live_chain -v`
- [x] Update:
  - `STATUS.md`
  - `docs/internal/handoffs/YYYY-MM-DD-main-chain-phase-5b-handoff.md`

## Final Done Criteria

- diagnostics exposes a stable live readiness matrix for operators.
- live prerequisite checks and diagnostics tell the same truth.
- failure drills cover the key main-chain failure surfaces with consistent evidence.
- closed-loop repair-resume acceptance remains green.
- operator runbook exists and matches current runtime truth.
- full regression pack remains green, and live chain remains green when prerequisites are present.
