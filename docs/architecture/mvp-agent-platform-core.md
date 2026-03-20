# MVP Agent Platform Core

> 更新时间：2026-03-20
> 目标：把 `Marten` 收口成一个小而硬的 agent platform core，用统一 contract 承载当前 MVP 主链：`main-agent -> ralph -> code-review-agent`。

## 一、北极星

当前阶段不是建设一个大而全的 agent 平台，而是把已经验证过的 MVP 主链收口到更轻、更稳、更可演进的核心骨架上。

MVP 的北极星只有一条：

> 先做一个小而硬的 `agent platform core`，让当前主链与未来 agent 都挂在同一套最小 contract 上，但不为未来通用性提前做重平台。

当前优先保障的真实链路不变：

`Feishu/Webhook -> main-agent -> issue/task handoff -> ralph -> code-review-agent -> final delivery`

## 二、设计边界

### 这次要解决什么

- 用统一的最小 agent contract 承载内置 agent。
- 收口入口、路由、会话、记忆、skill / MCP 装配等平台基础能力。
- 明确 `main-agent`、`ralph`、`code-review-agent` 在同一平台中的职责映射。
- 让当前主链更接近 `agent-first + skill-first + json-first` 的目标。

### 这次不解决什么

- 不做大而全的通用 multi-agent framework。
- 不做复杂队列、多任务并发调度系统。
- 不做完整长期记忆 / RAG 基建。
- 不把 reviewer 角色、垂直领域 agent、插件市场上升成平台一级对象。
- 不为了未来可能性，把 MVP schema 设计得过度完整。

## 三、平台分层

MVP 目标分层建议固定为 5 层：

### 1. `entry`

职责：

- 接收 Feishu / webhook / 内部事件输入。
- 做消息标准化和身份提取。
- 不承担业务编排。

### 2. `core`

职责：

- agent 注册与解析
- 路由决策
- session 管理
- handoff 管理
- memory 管理
- 当前主链 orchestration

这是唯一应承担控制权的层。

### 3. `runtime`

职责：

- provider 调用
- skill 加载
- MCP 装配
- token / cost 记账
- 执行时权限、超时和环境约束

### 4. `agents`

职责：

- 承载 agent-specific 行为、指令和输出结构。
- 当前只包括 `main-agent`、`ralph`、`code-review-agent` 三个内置 agent。

### 5. `artifacts`

职责：

- 记忆文件
- review 结果
- 任务输出
- workspace 产物

它们是运行产物，不是新的控制面。

## 四、最小 Agent Contract

MVP 不把 agent 的 8 个要素做成硬约束，而是只保留 4 个核心字段：

1. `agent_id`
2. `instructions`
3. `capabilities`
4. `runtime_policy`

### 1. `agent_id`

用途：

- 唯一标识
- 注册
- 路由
- 配置挂载

### 2. `instructions`

用途：

- 定义这个 agent 是谁
- 负责什么
- 不负责什么
- 在什么边界内工作

默认以 `AGENTS.md` 为主，必要时可引用 `TOOLS.md` 或 skill 文档，但不要求每个 agent 都拆成很多文件。

### 3. `capabilities`

用途：

- 声明 agent 能使用哪些 `skill / MCP / provider profile`
- 让 agent 的能力更多通过配置和文档表达，而不是埋在 Python 分支里

### 4. `runtime_policy`

MVP 只放真正影响执行的少数策略，例如：

- `session_scope`
- `memory_mode`
- `workspace_mode`

### 示例

```json
{
  "agent_id": "ralph",
  "instructions": {
    "system_file": "agents/ralph/AGENTS.md"
  },
  "capabilities": {
    "skills": ["coding", "planning"],
    "allowed_mcps": ["github", "filesystem"],
    "provider_profile": "default_coding"
  },
  "runtime_policy": {
    "session_scope": "task",
    "memory_mode": "agent",
    "workspace_mode": "repo_branch"
  }
}
```

## 五、内置 Agent 与配置模型

MVP 采用 `builtin-first, json-override` 模型。

### 内置 Agent

由 Python 内置注册，保证主链稳定：

- `main-agent`
- `ralph`
- `code-review-agent`

### JSON 配置

JSON 的职责不是凭空定义整个平台，而是：

- 覆盖内置 agent 的部分配置
- 调整 skill / MCP / provider 等实例级差异

因此平台应保持：

- Python 负责内置 agent 的执行器与主链稳定性
- JSON 只负责启停与覆盖，不在 MVP 中承担自定义 agent 装载职责

## 六、入口与路由模型

MVP 采用 `mixed-entry` 模型，但保持实现很薄。

### 路由顺序

1. 用户文本中显式点名 agent
2. 若未点名，则进入总入口 `main-agent`
3. `main-agent` 使用 LLM 做意图识别
4. 若识别为当前 agent 领域外的话题，优先询问用户是否切换
5. 若意图不变，则继续使用当前匹配的 agent

### 文本点名

MVP 只支持文本点名，不做 bot 绑定和复杂别名系统。

例如：

- `@ralph`
- `切到 Ralph`

当前 MVP 用户入口只考虑：

- `main-agent`
- `ralph`

`code-review-agent` 属于主链后置阶段，不作为默认用户直达入口。

### 路由对象

平台 core 只需要这些最小对象：

- `agent registry`
- `route resolver`
- `session manager`

不引入额外的重型 router framework。

## 七、Session 与 Handoff

MVP 的核心优先级是：

1. `session isolation`
2. `light memory`
3. `queue / concurrency` 未来再做

### 会话模型

MVP 采用“用户会话归属”和“内部任务 owner”分离的模型。

### 用户会话层

- 每个 session 有一个面向用户消息的 `active_agent`
- handoff 到用户可直接对话的 agent 后，默认粘住当前 agent
- `main-agent` 在后台继续观察会话是否出现明显跨域
- 当检测到明显跨域时，由 `main-agent` 重新做意图识别并优先向用户确认切换

### 主链任务层

- 主链任务另有自己的 `owner_agent`
- `owner_agent` 可以在 `ralph` 和 `code-review-agent` 之间流转
- `code-review-agent` 只属于内部主链阶段，不接管用户会话入口

示例：

```json
{
  "session_id": "xxx",
  "channel_id": "feishu:chat:123",
  "user_id": "u_123",
  "active_agent": "main-agent",
  "memory_profile": "light",
  "status": "active"
}
```

```json
{
  "task_id": "task_123",
  "session_id": "xxx",
  "owner_agent": "ralph",
  "stage": "coding",
  "status": "claimed"
}
```

### 切换规则

- `hard switch`: 用户显式点名，直接切换
- `soft switch`: guardian 检测到明显跨域，先确认再切换
- `no switch`: 仍属于当前 agent 能力域，继续使用当前 agent

## 八、Memory 策略

MVP 的记忆设计遵循极简原则，先不用向量库、embedding、retrieval pipeline 等重基建。

### 物理边界

只保留两类强制记忆，并物理隔离：

- `session memory`
- `agent memory`

`task memory` 不进入 MVP，只在未来演进中再评估。

### 1. `session memory`

只属于总入口与用户的会话层，目标是保持总入口上下文短而稳。

记录内容包括：

- 当前话题
- 当前 `active_agent`
- handoff 记录
- 已确认的路由判断

### 2. `agent memory`

属于具体 agent 的独立上下文，记录：

- 用户在该 agent 下的具体问题
- agent 的关键回答
- 已确认事实
- 阶段性结论

### 自动压缩

agent 级上下文达到窗口预算约 60% 时，触发自动摘要压缩：

- 原始内容沉淀到对应 `md` 文件
- 运行时只保留最近若干轮原文和摘要结果

### 持久化形态

记忆先以 Markdown 文件持久化，例如：

```text
artifacts/memory/
  sessions/
  agents/
```

## 九、Skill 与 MCP 分层

平台明确采用：

- `MCP as resource`
- `skill as behavior`

两者是并列概念，不做统一“大插件抽象”。

### MCP

职责：

- 外部资源接入
- 权限与上下文来源

来源：

- `mcps.json`

策略：

- `mcps.json` 定义可用资源
- MVP 运行时按内置 agent allowlist 装配需要的 MCP
- 不把“全局启动全部能力”作为当前主链默认策略

### Skill

职责：

- 组织 LLM 的行为步骤
- 约束执行方式
- 承载结构化工作流模板

来源：

- `skills/` 目录

策略：

- `skills/` 目录提供可发现 skill
- MVP 先按内置 agent allowlist 暴露 skill
- 是否调用某个 skill，再由总入口或具体 agent 的 LLM 判断

## 十、当前主链映射

### `main-agent`

定位：

- 总入口
- guardian
- 路由与澄清层

职责：

- 接收默认入口流量
- 识别文本点名
- 做 LLM 意图识别
- 创建或更新主链任务
- 执行 handoff
- 在必要时向用户确认切换

不负责：

- 直接承担所有专业任务执行
- 长时间持有复杂专业上下文

### `ralph`

定位：

- 内置任务型 coding agent

职责：

- 承接明确进入编码流程的 issue / task
- 进行 plan、编码、验证、提交和后续交接

未来多仓库原则：

- `ralph` 是一种内置 agent 类型，不是每个仓库复制一套框架
- 多仓库通过 `repo binding` 承载
- 自动扫描只处理明确标签或明确指派给 `ralph` 的 issue

### `code-review-agent`

定位：

- 内置任务型 review agent

职责：

- 对 `ralph` 产出做 review
- 产出统一的 review result / findings

未来扩展原则：

- reviewer roles 不升级为平台一级 agent
- 多角色 review 未来只作为 `code-review-agent` 的内部 skill 化步骤演进

## 十一、主链 Handoff Contract

MVP 必须明确的不是“谁负责什么”的口头描述，而是主链在 agent 之间如何稳定交接。

### 1. `main-agent -> ralph`

当 `main-agent` 判定请求进入编码主链后，必须生成一个结构清晰的 task handoff，至少包含：

- `task_id`
- `session_id`
- `owner_agent = ralph`
- `source = main-agent`
- `repo` 或目标工作区
- `issue` / 需求描述
- `acceptance` 或完成判断
- `status = claimed`

`main-agent` 的职责到此结束，不继续持有编码细节上下文。

### 2. `ralph -> code-review-agent`

当 `ralph` 完成编码与验证后，必须生成 review handoff，至少包含：

- `task_id`
- `session_id`
- `owner_agent = code-review-agent`
- `source = ralph`
- `workspace_ref` 或变更位置
- `validation_result`
- `review_scope`
- `status = in_review`

### 3. Review 返回路径

`code-review-agent` 只返回结构化 review 结果，不反向接管整个平台控制面。

最小返回结果应能表达：

- `task_id`
- `status = approved | changes_requested | failed`
- `findings`
- `summary`

后续由 `control` 决定是：

- 回给 `ralph` 进入修复
- 还是进入 final delivery

### 4. 状态归属

MVP 只允许一条主链状态真相：

- `control` 持有主状态
- `ralph` 和 `code-review-agent` 只提交阶段结果
- review result 和 coding artifact 是运行产物，不是新的主状态机

### 5. 最小状态流转

`control` 至少要明确拥有下面这条最小状态流：

`drafted -> claimed -> coding -> in_review -> approved -> delivered`

如果 review 要求修复，则走：

`in_review -> changes_requested -> coding -> in_review`

如果编码或 review 失败，则走：

`coding -> failed`

或：

`in_review -> failed`

这里的关键约束只有一条：

- 用户会话仍然挂在用户可对话 agent 上
- 内部任务 owner 和 stage 由 `control` 推进，不把 `code-review-agent` 暴露成用户会话 owner

## 十二、Ralph -> Review 主链

对于编码主链，`review` 不是可选插件，而是默认后置阶段。

MVP 主链应固定为：

`main-agent / direct route -> ralph -> code-review-agent -> final delivery`

这意味着：

- `ralph` 完成编码后默认总是进入 review
- `code-review-agent` 服务于主链闭环，不单独扩张成泛化平台

## 十三、目录与模块映射方向

MVP 仓库目录应继续收口到以下主骨架：

```text
app/
  channel/   # 入站标准化、出站通知
  control/   # 唯一 orchestration 层 / platform core
  runtime/   # llm / mcp / skills / token
  agents/    # main-agent / ralph / code-review-agent
  infra/     # 调度、sqlite、workspace、诊断
  models/    # schema
  ledger/    # token ledger
```

原则上：

- `channel` 不继续驱动 workflow
- `agents` 不承担平台级路由
- `runtime` 不承担业务编排
- `control` 收回主链控制权

## 十四、演进边界

本设计为未来预留扩展位，但不提前实现：

- agent 绑定专属机器人
- repo-bound `ralph`
- `code-review-agent` 的多角色内部 review
- 更强的长期记忆 / RAG
- 多 provider、多队列、多并发 worker

这些都应建立在当前 `agent platform core` 稳定之后演进，而不是反向推动 MVP 平台膨胀。

未来用户自定义 agent 也是演进方向，但不进入当前 MVP platform core。

## 十五、不做事项

这轮架构收口明确不做：

- 不把 8 要素 agent schema 做成强制规范
- 不做重型 plugin / marketplace
- 不做复杂 queue / scheduler 平台
- 不把垂直 agent 场景先塞进 MVP 主链
- 不为了未来多仓库和多 reviewer，先抽象出一整套重量级平台框架

## 十六、结论

`Marten` 的当前正确方向，不是继续长出更多层和更多平台对象，而是把已有主链压回一套更清晰的 agent-first 核心结构：

- 入口保持简单
- agent contract 保持最小
- session 与 memory 先做稳
- skill 与 MCP 分层明确
- `main-agent / ralph / code-review-agent` 统一挂在同一套 core 上

这样既能继续完成当前 MVP 仓库瘦身，也不会堵死后续演进到更轻量、可个人定制的 agent 平台。
