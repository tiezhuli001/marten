# Agent-Native Runtime Course Correction Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `Marten` 主链从“control plane + 可插拔外部 execution/review command”纠偏为“内置 agent 原生完成本地编码与 review”的单主链实现，并把失败语义改成显式失败而不是静默降级。

**Architecture:** 保持单主链 `gateway -> main-agent -> ralph -> code-review-agent -> delivery`，继续坚持 `LLM + MCP + skill first`，但把本地编码与 review 的执行 ownership 收回到内置 agent runtime，而不是外包给 `sleep_coding.execution.command` / `review.skill_command`。RAG 保留为 runtime 的工程检索层，但不再以“检索后直接拼大段文本进 prompt”作为默认唯一形态；prompt/context 装配需要显式策略层。失败路径统一改为 `fail closed`：编码、review、structured output、runtime/tooling 任一关键环节失败，都必须进入明确失败或 `needs_attention`，不能伪装成 non-blocking 成功。

**Tech Stack:** FastAPI, Python 3.11+, SQLite, builtin agents, MCP, local worktrees, unittest, existing control/session/task stores, RAGFacade, skills.

---

## Relationship To Existing Docs

- Architecture:
  - `docs/architecture/agent-first-implementation-principles.md`
  - `docs/architecture/agent-system-overview.md`
  - `docs/architecture/agent-runtime-contracts.md`
  - `docs/architecture/main-chain-operator-runbook.md`
- Current continuity:
  - `STATUS.md`
  - `docs/internal/handoffs/2026-03-23-context-sync-handoff.md`
  - `docs/internal/handoffs/2026-03-23-review-fix-followup-handoff.md`
- Previous main-chain plans:
  - `docs/plans/2026-03-23-main-chain-engineering-hardening-detailed.md`
  - `docs/plans/2026-03-23-main-chain-phase-2-resume-and-ops-hardening.md`
  - `docs/plans/2026-03-23-main-chain-phase-5b-failure-drills-and-live-readiness.md`

## Non-Negotiable Decisions

- `ralph` 是编码主路径的内置 agent，不再把 `sleep_coding.execution.command` 视为标准执行面。
- `code-review-agent` 是 review 主路径的内置 agent，不再把 `review.skill_command` 视为标准执行面。
- `sleep_coding.execution.command` 与 `review.skill_command` 不再保留为降级成功路径。
- 如果内置 agent runtime 缺少完成主链所需的本地能力，真实链路直接失败并暴露证据。
- review runtime、LLM structured output、context assembly、workspace access 任一关键步骤失败时，必须显式失败或进入 `needs_attention`，不允许自动回退成 “blocking=false” 或 dry-run 通过。
- RAG 先是 runtime 工程层，不是“把检索结果原样硬塞进 system prompt”的借口。

## Problem Statement

当前主链的主要偏移有四类：

1. `AgentRuntime` 把 workspace instructions、skills、MCP tools、retrieved context 直接拼进单个 system prompt，缺少显式上下文装配策略层。
2. `RalphDraftingService.build_execution_draft()` 仍以 `sleep_coding.execution.command` 或 LLM JSON `file_changes` 为核心执行面，没有真正的 agent-native 本地读写/执行闭环。
3. `ReviewSkillService.run()` 仍以 `review.skill_command` 或 LLM structured output 为核心 review 面，且失败时存在 minimal/non-blocking fallback。
4. failure semantics 仍偏 demo-friendly，而不是 production-friendly：部分失败会被转成 dry-run / fallback 继续链路，而不是明确暴露 runtime 不可用。

本计划的目标不是继续“把外部 command 配得更好”，而是把主链的执行 ownership 收回到内置 agent。

## File / Module Responsibility Map

### Runtime / Prompt Assembly

- Modify: `app/runtime/agent_runtime.py`
  - 从“system prompt 拼接器”升级为显式 context assembly 入口。
- Create: `app/runtime/context_policy.py`
  - 定义 bootstrap/workspace/skills/RAG/MCP/output contract 的装配顺序、预算和失败策略。
- Create: `tests/test_agent_runtime_policy.py`
  - 覆盖上下文装配、budget、RAG 注入策略与失败语义。

### Ralph Agent-Native Local Execution

- Modify: `app/agents/ralph/drafting.py`
  - 移除 `sleep_coding.execution.command` 主路径依赖；把“生成 draft JSON”纠偏为“Ralph 使用内置 runtime 完成本地工作树任务”。
- Modify: `app/agents/ralph/application.py`
  - 显式声明 Ralph runtime capability 要求与失败语义。
- Modify: `app/agents/ralph/workflow.py`
  - 调整 approve-plan 后的执行链路，不再依赖外部 command 作为标准路径。
- Create: `app/agents/ralph/runtime_executor.py`
  - 统一封装 Ralph 的本地读写、命令执行、文件变更收集、artifact 汇总。
- Test: `tests/test_sleep_coding.py`

### Review Agent-Native Workspace Review

- Modify: `app/agents/code_review_agent/skill.py`
  - 移除 `review.skill_command` / dry-run review 成功语义；失败必须显式失败。
- Modify: `app/agents/code_review_agent/context.py`
  - 提升 review context 构建，优先真实 workspace diff / changed files / validation evidence。
- Modify: `app/agents/code_review_agent/application.py`
  - 把 review runtime failure 投影到 control/review task truth，不再伪装成 non-blocking review。
- Create: `app/agents/code_review_agent/runtime_reviewer.py`
  - 封装内置 review agent 的本地 diff 分析、上下文采样、结构化输出校验。
- Test: `tests/test_review.py`

### Failure / State / Diagnostics

- Modify: `app/control/automation.py`
  - 接住 coding/review runtime failure，统一 terminal semantics。
- Modify: `app/infra/diagnostics.py`
  - 对 operator 暴露 “runtime capability missing / review runtime failed / context assembly failed”。
- Modify: `app/models/schemas.py`
  - 补充 agent-native execution/review evidence schema。
- Test: `tests/test_automation.py`
- Test: `tests/test_runtime_components.py`
- Test: `tests/test_mvp_e2e.py`

### Docs / Continuity

- Modify: `docs/architecture/agent-runtime-contracts.md`
- Modify: `docs/architecture/agent-first-implementation-principles.md`
- Modify: `docs/architecture/main-chain-operator-runbook.md`
- Modify: `STATUS.md`
- Modify: latest relevant local handoff under `docs/internal/handoffs/`

## Chunk 1: Lock The Architecture Decision

### Objective

- 把“内置 agent 原生执行”正式写成 source of truth，终止 command-native 方向继续蔓延。

### Success Criteria

- 架构文档明确声明：
  - `Ralph` / `code-review-agent` 是主路径执行 owner
  - external command 不是主路径
  - failure must be explicit
- 计划和状态文档不再把外部 command 描述成推荐能力面。

### Task 1.1: Update runtime contract docs

**Files:**
- Modify: `docs/architecture/agent-runtime-contracts.md`
- Modify: `docs/architecture/agent-first-implementation-principles.md`
- Modify: `docs/architecture/agent-system-overview.md`

- [ ] Step 1: Add failing doc-consistency grep checks or lightweight assertions in a new docs regression if needed.
- [ ] Step 2: Rewrite the coding/review ownership sections so builtin agents own execution and review reasoning end to end.
- [ ] Step 3: State that missing builtin runtime capability is a chain failure, not a reason to silently downgrade.
- [ ] Step 4: Re-read the three docs together and remove contradictory wording about command-driven execution.

### Task 1.2: Update continuity and operator docs

**Files:**
- Modify: `docs/architecture/main-chain-operator-runbook.md`
- Modify: `STATUS.md`
- Modify: `docs/internal/handoffs/YYYY-MM-DD-*.md`

- [ ] Step 1: Record the course-correction decision in continuity docs.
- [ ] Step 2: Update operator guidance so runtime capability failure surfaces as explicit blocking/needs_attention.
- [ ] Step 3: Ensure no continuity doc still recommends “configure a command and continue” as the default main-chain path.

### Chunk 1 Regression

- [ ] Run:
  - `rg -n "execution.command|review.skill_command|dry-run review|fallback" docs/architecture docs/plans STATUS.md docs/internal/handoffs -g '*.md'`
- [ ] Check drift:
  - docs now match the intended agent-native architecture
  - no source-of-truth doc still frames external commands as the standard path

---

## Chunk 2: Introduce Explicit Runtime Context Policy

### Objective

- 把当前“把一切拼进 system prompt”的做法重构成有策略的上下文装配层。

### Success Criteria

- context assembly 具备显式 policy：
  - bootstrap/system instruction
  - workspace instructions
  - skills catalog vs loaded instructions
  - RAG retrieval merge policy
  - MCP tool exposure
  - output contract placement
  - budget / truncation / failure behavior
- RAG 结果不再默认作为生文本硬塞；进入 prompt 需要通过 policy。

### Task 2.1: Add failing tests for prompt/context assembly policy

**Files:**
- Create: `tests/test_agent_runtime_policy.py`
- Modify if needed: `tests/test_rag_capability.py`

- [ ] Step 1: Write a failing test requiring context assembly to separate bootstrap instructions, retrieved context, and output contract into explicit sections.
- [ ] Step 2: Write a failing test requiring retrieval policy to be able to return no injected context when policy says tool/runtime-only.
- [ ] Step 3: Write a failing test requiring context truncation to preserve higher-priority sections before lower-priority sections.
- [ ] Step 4: Run:
  - `python -m unittest tests.test_agent_runtime_policy tests.test_rag_capability -v`

### Task 2.2: Implement `context_policy.py`

**Files:**
- Create: `app/runtime/context_policy.py`
- Modify: `app/runtime/agent_runtime.py`

- [ ] Step 1: Define typed policy objects for prompt assembly.
- [ ] Step 2: Move section ordering and truncation logic out of `_build_system_prompt()`.
- [ ] Step 3: Add explicit handling for RAG injection modes:
  - disabled
  - inline prompt context
  - runtime-only metadata (no prompt injection)
- [ ] Step 4: Fail explicitly if a required policy input is missing instead of silently flattening sections.
- [ ] Step 5: Re-run:
  - `python -m unittest tests.test_agent_runtime_policy tests.test_rag_capability -v`

### Chunk 2 Regression

- [ ] Run:
  - `python -m unittest tests.test_agent_runtime_policy tests.test_rag_capability tests.test_main_agent -v`
- [ ] Check drift:
  - context policy remains deterministic boundary code, not heuristic cognition code
  - RAG is still an engineering retrieval layer, not a second orchestration plane

---

## Chunk 3: Replace Command-Native Ralph Execution With Agent-Native Local Execution

### Objective

- 让 `Ralph` 作为 builtin agent 真正拥有本地 worktree 编码与验证闭环，不再依赖 `sleep_coding.execution.command`。

### Success Criteria

- `approve_plan` 后的标准路径不需要 `sleep_coding.execution.command`
- Ralph runtime 能在 worktree 内：
  - 读文件
  - 修改文件
  - 收集 diff / changed files
  - 记录 artifact / commit summary
  - 运行 validation
- 若缺少本地执行能力，任务明确失败，不走 fallback JSON 伪执行

### Task 3.1: Add failing tests for commandless agent-native execution

**Files:**
- Modify: `tests/test_sleep_coding.py`

- [ ] Step 1: Write a failing test that disables `sleep_coding.execution.command` and still expects Ralph to perform the normal coding path through builtin runtime.
- [ ] Step 2: Write a failing test that asserts missing runtime capability produces explicit failure, not heuristic `file_changes`.
- [ ] Step 3: Run:
  - `python -m unittest tests.test_sleep_coding.SleepCodingServiceTests -v`

### Task 3.2: Implement `runtime_executor.py`

**Files:**
- Create: `app/agents/ralph/runtime_executor.py`
- Modify: `app/agents/ralph/drafting.py`
- Modify: `app/agents/ralph/application.py`
- Modify: `app/agents/ralph/workflow.py`

- [ ] Step 1: Define the builtin Ralph execution contract around local worktree operations.
- [ ] Step 2: Replace `_resolve_execution_command()` as the default execution path with builtin runtime execution.
- [ ] Step 3: Keep generated artifacts structured, but make them the projection of real local work rather than the primary source of file edits.
- [ ] Step 4: Remove success-path fallback to heuristic `file_changes`.
- [ ] Step 5: Re-run:
  - `python -m unittest tests.test_sleep_coding.SleepCodingServiceTests -v`

### Task 3.3: Tighten git/worktree integration around builtin execution

**Files:**
- Modify: `app/infra/git_workspace.py`
- Modify if needed: `app/models/schemas.py`
- Test: `tests/test_sleep_coding.py`

- [ ] Step 1: Ensure worktree prep, changed-file collection, and commit/push evidence align with agent-native execution.
- [ ] Step 2: Keep commit/push as deterministic projection, but do not let dry-run masquerade as completed coding in live mode.
- [ ] Step 3: Re-run:
  - `python -m unittest tests.test_sleep_coding -v`

### Chunk 3 Regression

- [ ] Run:
  - `python -m unittest tests.test_sleep_coding tests.test_sleep_coding_worker tests.test_mvp_e2e -v`
- [ ] Check drift:
  - Ralph remains the cognition/execution owner
  - no new command-native main path was introduced

---

## Chunk 4: Replace Command-Native Review With Agent-Native Workspace Review

### Objective

- 让 `code-review-agent` 作为 builtin agent 真正拥有 workspace review 闭环，不再依赖 `review.skill_command`。

### Success Criteria

- 默认 review 路径不需要 `review.skill_command`
- review context 优先基于真实 workspace diff / changed files / validation evidence
- review runtime failure 明确失败，不再 fallback 成 minimal non-blocking review

### Task 4.1: Add failing tests for explicit review failure semantics

**Files:**
- Modify: `tests/test_review.py`

- [ ] Step 1: Write a failing test requiring runtime review failure to surface as failure/needs_attention rather than `blocking=false`.
- [ ] Step 2: Write a failing test requiring malformed structured output to fail the review, not produce a permissive fallback.
- [ ] Step 3: Run:
  - `python -m unittest tests.test_review.ReviewServiceTests -v`

### Task 4.2: Implement `runtime_reviewer.py`

**Files:**
- Create: `app/agents/code_review_agent/runtime_reviewer.py`
- Modify: `app/agents/code_review_agent/skill.py`
- Modify: `app/agents/code_review_agent/context.py`
- Modify: `app/agents/code_review_agent/application.py`

- [ ] Step 1: Define builtin review contract around workspace diff + validation evidence + task goal.
- [ ] Step 2: Remove dry-run success-path review and permissive non-blocking fallback from the standard runtime path.
- [ ] Step 3: Keep strict structured output validation as a hard gate.
- [ ] Step 4: Project runtime review failures onto review task/control task truth.
- [ ] Step 5: Re-run:
  - `python -m unittest tests.test_review -v`

### Chunk 4 Regression

- [ ] Run:
  - `python -m unittest tests.test_review tests.test_automation tests.test_mvp_e2e -v`
- [ ] Check drift:
  - review reasoning still belongs to the review agent, not to deterministic control code
  - failure semantics are now explicit and operator-visible

---

## Chunk 5: Unify Fail-Closed Main-Chain Semantics

### Objective

- 把 coding/review/runtime/context 失败统一收口成可诊断、不可误报的主链终态。

### Success Criteria

- 没有任何关键 runtime failure 会再投影成“看起来通过”
- diagnostics 能看出：
  - builtin execution capability missing
  - builtin review capability missing
  - context assembly failure
  - structured output failure
- live chain 只在 capability ready 时运行

### Task 5.1: Add failing automation/diagnostics tests

**Files:**
- Modify: `tests/test_automation.py`
- Modify: `tests/test_runtime_components.py`
- Modify: `tests/test_live_chain.py`

- [ ] Step 1: Add a failing test for review runtime failure that must halt final delivery.
- [ ] Step 2: Add a failing diagnostics test that exposes missing builtin runtime capability as blocking.
- [ ] Step 3: Add a failing live-chain prerequisite test requiring builtin coding/review capability to be present.
- [ ] Step 4: Run:
  - `python -m unittest tests.test_automation tests.test_runtime_components tests.test_live_chain -v`

### Task 5.2: Tighten control/diagnostics projections

**Files:**
- Modify: `app/control/automation.py`
- Modify: `app/infra/diagnostics.py`
- Modify if needed: `app/control/task_registry.py`
- Modify if needed: `app/models/schemas.py`

- [ ] Step 1: Introduce explicit terminal evidence for runtime capability failure and structured-output failure.
- [ ] Step 2: Prevent final delivery if review truth is missing, invalid, or failed.
- [ ] Step 3: Ensure operator endpoints tell the same truth as runtime state.
- [ ] Step 4: Re-run:
  - `python -m unittest tests.test_automation tests.test_runtime_components tests.test_live_chain -v`

### Chunk 5 Regression

- [ ] Run:
  - `python -m unittest tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e -v`
- [ ] If live prerequisites are ready, run:
  - `python -m unittest tests.test_live_chain -v`
- [ ] Update `STATUS.md`
- [ ] Update local handoff

---

## Final Regression Pack

- [ ] Run:
  - `python -m unittest tests.test_agent_runtime_policy tests.test_rag_capability tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_sleep_coding_worker tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e tests.test_framework_public_surface -v`
- [ ] If live prerequisites are ready, run:
  - `python -m unittest tests.test_live_chain -v`
- [ ] Re-read:
  - `docs/architecture/agent-first-implementation-principles.md`
  - `docs/architecture/agent-runtime-contracts.md`
  - `docs/architecture/main-chain-operator-runbook.md`
  - `STATUS.md`
  - latest relevant local handoff

## Final Done Criteria

- builtin `ralph` is the standard coding execution owner on the main chain.
- builtin `code-review-agent` is the standard review owner on the main chain.
- `sleep_coding.execution.command` and `review.skill_command` are no longer required for the standard chain and no longer act as silent downgrade success paths.
- runtime/context/structured-output failures are explicit and operator-visible.
- prompt/context assembly has an explicit policy layer instead of a flat string concatenation path.
- RAG remains an engineering retrieval layer and only injects prompt context through explicit policy.
- final delivery cannot happen unless coding and review truth are both real, valid, and complete.
