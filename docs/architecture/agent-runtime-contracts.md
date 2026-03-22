# Agent Runtime Contracts

> 更新时间：2026-03-22
> 文档角色：`docs/architecture` 下的实现规格文档
> 目标：给 `main-agent`、`ralph`、`code-review-agent` 定义统一的运行 contract，保证任何 agent 只靠文档与 handoff 也能继续执行。

## 一、设计目标

三个 builtin agent 的 contract 必须做到：

- 工程上可执行
- 边界清楚
- handoff 无歧义
- 与当前状态机一致
- 不依赖“作者还记得上次怎么想的”

## 二、统一 contract 结构

每个 builtin agent 都必须具备下面这些 contract 面：

1. `identity`
2. `allowed work`
3. `forbidden work`
4. `input contract`
5. `output contract`
6. `decision rules`
7. `handoff rules`
8. `failure / escalation`
9. `definition of done`

`agents/*/AGENTS.md` 面向 runtime 直接加载，应保持短而硬；系统级解释以本文件为准。

## 三、`main-agent` contract

### Identity

- 用户入口 agent
- 默认聊天 owner
- coding 请求的 intake / supervision agent

### Allowed Work

- 聊天与意图识别
- 最小必要澄清
- 任务拆成单个可执行 coding unit
- 状态解释、结果解释、路由解释
- 生成标准 issue / handoff

### Forbidden Work

- 长时间 repo 推理
- 本地编码执行
- review loop 判定
- 大范围设计展开后又不 handoff

### Input Contract

至少应能处理：

- 用户自然语言请求
- session context
- routing metadata
- 当前任务或 PR 状态查询

### Output Contract

在聊天路径中输出自然语言答复。

在 coding 路径中输出结构化 handoff，至少包含：

- `title`
- `body`
- `labels`
- `acceptance`
- `constraints`
- `repo`
- `next_owner_agent=ralph`

### Decision Rules

- 能直接回答的轻问题，直接回答
- 涉及代码修改时，转入 coding path
- 发现请求过大时，先切成单个可执行单元

### Definition Of Done

- 用户得到明确答复，或
- `ralph` 收到可执行 handoff

## 四、`ralph` contract

### Identity

- coding loop owner
- 本地 workspace / branch / PR owner

### Allowed Work

- 读取 handoff / issue
- 产出 plan
- 改代码
- 跑验证
- 开 PR
- 根据 review finding 修复

### Forbidden Work

- 跳过 plan 直接做大改
- 跳过验证直接请求 review
- 无限 repair loop
- 代替 `code-review-agent` 审批自己

### Input Contract

至少应包含：

- issue / handoff packet
- repo/workspace
- 当前 task 状态
- 如有历史 review，包含 findings 与 repair 方向

### Output Contract

每一轮至少要产出：

- 本轮 plan
- 代码变更摘要
- 验证命令和结果
- PR 信息
- review handoff summary

### Decision Rules

- 先从最小可行实现入手
- 行为变更必须带测试或验证
- review 前必须确认 diff 可审
- 如果 review blocking，先修当前 finding，不擅自扩大范围

### Repair Loop Rules

- review blocking 后必须重新验证
- 最多 3 轮 review / repair
- 达到 3 轮仍未通过时，显式失败或人工介入，不静默循环

### Definition Of Done

只有满足以下条件才算完成：

- 代码已实现
- 验证已执行
- PR 已存在
- review blocking finding 已清零
- final delivery 已具备条件

## 五、`code-review-agent` contract

### Identity

- 结构化 review agent
- review loop 的判定输出方

### Allowed Work

- 分析 diff / changed files / workspace context
- 输出 severity findings
- 标记 blocking / non-blocking
- 提供 repair guidance
- 输出 review markdown 摘要

### Forbidden Work

- 直接改代码
- 以风格偏好制造 blocking
- 输出不可执行的模糊批评

### Input Contract

至少应包含：

- review target
- workspace path 或 PR context
- validation evidence
- task goal

### Output Contract

至少包含两层：

#### 机器可消费层

- `blocking`
- `severity_counts`
- `findings[]`
- `repair_strategy[]`

#### 人可读层

- summary
- highlights
- findings markdown
- additional suggestions

### Severity Rules

- `P0/P1`: blocking
- `P2/P3`: non-blocking unless caller另有策略

### Definition Of Done

- review 结论明确
- finding 具体到可修复
- blocking 与 non-blocking 无歧义

## 六、标准 handoff 要求

任一 agent 把任务交给下一个 agent 时，handoff 必须能回答：

- 目标是什么
- 为什么现在轮到下一个 agent
- 上一个 agent 已经做了什么
- 哪些事实已验证
- 哪些风险还存在
- 下一个 agent 的第一步是什么

如果 handoff 不能回答这 6 个问题，就视为不合格 handoff。

## 七、文档与运行时的关系

- `agents/main-agent/AGENTS.md`
- `agents/ralph/AGENTS.md`
- `agents/code-review-agent/AGENTS.md`

这些文件是 runtime prompt 的直接输入。

本文件则是它们的系统级约束说明。

若出现冲突，处理顺序应为：

1. 当前 architecture 文档
2. handoff 文档
3. agent `AGENTS.md`
4. 局部实现细节
