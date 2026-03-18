# Phase 4 Plan

> 阶段名称：Token 账本与日报系统
> 目标：把平台的运营统计做成稳定能力
> 对应设计：[token-ledger-reporting.md](/Users/litiezhu/workspace/github/youmeng-gateway/docs/architecture/token-ledger-reporting.md)

## 一、阶段目标

本阶段要把“响应里带 token_usage”提升为“平台具备可查询、可汇总、可日报”的账本系统。

完成后应具备：

1. 近 7 天 token 查询
2. 近 30 天 token 查询
3. 每日 10 点昨日汇总
4. 可追踪的成本统计基础
5. 为后续周/月统计保留兼容聚合口径

本阶段还有一个额外要求：

> `Phase 4` 完成后，不继续立即扩展新 Agent，而是先对 `Phase 0 - Phase 4` 做一次整体 MVP 验证。

## 二、范围

### 本阶段要做

- 时间窗口查询 SQL
- `daily_token_summaries` 表
- 日报任务
- 7/30 天查询接口
- 报表摘要输出
- 为 Phase 0-4 联调准备一份 MVP 验证清单

### 本阶段不做

- 复杂 BI 仪表盘
- 多租户账本隔离
- 精确到供应商账单级对账
- Phase 5 及之后的功能预开发

### 本阶段说明

- 迭代计划里的“周/月统计”在本阶段先通过“近 7 天 / 近 30 天”实现 MVP
- 如果后续确实需要自然月口径，再在下一轮扩展按月聚合表

## 三、核心任务

### Task 4.1 原始 token 记录补字段

- `model_name`
- `provider`
- `cost_usd`
- `step_name`

### Task 4.2 时间窗口查询

- 最近 7 天聚合
- 最近 30 天聚合
- 按 intent 分布

### Task 4.3 日汇总表

- 生成 `daily_token_summaries`
- 每日写入昨日数据

### Task 4.4 报表输出层

- 返回结构化 JSON
- 生成可读摘要供 OpenClaw / 飞书复用

### Task 4.5 Phase 0-4 MVP 联调准备

- 明确最小闭环验收路径
- 列出联调环境要求
- 列出必须人工验证的节点

## 四、阶段产出

- 时间窗口查询接口
- 日报聚合表
- 日报定时任务
- 报表摘要模板
- Phase 0-4 MVP 联调清单

## 五、阶段通过标准

- [ ] 7 天查询可返回正确聚合
- [ ] 30 天查询可返回正确聚合
- [ ] 昨日日报可自动生成
- [ ] 已具备 Phase 0-4 整体 MVP 验证前置条件
