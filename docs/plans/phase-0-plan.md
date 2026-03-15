# Phase 0 Plan

> 阶段名称：前置准备与环境冻结
> 目标：把仓库、环境、文档、开发方式和最小工具链固定下来
> 对应迭代计划：`docs/plans/iteration-plan.md`

## 一、阶段目标

本阶段不做正式业务功能，只完成后续开发必须依赖的前置工作：

1. 仓库初始化
2. 文档骨架确认
3. Linux 服务器 Python 环境准备
4. OpenCode 安装与验证
5. OpenClaw 安装与验证
6. GitHub MCP 配置与验证
7. 飞书 Channel 预留接入方式

本阶段的成功标准不是“Agent 已可工作”，而是：

> 后续 Phase 1 的工程骨架可以在不返工环境的前提下直接开始。

---

## 二、范围

### 本阶段要做

- 项目目录初始化
- docs 体系初始化
- 服务器 conda 环境固定
- 基础依赖安装
- GitHub 仓库读写验证
- GitHub MCP 验证
- OpenCode / OpenClaw 可用性验证

### 本阶段不做

- 正式 Gateway 业务逻辑
- LangGraph 主图实现
- 睡后编程业务闭环
- Token Ledger 正式入库逻辑
- 小说 / 中医 / 玄学 Agent

---

## 三、任务拆解

## Task 0.1 仓库基线确认

### 目标

确认本仓库作为主项目仓库，目录结构和分支策略可用。

### 执行项

1. 确认远程仓库地址
2. 确认默认分支
3. 确认当前仓库工作区干净或可控
4. 补充 README 中的项目定位说明

### 交付物

- 可正常 `pull/push`
- README 至少包含一句项目定位

### 验收标准

- [ ] 仓库远程地址可用
- [ ] 可以从服务器访问仓库

---

## Task 0.2 文档体系初始化

### 目标

把 OpenClaw 后续可读取的文档体系先固定下来。

### 已有基础

当前仓库已初始化：

- `docs/plans/iteration-plan.md`
- `docs/status/current-status.md`
- `docs/status/backlog.md`
- `docs/architecture/phase-1-architecture.md`
- `docs/runbooks/server-setup.md`

### 本任务需要补齐

1. 确认这些文档路径不再变动
2. 在 `current-status.md` 中写清本周状态
3. 在 `backlog.md` 中补充 Phase 0 / 1 待办
4. 约定后续所有阶段更新都先写 docs 再写代码

### 交付物

- 文档目录冻结
- 当前状态可读
- backlog 可读

### 验收标准

- [ ] OpenClaw 后续可以直接读取 `docs/status/current-status.md`
- [ ] OpenClaw 后续可以直接读取 `docs/status/backlog.md`

---

## Task 0.3 服务器 Python 环境固定

### 目标

把 Linux 服务器上的 Python 运行环境固定下来。

### 执行项

1. 创建 conda 环境：

```bash
conda create -n youmeng-gateway python=3.11 -y
conda activate youmeng-gateway
```

2. 确认 Python 版本
3. 确认 pip 可用
4. 记录环境名到 `docs/runbooks/server-setup.md`

### 当前建议依赖

第一批只装必要依赖：

```bash
pip install langgraph langchain langchain-core langsmith
pip install fastapi uvicorn pydantic
pip install apscheduler
pip install psycopg[binary]
```

### 交付物

- 固定 conda 环境：`youmeng-gateway`
- 基础 Python 依赖可用

### 验收标准

- [ ] `python --version` 为 3.11.x
- [ ] 可以成功 import `langgraph`, `fastapi`, `langsmith`

---

## Task 0.4 Git 与 GitHub 访问验证

### 目标

确保服务器可以正常进行仓库操作。

### 执行项

1. 配置 SSH key
2. 验证 `git clone / pull / push`
3. 配置 git 用户名与邮箱

### 建议命令

```bash
ssh -T git@github.com
git remote -v
git status
```

### 交付物

- 服务器具备 GitHub 仓库访问能力

### 验收标准

- [ ] SSH 访问 GitHub 正常
- [ ] 可以 push 到 `youmeng-gateway`

---

## Task 0.5 GitHub MCP 配置

### 目标

让服务器上的 AI 工具具备 GitHub 仓库操作能力。

### 执行项

1. 准备 GitHub Token / OAuth
2. 配置 GitHub MCP
3. 验证 MCP 可以读取仓库信息、Issue、PR

### 注意

- MCP 是辅助能力
- 正式主链路后续仍以 `GitHub API + git` 为主

### 交付物

- GitHub MCP 可用

### 验收标准

- [ ] MCP 可读取当前仓库
- [ ] MCP 可读取 Issues / PRs

---

## Task 0.6 OpenCode 安装与验证

### 目标

把 OpenCode 作为服务器上的交互式编码助手准备好。

### 执行项

1. 安装 OpenCode
2. 验证版本
3. 在仓库目录中启动一次最小会话
4. 验证它能读取当前代码仓库和 docs

### 验收标准

- [ ] `opencode --version` 正常
- [ ] OpenCode 可在 `youmeng-gateway` 仓库中工作

---

## Task 0.7 OpenClaw 安装与验证

### 目标

把 OpenClaw 作为常驻 Gateway / Channel Layer 的候选准备好。

### 执行项

1. 安装 OpenClaw
2. 验证版本
3. 确认其可在服务器运行
4. 确认后续可挂接飞书

### 验收标准

- [ ] OpenClaw 安装完成
- [ ] 可以本地启动

---

## Task 0.8 飞书接入预验证

### 目标

先确认飞书作为沟通入口的接入路径可行。

### 执行项

1. 明确飞书机器人类型
2. 确认服务器接入方式：
   - Webhook
   - WebSocket / Event Subscription
3. 记录所需配置项：
   - App ID
   - App Secret
   - Bot 配置

### 本阶段要求

本阶段只要完成“接入方案确认”，不要求业务跑通。

### 验收标准

- [ ] 明确飞书接入方式
- [ ] 明确后续配置项

---

## 四、推荐执行顺序

1. Task 0.1 仓库基线确认
2. Task 0.2 文档体系初始化
3. Task 0.3 服务器 Python 环境固定
4. Task 0.4 Git 与 GitHub 访问验证
5. Task 0.5 GitHub MCP 配置
6. Task 0.6 OpenCode 安装与验证
7. Task 0.7 OpenClaw 安装与验证
8. Task 0.8 飞书接入预验证

---

## 五、阶段产出

完成本阶段后，仓库中至少应具备：

1. `docs/` 基础文档体系
2. 稳定的服务器 Python 环境
3. GitHub 访问能力
4. GitHub MCP 能力
5. OpenCode 可用
6. OpenClaw 可用
7. 飞书接入方案明确

---

## 六、阶段验收清单

- [ ] GitHub 仓库访问正常
- [ ] `docs/` 目录结构冻结
- [ ] conda 环境 `youmeng-gateway` 可用
- [ ] 基础 Python 依赖安装成功
- [ ] GitHub MCP 可访问仓库
- [ ] OpenCode 可用
- [ ] OpenClaw 可用
- [ ] 飞书接入方案明确

---

## 七、完成后立即进入

完成 Phase 0 后，立即进入：

> `docs/plans/phase-1-plan.md`

也就是：

- FastAPI Gateway 骨架
- LangGraph 主图骨架
- LangSmith tracing
- Token Ledger 最小表
- 状态写回机制
