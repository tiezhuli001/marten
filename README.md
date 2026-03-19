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
cp agents.json.example agents.json
cp models.json.example models.json
cp platform.json.example platform.json
cp mcp.json.example mcp.json
```

配置职责建议如下：

- `.env`: secrets、基础运行参数、JSON 配置入口
- `agents.json`: agent workspace、skills、MCP servers、agent spec
- `models.json`: provider profile、model profile
- `platform.json`: worker 默认值、worktree 行为、review loop、repo/channel 默认值
- `mcp.json`: MCP server 的 command、args、env、cwd、adapter

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

关键配置：

- `platform.json -> sleep_coding.execution.command`
- `platform.json -> sleep_coding.execution.allow_llm_fallback`
- `platform.json -> review.writeback_final_only`
- `platform.json -> review.follow_up_delay_seconds`

默认行为：

- Ralph 要求显式配置本地 execution command
- 未显式开启 `allow_llm_fallback` 时，不允许退回到 LLM 直接产出 patch
- review 默认每轮本地执行，只在最终结果时统一写回远程平台

## API Surface

- `GET /health`
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
2. [docs/architecture/mvp-agent-first-architecture.md](docs/architecture/mvp-agent-first-architecture.md)
3. [docs/architecture/github-issue-pr-state-model.md](docs/architecture/github-issue-pr-state-model.md)

## Roadmap

- 继续减少 Ralph 对 issue-only 上下文的依赖
- 继续强化 GitHub / GitLab source materialize 的健壮性
- 继续压缩 Python fallback，让 LLM + skill + 本地仓库成为真正主路径
- 在保证可调试性的前提下继续做仓库瘦身

## README Notes

这个 README 结构参考了开源社区常见模板组织方式，特别借鉴了 [othneildrew/Best-README-Template](https://github.com/othneildrew/Best-README-Template) 和 [Louis3797/awesome-readme-template](https://github.com/Louis3797/awesome-readme-template) 的章节组织思路，并按当前仓库的实际状态做了收敛。
