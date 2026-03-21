# Framework Package and Private Agent Rollout Plan

> 更新时间：2026-03-22
> 文档角色：`docs/evolution` 下的执行计划文档
> 目标：给 `Marten` 从当前主链仓库演进到“稳定框架 + 私有 agent 上层项目”的过程提供一份可执行路线。

## 一、执行目标

目标不是把 `Marten` 做成一个大而全的 agent 平台，而是把它稳步收口为：

- 可复用的底层框架
- 自带官方内置 agent
- 支持多机器人入口与通知分流
- 支持上层私有项目复用

## 二、阶段划分

### Phase 1: 明确框架边界

先把当前仓库收成“可被 package 化”的结构，而不是立即追求完整发布形态。

本阶段应完成：

- 明确 public surface
- 明确官方内置 agent 的复用边界
- 明确 channel endpoint / bot binding 模型
- 明确 RAG capability 的接口位置
- 明确哪些配置允许上层项目覆盖

本阶段不做：

- 不把新的私有 agent 加进当前仓库
- 不做重型 plugin marketplace
- 不做服务化大拆分

### Phase 2: 验证最小私有项目

新开一个独立私有项目，只验证一条最小私有链路。

验证重点：

- 是否能继续复用 `main-agent`
- 是否能继续复用 `ralph`
- 是否能继续复用 `code-review-agent`
- 是否能接入独立机器人入口
- 是否能挂接私有知识和私有 workflow

成功标准：

- 私有项目能跑通一条真实链路
- `Marten` 没有被迫加入明显的私有业务逻辑

### Phase 3: 再做 package 化与依赖升级策略

当 Phase 2 验证通过后，再补：

- package 入口整理
- 版本策略
- 私有项目升级方式
- 兼容策略
- 安装与分发方式

## 三、优先级建议

建议按下面顺序推进：

1. 多机器人入口和通知分流模型
2. 框架 public API / internal API 边界
3. 官方内置 agent 的复用方式
4. RAG capability 的框架接口
5. 私有项目最小验证
6. package 化与版本治理

## 四、短期不建议做的事

- 不建议现在就把 `Marten` 重写成纯服务化平台
- 不建议现在就引入复杂 marketplace / plugin registry
- 不建议先做大量新的私有 agent 再回头整理框架
- 不建议把私有知识直接塞进当前仓库

## 五、近期交付物建议

近期最值得产出的交付物是：

1. 一份框架定位与分层设计文档
2. 一份多机器人入口与通知分流设计
3. 一份 RAG capability 分层设计
4. 一个最小私有项目样板

## 六、完成标准

当下面这些条件同时成立时，说明这个路线基本走通：

1. `Marten` 可以明确回答自己的 public surface 是什么
2. 官方内置 agent 可以被上层项目复用
3. 多机器人入口与通知分流已经成为正式框架能力
4. RAG capability 在框架层，知识内容在私有项目层
5. 至少一个私有项目已验证“框架修复 -> 上层升级复用”的模式成立
