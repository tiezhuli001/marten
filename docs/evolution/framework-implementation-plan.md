# Framework Implementation Plan

> 更新时间：2026-03-22
> 文档角色：`docs/evolution` 下的最终执行计划文档
> 目标：把当前设计文档收束为一份可以直接驱动编码 agent 落地的实现计划。

## 一、计划目标

本计划的目标不是实现一个大而全的平台，而是把 `Marten` 稳步推进到下面的状态：

- 作为稳定框架存在
- 保留并暴露官方内置 agent
- 支持多机器人入口与通知分流
- 支持最小 RAG capability
- 允许独立私有项目在其之上复用与扩展

## 二、输入文档

实现前，编码 agent 必须先读下面 5 份文档：

1. [framework-positioning-and-private-agent-layering.md](../architecture/framework-positioning-and-private-agent-layering.md)
2. [framework-public-surface.md](../architecture/framework-public-surface.md)
3. [multi-endpoint-channel-routing.md](../architecture/multi-endpoint-channel-routing.md)
4. [rag-capability-mvp.md](../architecture/rag-capability-mvp.md)
5. [framework-package-and-private-agent-rollout-plan.md](framework-package-and-private-agent-rollout-plan.md)

## 三、实现总原则

编码阶段必须遵守下面这些约束：

- 优先 `prompt + MCP + skill + config`，不要把能力过早做成重工程逻辑
- 只做最小必要的框架改动
- 不把私有 agent 直接实现进当前仓库
- 不削弱 `main-agent / ralph / code-review-agent` 的官方内置地位
- 不把 RAG 演进成框架内置知识平台

## 四、阶段拆分

### Stage 1: Public Surface 收口

目标：

- 定义并实现最小 framework facade
- 明确 builtin agent 的标准入口
- 明确 extension surface 与 internal-only 边界

涉及范围：

- framework facade 入口
- builtin agent registry / loader
- config surface 收口

本阶段不做：

- 不做 package 发布
- 不做大量私有 agent 支持逻辑

验收标准：

- 上层项目不必依赖内部存储细节即可复用框架能力
- builtin agent 可通过标准入口被引用

### Stage 2: Multi-Endpoint Channel Routing

目标：

- 支持多个机器人 endpoint
- 支持默认 agent / workflow 绑定
- 支持通知分流

涉及范围：

- channel endpoint config
- route resolution
- session route state
- delivery policy

本阶段不做：

- 不做复杂 routing DSL
- 不做重型 endpoint 管理后台

验收标准：

- 不同机器人可绑定不同入口语义
- 主对话与高频通知已可分离

### Stage 3: RAG Capability MVP

目标：

- 定义 retrieval provider interface
- 定义 domain / policy / merge policy
- 让官方内置 agent 可选接入 `Operational RAG`

涉及范围：

- retrieval provider interface
- domain registration
- retrieval policy config
- context merge hook

本阶段不做：

- 不做框架内置私有知识内容
- 不做复杂索引平台

验收标准：

- 框架已有最小 RAG capability
- 私有项目未来可接自己的私有 domain

### Stage 4: 最小私有项目验证

目标：

- 新建一个独立私有项目验证复用模式

验证重点：

- 复用 `main-agent`
- 复用 `ralph`
- 复用 `code-review-agent`
- 接入独立 endpoint
- 接入私有知识 domain

本阶段不做：

- 不做大量私有 agent 堆砌
- 不做复杂业务平台化

验收标准：

- 私有项目能跑通一条真实链路
- `Marten` 未被迫塞入明显私有逻辑

## 五、模块级建议

编码 agent 在实现时，应优先考虑下面几类模块：

- facade / registry / config loader
- channel endpoint binding
- delivery routing
- retrieval interface / policy
- builtin agent 标准入口

编码 agent 不应优先从下面方向入手：

- 数据库大迁移
- 重型抽象层
- 大量新 service
- 复杂后台管理能力

## 六、测试策略

每个阶段都应至少包含：

- 配置解析测试
- route / policy 行为测试
- builtin agent 复用测试
- 不破坏当前 MVP 主链的回归测试

完成阶段实现后，应至少重新验证：

- 当前定向单测
- `tests/test_mvp_e2e.py`
- 必要时 `tests/test_live_chain.py`

## 七、风险与回退策略

### 风险 1: 框架边界抽象过重

处理策略：

- 优先最小 facade
- 不先引入重型层级

### 风险 2: 多 endpoint 设计侵入现有主链

处理策略：

- 先以配置驱动绑定为主
- 保留单入口默认回退逻辑

### 风险 3: RAG 设计过度平台化

处理策略：

- 只做 capability MVP
- 知识内容始终留在私有项目层

### 风险 4: 私有项目反向污染框架

处理策略：

- 任何私有需求先在私有项目验证
- 只有确认具备通用性后，再回抽到框架

## 八、完成标准

当下面条件同时成立时，说明已经进入“最后 coding 阶段”：

1. framework public surface 已定义清楚
2. 多 endpoint routing 规格已定义清楚
3. RAG capability MVP 规格已定义清楚
4. 最终实现计划已形成并可执行
5. 编码 agent 不再需要回头补关键设计边界即可进入实现

## 九、当前结论

基于当前文档集，项目在本轮结束后应被视为：

> 已完成设计阶段，已进入最后 coding 阶段。

后续编码 agent 的任务不再是继续讨论方向，而是严格按上述文档推进实现。
