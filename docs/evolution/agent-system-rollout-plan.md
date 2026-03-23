# Agent System Rollout Plan

> 更新时间：2026-03-22
> 文档角色：`docs/evolution` 下的当前 rollout 文档
> 目标：把 `Marten` 的三 agent 主链收口为工程上可用、可交接、可持续演进的正式 agent system。

## 一、目标状态

完成后，`Marten` 应具备下面这些特征：

- `main-agent` 是正式聊天入口，但不会吞掉重执行任务
- `ralph` 是 coding loop owner，而不只是写代码工具
- `code-review-agent` 的输出同时适合机器循环和人类阅读
- 任何 agent 都能靠 handoff、architecture 文档和 plans 继续工作

## 二、范围

本轮只做下面几类事：

- 收紧三 agent 的文档 contract
- 明确 review / repair 最多 3 轮的正式规则
- 固化 handoff 文档格式
- 用 plans 把后续实现拆成可执行步骤

本轮不做：

- 大规模运行时重构
- 新增私有 agent
- 重做 control plane

## 三、分阶段推进

### Stage 1: 文档入口收口

目标：

- 明确哪些是当前真相文档
- 明确哪些是历史文档
- 让后续 agent 不再从旧设计推演当前实现

### Stage 2: Agent System Canonicalization

目标：

- 固化 `main-agent -> ralph -> code-review-agent` 正式闭环
- 固化状态机、handoff、review loop 和 final delivery 规则

### Stage 3: Agent Contract Tightening

目标：

- 让三个 builtin agent 的 contract 与当前系统规则对齐
- 补齐 allowed work / forbidden work / output contract / failure mode

### Stage 4: Implementation Rollout

目标：

- 用详细 plan 驱动后续实现修改
- 确保任何新 agent 都可从文档继续执行

## 四、验收标准

当下面条件同时成立时，说明本轮 agent system 文档工作完成：

1. `docs/README.md` 已明确 current vs historical
2. 当前 agent system 有单独 canonical architecture 文档
3. 三个 builtin agent 的系统级 contract 已固定
4. handoff 模板存在且可直接使用
5. 至少一份实现计划可以让陌生 agent 继续执行而不依赖口头上下文

当前状态：以上条件已满足。本轮后续实现也已经把关键 contract 下沉到 runtime 输出与测试。

## 五、后续实现的强约束

后续实现 agent system 时，必须遵守：

- `main-agent` 不承担长执行链
- `ralph` 必须拥有 review / repair loop
- `code-review-agent` 不直接改代码
- review / repair 最多 3 轮
- final delivery 只在 blocking finding 清零后发生
