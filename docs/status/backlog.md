# Backlog

> 更新时间：2026-03-15

## P0

- [x] 生成 `docs/plans/phase-0-plan.md`
- [x] 生成 `docs/plans/phase-1-plan.md`
- [ ] 配置 Linux 服务器 conda 环境
- [ ] 安装并验证 OpenCode
- [ ] 安装并验证 OpenClaw
- [ ] 配置 GitHub MCP
- [ ] 配置飞书 Channel
- [x] 初始化 FastAPI 骨架
- [x] 初始化 LangGraph 主图骨架
- [x] 初始化 LangSmith tracing
- [x] 设计最小 Token Ledger 表结构

## P1

- [ ] 睡后编程 MVP：GitHub Issue -> PR 闭环
- [ ] 睡后编程真实飞书 webhook 联调
- [ ] 睡后编程真实 git worktree / push / PR 联调
- [ ] 睡后编程真实代码修改器接入 worktree
- [ ] Code Review Agent
- [ ] Token 日报任务
- [ ] 7 天 / 30 天 token 查询
- [ ] Phase 1 验收评审
- [ ] GitHub Issue / PR 状态模型落库
- [ ] Sleep Coding task 状态表设计

## P2

- [ ] 小说提取 Agent
- [ ] RAG 入库链路
- [ ] 中医养生 Agent
- [ ] 玄学 Agent

## 当前文档任务

- [x] 补齐 `docs/plans/phase-2-plan.md`
- [x] 补齐 `docs/plans/phase-3-plan.md`
- [x] 补齐 `docs/plans/phase-4-plan.md`
- [x] 补齐 `docs/plans/phase-5-plan.md`
- [x] 补齐 `docs/plans/phase-6-plan.md`
- [x] 补齐 `docs/plans/phase-7-plan.md`
- [x] 补齐 `docs/architecture/phase-3-code-review.md`
- [x] 补齐 `docs/architecture/phase-4-token-ledger-ops.md`
- [x] 补齐 `docs/architecture/phase-5-novel-ingest.md`
- [x] 补齐 `docs/architecture/phase-6-tcm-agent.md`
- [x] 补齐 `docs/architecture/phase-7-metaphysics-agent.md`
- [ ] 基于选定 Phase 生成下一轮实现计划

## 待决策

- [ ] Gateway 是否完全自建，还是在第一版借助 OpenClaw 做更多入口职责
- [ ] 向量库最终是否确定为 Qdrant
- [ ] 调度方式是否固定为 APScheduler，还是切到独立 worker

## 风险项

- [ ] OpenClaw 与飞书接入方式需要尽早验证
- [ ] GitHub MCP 的能力边界要尽早验证
- [ ] LangSmith 是否满足当前监控需求需要尽早验证
