# Phase 1 Acceptance

> 阶段名称：平台骨架
> 对应计划：[phase-1-plan.md](/Users/litiezhu/workspace/github/youmeng-gateway/docs/plans/phase-1-plan.md)
> 更新时间：2026-03-15

## 目标

本阶段验收的重点不是业务闭环，而是确认平台骨架已经具备后续扩展基础。

Phase 1 完成后，系统应达到：

1. FastAPI Gateway 可以稳定启动
2. LangGraph 主图可以接收请求并完成最小路由
3. 最小规则意图识别可用
4. Token Ledger 具备最小持久化能力
5. LangSmith 已有接入位点
6. `docs/status` 可以作为进度事实来源

## 整体预期效果

如果 Phase 1 验收通过，应该具备以下对外表现：

1. 开发者可以通过 HTTP 调用网关接口
2. 请求进入后会生成 `request_id` 和 `run_id`
3. 请求会进入 LangGraph 主图
4. 系统可以返回 `general / stats_query / sleep_coding` 三类最小结果
5. 响应中固定包含 `token_usage`
6. token 账本会把最小请求数据写入 SQLite
7. 状态文档能反映当前阶段、下一步和阻塞项

## 自动化测试点

### 1. 配置解析

需要明确测试：

- `APP_DATA_DIR` 是否解析为项目根目录下的相对路径
- `DATABASE_URL=sqlite:///...` 是否解析为正确的 SQLite 文件路径
- 绝对路径配置是否被保留

预期效果：

- 默认数据目录是项目内 `data/`
- 默认数据库路径是项目内 `data/youmeng_gateway.db`
- 自定义绝对路径不被错误改写

对应测试：

- [test_config.py](/Users/litiezhu/workspace/github/youmeng-gateway/tests/test_config.py)

### 2. 意图路由

需要明确测试：

- token 统计类文本是否命中 `stats_query`
- 编码类文本是否命中 `sleep_coding`
- 普通文本是否命中 `general`

预期效果：

- Phase 1 的规则路由可控、可预测

对应测试：

- [test_router.py](/Users/litiezhu/workspace/github/youmeng-gateway/tests/test_router.py)

### 3. API 最小入口

需要明确测试：

- `/health` 是否可返回 `200`
- `/gateway/message` 是否能返回合法响应结构

预期效果：

- API 可作为后续 OpenClaw / worker / 调度器的统一入口

对应测试：

- [test_api.py](/Users/litiezhu/workspace/github/youmeng-gateway/tests/test_api.py)

### 4. Token Ledger 最小持久化

需要明确测试：

- 请求是否能写入最小 SQLite 账本
- 统计查询是否能给出当前聚合结果

预期效果：

- 后续日报和近 7/30 天查询已经有底层数据模型可依赖

对应测试：

- [test_token_ledger.py](/Users/litiezhu/workspace/github/youmeng-gateway/tests/test_token_ledger.py)

## 手动验收点

### 1. 服务启动

执行：

```bash
uvicorn app.main:app --reload
```

预期：

- 服务可以启动
- 无启动时致命异常

### 2. 健康检查

执行：

```bash
curl http://127.0.0.1:8000/health
```

预期：

```json
{"status":"ok"}
```

### 3. 网关请求

执行：

```bash
curl -X POST http://127.0.0.1:8000/gateway/message \
  -H "Content-Type: application/json" \
  -d '{"user_id":"user-1","content":"帮我统计最近7天 token 消耗","source":"manual"}'
```

预期：

- 返回 `request_id`
- `intent` 为 `stats_query`
- 返回 `token_usage`

### 4. 状态文档读取

执行：

```bash
curl http://127.0.0.1:8000/status/current
```

预期：

- 返回 `docs/status/current-status.md` 的正文

## 本阶段通过标准

- 自动化测试全部通过
- 手动启动和接口调用通过
- `docs/status/current-status.md` 已更新
- 代码结构与计划一致，没有提前进入 Phase 2 业务实现

## 当前已完成情况

截至 2026-03-15，本阶段已完成：

- FastAPI 最小入口
- LangGraph 主图骨架
- 最小路由规则
- SQLite Token Ledger 最小持久化
- LangSmith 占位接入
- 配置模板与运行说明

## 尚未纳入 Phase 1 验收范围

- GitHub Issue -> PR 自动化
- Code Review Agent
- 日报定时任务
- 近 7 天 / 30 天真实时间窗口统计
- 飞书正式消息流
