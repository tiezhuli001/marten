# 2026-03-23 Context Sync Handoff

## Current Stage

- `agent-native runtime follow-up hardening` 已完成并通过 live-chain 验收

## Current Goal

- 保持 builtin-agent worktree-native 主链稳定：
  - `gateway -> main-agent -> ralph -> code-review-agent -> delivery`
- 不回退 `sleep_coding.execution.command` / `review.skill_command` / `allow_llm_fallback` 之类旧兼容面
- 保持 fail-closed：runtime / structured output / review failure 必须显式暴露

## Next Concrete Action

- 当前计划已执行完成
- 如果后续继续改动，优先在现有 builtin-agent 主链上迭代，不恢复 command/fallback 路径

## What Was Completed

- 新增纠偏计划：
  - `/Users/litiezhu/workspace/github/marten/docs/plans/2026-03-23-agent-native-runtime-course-correction.md`
- 完成文档纠偏：
  - `docs/architecture/agent-runtime-contracts.md`
  - `docs/architecture/agent-system-overview.md`
  - `docs/architecture/agent-first-implementation-principles.md`
  - `docs/architecture/main-chain-operator-runbook.md`
  - `docs/architecture/current-mvp-status-summary.md`
- 完成 runtime context policy：
  - `app/runtime/context_policy.py`
  - `app/runtime/agent_runtime.py`
  - `app/rag/retrieval.py`
  - `tests/test_agent_runtime_policy.py`
- 完成 Ralph agent-native 执行纠偏：
  - `app/agents/ralph/runtime_executor.py`
  - `app/agents/ralph/drafting.py`
  - builtin execution 缺少凭据时显式失败
  - builtin execution 非法 structured output 时显式失败
- 完成 review agent-native 纠偏：
  - `app/agents/code_review_agent/runtime_reviewer.py`
  - `app/agents/code_review_agent/skill.py`
  - review runtime failure 不再伪装成 non-blocking review
  - malformed structured review output 不再 permissive fallback
- 完成回归夹具同步：
  - `tests/test_sleep_coding.py`
  - `tests/test_review.py`
  - `tests/test_sleep_coding_worker.py`
  - `tests/test_automation.py`
  - `tests/test_mvp_e2e.py`
- 完成 follow-up hardening 收口：
  - `app/core/config.py`
    - 删除 `sleep_coding.execution.command`
    - 删除 `sleep_coding.execution.allow_llm_fallback`
    - 删除 `review.skill_command`
  - `app/infra/diagnostics.py`
    - live readiness / diagnostics 只认 builtin runtime truth
  - `app/agents/ralph/drafting.py`
    - 删除旧 command-compatible 执行壳
  - `app/models/schemas.py`
    - 补充 worktree-native execution / review evidence schema
  - `app/infra/git_workspace.py`
    - 补充真实 changed files / diff evidence capture
  - `app/agents/ralph/workflow.py`
  - `app/agents/ralph/application.py`
    - Ralph 输出真实 worktree evidence 并投影 validation workspace
  - `app/agents/code_review_agent/context.py`
    - review context 始终带任务级 changed files / diff / validation evidence
    - 若有 workspace snapshot，则作为附加证据而不是替代任务证据
  - `app/agents/code_review_agent/application.py`
    - review start 强制 execution evidence，control task 持久化 `review_evidence`
  - `app/control/automation.py`
  - `app/control/task_registry.py`
    - delivery / recovery 仅消费真实 execution/review truth
  - `tests/test_live_chain.py`
    - live-chain 真实通过，验证 Ralph 编码、validation、PR、review、final delivery 整链路

## Verification

- `python -m unittest tests.test_sleep_coding.SleepCodingServiceTests tests.test_review.ReviewServiceTests -v`
  - PASS
- `python -m unittest tests.test_sleep_coding_worker tests.test_automation tests.test_mvp_e2e -v`
  - PASS
- `python -m unittest tests.test_agent_runtime_policy tests.test_rag_capability tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_sleep_coding_worker tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e tests.test_framework_public_surface -v`
  - PASS (`Ran 150 tests in 118.537s`)
- `python -m unittest tests.test_live_chain -v`
  - PASS (`Ran 2 tests in 150.540s`)

## Risks / Notes

- `runtime_reviewer.py` 当前只对可明确判定的 shape 偏差做最小规范化（例如 `repair_strategy: str -> list[str]`），其余 malformed structured output 仍然 fail-closed
- 文档 grep 里仍会命中 `fallback` / `execution.command` / `review.skill_command`，但这些命中现在是“禁止项/历史说明/计划项”，不是当前推荐实现
- live chain 依赖本地真实配置 readiness；本次已在当前环境中通过

## Immediate Re-entry Read Order

1. `README.md`
2. `STATUS.md`
3. `docs/README.md`
4. `docs/plans/2026-03-23-agent-native-runtime-followup-hardening.md`
5. `docs/architecture/agent-first-implementation-principles.md`
6. `docs/architecture/agent-system-overview.md`
7. `docs/architecture/agent-runtime-contracts.md`
8. 本 handoff
