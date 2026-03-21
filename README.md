# Marten

`Marten` 是一个面向个人自动化研发流程的 agent control plane。

它把 `Feishu / GitHub / GitLab / MCP / 本地 worktree` 收口到一条可执行链路里，让 `Main Agent -> Ralph -> Review Agent` 能围绕真实 issue、真实仓库和真实 review loop 工作，而不是只做 prompt demo。

## Why This Repo

这个仓库解决的是一个很具体的问题：把“需求接收、任务领取、代码修改、自动 review、修复回路、最终通知”变成一条稳定的 agent 工作流。

当前主链路是：

`Feishu inbound -> gateway -> issue -> claim -> coding -> review -> final delivery`

设计原则：

- `MCP` 负责平台操作和外部系统桥接
- `LLM + skill` 负责规划、编码和审查的认知能力
- 本地 `worktree / checkout` 负责真实代码上下文、命令执行和验证
- JSON-first，默认值优先，减少脆弱编排

## Highlights

- Main Agent 可把用户请求转成 GitHub issue
- Ralph Worker 可轮询 issue、接管任务、在本地 worktree 中执行编码
- Review Agent 支持 `local / github / gitlab` 三种 source，并优先落本地后再 review
- 多轮 review loop 已改为 local-first，中间轮次通过渠道通知，最终结果再统一写回平台
- 统一记录 task、event、session、token usage，便于追踪和复盘

## Architecture

仓库当前收口为四层：

- `channel`: Feishu webhook 与通知输出
- `control plane`: task lifecycle、worker poll、follow-up、review loop
- `runtime`: LLM、skill、MCP、token accounting
- `agents`: Main Agent、Ralph、Code Review Agent

Ralph 和 Review Agent 的目标不是“远程读一点上下文就生成文本”，而是在真实仓库副本上工作：

- Ralph 在本地 worktree 中执行 coding command
- Review 先 materialize 远程 source，再基于本地代码和 diff 做审查
- GitHub / GitLab 只承担 issue、PR、comment、status 的读写桥接

## Workflow

1. 用户从 Feishu 或 API 提交需求
2. Main Agent 生成或接管 GitHub issue
3. Ralph Worker 轮询并 claim issue
4. Ralph 在本地 worktree 中规划、编码、验证、提交 PR
5. Review Agent 在本地代码上下文上执行 review
6. 若有阻塞问题，Ralph 延时后自动修复，最多 3 轮
7. 最终结果写回 GitHub / GitLab，并发送 Feishu 通知

## Current Scope

如果你只想快速理解当前仓库，不需要先看所有模块。

当前已经稳定收口的是一条单任务主链路：

- `Feishu / API -> Main Agent -> GitHub issue`
- `worker poll -> Ralph coding -> local validation -> PR`
- `Review Agent -> local-first review -> repair loop`
- `Feishu final delivery -> token usage summary`

当前这条链路已经在真实仓库上完成过多次 live 验证。

详细 issue / PR / review 编号只保留在内部状态文档，避免公开入口被历史样本绑死。

当前还没有展开的方向：

- 多仓库并发调度
- 多 reviewer 聚合
- 长期记忆和上下文压缩平台化

判断仓库目标是否偏移时，优先看这条主链路有没有被稀释成“功能拼盘”。如果某个改动不强化这条链路，基本就不该优先。

## Getting Started

### Requirements

- Python `3.11` 或 `3.12`
- Git
- 可用的 LLM provider 凭据
- 可选的 GitHub / GitLab / Feishu / MCP 配置

### Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

### Configure

```bash
cp .env.example .env
cp mcp.json.example mcp.json
cp models.json.example models.json
cp platform.json.example platform.json
```

配置职责建议如下：

- `mcp.json`: MCP server 的 command、args、env、cwd、adapter；JSON-first，可直接在这里放 token
- `models.json`: provider 凭据、api base、default model、profile 绑定；JSON-first，可配置多个 provider
- `platform.json`: repo 和少量运行行为覆盖；大部分 worker/review/execution 默认值内建在代码里
- `agents.json`: agent workspace、skills、MCP servers、model profile、prompt spec
- `.env`: 框架运行参数和可选 override；不是主 secrets 存储层

默认情况下，`agents.json` 可以不存在，系统会使用内建 agent spec。`mcp.json`、`models.json`、`platform.json` 才是主要配置入口；`.env` 更适合作为部署环境 override，而不是唯一的 key 来源。

最小可理解配置：

- `mcp.json`：告诉 Marten 怎么连 MCP server，并可直接放 server token
- `models.json`：告诉 Marten 用哪个 provider/model，以及 provider 的 key/base
- `platform.json`：告诉 Marten 默认 repo、worker、review、git 行为
- `.env`：只在你需要 runtime override 时再补

`models.json` 也支持直接把默认 profile 指到 MiniMax：

```json
{
  "profiles": {
    "default": {
      "model": "minimax/MiniMax-M2.5"
    }
  },
  "providers": {
    "minimax": {
      "protocol": "openai",
      "api_key": "your-api-key",
      "api_base": "https://api.minimax.io/v1",
      "default_model": "MiniMax-M2.5",
      "pricing_provider": "minimax"
    }
  }
}
```

如果你有自己的 OpenAI-compatible gateway，也可以直接定义一个自定义 provider id。例如把一个 gateway 暴露成 `cpcpa`：

```json
{
  "profiles": {
    "default": {
      "model": "cpcpa/gpt-5.4-mini"
    }
  },
  "providers": {
    "cpcpa": {
      "protocol": "openai",
      "api_key": "your-api-key",
      "api_base": "https://your-gateway.example.com/v1",
      "default_model": "gpt-5.4-mini",
      "pricing_provider": "openai"
    }
  }
}
```

`profile.model` 可以直接写成 `provider/model`，这样默认 profile 和 provider 绑定关系会更清晰。

### Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

启动后优先检查：

- `GET /health`
- `GET /diagnostics/integrations`
- `POST /main-agent/intake`
- `POST /workers/sleep-coding/poll`

## Local-First Execution

当前默认策略不是“把大段代码经由 MCP 喂给模型”，而是：

- coding / review 先把代码放到本地 worktree 或 checkout
- agent 再在本地目录中读文件、运行命令、生成修改
- 只有平台写回才走 MCP / API bridge

默认行为：

- Ralph 默认使用内建 LLM + agent runtime 生成 coding draft
- `sleep_coding.execution.command` 只是可选覆盖，用于把 coding 委托给外部本地执行器
- review 默认每轮本地执行，只在最终结果时统一写回远程平台
- review 默认在 `30s` 后触发 follow-up repair loop

常用覆盖项：

- `mcp.json -> servers.github.env.GITHUB_PERSONAL_ACCESS_TOKEN`
- `models.json -> providers.<provider>.api_key`
- `models.json -> providers.<provider>.api_base`
- `platform.json -> github.repository`
- `models.json -> profiles.default`

只有在你需要偏离默认行为时，再考虑 `agents.json` 或 `platform.json` 中的高级覆盖项；默认情况下不需要先理解这些细节。

一个真实可运行的最小配置组合通常是：

- `mcp.json`：至少一个 GitHub MCP server，带可用 token
- `models.json`：至少一个可用 provider，带可用 key/base
- `platform.json`：至少 `github.repository`
- `.env`：只放 webhook、framework runtime 或你明确想通过环境注入的覆盖项

如果你要跑真实全链路测试，而不是 mock e2e，还需要在 `platform.json` 显式打开：

```json
{
  "live_test": {
    "enabled": true,
    "timeout_seconds": 900,
    "poll_interval_seconds": 5
  }
}
```

然后执行：

```bash
python -m unittest tests.test_live_chain -v
```

这条 live test 不会使用 fake GitHub、fake review、fake channel。它会直接使用当前工作区里的真实 `models.json`、`mcp.json`、`platform.json` 和 `.env`，并要求 GitHub MCP、Ralph execution、Review skill、Feishu inbound/outbound 都已配置完成。

如果你第一次接触这个仓库，只要记住两件事：

1. `MCP` 负责平台操作，不负责替代本地代码执行。
2. Ralph 和 Review 都默认在本地代码副本上工作，远程平台只做 issue/PR/comment 写回。

## API Surface

- `GET /health`
- `GET /diagnostics/integrations`
- `POST /gateway/message`
- `POST /webhooks/feishu/events`
- `POST /main-agent/intake`
- `POST /workers/sleep-coding/poll`
- `GET /workers/sleep-coding/claims`
- `GET /control/tasks/{task_id}`
- `GET /control/tasks/{task_id}/events`
- `GET /tasks/sleep-coding/{task_id}`
- `GET /reviews/{review_id}`

## Testing

运行全量测试：

```bash
python -m unittest discover -s tests -v
```

当前重点回归包括：

- Main Agent intake
- worker issue polling
- Ralph local-first execution
- review materialize 与 local review loop
- MVP 端到端链路

## Docs

优先阅读：

1. [docs/evolution/mvp-evolution.md](docs/evolution/mvp-evolution.md)
2. [docs/architecture/mvp-agent-platform-core.md](docs/architecture/mvp-agent-platform-core.md)
3. [docs/architecture/github-issue-pr-state-model.md](docs/architecture/github-issue-pr-state-model.md)
4. [docs/archive/architecture/mvp-agent-first-architecture.md](docs/archive/architecture/mvp-agent-first-architecture.md)（历史/过渡文档）

## Roadmap

- 继续减少 Ralph 对 issue-only 上下文的依赖
- 继续强化 GitHub / GitLab source materialize 的健壮性
- 继续压缩 Python fallback，让 LLM + skill + 本地仓库成为真正主路径
- 在保证可调试性的前提下继续做仓库瘦身
