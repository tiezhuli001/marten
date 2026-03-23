# Agent-First Implementation Principles

> 更新时间：2026-03-23
> 文档角色：`docs/architecture` 下的实现边界文档
> 目标：明确 `Marten` 在 2026 年阶段应坚持的 `agent-first` / `LLM + MCP + skill first` 原则，避免实现重新退回到重编排、重状态机、弱 agent 的 2024 式做法。

## 一、核心判断

`Marten` 的默认实现原则是：

- 优先让 agent 通过 `LLM + MCP + skill` 完成理解、规划、review、repair 与 handoff
- 仅把必须确定性的边界、权限、门禁、状态投影与 artifact contract 收回到代码
- 不把本应由 agent 决策的认知工作过度固化成流程编排代码

换句话说：

> 控制面可以工程化，认知面不应过度工程化。

## 二、哪些地方必须继续 agent-first

下面这些能力，应优先交给 agent，而不是继续写死在运行时代码里：

### 1. 请求理解与任务拆分

- 用户请求是否需要澄清
- 需求应如何压缩成单个 coding unit
- 哪些上下文最 relevant
- 如何表述 acceptance / constraint 才更利于执行

代码只保留最小安全边界，不替 agent 做完整语义理解。

### 2. 编码方案与修复策略

- 先改哪里
- 哪个实现路径最小可行
- blocking finding 应按什么顺序修
- 修复时是否需要补测试、补验证、补注释

这些属于 `ralph` 的核心认知能力，不应逐步变成硬编码 repair playbook。
同样，标准主链上的本地编码 ownership 也应继续保留在 `ralph`，而不是默认外包给外部 execution command。

### 3. review 推理本身

- finding 是否成立
- 严重级别如何判断
- 哪些建议属于 blocking
- 哪些建议只是可选优化

代码只需要收口结构化输出与审批门禁，不应该把 review 结论主体重写成规则引擎。
标准主链上的 review ownership 应继续保留在 `code-review-agent`，而不是默认外包给外部 review command。

### 4. skill / MCP 选择与调用策略

- 当前问题更适合先查代码还是先跑验证
- 是否需要走 GitHub MCP、workspace MCP、RAG retrieval
- 哪些 skill 组合最适合当前任务

这应主要体现在 agent prompt、skill contract、tool availability 上，而不是散落在大量 orchestration if/else 中。

补充：

- RAG 首先是工程检索层：检索、过滤、去重、裁剪、注入策略都应由 runtime policy 管理
- 不应把“有 retrieval”简化成“把检索结果原样拼进 system prompt”

## 三、哪些地方应该降工程编排

下面这些模式，是当前代码后续需要警惕和收缩的方向：

### 1. 用大量离散状态替代 agent 判断

如果某段逻辑只是为了决定：

- 下一句怎么说
- 这轮怎么总结
- 这次 review 如何组织内容
- 这次 handoff 怎么描述

优先交给 agent 按 schema 输出，而不是继续堆状态分支。

### 2. 用硬编码 heuristics 覆盖本应由模型判断的细粒度语义

允许存在最小的安全 heuristics，例如：

- 明确聊天问题不要误开 coding path
- 明确交付门禁不能绕过

但不应把大量业务语义、任务拆分和意图细分都改写成关键词路由器。

### 3. 在多个层重复表达同一规则

若某条规则已经存在于：

- architecture 文档
- `AGENTS.md`
- output schema
- review/test

就不应再在多处业务代码中重复编码一遍，除非它是强约束门禁。

### 4. 用流程代码替代 artifact contract

优先做法应是：

- 稳定 `handoff`
- 稳定 `coding_artifact`
- 稳定 `machine_output`
- 稳定 `human_output`

而不是不断增加隐式字段和特殊状态，让下游只能依赖具体实现细节。

### 5. 用宽松 fallback 掩盖关键失败

如果 coding runtime、review runtime、structured output 或上下文组装失败，默认应显式失败或进入 `needs_attention`。

不应为了“让链路继续走完”而：

- 自动把 review 解释成 non-blocking
- 自动把 dry-run 解释成真实完成
- 自动把缺失 capability 解释成可接受降级

## 四、哪些地方必须保持工程化

以下内容到 2026 年 3 月仍必须保留在确定性运行时里：

### 1. 权限与边界

- 哪个 agent 能做什么
- 谁可以调用哪些 MCP / workspace / GitHub 操作
- 哪些动作需要 approval 或 escalation

### 2. 交付门禁

- review 未通过不能 final delivery
- repair loop 到上限必须进入 `needs_attention`
- provider 切换不能破坏统一 retrieval contract
- coding/review/runtime 关键失败不能被 permissive fallback 掩盖

### 3. 结构化输出与状态投影

- chat / coding handoff mode
- review machine / human outputs
- task / control task 的对齐状态
- 手工介入与失败状态显式暴露

### 4. 可验证 contract

- schema
- 回归测试
- control task payload
- handoff 文档

这些属于系统可信度，而不是“过度工程化”。

## 五、当前代码库的具体审计清单

下面清单用于后续每轮实现前后自查。

### A. 应继续坚持 agent-first 的部分

- `main-agent` 的聊天回复、澄清、handoff 文字组织，应主要由 model 输出，不要把回复模板继续写死在 gateway 或 control plane
- `ralph` 的 plan、execution draft、repair strategy，应继续由 agent + skill 驱动，不要演化成固定步骤脚本
- `code-review-agent` 的 finding 生成与修复建议，应保持 model-first，代码只消费结构化结果
- retrieval 的 query formulation、citation selection、上下文裁剪策略，应优先由 agent/runtime policy 决定，而不是 provider adapter 写死

### B. 应降工程编排的热点

- `main-agent` 中基于关键词的 `_should_route_to_coding()` 只能保留为最小兜底，不应继续膨胀成主路由逻辑
- `automation` 中 review loop 的状态分支应控制规模；若继续扩展，优先收成少数明确 gate，而不是引入更多中间状态
- `ralph` / `code-review-agent` payload 目前仍有若干 `dict[str, Any]`，后续应优先升级为显式 schema，而不是继续追加自由字段
- 任何“为了稳定输出”而新增的字符串约定、事件名约定、payload patch 约定，都应先判断能否改成 schema + tests，而不是继续叠编排代码

### C. 允许保留的确定性控制

- `main-agent` 不滥用 coding path
- 3 轮 blocking 后进入 `needs_attention`
- final delivery 必须以 review approved 为前置条件
- provider 切换不影响 retrieval contract
- builtin coding/review capability 缺失时显式失败

这些是系统边界，不是应交给模型自由发挥的部分。

## 六、默认决策规则

今后当实现上出现“该写代码约束，还是交给 agent”这个问题时，默认按下面顺序判断：

1. 如果这是权限、门禁、状态一致性或跨系统 contract，写代码约束
2. 如果这是理解、规划、review 推理或文本组织，优先交给 agent
3. 如果这是 retrieval 注入、prompt 预算、context 裁剪，优先先补 runtime context policy，而不是平铺字符串
4. 如果代码约束只是为了弥补 schema 不稳定，优先先补 schema 与测试
5. 如果新逻辑需要引入多个额外状态，先反问能否收敛成更少 gate

## 七、落地要求

后续任何 agent system 相关改动，都应至少同步检查：

- 是否增强了 agent 能力，而不是削弱 agent
- 是否把控制面和认知面混在一起
- 是否新增了不必要的状态机复杂度
- 是否能通过 schema、handoff、tests 替代额外编排代码

如果答案偏向“新增了大量流程代码，只是为了让 agent 看起来稳定”，默认视为偏离本原则。
