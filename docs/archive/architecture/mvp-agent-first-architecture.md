# MVP Agent-First Architecture

> 文档角色：历史/过渡说明文档。当前以 [mvp-agent-platform-core.md](/Users/litiezhu/workspace/github/marten/docs/architecture/mvp-agent-platform-core.md) 作为 canonical 架构文档。

> 更新时间：2026-03-21
> 目标：记录当前 `Marten` 的真实 MVP 架构边界，避免继续沿用旧阶段的大而全表述。

## 一、当前 MVP 只保留一条主链

当前稳定主链为：

`Feishu/Webhook -> Gateway -> main-agent -> Ralph -> code-review-agent -> final delivery`

这条链路之外的多来源 review、多平台 channel、多 SCM 平台不是当前 MVP 真相。

## 二、控制面职责

Gateway / control 只做四件事：

- 标准化入站消息
- 路由到目标 agent
- 管理 `user_session / agent_session / run_session`
- 管理控制任务、handoff 事件和自动 follow-up

控制面不承载 agent 智能本身，也不再把 webhook 直接绑死到某个 agent service。

## 三、运行时职责

当前共享 agent runtime 只保留 MVP 必需能力：

- 统一 LLM provider 调用
- 统一 skill 加载
- 统一 MCP 工具发现与注入
- 读取 agent workspace 下的 `AGENTS.md` 与 `TOOLS.md`
- 统一 token/cost 记账

当前不再保留 `SOUL.md` 兼容层。

## 四、三个内置 agent

### `main-agent`

- 总入口
- 负责意图识别、点名路由、issue intake
- 用户会话的活跃 owner 默认保持在这里

### `ralph`

- 负责 sleep-coding 主执行链
- 生成计划、编码、验证、提 PR
- 完成后默认进入 review

### `code-review-agent`

- 只 review `sleep_coding_task`
- review 上下文来自 Ralph 任务和对应 worktree
- 输出结构化 findings，并把结论回写给 Ralph 控制任务

## 五、会话与记忆边界

MVP 当前按物理边界拆成三类：

- `user_session`：用户对总入口的短上下文
- `agent_session`：agent 级上下文
- `run_session`：一次具体执行链

轻量记忆采用数据库 + markdown 镜像：

- `artifacts/memory/sessions/*.md`
- `artifacts/memory/agents/<agent_id>/*.md`

当前还没有引入复杂向量记忆或 task memory。

## 六、MVP 原则

- `agent first`：先稳住 agent contract，再扩具体垂直 agent
- `skill first`：优先通过 skill 和 workspace 指令表达差异
- `MCP as resource layer`：MCP 是底层资源接入，不是调度层
- `json first`：agent 间 handoff 和结构化输出必须显式可解析
- `GitHub only for now`：当前主链只面向 GitHub issue / PR 协作事实
- 轮次限制
- 状态机
- 幂等与失败恢复
- binding / session 管理

## 六、减法原则

为了“代码做减法而不是加法”，MVP 不应做：

- 自研复杂 multi-agent framework
- 自研复杂 message bus
- 自研复杂 prompt registry 平台
- 自研复杂 plugin marketplace
- 为了抽象而抽象的 provider 层

MVP 应做：

- 1 个 Gateway
- 1 个共享 Runtime
- 3 个核心 Agent
- 1 套共享 Infra
- 1 套最小 binding / session 机制

## 七、当前收敛补充

当前代码库已经明确收敛到以下原则：

- provider/model 由 `models.json` 驱动，`.env` 只做 override
- MCP server 由 `mcp.json` 驱动，不再依赖代码里注入 `GITHUB_TOKEN` / `OPENAI_API_KEY` 之类 placeholder alias
- GitHub 平台操作只走 MCP bridge，不再保留 GitHub REST 恢复路径
- MiniMax 内建 provider 现在只是默认的 OpenAI-compatible provider，不再保留专用 runtime 分支
- pricing 主路径优先读取 provider 配置，内建价格表只作为零配置 fallback

## 八、依赖库选择原则

参考 OpenClaw“尽量复用成熟库”的思路，Python 侧建议：

- `FastAPI`: Gateway / Webhook API
- `httpx`: 统一外部 HTTP 调用
- `pydantic` / `pydantic-settings`: 配置与 schema
- `APScheduler`: cron / polling / heartbeat
- `openai` 官方 SDK 或 OpenAI-compatible HTTP API: provider 主路径
- `MCP Python SDK`: MCP 客户端接入
- 飞书官方 SDK 或稳定 event/webhook SDK：Feishu channel adapter
- `SQLite` 先继续使用，后续再迁 PostgreSQL

不建议继续新增大量自写 HTTP 封装和 provider 逻辑，除非没有成熟库。

## 九、推荐的 MVP 形态

最适合当前项目的 MVP 不是：

> 一个不断叠加 service 的工程系统

而应该是：

> 一个 OpenClaw 风格的控制平面 + 3 个核心 agent + 最小共享基础设施

这样既能实现你的需求，也能保持结构优雅、模块清晰、后续可扩展。
