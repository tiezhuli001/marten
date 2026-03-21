# Framework Public Surface

> 更新时间：2026-03-22
> 文档角色：`docs/architecture` 下的实现规格文档
> 目标：定义 `Marten` 对上层私有项目的稳定接口面，避免把内部实现误当成框架 API。

## 一、设计目标

`Marten` 未来要作为底层框架被私有项目复用，就必须明确：

- 哪些能力是上层项目可以直接依赖的
- 哪些能力只允许通过扩展接口接入
- 哪些实现细节只能留在框架内部

本文件的角色不是设计目录重构，而是先定义稳定边界，为后续 package 化和私有项目复用提供规范。

## 二、分层原则

框架代码面对上层项目应分成三层：

1. `public surface`
2. `supported extension surface`
3. `internal only`

判断规则：

- 上层项目直接 import 依赖的对象必须进入 `public surface`
- 上层项目需要插入自己逻辑但不应依赖内部细节的对象进入 `supported extension surface`
- 仅服务当前框架内部编排的对象一律视为 `internal only`

## 三、Public Surface

这一层是未来必须尽量保持稳定的接口面。

### 1. Framework Facades

上层项目应通过 facade 访问框架能力，而不是直接依赖细碎内部 service。

应形成稳定 facade 的能力包括：

- channel endpoint registry facade
- session/context facade
- task/event facade
- runtime facade
- builtin agent facade
- RAG capability facade
- config loading facade

这些 facade 的职责是：

- 表达能力边界
- 隐藏内部存储与编排细节
- 为私有项目提供稳定入口

### 2. Builtin Agent Entry Points

下面这些官方内置 agent 必须具备可复用标准入口：

- `main-agent`
- `ralph`
- `code-review-agent`

标准入口的含义不是暴露全部内部实现，而是允许上层项目：

- 引用 agent id
- 绑定默认入口
- 作为 workflow owner 使用
- 覆盖 prompt / skills / MCP / provider binding

### 3. Config Surface

上层项目必须有清晰可覆盖的配置面。

最低要求包括：

- agents config
- models config
- platform config
- channel endpoint config
- retrieval / RAG config

配置面必须优先承担“装配能力”，而不是把策略散落到 Python 分支里。

## 四、Supported Extension Surface

这层允许上层项目扩展框架，但不意味着内部所有细节都稳定。

### 1. Agent Extension

上层项目应能够：

- 新增私有 agent spec
- 覆盖 agent 默认 prompt / skill / MCP / provider
- 将私有 agent 绑定到特定 channel endpoint 或 workflow

### 2. Channel Extension

上层项目应能够：

- 新增 channel endpoint
- 配置 endpoint 的默认 agent / workflow
- 配置通知分流策略

### 3. RAG Extension

上层项目应能够：

- 注册 retrieval provider
- 注册 knowledge domain
- 配置 retrieval policy
- 绑定 agent 到 domain / policy

### 4. Workflow Composition

上层项目应能够：

- 复用官方内置 workflow
- 在不破坏主链的前提下组合私有 workflow
- 配置 handoff / delivery policy

## 五、Internal Only

下面这些内容不应成为上层私有项目的直接依赖：

- sqlite store 细节
- `control_tasks` payload 内部字段布局
- `sleep_coding_tasks` / `review_runs` 持久化细节
- review loop 内部 helper
- 历史兼容字段与迁移兜底逻辑
- 面向当前实现的中间 helper 和私有函数

这些对象可以持续重构，但前提是不会破坏 public surface。

## 六、禁止的依赖方式

为避免未来框架和私有项目重新缠在一起，上层私有项目不应：

- 直接 import `app/control/*` 下的细碎内部模块来驱动主流程
- 直接依赖 `control_tasks` payload 的内部字段布局
- 通过 monkey patch 修改内置 workflow
- 通过复制内置 agent 代码来实现复用

允许的方式应始终优先是：

- 配置覆盖
- facade 调用
- extension interface
- hook / adapter

## 七、建议的模块演进方向

本阶段不要求立刻重排目录，但后续实现应朝下面的目标收口：

- `app/framework/*`
  - 放稳定 facade
- `app/builtin_agents/*`
  - 放官方内置 agent 的标准入口
- `app/extensions/*`
  - 放受支持的扩展接口
- `app/internal/*`
  - 或保留当前内部目录但在文档上明确 internal-only

重点不是目录名字本身，而是：

- 上层依赖应该落到哪层
- 编码 agent 改功能时应该把新能力放到哪层

## 八、实现期验收标准

当下面条件成立时，说明 public surface 设计达标：

1. 上层私有项目可以不依赖内部存储细节而复用框架能力
2. 官方内置 agent 的复用不依赖复制源码
3. 新增私有 agent / channel endpoint / retrieval provider 时，不需要改动大量内部编排代码
4. 框架内部重构不会直接破坏私有项目
5. 编码 agent 能依据本文件判断某个改动应该落在 public、extension 还是 internal 层
