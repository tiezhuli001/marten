# Current Status

> 更新时间：2026-03-19
> 当前阶段：能力内聚与仓库瘦身
> 当前目标：继续贴近 `LLM + MCP + skill`，限制工程复杂度和历史残留

## 当前结论

- 主链路目标没有变化：
  `Feishu inbound -> gateway -> issue -> claim -> coding -> review -> final delivery`
- 当前阶段已经不是补主链路功能，而是继续做减法
- 当前架构边界保持为：
  `channel -> control plane -> runtime -> agent`

## 本轮已完成

- 删除历史兼容层：
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
- review / gitlab 已收口到 agent 边界：
  - `app/agents/code_review_agent/skill.py`
  - `app/agents/code_review_agent/gitlab.py`
  - `app/agents/code_review_agent/application.py`
- Ralph 编排继续收口：
  - 计划通知在 `app/channel/ralph.py`
  - 进度写回在 `app/agents/ralph/progress.py`
  - `workflow.py` 继续减少 PR 发布写回细节
- review skill 继续收口为 strict JSON-first：
  - command output 必须直接返回 JSON
  - 不再容忍 markdown/code fence 形式的伪结构化输出
- docs 收口为最小必要集合：
  - 保留 `architecture/`
  - 保留 `evolution/`
  - 保留 `status/`
  - 删除旧 `plans/`、`requirements/`、`runbooks/`、`agents/README`
- 控制面与编排继续做了一轮内核收口：
  - review loop 决策已下沉到 `app/control/review_loop.py`
  - short-memory 已从 `SessionRegistryService` 分离到 `app/control/session_memory.py`
  - session CRUD 已下沉到 `app/control/session_store.py`
  - task CRUD 已下沉到 `app/control/task_store.py`
  - task/domain event 追加已下沉到 `app/control/task_events.py`

## 当前仓库状态

- `app/agents/ralph/workflow.py`: `364` 行
- `app/agents/code_review_agent/skill.py`: `228` 行
- `app/services/*.py` 已继续下降，当前只保留稳定领域服务：
  - `automation.py`：`263`
  - `observability.py`：`46`
  - `session_registry.py`：`128`
  - `task_registry.py`：`253`
- docs 文件已从历史混合状态收口到架构/演进/状态/交接
- 当前 diff 继续保持净减法：
  - `git diff --shortstat`: `+423 / -4993`
- tests 已继续收缩到当前核心边界：
  - `18 -> 14` 个核心测试文件保留
  - 总行数：`5923 -> 5138`

## 当前仍需继续的减法

- 继续压 `app/agents/ralph/workflow.py`
- 继续压 `app/agents/code_review_agent/application.py` 和 `skill.py`
- 持续检查是否有新代码回流到 `app/services/*`
- 保持“能交给 prompt / MCP / skill 的，不写 Python 兜底逻辑”

## 验证要求

本轮完成后必须继续满足：

- 高相关回归通过
- 全量回归通过
- `tests.test_mvp_e2e` 通过
- 模拟主链路 `gateway -> issue -> claim -> coding -> review -> final delivery` 通过

## 本轮验证结果

- 受影响核心回归：
  - `python -m unittest tests.test_control_context tests.test_session_registry tests.test_task_registry tests.test_automation tests.test_sleep_coding tests.test_sleep_coding_worker tests.test_review tests.test_mvp_e2e -v`
  - `47 tests OK`
- 全量回归：
  - `python -m unittest discover -s tests -v`
  - `87 tests OK`
- 模拟主链路：
  - `tests.test_mvp_e2e` 通过
  - 覆盖 `Feishu inbound -> gateway -> issue -> claim -> coding -> review -> final delivery`

## 真实环境验证

- 已修复真实链路阻塞点：
  - `scripts/run_sleep_coding_validation.py` 不再引用已删除的历史测试
- 已完成一次真实仓库验证：
  - Issue: `#56`
  - PR: `#57`
  - Merge Commit: `4e7ae48f31cf8cd7bb4fcc25006c844442ec2dfa`
- 验证范围覆盖：
  - GitHub issue 创建
  - Ralph 生成变更并打开 PR
  - GitHub review comment 写入
  - PR merge
  - Feishu webhook 通知成功送达

## 风险与约束

- 真实外部链路仍以 MCP / webhook / provider 配置为准
- `app_env=test` 继续用于隔离真实副作用
- 不允许为了“更优雅”重新引入厚服务层和历史 fallback
