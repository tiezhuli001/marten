# Concurrency Reduction Follow-up Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏单活、幂等和 queued/busy 可诊断性的前提下，重新评估 `Marten` 并发控制是否还能继续做减法。

**Architecture:** 当前并发控制分为三层：`Gateway` 进程内 session lock、SQLite `execution_lane`、worker claim lease。根据 2026-03-25 的验证结果，`Gateway` session lock 目前承载了同 session 并发幂等行为，不能在没有替代机制时直接删除；后续减法必须建立在更强 harness 和明确替代方案之上。

**Tech Stack:** Python 3.11+, SQLite, unittest, FastAPI control-plane, worker poll loop.

## Execution Result

> 更新时间：2026-03-25
> 执行结论：本 follow-up 已完成到“并发层职责冻结、删减候选逐层复核、当前没有安全可删层”的目标；本轮不继续强删 `Gateway` session lock、`execution_lane` 或 worker claim lease。

- 已补并发行为 harness：
  - `tests.test_session_registry::test_acquire_same_queued_task_id_is_idempotent`
  - `tests.test_sleep_coding_worker::test_poll_once_claims_queued_issue_after_lane_is_released`
- 结合既有 harness，当前结论更明确：
  - `Gateway` session lock 仍负责同 session 并发幂等，不能直接删除
  - `execution_lane` 负责 active/queued 的主链单活 truth
  - worker claim lease 负责 issue poll / lease / retry 生命周期
  - `execution_lane` 与 claim lease 不是简单重复表达
- 本轮未做任何锁层删减；删减前提仍然是先有替代机制和更强证据
- 最新 fresh live 证据：
  - issue `#233`
  - sleep-coding control task `beb885c0-df10-4984-927f-fea4e899aa32`
  - sleep-coding task `3fabd549-0fc5-44ad-ae63-14af3904f5af`
  - review run `073256b1-d6c3-4d46-884d-5047cb1875ce`
  - PR `#234`
  - live 完成后 `execution_lane.active_task_id == None`

---

## Chunk 1: Freeze Behavior Harness

### Task 1.1: Lock gateway/session/worker behavior

**Files:**
- Modify: `tests/test_gateway.py`
- Modify: `tests/test_session_registry.py`
- Modify: `tests/test_sleep_coding_worker.py`

- [x] Step 1: 保持并扩展当前行为测试：
  - 同 session 同 message 并发进入必须幂等
  - execution lane 删除 queued entry 时不能影响 active task
  - worker 在 lane 被其他任务占用时只能标记 queued，不能丢任务
- [x] Step 2: Run:
  - `python -m unittest tests.test_gateway tests.test_session_registry tests.test_sleep_coding_worker -v`

## Chunk 2: Evaluate Removal Candidates One Layer At A Time

### Task 2.1: Re-check gateway session lock

**Files:**
- Modify if needed: `app/control/gateway.py`
- Modify if needed: `app/control/session_registry.py`

- [x] Step 1: 先证明若移除 `Gateway` session lock，幂等和 dedupe 是否还能成立。
- [x] Step 2: 只有在替代机制能接住同 session 同 message 并发幂等时，才允许删除该锁。
- [x] Step 3: 若不能成立，明确保留并记录原因，不继续强删。

### Task 2.2: Re-check execution lane vs worker claim overlap

**Files:**
- Modify if needed: `app/control/session_registry.py`
- Modify if needed: `app/control/sleep_coding_worker.py`
- Modify if needed: `app/control/sleep_coding_worker_store.py`

- [x] Step 1: 评估 `execution_lane` 和 claim lease 是否存在真实重复表达。
- [x] Step 2: 若选择删减，必须一次只收敛一层。
- [x] Step 3: 每次删减后都回跑：
  - `python -m unittest tests.test_gateway tests.test_session_registry tests.test_sleep_coding_worker -v`
  - `python scripts/run_test_suites.py regression`

## Chunk 3: Final Verification

### Task 3.1: Re-run live after any concurrency change

**Files:**
- Modify if needed: `STATUS.md`

- [x] Step 1: Run:
  - `python scripts/run_test_suites.py live`
- [x] Step 2: 记录 live 完成后：
  - `execution_lane.active_task_id`
  - queued tasks truth
  - 最新 issue / task / review / PR evidence
