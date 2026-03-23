# Main Chain Phase 2 Resume And Ops Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有主链硬化基础上，继续把 `Ralph -> Review -> Delivery` 收口成可恢复、可交付、可运维的工程链路。

**Architecture:** 继续坚持单主链和 `LLM + MCP + skill first`。代码只补持久化事实、gate、resume、evidence、operator semantics，不把 agent 推理替换成硬编码流程。下一阶段的中心是：`persisted facts -> Ralph resume -> review return -> truthful delivery / ops status`。

**Tech Stack:** FastAPI, Python 3.11+, SQLite, builtin agents, MCP, skills, unittest, current control/session/task stores.

---

## Relationship To Existing Docs

- Current continuity:
  - `STATUS.md`
  - `docs/internal/handoffs/2026-03-23-main-chain-hardening-handoff.md`
- Previous hardening plan:
  - `docs/plans/2026-03-23-main-chain-engineering-hardening.md`
  - `docs/plans/2026-03-23-main-chain-engineering-hardening-detailed.md`
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
  - 是否引入了对 agent 推理的硬编码替代
  - 主链 E2E 是否仍然完整
- 每次中断前必须更新 `STATUS.md` 和本地 handoff。

---

## Chunk 1: Ralph Resume From Persisted Facts

### Objective

- 让 `Ralph` 真正能从已经持久化的 task / control / PR / review 事实继续执行，而不是默认重新推导整条链。

### Success Criteria

- 已计划、已验证、已有 PR、已收 review 返回的 task 都能在下一次动作时正确 resume。
- resume 优先使用已持久化事实，不重复开 PR、不重复生成无意义 plan、不丢 review handoff。
- `SleepCodingWorker` 和 `AutomationService` 对 resume 的理解一致。

### Task 1.1: Resume planned task without regenerating plan

**Files:**
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/ralph/workflow.py`
- Test: `tests/test_sleep_coding.py`

- [x] Step 1: Write a failing test for resuming a task that is already `awaiting_confirmation` and already has a persisted plan.
- [x] Step 2: Run:
  - `python -m unittest tests.test_sleep_coding.SleepCodingServiceTests.test_resume_planned_task_reuses_persisted_plan -v`
- [x] Step 3: Confirm failure is caused by unnecessary plan regeneration or state loss.
- [x] Step 4: Implement the smallest resume path that reuses persisted plan/task payload.
- [x] Step 5: Re-run the single test and confirm green.

### Task 1.2: Resume after validation without rerunning the wrong stage

**Files:**
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/ralph/workflow.py`
- Test: `tests/test_sleep_coding.py`

- [x] Step 1: Write a failing test for resuming a task that already has persisted validation output.
- [x] Step 2: Run:
  - `python -m unittest tests.test_sleep_coding.SleepCodingServiceTests.test_resume_after_validation_reuses_validation_result -v`
- [x] Step 3: Confirm failure is caused by re-entering the wrong stage or dropping validation evidence.
- [x] Step 4: Make resume prefer persisted validation facts and only continue from the next valid stage.
- [x] Step 5: Re-run the single test and confirm green.

### Task 1.3: Resume with existing PR and review handoff intact

**Files:**
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/ralph/workflow.py`
- Modify if needed: `app/agents/ralph/progress.py`
- Test: `tests/test_sleep_coding.py`
- Test: `tests/test_mvp_e2e.py`

- [x] Step 1: Write a failing test for a task that already has a PR and should not create a second PR on resume.
- [x] Step 2: Write a failing test for a task with existing `review_handoff` that must remain complete after resume.
- [x] Step 3: Run:
  - `python -m unittest tests.test_sleep_coding tests.test_mvp_e2e -v`
- [x] Step 4: Fix resume so it prioritizes persisted PR and handoff facts over re-derivation.
- [x] Step 5: Re-run the failing tests and confirm green.

### Task 1.4: Resume correctly after review requested changes

**Files:**
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/ralph/workflow.py`
- Modify if needed: `app/control/automation.py`
- Test: `tests/test_sleep_coding.py`
- Test: `tests/test_automation.py`

- [x] Step 1: Write a failing test for a task that already received `review_returned=changes_requested` and should resume coding with repair context.
- [x] Step 2: Ensure the failing test asserts repair context comes from persisted review/control facts, not from hidden in-memory state.
- [x] Step 3: Run:
  - `python -m unittest tests.test_sleep_coding tests.test_automation -v`
- [x] Step 4: Implement the smallest repair resume path that preserves review round and repair context.
- [x] Step 5: Re-run the failing tests and confirm green.

### Chunk 1 Regression

- [x] Run:
  - `python -m unittest tests.test_sleep_coding tests.test_sleep_coding_worker tests.test_automation tests.test_mvp_e2e -v`
- [x] Check drift:
  - resume logic did not bypass review gate
  - no duplicate PR creation was introduced
  - no additional hard-coded orchestration branch replaced agent reasoning
- [x] Update `STATUS.md`.
- [x] Update local handoff if stopping here.

---

## Chunk 2: Review Return Contract And Validation Evidence Gate

### Objective

- 让 `review -> repair -> review` 形成明确的 persisted contract，并且 review 入口必须看到验证证据或结构化 gap。

### Success Criteria

- review 返回给 Ralph 的信息足够执行修复，不依赖隐式上下文。
- 没有验证证据或显式验证缺口时，不允许进入 review handoff。
- blocking、repair round、review return 在 control task 和 domain task 上是一致的。

### Task 2.1: Require explicit validation evidence before review handoff

**Files:**
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/ralph/workflow.py`
- Modify if needed: `app/agents/ralph/progress.py`
- Test: `tests/test_sleep_coding.py`
- Test: `tests/test_mvp_e2e.py`

- [x] Step 1: Write a failing test where task tries to enter review without validation result and without structured validation gap.
- [x] Step 2: Run:
  - `python -m unittest tests.test_sleep_coding tests.test_mvp_e2e -v`
- [x] Step 3: Confirm failure is caused by missing gate, not fixture setup.
- [x] Step 4: Add the minimal gate that blocks review handoff unless evidence is present.
- [x] Step 5: Re-run the failing tests and confirm green.

### Task 2.2: Harden review return payload for repair execution

**Files:**
- Modify: `app/agents/code_review_agent/application.py`
- Modify: `app/control/task_registry.py`
- Modify if needed: `app/models/schemas.py`
- Test: `tests/test_review.py`
- Test: `tests/test_automation.py`

- [x] Step 1: Write a failing test for `review_returned` without enough repair context for Ralph.
- [x] Step 2: Add assertions for:
  - blocking decision
  - repair strategy / summary
  - next owner
  - review round / review id continuity
- [x] Step 3: Run:
  - `python -m unittest tests.test_review tests.test_automation -v`
- [x] Step 4: Tighten persisted review return payloads and any typed accessors needed by resume paths.
- [x] Step 5: Re-run the failing tests and confirm green.

### Task 2.3: Keep blocking and escalation deterministic at the gate

**Files:**
- Modify: `app/agents/code_review_agent/application.py`
- Modify: `app/control/automation.py`
- Test: `tests/test_review.py`
- Test: `tests/test_automation.py`

- [x] Step 1: Write a failing test where blocking findings are projected inconsistently across review and automation layers.
- [x] Step 2: Write a failing test where max repair rounds are exceeded but persisted control facts are incomplete.
- [x] Step 3: Run:
  - `python -m unittest tests.test_review tests.test_automation -v`
- [x] Step 4: Normalize gate-level status/evidence without converting review into hard-coded lint rules.
- [x] Step 5: Re-run the failing tests and confirm green.

### Chunk 2 Regression

- [x] Run:
  - `python -m unittest tests.test_sleep_coding tests.test_review tests.test_automation tests.test_mvp_e2e -v`
- [x] Check drift:
  - review remains model-first for findings
  - new validation gate does not create false “completed” semantics
  - repair return still stays on single main chain
- [x] Update `STATUS.md`.
- [x] Update local handoff if stopping here.

---

## Chunk 3: Delivery Truthfulness And Operator Semantics

### Objective

- 把“完成 / 失败 / needs_attention” 的对外语义完全做实，让 operator 和用户都不会被中间态误导。

### Success Criteria

- 没有 `approved review + evidence` 就没有 final delivery。
- `needs_attention` / `failed` / `completed` 通知和 control 状态严格对齐。
- operator 可以从 control task 和 diagnostics 直接判断链路停在哪一层。

### Task 3.1: Prevent misleading delivery on incomplete evidence

**Files:**
- Modify: `app/control/automation.py`
- Modify if needed: `app/channel/delivery.py`
- Test: `tests/test_automation.py`
- Test: `tests/test_mvp_e2e.py`

- [x] Step 1: Write a failing test where coding is done but review status or evidence bundle is incomplete and final delivery still fires.
- [x] Step 2: Run:
  - `python -m unittest tests.test_automation tests.test_mvp_e2e -v`
- [x] Step 3: Confirm failure is a delivery gate gap.
- [x] Step 4: Tighten the final delivery gate without changing the single main-chain flow.
- [x] Step 5: Re-run the failing tests and confirm green.

### Task 3.2: Standardize operator-facing terminal evidence

**Files:**
- Modify: `app/models/schemas.py`
- Modify: `app/control/automation.py`
- Modify if needed: `app/control/task_registry.py`
- Test: `tests/test_automation.py`
- Test: `tests/test_runtime_components.py`

- [x] Step 1: Write a failing test for missing or inconsistent terminal evidence on:
  - `completed`
  - `failed`
  - `needs_attention`
- [x] Step 2: Run:
  - `python -m unittest tests.test_automation tests.test_runtime_components -v`
- [x] Step 3: Normalize one stable evidence bundle / operator view for terminal states.
- [x] Step 4: Re-run the failing tests and confirm green.

### Task 3.3: Keep diagnostics aligned with real operator questions

**Files:**
- Modify: `app/infra/diagnostics.py`
- Modify if needed: `tests/test_runtime_components.py`
- Modify if needed: `tests/test_live_chain.py`

- [x] Step 1: Write a failing diagnostics test for a degraded state that should clearly answer:
  - what is ready
  - what is blocked
  - where operator should look next
- [x] Step 2: Run:
  - `python -m unittest tests.test_runtime_components tests.test_live_chain -v`
- [x] Step 3: Add the minimal readiness explanation needed by operator flows.
- [x] Step 4: Re-run the failing tests and confirm green.

### Chunk 3 Regression

- [x] Run:
  - `python -m unittest tests.test_automation tests.test_runtime_components tests.test_mvp_e2e tests.test_live_chain -v`
- [x] Check drift:
  - no fake “done” semantics leaked back in
  - diagnostics still reflect actual runtime, not aspirational config
  - live chain remains green if prerequisites are available
- [x] Update `STATUS.md`.
- [x] Update local handoff if stopping here.

---

## Final Regression Pack

- [x] Run:
  - `python -m unittest tests.test_main_agent tests.test_gateway tests.test_control_context tests.test_session_registry tests.test_task_registry tests.test_sleep_coding_worker tests.test_sleep_coding tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e tests.test_framework_public_surface -v`
- [x] If live prerequisites are ready, run:
  - `python -m unittest tests.test_live_chain -v`
- [x] Update:
  - `STATUS.md`
  - `docs/internal/handoffs/YYYY-MM-DD-main-chain-phase-2-handoff.md`

## Final Done Criteria

- Ralph can resume from persisted plan / validation / PR / review-return facts.
- Review handoff requires validation evidence or explicit structured gap.
- Review return payloads are sufficient for repair execution without hidden state.
- Final delivery only happens with approved review and complete evidence.
- Operator-facing terminal states are truthful and consistent across control tasks, notifications, and diagnostics.
- Full regression pack remains green, and live chain remains green when prerequisites are present.
