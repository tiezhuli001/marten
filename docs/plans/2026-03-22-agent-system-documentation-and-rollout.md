# Agent System Documentation And Rollout Plan

> **For agentic workers:** REQUIRED: Use handoff docs plus current architecture docs while executing. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `Marten` 的三 agent 主链文档收口成当前唯一可信入口，并为后续运行时实现提供明确执行计划。

**Architecture:** 先固定文档树和 canonical contract，再按 agent system 的正式闭环推进实现。任何后续实现必须围绕 `main-agent -> ralph -> code-review-agent -> final delivery`。

**Tech Stack:** Markdown docs, existing `agents/*/AGENTS.md`, task/review/PR lifecycle in current Python runtime.

---

## Chunk 1: 文档树收口

### Task 1: 确认当前主入口文档

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/archive/README.md`

- [ ] Step 1: 读取当前 docs 入口与 archive 说明
- [ ] Step 2: 明确 current source of truth 与 historical references
- [ ] Step 3: 更新 docs 入口，去掉旧阶段文档作为主入口的角色
- [ ] Step 4: 自查阅读顺序是否能让新 agent 在 10 分钟内知道从哪里开始

### Task 2: 归档上一轮已完成设计

**Files:**
- Move to archive: `docs/archive/architecture/*`
- Move to archive: `docs/archive/plans/*`

- [ ] Step 1: 识别上一轮已完成使命的设计与计划文档
- [ ] Step 2: 确保主文档树已有新的 canonical 替代
- [ ] Step 3: 再归档旧文档
- [ ] Step 4: 更新主入口中的历史映射

## Chunk 2: Agent System Canonical Docs

### Task 3: 写 `agent-system-overview.md`

**Files:**
- Create: `docs/architecture/agent-system-overview.md`

- [ ] Step 1: 固化三 agent 主链和状态机
- [ ] Step 2: 固化 review / repair 最多 3 轮规则
- [ ] Step 3: 固化 final delivery 只能在 review 通过后发生
- [ ] Step 4: 检查文档是否和当前 `current-mvp-status-summary.md` 一致

### Task 4: 写 `agent-runtime-contracts.md`

**Files:**
- Create: `docs/architecture/agent-runtime-contracts.md`
- Reference: `agents/main-agent/AGENTS.md`
- Reference: `agents/ralph/AGENTS.md`
- Reference: `agents/code-review-agent/AGENTS.md`

- [ ] Step 1: 为三个 agent 统一 contract 结构
- [ ] Step 2: 明确 allowed / forbidden work
- [ ] Step 3: 明确 input / output / handoff / failure
- [ ] Step 4: 检查 contract 是否能直接指导后续 prompt/runtime 文档收紧

## Chunk 3: Handoff System

### Task 5: 固化 handoff 规则和模板

**Files:**
- Create: `docs/handoffs/README.md`
- Create: `docs/handoffs/templates/agent-handoff-template.md`

- [ ] Step 1: 定义何时必须写 handoff
- [ ] Step 2: 定义最小字段
- [ ] Step 3: 定义 quality bar
- [ ] Step 4: 检查是否能支持跨轮次、跨 agent 接手

## Chunk 4: Implementation Rollout

### Task 6: 用本计划驱动后续实现

**Files:**
- Modify later: `agents/*/AGENTS.md`
- Modify later: relevant runtime/control-plane code

- [ ] Step 1: 先按 architecture + handoff docs 对齐 agent prompt 文档
- [ ] Step 2: 再把 runtime 状态机和 review loop 对齐文档
- [ ] Step 3: 增加回归测试覆盖 review / repair 最多 3 轮与 final delivery gating
- [ ] Step 4: 重新核对文档与实现是否偏移

## Verification

- [ ] `sed -n '1,240p' docs/README.md`
- [ ] `sed -n '1,260p' docs/architecture/agent-system-overview.md`
- [ ] `sed -n '1,320p' docs/architecture/agent-runtime-contracts.md`
- [ ] `sed -n '1,220p' docs/handoffs/README.md`
- [ ] `rg -n "framework-positioning|framework-public-surface|multi-endpoint-channel-routing|rag-capability-mvp|framework-implementation-plan" docs`

## Done Criteria

- 新 agent 不读 archive 也能找到正确入口
- handoff、architecture、plan 三层职责清楚
- 任何执行 agent 都能根据这些文档继续推进 agent system 实现
