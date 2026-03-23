# Main Chain Engineering Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `Marten` 从“能跑通主链”推进到“入口到交付工程可用、可恢复、可诊断”的单链路 agent platform core，同时坚持 `LLM + MCP + skill first`。

**Architecture:** 以单条 canonical chain 为核心：`Inbound Gateway -> Canonical Session Context -> Main Agent Intake -> Control Task -> Ralph Execution Loop -> Review Loop -> Delivery Gate -> Final Delivery`。代码只收口入口治理、会话/事件/状态、超时/恢复/门禁；理解、规划、review 推理和 skill/MCP 选择仍优先交给 agent。

**Tech Stack:** FastAPI, Python 3.11+, SQLite-backed control/session stores, builtin agents (`main-agent`, `ralph`, `code-review-agent`), MCP, skills, existing unittest suite.

---

## Scope Guardrails

- 不扩成通用多 agent 编排平台。
- 不引入额外长期并行 agent 拓扑。
- 不把 agent 的认知决策回写成大量关键词路由或硬编码规则。
- 不优先做 RAG / Milvus 扩展；主链工程可用性优先。
- 不在 `main` 分支直接做实现。

## File Map

### Core runtime and control-plane files

- Modify: `app/control/gateway.py`
- Modify: `app/control/workflow.py`
- Modify: `app/control/context.py`
- Modify: `app/control/session_registry.py`
- Modify: `app/control/task_registry.py`
- Modify: `app/control/task_store.py`
- Modify: `app/control/task_events.py`
- Modify: `app/control/automation.py`
- Modify: `app/control/sleep_coding_worker.py`
- Modify: `app/main.py`
- Modify: `app/api/routes.py`
- Modify: `app/infra/diagnostics.py`
- Modify: `app/infra/scheduler.py`
- Modify: `app/models/schemas.py`

### Builtin agent runtime files

- Modify: `app/agents/main_agent/application.py`
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/ralph/workflow.py`
- Modify: `app/agents/code_review_agent/application.py`
- Modify later as needed: `agents/main-agent/AGENTS.md`
- Modify later as needed: `agents/ralph/AGENTS.md`
- Modify later as needed: `agents/code-review-agent/AGENTS.md`

### Tests

- Modify: `tests/test_gateway.py`
- Modify: `tests/test_control_context.py`
- Modify: `tests/test_session_registry.py`
- Modify: `tests/test_task_registry.py`
- Modify: `tests/test_sleep_coding_worker.py`
- Modify: `tests/test_main_agent.py`
- Modify: `tests/test_sleep_coding.py`
- Modify: `tests/test_review.py`
- Modify: `tests/test_automation.py`
- Modify: `tests/test_runtime_components.py`
- Modify: `tests/test_mvp_e2e.py`
- Modify: `tests/test_live_chain.py`

### Docs / continuity

- Modify: `docs/architecture/current-mvp-status-summary.md`
- Modify if needed: `docs/architecture/agent-system-overview.md`
- Modify if needed: `docs/architecture/agent-runtime-contracts.md`
- Modify: `STATUS.md` in workspace root
- Add local handoff: `docs/internal/handoffs/YYYY-MM-DD-<topic>-handoff.md`

---

## Chunk 1: Gateway, Session, And Lane Hardening

### Task 1: Define canonical inbound context and session key rules

**Files:**
- Modify: `app/control/gateway.py`
- Modify: `app/control/context.py`
- Modify: `app/control/session_registry.py`
- Modify: `app/models/schemas.py`
- Test: `tests/test_gateway.py`
- Test: `tests/test_control_context.py`
- Test: `tests/test_session_registry.py`

- [ ] Step 1: Write a failing test for stable canonical session resolution across `gateway/message`, `main-agent/intake`, and Feishu/webhook entry paths.
- [ ] Step 2: Run `python -m unittest tests.test_gateway tests.test_control_context tests.test_session_registry -v` and confirm the new case fails for the expected reason.
- [ ] Step 3: Implement a single canonical session-key / chain-key derivation path so the same conversation does not fork hidden sessions.
- [ ] Step 4: Preserve `active_agent`, `delivery_endpoint_id`, `request_id`, and chain continuity in session payload updates.
- [ ] Step 5: Re-run `python -m unittest tests.test_gateway tests.test_control_context tests.test_session_registry -v` and confirm green.

### Task 2: Add inbound dedupe and per-session lane semantics without breaking single-chain behavior

**Files:**
- Modify: `app/control/gateway.py`
- Modify: `app/control/workflow.py`
- Modify: `app/control/session_registry.py`
- Modify if needed: `app/infra/scheduler.py`
- Test: `tests/test_gateway.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: Write a failing test showing duplicate inbound delivery for the same message/request is ignored or collapsed to one control-chain execution.
- [ ] Step 2: Run `python -m unittest tests.test_gateway tests.test_mvp_e2e -v` and verify the new dedupe case fails before implementation.
- [ ] Step 3: Implement a minimal dedupe key strategy for supported inbound surfaces, scoped tightly enough to avoid false positives.
- [ ] Step 4: Add per-session serialization semantics so same-session work is not processed in conflicting parallel branches.
- [ ] Step 5: Re-run `python -m unittest tests.test_gateway tests.test_mvp_e2e -v` and confirm green.

### Task 3: Harden fast-ack + async-follow-up entry behavior

**Files:**
- Modify: `app/control/workflow.py`
- Modify: `app/channel/feishu.py`
- Modify: `app/api/routes.py`
- Test: `tests/test_feishu.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: Write a failing test for a fast inbound acknowledgment that still records enough state for later automation follow-up and resume.
- [ ] Step 2: Run `python -m unittest tests.test_feishu tests.test_mvp_e2e -v` and confirm failure is due to missing/incorrect ack semantics.
- [ ] Step 3: Implement explicit “started / accepted / follow-up-triggered” semantics without faking final success.
- [ ] Step 4: Make sure follow-up result payloads include concrete task linkage for resume and diagnostics.
- [ ] Step 5: Re-run `python -m unittest tests.test_feishu tests.test_mvp_e2e -v`.

---

## Chunk 2: Control Task, Event Log, Timeout, And Recovery Hardening

### Task 4: Make control-task event history the resume backbone

**Files:**
- Modify: `app/control/task_registry.py`
- Modify: `app/control/task_store.py`
- Modify: `app/control/task_events.py`
- Modify: `app/models/schemas.py`
- Test: `tests/test_task_registry.py`
- Test: `tests/test_automation.py`

- [ ] Step 1: Write a failing test proving a paused/interrupted chain can reconstruct the next safe action from control task + events without hidden in-memory context.
- [ ] Step 2: Run `python -m unittest tests.test_task_registry tests.test_automation -v` and confirm the new recovery case fails first.
- [ ] Step 3: Tighten event payload requirements so handoff, retry, review-return, delivery-complete, and failure-escalation events are sufficient for replay/recovery.
- [ ] Step 4: Add typed surface where necessary for event consumers, but do not duplicate the entire task payload into every event.
- [ ] Step 5: Re-run `python -m unittest tests.test_task_registry tests.test_automation -v`.

### Task 5: Unify timeout/retry/escalation policy across main chain services

**Files:**
- Modify: `app/control/automation.py`
- Modify: `app/control/sleep_coding_worker.py`
- Modify: `app/agents/main_agent/application.py`
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/code_review_agent/application.py`
- Test: `tests/test_main_agent.py`
- Test: `tests/test_sleep_coding.py`
- Test: `tests/test_review.py`
- Test: `tests/test_runtime_components.py`

- [ ] Step 1: Write failing tests for one representative timeout/retry/escalation path in each stage: intake, coding execution, validation, review command.
- [ ] Step 2: Run `python -m unittest tests.test_main_agent tests.test_sleep_coding tests.test_review tests.test_runtime_components -v` and verify failures are expected.
- [ ] Step 3: Normalize timeout and retry handling so every boundary yields explicit task/event status instead of silent hanging or ambiguous exceptions.
- [ ] Step 4: Ensure repeated failure exits to `failed` or `needs_attention` with concrete evidence instead of endless loop retries.
- [ ] Step 5: Re-run `python -m unittest tests.test_main_agent tests.test_sleep_coding tests.test_review tests.test_runtime_components -v`.

### Task 6: Make diagnostics and health endpoints reflect real readiness

**Files:**
- Modify: `app/infra/diagnostics.py`
- Modify: `app/api/routes.py`
- Modify: `app/main.py`
- Test: `tests/test_runtime_components.py`
- Test: `tests/test_live_chain.py`

- [ ] Step 1: Write a failing test requiring diagnostics to expose the readiness of gateway, GitHub MCP, Ralph execution, review skill, and channel delivery prerequisites.
- [ ] Step 2: Run `python -m unittest tests.test_runtime_components tests.test_live_chain -v` and watch the new expectation fail.
- [ ] Step 3: Implement readiness reporting with clear “ok / degraded / unavailable” states and concrete reasons.
- [ ] Step 4: Keep `/health` cheap and `/diagnostics/integrations` detailed; do not turn health into an expensive orchestration run.
- [ ] Step 5: Re-run `python -m unittest tests.test_runtime_components tests.test_live_chain -v`.

---

## Chunk 3: Main-Agent, Ralph, And Review Loop Hardening

### Task 7: Tighten main-agent intake without turning it into a rules engine

**Files:**
- Modify: `app/agents/main_agent/application.py`
- Modify: `agents/main-agent/AGENTS.md`
- Test: `tests/test_main_agent.py`
- Test: `tests/test_gateway.py`

- [ ] Step 1: Write failing tests for the smallest set of misroutes that actually harm the engineering main chain: swallowed coding request, over-eager coding route, missing clarification boundary.
- [ ] Step 2: Run `python -m unittest tests.test_main_agent tests.test_gateway -v` and verify the new cases fail for routing/contract reasons.
- [ ] Step 3: Adjust intake decision rules and prompts so `main-agent` remains chat-first but does not drop real coding work.
- [ ] Step 4: Keep heuristic routing minimal; prefer LLM output + schema enforcement over branching growth.
- [ ] Step 5: Re-run `python -m unittest tests.test_main_agent tests.test_gateway -v`.

### Task 8: Harden Ralph execution loop around plan, validate, and recover

**Files:**
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/ralph/workflow.py`
- Modify: `agents/ralph/AGENTS.md`
- Test: `tests/test_sleep_coding.py`
- Test: `tests/test_sleep_coding_worker.py`

- [ ] Step 1: Write failing tests for resume-after-partial-progress, validation evidence requirements, and PR/review handoff completeness.
- [ ] Step 2: Run `python -m unittest tests.test_sleep_coding tests.test_sleep_coding_worker -v` and confirm the new cases fail.
- [ ] Step 3: Ensure Ralph can resume from persisted artifacts/control events without re-planning the whole task from scratch.
- [ ] Step 4: Require explicit validation evidence before review entry unless the gap is surfaced in structured output.
- [ ] Step 5: Re-run `python -m unittest tests.test_sleep_coding tests.test_sleep_coding_worker -v`.

### Task 9: Harden review loop, blocking policy, and repair return path

**Files:**
- Modify: `app/agents/code_review_agent/application.py`
- Modify: `app/control/automation.py`
- Modify: `agents/code-review-agent/AGENTS.md`
- Test: `tests/test_review.py`
- Test: `tests/test_automation.py`

- [ ] Step 1: Write failing tests for the blocking/non-blocking contract, repair round counting, and review-return-to-Ralph recovery.
- [ ] Step 2: Run `python -m unittest tests.test_review tests.test_automation -v` and confirm the new loop-control cases fail first.
- [ ] Step 3: Keep review reasoning model-first, but make the control-plane gate deterministic: `P0/P1` blocking, max rounds enforced, explicit final state.
- [ ] Step 4: Make sure the return path carries enough repair context without overloading runtime with review-specific branching.
- [ ] Step 5: Re-run `python -m unittest tests.test_review tests.test_automation -v`.

---

## Chunk 4: Delivery Gate, Notifications, And Evidence-Backed Completion

### Task 10: Make final delivery a strict gate, not a best-effort notification

**Files:**
- Modify: `app/control/automation.py`
- Modify: `app/control/workflow.py`
- Modify if needed: `app/channel/notifications.py`
- Test: `tests/test_automation.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: Write a failing test where coding appears complete but final delivery must still be blocked because review approval or evidence is missing.
- [ ] Step 2: Run `python -m unittest tests.test_automation tests.test_mvp_e2e -v` and verify the new delivery-gate case fails correctly.
- [ ] Step 3: Tighten final delivery to require approved review state, consistent control-task state, and available evidence summary.
- [ ] Step 4: Ensure intermediate notifications never impersonate final success.
- [ ] Step 5: Re-run `python -m unittest tests.test_automation tests.test_mvp_e2e -v`.

### Task 11: Standardize user-facing and machine-facing completion evidence

**Files:**
- Modify: `app/models/schemas.py`
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/code_review_agent/application.py`
- Modify: `app/control/automation.py`
- Test: `tests/test_sleep_coding.py`
- Test: `tests/test_review.py`
- Test: `tests/test_mvp_e2e.py`

- [ ] Step 1: Write failing tests for a completion summary that is missing validation evidence, token usage, or review decision linkage.
- [ ] Step 2: Run `python -m unittest tests.test_sleep_coding tests.test_review tests.test_mvp_e2e -v` and confirm expected failure.
- [ ] Step 3: Normalize the final evidence bundle so downstream delivery and operators see the same truth.
- [ ] Step 4: Do not add a new orchestration layer; re-use existing typed artifacts and review outputs.
- [ ] Step 5: Re-run `python -m unittest tests.test_sleep_coding tests.test_review tests.test_mvp_e2e -v`.

---

## Chunk 5: Live Readiness, Rollout, And Operational Proof

### Task 12: Strengthen live-chain prerequisites and failure drills

**Files:**
- Modify: `tests/test_live_chain.py`
- Modify: `app/infra/diagnostics.py`
- Modify if needed: `docs/architecture/current-mvp-status-summary.md`

- [ ] Step 1: Write a failing live-prerequisite test for one missing integration or degraded dependency state that currently slips through.
- [ ] Step 2: Run `python -m unittest tests.test_live_chain -v` with a controlled precondition and confirm the failure signal is actionable.
- [ ] Step 3: Tighten prerequisite reporting so live-chain execution is either safe to run or clearly skipped with exact reasons.
- [ ] Step 4: Re-run `python -m unittest tests.test_live_chain -v`.

### Task 13: Run canonical regression packs per phase and refresh continuity docs

**Files:**
- Modify: `STATUS.md`
- Add local handoff: `docs/internal/handoffs/YYYY-MM-DD-main-chain-hardening-handoff.md`

- [ ] Step 1: After each chunk, run the narrow regression pack for that chunk and record exact output.
- [ ] Step 2: At end of each phase, run:
  - `python -m unittest tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e tests.test_framework_public_surface -v`
- [ ] Step 3: Before claiming phase completion, update `STATUS.md` with:
  - current goal
  - completed work
  - in progress work
  - next actions
  - blockers
  - verification commands and latest results
- [ ] Step 4: Write a fresh local handoff under `docs/internal/handoffs/` with the exact recovery point for the next agent.

---

## Verification Baseline

- [ ] `python -m unittest tests.test_gateway tests.test_control_context tests.test_session_registry -v`
- [ ] `python -m unittest tests.test_task_registry tests.test_sleep_coding_worker tests.test_automation -v`
- [ ] `python -m unittest tests.test_main_agent tests.test_sleep_coding tests.test_review -v`
- [ ] `python -m unittest tests.test_runtime_components tests.test_mvp_e2e tests.test_framework_public_surface -v`
- [ ] `python -m unittest tests.test_live_chain -v`

## Done Criteria

- Inbound gateway has canonical request/session identity, dedupe, and same-session safety.
- Control tasks and events are sufficient for resume/recovery without hidden conversation context.
- Main-agent, Ralph, and review loop respect `LLM + MCP + skill first` while deterministic gates own timeout, retry, escalation, and delivery.
- Final delivery is evidence-backed and strictly gated on approved review.
- Diagnostics can tell an operator whether the main chain is genuinely runnable.
- A new agent can continue implementation from `architecture + plan + STATUS.md + local handoff` without oral context.
