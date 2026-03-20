# MVP Agent-First Architecture

> 更新时间：2026-03-16
> 目标：参考 OpenClaw 的控制平面与 agent runtime 思路，为 `Marten` 定义更适合当前 MVP 的 agent-first 架构。

## 一、设计目标

MVP 目标不是先做“大而全的平台”，而是做一个足够优雅的最小多 agent 系统：

1. 用户从 Feishu 发起需求
2. Gateway 统一接收并标准化消息
3. Main Agent 负责需求理解与 GitHub issue 创建
4. Ralph 负责异步编码与提 PR
5. Code Review Agent 负责 review 与 repair loop
6. Shared Infra 负责 token/cost、调度、状态机、通知

## 二、核心架构方向

### 1. Gateway 作为控制平面

参考 OpenClaw，MVP 应把 Gateway 视为：

- 唯一入口
- 消息标准化中心
- binding / routing 中心
- session / task 的控制平面

Gateway 不直接承担所有 agent 智能，只负责：

- 接入 Channel
- 识别消息来源
- 路由到目标 Agent
- 管理会话和任务状态

第一版就应明确两层抽象：

- `normalized message`
- `binding -> agent route`

也就是说，Feishu 入站消息先标准化，再由 Gateway 根据 binding 决定进入哪个 Agent，而不是直接把 webhook 绑死到某个 service。

### 2. Agent Runtime 共享，不为每个 Agent 重写框架

MVP 应采用一个共享 runtime：

- 统一 provider 调用
- 统一 skill 加载
- 统一 MCP 调用
- 统一工具权限和超时控制
- 统一 token/cost 记账

各个 Agent 只定义：

- 角色
- 可用 skills
- 可用 MCP / tools
- 状态边界
- workspace / 指令文件

Agent 的差异应优先通过工作区和指令表达，而不是优先写成 Python 分支逻辑。

### 3. 每个 Agent 有独立职责，不追求“万物都是 Agent”

MVP 只保留 3 个核心 Agent：

- `main-agent`
- `ralph`
- `code-review-agent`

避免过早扩展更多 agent。

### 4. Channel Adapter 与 Agent 解耦

参考 OpenClaw 的 channel adapter 思路：

- Feishu 只负责入站 / 出站通信
- Agent 不直接耦合 Feishu 协议细节
- 所有 channel 消息先转换为统一内部消息格式

这样后续再扩 Telegram / Slack / WebChat 时，不需要重写 Agent。

## 三、OpenClaw 风格下的关键补充

### 1. Binding / Session 是 MVP 必需概念

MVP 不应只停留在“有一个 FastAPI 接口”，而应明确具备：

- `binding`: 哪类消息路由到哪个 agent
- `session`: 同一用户 / 同一线程 / 同一任务的上下文边界

第一版可以简化，但不能缺失这两个概念。

建议的最小 binding：

- Feishu 普通对话 -> `main-agent`
- Sleep Coding 任务事件 -> `ralph`
- Review 任务事件 -> `code-review-agent`

### 2. Per-Agent Workspace / Instruction Files

参考 OpenClaw，MVP 应尽量把 agent 的差异写在工作区和指令文件里，而不是埋在业务代码里。

第一版建议每个核心 agent 至少有：

- `AGENTS.md`
- `TOOLS.md`
- `skills/`

可选：

- `SOUL.md`
- `IDENTITY.md`

这样后续调整 agent 行为时，优先改指令和 skill，而不是优先改代码。

## 四、MVP 的最小模块划分

### A. Channel Layer

职责：

- Feishu 入站事件接入
- Feishu 出站消息发送
- 消息标准化
- 用户与会话标识提取

建议：

- MVP 只做 Feishu
- 不提前设计多平台复杂抽象
- 但内部消息结构要统一，避免后面返工

### B. Gateway / Control Plane

职责：

- 接收标准化消息
- 根据 binding 路由到 Agent
- 统一 session / task / run 管理
- 统一事件流与状态写回

建议：

- 继续保留 FastAPI 作为 HTTP 网关
- 不为 MVP 额外引入复杂消息总线
- 以数据库 + scheduler + service 编排为主
- 明确引入最小 binding 和 session manager

### C. Shared Agent Runtime

职责：

- 调用 LLM provider
- 加载 skills
- 调用 MCP / tools
- 统一采集 usage / cost
- 管理超时、重试、权限
- 解析 agent workspace 指令

建议：

- 不为每个 agent 写单独的 provider / skill / MCP 代码
- 使用统一 runtime，agent 只注入配置和上下文

### D. Main Agent

职责：

- 理解用户需求
- 生成 issue 草案
- 调用 GitHub 创建 issue
- 给用户确认或直接回传 issue 结果

### E. Ralph

职责：

- 轮询或定时发现可处理 issue
- 生成 plan
- 调用 coding skill / MCP 在 worktree 中编码
- 验证、commit、push、创建 PR

### F. Code Review Agent

职责：

- review local / GitHub / GitLab
- 生成 review 结果
- 评论回写
- 输出结构化 findings
- 驱动 repair loop

### G. Shared Infra

职责：

- token ledger
- pricing registry
- scheduler / polling
- 状态存储
- 通知发送

## 五、Agent-First 的实现原则

### 应优先交给 LLM + skill + MCP 的工作

- 需求理解
- issue 生成
- plan 生成
- 编码实现
- code review
- repair strategy
- 最终结果总结

### 应优先交给工程代码的工作

- Feishu 鉴权与会话映射
- GitHub / GitLab / MCP 连接配置
- token/cost 精确记账
- worker 调度
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
