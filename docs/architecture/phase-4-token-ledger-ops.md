# Phase 4 Design Prep: Token Ledger Ops

> 更新时间：2026-03-15

## 目标

把 token 记录从开发期调试信息升级为平台运营能力。

## 设计重点

1. 原始 token 记录实时入库
2. 周期查询基于数据库，不依赖 LLM 记忆
3. 日报生成与自然语言摘要分离

## 最小数据流

```text
request finished
-> write token_usage_records
-> aggregate by day
-> expose query endpoints
-> daily scheduler builds summary
```

## 关键输出

- 昨日日报
- 最近 7 天统计
- 最近 30 天统计
- Top 消耗任务

## Phase 4 完成后的动作

Phase 4 不是立即继续扩展新 Agent 的起点，而是第一阶段 MVP 联调前的最后一块运营能力补齐。

Phase 4 完成后，应先验证：

1. Gateway 能接收请求
2. Sleep Coding 能创建 task / PR
3. Code Review 能生成结果并回写
4. Token Ledger 能查询和生成日报

只有这条最小闭环稳定后，再进入 Phase 5。
