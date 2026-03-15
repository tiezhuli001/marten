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
