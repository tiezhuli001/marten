# Phase 1 Architecture

> 范围：Phase 0 + Phase 1

## 目标

先建立平台最小骨架，不急于上完整业务能力。

## 组件

```text
Feishu
-> OpenClaw
-> Gateway (FastAPI)
-> LangGraph Main Graph
   -> Intent Router
   -> General Handler
   -> Sleep Coding Placeholder
   -> Stats Query
-> Token Ledger
-> LangSmith
-> PostgreSQL
```

## 第一阶段只支持的意图

- `sleep_coding`
- `stats_query`
- `general`

## 第一阶段最小能力

1. 接收请求
2. 生成 request_id
3. 进入 LangGraph
4. 记录 token
5. 返回结果
6. 写回状态

## 最小数据表

### requests

- id
- user_id
- intent
- status
- created_at
- finished_at

### workflow_runs

- id
- request_id
- workflow_name
- status
- current_step
- checkpoint_data
- created_at
- updated_at

### token_usage_records

- id
- request_id
- agent_name
- model_name
- prompt_tokens
- completion_tokens
- total_tokens
- cost
- created_at

### daily_token_stats

- date
- total_prompt_tokens
- total_completion_tokens
- total_tokens
- total_cost
- generated_at

## 关键原则

1. 所有请求必须有 request_id
2. 所有 workflow 必须有 run_id
3. 所有模型调用必须可记录 token
4. 所有状态必须可写回文档或数据库
5. 先做稳定骨架，再做复杂自动编码
