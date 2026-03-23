# Agent System Overview

> 更新时间：2026-03-22
> 文档角色：`docs/architecture` 下的 canonical agent system 文档
> 目标：定义 `Marten` 当前正式生效的三 agent 主链、职责边界、handoff contract 与闭环规则。

实现边界与 agent-first 原则，另见：

- [agent-first-implementation-principles.md](agent-first-implementation-principles.md)

## 一、设计结论

`Marten` 当前正式支持的内置 agent system 只有一条主链：

`entry -> main-agent -> ralph -> code-review-agent -> final delivery`

这不是临时流程，而是当前实现与后续演进都应围绕的正式执行骨架。

## 二、三类 agent 的系统定位

### 1. `main-agent`

定位：

- 主要聊天入口
- 用户会话 owner
- 轻监督与路由 agent

负责：

- 理解用户意图
- 回答轻量状态类问题
- 做最小必要的澄清
- 把 coding 请求转成标准 handoff packet / issue draft

不负责：

- 长时间 repo 推理
- 大规模编码执行
- review loop
- 代替 `ralph` 或 `code-review-agent`

### 2. `ralph`

定位：

- coding loop owner
- 本地 worktree / branch / PR owner

负责：

- 读取 issue / handoff
- 规划
- 编码
- 验证
- 开 PR
- 接收 review 结果
- 修复并重新验证

`ralph` 不只是“写代码的 agent”，而是整个 coding loop 的执行 owner。

### 3. `code-review-agent`

定位：

- review loop owner
- 结构化 findings producer

负责：

- 审查具体变更
- 识别 blocking / non-blocking finding
- 输出机器可消费的 review 结果
- 输出人可读的 review 摘要

不负责：

- 直接改代码
- 代替 `ralph` 修复问题
- 主持用户入口对话

## 三、当前正式闭环

当前 agent system 的正式闭环如下：

1. 用户从 channel / API 进入
2. `main-agent` 处理聊天、澄清、路由
3. 对于 coding 请求，`main-agent` 生成标准 handoff
4. `ralph` 接手后完成 plan -> code -> validate
5. `ralph` 创建 PR 或恢复既有 PR
6. `code-review-agent` 对 PR / workspace 执行 review
7. 如存在 blocking finding，回到 `ralph`
8. `ralph` 修复后重新验证，再次交给 `code-review-agent`
9. 最多 3 轮 review / repair
10. 当 blocking finding 清零后，由控制面统一做 final delivery

## 四、闭环约束

### 1. `main-agent` 约束

- 必须把 coding 请求收成可执行 handoff
- 可以回答状态问题，但不能吞掉真正的 coding 请求
- 不能越权执行长链路任务

### 2. `ralph` 约束

- 每次编码都要有 plan
- 行为变更必须带验证
- review 之前必须有验证结果或明确验证缺口
- 不能跳过 PR 和 review 直接宣布完成

### 3. `code-review-agent` 约束

- 必须输出结构化 findings
- `P0/P1` 视为 blocking
- finding 必须足够具体，能直接驱动 repair
- 不以风格偏好制造 blocking loop

## 五、最多 3 轮的 review / repair contract

当前正式规则：

- 第 1 轮 review 后，若存在 blocking finding，回到 `ralph`
- `ralph` 修复后必须重新验证
- 再次进入 review
- 整个 repair loop 最多 3 轮

达到上限后：

- 不再无限循环
- 控制面必须记录失败或 handoff 状态
- 最终由系统显式暴露为需要人工介入，而不是静默卡住

## 六、通知与交付规则

飞书通知不应在链路中间乱发成功信号。

正式规则：

- issue 创建时可发“任务开始”通知
- 中间 review / repair 可发过程通知，但不能冒充成功交付
- 只有在 review loop 通过后，才能发送 final delivery

这保证用户看到的“完成”与真实系统状态一致。

## 七、handoff 设计原则

handoff 必须让下一个 agent 不需要重新猜上下文。

最小 handoff 必须包含：

- 当前目标
- 上游来源
- 受影响 repo / workspace
- 当前状态
- 已完成工作
- 未完成工作
- acceptance / validation
- blocker 或 risk
- 下一个 agent 需要立刻做的动作

handoff 的详细格式以 `docs/handoffs/README.md` 与模板为准。

## 八、与旧设计文档的关系

上一轮关于 framework layering、public surface、多 endpoint、RAG MVP 的设计已经完成使命。

它们仍然可以解释历史推导过程，但不再是当前 agent system 的主入口。当前实现与后续执行应优先以本文件、agent runtime contracts、RAG provider surface 和当前 plans 为准。

## 九、实现原则补充

当前系统在实现层默认遵循：

- `agent-first`
- `LLM + MCP + skill first`
- 仅对权限、门禁、状态投影、artifact contract 做确定性编排

如果某项能力本质上属于理解、规划、review 推理或 handoff 组织，应优先交给 agent，而不是继续下沉成更细的流程代码。
