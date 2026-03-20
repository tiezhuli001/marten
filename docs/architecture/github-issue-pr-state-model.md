# GitHub Issue/PR State Model

> 更新时间：2026-03-20
> 用途：记录当前真实主链路里 GitHub 外部状态和内部任务状态的最小映射。

## 主链路事实

当前真实链路固定为：

`Feishu inbound -> gateway -> issue -> claim -> coding -> review -> final delivery`

GitHub 只承载协作事实：

- Issue：需求入口
- PR：代码交付物
- Review：评审结论

内部控制面负责真实执行状态、重试、follow-up 和 token 记账。

## 外部实体

### Issue

- `issue_number`
- `title`
- `body`
- `labels`
- `state`

### Pull Request

- `pr_number`
- `head_branch`
- `base_branch`
- `state`
- `review_decision`

### Review

- `review_id`
- `state`
- `summary`
- `blocking_findings`

## 内部任务状态

当前主链路只关心这些稳定状态：

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

不再把 GitHub 的 `open/closed` 直接当成业务真相。

## 事件原则

- Issue draft 必须先经过 MainAgent intake。
- sleep-coding 和 review 只写当前域事件：
  - `follow_up.*`
  - `child.follow_up.*`
- review handoff 只围绕 `handoff_to_ralph`、`handoff_to_code_review`、`review_returned`。
- 不再保留 GitLab / 多来源 review 的历史事件枚举。

## 写回原则

- 计划完成后写回 Issue
- PR 创建后写回 Issue 和 PR
- Review 完成后写回 PR 和内部状态
- Final delivery 由控制面统一发送到 Feishu

## 当前结论

- GitHub 平台操作必须走 MCP，不再回摆到 GitHub REST 旁路。
- 内部数据库仍是任务状态、事件和 token ledger 的唯一真相源。
- 文档只记录当前仍有效的最小状态模型，不再保留旧阶段的大而全枚举。
