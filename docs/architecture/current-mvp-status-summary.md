# Current MVP Status Summary

> 更新时间：2026-03-22
> 用途：用一页说明当前公开仓库的真实架构、主链路、状态模型，以及文档声明与代码实现的对齐结果。

## 一、当前项目处于什么阶段

`Marten` 当前不在功能扩张期，而在 `post-MVP cleanup / 收口` 阶段。

判断标准不是“又加了多少能力”，而是：

- 是否继续收紧到单条 MVP 主链
- 是否继续减少并列真相源
- 是否让文档入口与真实代码状态一致
- 是否避免把内部临时推演重新暴露成公开架构

当前唯一优先保障的真实链路是：

`Feishu/Webhook -> gateway/workflow -> main-agent -> ralph -> code-review-agent -> final delivery`

## 二、当前架构摘要

仓库当前公开结构可以按 4 层理解：

### 1. `channel`

- 负责 Feishu webhook 和通知输出
- 只处理入口/出口，不承担主编排

### 2. `control plane`

- 负责 task lifecycle、worker poll、follow-up、review loop
- 当前唯一主编排层
- 真正的状态控制以 `control_tasks`、`task_events`、`session` 为中心

### 3. `runtime`

- 负责 provider、skill、MCP、token/cost accounting
- 保持 JSON-first 和 provider metadata 驱动

### 4. `agents`

- 当前只围绕三个内置 agent：
  - `main-agent`
  - `ralph`
  - `code-review-agent`

运行产物如 review markdown、workspace 文件、任务输出属于 `artifacts`，不是新的控制面。

## 三、当前运行链路

公开仓库已经收口成一条单任务主链：

1. 用户从 Feishu 或 API 提交需求
2. `main-agent` 把请求转成 GitHub issue / handoff
3. `ralph` worker 轮询 issue 并 claim 任务
4. `ralph` 在本地 worktree 中规划、编码、验证、提交 PR
5. `code-review-agent` 基于本地代码上下文执行 review
6. 如有阻塞问题，自动进入 repair loop，最多 3 轮
7. 最终结果统一写回平台，并发送 Feishu delivery

当前实现强调 `local-first`：

- coding 先落到本地 worktree
- review 先 materialize 到本地代码上下文
- GitHub / GitLab 只做 issue、PR、comment、status bridge
- 最终通知由控制面统一发送

## 四、当前状态模型

### 1. 编排真相

当前主编排真相是 `control_tasks`。

- `sleep_coding_tasks` 是 Ralph 域任务
- `review_runs` 是 review 运行产物
- 两者都不再与 `control_tasks` 并列为主真相

这意味着：

- worker claim 状态以 control task 投影为准
- review loop 恢复优先读 control task payload projection
- review artifact 只作为恢复兜底，不再承担主编排职责

### 2. Review contract

review 已经收口为：

- `task_id -> ReviewTarget`

不再以 `ReviewSource` 作为主 contract。

当前 `ReviewTarget` 的最小字段是：

- `task_id`
- `repo`
- `pr_number`
- `url`
- `workspace_path`
- `base_branch`
- `head_branch`

`ReviewRun` 直接保存 `target`，而不是 `source`。

### 3. 任务状态

当前稳定任务状态包括：

- `created`
- `planning`
- `awaiting_confirmation`
- `coding`
- `validating`
- `pr_opened`
- `in_review`
- `changes_requested`
- `approved`
- `merged`
- `failed`
- `cancelled`

GitHub 的 open/closed 不再直接充当业务状态真相。

## 五、当前阶段新增完成事实

在上一轮状态收口之后，主链又补完了一轮运行时防卡死加固。

### 1. 外部执行超时已补齐

当前主链上最容易卡死的 3 条外部执行路径已经补上超时控制：

- `sleep_coding.validation.timeout_seconds`
- `sleep_coding.execution.timeout_seconds`
- `review.command_timeout_seconds`

覆盖范围包括：

- Ralph validation command
- Ralph 本地 execution command
- Code Review 外部 command

这些超时都会把“无限等待”收敛成明确失败，不再让任务无界卡住。

### 2. repair loop 约束与外部执行约束已经形成闭环

当前主链已经同时具备两层防钻牛角尖保护：

- LLM 请求有单次超时和最大重试次数
- review repair loop 有最大轮次，达到上限后 handoff
- 外部命令执行也有超时，不会因为本地 command 卡死而绕过编排层约束

### 3. 当前测试状态

本轮 timeout hardening 后，已通过：

- `python -m unittest tests/test_runtime_components.py tests/test_sleep_coding.py tests/test_review.py tests/test_automation.py -v`
  - 结果：`Ran 63 tests ... OK`
- `python -m unittest tests/test_mvp_e2e.py -v`
  - 结果：`Ran 5 tests ... OK`
- `python -m unittest tests/test_live_chain.py -v`
  - 结果：`Ran 1 test in 127.159s ... OK`
- `python -m unittest discover -s tests -v`
  - 结果：`Ran 131 tests in 170.390s OK`

## 六、文档声明与真实代码的对照

下面是本轮最关键的 4 组实现对照。

### 1. Review 已从 `source` 收口到 `target`

代码事实：

- `app/models/schemas.py` 定义 `ReviewTarget`
- `app/models/schemas.py` 中 `ReviewRun` 直接保存 `target`
- `app/agents/code_review_agent/store.py` 读取时优先 `target_payload`
- `app/agents/code_review_agent/store.py` 仅在兼容历史数据时回退 `source_payload`
- `app/agents/code_review_agent/store.py` 兼容读取时会去掉旧 `source_type`
- `app/agents/code_review_agent/application.py` 新写入直接落 `target.model_dump_json()`

结论：

- `source_payload` 现在只承担历史迁移兜底
- 当前真实 review contract 已经是 `ReviewTarget`

### 2. review loop 状态回写到父 control task

代码事实：

- `app/agents/code_review_agent/application.py` 中 `_sync_parent_review_projection()` 会回写父任务 payload
- 回写字段包括：
  - `latest_review_id`
  - `latest_review_blocking`
  - `latest_review_status`
  - `latest_review_summary`
  - `review_round`
  - `blocking_review_count`
- `app/control/automation.py` 中 review loop 恢复优先读取 control task projection
- `app/control/automation.py` 中 rerun coding 后会清空过期 review projection，避免旧状态造成循环

结论：

- 自动化恢复路径已经以 `control_tasks` 投影为主
- `review_runs` 不再承担唯一恢复源角色

### 3. worker claim 状态以 `control_tasks` 为主投影

代码事实：

- `app/agents/ralph/workflow.py` 中 Ralph 创建 control task 时写入 `external_ref=sleep_coding_task:<task_id>`
- `app/control/sleep_coding_worker.py` 中 worker 会在 poll/list 路径中调用 `_sync_claim_statuses()`
- `_sync_claim_statuses()` 通过查询 `control_tasks` 中最新 `sleep_coding` task 的 `status` 和 `payload`
- `_extract_domain_task_id()` 通过 `external_ref=sleep_coding_task:<task_id>` 恢复 domain task id

结论：

- `sleep_coding_issue_claims` 不再单独推导真实业务状态
- claim 只是 worker 视角记录，编排真相仍回到 control plane

### 4. provider 配置只接受 canonical snake_case

代码事实：

- `app/core/config.py` 中 provider 协议读取走 `protocol`
- `app/core/config.py` 中 API key 读取走 `api_key`
- `app/core/config.py` 中 API base 读取走 `api_base`
- `app/core/config.py` 中默认模型读取走 `default_model`
- `app/core/config.py` 中定价提供方读取走 `pricing_provider`

结论：

- `models.json` 的 provider 元数据已经收口到 canonical snake_case
- README 示例与运行时解析口径一致

### 5. 外部执行路径已补统一超时

代码事实：

- `app/core/config.py` 新增 execution / validation / review command timeout 配置解析
- `app/agents/ralph/validation.py` 的 validation subprocess 现在带 timeout
- `app/agents/ralph/drafting.py` 的本地 execution subprocess 现在带 timeout
- `app/agents/code_review_agent/skill.py` 的 review command subprocess 现在带 timeout

结论：

- 主链不再只防 LLM HTTP 死等，也同时防本地外部命令无界阻塞

## 七、当前阶段的红线

如果后续继续演进，不应回退下面这些约束：

- 不要重新引入 `ReviewSource` 作为主 contract
- 不要把 `sleep_coding_tasks` 或 `review_runs` 提升回与 `control_tasks` 并列的主编排真相
- 不要把内部 handoff / 临时计划文档重新暴露为公开架构入口
- 不要把当前单条主链稀释成功能拼盘
- 不要重新把 validation / execution / review command 放回无超时状态

## 八、继续阅读

读完这份摘要后，建议继续看：

1. [mvp-agent-platform-core.md](mvp-agent-platform-core.md)
2. [github-issue-pr-state-model.md](github-issue-pr-state-model.md)
3. [mvp-evolution.md](../evolution/mvp-evolution.md)
4. [docs/README.md](../README.md)
