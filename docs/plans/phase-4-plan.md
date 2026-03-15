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

## 二、范围

### 本阶段要做

- 时间窗口查询 SQL
- `daily_token_summaries` 表
- 日报任务
- 7/30 天查询接口
- 报表摘要输出

### 本阶段不做

- 复杂 BI 仪表盘
- 多租户账本隔离
- 精确到供应商账单级对账

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

## 四、阶段产出

- 时间窗口查询接口
- 日报聚合表
- 日报定时任务
- 报表摘要模板

## 五、阶段通过标准

- [ ] 7 天查询可返回正确聚合
- [ ] 30 天查询可返回正确聚合
- [ ] 昨日日报可自动生成
