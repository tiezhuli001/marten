# Phase 4 Implementation Plan

> 更新时间：2026-03-16
> 阶段：Phase 4 Token Ledger / Daily Reporting
> 说明：本文件是编码前的实现计划，供回溯和多 agent 协作使用。

## 一、需求澄清

Phase 4 的核心不是再做一个依赖 skill 的 agent，而是补齐平台运营层的确定性能力：

1. token 原始记录要可追踪
2. 近 7 天 / 近 30 天统计要可查询
3. 昨日日报要可生成、可落库、可读取
4. 输出既要有结构化 JSON，也要有稳定的规则摘要
5. Phase 4 完成后，要能直接进入 Phase 0-4 整体 MVP 验证

这里的 token ledger 属于工程侧基础设施，不应依赖 LLM 或 skill 参与核心计算。

## 二、编码目标

本轮编码只实现最小可运行版：

1. 扩展 token usage 原始记录字段
2. 增加 `daily_token_summaries` 聚合表
3. 实现 `7d / 30d / yesterday` 三类查询能力
4. 提供结构化 API 返回
5. 提供规则化日报摘要
6. 落地可被 scheduler 调用的昨日日报任务入口
7. 产出 Phase 0-4 MVP 验证清单文档

## 三、实现拆解

### Step 1 Token Ledger Schema 扩展

在现有 SQLite 账本表基础上补齐最小字段：

- `model_name`
- `provider`
- `cost_usd`
- `step_name`

原则：

- 不引入 Alembic
- 保持当前轻量 schema 初始化与兼容升级风格
- 兼容已有 Phase 1-3 数据

### Step 2 日汇总表

新增 `daily_token_summaries` 表，至少包含：

- `summary_date`
- `request_count`
- `workflow_run_count`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `estimated_cost_usd`
- `top_intent`
- `top_step_name`
- `created_at`

原则：

- 一天只保留一条汇总记录
- 支持重复生成同一天摘要时幂等更新

### Step 3 Ledger Service 能力扩展

扩展 `app/ledger/service.py`：

- 写入扩展后的 token usage 记录
- 查询最近 7 天聚合
- 查询最近 30 天聚合
- 查询指定日期的日汇总
- 生成昨日汇总并写入 `daily_token_summaries`
- 产出 Top 消耗任务 / Top intent / Top step 的统计

这里的统计全部走数据库，不做内存缓存，不依赖 LLM。

### Step 4 API Schema 扩展

在 `app/models/schemas.py` 中新增最小报表模型：

- `TokenUsageBreakdown`
- `TokenWindowSummary`
- `DailyTokenSummary`
- `TokenReportResponse`

原则：

- 结构化数据和可读摘要同时返回
- 查询结果可直接供 OpenClaw / Channel 复用

### Step 5 报表查询接口

新增最小 API：

- `GET /reports/tokens?window=7d`
- `GET /reports/tokens?window=30d`
- `GET /reports/tokens/daily/{summary_date}`
- 可选：`POST /reports/tokens/daily/generate?date=YYYY-MM-DD`

说明：

- 第一版不支持任意窗口查询
- 第一版不做复杂筛选条件

### Step 6 规则化摘要生成

实现一个确定性的摘要渲染器：

- 输入：结构化 token 统计
- 输出：日报或窗口摘要文本

摘要内容至少包含：

- 时间窗口
- 请求数
- workflow 数
- 总 token
- 估算成本
- 主要消耗来源

原则：

- 不引入 skill
- 不依赖 LLM
- 输出模板稳定且可测试

### Step 7 日报任务入口

提供可被 scheduler 调用的任务函数，例如：

- `generate_daily_summary(summary_date)`
- `generate_yesterday_summary()`

说明：

- 本阶段先实现任务能力和调用入口
- “每日 10 点触发”作为调度目标写入文档与代码注释，不强行在本轮接完整调度系统

### Step 8 MVP 验证清单

新增一份 Phase 0-4 联调清单文档，至少覆盖：

- 环境前置条件
- Gateway 验证步骤
- Sleep Coding 验证步骤
- Code Review 验证步骤
- Token Ledger / Daily Report 验证步骤
- 必须人工确认的节点

## 四、推荐编码顺序

1. 先扩 ledger schema 与兼容升级
2. 再做 `daily_token_summaries`
3. 再扩 `TokenLedgerService` 查询和聚合
4. 再补 API schema
5. 再补 `/reports/tokens` 接口
6. 再做规则摘要渲染
7. 再做昨日日报生成入口
8. 最后补文档、测试和 MVP 验证清单

## 五、验收口径

- 可写入带 `model_name/provider/cost_usd/step_name` 的 token 使用记录
- `7d` 查询返回正确聚合
- `30d` 查询返回正确聚合
- 昨日日报可生成并落库
- API 同时返回结构化统计和规则摘要
- 已产出 Phase 0-4 MVP 验证清单
- 文档与实现一致

## 六、明确不做

本轮不做：

- PostgreSQL 迁移
- Alembic
- BI 看板
- 多租户
- 任意日期范围查询
- 自然语言智能分析
- 依赖 skill 的账本统计
- Phase 5 预开发

## 七、闭环判断

Phase 4 完成后，最小闭环应为：

```text
request finished
-> token usage records persisted
-> 7d / 30d queries available
-> yesterday summary generated and stored
-> API returns structured stats + readable summary
-> MVP validation checklist ready
```

如果这条链路打通，就说明 Phase 4 已经满足“为 Phase 0-4 整体 MVP 验证做准备”的阶段目标。
