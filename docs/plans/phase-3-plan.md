# Phase 3 Plan

> 阶段名称：Code Review 能力
> 目标：补齐睡后编程后的 review 回路，形成受控的软件工程交付链
> 对应设计：[phase-3-code-review.md](/Users/litiezhu/workspace/github/youmeng-gateway/docs/architecture/phase-3-code-review.md)

## 一、阶段目标

本阶段的核心不是“再写一个 agent”，而是把代码交付从“能提 PR”提升到“能稳定 review 和回退”。

完成后应具备：

1. 自动生成 review 摘要
2. 区分 blocking 与 non-blocking 评论
3. 跟踪 review 决策
4. 将 `request_changes` 接回 sleep_coding

## 二、范围

### 本阶段要做

- Review 状态模型
- 自动 review 摘要生成
- PR 评论回写
- `request_changes` -> 重新编码 流转
- Review 决策写库

### 本阶段不做

- 完整静态分析平台
- 安全审计深度能力
- 多 reviewer 协作策略

## 三、核心任务

### Task 3.1 Review 状态建模

- 定义 `in_review / changes_requested / approved`
- 落库到任务状态

### Task 3.2 自动 Review 摘要

- 从变更 diff 中产出结构化 review 摘要
- 输出风险、测试缺口、需人工确认点

### Task 3.3 PR 评论回写

- 将 review 摘要写回 PR
- 记录回写时间和对应 task

### Task 3.4 Review 决策流转

- 支持 `approve`
- 支持 `request_changes`
- 支持 `cancel`

## 四、阶段产出

- Review 状态模型
- 自动 review 摘要生成器
- PR 评论回写能力
- changes requested 回流机制

## 五、阶段通过标准

- [ ] PR 可生成自动 review 摘要
- [ ] `request_changes` 可回流至 coding
- [ ] 最终 review 决策可持久化
