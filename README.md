# youmeng-gateway

个人多 Agent 应用的 Gateway / Control Plane 仓库。

当前目标不是再造一个后端服务集合，而是收敛成一个：

- `Gateway + Control Plane`
- `Main Agent / Ralph / Code Review Agent`
- `Shared Runtime (LLM / Skill / MCP)`
- `JSON-first, defaults-first`

的多 Agent 应用。

## 当前能力

当前仓库已经具备以下 MVP 主链路：

1. Feishu 入站 webhook 接收用户消息
2. Main Agent 把请求转成 GitHub issue
3. Ralph Worker 发现 issue 并接管
4. Ralph 生成 plan / coding draft / PR
5. Code Review Agent 生成 structured findings，并进入 repair loop
6. 最终通过 Feishu channel webhook 发出阶段通知和完成通知
7. 统一记录 task / event / session / token usage

## Quick Start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .

cp .env.example .env
cp agents.json.example agents.json
cp models.json.example models.json
cp platform.json.example platform.json
cp mcp.json.example mcp.json

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

推荐使用 `Python 3.11` 或 `3.12`。

## 配置方式

当前推荐配置边界如下：

### `.env`

只放：

- secrets
- 基础运行参数
- JSON 配置入口

### `agents.json`

定义：

- agent workspace
- skills
- mcp servers
- model profile

### `models.json`

定义：

- provider profile
- model profile
- 不同 agent 默认用什么模型

### `platform.json`

定义：

- sleep-coding worker 默认值
- git/worktree 默认行为
- review loop 默认值
- 平台级 repo / channel 默认值

### `mcp.json`

定义：

- MCP server 连接方式
- command / args / env / cwd / adapter

`mcp.json` 是可插拔的：

- 不配置也不影响系统启动
- 配置了就启用 MCP

## 最小启动路径

1. 在 `.env` 填：
   - `OPENAI_API_KEY` 或 `MINIMAX_API_KEY`
   - `GITHUB_TOKEN`
   - `CHANNEL_WEBHOOK_URL`
   - `FEISHU_VERIFICATION_TOKEN`
2. 在 `mcp.json` 配 GitHub MCP
3. 在 `agents.json / models.json / platform.json` 保留默认或按需调整
4. 启动服务
5. 调用：
   - `GET /health`
   - `GET /diagnostics/integrations`
   - `POST /main-agent/intake`

## 关键接口

- `GET /health`
- `GET /status/current`
- `GET /diagnostics/integrations`
- `POST /gateway/message`
- `POST /webhooks/feishu/events`
- `POST /main-agent/intake`
- `POST /workers/sleep-coding/poll`
- `GET /workers/sleep-coding/claims`
- `POST /tasks/sleep-coding`
- `POST /tasks/sleep-coding/{task_id}/actions`
- `POST /tasks/sleep-coding/{task_id}/review`
- `GET /control/tasks/{task_id}`
- `GET /control/tasks/{task_id}/events`

## 文档入口

优先阅读：

1. [docs/status/current-status.md](/Users/litiezhu/workspace/github/youmeng-gateway/docs/status/current-status.md)
2. [docs/requirements/mvp-gap-analysis.md](/Users/litiezhu/workspace/github/youmeng-gateway/docs/requirements/mvp-gap-analysis.md)
3. [docs/plans/mvp-execution-plan.md](/Users/litiezhu/workspace/github/youmeng-gateway/docs/plans/mvp-execution-plan.md)
4. [docs/architecture/multi-agent-refactor-plan.md](/Users/litiezhu/workspace/github/youmeng-gateway/docs/architecture/multi-agent-refactor-plan.md)
5. [docs/architecture/multi-agent-platform-roadmap.md](/Users/litiezhu/workspace/github/youmeng-gateway/docs/architecture/multi-agent-platform-roadmap.md)
6. [docs/architecture/config-layer-refactor-and-migration.md](/Users/litiezhu/workspace/github/youmeng-gateway/docs/architecture/config-layer-refactor-and-migration.md)

用户配置与联调手册见：

- [youmeng-gateway-mvp-配置与联调操作手册.md](/Users/litiezhu/docs/ytsd/工作学习/AI学习/个人需求/youmeng-gateway-mvp-配置与联调操作手册.md)

<!-- ralph-e2e-issue-29 -->
