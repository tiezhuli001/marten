# Session Handoff

> 更新时间：2026-03-19

## 1. 当前目标

- 目标不变：
  `Feishu inbound -> gateway -> issue -> claim -> coding -> review -> final delivery`
- 当前工作重点不再是补功能，而是继续瘦身
- 判断标准是：
  - 更少的工程代码
  - 更少的 `app/services/*`
  - 更少的历史文档
  - 更多依赖 prompt / MCP / skill 发挥 agent 能力

## 2. 本轮已落地的减法

- 已删除历史 compat/service 入口：
  - `app/services/background_jobs.py`
  - `app/services/channel.py`
  - `app/services/diagnostics.py`
  - `app/services/feishu.py`
  - `app/services/git_workspace.py`
  - `app/services/github.py`
  - `app/services/main_agent.py`
  - `app/services/review.py`
  - `app/services/scheduler.py`
  - `app/services/sleep_coding.py`
  - `app/services/sleep_coding_worker.py`
  - `app/services/gitlab.py`
- review 边界已收口到：
  - `app/agents/code_review_agent/application.py`
  - `app/agents/code_review_agent/skill.py`
  - `app/agents/code_review_agent/gitlab.py`
  - `app/agents/code_review_agent/bridge.py`
- Ralph 边界已继续收口到：
  - `app/agents/ralph/application.py`
  - `app/agents/ralph/workflow.py`
  - `app/agents/ralph/progress.py`
  - `app/channel/ralph.py`
- 关键厚度变化：
  - `app/agents/ralph/workflow.py`: `404 -> 364`
  - `app/agents/code_review_agent/skill.py`: `245 -> 228`
  - `app/services/automation.py`: `280 -> 263`
  - `app/services/session_registry.py`: `256 -> 128`
  - `app/services/task_registry.py`: `341 -> 253`
- 本轮还额外删除了非主链路 API 表面积：
  - `/status/current`
  - `/workers/sleep-coding/run-once`
  - `/reports/tokens*`
- 本轮还删除了低价值 wrapper/历史测试：
  - `tests/test_api.py`
  - `tests/test_config.py`
  - `tests/test_router.py`
  - `tests/test_scheduler.py`
- 本轮还新增了更薄的控制面内核：
  - `app/control/review_loop.py`
  - `app/control/session_store.py`
  - `app/control/session_memory.py`
  - `app/control/task_store.py`
  - `app/control/task_events.py`

## 3. 文档收敛结果

当前 docs 只应保留：

- `docs/architecture/mvp-agent-first-architecture.md`
- `docs/architecture/github-issue-pr-state-model.md`
- `docs/evolution/mvp-evolution.md`
- `docs/status/current-status.md`
- `docs/status/session-handoff.md`

已删除：

- `docs/agents/README.md`
- `docs/architecture/token-ledger-reporting.md`
- `docs/plans/*`
- `docs/requirements/*`
- `docs/runbooks/server-setup.md`

## 4. 下一位 agent 的工作准则

- 不要再新增 `app/services/*` 兼容入口
- 不要为了“稳一点”把 agent 输出 fallback 回工程解析
- 不要恢复历史文档或阶段性计划副本
- 每次改完都要先检查是否仍符合：
  `channel -> control plane -> runtime -> agent`

## 5. 继续瘦身的优先顺序

1. 继续压 `app/agents/ralph/workflow.py`
2. 继续压 `app/agents/code_review_agent/skill.py`
3. 审查 `app/services/automation.py` 是否还有可继续下沉/删除的 orchestration
4. 保持 docs 最小集合，不再回流 requirements/plans

## 6. 交付前必须验证

- `python -m unittest discover -s tests -v`
- `python -m unittest tests.test_sleep_coding tests.test_review tests.test_automation tests.test_mvp_e2e -v`
- 确认 `tests.test_mvp_e2e` 覆盖的主链路仍通过
- 更新本文件和 `current-status.md`

## 7. 本轮验证结果

- 受影响核心回归：
  - `47 tests OK`
- 全量回归：
  - `87 tests OK`
- `tests.test_mvp_e2e` 已通过

## 8. 最新真实环境结果

- 真实链路已执行到外部仓库：
  - Issue `#56`
  - PR `#57`
  - merge commit `4e7ae48f31cf8cd7bb4fcc25006c844442ec2dfa`
  - 参考：
    - `https://github.com/tiezhuli001/youmeng-gateway/issues/56`
    - `https://github.com/tiezhuli001/youmeng-gateway/pull/57`
- 真实阻塞点已确认并修复：
  - `scripts/run_sleep_coding_validation.py` 原先引用了已删除的历史测试，导致 `approve_plan` 后 validation 失败
- 真实外部结果已确认：
  - GitHub issue 已关闭
  - PR 已 merged
  - Feishu webhook 已成功送达完成通知
