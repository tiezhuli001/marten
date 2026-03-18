# 配置层重构设计与迁移计划

> 更新时间：2026-03-17
> 目标：把 `youmeng-gateway` 从“env 驱动的工程原型”收敛为“defaults-first、JSON-first、agent-first”的 Agent 应用配置体系。

## 1. 背景

当前项目已经完成多 Agent MVP 主闭环，但配置层仍然过于工程化：

- `.env` 暴露了过多 agent、worker、MCP 细节
- 多模型接入仍然主要依赖环境变量切换
- agent 的能力边界和默认模型没有中心化定义
- 高级 worker 参数直接暴露给用户，容易增加接入门槛

这与当前项目的长期目标不完全一致。

项目目标不是“后端服务集合”，而是：

> 一个足够先进、可持续扩展的多 Agent 应用。

因此配置层也应该体现这种产品形态。

## 2. 设计原则

### 2.1 Defaults First

- 用户不配置大多数高级参数时，系统也应能工作
- 复杂调优项不应成为首屏配置压力

### 2.2 JSON First

- `.env` 只保留 secrets 和基础运行参数
- 结构化配置应优先使用 JSON 文件

### 2.3 Agent First

- agent 的模型、skills、workspace、MCP servers 应由 agent 定义驱动
- 平台负责连接与治理，不把所有行为硬编码在环境变量里

### 2.4 Optional MCP

- `mcp.json` 完全可插拔
- 不配置 MCP 也不影响主系统启动
- 用户配置后即可使用
- token 可以直接由用户写在 `mcp.json` 中维护

## 3. 目标配置分层

长期目标配置边界建议如下：

### `.env`

只保留：

- 端口
- 数据库
- webhook secret
- provider API key
- 少量 fallback

### `mcp.json`

负责：

- MCP server 定义
- command / args / env / cwd / adapter

特点：

- 可选
- 用户自主管理
- token 可直接维护在文件中

### `models.json`

负责：

- provider profile
- model profile
- agent 默认模型选择
- `cheap / review / coding / default` 等 profile

### `agents.json`

负责：

- agent 列表
- workspace
- skills
- MCP servers
- model profile

### `platform.json`

负责：

- worker 默认值
- review loop 默认值
- sleep-coding 默认标签
- scheduler 默认行为

## 4. 当前到目标的迁移策略

### Phase A：加 JSON 支持，不破坏旧配置

目标：

- `agents.json / models.json / platform.json` 可读
- 没有这些文件时，继续 fallback 到 env

### Phase B：AgentRuntime 改为优先吃 agent/model profile

目标：

- agent 级别能决定默认模型
- provider / model 不再主要通过 env 拼接

### Phase C：Worker / Review 默认值迁到 platform.json

目标：

- `.env.example` 大幅缩减
- 高级参数进入平台配置

### Phase D：文档与联调手册切换到 JSON-first

目标：

- 用户首先配置 JSON
- `.env` 只作为 secrets 和启动参数补充

## 5. 本轮实施范围

本轮只做第一批基础改造：

1. 新增 `platform.json.example`
2. 新增 `agents.json.example`
3. 新增 `models.json.example`
4. settings 支持读取这些 JSON
5. agent workspace / skill / MCP server 改为优先从 JSON 读取
6. worker / review 默认值改为优先从 `platform.json` 读取
7. AgentRuntime 支持 agent model profile
8. 保留 legacy env fallback

## 6. 本轮非目标

本轮不做：

1. 完整 permission matrix
2. 长期 memory 系统
3. 所有配置完全移出 env
4. 新增更多 provider

## 7. 验收标准

本轮完成后，应满足：

1. 没有 JSON 文件时，项目仍按旧方式运行
2. 有 `agents.json / models.json / platform.json` 时，相关默认值从 JSON 生效
3. `.env` 压力开始下降，但不强制一次性迁移
4. agent 不再主要依赖 env 决定 workspace/skills/MCP/model
5. MCP 继续保持可插拔

## 8. 结论

配置层的目标不是“把 env 换成 json”这么简单，而是：

> 让 `youmeng-gateway` 从“后端式配置系统”演进为“多 Agent 应用式配置系统”。

这一步是吸收 OpenClaw / OpenCode 精髓的必要动作，也是后续继续做 supervisor、permission、binding、optional memory 的前提。
