# Agent-Native Runtime Follow-Up Hardening Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

> Execution status: completed on 2026-03-23. `STATUS.md` and the latest local handoff contain the final verification evidence and re-entry guidance.

**Goal:** 把当前“主路径已纠偏，但旧配置/旧兼容壳仍在、worktree-native runtime 仍未落地”的状态，继续推进到你要求的最终形态：无 command/fallback 标准路径、builtin agent 原生 worktree 执行与 review、diagnostics/live-chain 与真实能力面对齐。

**Architecture:** 保持唯一主链 `gateway -> main-agent -> ralph -> code-review-agent -> delivery`。这轮不再讨论方向，而是收口执行面：删除 command-native 配置与实现壳，改造 Ralph/Review 为真实本地 worktree owner，统一 operator diagnostics 与 live-chain 前置条件，使系统行为、文档和运行时 truth 完全一致。

**Tech Stack:** FastAPI, Python 3.11+, SQLite, unittest, builtin agents, MCP, local git worktrees, existing task/session stores, Feishu webhook, runtime context policy.

---

## User Requirement Lock

本计划必须严格服务于以下用户诉求，不允许在执行中被“兼容性”“平滑迁移”“保留旧路径”重新稀释：

1. `ralph` 是标准编码 agent，`code-review-agent` 是标准 review agent。
2. 不接受 `sleep_coding.execution.command` 和 `review.skill_command` 作为标准路径、降级路径或“先留着以后再说”的兼容壳。
3. 不接受 `sleep_coding.execution.allow_llm_fallback` 之类的 permissive 配置继续掩盖主链失败。
4. 失败必须 fail-closed，不接受“链路先走完、结果看起来像成功”。
5. 目标形态不是“LLM 输出结构化 JSON，然后系统投影一下”，而是 builtin agent 对本地 worktree 真正负责。
6. live-chain 必须被真实执行和验证，而不是只靠 readiness 逻辑推断“应该可以跑”。

## Forbidden Shortcuts

执行过程中，明确禁止以下偏移：

- 禁止把旧 command path 改名后继续保留
- 禁止把 command path 迁到 diagnostics / helper / test fixture 中伪装成“非主路径”
- 禁止用更多 heuristics、字符串协议、事件拼装逻辑去代替 agent runtime 能力
- 禁止把 `file_changes` / `review_markdown` 继续当作真实 worktree 操作的替身
- 禁止为了让测试继续通过而只修改 fake fixtures、却不修主实现
- 禁止把“live-chain readiness 为 ready”当作 live-chain 已验证

## Scope And Non-Negotiables

- 标准主链不得再依赖 `sleep_coding.execution.command`
- 标准主链不得再依赖 `review.skill_command`
- `sleep_coding.execution.allow_llm_fallback` 及同类“继续跑完”的 permissive 开关不再作为主链配置面
- 缺少 builtin coding/review capability 时必须显式失败
- `ralph` 必须对本地 worktree 负责：读代码、改代码、执行验证、收集 diff/evidence
- `code-review-agent` 必须基于本地 worktree/diff/validation evidence 做 review，而不是只消费抽象摘要
- diagnostics / live-chain readiness 只能基于 builtin runtime truth，而不能继续认可 command/fallback 能力面

## Exact End-State Definition

本计划验收时，以下判断必须同时成立：

### A. Command/Fallback Surface Removed

- `app/core/config.py` 中不再存在：
  - `sleep_coding_execution_command`
  - `sleep_coding_execution_allow_llm_fallback`
  - `review_skill_command`
- `app/infra/diagnostics.py` 不再识别 command mode
- `app/agents/ralph/drafting.py` 不再存在本地 command 执行 helper
- `app/agents/code_review_agent/skill.py` 不再存在 command-compatible 主链 helper

### B. Ralph Is Truly Worktree-Native

- execution 输入必须显式包含 worktree 路径和任务上下文
- execution 结果必须显式包含真实 changed files / diff / validation evidence
- artifact / commit summary 必须来自真实工作树结果投影
- 若没有 worktree evidence，任务不得进入“coding completed / in_review”

### C. Review Agent Is Truly Worktree/Diff-Native

- review 输入必须优先包含 changed files / diff / validation evidence / task goal
- review 输出必须是 strict structured output
- 若 evidence 缺失或 structured output 非法，review 必须失败
- 若 review truth 不完整，delivery 不得发生

### D. Live Chain Is Real

- `tests.test_live_chain` 必须实际执行
- live-chain 失败时要拿到第一真实故障点
- diagnostics readiness 必须与 live-chain 结果一致

## Relationship To Existing Plan

- 本计划是对以下计划的 follow-up hardening，不替代其历史记录：
  - `docs/plans/2026-03-23-agent-native-runtime-course-correction.md`
- 现状判断和偏移结论来自：
  - `docs/architecture/agent-runtime-contracts.md`
  - `docs/architecture/agent-system-overview.md`
  - `docs/architecture/agent-first-implementation-principles.md`
  - `STATUS.md`

## Execution Outcome

- Completed: Chunk 1 through Chunk 6
- Result:
  - command / fallback config surface removed from the standard chain
  - legacy command-compatible shells removed from Ralph and review execution paths
  - Ralph now projects real worktree evidence into task truth
  - code-review-agent now consumes task evidence plus workspace snapshot evidence
  - delivery and recovery paths now require truthful execution / review evidence
  - live-chain was executed for real and passed in the local configured environment
- Final verification:
  - `python -m unittest tests.test_agent_runtime_policy tests.test_rag_capability tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_sleep_coding_worker tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e tests.test_framework_public_surface -v`
  - `python -m unittest tests.test_live_chain -v`
  - `rg -n "execution_command|allow_llm_fallback|review_skill_command|mode.: .command" app tests docs -g '*.py' -g '*.md'`

## Current Drift To Fix

1. 配置层仍保留 `sleep_coding.execution.command`、`sleep_coding.execution.allow_llm_fallback`、`review.skill_command`
2. 兼容实现函数仍保留在代码中，容易把主链重新拉回 command-native 路径
3. `IntegrationDiagnosticsService` 仍把 command/fallback 视为合法能力面，和当前架构文档不一致
4. `RalphRuntimeExecutor` / `RuntimeReviewer` 目前更像“严格 structured-output 网关”，还不是 worktree-native runtime
5. live-chain readiness 已满足，但还没有把 live-chain 测试纳入本轮纠偏验收

## File / Module Responsibility Map

### Config / Diagnostics Cleanup

- Modify: `app/core/config.py`
  - 删除 command-native / permissive fallback 配置面，收口成 builtin runtime capability truth
- Modify: `app/infra/diagnostics.py`
  - 按 builtin runtime truth 输出 readiness，不再识别 command mode
- Modify: `tests/test_runtime_components.py`
  - 更新配置和 diagnostics 断言

### Ralph Worktree-Native Execution

- Modify: `app/agents/ralph/runtime_executor.py`
  - 从“structured draft parser”升级为真实 worktree-native execution coordinator
- Modify: `app/agents/ralph/drafting.py`
  - 删除 command/native 双轨残留
- Modify: `app/agents/ralph/workflow.py`
  - 让 artifact / commit summary 成为真实 worktree 结果的投影
- Modify: `app/infra/git_workspace.py`
  - 明确 changed files / diff evidence / commit evidence contract
- Modify if needed: `app/models/schemas.py`
  - 补 execution evidence schema
- Test: `tests/test_sleep_coding.py`

### Review Worktree-Native Runtime

- Modify: `app/agents/code_review_agent/runtime_reviewer.py`
  - 基于真实 workspace diff / changed files / validation evidence 组织 review 输入
- Modify: `app/agents/code_review_agent/context.py`
  - 提升 review context builder，优先真实工作树证据
- Modify: `app/agents/code_review_agent/skill.py`
  - 删除 command 兼容残留，保留 builtin runtime only
- Modify: `app/agents/code_review_agent/application.py`
  - 把 review evidence 明确投影到 control task truth
- Modify if needed: `app/models/schemas.py`
  - 补 review evidence schema
- Test: `tests/test_review.py`

### Control Plane / Delivery / Live Chain

- Modify: `app/control/automation.py`
  - 保证 delivery 只消费真实 coding/review truth
- Modify: `tests/test_automation.py`
  - 覆盖 runtime capability 缺失与 invalid evidence 的 fail-closed
- Modify: `tests/test_mvp_e2e.py`
  - 覆盖新能力面下的端到端行为
- Modify: `tests/test_live_chain.py`
  - 把 live-chain 纳入验收

### Docs / Continuity

- Modify: `docs/architecture/agent-runtime-contracts.md`
- Modify: `docs/architecture/agent-system-overview.md`
- Modify: `docs/architecture/agent-first-implementation-principles.md`
- Modify: `docs/architecture/main-chain-operator-runbook.md`
- Modify: `STATUS.md`
- Modify: latest relevant local handoff under `docs/internal/handoffs/`

## Chunk 1: Remove Command/Fallback Config Surface

### Objective

- 彻底删除 command-native 与 permissive fallback 配置面，避免标准主链回退。

### Success Criteria

- `Settings` 不再提供以下主链配置：
  - `sleep_coding_execution_command`
  - `sleep_coding_execution_allow_llm_fallback`
  - `review_skill_command`
- diagnostics 不再输出 `mode=command`
- 测试不再把 command/fallback 视为正式能力面

### Task 1.1: Add failing config/diagnostics tests

**Files:**
- Modify: `tests/test_runtime_components.py`

- [ ] Step 1: 写 failing test，断言 `Settings` 不再暴露 command/fallback 标准配置面
- [ ] Step 2: 写 failing test，断言 diagnostics 只接受 builtin runtime truth，不再返回 `mode=command`
- [ ] Step 3: Run:
  - `python -m unittest tests.test_runtime_components.RuntimeComponentTests -v`

### Task 1.2: Remove config surface and diagnostics compatibility

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/infra/diagnostics.py`

- [ ] Step 1: 删除 `resolved_sleep_coding_execution_command`
- [ ] Step 2: 删除 `resolved_sleep_coding_execution_allow_llm_fallback`
- [ ] Step 3: 删除 `resolved_review_skill_command`
- [ ] Step 4: 删除对应 dataclass/base settings 字段，不只删 `resolved_*` 属性
- [ ] Step 5: 重写 diagnostics 中 `ralph_execution` / `review_skill` 的能力判定，只认 builtin runtime prerequisites
- [ ] Step 6: 确认 `platform.json` 中即便仍存在这些旧字段，也不会再被主链消费
- [ ] Step 5: Re-run:
  - `python -m unittest tests.test_runtime_components.RuntimeComponentTests -v`

### Chunk 1 Regression

- [ ] Run:
  - `rg -n "execution_command|allow_llm_fallback|review_skill_command|mode.: .command" app tests`
- [ ] Check drift:
  - 配置面已经不再暗示 command-native 主路径
  - 没有“仅在 diagnostics/test 中残留”的伪删除

## Chunk 2: Delete Legacy Command-Compatible Implementation Shell

### Objective

- 删除当前仍然滞留在代码中的旧 command/native 双轨实现壳。

### Success Criteria

- Ralph 不再保留 `_run_local_execution_command()` / `_resolve_execution_command()`
- Review 不再保留 command output parser 作为主链兼容路径
- 测试不再覆盖旧 command 主路径

### Task 2.1: Add failing cleanup tests

**Files:**
- Modify: `tests/test_sleep_coding.py`
- Modify: `tests/test_review.py`

- [ ] Step 1: 写 failing test，要求 Ralph 仅能通过 builtin runtime 进入 execution path
- [ ] Step 2: 写 failing test，要求 Review 仅能通过 builtin runtime 进入 review path
- [ ] Step 3: Run:
  - `python -m unittest tests.test_sleep_coding tests.test_review -v`

### Task 2.2: Remove dead compatibility code

**Files:**
- Modify: `app/agents/ralph/drafting.py`
- Modify: `app/agents/code_review_agent/skill.py`

- [ ] Step 1: 删除 `_run_local_execution_command()`
- [ ] Step 2: 删除 `_resolve_execution_command()`
- [ ] Step 3: 删除 review command 兼容解析和残留字段
- [ ] Step 4: 清理不再使用的 import / helper / tests
- [ ] Step 5: 确认 tests 中不再要求旧 command path 继续可调用
- [ ] Step 6: Re-run:
  - `python -m unittest tests.test_sleep_coding tests.test_review -v`

### Chunk 2 Regression

- [ ] Run:
  - `rg -n "_run_local_execution_command|_resolve_execution_command|review skill command|strict JSON output" app tests`
- [ ] Check drift:
  - 代码库已没有 command-native 主链残留壳
  - 没有“换个函数名保留同逻辑”的隐藏兼容层

## Chunk 3: Make Ralph Truly Worktree-Native

### Objective

- 让 `ralph` 不只是产出结构化草案，而是真正拥有本地 worktree 执行闭环。

### Success Criteria

- Ralph 在 worktree 内拥有至少以下真实能力：
  - 读取目标仓库文件
  - 修改目标仓库文件
  - 收集 changed files / diff evidence
  - 执行 validation command
  - 生成 artifact / commit summary 作为投影
- `file_changes` 不再是主执行面，而只是结果投影
- 若只是让 LLM 返回 `file_changes` 而没有真实 worktree evidence，本 chunk 视为未完成

### Task 3.1: Add failing worktree-native execution tests

**Files:**
- Modify: `tests/test_sleep_coding.py`

- [ ] Step 1: 写 failing test，要求 execution evidence 来源于真实 worktree changed files，而不是纯 LLM `file_changes`
- [ ] Step 2: 写 failing test，要求 validation 在 worktree 路径执行并把证据写回 task payload
- [ ] Step 3: 写 failing test，要求 artifact/summary 从真实 changed files 投影
- [ ] Step 4: 写 failing test，要求没有 changed files / diff evidence 时不得进入 review
- [ ] Step 5: Run:
  - `python -m unittest tests.test_sleep_coding.SleepCodingServiceTests -v`

### Task 3.2: Implement worktree-native execution contract

**Files:**
- Modify: `app/agents/ralph/runtime_executor.py`
- Modify: `app/infra/git_workspace.py`
- Modify: `app/agents/ralph/workflow.py`
- Modify if needed: `app/models/schemas.py`

- [ ] Step 1: 定义 Ralph worktree execution evidence schema
- [ ] Step 2: 在 `runtime_executor.py` 中增加真实 worktree inspection / evidence collection 流程
- [ ] Step 3: 明确“agent 做了什么”和“runtime 收集到了什么证据”是两回事，证据必须由运行时从 worktree 侧采样
- [ ] Step 4: 让 `workflow.py` 持久化 changed files / diff / validation evidence
- [ ] Step 5: 让 artifact 和 commit summary 从真实结果投影，而不是只信 LLM 输出
- [ ] Step 6: 明确 review handoff 只引用真实 execution evidence
- [ ] Step 7: Re-run:
  - `python -m unittest tests.test_sleep_coding.SleepCodingServiceTests -v`

### Chunk 3 Regression

- [ ] Run:
  - `python -m unittest tests.test_sleep_coding tests.test_sleep_coding_worker -v`
- [ ] Check drift:
  - Ralph 已是 worktree execution owner，而不是 structured-draft broker
  - 没有把“真实 worktree 执行”偷换成“更复杂的 JSON contract”

## Chunk 4: Make Code Review Agent Truly Worktree/Diff-Native

### Objective

- 让 `code-review-agent` 直接基于工作树证据做 review，而不是主要依赖抽象 context 摘要。

### Success Criteria

- review 输入优先包含：
  - changed files
  - diff evidence
  - validation evidence
  - task goal / acceptance
- review 输出仍然是 strict structured output
- review runtime failure 继续 fail-closed
- 若 review 主要还是消费摘要字符串，而不是 worktree/diff evidence，本 chunk 视为未完成

### Task 4.1: Add failing review-evidence tests

**Files:**
- Modify: `tests/test_review.py`

- [ ] Step 1: 写 failing test，要求 review context 优先使用真实 changed files / validation evidence
- [ ] Step 2: 写 failing test，要求缺失 review evidence 时显式失败
- [ ] Step 3: 写 failing test，要求 malformed structured review output 仍然 hard-fail
- [ ] Step 4: 写 failing test，要求 review 结果写回 control task 时携带 evidence 摘要/引用
- [ ] Step 5: Run:
  - `python -m unittest tests.test_review.ReviewServiceTests -v`

### Task 4.2: Implement worktree-native review context and evidence

**Files:**
- Modify: `app/agents/code_review_agent/runtime_reviewer.py`
- Modify: `app/agents/code_review_agent/context.py`
- Modify: `app/agents/code_review_agent/application.py`
- Modify if needed: `app/models/schemas.py`

- [ ] Step 1: 定义 review evidence schema
- [ ] Step 2: 在 `context.py` 中优先拼装 changed files / diff / validation evidence
- [ ] Step 3: 在 `runtime_reviewer.py` 中把 evidence 作为 review runtime 的硬输入
- [ ] Step 4: 在 `application.py` 中把 evidence 和 review truth 对齐写回 control task
- [ ] Step 5: 明确 review markdown 只是 human projection，不得替代 machine truth / evidence truth
- [ ] Step 6: Re-run:
  - `python -m unittest tests.test_review.ReviewServiceTests -v`

### Chunk 4 Regression

- [ ] Run:
  - `python -m unittest tests.test_review tests.test_automation -v`
- [ ] Check drift:
  - review reasoning 仍归 `code-review-agent`
  - review evidence 已基于 worktree truth
  - 没有退回“摘要驱动 review”

## Chunk 5: Align Control Plane And Diagnostics To Builtin Runtime Truth

### Objective

- 让 automation / diagnostics / delivery 都只消费 builtin runtime truth。

### Success Criteria

- delivery 不接受缺失或伪造的 coding/review truth
- diagnostics 能明确暴露：
  - missing builtin coding capability
  - missing builtin review capability
  - invalid execution evidence
  - invalid review evidence
- 不再允许“看起来完成”但 truth 不完整
- 若 control plane 通过增加更多中间状态来掩盖 evidence 缺口，本 chunk 视为失败

### Task 5.1: Add failing control-plane tests

**Files:**
- Modify: `tests/test_automation.py`
- Modify: `tests/test_runtime_components.py`
- Modify: `tests/test_mvp_e2e.py`

- [ ] Step 1: 写 failing test，要求 invalid execution/review evidence 阻止 final delivery
- [ ] Step 2: 写 failing test，要求 diagnostics 只暴露 builtin runtime truth
- [ ] Step 3: 写 failing test，要求 E2E 链路中的 review/coding truth 缺失时直接失败
- [ ] Step 4: 写 failing test，要求 operator next_action 指向真实缺口，而不是泛化错误
- [ ] Step 5: Run:
  - `python -m unittest tests.test_automation tests.test_runtime_components tests.test_mvp_e2e -v`

### Task 5.2: Tighten automation and operator truth

**Files:**
- Modify: `app/control/automation.py`
- Modify: `app/infra/diagnostics.py`
- Modify if needed: `app/models/schemas.py`

- [ ] Step 1: 把 final delivery gate 建立在 execution/review evidence 完整性上
- [ ] Step 2: 让 diagnostics 输出 builtin runtime truth-only readiness
- [ ] Step 3: 对 invalid evidence 给出 operator-visible next_action
- [ ] Step 4: 确认 automation 没有把缺失 truth 自动投影成 dry-run success
- [ ] Step 5: Re-run:
  - `python -m unittest tests.test_automation tests.test_runtime_components tests.test_mvp_e2e -v`

### Chunk 5 Regression

- [ ] Run:
  - `python -m unittest tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_sleep_coding_worker tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e -v`
- [ ] Check drift:
  - control plane 只做 gate/projection，不偷回认知执行面

## Chunk 6: Run And Fix Live Chain

### Objective

- 把 live-chain 真正纳入本轮 hardening 验收。

### Success Criteria

- `tests.test_live_chain` 可以在当前本地配置下运行
- 如失败，能明确暴露是 MCP、Feishu、LLM、review truth、delivery truth 还是 worker loop 问题
- 修复后的 readiness / live-chain 结果与 diagnostics 一致

### Task 6.1: Execute live-chain and capture first real failure

**Files:**
- Modify if needed: `tests/test_live_chain.py`
- Modify if needed: `app/infra/diagnostics.py`
- Modify if needed: `app/control/automation.py`

- [ ] Step 1: Run:
  - `python -m unittest tests.test_live_chain -v`
- [ ] Step 2: 记录第一个真实失败点，不允许先猜测
- [ ] Step 3: 如果第一次直接通过，仍要把结果写入 `STATUS.md` / local handoff，不能只口头说明
- [ ] Step 4: 为失败点增加最小回归测试或断言

### Task 6.2: Repair live-chain mismatch

**Files:**
- Modify only the minimal failing surface from step 6.1

- [ ] Step 1: 修复导致 live-chain 失败的真实缺口
- [ ] Step 2: Re-run:
  - `python -m unittest tests.test_live_chain -v`
- [ ] Step 3: 确认 `IntegrationDiagnosticsService.get_live_readiness()` 与 live-chain 结果一致
- [ ] Step 4: 如果 live-chain 失败但 readiness 仍为 ready，必须先修 diagnostics truth 再收尾

### Chunk 6 Regression

- [ ] Run:
  - `python -m unittest tests.test_runtime_components tests.test_live_chain -v`
- [ ] Check drift:
  - diagnostics 不是乐观猜测，而是 live-chain truth 的前置投影

## Final Regression Pack

- [ ] Run:
  - `python -m unittest tests.test_agent_runtime_policy tests.test_rag_capability tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_sleep_coding_worker tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e tests.test_framework_public_surface -v`
- [ ] Run:
  - `python -m unittest tests.test_live_chain -v`
- [ ] Run:
  - `rg -n "execution_command|allow_llm_fallback|review_skill_command|mode.: .command" app tests docs -g '*.py' -g '*.md'`
- [ ] Update:
  - `STATUS.md`
  - latest relevant local handoff under `docs/internal/handoffs/`

## Final Done Criteria

- 代码库中已没有 command-native 主链配置面
- 代码库中已没有 command-compatible 主链实现壳
- `ralph` 真正拥有本地 worktree 编码与验证闭环
- `code-review-agent` 真正拥有基于 worktree/diff/evidence 的 review 闭环
- diagnostics / automation / delivery 只认 builtin runtime truth
- live-chain 在当前本地配置下可执行，且结果与 diagnostics 一致
- 文档、计划、状态文件和本地 handoff 对上述事实没有自相矛盾之处
