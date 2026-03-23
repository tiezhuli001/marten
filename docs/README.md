# Docs

本目录现在按“当前真相”和“历史材料”分层。

目标只有三个：

- 说明当前仍成立的系统事实
- 固化当前 agent system 与 RAG 的稳定边界
- 让任何 agent 只靠 handoff、设计文档、执行计划就能继续推进

目录语义如下：

- `architecture/`: 当前正式生效的架构边界、状态模型、系统 contract
- `evolution/`: 当前仍有效的演进约束与 rollout 方向
- `handoffs/`: 交接文档规则与模板
- `plans/`: 当前可执行的实现计划
- `archive/`: 历史方案、旧阶段计划、已被取代的设计文档

`docs/internal/` 只作为本地工作目录存在，不属于公开主文档树，也不应提交远程仓库。具体 handoff、会话交接、临时 baseline 等本地文档统一放在这里；需要共享的内容，应先提炼后进入 `architecture/`、`evolution/`、`handoffs/` 或 `plans/`。

文档与实现约束：

- 不要直接在 `main` 分支上修改；开始任何实现前先创建工作分支
- `docs/handoffs/` 只放规则与模板，不放具体 handoff
- 具体 handoff、session 交接、临时 baseline 统一进入 `docs/internal/`

## Current Source Of Truth

如果你要理解当前 `Marten`，推荐按下面顺序阅读。

### 1. 当前主链与状态事实

- [architecture/current-mvp-status-summary.md](architecture/current-mvp-status-summary.md)
- [architecture/github-issue-pr-state-model.md](architecture/github-issue-pr-state-model.md)
- [architecture/mvp-agent-platform-core.md](architecture/mvp-agent-platform-core.md)

### 2. 当前 agent system 正式边界

- [architecture/agent-first-implementation-principles.md](architecture/agent-first-implementation-principles.md)
- [architecture/agent-system-overview.md](architecture/agent-system-overview.md)
- [architecture/agent-runtime-contracts.md](architecture/agent-runtime-contracts.md)
- [architecture/main-chain-operator-runbook.md](architecture/main-chain-operator-runbook.md)

### 3. 当前 RAG 正式边界

- [architecture/rag-provider-surface.md](architecture/rag-provider-surface.md)

### 4. 当前演进方向

- [evolution/mvp-evolution.md](evolution/mvp-evolution.md)
- [evolution/agent-system-rollout-plan.md](evolution/agent-system-rollout-plan.md)
- [evolution/rag-provider-rollout-plan.md](evolution/rag-provider-rollout-plan.md)

### 5. 当前执行依据

- [handoffs/README.md](handoffs/README.md)
- [handoffs/templates/agent-handoff-template.md](handoffs/templates/agent-handoff-template.md)
- [plans/2026-03-22-agent-system-documentation-and-rollout.md](plans/2026-03-22-agent-system-documentation-and-rollout.md)
- [plans/2026-03-22-rag-provider-surface-rollout.md](plans/2026-03-22-rag-provider-surface-rollout.md)

本地继续执行时，还应额外查看：

- `docs/internal/handoffs/` 下与当前任务相关的最新 handoff（若存在）

## Minimal Read Set Before Implementation

如果目标是继续实现，而不是重新讨论方向，至少先读完下面 7 份文档：

1. [architecture/agent-first-implementation-principles.md](architecture/agent-first-implementation-principles.md)
2. [architecture/agent-system-overview.md](architecture/agent-system-overview.md)
3. [architecture/agent-runtime-contracts.md](architecture/agent-runtime-contracts.md)
4. [architecture/rag-provider-surface.md](architecture/rag-provider-surface.md)
5. [handoffs/README.md](handoffs/README.md)
6. [plans/2026-03-22-agent-system-documentation-and-rollout.md](plans/2026-03-22-agent-system-documentation-and-rollout.md)
7. [plans/2026-03-22-rag-provider-surface-rollout.md](plans/2026-03-22-rag-provider-surface-rollout.md)

## Historical References

上一轮仍有长期解释价值的架构推演文档，现已下沉到 `archive/`：

- [archive/architecture/2026-03-22-framework-positioning-and-private-agent-layering.md](archive/architecture/2026-03-22-framework-positioning-and-private-agent-layering.md)
- [archive/architecture/2026-03-22-framework-public-surface.md](archive/architecture/2026-03-22-framework-public-surface.md)
- [archive/architecture/2026-03-22-multi-endpoint-channel-routing.md](archive/architecture/2026-03-22-multi-endpoint-channel-routing.md)
- [archive/architecture/2026-03-22-rag-capability-mvp.md](archive/architecture/2026-03-22-rag-capability-mvp.md)
- [archive/architecture/mvp-agent-first-architecture.md](archive/architecture/mvp-agent-first-architecture.md)

这些文档仍可用于回溯“为什么会这样演进”，但不应继续充当当前实现入口。纯阶段性旧计划、过期 handoff 和只剩临时执行痕迹的历史文件，已经直接删除，不再保留。

## Cleaning Rules

- 不让 `architecture/` 同时承载“当前真相”和“上一轮设计推演”
- 不让 `evolution/` 同时承载“长期方向”和“已经完成的旧计划”
- 不把内部临时 handoff、工作日志、运行产物直接暴露为主文档
- 不在 `docs/handoffs/` 中存放具体 handoff；具体 handoff 只允许进入 `docs/internal/`
- 任何已经被新 canonical 文档覆盖的旧文档，应先总结，再归档
