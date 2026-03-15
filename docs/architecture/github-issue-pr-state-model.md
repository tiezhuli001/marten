# GitHub Issue/PR State Model

> 更新时间：2026-03-15
> 目标：为睡后编程和后续 review 流程定义统一状态模型

## 设计目标

需要统一三类状态：

1. GitHub 外部状态
2. 内部任务状态
3. 用户决策状态

这样 OpenClaw、Gateway、worker 和后续 token 报表才能对齐同一份事实来源。

## 核心实体

### 1. Issue

表示需求入口。

关键字段：

- `issue_number`
- `title`
- `body`
- `labels`
- `state`
- `creator`
- `created_at`
- `labels`

### 2. Sleep Coding Task

表示内部执行状态。

关键字段：

- `task_id`
- `issue_number`
- `status`
- `repo`
- `base_branch`
- `head_branch`
- `worker_id`
- `started_at`
- `finished_at`

### 3. Pull Request

表示代码交付物。

关键字段：

- `pr_number`
- `head_branch`
- `base_branch`
- `state`
- `mergeable_state`
- `review_decision`
- `labels`

## 内部任务状态建议

建议统一以下状态：

1. `created`
2. `planning`
3. `awaiting_confirmation`
4. `coding`
5. `validating`
6. `pr_opened`
7. `in_review`
8. `changes_requested`
9. `approved`
10. `merged`
11. `failed`
12. `cancelled`

## 状态流转建议

```text
created
-> planning
-> awaiting_confirmation
-> coding
-> validating
-> pr_opened
-> in_review
-> approved -> merged
-> changes_requested -> coding
-> failed
-> cancelled
```

## GitHub 状态映射

### Issue

- `open`：需求可继续推进
- `closed`：任务已结束或取消

### Pull Request

- `open`：正在 review
- `closed + merged=false`：放弃或退回
- `closed + merged=true`：任务完成

## 用户动作模型

需要支持的用户动作：

1. `approve_plan`
2. `reject_plan`
3. `approve_pr`
4. `request_changes`
5. `cancel_task`

## 评论与状态写回策略

建议至少写回三个节点：

1. 计划生成完成时写回 Issue
2. PR 创建时写回 Issue 和 PR
3. 最终完成时写回 Issue、PR 和 `docs/status/current-status.md`

标签与通知补充：

- Issue 与 PR 默认带 `agent:ralph`、`workflow:sleep-coding`
- Channel 负责出站通知，不替代内部真实状态表

## 最小表结构建议

### `sleep_coding_tasks`

- `task_id`
- `issue_number`
- `status`
- `repo`
- `base_branch`
- `head_branch`
- `pr_number`
- `last_error`
- `created_at`
- `updated_at`

### `task_events`

- `id`
- `task_id`
- `event_type`
- `payload`
- `created_at`

## 设计结论

后续不要直接拿 GitHub 的 `open/closed` 当作全部业务状态。  
正确做法是：

- GitHub 保留外部协作状态
- 内部数据库保留真实执行状态
- `docs/status` 保留人类可读的项目阶段摘要
