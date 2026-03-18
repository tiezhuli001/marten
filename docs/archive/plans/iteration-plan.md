# 多 Agent 个人平台正式迭代计划

> 版本：v1.0
> 日期：2026-03-15
> 当前确认路线：`LangGraph + LangSmith` 先行，后续保留向 `Go / Eino` 工程化演进空间
> 当前工作环境：Linux 服务器 + conda Python 环境
> 当前协作方式：Mac 通过 SSH 远程监督；服务器作为主开发/运行环境；飞书作为沟通入口
> 代码仓库：[youmeng-gateway](https://github.com/tiezhuli001/youmeng-gateway)

## 计划结论

当前最合理的总体策略不是一次性做完整平台，而是：

> 先做一个工程骨架，再做一个最复杂的闭环 Agent，最后再扩展到多 Agent 平台。

现阶段的首要目标是：

1. 建立 GitHub 私有主项目
2. 建立服务器开发与运行环境
3. 明确 OpenClaw / OpenCode / 自研平台的边界
4. 配置 GitHub MCP 方便仓库操作
5. 先完成“睡后编程 + Code Review + Token 账本 + LangSmith 监控”的最小闭环
6. 再扩小说提取、中医养生、玄学 Agent

## 总体目标

目标系统不是普通聊天 Agent，而是一个可长期运行的个人多 Agent 平台，具备：

1. 常驻 Gateway
2. 多 Agent 能力
3. 工程化基础设施
4. 长期演进能力

## 当前环境

| 项目 | 当前情况 |
|------|----------|
| 本机 | Mac，公司电脑 |
| 代码仓库 | GitHub 私有仓库 |
| 主运行环境 | Linux 服务器 |
| Python 管理 | conda |
| 沟通入口 | 飞书 |
| 预期运行位置 | 服务器，而不是 Mac |

## 开发与协作方式定稿

分层关系：

- `OpenClaw`: 常驻 Gateway / Channel Layer / 进度反馈入口
- `OpenCode`: 服务器上的交互式编码助手
- `自研平台`: 正式业务逻辑、LangGraph 工作流、Token Ledger、Scheduler、RAG、GitHub 自动化

当前阶段的协作方式：

> OpenClaw 负责沟通与进度反馈，OpenCode 通过 SSH 由人直接使用来编码。

## 文档与进度管理

OpenClaw 的进度来源按优先级排序：

1. Git 仓库中的 Markdown 文档
2. GitHub Issue / PR 状态
3. 任务状态表 / 数据库
4. Worker 日志与结果文件

最关键的文档：

- `docs/status/current-status.md`
- `docs/status/backlog.md`

## 技术路线定稿

| 类别 | 选型 |
|------|------|
| 编排框架 | LangGraph |
| 观测 | LangSmith |
| RAG 组件 | LangChain |
| Gateway | FastAPI |
| 数据库 | 目标 PostgreSQL，Phase 1/2 先用 SQLite |
| 向量库 | 先固定一个，优先 Qdrant |
| 调度 | APScheduler（MVP） |
| 代码托管集成 | GitHub API + git + GitHub MCP |
| 交互式编码 | OpenCode |
| Channel / Session | OpenClaw + 飞书 |

数据库策略说明：

- 长期正式目标是 PostgreSQL
- 但为了降低前两阶段的实现和部署复杂度，`Phase 1 / Phase 2` 先以 SQLite 跑通单机闭环
- 到 `Phase 3 / Phase 4` 再评估迁移到 PostgreSQL，并补 Alembic 或等价迁移机制

## 正式迭代阶段

### Phase 0：前置准备与环境冻结

目标：在编码前，把仓库、环境、文档、进度来源定下来。

任务：

1. 初始化 GitHub 私有主项目
2. 建立服务器 conda 环境
3. 安装 OpenCode
4. 安装 OpenClaw
5. 配置 GitHub MCP
6. 配置飞书 Channel
7. 初始化 `docs/` 目录
8. 建立最小 `current-status.md` 与 `backlog.md`

### Phase 1：平台骨架

目标：先把工程底座搭起来，不急于上复杂业务。

核心模块：

1. Gateway（FastAPI）
2. Intent Router（只支持最小意图）
3. LangGraph 主图骨架
4. Token Ledger 基础表
5. LangSmith Tracing
6. 状态写回机制

说明：

- `Phase 1` 只要求最小可运行和最小持久化
- 不要求日报、周报、月报
- 不要求 PostgreSQL 正式落地，SQLite 可作为阶段性实现

### Phase 2：睡后编程 MVP

工作流：

```text
用户提出开发需求
-> 创建 GitHub Issue
-> 读取 Issue
-> 生成计划
-> 修改代码
-> 生成 PR
-> 触发 Code Review
-> 人工确认
-> Merge 或退回
-> 汇总 token 消耗
```

### Phase 3：Code Review 能力

目标：扩展睡后编程闭环，形成更完整的软件工程回路。

说明：

- review 内容优先复用现有 `code-review skill`
- 平台负责回写、归档和流转，不自研复杂 review 引擎

### Phase 4：Token 账本与日报系统

目标：把平台运营能力做起来。

说明：

- `Phase 4` 完成后，先做 `Phase 0 - Phase 4` 的整体 MVP 验证
- 验证通过后，再继续 Phase 5 及之后的 Agent 扩展

### Phase 5：小说提取 Agent

目标：验证第二类工作流：搜索 + 人工确认 + 抽取 + RAG 入库。

### Phase 6：中医养生 Agent

目标：验证知识型 Agent：RAG + Skill 模板化输出。

### Phase 7：玄学 Agent

目标：在平台和知识型 Agent 稳定后，再做规则更复杂的玄学 Agent。

## 时序与预计时间

| 阶段 | 目标 | 预计时间 |
|------|------|----------|
| Phase 0 | 环境与文档前置 | 1-2 周 |
| Phase 1 | 平台骨架 | 1-2 周 |
| Phase 2 | 睡后编程 MVP | 2-3 周 |
| Phase 3 | Code Review | 1-2 周 |
| Phase 4 | Token 账本与日报 | 1 周 |
| Phase 5 | 小说提取 Agent | 2-3 周 |
| Phase 6 | 中医养生 Agent | 2-3 周 |
| Phase 7 | 玄学 Agent | 2-3 周 |

总周期保守估计：`12-18 周`

## 下一步动作

1. 确认 GitHub 私有仓库 `youmeng-gateway` 为主项目
2. 进入第一期执行 Plan（Phase 0 + Phase 1）
