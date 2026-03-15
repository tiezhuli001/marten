# Token Ledger Reporting Design

> 更新时间：2026-03-15
> 目标：为日报和近 7/30 天查询提前定义数据与查询设计

## 当前基础

Phase 1 已经有最小表：

1. `requests`
2. `workflow_runs`
3. `token_usage_records`

当前只完成了最小写入，还没有正式时间窗口查询和日报任务。

## 设计目标

后续需要支持三类视图：

1. 单次请求 token 消耗
2. 指定时间窗口聚合
3. 每日汇总报表

## 查询场景

### 1. 请求结束后的即时返回

目标：

- 每个请求结束后，响应里带上 `token_usage`

### 2. 最近 7 天查询

目标：

- 用户主动查询近 7 天 token 总消耗
- 返回请求数、总 token、按意图分布

### 3. 最近 30 天查询

目标：

- 用户主动查询近 30 天 token 总消耗
- 返回请求数、总 token、趋势摘要

### 4. 昨日日报

目标：

- 每天固定时间生成昨日汇总
- 先写入数据库，再由 OpenClaw / 飞书读取转发

## 建议新增字段

### `requests`

建议后续增加：

- `source`
- `user_id`
- `intent`
- `status`

### `workflow_runs`

建议后续增加：

- `workflow_name`
- `started_at`
- `finished_at`
- `duration_ms`

### `token_usage_records`

建议后续增加：

- `model_name`
- `provider`
- `cost_usd`
- `step_name`

## 建议新增聚合表

### `daily_token_summaries`

字段建议：

- `summary_date`
- `request_count`
- `workflow_run_count`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `estimated_cost_usd`
- `created_at`

## 报表生成策略

### 日报任务

建议每天 `10:00` 生成前一日汇总。

流程：

```text
定时任务触发
-> 统计昨日 token_usage_records
-> 写入 daily_token_summaries
-> 生成自然语言摘要
-> 写入状态源 / 推送给 OpenClaw
```

### 周期查询

近 7/30 天查询建议优先实时算，不先做复杂缓存。

原因：

1. 初期数据量不大
2. 查询逻辑简单
3. 先保证正确性

## 查询返回建议

### 最近 7 天 / 30 天

返回内容建议：

- 时间窗口
- 请求数
- workflow 数
- 总 token
- 按 intent 聚合
- Top 消耗任务

### 昨日日报

返回内容建议：

- 昨日总请求数
- 昨日总 token
- 昨日主要消耗来源
- 是否较前一天上升

## 推荐实现顺序

1. 先补时间窗口 SQL 查询
2. 再补日报聚合表
3. 再补定时任务
4. 最后接 OpenClaw / 飞书通知

## 设计结论

日报和 7/30 天查询不应该依赖 LLM 记忆。  
正确做法是：

- token 原始记录实时写库
- 查询逻辑直接基于数据库
- 自然语言摘要只是展示层
