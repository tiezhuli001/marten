# Live Chain Root Cause Correction Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `Marten` 的真实链路修回“失败暴露真实原因、只保留必要重试、不用宽松降级掩盖问题”的工程原则，同时完成相关文档细节同步。

**Architecture:** 保持唯一主链 `Feishu/API -> main-agent -> ralph -> code-review-agent -> delivery` 不变，但收紧 runtime 边界：传输级问题只做必要重试，关键 agent 步骤失败后显式失败并保留证据，不默认切到 heuristic success path。agent 间交互优先收敛成“状态事件 + 结果 artifact contract”，避免继续把整条认知链强行工程化成脆弱的 strict JSON + 伪工具目录组合。

**Tech Stack:** FastAPI, Python 3.11+, SQLite, builtin agents, MCP, skills, local git worktrees, unittest, Feishu webhook, JSON-first config (`platform.json`, `models.json`, `mcp.json`, `agents.json`).

**Reference Baseline:**
- `docs/plans/2026-03-24-private-server-self-host-rollout.md`
- `docs/architecture/agent-system-overview.md`
- `docs/architecture/agent-first-implementation-principles.md`
- `/Users/litiezhu/docs/ytsd/工作学习/AI学习/agent/Agent-to-Agent通信模式深度调研报告.md`

## Execution Result

> 更新时间：2026-03-25
> 执行结论：本轮计划已完成到“failure semantics 收紧 + runtime boundary 澄清 + fresh live 复验通过”的目标；Chunk 5 只完成 inventory / bugfix，不继续做高风险锁层删减。后续 parser-role / concurrency follow-up 也已完成，当前计划无剩余执行项。

- Chunk 1 完成：
  - 文档已明确 transport retry、critical-path failure、structured output failure、operator evidence 边界
- Chunk 2 完成：
  - `ralph execution` provider failure 后的 heuristic success fallback 已移除
- Chunk 3 完成：
  - execution / review parse failure 现已持久化 `failure_evidence`
  - control task 会写入 `execution_failure_evidence` / `review_failure_evidence`
- Chunk 4 完成到阶段性目标：
  - 已新增 `docs/architecture/live-chain-failure-semantics.md`
  - 已明确 `sleep_coding` / `code_review` 当前没有真实 tool-call loop，属于 structured / artifact boundary
  - 已明确 `app/runtime/structured_output.py` 当前是宽容边界解析器，不是主链强协议解析器
  - 已拆出 parser-role follow-up 计划：
    - `docs/plans/2026-03-25-structured-output-role-followup.md`
- Chunk 5 完成到 audit-only：
  - 已完成 SQLite / concurrency inventory
  - 未做大规模锁层删除
  - 仅修复一个真实并发真相 bug：
    - terminal delivery 现在会释放实际持有 execution lane 的 control task
    - 回归测试：`tests/test_automation.py::test_final_delivery_releases_lane_for_sleep_coding_control_task`
  - 已补 gateway / session / worker 行为 harness，且验证当前 `Gateway` session lock 仍承载同 session 并发幂等，不可直接删除
  - no-op lock 实验表明：
    - 移除 `Gateway` session lock 后，同 session 重复消息会生成两次并发执行，当前不能安全删掉这一层
  - 已拆出并发减法 follow-up 计划：
    - `docs/plans/2026-03-25-concurrency-reduction-followup.md`
- Chunk 6 完成：
  - `python -m unittest tests.test_sleep_coding tests.test_review tests.test_main_agent tests.test_automation tests.test_agent_runtime_policy -v`
    - PASS (`Ran 98 tests in 4.253s`)
  - `python scripts/run_test_suites.py quick`
    - PASS (`Ran 132 tests in 9.063s`)
  - `python scripts/run_test_suites.py regression`
    - PASS (`Ran 224 tests in 11.539s`)
  - `python scripts/run_test_suites.py manual`
    - PASS (`Ran 4 tests in 0.010s`)
  - `python scripts/run_test_suites.py live`
    - PASS (`Ran 4 tests in 84.283s`)
  - 最新 live 证据：
    - issue `#233`
    - sleep-coding control task `beb885c0-df10-4984-927f-fea4e899aa32`
    - sleep-coding task `3fabd549-0fc5-44ad-ae63-14af3904f5af`
    - review run `073256b1-d6c3-4d46-884d-5047cb1875ce`
    - PR `#234`
    - live 完成后 `execution_lane.active_task_id == None`

---

## Requirement Lock

本轮只处理下面这些纠偏目标，不引入新的产品能力：

1. 不为了让 live test 通过而增加 permissive fallback 或伪成功链路。
2. 执行、review、delivery 等关键主链节点失败时，优先暴露根因和原始证据。
3. 只保留必要的 transport retry；不要把 agent 认知失败静默改写成 heuristic success。
4. 重新审视 SQLite 并发控制、入口锁和 worker claim 的必要性，优先做减法。
5. 重新审视“禁用工具目录 + 强制结构化解析”的设计是否偏离 agent-first 原则，并按参考调研文档收敛交互边界。
6. 本轮先完成计划与文档细化，不默认承诺立即执行所有实现。

## Non-Negotiable Principles

- 不把 `ralph execution`、`code-review-agent` 的真实失败默认降级成“继续通过”。
- 不新增“失败后自动切到另一套成功路径”的隐式回滚。
- 传输级异常允许重试，但必须有明确次数、延迟和原始错误留存。
- agent 间边界优先表达为：
  - 状态事件
  - handoff contract
  - artifact contract
  - 明确 operator evidence
- 只有 runtime 真的支持 tool-call loop，prompt 里才允许把工具能力当作可执行能力暴露给模型。
- 若某个能力本质上仍依赖模型自由输出，就不要把它伪装成强保证 RPC 协议。

## File / Module Responsibility Map

### Runtime / Prompt Boundary

- Modify: `app/runtime/agent_runtime.py`
  - 明确工具能力暴露策略与 workflow 边界
- Modify: `app/runtime/structured_output.py`
  - 明确当前解析器角色是“边界解析器”还是“主链协议解析器”
- Modify if needed: `app/runtime/llm.py`
  - 保持 transport retry 的职责边界，不上浮成业务降级器

### Ralph Execution / Failure Semantics

- Modify: `app/agents/ralph/drafting.py`
- Modify: `app/agents/ralph/runtime_executor.py`
- Modify if needed: `app/agents/ralph/workflow.py`
- Modify if needed: `app/agents/ralph/progress.py`

### Review / Main-Agent Failure Semantics

- Modify if needed: `app/agents/main_agent/application.py`
- Modify if needed: `app/agents/code_review_agent/runtime_reviewer.py`
- Modify if needed: `app/control/automation.py`

### Concurrency / SQLite Truth

- Modify if needed: `app/control/gateway.py`
- Modify if needed: `app/control/session_registry.py`
- Modify if needed: `app/control/sleep_coding_worker.py`
- Modify if needed: `app/control/task_registry.py`
- Modify if needed: `app/infra/sqlite_utils.py`

### Docs / Truth Sync

- Modify: `README.md`
- Modify: `STATUS.md`
- Modify if needed: `docs/README.md`
- Modify if needed: `docs/architecture/agent-system-overview.md`
- Modify if needed: `docs/architecture/agent-first-implementation-principles.md`
- Add if needed: `docs/architecture/live-chain-failure-semantics.md`

### Tests

- Modify: `tests/test_sleep_coding.py`
- Modify: `tests/test_review.py`
- Modify: `tests/test_main_agent.py`
- Modify: `tests/test_agent_runtime_policy.py`
- Modify if needed: `tests/test_live_chain.py`
- Modify if needed: `tests/test_session_registry.py`
- Modify if needed: `tests/test_gateway.py`
- Modify if needed: `tests/test_sleep_coding_worker.py`

---

## Chunk 1: Freeze Failure-Semantics Contract In Docs

**Status:** Completed

### Objective

- 先把“允许什么 retry / 不允许什么 fallback / 失败时必须保留哪些证据”写成当前正式约束，避免后续实现又漂移。

### Success Criteria

- 文档明确区分：
  - transport retry
  - agent runtime failure
  - structured output failure
  - delivery failure
- 文档不再默认接受“为了跑通 live 而 permissive fallback”。

### Task 1.1: Write explicit failure-semantics rules

**Files:**
- Modify: `docs/architecture/agent-system-overview.md`
- Modify: `docs/architecture/agent-first-implementation-principles.md`
- Modify: `STATUS.md`

- [x] Step 1: 在 `agent-system-overview` 中补“关键主链步骤失败必须显式失败，不默认降级”的正式规则。
- [x] Step 2: 在 `agent-first-implementation-principles` 中补“transport retry allowed, heuristic success fallback forbidden in critical path”的实现原则。
- [x] Step 3: 在 `STATUS.md` 把下一步收敛为“修正失败语义与并发边界”，不要继续写成“live 已通过即可结束”。
- [x] Step 4: Run:
  - `rg -n "retry|fallback|显式失败|needs_attention|structured output|transport" docs/architecture STATUS.md`
- [x] Step 5: 确认文档表述与用户要求一致：目标是修根因，不是保测试通过。

---

## Chunk 2: Remove Invalid Critical-Path Fallbacks

**Status:** Completed

### Objective

- 回退上一轮不符合原则的关键路径降级，恢复“重试后失败就是失败”。

### Success Criteria

- `ralph execution` 不再在 provider 失败时默认生成 heuristic execution draft。
- `main-agent` / `review` 是否允许 fallback 有清晰边界并被文档化。
- 失败会留下足够证据供 operator 判断下一步，而不是静默进入成功状态。

### Task 2.1: Lock failing tests for forbidden execution fallback

**Files:**
- Modify: `tests/test_sleep_coding.py`
- Modify if needed: `tests/test_live_chain.py`

- [x] Step 1: 写 failing test，要求 `ralph execution` 在 recoverable transport failure 重试耗尽后进入显式失败，而不是转成 `in_review`。
- [x] Step 2: 若已有测试把 execution provider failure 视为可接受 fallback success，先改成新的失败语义。
- [x] Step 3: Run:
  - `python -m unittest tests.test_sleep_coding -v`
- [x] Step 4: 确认当前失败点来自 execution fallback 逻辑，而不是测试夹具。

### Task 2.2: Remove execution heuristic-success fallback

**Files:**
- Modify: `app/agents/ralph/drafting.py`
- Modify if needed: `app/agents/ralph/runtime_executor.py`
- Modify if needed: `app/agents/ralph/workflow.py`
- Test: `tests/test_sleep_coding.py`

- [x] Step 1: 去掉 `build_execution_draft()` 在 provider failure 下直接切 heuristic success 的逻辑。
- [x] Step 2: 保留 transport retry，但 retry 耗尽后返回显式失败。
- [x] Step 3: 确保失败时把原始异常和阶段名写进 task/control-task evidence。
- [x] Step 4: Re-run:
  - `python -m unittest tests.test_sleep_coding -v`

### Task 2.3: Audit intake/review fallback boundaries

**Files:**
- Modify if needed: `app/agents/main_agent/application.py`
- Modify if needed: `app/agents/code_review_agent/runtime_reviewer.py`
- Modify if needed: `tests/test_main_agent.py`
- Modify if needed: `tests/test_review.py`

- [x] Step 1: 审计 `main-agent intake` 的 heuristic issue fallback 是否仍符合“入口容错而非伪成功交付”边界。
- [x] Step 2: 审计 `code-review-agent` 是否存在“失败默认为 non-blocking”或等价行为。
- [x] Step 3: 如有越界 fallback，先写 failing test，再收回到显式失败。
- [x] Step 4: Run:
  - `python -m unittest tests.test_main_agent tests.test_review -v`

---

## Chunk 3: Add Real Failure Evidence Before Any Further Recovery Logic

**Status:** Completed

### Objective

- 失败后先拿到足够证据，再谈人工重试、恢复或回滚。

### Success Criteria

- 执行、review、structured output 失败时，operator 能直接看到：
  - 原始异常
  - 原始模型输出或其安全截断
  - 当前阶段
  - 已发生的副作用
  - 推荐下一动作

### Task 3.1: Persist raw failure evidence for execution/review parse failures

**Files:**
- Modify: `app/agents/ralph/runtime_executor.py`
- Modify if needed: `app/agents/code_review_agent/runtime_reviewer.py`
- Modify if needed: `app/agents/ralph/progress.py`
- Modify if needed: `app/control/task_registry.py`
- Test: `tests/test_sleep_coding.py`
- Test: `tests/test_review.py`

- [x] Step 1: 写 failing test，要求 structured output parse failure 会把原始输出片段持久化到 task/control-task evidence。
- [x] Step 2: 执行路径至少记录：
  - `step_name`
  - `provider`
  - `model`
  - `raw_output_excerpt`
  - `parse_error`
- [x] Step 3: review 路径做同样处理，避免只留下一句 “invalid structured output”。
- [x] Step 4: Re-run:
  - `python -m unittest tests.test_sleep_coding tests.test_review -v`

### Task 3.2: Define retry-before-recovery operator contract

**Files:**
- Modify if needed: `app/control/automation.py`
- Modify if needed: `app/models/schemas.py`
- Modify if needed: `docs/architecture/live-chain-failure-semantics.md`
- Test: `tests/test_automation.py`

- [x] Step 1: 写 failing test，要求系统在 retry 耗尽后进入显式失败/needs_attention，并附 recovery evidence，而不是自动切另一条成功路径。
- [x] Step 2: 若需要增加显式 schema 字段，优先加最小结构字段，不继续堆自由 dict。
- [x] Step 3: Re-run:
  - `python -m unittest tests.test_automation -v`

---

## Chunk 4: Rework Tool Exposure And Structured Interaction Boundary

**Status:** Completed (Closed Via Follow-up)

### Objective

- 不再长期依赖“禁用工具目录”这种战术修补；要么暴露真实可执行能力，要么收缩成无工具的 artifact/消息边界。

### Success Criteria

- 对每个 workflow，能明确回答：
  - 模型是否真的可以发起工具调用
  - runtime 是否真的执行这些工具调用
  - 结果是返回文本、artifact，还是结构化对象
- `structured_output.py` 不再被当成“通用 agent 间协议层”滥用。

### Task 4.1: Document actual runtime capability matrix

**Files:**
- Add or modify: `docs/architecture/live-chain-failure-semantics.md`
- Modify if needed: `docs/architecture/agent-system-overview.md`
- Modify if needed: `README.md`

- [x] Step 1: 写清楚 `main-agent`、`ralph plan`、`ralph execution`、`code-review-agent` 当前分别是：
  - tool-capable
  - no tool-call loop
  - artifact-only
  - structured-output boundary
- [x] Step 2: 直接引用 A2A 调研结论：优秀项目多是“子 agent 独立执行，主 agent 收最终结果/事件”，不是强行把所有交互都做成 strict schema RPC。
- [x] Step 3: Run:
  - `rg -n "tool-call|artifact|A2A|structured output|runtime capability" docs/architecture README.md`

### Task 4.2: Choose one of two explicit runtime directions

**Files:**
- Modify: `app/runtime/agent_runtime.py`
- Modify if needed: `tests/test_agent_runtime_policy.py`

- [x] Step 1: 先选定并文档化方向，不直接混用：
  - 方向 A：实现真实 tool-call loop
  - 方向 B：关键 workflow 明确为“无工具 artifact 生成”，不暴露伪工具目录
- [x] Step 2: 若短期保持方向 B，文档和代码都必须写清楚这是“runtime capability boundary”，不是“模型不允许自主判断”。
- [x] Step 3: 若准备走方向 A，补一份独立子计划，不在本轮混做。
- [x] Step 4: Re-run:
  - `python -m unittest tests.test_agent_runtime_policy -v`

### Task 4.3: Shrink structured-output role to stable boundaries only

**Files:**
- Modify if needed: `app/runtime/structured_output.py`
- Modify if needed: `app/agents/ralph/runtime_executor.py`
- Modify if needed: `app/agents/code_review_agent/runtime_reviewer.py`
- Test: `tests/test_sleep_coding.py`
- Test: `tests/test_review.py`

- [x] Step 1: 审计哪些地方真的需要 schema object，哪些地方其实应该传 artifact markdown 或 human-readable summary。
- [x] Step 2: 不再扩大“从自由文本里硬抠 JSON 对象”的适用范围。
- [x] Step 3: 结论：当前 execution draft 仍需要承载 `artifact_markdown`、`commit_message`、`file_changes` 三元 contract，因此暂不移除 JSON envelope，但已明确 parser 只是边界提取器，不是协议保证层。
- [x] Step 4: Re-run:
  - `python -m unittest tests.test_sleep_coding tests.test_review -v`

### Task 4.4: Split parser-role follow-up from runtime-boundary work

**Files:**
- Modify if needed: `app/runtime/structured_output.py`
- Add if needed: `docs/plans/<new-parser-followup-plan>.md`

- [x] Step 1: 明确 `structured_output.py` 未来到底承担：
  - 边界宽容解析器
  - 还是严格主链协议解析器
- [x] Step 2: 若要继续收紧解析职责，单独拆成后续子计划，不与 live-chain 纠偏混做。
- [x] Step 3: 为后续子计划补充最小测试矩阵：
  - 哪些 workflow 允许宽容解析
  - 哪些 workflow 必须 strict fail-closed

---

## Chunk 5: Reduce SQLite / Concurrency Complexity To One Necessary Truth

**Status:** Completed (Closed Via Follow-up)

### Objective

- 评估并收敛当前单机并发控制，避免入口锁、lane 状态和 claim 机制重复表达同一规则。

### Success Criteria

- 可以明确解释每一类锁/门禁的必要性。
- 删除或收敛重复层，不影响“单活执行槽 + operator 可诊断”目标。

### Task 5.1: Inventory current concurrency controls

**Files:**
- Modify or add: `docs/architecture/live-chain-failure-semantics.md`
- Inspect: `app/control/gateway.py`
- Inspect: `app/control/session_registry.py`
- Inspect: `app/control/sleep_coding_worker.py`
- Inspect: `app/infra/sqlite_utils.py`

- [x] Step 1: 列出当前三层并发控制：
  - 进程内 `threading.Lock`
  - SQLite `execution_lane`
  - worker claim lease
- [x] Step 2: 对每一层写“存在理由 / 与其他层的重叠 / 可删除风险”。
- [x] Step 3: 明确第一阶段单机自用场景下的最小必要集合。

### Task 5.1b: Fix proven execution-lane truth bug before any reduction

**Files:**
- Modify: `app/control/automation.py`
- Modify: `tests/test_automation.py`

- [x] Step 1: 复现 terminal delivery 结束后仍残留 `execution_lane.active_task_id` 的真实 bug。
- [x] Step 2: 修复 lane release，使其释放实际持有 lane 的 control task，而不是只按父任务释放。
- [x] Step 3: Run:
  - `python -m unittest tests.test_automation.AutomationServiceTests.test_final_delivery_releases_lane_for_sleep_coding_control_task -v`

### Task 5.2: Write failing tests for redundant-lock removal target

**Files:**
- Modify: `tests/test_gateway.py`
- Modify: `tests/test_session_registry.py`
- Modify if needed: `tests/test_sleep_coding_worker.py`

- [x] Step 1: 写 tests，锁定真正要保住的行为：
  - 单活
  - 不丢任务
  - 可诊断 queued/busy
- [x] Step 2: 不为现有锁实现写“实现耦合型”测试。
- [x] Step 3: Run:
  - `python -m unittest tests.test_gateway tests.test_session_registry tests.test_sleep_coding_worker -v`

### Task 5.3: Remove one redundant concurrency layer at a time

**Files:**
- Modify if needed: `app/control/gateway.py`
- Modify if needed: `app/control/session_registry.py`
- Modify if needed: `app/control/sleep_coding_worker.py`
- Test: `tests/test_gateway.py`
- Test: `tests/test_session_registry.py`
- Test: `tests/test_sleep_coding_worker.py`

- [x] Step 1: 先决定删哪一层冗余最小，默认优先评估入口层 per-session `threading.Lock`；经并发幂等实验验证，当前无安全删除候选。
- [x] Step 2: 每次只删除或收敛一层，不同时改 lane 与 claim；本轮不进入删除阶段。
- [x] Step 3: 每改一层就回跑单活/worker 相关测试；本轮通过 harness 和 no-op lock 证伪实验确认不得强删。
- [x] Step 4: Re-run:
  - `python -m unittest tests.test_gateway tests.test_session_registry tests.test_sleep_coding_worker -v`

### Task 5.4: Re-scope concurrency reduction into a dedicated follow-up chunk

**Files:**
- Modify: `docs/plans/2026-03-25-live-chain-root-cause-correction-plan.md`
- Add if needed: `docs/plans/<new-concurrency-reduction-plan>.md`

- [x] Step 1: 先把 Chunk 5 剩余工作改成“并发减法 follow-up”，不要继续写成已完成。
- [x] Step 2: 只有在补齐 `tests.test_gateway` / `tests.test_session_registry` / `tests.test_sleep_coding_worker` 的行为测试后，才进入锁层删减。
- [x] Step 3: 若后续要删层，单独拆计划并限定一次只收敛一层。

---

## Chunk 6: Real-Chain Verification Under Corrected Principles

**Status:** Completed

### Objective

- 在去掉错误降级后，再次用真实链路确认问题是否还存在，以及新的根因是否已暴露清楚。

### Success Criteria

- live 通过时，说明不是靠 permissive fallback 通过。
- live 失败时，能直接给出根因证据和下一修复点。

### Task 6.1: Re-run layered verification before live

**Files:**
- No code changes required

- [x] Step 1: Run:
  - `python -m unittest tests.test_sleep_coding tests.test_review tests.test_main_agent tests.test_automation tests.test_agent_runtime_policy -v`
- [x] Step 2: Run:
  - `python scripts/run_test_suites.py quick`
- [x] Step 3: Run:
  - `python scripts/run_test_suites.py regression`
- [x] Step 4: 确认没有新的 permissive fallback 回归进主链。

### Task 6.2: Re-run live with evidence capture

**Files:**
- Modify if needed: `tests/test_live_chain.py`
- Modify if needed: `STATUS.md`

- [x] Step 1: Run:
  - `python scripts/run_test_suites.py live`
- [x] Step 2: 如果 PASS，记录：
  - 最新 issue / task / review / PR 证据
  - 证明不是 heuristic success path
- [x] Step 3: 本轮 fresh live 未触发 FAIL 分支；失败时仍按下面证据要求记录：
  - 失败阶段
  - 原始 provider / parse / side-effect 证据
  - 下一步唯一 blocker
- [x] Step 4: 将真实结论同步回 `STATUS.md`，不要写成乐观口径。

---

## Execution Notes

- 本计划优先级不是“先把 live 再跑绿”，而是“先把失败语义、交互边界、并发真相修正到合理状态，再看 live 结果”。
- 如果执行中发现 `tool-call loop` 需要单独建设，不要在本计划里顺手扩展成大改；应该拆成独立后续计划。
- 如果执行中发现某个 fallback 其实属于 operator 显式恢复动作，应把它移到 control-plane/operator action，而不是保留在默认主链里。
