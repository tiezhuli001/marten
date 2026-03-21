# Multi-Endpoint Channel Routing

> 更新时间：2026-03-22
> 文档角色：`docs/architecture` 下的实现规格文档
> 目标：定义多机器人入口、默认 agent/workflow 绑定、通知分流与会话归属的最小实现模型。

## 一、设计目标

框架必须支持：

- 多个机器人作为独立入口
- 不同机器人绑定不同默认 agent / workflow
- 高频 review / follow-up / delivery 通知分流到独立出口
- 主对话入口保持清爽，不被系统通知污染

同时必须遵守框架宗旨：

- 能力主要来自 `LLM + prompt + MCP + skill`
- 工程层只负责最小必要的路由、绑定和状态控制

## 二、最小对象模型

### 1. `ChannelEndpoint`

表示一个可接收或发送消息的入口/出口。

最小字段：

- `endpoint_id`
- `provider`
- `mode`
- `entry_enabled`
- `delivery_enabled`

### 2. `EndpointBinding`

表示某个 endpoint 的默认路由行为。

最小字段：

- `endpoint_id`
- `default_agent`
- `default_workflow`
- `delivery_policy`
- `allowed_handoffs`

### 3. `ConversationRoute`

表示一条会话当前走到哪里。

最小字段：

- `session_id`
- `source_endpoint_id`
- `active_agent`
- `active_workflow`
- `delivery_endpoint_id`

## 三、入口路由规则

入口路由应保持极简。

建议按以下优先级决策：

1. 用户显式点名 agent
2. 当前 endpoint 的 `default_agent`
3. 当前 endpoint 的 `default_workflow`
4. 若都未定义，则回退到主入口默认 `main-agent`

这套规则足以支持：

- 主对话机器人默认进入 `main-agent`
- 某个机器人默认进入 coding workflow
- 某个机器人默认进入私有 agent
- 用户在同一入口中显式切换 agent

## 四、会话归属规则

多 endpoint 入口引入后，必须区分：

- 用户从哪个 endpoint 进入
- 当前会话由哪个 agent 接管
- 后续通知从哪个 endpoint 发出

建议规则：

- `source_endpoint_id` 永远记录初始入口
- `active_agent` 可在会话中动态切换
- `delivery_endpoint_id` 可独立于入口
- `code-review-agent` 仍不作为默认用户直达入口，只作为主链内部 owner

## 五、通知分流规则

通知分流不应做成复杂策略引擎，先支持最小 3 类策略即可。

### 1. `same_endpoint`

- 从原入口回发

### 2. `fixed_endpoint`

- 始终发到指定通知机器人 / 群

### 3. `workflow_mapped`

- 按 workflow 类型映射不同通知出口

这三类已经足够覆盖当前目标：

- 主入口只做对话
- review / follow-up / delivery 发到独立通知出口
- 某些私有 workflow 有自己的专用出口

## 六、推荐配置模型

本阶段优先使用配置驱动，不引入重型后台管理。

最小配置能力应包括：

- 定义多个 endpoint
- 给 endpoint 绑定默认 agent / workflow
- 给 workflow 绑定 delivery policy
- 配置允许的 handoff 范围

推荐先支持：

- Feishu 多 endpoint
- 后续其他 provider 复用同一抽象

## 七、异常与回退规则

### 1. endpoint 未命中绑定

- 回退到主入口默认 `main-agent`

### 2. 指定 delivery endpoint 不可用

- 回退到 `same_endpoint`
- 并记录 delivery failure event

### 3. handoff 不在允许范围内

- 保持当前 `active_agent`
- 返回显式 routing failure 事件

## 八、短期不做

为守住“最小必要工程面”的原则，短期不做：

- 可视化 routing DSL
- 重型权限规则引擎
- bot-to-bot 复杂协同编排
- 独立 endpoint 管理后台
- 每个 channel 单独定制一套编排逻辑

## 九、实现期验收标准

当下面条件同时成立时，说明多 endpoint 模型足够可实现：

1. 不同机器人可以绑定不同默认 agent / workflow
2. 主对话入口与高频通知出口已经可以分离
3. 会话能清楚记录入口、当前 owner 和 delivery 出口
4. 编码 agent 能通过配置扩展新的 endpoint，而不是改写大量控制面代码
