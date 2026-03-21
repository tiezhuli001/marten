# Framework Positioning and Private Agent Layering

> 更新时间：2026-03-22
> 文档角色：`docs/architecture` 下的设计文档
> 目标：明确 `Marten` 作为底层框架的定位，以及框架层与私有 agent 项目层之间的稳定边界。

## 一、设计结论

`Marten` 应被定位为一个稳定的 agent framework / control plane 仓库，而不是直接承载所有私有需求的业务仓库。

它需要长期承担两类职责：

- 提供通用框架能力
- 提供一组可复用的官方内置 agent

私有需求则应进入独立私有项目，通过依赖 `Marten` 来复用这些能力，而不是继续把私有 agent 直接长进当前仓库。

## 二、为什么要这样分层

当前仓库已经围绕单条 MVP 主链完成收口：

`Feishu/Webhook -> gateway/workflow -> main-agent -> ralph -> code-review-agent -> final delivery`

这说明 `Marten` 最有价值的部分不是某一个垂直业务 agent，而是：

- channel 接入
- 会话与上下文管理
- task / event / follow-up loop
- skill / MCP / LLM runtime
- coding / review 主链

这些能力天然适合作为底层框架存在。

如果继续把私有 agent 直接加进这个仓库，会产生三个问题：

1. 框架层和业务层边界模糊
2. 私有需求会不断把公共仓库拉回“功能拼盘”
3. 后续其他私有项目无法清晰判断哪些能力属于底层框架

因此更合理的方向是：

- `Marten` 只保留通用能力与官方内置 agent
- 私有项目基于 `Marten` 组装自己的私有 agent 与私有 workflow

## 三、框架层职责

`Marten` 作为框架层，应稳定提供下面这些能力。

### 1. Channel 与入口层

- 多 channel provider 接入
- 多机器人 endpoint 注册
- 入口消息标准化
- channel endpoint 到 agent / workflow 的绑定
- 对话入口与通知出口分离

### 2. Control Plane

- session 管理
- context / memory 拼装
- task / event lifecycle
- handoff 与 follow-up
- review loop 与 delivery orchestration

### 3. Runtime

- LLM provider 调用
- MCP 装配
- skill 加载
- token / cost accounting
- 执行时超时、重试、缓存、观测

### 4. Agent Spec 与装配

- agent descriptor / spec
- agent runtime policy
- agent 与 skill / MCP / provider 的绑定
- 上层项目的配置覆盖能力

### 5. 官方内置 Agent

`Marten` 需要长期保留并暴露官方内置 agent：

- `main-agent`
- `ralph`
- `code-review-agent`

这些内置 agent 不只是当前仓库的实现细节，而是框架的一部分。上层私有项目应能够直接复用它们，而不是复制一份实现。

## 四、私有项目职责

私有项目不应重复实现框架层能力，而应专注于：

- 私有 agent 定义
- 私有 skill
- 私有 prompt / workspace docs
- 私有 workflow 组合
- 私有仓库映射
- 私有知识与检索策略
- 私有 channel 路由配置

私有项目的定位应该是：

> 基于 `Marten` 的私有 agent suite，而不是另一个重新实现 control plane 的系统。

## 五、多机器人入口模型

框架不应再默认只有一个机器人入口。

未来的稳定模型应为：

- 多个机器人都可以作为独立入口
- 不同机器人可绑定不同默认 agent / workflow
- 高频 review / follow-up / delivery 通知可走独立通知机器人
- 主对话机器人只承担用户沟通，不被高频系统通知污染

建议框架把 channel endpoint 提升为一等配置对象，每个 endpoint 至少定义：

- `provider`
- `mode`
- `default_agent`
- `default_workflow`
- `delivery_policy`

这样可以同时支持：

- 主对话入口
- 编码执行入口
- 高频通知出口
- 未来的私有 agent 专用入口

## 六、RAG 的分层位置

RAG 应作为框架能力存在，但私有知识内容不应进入框架仓库。

### 框架层负责

- retrieval provider 接口
- index / store adapter 接口
- query 生命周期钩子
- 与 session / context / memory 的拼接点
- 缓存、权限、观测、token 成本控制

### 私有项目负责

- 私有知识内容
- 数据清洗与索引
- 召回策略
- agent 到知识域的绑定关系

建议把 RAG 进一步拆成两类：

- `Operational RAG`
  - 面向框架与官方内置 agent
  - 例如 repo 文档、issue、PR、review 历史、workflow 规则
- `Domain RAG`
  - 面向私有 agent
  - 例如私有知识库、私有 SOP、私有语料

两类都通过同一套框架接口接入，但内容与召回策略由上层决定。

## 七、推荐使用方式

推荐使用方式不是“继续把所有 agent 都塞进 `Marten`”，而是：

1. 在 `Marten` 中持续优化底层框架能力
2. 在私有项目中复用框架层与官方内置 agent
3. 私有需求如果暴露出框架问题，先回到 `Marten` 修复
4. 私有项目再升级依赖继续使用

这意味着：

- `Marten` 是基础设施仓库
- 私有项目是个人生产力应用层

## 八、判断一个需求该落哪层

可以用下面的简单规则判断：

- 如果一个能力未来大概率会被多个私有 agent 或多个项目复用，就进 `Marten`
- 如果一个能力明显只服务某个私有场景，就留在私有项目
- 如果一时看不清是否通用，先在私有项目验证，验证成立后再抽回 `Marten`

## 九、设计红线

后续演进不应回退下面这些原则：

- 不要把 `Marten` 重新拉回私有业务仓库
- 不要把私有知识内容直接写进框架仓库
- 不要让多机器人入口能力退回单入口假设
- 不要把官方内置 agent 降回不可复用的仓库内部实现
- 不要让上层私有项目重新实现一套独立 control plane
