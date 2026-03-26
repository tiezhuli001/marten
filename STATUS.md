## Goal

推进 `Marten` 的“私有服务器自用”第一阶段上线与后续纠偏：

- `Feishu` 作为主入口，`Web/API` 作为诊断、运维和备用入口
- 保持唯一主链 `Feishu/API -> main-agent -> ralph -> code-review-agent -> delivery`
- 保持 `LLM + MCP + skill first`，工程代码只保留状态真相、队列、超时、诊断和 delivery gate
- 真实链路失败时暴露根因，不用宽松 fallback 伪装成功

## Current Phase

- `private-server self-host rollout` 已完成
- `live-chain root-cause correction` 及其两个 follow-up 已完成本轮实现、harness 补强、回归和 fresh live 验证
- `agent-first codebase reduction` 已在 `2026-03-26` 完成最终收口、delta gate 与 fresh verification

## Done Criteria

- 第一阶段 self-host 目标与 `README.md` / `docs/README.md` / `STATUS.md` 口径一致
- 主链保持 `main-agent -> ralph -> code-review-agent -> delivery`
- transport retry、structured-output failure、operator evidence、delivery truth 的边界明确且实现一致
- `docs + tests` 相对基线净减重达到 `2,000+` 行
- `quick / regression / manual / live` 全部 fresh 通过

## Current Target

- 以 `2026-03-26` fresh live 结果为当前运行基线
- 保持 fail-closed failure semantics，不恢复关键路径 permissive fallback
- 当前没有已证明安全的并发层删减候选，不直接删 SQLite / lane / claim 层
- 当前没有未完成的仓内执行 chunk；如进入下一阶段，应先写新计划

## Next Action

- 若继续下一轮：
  - 先新建新的执行计划，不再继续复用已完成的 `2026-03-25` reduction / live-correction 计划
  - 只有在未来某个 workflow 真正引入强协议需求时，才新增 strict parser 或新的 tool-call runtime

## Completed Work

- `2026-03-24` 第一阶段 self-host rollout 已完成：
  - 单任务队列与单活执行槽已落地
  - `Feishu` 主入口 session continuity 与 busy/queued 语义已落地
  - repo continuity、operator surface、split-process 启动契约已落地
- `2026-03-25` 文档与仓库减法已完成一轮收口：
  - 清理 `docs/archive/` 中大批历史 rollout / architecture 草稿
  - 收紧 `README.md` / `docs/README.md` 推荐阅读路径
  - 删除 `examples/private_agent_suite/` 与 `tests/test_private_project_example.py`
  - 将 RAG 收紧为 facade / policy / in-memory 示例保留面
- `2026-03-26` `agent-first codebase reduction` 已闭环：
  - `docs/archive/` 从 `3,412` 行 / `15` 个 Markdown 文件收口到 `253` 行 / `3` 个文件
  - `docs/` 总量从 `8,275` 行降到 `6,068` 行
  - `tests/test_framework_public_surface.py` 从默认回归移到 `manual`，并收紧到 `43` 行 smoke
  - `tests/test_rag_capability.py` 从 `528` 行收紧到 `164` 行，只保留 facade retrieval 与 runtime merge contract
  - `tests/test_rag_indexing.py` 维持 `manual`，不再作为默认主链回归面
  - `app/rag/providers/*` 已删除，`app/rag/` 当前仅保留 `465` 行最小 retained surface
  - `docs + tests` 从基线 `20,110` 行降到 `18,023` 行，净减重 `2,087` 行
- `2026-03-25` 真实链路纠偏已完成：
  - `app/agents/ralph/drafting.py`
    - 移除 execution provider failure 后的 heuristic success fallback
  - `app/agents/ralph/runtime_executor.py`
  - `app/agents/code_review_agent/runtime_reviewer.py`
    - structured output failure 现在保留 `failure_evidence`
  - `app/agents/ralph/application.py`
  - `app/agents/code_review_agent/application.py`
    - execution / review 失败现在显式写回 control task evidence，并进入 `needs_attention`
  - `app/runtime/agent_runtime.py`
    - `sleep_coding` / `code_review` 明确为无真实 tool-call loop 的 structured / artifact boundary
  - `app/runtime/structured_output.py`
    - 明确当前职责是宽容边界提取，不是主链强协议解析器
  - `docs/architecture/live-chain-failure-semantics.md`
    - 新增 failure semantics、runtime capability matrix、并发 inventory 真相说明
    - 新增 `parse_structured_object()` call-site matrix
- `2026-03-25` 并发纠偏结论已落地：
  - 未做“看起来重复就删除”的锁层减法
  - 先完成 inventory 审计，再只修真实 bug
  - 已修复 terminal delivery 错释放 execution lane 的问题：
    - `app/control/automation.py`
    - `tests/test_automation.py::test_final_delivery_releases_lane_for_sleep_coding_control_task`
  - 已补同 session 并发幂等与 worker claim 行为 harness：
    - `tests/test_gateway.py::test_same_session_duplicate_message_is_idempotent_under_concurrency`
    - `tests/test_session_registry.py::test_release_non_active_task_removes_only_queued_entry`
    - `tests/test_sleep_coding_worker.py::test_poll_once_marks_claim_queued_when_lane_is_owned_by_other_task`
    - `tests/test_session_registry.py::test_acquire_same_queued_task_id_is_idempotent`
    - `tests/test_sleep_coding_worker.py::test_poll_once_claims_queued_issue_after_lane_is_released`
  - 已验证 `Gateway` session lock 仍有真实语义价值：
    - no-op lock 实验下，同 session 重复消息会被并发处理两次，不能直接删除
  - 已验证 `execution_lane` 与 worker claim lease 不是同一层状态副本：
    - lane 负责 active / queued 单活 truth
    - claim lease 负责 issue poll / lease / retry 生命周期
- `2026-03-26` fresh live 再验证通过：
  - 最新 issue: `#233`
  - 最新 sleep-coding control task: `beb885c0-df10-4984-927f-fea4e899aa32`
  - 最新 sleep-coding task: `3fabd549-0fc5-44ad-ae63-14af3904f5af`
  - 最新 review run: `073256b1-d6c3-4d46-884d-5047cb1875ce`
  - 最新 PR: `https://github.com/tiezhuli001/marten/pull/234`
  - live 完成后 `execution_lane` 已自动回空，不再残留 active task

## In Progress

- 无当前执行中的实现项

## Blockers

- 无

## Verification

- `python -m unittest tests.test_main_agent tests.test_sleep_coding tests.test_review tests.test_session_registry tests.test_sleep_coding_worker -v`
  - PASS (`Ran 99 tests in 3.536s`)
- `python -m unittest tests.test_gateway tests.test_session_registry tests.test_sleep_coding_worker -v`
  - PASS (`Ran 36 tests in 1.090s`)
- `python scripts/run_test_suites.py quick`
  - PASS (`Ran 132 tests in 9.063s`)
- `python scripts/run_test_suites.py regression`
  - PASS (`Ran 224 tests in 11.539s`)
- `python scripts/run_test_suites.py manual`
  - PASS (`Ran 4 tests in 0.010s`)
- `python scripts/run_test_suites.py live`
  - PASS (`Ran 4 tests in 84.283s`)
- `find app -type f -name '*.py' -print0 | xargs -0 wc -l | tail -n 1`
  - PASS (`15,637 total`)
- `find tests -type f -name '*.py' -print0 | xargs -0 wc -l | tail -n 1`
  - PASS (`11,955 total`)
- `find docs -type f -name '*.md' -print0 | xargs -0 wc -l | tail -n 1`
  - PASS (`6,068 total`)
- `python - <<'PY' ... sessions.get_execution_lane() ... PY`
  - PASS:
    - `active_task_id: None`
    - `queued_task_ids: []`
