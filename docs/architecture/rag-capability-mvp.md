# RAG Capability MVP

> 更新时间：2026-03-22
> 文档角色：`docs/architecture` 下的实现规格文档
> 目标：定义 `Marten` 中最小可复用的 RAG capability，使私有 agent 后续可以基于框架接入知识增强能力。

## 一、设计目标

RAG 在当前路线中的定位是：

- 主要服务私有 agent
- 框架层只先提供一套最小可复用 capability
- 不在第一阶段把 `Marten` 做成重型知识平台

核心原则不变：

- agent 的主要能力仍来自 `prompt + MCP + skill + workspace docs`
- RAG 是增强项，不是主链的唯一依赖

## 二、MVP 边界

MVP 只解决四件事：

1. agent 如何声明自己需要哪些 knowledge domain
2. runtime 如何调用 retrieval provider
3. retrieval 结果如何拼进上下文
4. 上层私有项目如何接入自己的知识内容

MVP 不解决：

- 重型 embedding pipeline
- 大一统知识中心
- 复杂索引管理后台
- 框架内置私有知识内容

## 三、最小对象模型

### 1. `KnowledgeDomain`

表示一个知识域，不绑定具体存储实现。

最小字段：

- `domain_id`
- `domain_type`
- `owner`
- `visibility`

建议 `domain_type` 先只支持：

- `operational`
- `private`

### 2. `RetrievalProvider`

表示一个可被 runtime 调用的检索来源。

最小能力：

- `search(query, domain, options)`
- `fetch(item_ref)`

### 3. `RetrievalPolicy`

表示某个 agent / workflow 何时调用哪个 domain。

最小字段：

- `agent_id`
- `workflow`
- `domains`
- `top_k`
- `trigger_mode`

建议 `trigger_mode` 只支持：

- `never`
- `always`
- `on_demand`
- `fallback_only`

### 4. `ContextMergePolicy`

表示检索结果如何拼入 agent 输入。

最小字段：

- `merge_mode`
- `max_tokens`
- `dedupe`
- `citation_mode`

## 四、双层 RAG 模型

### 1. `Operational RAG`

面向框架与官方内置 agent。

典型内容：

- repo 文档
- issue / PR / review 历史
- workflow 规则
- 架构说明

使用对象：

- `main-agent`
- `ralph`
- `code-review-agent`

### 2. `Private Domain RAG`

面向私有项目中的私有 agent。

典型内容：

- 私有知识库
- 私有 SOP
- 私有历史语料
- 私有案例与规则

使用对象：

- 私有 agent
- 私有 workflow

这两层应共用同一套 capability 接口，但内容和策略由不同层维护。

## 五、框架层职责

`Marten` 在 RAG MVP 阶段只负责：

- retrieval provider 接口
- domain 注册接口
- retrieval policy 装配
- context merge hook
- 缓存与观测钩子

不负责：

- 私有知识内容本身
- 私有索引结构
- 私有语料管理后台

## 六、私有项目职责

私有项目负责：

- 提供私有 domain
- 提供私有 retrieval provider 或 provider 配置
- 定义私有 agent 的 retrieval policy
- 管理私有知识内容与索引

也就是说，上层项目接的是框架 capability，不是把知识写回框架仓库。

## 七、推荐接入方式

MVP 阶段建议按下面顺序接入：

1. 框架先支持 retrieval provider interface
2. 框架先支持 domain / policy 配置
3. 先让官方内置 agent 可选接入 `Operational RAG`
4. 再让私有项目接入 `Private Domain RAG`

这样可以保证：

- 框架先有能力面
- 私有项目再决定是否使用和如何使用

## 八、短期不做

短期不建议做：

- 向量库绑定到框架核心
- 每个 agent 各写一套检索工程逻辑
- 将 RAG 变成主链强依赖
- 在框架中落私有知识内容

## 九、实现期验收标准

当下面条件同时成立时，说明 RAG capability MVP 足够进入实现阶段：

1. 官方内置 agent 能可选接入 `Operational RAG`
2. 私有项目能通过配置接入 `Private Domain RAG`
3. 私有知识内容不需要写入 `Marten` 仓库
4. 没有把框架演进成重型知识平台
