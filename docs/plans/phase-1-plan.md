# Phase 1 Plan

> 阶段名称：平台骨架
> 目标：建立最小可运行工程骨架，为睡后编程 MVP 做准备
> 对应迭代计划：`docs/plans/iteration-plan.md`

## 一、阶段目标

本阶段只解决“平台能不能跑起来”的问题，不解决复杂业务问题。

要达成的能力：

1. FastAPI Gateway 可运行
2. LangGraph 主图骨架可运行
3. 最小意图路由可运行
4. LangSmith tracing 可用
5. Token Ledger 最小记录可入库
6. 状态可写回文档或数据库

本阶段结束后，应具备：

> 一个能接收请求、做最小路由、记录 trace 和 token、返回结果的骨架系统。

---

## 二、范围

### 本阶段要做

- 项目代码目录初始化
- FastAPI 骨架
- 配置管理
- LangGraph 主图骨架
- 最小 Intent Router
- LangSmith 接入
- Token Ledger 最小表结构与写入
- 状态写回

### 本阶段不做

- 睡后编程完整闭环
- GitHub Issue / PR 自动化
- 小说 / 中医 / 玄学 Agent
- 飞书正式业务消息流

---

## 三、建议目录结构

建议第一版代码结构如下：

```text
app/
├── api/
├── core/
├── graph/
├── ledger/
├── models/
├── services/
└── main.py

docs/
├── plans/
├── status/
├── architecture/
└── runbooks/
```

### 目录说明

- `api/`: FastAPI 路由
- `core/`: 配置、日志、基础设施
- `graph/`: LangGraph 工作流
- `ledger/`: token 账本逻辑
- `models/`: Pydantic 模型
- `services/`: GitHub / LangSmith / 其他外部服务封装

---

## 四、任务拆解

## Task 1.1 项目代码骨架初始化

### 目标

建立最小 Python 项目结构。

### 执行项

1. 创建 `app/` 目录结构
2. 创建 `app/main.py`
3. 创建基础 `README` 更新说明
4. 创建基础配置文件占位

### 验收标准

- [ ] 能启动一个空 FastAPI 应用

---

## Task 1.2 配置管理

### 目标

统一所有服务的配置入口。

### 建议配置项

- `APP_ENV`
- `APP_PORT`
- `LANGSMITH_API_KEY`
- `LANGSMITH_PROJECT`
- `OPENAI_API_KEY` 或模型供应商相关配置
- `DATABASE_URL`
- `GITHUB_TOKEN`

### 建议实现

- 使用 `.env`
- 使用 `pydantic-settings` 或等价方案

### 验收标准

- [ ] 配置可以通过环境变量加载

---

## Task 1.3 FastAPI Gateway 最小实现

### 目标

建立一个最小可调用的 Gateway。

### 第一阶段接口建议

1. `GET /health`
2. `POST /gateway/message`
3. `GET /status/current`

### `POST /gateway/message` 最小请求结构

```json
{
  "user_id": "string",
  "content": "string",
  "source": "manual"
}
```

### 最小响应结构

```json
{
  "request_id": "string",
  "intent": "general",
  "message": "string",
  "token_usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

### 验收标准

- [ ] `/health` 返回 200
- [ ] `/gateway/message` 可调用

---

## Task 1.4 LangGraph 主图骨架

### 目标

让 Gateway 请求进入 LangGraph。

### 第一版主图节点

1. `intent_classifier`
2. `router`
3. `general_handler`
4. `stats_query_handler`
5. `token_ledger`
6. `response_formatter`

### 第一版只支持的意图

- `general`
- `stats_query`
- `sleep_coding` 占位

### 说明

`sleep_coding` 在本阶段只需要：

- 路由占位
- 返回 “not implemented yet”

不要在本阶段开始做完整编码闭环。

### 验收标准

- [ ] 请求能进入 graph
- [ ] graph 可根据不同意图返回结果

---

## Task 1.5 最小 Intent Router

### 目标

先用简单可控方式完成意图识别。

### 第一版建议

规则优先，LLM 兜底暂缓。

### 建议规则

- 包含 “统计 / token / 消耗 / 最近7天 / 最近30天” -> `stats_query`
- 包含 “写代码 / 修 bug / issue / pr / review” -> `sleep_coding`
- 其他 -> `general`

### 原则

第一版不要追求高智能，先追求可控。

### 验收标准

- [ ] 最小规则路由可工作

---

## Task 1.6 LangSmith 接入

### 目标

把 trace 提前接进来。

### 执行项

1. 配置 LangSmith 项目
2. 在 Gateway 请求进入 graph 时打 trace
3. 给 request_id / run_id 建立关联

### 验收标准

- [ ] 可在 LangSmith 中看到请求链路

---

## Task 1.7 Token Ledger 最小实现

### 目标

建立后续账本系统的最小底座。

### 第一版最小表

1. `requests`
2. `workflow_runs`
3. `token_usage_records`

### 第一版最小能力

- 每次请求生成 `request_id`
- 每次 workflow 生成 `run_id`
- 每次模型调用记录 token
- 每次请求结束后聚合 token

### 注意

本阶段不做：

- 每日汇总
- 周/月报

这些放到 Phase 4。

### 验收标准

- [ ] 请求结束后能返回 token_usage 字段

---

## Task 1.8 状态写回机制

### 目标

让 OpenClaw 后续可以读到当前状态。

### 第一版建议

最简单方案：

- 每次重要阶段更新后，更新 `docs/status/current-status.md`

后续再逐步增加数据库状态源。

### 必须写回的内容

- 当前阶段
- 当前在做什么
- 下一步做什么
- 当前阻塞

### 验收标准

- [ ] 本阶段结束时 `current-status.md` 已更新

---

## 五、推荐执行顺序

1. Task 1.1 项目代码骨架初始化
2. Task 1.2 配置管理
3. Task 1.3 FastAPI Gateway 最小实现
4. Task 1.4 LangGraph 主图骨架
5. Task 1.5 最小 Intent Router
6. Task 1.6 LangSmith 接入
7. Task 1.7 Token Ledger 最小实现
8. Task 1.8 状态写回机制

---

## 六、阶段产出

完成本阶段后，应至少具备：

1. 可启动的 FastAPI 服务
2. 可运行的 LangGraph 主图骨架
3. 最小意图识别
4. 可查看的 LangSmith trace
5. 最小 token 记录能力
6. OpenClaw 可读取的当前状态文档

---

## 七、阶段验收清单

- [ ] FastAPI Gateway 可运行
- [ ] LangGraph 主图骨架可运行
- [ ] 最小意图识别可用
- [ ] LangSmith trace 可查看
- [ ] token_usage 可在响应中返回
- [ ] `current-status.md` 已更新

---

## 八、完成后立即进入

完成 Phase 1 后，下一阶段就是：

> 睡后编程 MVP（Phase 2）

届时再写：

- GitHub Issue 处理
- 代码工作区策略
- PR 创建
- Code Review
- 人工确认节点
