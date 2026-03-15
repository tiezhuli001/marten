# Phase 2 Design Prep: Sleep Coding MVP

> 更新时间：2026-03-15
> 目标：为 `Phase 2` 的睡后编程最小闭环提供设计基线

## 目标

`Sleep Coding MVP` 要解决的不是“自动完成所有开发”，而是先跑通一个受控的软件工程闭环：

```text
用户提出需求
-> 生成 GitHub Issue
-> 进入 sleep_coding 工作流
-> 生成实施计划
-> 编码与本地验证
-> 创建 PR
-> 触发 Review
-> 用户确认
-> merge / return
-> 记录 token 和状态
```

## 设计原则

1. 人工确认必须保留
2. 先支持单任务串行，不做并发调度
3. 先支持单仓库，不做多仓库治理
4. 先保证状态可追踪，再追求自动化程度
5. 编码失败要允许回退和重试

## MVP 边界

### In Scope

- 从 GitHub Issue 启动任务
- 生成任务计划
- 在工作分支内修改代码
- 本地执行最小验证
- 创建 PR
- 输出 review 摘要
- 等待人工确认

### Out of Scope

- 自动 merge 到 `main`
- 多 agent 并行协作
- 长链路自我修复
- 飞书内直接完成所有审批动作

## 推荐工作流

### Step 1. 任务创建

输入来源：

- 用户直接发需求到 Gateway
- 或用户手动先建 GitHub Issue

建议统一化：

- 所有 `sleep_coding` 请求都落成 GitHub Issue
- `issue_number` 作为任务外部主键

### Step 2. 任务入队

写入内部任务状态：

- `task_id`
- `issue_number`
- `repo`
- `base_branch`
- `head_branch`
- `status`

### Step 3. 计划生成

输出：

- 任务理解
- 修改范围
- 验证方式
- 风险点

建议产物：

- 评论回写到 Issue
- 同步写入 `docs/status/current-status.md`

### Step 4. 编码执行

执行方式建议：

- 由 worker 在独立工作目录进行
- 分支命名规则固定，例如 `codex/issue-123-sleep-coding`

输入：

- Issue 内容
- 相关文档
- 当前代码上下文

输出：

- 代码修改
- 本地测试结果
- 变更摘要

### Step 5. PR 创建

输出：

- PR 标题
- PR 描述
- 关联 Issue
- 本地验证结果

### Step 6. Review 阶段

至少区分两种 review：

1. 自动 review 摘要
2. 用户人工 review

### Step 7. 人工确认

确认结果：

- approve
- request_changes
- cancel

### Step 8. 结束与记账

沉淀内容：

- task 最终状态
- PR 链接
- token 消耗
- 错误日志
- 当前阶段进度更新

## Phase 2 前置依赖

在正式进入 Phase 2 编码前，应先满足：

1. Phase 1 验收通过
2. GitHub Token / API 可用
3. worker 工作目录策略确定
4. PR 模板和 Issue 模板确定
5. token ledger 查询接口草案确定

## 推荐 API / 事件边界

### Gateway

- `POST /gateway/message`
- `POST /tasks/sleep-coding`

### GitHub Integration

- 创建 Issue
- 读取 Issue
- 创建 PR
- 获取 PR 状态
- 写评论

### Token Ledger

- 请求级写入
- 工作流级写入
- 任务级聚合

## 验收目标

Phase 2 MVP 完成时，至少要证明：

1. 可以从一个真实 Issue 启动任务
2. 可以生成真实代码修改并通过最小测试
3. 可以自动创建 PR
4. 可以把执行状态和 token 消耗沉淀下来
