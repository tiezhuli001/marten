# Session Handoff

> 更新时间：2026-03-21 23:40 CST
> 用途：当需要切换到下一个 agent 继续执行时，提供最小但足够的接手事实集。

## 1. 当前目标状态

- 本轮目标已经从“继续收口”推进到“对齐文档与真实仓库状态，并完成剩余 post-MVP cleanup 批次”。
- 当前仓库真相仍然围绕单条 MVP 主链：
  - `Feishu/Webhook -> gateway/workflow -> main-agent -> ralph -> code-review-agent -> final delivery`
- 不要把已完成的 closure sprint 误读成“只做了局部整理”。本轮已经继续完成剩余批次并做了回归验证。

## 2. 当前分支

- 分支：`codex/post-mvp-iteration-closure`

## 3. 本轮新增完成事实

### Review contract 继续收口

- `ReviewSource` 已从主模型和主持久化读写路径退出。
- `ReviewRun` 现在直接保存 `target`，review 统一回到 task-derived `ReviewTarget`。
- `review_runs` 新写入使用 `target_payload`；读取仍兼容历史 `source_payload`，仅作为迁移兜底。
- 自动化主链不再依赖 `ReviewSource` 概念做恢复或回写。

### 状态真相进一步收敛

- `SleepCodingWorkerService._sync_claim_statuses()` 已改为从 `control_tasks` 同步 claim 状态和错误，而不是从 `sleep_coding_tasks` 直接推导。
- `sleep_coding_issue_claims` 的 task 绑定现在通过 control task 的 `external_ref=sleep_coding_task:<task_id>` 恢复 domain task id。
- 自动化 review loop 已把 `latest_review_*`、`blocking_review_count`、`review_round` 投影回父 `sleep_coding` control task。
- 自动化恢复路径优先读取 control task projection，仅在兜底时读取 `review_runs` artifact。

### 运行时兼容层继续收紧

- `models.json` provider 读取已收为 canonical snake_case：
  - `protocol`
  - `api_key`
  - `api_base`
  - `default_model`
  - `pricing_provider`
- 运行时测试与 README 示例已同步为 canonical key。

### 文档归档完成

- `docs/architecture/mvp-agent-platform-core.md` 继续作为 canonical 架构文档。
- `docs/archive/architecture/mvp-agent-first-architecture.md` 已正式归档。
- `README.md` 与 `docs/README.md` 的公开阅读入口已改到当前真实文档结构。

## 4. 当前测试状态

### 已通过

- `python -m compileall app tests`
- `python -m unittest tests/test_review.py tests/test_automation.py tests/test_sleep_coding_worker.py tests/test_runtime_components.py tests/test_llm_runtime.py -v`
  - 结果：`Ran 61 tests ... OK`
- `python -m unittest tests/test_mvp_e2e.py -v`
  - 结果：`Ran 5 tests ... OK`
- `python -m unittest discover -s tests -v`
  - 结果：`Ran 128 tests in 207.727s OK`
- 本分支此前已通过单独 `tests/test_live_chain.py -v`，且本轮全量 `discover` 已再次覆盖 `test_real_chain_uses_live_llm_mcp_review_and_feishu`

## 5. 关键实现变化

- `app/models/schemas.py`
  - 新增/收敛 `ReviewTarget`
  - `ReviewRun.source -> ReviewRun.target`
- `app/agents/code_review_agent/store.py`
  - review run 新写入 `target_payload`
  - 读取兼容 legacy `source_payload`
- `app/agents/code_review_agent/application.py`
  - review/control projection 回写到父 control task
- `app/control/automation.py`
  - review loop 支持从 control task projection 恢复
  - 修复 rerun coding 后旧 review projection 造成的无限循环
- `app/control/sleep_coding_worker.py`
  - claim status 同步改为基于 `control_tasks`
- `app/core/config.py`
  - provider config 仅读 canonical key

## 6. 如果下一位 agent 接手，优先做什么

1. 先确认当前 dirty worktree 是否已经全部提交。
2. 再跑一遍本轮最终三段验证：
   - `python -m unittest tests/test_mvp_e2e.py -v`
   - `python -m unittest tests/test_live_chain.py -v`
   - `python -m unittest discover -s tests -v`
3. 如果要继续演进，不要回退这些已完成约束：
   - review 只围绕 `task_id -> ReviewTarget`
   - worker/control 状态以 `control_tasks` 为主投影
   - provider config 只接受 canonical snake_case
   - `mvp-agent-platform-core` 是唯一公开 canonical 架构文档

## 7. 接手红线

- 不要重新引入 `ReviewSource` 作为主 contract。
- 不要再把 `sleep_coding_tasks` / `review_runs` 提升回与 `control_tasks` 并列的主编排真相。
- 不要把 `docs/internal/` 临时文档重新暴露为公开架构入口。
