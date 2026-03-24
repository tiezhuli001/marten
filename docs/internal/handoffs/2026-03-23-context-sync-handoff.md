# 2026-03-23 Context Sync Handoff

## Current Stage

- `private-server self-host rollout` 计划已完成实现与回归验证

## Current Goal

- 以 `docs/plans/2026-03-24-private-server-self-host-rollout.md` 为当前唯一执行计划
- 当前产品目标是：
  - 私有服务器自用
  - `Feishu` 主入口，`Web/API` 辅助入口
  - 配置驱动选择任意单个有权限的 GitHub 仓库
  - 单用户单任务优先，明确 busy/queued 语义
- 继续守住基础架构约束：
  - 唯一主链 `gateway -> main-agent -> ralph -> code-review-agent -> delivery`
  - `LLM + MCP + skill first`
  - `quick / regression / live` 分层测试不回退
  - runtime / review failure 继续 fail-closed

## Next Concrete Action

- 当前实现目标已完成，下一步不再是仓内继续补 chunk。
- 如果继续推进，优先做：
  - 目标私有服务器上的真实部署
  - `live_test.enabled=true` 后的 live suite 验收
  - 真实使用后的下一阶段多 agent / 子 agent 隔离规划

## 2026-03-24 Drift Cleanup Audit

- 已完成文档与实现二次复核，目标是清掉 rollout 结束后仍可能误导接手人的残留口径。
- 文档修正：
  - `STATUS.md`
    - 删除过期 `Chunk 3 进行中` 残留
  - `docs/internal/handoffs/2026-03-23-context-sync-handoff.md`
    - 为后续 chunk 日志补充“历史归档”说明
    - 历史小节中的“当前下一步”统一改为“当时记录的下一步”
  - `docs/architecture/current-mvp-status-summary.md`
    - 更新时间同步到 `2026-03-24`
    - 明确 self-host 第一阶段 rollout 已完成，当前工作重心是服务器部署与真实环境验收
- 实现复核：
  - `app/main.py` 仍保持纯 API 入口，没有重新内挂 scheduler
  - `scripts/run_worker_scheduler.py` 仍是独立 worker 入口
  - `app/infra/diagnostics.py` 仍通过 `self_host_boot` 暴露 `split_process` 契约
- 当前结论：
  - 未发现 rollout 完成后的实现回退
  - 未发现会误导下一个 agent 的“仍在进行中”文档残留

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
  - `tests/test_mvp_e2e.py` 现已显式注入 fake main-agent runtime，不再用 `test-key` 外呼真实 OpenAI
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
- 完成测试性能优化：
  - `app/testing/__init__.py`
  - `app/testing/suites.py`
  - `scripts/run_test_suites.py`
    - 新增 `quick / regression / live` 分层测试入口
  - `app/agents/main_agent/application.py`
    - 移除 service 层额外 runtime retry
  - `app/agents/code_review_agent/skill.py`
    - 移除 service 层额外 runtime retry
  - `tests/test_live_chain.py`
    - live profile 改为更短 timeout / 单次尝试 / 更密轮询
  - `scripts/run_sleep_coding_validation.py`
    - 修正过时 smoke 测试引用
  - `tests/test_test_suites.py`
    - 新增 suite layering 回归
- 完成 live prompt / evidence hardening：
  - `app/runtime/context_policy.py`
    - 支持按 agent/workflow 覆盖 prompt `max_chars`
  - `app/runtime/agent_runtime.py`
    - prompt policy 解析改为感知 `agent_id` / `workflow`
  - `platform.json`
    - 对 `main-agent` 启用 agent-specific prompt 截断
  - `tests/test_agent_runtime_policy.py`
    - 新增 agent-specific truncation 回归
  - `app/agents/code_review_agent/context.py`
    - review diff evidence / workspace snapshot 增加 deterministic truncation
  - `tests/test_review.py`
    - 新增 oversized review context 截断回归
- 本轮 live 调试中暴露并修复的两个真实 blocker：
  - `main-agent` intake 在 `MiniMax-M2.5` 下因 prompt 过重而 30s 超时
  - `code-review-agent` 在 Ralph 改动偏大时因 review context 超大而 30s 超时
  - 两处均通过缩小 prompt / evidence 体积修复，而非放宽 timeout 掩盖问题

## Verification

- `python -m unittest tests.test_sleep_coding.SleepCodingServiceTests tests.test_review.ReviewServiceTests -v`
  - PASS
- `python -m unittest tests.test_sleep_coding_worker tests.test_automation tests.test_mvp_e2e -v`
  - PASS
- `python -m unittest tests.test_agent_runtime_policy tests.test_rag_capability tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_sleep_coding_worker tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e tests.test_framework_public_surface -v`
  - PASS (`Ran 150 tests in 118.537s`)
- `python -m unittest tests.test_live_chain -v`
  - PASS (`Ran 2 tests in 150.540s`)
- `python -m unittest tests.test_main_agent tests.test_review tests.test_runtime_components tests.test_test_suites -v`
  - PASS (`Ran 62 tests in 9.355s`)
- `python -m unittest tests.test_mvp_e2e -v`
  - PASS (`Ran 8 tests in 4.448s`)
- `python scripts/run_sleep_coding_validation.py`
  - PASS (`Ran 3 tests in 0.609s`)
- `command time -lp python scripts/run_test_suites.py quick`
  - PASS (`Ran 119 tests in 11.662s`, `real 13.26s`)
- `command time -lp python scripts/run_test_suites.py regression`
  - PASS (`Ran 154 tests in 17.561s`, `real 19.85s`)
- `python -m unittest tests.test_agent_runtime_policy -v`
  - PASS (`Ran 4 tests in 0.037s`)
- `python -m unittest tests.test_review -v`
  - PASS (`Ran 19 tests in 0.697s`)
- `command time -lp python scripts/run_test_suites.py live`
  - 首次 FAIL：`main-agent` intake `LLM provider request timed out after 30.0 seconds`
  - 二次 FAIL：review background follow-up timeout，现场 review context `219731` chars
  - 修复后 PASS (`Ran 4 tests in 139.008s`, `real 141.39s`)
- 旧非 live 基线：
  - `command time -lp python -m unittest tests.test_agent_runtime_policy tests.test_rag_capability tests.test_main_agent tests.test_gateway tests.test_sleep_coding tests.test_sleep_coding_worker tests.test_review tests.test_automation tests.test_runtime_components tests.test_mvp_e2e tests.test_framework_public_surface`
  - PASS (`real 123.38s`)

## Risks / Notes

- `runtime_reviewer.py` 当前只对可明确判定的 shape 偏差做最小规范化（例如 `repair_strategy: str -> list[str]`），其余 malformed structured output 仍然 fail-closed
- 文档 grep 里仍会命中 `fallback` / `execution.command` / `review.skill_command`，但这些命中现在是“禁止项/历史说明/计划项”，不是当前推荐实现
- live chain 依赖本地真实配置 readiness；本轮已重新真实执行并通过
- 当前性能收益主要来自：
  - 默认不跑 live-chain
  - service 层不再重复 retry
  - live test 自身的 poll / timeout 更紧
- 当前 live 稳定性额外依赖：
  - `main-agent` prompt 被 agent-specific context policy 收紧
  - review evidence 注入不再无上限展开完整 diff / workspace snapshot

## Immediate Re-entry Read Order

1. `README.md`
2. `STATUS.md`
3. `docs/README.md`
4. `docs/plans/2026-03-24-private-server-self-host-rollout.md`
5. `docs/architecture/agent-first-implementation-principles.md`
6. `docs/architecture/agent-system-overview.md`
7. `docs/architecture/agent-runtime-contracts.md`
8. 本 handoff

## 2026-03-24 Re-entry Sync

- 已重新确认当前工作分支为 `codex/context-sync-20260323`，不在 `main`
- 已按 re-entry 顺序重读：
  - `README.md`
  - `STATUS.md`
  - `docs/README.md`
  - `docs/architecture/current-mvp-status-summary.md`
  - `docs/architecture/agent-first-implementation-principles.md`
  - `docs/architecture/agent-system-overview.md`
  - `docs/architecture/agent-runtime-contracts.md`
  - `docs/evolution/mvp-evolution.md`
  - `docs/plans/2026-03-23-agent-native-runtime-followup-hardening.md`
  - `docs/plans/2026-03-23-main-chain-engineering-hardening-detailed.md`
  - 本 handoff
- 重新确认的当前阶段：
  - `test-chain layering and retry tightening` 已完成并通过 live 验收
- 重新确认的当前目标：
  - 守住 builtin-agent worktree-native 主链
  - 守住 `quick / regression / live` 分层测试入口
  - 不回退 command/fallback 兼容面
  - 继续 fail-closed
- 重新确认的下一步执行项：
  - 当前没有进行中的实现 chunk
  - 若继续迭代，优先压缩 live-chain 真实外部等待时间与上下文体积，但不放宽 timeout、不恢复 fallback、也不把 live 混回默认回归
- 结论：
  - 本次上下文同步未发现新的目标漂移
  - `STATUS.md` 与本 handoff 现已重新对齐

## 2026-03-24 Live Re-Verification

- 已重新运行 fresh verification：
  - `command time -lp python scripts/run_test_suites.py live`
- 结果：
  - FAIL (`Ran 4 tests in 184.887s`, `real 186.81s`)
- 第一真实失败点：
  - `tests.test_live_chain.LiveChainIntegrationTests.test_real_chain_uses_live_llm_mcp_review_and_feishu`
  - task `6b70bd78-b58b-45a3-98a3-ea72999af8df` 最终状态是 `needs_attention`，不是 `approved`
  - `background_follow_up_error = LLM provider request timed out after 30.0 seconds`
- 现场链路 evidence：
  - issue `#203`
  - PR `#204`
  - control task `b6eb10b7-3a3a-4d00-b9c5-0818f88b156e`
  - `follow_up.failed` 发生在 review/background follow-up 阶段，不是 intake readiness 阶段
- 当前结论更新：
  - 未提交改动里的优化方向仍成立：
    - live suite 被独立隔离
    - service 层重复 retry 已移除
    - main-agent prompt / review context 已收紧
  - 但 fresh live evidence 说明当前环境下整链路还未重新达到稳定通过状态
  - 因此不能再把“live 已通过”当作当前真相，除非后续修复后再次 fresh 验证通过

## 2026-03-24 Live Fix Completion

- 根因确认：
  - 失败不是单纯 review prompt 过大
  - `GitWorkspaceService.prepare_worktree()` 从当前工作分支 `HEAD` 开新 worktree，导致 live issue 的 PR 带上当前开发分支相对 `main` 的历史差异
  - review 因看到大量无关文件变更而正常进入 blocking repair loop，后续 background follow-up 再次命中 30s timeout
- 修复：
  - `app/infra/git_workspace.py`
    - worktree 基线改为优先从仓库基线分支起，而不是当前 `HEAD`
  - `tests/test_sleep_coding.py`
    - 新增 `test_prepare_worktree_uses_main_baseline_instead_of_current_head`
- 修复后验证：
  - `python -m unittest tests.test_sleep_coding.GitWorkspaceServiceTests.test_prepare_worktree_uses_main_baseline_instead_of_current_head -v`
    - PASS
  - `python -m unittest tests.test_sleep_coding.GitWorkspaceServiceTests -v`
    - PASS
  - `command time -lp python scripts/run_test_suites.py live`
    - PASS (`Ran 4 tests in 92.458s`, `real 94.23s`)
- 当前结论：
  - live-chain 已重新 fresh 验证通过
  - 本轮修复保持 fail-closed 和 builtin-agent 主链约束，没有通过放宽 timeout 或恢复 fallback 来掩盖问题

## 2026-03-24 Self-Host Product Plan

- 新增计划：
  - `docs/plans/2026-03-24-private-server-self-host-rollout.md`
- 计划目标：
  - 私有服务器自用
  - `Feishu` 为主入口，`Web/API` 为辅
  - 任意单个有权限的 GitHub 仓库由配置与请求决定
  - 单用户单任务优先，队列化处理
  - 明确坚持 `LLM + MCP + skill first`
- 计划约束：
  - 不把系统做成重工程编排平台
  - 不引入多主任务并发
  - 工程层只保留单任务队列、状态真相、超时、诊断、delivery gate
- 已固定给下一个 agent 的关键决策：
  - `API/webhook` 独立进程
  - `scheduler/worker` 独立进程
  - 第一阶段不采用单进程内挂 scheduler
  - 一个任务只绑定一个 repo，遵循“请求优先，否则配置默认”
  - 当前阶段只做单活主任务，不实现新的多 agent runtime orchestration
- 推荐下一步执行顺序：
  - Chunk 1: Self-host product boundary
  - Chunk 2: Single-task queue and lane hardening
  - Chunk 3: Feishu-first inbound hardening
  - Chunk 5: Repo continuity
  - Chunk 4: API operator surface
  - Chunk 6: Deployment baseline
  - Chunk 7: Guard LLM-first boundaries
  - Chunk 8: Final verification and continuity sync

> 以下 Chunk 小节保留为 `2026-03-24` 当天的执行归档。
> 其中“下一步”表述均指当时顺序，不代表当前还有未完成实现。

## 2026-03-24 Chunk 1 Completion

- 已完成 `Chunk 1: Define Self-Host Product Boundary`
- 完成内容：
  - `README.md`
    - 增加私有服务器自用运行形态、双进程最小运行模型、单任务约束
  - `docs/architecture/main-chain-operator-runbook.md`
    - 增加单任务/排队/busy operator 说明
  - `STATUS.md`
    - 增加 self-host 第一阶段 done criteria
  - `tests/test_main_agent.py`
    - 覆盖 request repo 优先并写入 control task truth
  - `tests/test_mvp_e2e.py`
    - 覆盖 request repo 通过公开 API surface round-trip
- 目标偏移检查：
  - 没有把 repo 选择扩成新的业务规则引擎
  - 没有增加第二条主链
  - 文档入口保持 `LLM + MCP + skill first`，没有退回重编排叙事
- 验证：
  - `rg -n "self-host|single-flight|Feishu|single tenant|single task" README.md docs STATUS.md`
    - PASS
  - `python -m unittest tests.test_main_agent tests.test_mvp_e2e -v`
    - PASS (`Ran 24 tests in 2.175s`)
- 当前结论：
  - Chunk 1 已完成
  - 当时记录的下一步是 `Chunk 2: Single-task queue and lane hardening`

## 2026-03-24 Chunk 2 Completion

- 已完成 `Chunk 2: Single-Task Queue And Lane Hardening`
- 完成内容：
  - `app/models/schemas.py`
    - 新增 `workflow_state` / `active_task_id` 和 execution lane schema
  - `app/control/session_registry.py`
    - 新增持久化 execution lane（active + queued）
  - `app/control/gateway.py`
    - general / direct sleep-coding 入口增加 single-flight gate
    - queued / running truth 写回 control task payload
  - `app/control/workflow.py`
    - queued/running 请求不再继续自动 follow-up
  - `app/control/sleep_coding_worker.py`
    - worker 只允许当前 active lane 对应 parent 继续 claim
  - `app/control/automation.py`
    - 终态释放 execution lane
  - `app/channel/feishu.py`
    - ack 暴露 `workflow_state` / `active_task_id`
  - `tests/test_gateway.py`
    - 覆盖第二个 general 请求进入 queued
  - `tests/test_session_registry.py`
    - 覆盖 execution lane 状态迁移
  - `tests/test_mvp_e2e.py`
    - 覆盖公开 `/gateway/message` API 的 `accepted -> queued` 语义
- 目标偏移检查：
  - single-flight gate 放在 control-plane / worker 边界，没有塞进 agent prompt
  - 没有新增第二条主链
  - 只是增加队列真相和门禁，没有把系统改成复杂调度平台
- 验证：
  - `python -m unittest tests.test_gateway tests.test_session_registry tests.test_mvp_e2e -v`
    - PASS (`Ran 28 tests in 1.495s`)
- 当前结论：
  - Chunk 2 已完成
  - 当时记录的下一步是 `Chunk 3: Feishu-first self-host inbound hardening`

## 2026-03-24 Chunk 3 Completion

- 已完成 `Chunk 3: Feishu-First Self-Host Inbound Hardening`
- 完成内容：
  - `app/channel/endpoints.py`
    - endpoint 解析支持 canonical session ref 和 raw external ref 候选
  - `app/channel/feishu.py`
    - Feishu inbound 统一写入 canonical `session_key`
    - ack 暴露 `source_endpoint_id` / `delivery_endpoint_id`
  - `app/control/gateway.py`
    - 请求完成后把 session continuity / task linkage truth 写回 run/user session
  - `app/control/session_registry.py`
    - 新增 `record_session_turn()` 统一持久化 session-level truth
  - `app/control/context.py`
    - main-agent context 增加轻量 `Session State`
  - `app/infra/diagnostics.py`
    - `feishu` 组件增加 `inbound_status` / `delivery_status`
  - `tests/test_feishu.py`
    - 覆盖 canonical chat endpoint binding 回归
  - `tests/test_gateway.py`
    - 覆盖同一 Feishu session 下 stats -> coding continuity 回归
  - `tests/test_mvp_e2e.py`
    - 覆盖 Feishu stats -> coding endpoint continuity e2e
  - `tests/test_runtime_components.py`
    - 覆盖 Feishu inbound / delivery readiness diagnostics 回归
  - `README.md`
    - 增加 self-host 首次启动后的 Feishu smoke path 检查项
  - `docs/architecture/main-chain-operator-runbook.md`
    - 增加 Feishu diagnostics 字段和 operator 场景说明
- 目标偏移检查：
  - 这轮只补 deterministic inbound/session/diagnostics 边界，没有把入口行为下沉成新的工程编排层
  - `main-agent` 仍然负责 chat / coding 判断，工程层只补 continuity truth
  - `Feishu` 仍是主入口，`Web/API` 仍是 operator surface，没有长出第二控制面
- 验证：
  - `python -m unittest tests.test_feishu tests.test_gateway tests.test_mvp_e2e tests.test_runtime_components -v`
    - PASS (`Ran 54 tests in 8.206s`)
- 当前结论：
  - Chunk 3 已完成
  - 当时记录的下一步是 `Chunk 5: Config-driven single-repo-at-a-time execution`

## 2026-03-24 Chunk 5 Completion

- 已完成 `Chunk 5: Config-Driven Single-Repo-At-A-Time Execution`
- 完成内容：
  - `app/control/task_store.py`
    - 新增 `find_latest_task()`，用于恢复最新待处理 intake repo truth
  - `app/control/task_registry.py`
    - 暴露 `find_latest_task()` 给 worker / control 层
  - `app/control/sleep_coding_worker.py`
    - worker poll repo 解析优先级改为：
      - `request.repo`
      - execution lane active/queued parent repo
      - 最新待处理 main-agent intake repo
      - 最后才回退默认 repo
    - claim/start_task 时优先继承 parent repo
  - `app/agents/ralph/workflow.py`
    - Ralph start_task 优先继承 `parent_task.repo`
  - `tests/test_main_agent.py`
    - 补 request repo 进入开工通知的回归
  - `tests/test_sleep_coding_worker.py`
    - 覆盖 active parent repo 优先于默认 repo
  - `tests/test_mvp_e2e.py`
    - 覆盖 custom repo 从 intake -> worker -> review -> delivery 全链路 continuity
- 目标偏移检查：
  - 只补 repo truth 的继承链，没有新增 repo 路由引擎
  - 仍然保持“一个任务只绑定一个 repo”，没有扩成多 repo 并行平台
  - `LLM + MCP + skill first` 主边界未变，工程层只补 deterministic continuity
- 验证：
  - `python -m unittest tests.test_main_agent tests.test_sleep_coding_worker tests.test_mvp_e2e -v`
    - PASS (`Ran 39 tests in 3.161s`)
- 当前结论：
  - Chunk 5 已完成
  - 当时记录的下一步是 `Chunk 4: API as operator surface`

## 2026-03-24 Chunk 4 Completion

- 已完成 `Chunk 4: API As Operator Surface, Not Second Control Plane`
- 完成内容：
  - `app/models/schemas.py`
    - 新增 operator snapshot / control-task operator action schema
  - `app/api/routes.py`
    - 新增 `GET /control/operator/state`
    - 新增 `POST /control/tasks/{task_id}/actions`
  - `app/control/automation.py`
    - 新增 deterministic `handle_control_task_action()`
    - 支持 `approve_plan` / `resume` / `mark_needs_attention`
  - `app/control/task_store.py`
    - `find_latest_task()` 支持跨 task type 查最近失败项
  - `app/control/task_registry.py`
    - operator snapshot 可消费最近失败 control task truth
  - `tests/test_runtime_components.py`
    - 覆盖 operator state 返回 active / queued / recent failure
  - `tests/test_mvp_e2e.py`
    - 覆盖 `/control/operator/state` 真实返回 active / queued
  - `tests/test_automation.py`
    - 覆盖 control task action 的 approve_plan / resume / mark_needs_attention
  - `README.md`
    - 增加 operator state / control task actions 入口
  - `docs/architecture/main-chain-operator-runbook.md`
    - operator 检查顺序改为先看 `/control/operator/state`
- 目标偏移检查：
  - API 只暴露 deterministic control truth 和最小人工动作，没有复制新的业务状态机
  - review/coding 推理仍留在 agent 侧，没有被迁成 API if/else 编排
  - 单租户单任务 operator 语义更清晰，但项目没有长成“控制面平台”
- 验证：
  - `python -m unittest tests.test_runtime_components tests.test_mvp_e2e tests.test_automation -v`
    - PASS (`Ran 56 tests in 7.000s`)
- 当前结论：
  - Chunk 4 已完成
  - 当时记录的下一步是 `Chunk 6: server deployment baseline`

## 2026-03-24 Chunk 6 Completion

- 已完成 `Chunk 6: Server Deployment Baseline`
- 完成内容：
  - `app/main.py`
    - API 进程不再内挂 scheduler
  - `app/infra/scheduler.py`
    - 新增 `run_forever()`，供独立 worker 进程使用
  - `scripts/run_worker_scheduler.py`
    - 新增最小 scheduler/worker 进程入口
  - `app/infra/diagnostics.py`
    - 新增 `repo_contract`
    - 新增 `self_host_boot`
  - `tests/test_runtime_components.py`
    - 覆盖 self-host boot readiness / split-process contract
  - `README.md`
    - 增加 API / worker 双进程启动契约
  - `docs/architecture/main-chain-operator-runbook.md`
    - 增加 `self_host_boot` 的 operator 判读规则
- 目标偏移检查：
  - 只是把既定双进程模型落成启动契约，没有引入新部署框架
  - diagnostics 只补自检 truth，没有发明新的运行编排层
  - worker 仍然通过既有 automation / sleep-coding 主链工作
- 验证：
  - `python -m unittest tests.test_runtime_components tests.test_mvp_e2e tests.test_live_chain -v`
    - PASS (`Ran 43 tests in 6.227s`, `skipped=1`)
- 当前结论：
  - Chunk 6 已完成
  - 当时记录的下一步是 `Chunk 7: preserve LLM-first agent boundaries while productizing`

## 2026-03-24 Chunk 7 Audit

- 已完成 `Chunk 7: Preserve LLM-First Agent Boundaries While Productizing`
- 完成内容：
  - `docs/architecture/agent-first-implementation-principles.md`
    - 明确 self-host 阶段允许保留的确定性控制：
      - single-flight queue
      - repo continuity
      - operator snapshot / control task actions
      - self-host boot diagnostics / split-process startup contract
- 审计结论：
  - 新增 API/operator 逻辑仍停留在 deterministic control truth，没有把 planning/review 推理迁回控制面
  - `main-agent` 仍负责 chat / coding handoff 判断
  - `ralph` 仍负责 worktree coding / validation
  - `code-review-agent` 仍负责 review 结论
- 验证：
  - `python -m unittest tests.test_main_agent tests.test_review -v`
    - PASS (`Ran 34 tests in 0.826s`)

## 2026-03-24 Final Verification Sweep

- 已完成最终 full verification sweep
- 验证：
  - `python scripts/run_test_suites.py regression`
    - PASS (`Ran 170 tests in 9.809s`)
  - `python -m unittest tests.test_live_chain -v`
    - PASS (`Ran 4 tests in 210.589s`)
- 当前结论：
  - self-host rollout 所有 chunk 已完成
  - 当前仓库已经达到“私有服务器自用第一阶段可交付”的实现状态
