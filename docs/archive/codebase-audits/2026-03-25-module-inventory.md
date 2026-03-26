# 2026-03-25 Module Inventory

> 更新时间：2026-03-26
> 文档角色：仓库减法完成后的历史审计快照，用来解释“为什么保留这些边界、为什么删掉其余外围面”。

## Scope

本次 inventory 的判断基线不是“这个模块是否写得漂亮”，而是：

- 是否属于当前 self-host 单链主产品
- 是否属于主链必须保留的边界/稳定性工程面
- 是否属于未来演进保留面，但不应继续膨胀成当前产品默认复杂度

结论标签：

- `core`: 当前主链直接依赖
- `boundary`: 当前主链需要，但职责应保持工程边界而非继续扩编排
- `keep_for_evolution`: 当前不删，但不应继续被当作当前最小产品面

## App Module Classification

| Module | Files | Lines | Classification | Evidence |
| --- | ---: | ---: | --- | --- |
| `app/agents` | 20 | 4408 | `core` | 当前三 agent 主链本体 |
| `app/control` | 14 | 3840 | `core` | 单任务队列、状态真相、repair loop、operator truth |
| `app/channel` | 6 | 926 | `core` | Feishu 主入口与 delivery |
| `app/api` | 2 | 291 | `core` | 当前 operator/API surface |
| `app/infra/diagnostics.py` + `app/infra/scheduler.py` + `app/infra/git_workspace.py` | 3 | 891 | `boundary` | split-process、diagnostics、worktree materialization |
| `app/runtime` | 9 | 1898 | `boundary` | LLM/MCP/skills/structured output 运行时边界 |
| `app/core` | 3 | 884 | `boundary` | 配置与日志，是当前工程边界 |
| `app/models` | 3 | 650 | `boundary` | schema / contract 真相 |
| `app/ledger` | 2 | 784 | `boundary` | token / usage 记录已接入主链，不是死代码 |
| `app/rag` | 3 | 465 | `keep_for_evolution` | 当前只保留 facade、policy、in-memory provider 与 indexing helper，不视为当前最小主链面 |
| `app/framework` | 3 | 140 | `keep_for_evolution` | 公共 facade / future-facing surface，保留但只用 manual smoke 守面 |
| `app/infra/background_jobs.py` | 1 | 48 | `boundary` | follow-up event bus 的工程封装 |

## Largest App Files

| File | Lines | Classification |
| --- | ---: | --- |
| `app/control/automation.py` | 923 | `core`, 但过胖，后续应拆边界 |
| `app/core/config.py` | 875 | `boundary`, 但过胖 |
| `app/runtime/mcp.py` | 802 | `boundary`, 但过胖 |
| `app/ledger/service.py` | 783 | `boundary`, 非删除候选 |
| `app/models/schemas.py` | 634 | `boundary`, 可考虑拆 schema 主题 |
| `app/agents/ralph/application.py` | 626 | `core`, 但过胖 |
| `app/agents/code_review_agent/application.py` | 595 | `core`, 但过胖 |
| `app/control/sleep_coding_worker.py` | 591 | `core`, 但过胖 |
| `app/agents/main_agent/application.py` | 563 | `core`, 但过胖 |
| `app/agents/ralph/workflow.py` | 532 | `core`, 但过胖 |

## Reduced Test Surface

| Test Module | Lines | Classification | Decision |
| --- | ---: | --- | --- |
| `tests.test_feishu` | 225 | `core` | promote to `regression` |
| `tests.test_session_registry` | 154 | `core` | promote to `regression` |
| `tests.test_task_registry` | 117 | `core` | promote to `regression` |
| `tests.test_channel_routing` | 99 | `core` | promote to `regression` |
| `tests.test_control_context` | 59 | `boundary` | promote to `regression` |
| `tests.test_llm_runtime` | 552 | `boundary` | promote to `regression` |
| `tests.test_token_ledger` | 287 | `boundary` | promote to `regression` |
| `tests.test_channel` | 129 | `boundary` | promote to `regression` |
| `tests.test_rag_capability` | 164 | `keep_for_evolution` | keep in `quick/regression`, but only with minimal retrieval/runtime contract coverage |
| `tests.test_framework_public_surface` | 43 | `keep_for_evolution` | keep manual-only, single smoke for public facade |
| `tests.test_rag_indexing` | 87 | `keep_for_evolution` | keep manual-only, not default suite |
| `tests.test_private_project_example` | 0 | `delete` | removed with private example cleanup |

## Current Decision

- 当前不删除 `RAG`
- 当前不删除 `framework` facade，但它不再属于默认回归或默认阅读入口
- 当前删除 `private_agent_suite` 示例文件与专属测试，不再把 example 当主仓库默认复杂度
- 当前优先处理测试入口：把属于主链或边界的测试纳入 `regression`
- 对仅服务未来演进的测试，只保留 `manual` smoke：
  - `tests.test_framework_public_surface`
  - `tests.test_rag_indexing`
- 当前 reduction close-out 后的净结果：
  - `docs + tests`: `20,110 -> 18,023`
  - 净减重：`2,087` 行
